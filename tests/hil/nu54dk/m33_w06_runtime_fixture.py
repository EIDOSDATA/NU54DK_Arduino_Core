#!/usr/bin/env python3
"""! @brief W06의 두 runtime fixture를 현재 exact source와 세 보드에서 생성합니다. """
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any, Callable


HIL = Path(__file__).resolve().parent
ROOT = HIL.parents[2]
TOOLS = ROOT / "tools/bluetooth"
CI = ROOT / "tools/ci"
for module_root in (HIL, TOOLS, CI):
    if str(module_root) not in sys.path:
        sys.path.insert(0, str(module_root))

import m33_ecosystem_hil as ecosystem  # noqa: E402
import m33_w06_artifacts as artifacts  # noqa: E402
import m33_execution as execution  # noqa: E402
from ble_pair_hil_common import flash_image_pyocd_sha256  # noqa: E402
from m6_serial_echo import import_pyserial  # noqa: E402
from m32_ble_capability_run import (  # noqa: E402
    collect_register_identity_sha256,
    discover,
)
from m33_sdk_risk_common import (  # noqa: E402
    exact_program_evidence,
    readback_programmed_images,
    reserve_sidecars,
    validate_programming_receipt,
)


SCHEMA_VERSION = 1
KIND = "m33_w06_runtime_producer"
ROLES = ("client", "peer", "third")
SHA256 = re.compile(r"[0-9a-f]{64}")
PROFILE_SLOTS = {
    "server": (
        ("m33_profiles_native", "hex-server"),
        ("m33_profiles_native", "build-record-server"),
        "native",
        "server",
    ),
    "client": (
        ("m33_profiles_native", "hex-client"),
        ("m33_profiles_native", "build-record-client"),
        "native",
        "client",
    ),
    "watcher": (
        ("m33_profiles_native", "hex-watcher-idle"),
        ("m33_profiles_native", "build-record-watcher-idle"),
        "standard",
        "watcher",
    ),
}
FORBIDDEN_COMMAND_TOKENS = (
    "mass-erase",
    "mass_erase",
    "auto-unlock",
    "auto_unlock=true",
    "recover",
    "--erase=chip",
)


class RuntimeFixtureFailure(RuntimeError):
    """! @brief build·실기·증거 결합 실패를 나타냅니다. """


def digest(path: Path) -> str:
    """! @brief 파일 byte의 SHA-256을 반환합니다. """

    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_new_json(path: Path, document: dict[str, Any]) -> None:
    """! @brief 기존 파일을 덮어쓰지 않고 JSON을 기록합니다. """

    execution.write_new_json(path, document)


def ensure_safe_command(command: list[str]) -> None:
    """! @brief producer가 erase/unlock/recover 우회 명령을 만들지 못하게 합니다. """

    lowered = " ".join(command).casefold()
    if any(token in lowered for token in FORBIDDEN_COMMAND_TOKENS):
        raise RuntimeFixtureFailure("forbidden erase/unlock/recover command")


def run_checked(
    command: list[str],
    timeout: int,
    executor: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    *,
    log_root: Path | None = None,
    probe_hashes: set[str] | None = None,
) -> None:
    """! @brief 실패·timeout 출력도 보존하되 raw probe 식별자는 기록하지 않습니다. """

    ensure_safe_command(command)
    interrupted = None
    try:
        result = executor(
            command, cwd=ROOT, capture_output=True, timeout=timeout,
            check=False, shell=False,
        )
    except subprocess.TimeoutExpired as error:
        interrupted = error
        result = subprocess.CompletedProcess(command, -1, error.stdout, error.stderr)
    if log_root is not None:
        from m33_regression_run import _reject_raw_probe_identity_bytes

        for name, value in (("stdout", result.stdout), ("stderr", result.stderr)):
            raw = artifacts.output_bytes(value)
            _reject_raw_probe_identity_bytes(raw, "runtime " + name, probe_hashes)
            execution.write_new_bytes(log_root / (name + ".log"), raw)
        write_new_json(log_root / "command.json", {
            "command": command, "exit_code": result.returncode,
            "timeout_seconds": timeout, "timed_out": interrupted is not None,
            "stdout_sha256": digest(log_root / "stdout.log"),
            "stderr_sha256": digest(log_root / "stderr.log"),
        })
    if interrupted is not None:
        raise execution.ExecutionFailure(
            "SAFETY" if probe_hashes else "ENVIRONMENT",
            "producer timeout; inspect child evidence and current board state",
        ) from interrupted
    if result.returncode != 0:
        raise execution.ExecutionFailure(
            "INTERNAL",
            f"producer subprocess failed: {Path(command[0]).name}/{Path(command[2]).name}"
        )


def runtime_python() -> Path:
    """! @brief HIL 의존성이 설치된 현재 Python 실행기를 반환합니다. """

    python = Path(sys.executable).resolve()
    if not python.is_file():
        raise RuntimeFixtureFailure("current runtime Python executable is missing")
    return python


def index_entries(rows: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    """! @brief 검증된 W06 build row를 중복 없는 key mapping으로 변환합니다. """
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise RuntimeFixtureFailure("W06 build index entry is not an object")
        key = (row.get("campaign_id"), row.get("name"))
        if not all(isinstance(value, str) and value for value in key) or key in result:
            raise RuntimeFixtureFailure("W06 build index key mismatch")
        result[key] = row
    return result


def require_index_file(
    entries: dict[tuple[str, str], dict[str, Any]], key: tuple[str, str]
) -> Path:
    """! @brief index의 exact file byte와 기록 hash를 다시 검증합니다. """

    row = entries.get(key)
    if row is None:
        raise RuntimeFixtureFailure(f"W06 build index slot missing: {key[0]}:{key[1]}")
    path = Path(str(row.get("source", ""))).resolve()
    if (
        not path.is_file()
        or path.stat().st_size <= 0
        or SHA256.fullmatch(str(row.get("sha256", ""))) is None
        or digest(path) != row["sha256"]
    ):
        raise RuntimeFixtureFailure(f"W06 build index byte mismatch: {key[0]}:{key[1]}")
    return path


def load_profile_inputs(
    plan_path: Path,
    index_path: Path,
    sdk_root: Path | None = None,
    toolchain_root: Path | None = None,
) -> tuple[dict[str, dict[str, Path]], dict[str, Any]]:
    """! @brief 재결합한 current-S profile 입력을 validated W06 index에서 가져옵니다. """

    plan = artifacts.strict_json(plan_path.resolve())
    artifacts.validate_plan(plan)
    index = artifacts.strict_json(index_path.resolve())
    source = plan.get("source")
    if not isinstance(source, dict) or source.get("source_clean") is not True:
        raise RuntimeFixtureFailure("W06 build index clean source identity missing")
    current = artifacts.validate_source_lock(
        ROOT,
        sdk_root or Path(str(source.get("sdk_root", ""))),
        toolchain_root or Path(str(source.get("toolchain_root", ""))),
        str(source.get("source_revision", "")),
    )
    try:
        artifacts.validate_source_binding(source, current)
    except Exception as error:
        raise RuntimeFixtureFailure(
            "W06 build index is not exact current source"
        ) from error
    effective_source = current
    try:
        validated = artifacts.validate_index(
            plan,
            index,
            effective_source=effective_source,
        )
        relocations = artifacts.validate_relocations(index)
    except Exception as error:
        raise RuntimeFixtureFailure("W06 build index validation failed") from error
    entries = index_entries(validated)
    profiles: dict[str, dict[str, Path]] = {}
    for logical_role, (image_key, record_key, family, role) in PROFILE_SLOTS.items():
        image = require_index_file(entries, image_key)
        record = require_index_file(entries, record_key)
        try:
            artifacts.validate_profile_record(
                record,
                image,
                effective_source,
                family,
                role,
                relocations,
            )
        except Exception as error:
            raise RuntimeFixtureFailure(
                f"profile input mismatch: {logical_role}"
            ) from error
        profiles[logical_role] = {"image": image, "build_record": record}
    return profiles, effective_source


def build_ecosystem_commands(
    python: Path,
    sdk_root: Path,
    toolchain_root: Path,
    output: Path,
) -> list[list[str]]:
    """! @brief client와 peer를 고정 순서로 build하는 shell-free 명령을 만듭니다. """

    return [
        [
            str(python),
            "-B",
            str(TOOLS / "m33_ecosystem_hil.py"),
            "build",
            "--role",
            role,
            "--sdk",
            str(sdk_root),
            "--toolchain",
            str(toolchain_root),
            "--output",
            str(output / "builds" / ("ecosystem-" + role)),
        ]
        for role in ("client", "peer")
    ]


def build_ecosystem_inputs(
    source: dict[str, Any],
    output: Path,
    timeout: int,
    executor: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> dict[str, dict[str, Path]]:
    """! @brief 기존 ecosystem builder로 current-S 두 역할을 직렬 build합니다. """

    sdk_root = Path(source["sdk_root"]).resolve()
    bundle = artifacts.toolchain_bundle_root(Path(source["toolchain_root"]))
    python = runtime_python()
    journal = execution.StageJournal(output / ".build-stages", {
        key: value for key, value in source.items()
        if key not in {"sdk_root", "toolchain_root"}
    })
    result: dict[str, dict[str, Path]] = {}
    expected_identity = ecosystem.source_identity()
    for role in ("client", "peer"):
        def validate(attempt: Path) -> None:
            """! @brief 재사용 build의 모든 최종 byte와 exact source를 검사합니다. """

            root = attempt / "builds" / ("ecosystem-" + role)
            document = execution.read_json(root / "build-manifest.json")
            execution.require(
                document.get("role") == role and
                document.get("identity") == expected_identity and
                document.get("source_revision") == source["source_revision"] and
                document.get("source_clean") is True and
                document.get("identity_stable") is True and
                document.get("exit_code") == 0,
                "ecosystem exact build mismatch: " + role,
            )
            for field, relative in (("image", "build/zephyr/zephyr.hex"),
                                    ("elf", "build/zephyr/zephyr.elf"),
                                    ("config", "build/zephyr/.config")):
                execution.require(digest(root / relative) == document.get(field + "_sha256"),
                                  "ecosystem build byte drift: " + role + ":" + field)

        def build(attempt: Path) -> list[Path]:
            """! @brief 실패한 역할만 새 attempt의 격리 경로에서 빌드합니다. """

            commands = build_ecosystem_commands(python, sdk_root, bundle, attempt)
            command = commands[0 if role == "client" else 1]
            run_checked(command, timeout, executor, log_root=attempt / "command")
            root = attempt / "builds" / ("ecosystem-" + role)
            return [root / "build-manifest.json", root / "build.log",
                    root / "build/zephyr/zephyr.hex", root / "build/zephyr/zephyr.elf",
                    root / "build/zephyr/.config"]

        attempt = journal.run("build-" + role, {"role": role}, build, validate)
        root = attempt / "builds" / ("ecosystem-" + role)
        record = root / "build-manifest.json"
        image = root / "build/zephyr/zephyr.hex"
        document = json.loads(record.read_text(encoding="utf-8"))
        if (
            document.get("role") != role
            or document.get("identity") != expected_identity
            or document.get("source_revision") != source["source_revision"]
            or document.get("source_clean") is not True
            or document.get("identity_stable") is not True
            or document.get("image_sha256") != digest(image)
        ):
            raise RuntimeFixtureFailure(f"ecosystem exact build mismatch: {role}")
        result[role] = {"image": image.resolve(), "build_record": record.resolve()}
    return result


def profile_commands(
    python: Path,
    source: dict[str, Any],
    profiles: dict[str, dict[str, Path]],
    probe_hashes: dict[str, str],
    output: Path,
) -> tuple[list[str], list[str], list[str]]:
    """! @brief 제한 cleanup 뒤 native fresh와 idle exporter 명령을 만듭니다. """

    mapping = (
        ("server", "client", profiles["server"]),
        ("client", "peer", profiles["client"]),
        ("watcher", "third", profiles["watcher"]),
    )
    commands = []
    for phase in ("cleanup", "fresh"):
        command = [
            str(python),
            "-B",
            str(HIL / "m33_profile_run.py"),
            "--family",
            "native",
            "--native-security-phase",
            phase,
            "--sdk-root",
            source["sdk_root"],
        ]
        for profile_role, physical_role, values in mapping:
            command.extend((
                "--role",
                profile_role,
                probe_hashes[physical_role],
                str(values["image"]),
                "--build-record",
                profile_role,
                str(values["build_record"]),
            ))
        command.extend((
            "--output-prefix",
            str(output / f"profile-{phase}"),
            "--execute",
        ))
        commands.append(command)
    prefix = output / "profile-fresh"
    fixture = output / "third-idle" / "third-idle-fixture.json"
    export = [
        str(python),
        "-B",
        str(HIL / "m33_profile_idle_fixture.py"),
        "--evidence",
        str(prefix.with_suffix(".json")),
        "--build-record",
        str(profiles["watcher"]["build_record"]),
        "--output",
        str(fixture),
    ]
    return commands[0], commands[1], export


def copy_ecosystem_inputs(
    fixture_path: Path,
    inputs: dict[str, dict[str, Path]],
) -> tuple[dict[str, dict[str, Path]], dict[str, dict[str, str]]]:
    """! @brief ecosystem image와 JSON build record를 인접 sidecar로 보존합니다. """

    roles = ("client", "peer")
    sidecars = reserve_sidecars(fixture_path, roles)
    records: dict[str, dict[str, str]] = {}
    for role in roles:
        shutil.copyfile(inputs[role]["image"], sidecars[role]["image"])
        shutil.copyfile(inputs[role]["build_record"], sidecars[role]["build_record"])
        if digest(sidecars[role]["image"]) != digest(inputs[role]["image"]):
            raise RuntimeFixtureFailure(f"ecosystem copied image mismatch: {role}")
        records[role] = {"record_sha256": digest(sidecars[role]["build_record"])}
    return sidecars, records


def _serial_ready(
    serial_module: Any,
    endpoints: dict[str, tuple[str, str]],
    identity: str,
) -> list[str]:
    """! @brief software reset 뒤 client/peer가 현재 image READY인지 직렬 확인합니다. """

    transcript: list[str] = []
    for role in ("client", "peer"):
        port_name, _raw_uid = endpoints[role]
        port = serial_module.Serial(
            port_name, 115200, timeout=0.1, write_timeout=1.0
        )
        try:
            port.reset_input_buffer()
            endpoint = ecosystem.Endpoint(port, role, identity, transcript)
            endpoint.send("STATUS")
            ready = endpoint.receive("READY")
            if ready["links"] != 0:
                raise RuntimeFixtureFailure(f"ecosystem {role} did not start disconnected")
        finally:
            port.close()
    return transcript


def audit_third_board(
    hashes: dict[str, str],
    ports: dict[str, str],
    fixture_path: Path,
    backend: Any | None = None,
) -> dict[str, Any]:
    """! @brief third watcher를 halt한 뒤 radio·HEX·lifecycle RAM을 읽기 전용 검사합니다. """

    import m33_diagnostics as diagnostics

    watcher = diagnostics.load_watcher_fixture(
        fixture_path,
        digest(fixture_path),
        hashes["third"],
    )
    backend = backend or diagnostics.PyocdPreparationBackend()
    with diagnostics.private_debug_output():
        probes, live_ports = backend.discover()
        mapped = diagnostics.map_live_probes(
            probes,
            live_ports,
            [hashes[role] for role in ROLES],
            [ports["client"], ports["peer"]],
        )
        with backend.session(mapped[2]) as session:
            monitor = diagnostics.RawResetMonitor(session.target)
            diagnostics.halt_and_wait(session.target, monitor)
            isolation = diagnostics.verify_isolation(session.target, monitor)
            readback = diagnostics.readback_ranges(
                session.target,
                watcher["image"]["ranges"],
                monitor=monitor,
            )
            lifecycle = diagnostics.verify_watcher_ram(
                session.target,
                watcher,
                monitor,
            )
    return {
        "probe_sha256": hashes["third"],
        "state": "halted_verified",
        "radio": isolation,
        "readback": readback,
        "lifecycle_ram": lifecycle,
        "fixture_sha256": digest(fixture_path),
    }


def validate_third_board_audit(
    value: dict[str, Any],
    hashes: dict[str, str],
    ports: dict[str, str],
    fixture_path: Path,
) -> dict[str, Any]:
    """! @brief 저장된 third halt/radio/image/RAM audit 전체를 다시 검증합니다. """

    import m33_diagnostics as diagnostics

    if (
        set(hashes) != set(ROLES)
        or len(set(hashes.values())) != 3
        or any(SHA256.fullmatch(item) is None for item in hashes.values())
        or set(ports) != {"client", "peer"}
        or len({item.casefold() for item in ports.values()}) != 2
    ):
        raise RuntimeFixtureFailure("third audit board denominator mismatch")
    fixture_hash = digest(fixture_path)
    watcher = diagnostics.load_watcher_fixture(
        fixture_path, fixture_hash, hashes["third"]
    )
    if not isinstance(value, dict) or set(value) != {
        "probe_sha256", "state", "radio", "readback", "lifecycle_ram",
        "fixture_sha256",
    }:
        raise RuntimeFixtureFailure("third audit schema mismatch")
    if (
        value["probe_sha256"] != hashes["third"]
        or value["state"] != "halted_verified"
        or value["fixture_sha256"] != fixture_hash
    ):
        raise RuntimeFixtureFailure("third audit identity mismatch")
    expected_readback = [
        {
            "start": start,
            "length": len(raw),
            "expected_sha256": diagnostics.digest_bytes(raw),
            "observed_sha256": diagnostics.digest_bytes(raw),
            "status": "PASS",
        }
        for start, raw in watcher["image"]["ranges"]
    ]
    if value["readback"] != expected_readback:
        raise RuntimeFixtureFailure("third audit image readback mismatch")
    expected_ram = []
    ram_values = {
        "nonce": watcher["data"]["nonce"].encode("ascii") + b"\0",
        "started": b"\0",
        "cleanup_complete": b"\1",
        "stop_reported": b"\1",
        "failed": b"\0",
        "watchdog_channel": b"\xff" * 4,
    }
    for name, symbol in watcher["symbols"].items():
        raw = ram_values[name]
        expected_ram.append({
            **symbol,
            "name": name,
            "read_sha256": diagnostics.digest_bytes(raw),
            "read_value": raw[:-1].decode("ascii") if name == "nonce" else
            int.from_bytes(raw, "little", signed=name == "watchdog_channel"),
            "expected_sha256": diagnostics.digest_bytes(raw),
            "status": "PASS",
            "elf_sha256": watcher["data"]["files"]["elf"]["sha256"],
            "image_sha256": watcher["image"]["sha256"],
            "source_revision": watcher["data"]["revisions"]["core"],
        })
    if value["lifecycle_ram"] != expected_ram:
        raise RuntimeFixtureFailure("third audit lifecycle RAM mismatch")
    radio = value["radio"]
    if not isinstance(radio, dict) or set(radio) != {
        "cpu", "radio_state_address", "radio_state", "registers",
        "reset_observed", "read_only",
    }:
        raise RuntimeFixtureFailure("third audit radio schema mismatch")
    registers = radio["registers"]
    route_addresses = [
        diagnostics.RADIO_BASE + offset
        for offset in diagnostics.RADIO_SUBSCRIBE + diagnostics.RADIO_PUBLISH
    ]
    route_addresses.extend(
        base + offset
        for base in diagnostics.WDT_BASES
        for offset in diagnostics.WDT_ROUTES
    )
    expected_registers = {"dhcsr_halt"}
    expected_registers.update(f"0x{address:08x}" for address in route_addresses)
    expected_registers.add(f"0x{diagnostics.RADIO_BASE + 0x400:08x}")
    expected_registers.add(f"0x{diagnostics.RADIO_STATE:08x}")
    for base in diagnostics.WDT_BASES:
        expected_registers.update({
            f"0x{base + 0x100:08x}",
            f"0x{base + 0x400:08x}",
            f"0x{base + 0x50C:08x}",
        })
    if (
        radio["cpu"] != "HALTED"
        or radio["radio_state_address"] != diagnostics.RADIO_STATE
        or radio["radio_state"] != diagnostics.RADIO_DISABLED
        or radio["reset_observed"] is not False
        or radio["read_only"] is not True
        or not isinstance(registers, dict)
        or set(registers) != expected_registers
        or registers["dhcsr_halt"] != diagnostics.DHCSR_HALTED
        or any(registers[f"0x{address:08x}"] & (1 << 31)
               for address in route_addresses)
        or registers[f"0x{diagnostics.RADIO_BASE + 0x400:08x}"] != 0
        or registers[f"0x{diagnostics.RADIO_STATE:08x}"] != 0
    ):
        raise RuntimeFixtureFailure("third audit radio isolation mismatch")
    for base in diagnostics.WDT_BASES:
        if (
            registers[f"0x{base + 0x100:08x}"] != 0
            or registers[f"0x{base + 0x400:08x}"] & 1
            and registers[f"0x{base + 0x50C:08x}"] & 8
        ):
            raise RuntimeFixtureFailure("third audit watchdog isolation mismatch")
    return value


def prepare_ecosystem_fixture(
    output: Path,
    inputs: dict[str, dict[str, Path]],
    probe_hashes: dict[str, str],
    third_fixture: Path,
) -> Path:
    """! @brief 두 ecosystem 보드를 순차 기록하고 third를 read-only audit합니다. """

    from m33_diagnostics import HashedProbeLocks, private_debug_output

    fixture_path = output / "ecosystem-fixture.json"
    preflight_path = output / "ecosystem-preflight.json"
    sidecars, build_records = copy_ecosystem_inputs(fixture_path, inputs)
    serial_module, list_ports = import_pyserial()
    discovered = {
        role: discover(probe_hashes[role], list_ports)
        for role in ROLES
    }
    raw_ids = {role: discovered[role][0] for role in ROLES}
    ports = {role: discovered[role][2] for role in ROLES}
    if (
        len(set(raw_ids.values())) != 3
        or len({value.casefold() for value in ports.values()}) != 3
    ):
        raise RuntimeFixtureFailure("three exact boards must have distinct probes and ports")
    identity = ecosystem.source_identity()
    images = {role: sidecars[role]["image"] for role in ("client", "peer")}
    flash_records: dict[str, dict[str, str]] = {}
    debug_identity: dict[str, dict[str, str]] = {}
    report: dict[str, Any] = {
        "schema_version": 1,
        "kind": "m33_w06_ecosystem_preflight",
        "status": "FAIL",
        "source_revision": identity[:40],
        "source_clean": True,
        "execution_order": [],
        "safety": {
            "erase": "sector_only",
            "auto_unlock": False,
            "mass_erase": False,
            "automatic_recover": False,
            "software_reset": True,
            "external_device": False,
            "host_track": False,
        },
    }
    try:
        with HashedProbeLocks(list(probe_hashes.values())):
            for role in ("client", "peer"):
                debug_identity[role] = collect_register_identity_sha256(
                    probe_hashes[role], discovered[role][1]
                )
                mode, programmed = flash_image_pyocd_sha256(
                    role,
                    probe_hashes[role],
                    images[role],
                    120.0,
                )
                flash_records[role] = {"mode": mode, "bytes": programmed}
                report["execution_order"].append(role + ":sector-program-software-reset")
            with private_debug_output():
                readbacks, receipt = readback_programmed_images(
                    {role: raw_ids[role] for role in ("client", "peer")},
                    {role: probe_hashes[role] for role in ("client", "peer")},
                    images,
                    sidecars,
                )
            validate_programming_receipt(receipt, ("client", "peer"), readbacks)
            transcript = _serial_ready(
                serial_module,
                {role: (ports[role], raw_ids[role]) for role in ("client", "peer")},
                identity,
            )
            report["execution_order"].append("client-peer:readback-ready")
            report["third"] = audit_third_board(
                probe_hashes,
                ports,
                third_fixture,
            )
            validate_third_board_audit(
                report["third"], probe_hashes,
                {role: ports[role] for role in ("client", "peer")},
                third_fixture,
            )
            report["execution_order"].append("third:halt-read-only-audit")
        report["exact_program"] = exact_program_evidence(
            ("client", "peer"),
            {role: probe_hashes[role] for role in ("client", "peer")},
            sidecars,
            flash_records,
            build_records,
            readbacks,
        )
        report["debug_identity"] = debug_identity
        report["transcript"] = transcript
        report["status"] = "PASS"
    except Exception as error:
        report["error_type"] = type(error).__name__
        write_new_json(preflight_path, report)
        raise RuntimeFixtureFailure("ecosystem three-board preparation failed") from None
    write_new_json(preflight_path, report)
    boards = []
    for role in ("client", "peer"):
        boards.append({
            "role": role,
            "probe_sha256": probe_hashes[role],
            "port": ports[role],
            "readback": "verified",
            "image": str(sidecars[role]["image"].resolve()),
            "image_sha256": digest(sidecars[role]["image"]),
            "build_record": str(sidecars[role]["build_record"].resolve()),
            "build_record_sha256": digest(sidecars[role]["build_record"]),
            "flash": report["exact_program"][role]["flash"],
        })
    fixture = {
        "schema_version": 1,
        "other_radios": "isolated_verified",
        "test_owned_bond_cleanup": True,
        "identity": identity,
        "preflight_evidence": str(preflight_path.resolve()),
        "preflight_sha256": digest(preflight_path),
        "boards": boards,
        "isolated_probe_sha256": [probe_hashes["third"]],
    }
    ecosystem.validate_fixture(fixture)
    write_new_json(fixture_path, fixture)
    return fixture_path


def runtime_manifest(
    source: dict[str, Any],
    ecosystem_fixture: Path,
    third_fixture: Path,
) -> dict[str, Any]:
    """! @brief artifact bind CLI가 소비할 정확히 두 runtime input을 만듭니다. """

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "status": "PASS",
        "source_revision": source["source_revision"],
        "source_clean": True,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "runtime_inputs": [
            {
                "campaign_id": "m33_ecosystem",
                "name": "fixture",
                "kind": "fixture",
                "path": str(ecosystem_fixture.resolve()),
                "sha256": digest(ecosystem_fixture),
            },
            {
                "campaign_id": "m33_diagnostics_dtm",
                "name": "third-idle-fixture",
                "kind": "fixture",
                "path": str(third_fixture.resolve()),
                "sha256": digest(third_fixture),
            },
        ],
        "safety": {
            "probe_identity": "sha256-only",
            "board_count": 3,
            "execution": "sequential",
            "erase": "sector_only",
            "auto_unlock": False,
            "mass_erase": False,
            "automatic_recover": False,
            "external_device": False,
            "host_track": False,
        },
    }


def validate_probe_hashes(args: argparse.Namespace) -> dict[str, str]:
    """! @brief 서로 다른 세 SHA-256만 실물 identity 입력으로 허용합니다. """

    values = {role: getattr(args, role + "_probe_sha256") for role in ROLES}
    if any(SHA256.fullmatch(value) is None for value in values.values()):
        raise RuntimeFixtureFailure("probe identity must be lowercase SHA-256")
    if len(set(values.values())) != 3:
        raise RuntimeFixtureFailure("three distinct probe SHA-256 values are required")
    return values


def _produce(
    args: argparse.Namespace,
    executor: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    prepared_inputs: tuple[dict, dict] | None = None,
) -> dict[str, Any]:
    """! @brief 불변 build와 상태 의존 fixture cycle을 별도 checkpoint로 실행합니다. """

    hashes = validate_probe_hashes(args)
    output = args.output.resolve()
    profiles, source = prepared_inputs or load_profile_inputs(
        args.plan,
        args.build_index,
        getattr(args, "sdk_root", None),
        getattr(args, "toolchain_root", None),
    )
    toolchain_bundle = artifacts.toolchain_bundle_root(Path(source["toolchain_root"]))
    for protected in (
        ROOT.resolve(),
        Path(source["sdk_root"]).resolve(),
        toolchain_bundle,
    ):
        if output.is_relative_to(protected):
            raise RuntimeFixtureFailure("producer output must be outside source/SDK/toolchain")
    output.mkdir(parents=True, exist_ok=True)
    ecosystem_inputs = build_ecosystem_inputs(
        source,
        output,
        args.timeout_seconds,
        executor,
    )
    python = runtime_python()
    plan = {
        "schema_version": 1,
        "kind": "m33_w06_runtime_producer_plan",
        "status": "NOT_RUN",
        "source_revision": source["source_revision"],
        "probe_sha256": hashes,
        "builds": {
            role: {
                name: {"path": str(path.resolve()), "sha256": digest(path)}
                for name, path in values.items()
            }
            for role, values in ecosystem_inputs.items()
        },
        "physical_sequence": [
            "profile-native-cleanup:current-nonce-peer-only",
            "profile-native-fresh:server-client-watcher",
            "third-idle-read-only-export",
            "ecosystem-client:sector-program-reset-readback",
            "ecosystem-peer:sector-program-reset-readback",
            "third:halt-read-only-audit",
        ],
        "safety": {
            "erase": "sector_only",
            "auto_unlock": False,
            "mass_erase": False,
            "automatic_recover": False,
            "external_device": False,
            "host_track": False,
        },
    }
    plan_path = output / "runtime-producer-plan.json"
    if plan_path.exists():
        execution.require(execution.read_json(plan_path) == plan,
                          "runtime producer plan/input drift")
    else:
        write_new_json(plan_path, plan)
    if not args.execute:
        return plan
    if not all((
        args.authorize_sector_program,
        args.authorize_software_reset,
        args.authorize_three_board_hil,
    )):
        raise RuntimeFixtureFailure("three explicit physical execution authorizations are required")
    binding = {
        "source": {key: value for key, value in source.items()
                   if key not in {"sdk_root", "toolchain_root"}},
        "probe_sha256": hashes,
        "profiles": {role: {name: digest(path) for name, path in values.items()}
                     for role, values in profiles.items()},
        "builds": {role: {name: digest(path) for name, path in values.items()}
                   for role, values in ecosystem_inputs.items()},
    }
    journal = execution.StageJournal(output / ".runtime-stages", binding)

    def run_cycle(attempt: Path) -> list[Path]:
        """! @brief 중단 후 mutable 보드 상태 chain 전체를 새 attempt에 준비합니다. """

        _run_fixture_cycle(attempt, source, profiles, hashes, ecosystem_inputs,
                           python, args.timeout_seconds, executor)
        return sorted(path for path in attempt.rglob("*") if path.is_file())

    def validate_cycle(attempt: Path) -> None:
        """! @brief 원래 production fixture validator로 재개 결과를 확인합니다. """

        artifacts.runtime_producer_paths({"source": source}, attempt / "runtime-producer.json")

    completed = journal.run("fixture-cycle", {"timeout_seconds": args.timeout_seconds},
                            run_cycle, validate_cycle)
    manifest = execution.read_json(completed / "runtime-producer.json")
    final = output / "runtime-producer.json"
    if final.exists():
        execution.require(execution.read_json(final) == manifest,
                          "runtime producer final manifest drift")
    else:
        write_new_json(final, manifest)
    return manifest


def _run_fixture_cycle(
    output: Path, source: dict, profiles: dict, hashes: dict,
    ecosystem_inputs: dict, python: Path, timeout: int,
    executor: Callable[..., subprocess.CompletedProcess],
) -> None:
    """! @brief cleanup·fresh·idle export·ecosystem의 물리 의존 순서를 보존합니다. """

    cleanup_command, run_command, export_command = profile_commands(
        python, source, profiles, hashes, output,
    )
    run_checked(cleanup_command, timeout, executor,
                log_root=output / "commands/cleanup", probe_hashes=set(hashes.values()))
    cleanup_evidence = output / "profile-cleanup.json"
    cleanup = json.loads(cleanup_evidence.read_text(encoding="utf-8"))
    if (
        cleanup.get("status") != "PASS"
        or cleanup.get("family") != "native"
        or cleanup.get("native_security_phase") != "cleanup"
        or cleanup.get("revisions", {}).get("core") != source["source_revision"]
        or set(cleanup.get("native_cleanup", {}).get("cleaned", {}))
           != {"server", "client"}
    ):
        raise RuntimeFixtureFailure("current-S scoped native cleanup evidence did not PASS")
    run_checked(run_command, timeout, executor,
                log_root=output / "commands/fresh", probe_hashes=set(hashes.values()))
    profile_evidence = output / "profile-fresh.json"
    profile = json.loads(profile_evidence.read_text(encoding="utf-8"))
    if (
        profile.get("status") != "PASS"
        or profile.get("family") != "native"
        or profile.get("native_security_phase") != "fresh"
        or profile.get("revisions", {}).get("core") != source["source_revision"]
    ):
        raise RuntimeFixtureFailure("current-S native fresh profile evidence did not PASS")
    run_checked(export_command, timeout, executor,
                log_root=output / "commands/idle-export", probe_hashes=set(hashes.values()))
    third_fixture = output / "third-idle/third-idle-fixture.json"
    ecosystem_fixture = prepare_ecosystem_fixture(
        output,
        ecosystem_inputs,
        hashes,
        third_fixture,
    )
    current = artifacts.validate_source_lock(
        ROOT,
        Path(source["sdk_root"]),
        Path(source["toolchain_root"]),
        source["source_revision"],
    )
    if current != source:
        raise RuntimeFixtureFailure("source changed during runtime fixture production")
    manifest = runtime_manifest(source, ecosystem_fixture, third_fixture)
    write_new_json(output / "runtime-producer.json", manifest)


def produce(
    args: argparse.Namespace,
    executor: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> dict[str, Any]:
    """! @brief 하나의 writer만 runtime root를 소유하고 완료 단계부터 재개합니다. """

    profiles, source = load_profile_inputs(
        args.plan, args.build_index, getattr(args, "sdk_root", None),
        getattr(args, "toolchain_root", None),
    )
    output = args.output.absolute()
    for protected in (ROOT.resolve(), Path(source["sdk_root"]).resolve(),
                      artifacts.toolchain_bundle_root(Path(source["toolchain_root"]))):
        if output.resolve().is_relative_to(protected):
            raise RuntimeFixtureFailure("producer output must be outside source/SDK/toolchain")
    with execution.exclusive(output):
        return _produce(args, executor, (profiles, source))


def main() -> int:
    """! @brief 기본 build-only plan과 명시 승인된 세 보드 실행을 분리합니다. """

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--build-index", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sdk-root", type=Path)
    parser.add_argument("--toolchain-root", type=Path)
    for role in ROLES:
        parser.add_argument("--" + role + "-probe-sha256", required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--authorize-sector-program", action="store_true")
    parser.add_argument("--authorize-software-reset", action="store_true")
    parser.add_argument("--authorize-three-board-hil", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    args = parser.parse_args()
    try:
        result = produce(args)
    except (
        RuntimeFixtureFailure,
        OSError,
        ValueError,
        KeyError,
        json.JSONDecodeError,
        subprocess.SubprocessError,
    ) as error:
        print(f"M33_W06_RUNTIME_PRODUCER_FAIL: {error}", file=sys.stderr)
        return 1
    print(json.dumps({
        "status": result["status"],
        "kind": result["kind"],
        "output": str((args.output.resolve() / "runtime-producer.json")
                      if result["status"] == "PASS"
                      else args.output.resolve() / "runtime-producer-plan.json"),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
