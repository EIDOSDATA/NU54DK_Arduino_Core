#!/usr/bin/env python3
"""! @brief 세 NU54DK에서 M32-W11 유한 GATT soak를 실행합니다. """

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys


HIL = Path(__file__).resolve().parent
REPOSITORY = HIL.parents[2]
APPLICATION_ROOT = REPOSITORY / "tests" / "zephyr" / "m32_regression_soak_hil"
FIRMWARE_SOURCE = REPOSITORY / "tests" / "zephyr" / "m28_ble_3board_hil" / "src" / "main.cpp"
if str(HIL) not in sys.path:
    sys.path.insert(0, str(HIL))
TOOLS = REPOSITORY / "tools" / "bluetooth"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from ble_pair_hil_common import (  # noqa: E402
    BOARD_ROOT,
    BlePairHilFailure,
    RoleEndpoint,
    build_nonce,
    file_sha256,
    git_revision,
    protocol_lines,
    take_exact,
    validate_hex_image,
    validate_image_unchanged,
)
from m6_serial_echo import DaplinkVolume, import_pyserial, read_details  # noqa: E402
from m28_ble_3board import (  # noqa: E402
    ROLES,
    ThreeBoardExecutionFailure,
    execute_three_board,
)
from m32_ble_capability import ExpectedIdentity  # noqa: E402
from m32_ble_capability_run import collect_register_identity, discover  # noqa: E402
from m33_regression import intel_hex_ranges, read_json  # noqa: E402
sys.path.insert(0, str(APPLICATION_ROOT))
from m33_w06_manifest import current_source_digests  # noqa: E402
from v04_protocol import ProbeLocks  # noqa: E402


TEST_ID = "M32-SOAK-01:primary"
PACKET_DENOMINATOR = 10000
ALLOWED_LOSS = 100
LATENCY_LIMIT_MS = 500
RECOVERY_TIMEOUT_MS = 30000
SOAK_DURATION_SECONDS = 1800
SOURCE_MANIFEST_FIELDS = (
    "core_revision",
    "board_revision",
    "ncs_revision",
    "zephyr_revision",
    "core_source_sha256",
    "application_source_sha256",
    "board_source_sha256",
    "firmware_source_sha256",
    "application_cmake_sha256",
    "application_config_sha256",
)
BUILD_SOURCE_FIELDS = (
    "core_source_sha256",
    "application_source_sha256",
    "board_source_sha256",
)

_SOAK_HARDWARE_AUTHORITY = object()


@dataclass(frozen=True)
class _SoakHardwareRuntime:
    """! @brief 3보드 실행 call stack에서만 생성하는 비직렬화 receipt입니다. """
    authority: object
    nonce: str
    roles: tuple[str, ...]
    probe_sha256: tuple[str, ...]
    image_sha256: tuple[str, ...]
    transcript_sha256: tuple[str, ...]
    flash_mode: tuple[str, ...]
    flash_bytes: tuple[int, ...]
    readback_sha256: tuple[str, ...]
    active_started_ns: int
    active_finished_ns: int


def _validate_soak_runtime(runtime: _SoakHardwareRuntime, nonce: str,
                           boards: dict, images: dict[str, Path],
                           transcripts: dict[str, bytes], flash_records: dict,
                           readback_records: dict, active_interval: dict) -> None:
    """! @brief flash/START/FINAL/readback을 수행한 동일 프로세스 receipt를 검증합니다. """
    if not (
        runtime.authority is _SOAK_HARDWARE_AUTHORITY
        and runtime.nonce == nonce
        and runtime.roles == tuple(ROLES)
        and runtime.probe_sha256 == tuple(boards[role]["probe_sha256"] for role in ROLES)
        and runtime.image_sha256 == tuple(file_sha256(images[role]) for role in ROLES)
        and runtime.transcript_sha256 == tuple(
            hashlib.sha256(transcripts[role]).hexdigest() for role in ROLES
        )
        and runtime.flash_mode == tuple(flash_records[role]["mode"] for role in ROLES)
        and runtime.flash_bytes == tuple(int(flash_records[role]["bytes"])
                                         for role in ROLES)
        and runtime.readback_sha256 == tuple(
            hashlib.sha256(json.dumps(readback_records[role], sort_keys=True,
                                      separators=(",", ":")).encode("utf-8")).hexdigest()
            for role in ROLES
        )
        and runtime.active_started_ns == active_interval.get("started_ns")
        and runtime.active_finished_ns == active_interval.get("finished_ns")
        and runtime.active_finished_ns > runtime.active_started_ns
    ):
        raise RegressionSoakFailure("production soak same-process receipt mismatch")


class RegressionSoakFailure(BlePairHilFailure):
    """! @brief W11 mapping·image·protocol·evidence 실패를 나타냅니다. """


def source_manifest(
    identity: ExpectedIdentity,
    build_records: dict[str, dict[str, str]],
) -> dict[str, str]:
    """! @brief image와 원본 build record가 공유해야 할 source manifest를 계산합니다. """
    if set(build_records) != set(ROLES):
        raise RegressionSoakFailure("세 역할 build record가 모두 필요합니다")
    build_sources: dict[str, str] = {}
    for field in BUILD_SOURCE_FIELDS:
        values = {build_records[role].get(field, "") for role in ROLES}
        if len(values) != 1 or not re.fullmatch(r"[0-9a-f]{64}", next(iter(values))):
            raise RegressionSoakFailure(f"역할별 build source digest 불일치: {field}")
        build_sources[field] = next(iter(values))
    manifest = {
        "core_revision": identity.core,
        "board_revision": identity.board,
        "ncs_revision": identity.ncs,
        "zephyr_revision": identity.zephyr,
        **build_sources,
        "firmware_source_sha256": file_sha256(FIRMWARE_SOURCE),
        "application_cmake_sha256": file_sha256(APPLICATION_ROOT / "CMakeLists.txt"),
        "application_config_sha256": file_sha256(APPLICATION_ROOT / "prj.conf"),
    }
    encoded = "\n".join(f"{key}={manifest[key]}" for key in SOURCE_MANIFEST_FIELDS)
    manifest["sha256"] = hashlib.sha256(encoded.encode("ascii")).hexdigest()
    return manifest


def _identity_suffix(manifest: dict[str, str]) -> bytes:
    """! @brief compile-time image identity의 고정 UART suffix를 반환합니다. """
    fields = "".join(f":{key}={manifest[key]}" for key in SOURCE_MANIFEST_FIELDS)
    return f"{fields}:source_manifest_sha256={manifest['sha256']}".encode("ascii")


def _parse_role(
    transcript: bytes,
    nonce: str,
    role: str,
    manifest: dict[str, str] | None = None,
) -> dict[str, int | str]:
    """! @brief 한 역할의 10,000 packet·gap·cleanup 결과를 검증합니다. """
    lines = protocol_lines(transcript, "M28B3", nonce)
    identity_suffix = b"" if manifest is None else _identity_suffix(manifest)
    ready = f"NUCODE_M28B3_READY:role={role}:test=SOAK".encode("ascii") + identity_suffix
    cursor = take_exact(
        lines,
        0,
        ready,
    )
    while cursor < len(lines) and lines[cursor] == ready:
        cursor += 1
    suffix = f":nonce={nonce}".encode("ascii")
    if role in ("peripheral", "mixed"):
        cursor = take_exact(
            lines,
            cursor,
            f"NUCODE_M28B3_{role}:ADVERTISE:PASS:test=SOAK".encode("ascii")
            + suffix,
        )
    expected_tx = PACKET_DENOMINATOR if role in ("mixed", "central") else 0
    expected_rx = PACKET_DENOMINATOR if role in ("peripheral", "mixed") else 0
    cursor = take_exact(
        lines,
        cursor,
        (
            f"NUCODE_M28B3_{role}:TRACE:PASS:test=SOAK:source=rf-gatt"
            f":tx={expected_tx}:rx={expected_rx}"
        ).encode("ascii")
        + suffix,
    )
    if cursor >= len(lines):
        raise RegressionSoakFailure(f"{role} SOAK result 누락")
    link_count = 2 if role == "mixed" else 1
    sequence_field = "sequence_per_link" if role == "mixed" else "sequence"
    pattern = re.compile(
        (
            rf"NUCODE_M28B3_{role}:SOAK:PASS:duration_s={SOAK_DURATION_SECONDS}"
            rf":links={link_count}:{sequence_field}={PACKET_DENOMINATOR}"
            r":loss=0:corrupt=0:duplicate=0:unexpected_disconnect=0"
            r":recovery_failures=0:drops=0:max_gap_ms=([0-9]+)"
            r":cleanup_ms=([0-9]+):cleanup=pass"
            rf":nonce={nonce}"
        ).encode("ascii")
    )
    matched = pattern.fullmatch(lines[cursor])
    if matched is None:
        raise RegressionSoakFailure(f"{role} SOAK result 불일치")
    cursor += 1
    maximum_gap_ms = int(matched.group(1))
    cleanup_ms = int(matched.group(2))
    if maximum_gap_ms > LATENCY_LIMIT_MS or cleanup_ms > RECOVERY_TIMEOUT_MS:
        raise RegressionSoakFailure(f"{role} gap 또는 cleanup 상한 초과")
    if expected_rx != 0 and maximum_gap_ms == 0:
        raise RegressionSoakFailure(f"{role} 수신 gap 관측 누락")
    cursor = take_exact(
        lines,
        cursor,
        f"NUCODE_M28B3_{role}:FINAL:PASS:test=SOAK".encode("ascii")
        + identity_suffix
        + suffix,
    )
    if cursor != len(lines):
        raise RegressionSoakFailure(f"{role} FINAL 뒤 protocol token 존재")
    return {
        "role": role,
        "transmitted": expected_tx,
        "received": expected_rx,
        "loss": 0,
        "corrupt": 0,
        "duplicate": 0,
        "maximum_gap_ms": maximum_gap_ms,
        "cleanup_ms": cleanup_ms,
        "cleanup": "pass",
    }


def _output_paths(prefix: Path) -> tuple[Path, dict[str, Path], dict[str, dict[str, Path]]]:
    """! @brief 덮어쓰지 않을 JSON·역할별 transcript 경로를 반환합니다. """
    evidence = prefix.with_suffix(".json")
    transcripts = {
        role: prefix.with_name(f"{prefix.name}.{role}.transcript.log")
        for role in ROLES
    }
    artifacts = {
        role: {
            "image": prefix.with_name(f"{prefix.name}.{role}.image.hex"),
            "build_record": prefix.with_name(f"{prefix.name}.{role}.build-record.txt"),
            "readback": prefix.with_name(f"{prefix.name}.{role}.readback.json"),
            "flash_record": prefix.with_name(f"{prefix.name}.{role}.flash.json"),
        }
        for role in ROLES
    }
    pending = evidence.with_name(evidence.name + ".pending")
    existing = [path for path in (evidence, pending, *transcripts.values(),
                                   *(path for values in artifacts.values() for path in values.values()))
                if path.exists()]
    if existing:
        raise RegressionSoakFailure("기존 W11 soak evidence를 덮어쓰지 않습니다")
    evidence.parent.mkdir(parents=True, exist_ok=True)
    return evidence, transcripts, artifacts


def _build_record_path(image: Path) -> Path:
    """! @brief CMake configure가 image build 전에 만든 full identity 원본 record를 찾습니다. """
    return image.parent.parent / "m33_w06_build_record.json"


def validate_m33_build_record(
    image: Path,
    identity: ExpectedIdentity,
    role: str,
) -> dict[str, str]:
    """! @brief 12자리 승격 없이 full revision·현재 source 원본 record를 검증합니다. """
    path = _build_record_path(image)
    record = read_json(path)
    required = {
        "schema_version", "kind", "role", "core_revision", "board_revision",
        "ncs_revision", "zephyr_revision", "core_source_sha256",
        "application_source_sha256", "board_source_sha256",
        "firmware_source_sha256", "application_cmake_sha256",
        "application_config_sha256", "source_manifest_sha256",
    }
    if set(record) != required or record.get("schema_version") != 1 or \
            record.get("kind") != "m33-w06-original-build-record" or \
            record.get("role") != role:
        raise RegressionSoakFailure("M33 full build record schema/role 불일치")
    expected_revisions = {
        "core_revision": identity.core,
        "board_revision": identity.board,
        "ncs_revision": identity.ncs,
        "zephyr_revision": identity.zephyr,
    }
    for key, expected in expected_revisions.items():
        if record.get(key) != expected or not re.fullmatch(r"[0-9a-f]{40}", record[key]):
            raise RegressionSoakFailure(f"M33 full build record revision 불일치: {key}")
    expected_sources = {
        **current_source_digests(REPOSITORY, BOARD_ROOT, APPLICATION_ROOT),
        "firmware_source_sha256": file_sha256(FIRMWARE_SOURCE),
        "application_cmake_sha256": file_sha256(APPLICATION_ROOT / "CMakeLists.txt"),
        "application_config_sha256": file_sha256(APPLICATION_ROOT / "prj.conf"),
    }
    for key, expected in expected_sources.items():
        if record.get(key) != expected or not re.fullmatch(r"[0-9a-f]{64}", record[key]):
            raise RegressionSoakFailure(f"M33 full build record source 불일치: {key}")
    manifest_values = {**expected_revisions, **expected_sources}
    encoded = "\n".join(f"{key}={manifest_values[key]}" for key in SOURCE_MANIFEST_FIELDS)
    expected_manifest = hashlib.sha256(encoded.encode("ascii")).hexdigest()
    if record.get("source_manifest_sha256") != expected_manifest:
        raise RegressionSoakFailure("M33 full build record manifest digest 불일치")
    record["record_name"] = path.name
    record["record_sha256"] = file_sha256(path)
    return record


def _write_json(path: Path, value: dict) -> None:
    """! @brief 증거 JSON을 새 파일에만 기록합니다. """
    if path.exists():
        raise RegressionSoakFailure("기존 W06 artifact를 덮어쓰지 않습니다")
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _load_pyocd_site_packages() -> None:
    """! @brief 고정 NCS bundle의 pyOCD를 readback에만 불러옵니다. """
    try:
        __import__("pyocd")
        return
    except ModuleNotFoundError:
        from pyocd_launcher import _resolve_site_packages
        site_packages = _resolve_site_packages()
        if site_packages is not None and str(site_packages) not in sys.path:
            sys.path.insert(0, str(site_packages))


def _checkout_dirty(path: Path, ignored_paths: tuple[Path, ...] = ()) -> bool:
    """! @brief exact evidence에 참여하는 checkout의 미커밋 byte를 검사합니다. """
    command = ["git", "-C", str(path), "status", "--porcelain=v1", "--untracked-files=all"]
    exclusions = []
    for ignored in ignored_paths:
        try:
            relative = ignored.resolve().relative_to(path.resolve()).as_posix()
        except ValueError:
            continue
        exclusions.append(f":(exclude){relative}")
    if exclusions:
        command.extend(["--", ".", *exclusions])
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RegressionSoakFailure("source checkout clean 상태를 확인하지 못했습니다")
    return bool(result.stdout.strip())


def _readback_programmed_images(endpoints: dict[str, RoleEndpoint], images: dict[str, Path]) -> dict[str, list[dict]]:
    """! @brief FINAL 뒤 target을 halt하여 exact HEX의 모든 programmed byte를 읽고 다시 resume합니다. """
    _load_pyocd_site_packages()
    from m33_diagnostics import (
        IdleAuditFailure,
        PyocdPreparationBackend,
        halt_and_wait,
        private_debug_output,
        readback_ranges,
        wait_for_target_state,
    )

    with private_debug_output():
        backend = PyocdPreparationBackend()
        probes, _ = backend.discover()
        by_uid = {probe.unique_id.strip().lower(): probe for probe in probes}
        if len(probes) != len(by_uid) or set(by_uid) != {endpoint.board_id for endpoint in endpoints.values()}:
            raise RegressionSoakFailure("readback probe mapping이 exact 세 보드와 다릅니다")
        records = {}
        for role in ROLES:
            ranges = intel_hex_ranges(images[role])
            with backend.session(by_uid[endpoints[role].board_id]) as session:
                failure: RegressionSoakFailure | None = None
                observed: list[dict] = []
                try:
                    monitor = halt_and_wait(session.target)
                    observed = readback_ranges(
                        session.target, ranges, monitor=monitor
                    )
                except IdleAuditFailure as error:
                    kind = error.evidence.get("kind", "unknown")
                    failure = RegressionSoakFailure(
                        f"{role} readback debugger 상태 실패: {kind}"
                    )
                except Exception as error:
                    failure = RegressionSoakFailure(
                        f"{role} readback 실패: {type(error).__name__}"
                    )
                try:
                    session.target.resume()
                    wait_for_target_state(
                        session.target, {"RUNNING", "SLEEPING"}
                    )
                except Exception as error:
                    restore_failure = RegressionSoakFailure(
                        f"{role} readback resume 실패: {type(error).__name__}"
                    )
                    if failure is not None:
                        raise RegressionSoakFailure(
                            f"{failure}; {restore_failure}"
                        ) from None
                    raise restore_failure from None
                if failure is not None:
                    raise failure
                records[role] = observed
        return records


def _save(
    evidence_path: Path,
    transcript_paths: dict[str, Path],
    evidence: dict,
    transcripts: dict[str, bytes],
    raw_uids: tuple[str, ...],
    nonce: str,
    active_interval: dict[str, int],
) -> None:
    """! @brief raw UID를 거부하고 성공·실패 원본을 원자적 순서로 보존합니다. """
    for role, raw in transcripts.items():
        lowered = raw.lower()
        if any(uid.encode("ascii") in lowered for uid in raw_uids):
            raise RegressionSoakFailure("raw probe UID가 transcript에 포함됨")
        transcript_paths[role].write_bytes(raw)
    evidence["transcripts"] = {
        role: {
            "name": transcript_paths[role].name,
            "size": len(transcripts[role]),
            "sha256": hashlib.sha256(transcripts[role]).hexdigest(),
        }
        for role in ROLES
    }
    if evidence["status"].startswith("PASS"):
        receipt = {
            "schema_version": 1,
            "kind": "pyocd-sector-uart-live-session-v1",
            "producer_sha256": evidence["producer"]["route_sha256"],
            "nonce_sha256": hashlib.sha256(nonce.encode("ascii")).hexdigest(),
            "source_manifest_sha256": evidence["source_manifest"]["sha256"],
            "active_started_ns": active_interval["started_ns"],
            "active_finished_ns": active_interval["finished_ns"],
            "roles": {
                role: {
                    "probe_sha256": evidence["boards"][role]["probe_sha256"],
                    "image_sha256": evidence["images"][role]["file"]["sha256"],
                    "readback_sha256": evidence["images"][role]["readback"]["sha256"],
                    "flash_record_sha256":
                    evidence["images"][role]["flash_record"]["sha256"],
                    "transcript_sha256": evidence["transcripts"][role]["sha256"],
                }
                for role in ROLES
            },
        }
        encoded = json.dumps(
            receipt, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        receipt["sha256"] = hashlib.sha256(encoded).hexdigest()
        evidence["execution_receipt"] = receipt
    else:
        evidence["execution_receipt"] = None
    evidence["observed_utc"] = datetime.now(timezone.utc).isoformat()
    evidence_path.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def execute(args: argparse.Namespace) -> dict:
    """! @brief exact source와 세 V2 probe에서 W11 soak를 한 번 실행합니다. """
    prefix = args.output_prefix.resolve()
    evidence_path, transcript_paths, artifact_paths = _output_paths(prefix)
    output_paths = (evidence_path, *transcript_paths.values(),
                    *(path for values in artifact_paths.values() for path in values.values()))
    lock = json.loads(
        (REPOSITORY / "tools/ci/ncs-3.4.0.lock.json").read_text(encoding="utf-8")
    )
    sdk = args.sdk_root.resolve()
    identity = ExpectedIdentity(
        git_revision(REPOSITORY),
        git_revision(BOARD_ROOT),
        git_revision(sdk / "nrf"),
        git_revision(sdk / "zephyr"),
    )
    if not all(re.fullmatch(r"[0-9a-f]{40}", value) for value in asdict(identity).values()):
        raise RegressionSoakFailure("build identity는 full 40-character revision이어야 합니다")
    if (
        identity.board != lock["board"]["revision"]
        or identity.ncs != lock["ncs"]["revision"]
        or identity.zephyr != lock["zephyr"]["revision"]
    ):
        raise RegressionSoakFailure("board/SDK revision lock mismatch")
    checkouts = (REPOSITORY, BOARD_ROOT, sdk / "nrf", sdk / "zephyr")
    dirty = any(_checkout_dirty(path, output_paths if path == REPOSITORY else ())
                for path in checkouts)
    if dirty and not args.development:
        raise RegressionSoakFailure("exact HIL에는 clean source commit이 필요합니다")

    serial_module, list_ports = import_pyserial()
    endpoints: dict[str, RoleEndpoint] = {}
    public_boards: dict[str, dict] = {}
    raw_uids: list[str] = []
    for role in ROLES:
        digest = getattr(args, f"probe_{role}_sha256")
        uid, volume, vcom = discover(digest, list_ports)
        details = read_details(Path(volume))
        if details is None:
            raise RegressionSoakFailure(f"{role} DAPLink details 누락")
        endpoints[role] = RoleEndpoint(
            uid,
            DaplinkVolume(Path(volume), details),
            vcom,
        )
        public_boards[role] = {
            "probe_sha256": digest,
            "volume": volume,
            "vcom": vcom,
        }
        raw_uids.append(uid)
    if len(set(raw_uids)) != len(ROLES):
        raise RegressionSoakFailure("세 역할이 서로 다른 probe에 매핑되지 않음")

    images = {
        role: validate_hex_image(getattr(args, f"hex_{role}")) for role in ROLES
    }
    image_sizes = {role: images[role].stat().st_size for role in ROLES}
    image_hashes = {role: file_sha256(images[role]) for role in ROLES}
    if len(set(image_hashes.values())) != len(ROLES):
        raise RegressionSoakFailure("세 역할 image가 서로 달라야 합니다")
    build_records = {
        role: validate_m33_build_record(images[role], identity, role)
        for role in ROLES
    }
    build_identity = source_manifest(identity, build_records)
    for role in ROLES:
        shutil.copyfile(images[role], artifact_paths[role]["image"])
        shutil.copyfile(_build_record_path(images[role]), artifact_paths[role]["build_record"])

    nonce = build_nonce()
    transcripts = {role: b"" for role in ROLES}
    results: dict[str, dict[str, int | str]] = {}
    flash_records: dict[str, dict[str, str]] = {}
    readback_records: dict[str, list[dict]] = {}
    host_monotonic_elapsed_ms: int | None = None
    active_interval: dict[str, int] = {}
    status = "FAIL"
    reason: str | None = None
    try:
        with ProbeLocks(raw_uids):
            for role in ROLES:
                public_boards[role]["registers"] = collect_register_identity(
                    endpoints[role].board_id,
                    endpoints[role].volume.root.as_posix(),
                )
            def record_active_interval(started_ns: int, finished_ns: int) -> None:
                """! @brief central START부터 세 FINAL까지의 host monotonic 구간만 저장합니다. """
                if active_interval:
                    raise RegressionSoakFailure("active timing callback 중복")
                if finished_ns < started_ns:
                    raise RegressionSoakFailure("active timing interval 역행")
                active_interval.update(started_ns=started_ns, finished_ns=finished_ns)

            execution = execute_three_board(
                serial_module=serial_module,
                endpoints=endpoints,
                images=images,
                test_name="SOAK",
                nonce=nonce,
                baud_rate=115200,
                flash_timeout=120.0,
                result_timeout=2100.0,
                flash_backend="pyocd-sector",
                hardware_reset=True,
                preserve_nrf54l_access=True,
                ready_replay_settle_seconds=0.25,
                ready_token_suffix=_identity_suffix(build_identity),
                active_timing_callback=record_active_interval,
            )
            if set(active_interval) != {"started_ns", "finished_ns"}:
                raise RegressionSoakFailure("active timing callback 누락")
            host_monotonic_elapsed_ms = (
                active_interval["finished_ns"] - active_interval["started_ns"]
            ) // 1000000
            for role in ROLES:
                role_execution = getattr(execution, role)
                transcripts[role] = role_execution.transcript
                validate_image_unchanged(images[role], image_sizes[role], image_hashes[role])
                results[role] = _parse_role(
                    role_execution.transcript, nonce, role, build_identity
                )
                flash_records[role] = {"mode": role_execution.flash_sequence,
                                       "bytes": role_execution.flash_bytes}
            readback_records = _readback_programmed_images(endpoints, images)
            for role in ROLES:
                readback = {"schema_version": 2, "status": "PASS", "role": role,
                            "source_revision": identity.core,
                            "source_manifest_sha256": build_identity["sha256"],
                            "probe_sha256": public_boards[role]["probe_sha256"],
                            "backend": "pyocd-live-target", "halted": True, "resumed": True,
                            "image_sha256": image_hashes[role], "ranges": readback_records[role]}
                _write_json(artifact_paths[role]["readback"], readback)
                flash = {"schema_version": 2, "status": "PASS", "role": role,
                         "source_revision": identity.core, "probe_sha256": public_boards[role]["probe_sha256"],
                         "cmsis_dap": "v2-only", "mode": flash_records[role]["mode"], "erase": "sector",
                         "auto_unlock": False, "automatic_recover": False, "mass_erase": False,
                         "source_manifest_sha256": build_identity["sha256"],
                         "image_sha256": image_hashes[role], "programmed_bytes": int(flash_records[role]["bytes"]),
                         "readback_sha256": file_sha256(artifact_paths[role]["readback"])}
                _write_json(artifact_paths[role]["flash_record"], flash)
            final_dirty = any(_checkout_dirty(path, output_paths if path == REPOSITORY else ())
                              for path in checkouts)
            dirty = dirty or final_dirty
            if final_dirty and not args.development:
                raise RegressionSoakFailure("실행 중 source checkout이 변경되었습니다")
        status = "PASS_CANDIDATE" if dirty else "PASS"
    except Exception as error:
        if isinstance(error, ThreeBoardExecutionFailure):
            transcripts.update(error.transcripts)
        reason = f"{type(error).__name__}: {error}"
        for uid in raw_uids:
            reason = reason.replace(uid, "<redacted-identity>")
        reason = re.sub(r"(?i)(?:uid|probe_id)=[^\s,;]+", "uid=<redacted>", reason)

    evidence = {
        "schema_version": 3,
        "evidence_kind": "m33_fresh_soak",
        "producer": {
            "schema_version": 1,
            "kind": "physical_hil",
            "route": "tests/hil/nu54dk/m32_regression_soak_run.py",
            "route_sha256": file_sha256(Path(__file__).resolve()),
            "protocol": "NUCODE_M28B3_SOAK_V3",
        },
        "test_ids": [TEST_ID, "M33-REG-01:representative_soak"],
        "status": status,
        "scope": "three_board_bounded_gatt_soak",
        "source_clean": not bool(dirty),
        "identity": asdict(identity),
        "source_manifest": build_identity,
        "boards": public_boards,
        "images": {
            role: {
                "role": role,
                "file": {"path": artifact_paths[role]["image"].name,
                         "sha256": file_sha256(artifact_paths[role]["image"])},
                "build_record": {"path": artifact_paths[role]["build_record"].name,
                                  "sha256": file_sha256(artifact_paths[role]["build_record"])},
                "readback": ({"path": artifact_paths[role]["readback"].name,
                              "sha256": file_sha256(artifact_paths[role]["readback"])}
                             if artifact_paths[role]["readback"].is_file() else None),
                "flash_record": ({"path": artifact_paths[role]["flash_record"].name,
                                  "sha256": file_sha256(artifact_paths[role]["flash_record"])}
                                 if artifact_paths[role]["flash_record"].is_file() else None),
                "build": build_records[role],
                "source_manifest": build_identity,
                "load_ranges": [
                    {"start": start, "length": len(data),
                     "sha256": hashlib.sha256(data).hexdigest()}
                    for start, data in intel_hex_ranges(artifact_paths[role]["image"])
                ],
            }
            for role in ROLES
        },
        "duration_seconds": SOAK_DURATION_SECONDS,
        "packet_denominator_per_link": PACKET_DENOMINATOR,
        "allowed_loss_packets": ALLOWED_LOSS,
        "observed_loss_packets": 0 if status.startswith("PASS") else None,
        "latency_limit_ms": LATENCY_LIMIT_MS,
        "recovery_timeout_s": RECOVERY_TIMEOUT_MS // 1000,
        "host_monotonic_scope": "central_start_to_all_final",
        "host_monotonic_elapsed_ms": host_monotonic_elapsed_ms,
        "results": results,
        "reason": reason,
        "safety": {
            "cmsis_dap": "v2-only",
            "auto_unlock": False,
            "erase": "sector",
            "reset": "software",
            "automatic_recover": False,
            "mass_erase": False,
            "termination": "autonomous_finite_cleanup_final",
            "stop_token": False,
        },
        "firmware_cleanup_contract": {
            "path": FIRMWARE_SOURCE.relative_to(REPOSITORY).as_posix(),
            "sha256": build_identity["firmware_source_sha256"],
            "source_manifest_sha256": build_identity["sha256"],
            "mode": "autonomous_finite_cleanup_final",
            "stop_token": False,
        },
    }
    pending_evidence = evidence_path.with_name(evidence_path.name + ".pending")
    if pending_evidence.exists():
        raise RegressionSoakFailure("기존 pending W06 evidence를 덮어쓰지 않습니다")
    _save(
        pending_evidence,
        transcript_paths,
        evidence,
        transcripts,
        tuple(raw_uids),
        nonce,
        active_interval,
    )
    if status.startswith("PASS"):
        runtime = _SoakHardwareRuntime(
            _SOAK_HARDWARE_AUTHORITY, nonce, tuple(ROLES),
            tuple(public_boards[role]["probe_sha256"] for role in ROLES),
            tuple(file_sha256(images[role]) for role in ROLES),
            tuple(hashlib.sha256(transcripts[role]).hexdigest() for role in ROLES),
            tuple(flash_records[role]["mode"] for role in ROLES),
            tuple(int(flash_records[role]["bytes"]) for role in ROLES),
            tuple(hashlib.sha256(json.dumps(
                readback_records[role], sort_keys=True, separators=(",", ":")
            ).encode("utf-8")).hexdigest() for role in ROLES),
            active_interval["started_ns"], active_interval["finished_ns"],
        )
        _validate_soak_runtime(runtime, nonce, public_boards, images, transcripts,
                               flash_records, readback_records, active_interval)
        from m33_regression_run import validate_soak
        validate_soak(pending_evidence, identity.core, development=args.development,
                      allow_physical_audit=True)
    pending_evidence.replace(evidence_path)
    if status.startswith("PASS"):
        validate_soak(evidence_path, identity.core, development=args.development,
                      allow_physical_audit=True)
        _validate_soak_runtime(runtime, nonce, public_boards, images, transcripts,
                               flash_records, readback_records, active_interval)
    return evidence


def main() -> int:
    """! @brief raw UID 없이 W11 soak 인자를 받고 기계 판정을 출력합니다. """
    parser = argparse.ArgumentParser()
    for role in ROLES:
        option = role.replace("_", "-")
        parser.add_argument(f"--probe-{option}-sha256", required=True)
        parser.add_argument(f"--hex-{option}", required=True, type=Path)
    parser.add_argument("--sdk-root", required=True, type=Path)
    parser.add_argument("--output-prefix", required=True, type=Path)
    parser.add_argument("--development", action="store_true")
    args = parser.parse_args()
    try:
        result = execute(args)
    except Exception as error:
        message = re.sub(r"(?i)\b[0-9a-f]{16,64}\b", "<redacted-identity>", str(error))
        print(
            f"M32_SOAK_HIL_FAIL: {type(error).__name__}: {message[:400]}",
            file=sys.stderr,
        )
        return 1
    print(f"M32_SOAK_HIL_STATUS={result['status']};TEST={TEST_ID}")
    return 0 if result["status"].startswith("PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
