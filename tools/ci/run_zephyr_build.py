#!/usr/bin/env python3
"""! @brief M12의 대표 Zephyr target suite를 build-only로 실행합니다. """

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Sequence


REPOSITORY = Path(__file__).resolve().parents[2]
SCRIPT_ROOT = Path(__file__).resolve().parent
LOCK_MODULE_PATH = SCRIPT_ROOT / "verify_ci_lock.py"
SPEC = importlib.util.spec_from_file_location("nu54_m12_lock", LOCK_MODULE_PATH)
assert SPEC and SPEC.loader
LOCK_MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(LOCK_MODULE)
BOARD_TARGET = "nrf54l15dk/nrf54l15/cpuapp/nu54dk"
M16_APPLICATION = REPOSITORY / "tests" / "zephyr" / "m16_ble_hil"
M16_ROLE_SUITES = (
    ("peripheral", "nucode.m16.ble_hil_peripheral"),
    ("central", "nucode.m16.ble_hil_central"),
)
SUITE_GROUPS = {
    "v0.1.0": (
        ("m3_runtime", "nucode.m3.runtime"),
        ("m4_api_contract", "nucode.m4.api_contract"),
        ("m6_core_api", "nucode.m6.core_api"),
        ("m7_core_api", "nucode.m7.core_api"),
    ),
    "v0.2.0": (
        ("m14_core_contract", "nucode.m14.core_contract"),
        ("m14_variant_contract", "nucode.m14.variant_contract"),
        ("m14_pin_hil", "nucode.m14.pin_hil"),
        ("m15_board", "nucode.m15.board"),
        ("m15_hil", "nucode.m15.auto_hil"),
        ("m15_wake", "nucode.m15.wake"),
        ("m16_ble_contract", "nucode.m16.ble_contract"),
        ("m16_ble_hil", "nucode.m16.ble_hil_peripheral"),
        ("m16_ble_hil", "nucode.m16.ble_hil_central"),
        ("m17_sensor_direct", "nucode.m17.sensor_direct"),
    ),
    "v0.3.0": (
        ("m19_ble_gap_contract", "nucode.m19.ble_gap_contract"),
        ("m19_ble_gap_hil", "nucode.m19.ble_gap_hil_peripheral"),
        ("m19_ble_gap_hil", "nucode.m19.ble_gap_hil_central"),
        ("m20_ble_gatt_contract", "nucode.m20.ble_gatt_contract"),
        ("m20_ble_gatt_hil", "nucode.m20.ble_gatt_hil_peripheral"),
        ("m20_ble_gatt_hil", "nucode.m20.ble_gatt_hil_central"),
        ("ac01_contract", "nucode.ac01.contract"),
        ("ac01_hil", "nucode.ac01.gpio_hil"),
        ("ac02a_ownership_contract", "nucode.ac02a.ownership_contract"),
        ("ac02b_b2_contract", "nucode.ac02b.b2_contract"),
        ("ac02b_analog_contract", "nucode.ac02b.analog_contract"),
        ("ac02b_hil_dut", "nucode.ac02b.hil_dut"),
        ("ac02b_hil_peer", "nucode.ac02b.hil_peer"),
        ("ac03_storage_contract", "nucode.ac03.storage_contract"),
        ("ac03_hil", "nucode.ac03.storage_hil"),
    ),
    "v0.4.0": (
        ("m23_inventory_contract", "nucode.m23.inventory_contract"),
        ("m24_serial_fabric_contract", "nucode.m24.fabric"),
        ("m24_uarte_driver_contract", "nucode.m24.uarte"),
        ("m24_spi_driver_contract", "nucode.m24.spi"),
        ("m24_twi_driver_contract", "nucode.m24.twi"),
        ("m24_uarte_onboard_hil", "nucode.m24.uarte20_hil"),
        ("m24_uarte_onboard_hil", "nucode.m24.uarte21_hil"),
        ("m24_uarte_onboard_hil", "nucode.m24.uarte22_hil"),
        ("m24_uarte_onboard_hil", "nucode.m24.uarte30_hil"),
        ("m24_twim_onboard_hil", "nucode.m24.twim20_hil"),
        ("m24_twim_onboard_hil", "nucode.m24.twim21_hil"),
        ("m24_twim_onboard_hil", "nucode.m24.twim22_hil"),
        ("m25_analog_fabric_contract", "nucode.m25.analog"),
        ("m25_event_fabric_contract", "nucode.m25.event"),
        ("m25_stream_fabric_contract", "nucode.m25.stream"),
        ("m25_onboard_hil", "nucode.m25.onboard_hil"),
        ("m26_system_fabric_contract", "nucode.m26.system"),
    ),
}
SUITES = tuple(suite for group in SUITE_GROUPS.values() for suite in group)
WINDOWS_OUTDIR_MAX_LENGTH = 8
M15_DIRECTORIES = ("m15_board", "m15_hil", "m15_wake")


class BuildFailure(RuntimeError):
    """! @brief 대표 Zephyr build 계약 실패를 나타냅니다. """


## @brief 파일 byte의 SHA-256을 계산합니다.
def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


## @brief Windows 도구의 MAX_PATH 영향을 피할 수 있는 짧은 출력 경로인지 검사합니다.
def validate_outdir_path(outdir: Path) -> None:
    if os.name == "nt" and len(str(outdir)) > WINDOWS_OUTDIR_MAX_LENGTH:
        raise BuildFailure(
            "Windows Twister outdir가 너무 깁니다. "
            f"{WINDOWS_OUTDIR_MAX_LENGTH}자 이하의 짧은 절대 경로를 사용하십시오: "
            r"예: C:\t\m12"
        )


## @brief Twister 결과가 정확한 build-only suite 집합인지 검사합니다.
def validate_report(
    report_path: Path, suites_to_validate: Sequence[tuple[str, str]] = SUITES
) -> None:
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BuildFailure(f"Twister 결과를 읽지 못했습니다: {error}") from error
    suites = report.get("testsuites")
    if not isinstance(suites, list):
        raise BuildFailure("Twister testsuites가 배열이 아닙니다.")
    expected = {scenario for _directory, scenario in suites_to_validate}
    actual: set[str] = set()
    for suite in suites:
        if not isinstance(suite, dict):
            raise BuildFailure("Twister suite record가 object가 아닙니다.")
        name = suite.get("name")
        if not isinstance(name, str) or name in actual:
            raise BuildFailure("Twister suite 이름이 없거나 중복됩니다.")
        actual.add(name)
        if (
            suite.get("platform") != BOARD_TARGET
            or suite.get("status") != "not run"
            or any(
                not isinstance(testcase, dict)
                or testcase.get("status") != "not run"
                or testcase.get("reason") != "Test was built only"
                for testcase in suite.get("testcases", [])
            )
        ):
            raise BuildFailure(f"Twister build-only 결과가 PASS가 아닙니다: {name}")
    if actual != expected:
        raise BuildFailure(f"Twister suite 집합이 다릅니다: {sorted(actual)}")


## @brief 실패한 Twister suite와 사유를 한 줄 진단으로 요약합니다.
def failure_summary(report_path: Path) -> str:
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        return f"twister.json unavailable ({error})"
    suites = report.get("testsuites")
    if not isinstance(suites, list):
        return "twister.json testsuites is not an array"
    failures: list[str] = []
    for suite in suites:
        if not isinstance(suite, dict):
            continue
        status = str(suite.get("status", "unknown"))
        if status == "not run":
            continue
        name = str(suite.get("name", "unknown-suite"))
        reason = str(suite.get("reason", "no reason"))
        failures.append(f"{name}: {status} ({reason})")
    return "; ".join(failures[:8]) or "failed suite was not recorded"


## @brief M15 target의 생성 DTS가 NU54DK 외부 LFXO 커패시터 구성을 사용하는지 검사합니다.
def validate_m15_lfxo(
    outdir: Path, suites_to_validate: Sequence[tuple[str, str]] = SUITES
) -> None:
    platform_directory = BOARD_TARGET.replace("/", "_")
    scenario_by_directory = dict(suites_to_validate)
    for directory in M15_DIRECTORIES:
        if directory not in scenario_by_directory:
            continue
        devicetree_path = (
            outdir
            / platform_directory
            / "zephyr_gnu"
            / scenario_by_directory[directory]
            / directory
            / "zephyr"
            / "zephyr.dts"
        )
        if not devicetree_path.is_file():
            raise BuildFailure(f"M15 생성 devicetree가 없습니다: {devicetree_path}")
        devicetree = devicetree_path.read_text(encoding="utf-8")
        marker = "lfxo: lfxo {"
        start = devicetree.find(marker)
        end = devicetree.find("\n\t\t};", start)
        if start < 0 or end < 0:
            raise BuildFailure(f"M15 LFXO node를 찾지 못했습니다: {directory}")
        body = devicetree[start:end]
        if (
            'load-capacitors = "external";' not in body
            or "load-capacitance-femtofarad" in body
        ):
            raise BuildFailure(f"M15 외부 LFXO 부하 커패시터 계약이 다릅니다: {directory}")


## @brief 한 M16 role build가 role·board·source·산출물을 정확히 반영했는지 검사합니다.
def validate_m16_role_build(build_directory: Path, role: str) -> dict[str, Any]:
    roles = {entry_role for entry_role, _scenario in M16_ROLE_SUITES}
    if role not in roles:
        raise BuildFailure(f"알 수 없는 M16 role입니다: {role}")
    image_directory = build_directory / "m16_ble_hil"
    required_files = {
        "cache": build_directory / "CMakeCache.txt",
        "commands": image_directory / "compile_commands.json",
        "build_info": image_directory / "build_info.yml",
        "record": image_directory / "nucode_arduino_core_build.yml",
        "hex": image_directory / "zephyr" / "zephyr.hex",
        "elf": image_directory / "zephyr" / "zephyr.elf",
    }
    for label, path in required_files.items():
        if not path.is_file() or path.stat().st_size <= 0:
            raise BuildFailure(f"M16 {role} {label} 산출물이 없습니다: {path}")

    cache = required_files["cache"].read_text(encoding="utf-8", errors="strict")
    role_cache = f"M16_ROLE:UNINITIALIZED={role}"
    if role_cache not in cache:
        raise BuildFailure(f"M16 {role} CMake role 전달을 확인하지 못했습니다.")

    build_info = required_files["build_info"].read_text(
        encoding="utf-8", errors="strict"
    )
    normalized_application = M16_APPLICATION.as_posix()
    if (
        f"qualifiers: 'nrf54l15/cpuapp/nu54dk'" not in build_info
        or normalized_application not in build_info.replace("\\", "/")
    ):
        raise BuildFailure(f"M16 {role} build identity가 target 계약과 다릅니다.")

    try:
        commands = json.loads(required_files["commands"].read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BuildFailure(f"M16 {role} compile_commands를 읽지 못했습니다: {error}") from error
    if not isinstance(commands, list):
        raise BuildFailure(f"M16 {role} compile_commands가 배열이 아닙니다.")
    main_commands: list[str] = []
    for command in commands:
        if not isinstance(command, dict):
            raise BuildFailure(f"M16 {role} compile command record가 object가 아닙니다.")
        source = command.get("file")
        if not isinstance(source, str) or not source.replace("\\", "/").endswith(
            "/tests/zephyr/m16_ble_hil/src/main.cpp"
        ):
            continue
        if isinstance(command.get("command"), str):
            main_commands.append(command["command"])
        elif isinstance(command.get("arguments"), list) and all(
            isinstance(argument, str) for argument in command["arguments"]
        ):
            main_commands.append(" ".join(command["arguments"]))
        else:
            raise BuildFailure(f"M16 {role} main.cpp compile command 형식이 잘못됐습니다.")
    if len(main_commands) != 1:
        raise BuildFailure(
            f"M16 {role} main.cpp compile command 수가 정확히 1이 아닙니다: "
            f"{len(main_commands)}"
        )
    has_central_definition = "-DNUCODE_M16_CENTRAL=1" in main_commands[0]
    if has_central_definition != (role == "central"):
        raise BuildFailure(f"M16 {role} role compile definition이 다릅니다.")

    record = required_files["record"].read_text(encoding="utf-8", errors="strict")
    if (
        "board: 'nrf54l15dk'" not in record
        or "board_qualifiers: 'nrf54l15/cpuapp/nu54dk'" not in record
    ):
        raise BuildFailure(f"M16 {role} build record target이 다릅니다.")
    return {
        "role": role,
        "status": "build-only-passed",
        "validation_scope": "image-build-only",
        "scenario": dict(M16_ROLE_SUITES)[role],
        "role_compile_definition": (
            "NUCODE_M16_CENTRAL=1" if role == "central" else "absent"
        ),
        "hex_size": required_files["hex"].stat().st_size,
        "hex_sha256": file_sha256(required_files["hex"]),
        "elf_size": required_files["elf"].stat().st_size,
        "elf_sha256": file_sha256(required_files["elf"]),
        "build_record_sha256": file_sha256(required_files["record"]),
    }


## @brief Twister가 만든 M16 peripheral·central image를 role별로 검증합니다.
def validate_m16_role_builds(
    outdir: Path, suites_to_validate: Sequence[tuple[str, str]] = SUITES
) -> list[dict[str, Any]]:
    selected_scenarios = {scenario for _directory, scenario in suites_to_validate}
    selected_roles = tuple(
        (role, scenario)
        for role, scenario in M16_ROLE_SUITES
        if scenario in selected_scenarios
    )
    if not selected_roles:
        return []
    if selected_roles != M16_ROLE_SUITES:
        raise BuildFailure("M16 peripheral·central role은 같은 build 그룹에 있어야 합니다.")
    platform_directory = BOARD_TARGET.replace("/", "_")
    records: list[dict[str, Any]] = []
    for role, scenario in selected_roles:
        scenario_directory = (
            outdir / platform_directory / "zephyr_gnu" / scenario
        )
        records.append(validate_m16_role_build(scenario_directory, role))
    if records[0]["hex_sha256"] == records[1]["hex_sha256"]:
        raise BuildFailure(
            "M16 peripheral과 central HEX가 같아 role 분리를 확인하지 못했습니다."
        )
    return records


## @brief exact NCS workspace에서 고정된 target suite만 빌드합니다.
def run_build(
    workspace: Path,
    outdir: Path,
    lock: dict[str, Any],
    suites_to_build: Sequence[tuple[str, str]] = SUITES,
    jobs: int = 2,
) -> list[dict[str, Any]]:
    LOCK_MODULE.validate_workspace(workspace, lock)
    validate_outdir_path(outdir)
    if outdir.exists():
        raise BuildFailure(f"Twister outdir는 실행 전에 없어야 합니다: {outdir}")
    board_root = REPOSITORY / "board_package" / "NU54DK_Zephyr_DTS"
    if LOCK_MODULE.git_revision(board_root) != lock["board"]["revision"]:
        raise BuildFailure("checkout된 board submodule이 M12 lock과 다릅니다.")
    command: list[str | Path] = [sys.executable, workspace / "zephyr" / "scripts" / "twister"]
    for directory, _scenario in suites_to_build:
        command.extend(("--testsuite-root", REPOSITORY / "tests" / "zephyr" / directory))
    command.extend(
        (
            "--platform",
            BOARD_TARGET,
            "--board-root",
            board_root / "boards",
            "--build-only",
            "--ninja",
            "--detailed-test-id",
            "--jobs",
            str(jobs),
            "--outdir",
            outdir,
            "--extra-args",
            f"BOARD_ROOT={board_root.as_posix()}",
            "--extra-args",
            f"EXTRA_ZEPHYR_MODULES={REPOSITORY.as_posix()}",
            "--extra-args",
            "USE_CCACHE=0",
        )
    )
    for _directory, scenario in suites_to_build:
        command.extend(("--scenario", scenario))
    environment = dict(os.environ)
    environment["ZEPHYR_BASE"] = str(workspace / "zephyr")
    environment["CCACHE_DISABLE"] = "1"
    print(f"[M12-ZEPHYR] exec: {subprocess.list2cmdline([str(item) for item in command])}")
    result = subprocess.run(command, cwd=workspace, env=environment, check=False)
    if result.returncode != 0:
        summary = failure_summary(outdir / "twister.json")
        raise BuildFailure(
            f"Twister가 종료 코드 {result.returncode}로 실패했습니다. 실패 위치: {summary}"
        )
    validate_report(outdir / "twister.json", suites_to_build)
    validate_m15_lfxo(outdir, suites_to_build)
    return validate_m16_role_builds(outdir, suites_to_build)


## @brief 대표 Zephyr build를 실행하고 고정 identity evidence를 기록합니다.
def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument("--lock", type=Path, default=SCRIPT_ROOT / "ncs-3.4.0.lock.json")
    parser.add_argument(
        "--group",
        choices=("all", *SUITE_GROUPS),
        default="all",
        help="현재 source에서 검증할 릴리스 도입 기능군",
    )
    parser.add_argument("--jobs", type=int, choices=range(1, 9), default=2)
    args = parser.parse_args(arguments)
    lock = LOCK_MODULE.strict_json_object(args.lock.resolve())
    LOCK_MODULE.validate_lock(lock)
    workspace = args.workspace.resolve()
    outdir = args.outdir.resolve()
    outdir.parent.mkdir(parents=True, exist_ok=True)
    selected_suites = SUITES if args.group == "all" else SUITE_GROUPS[args.group]
    m16_role_builds = run_build(
        workspace, outdir, lock, selected_suites, args.jobs
    )
    evidence = {
        "schema_version": 2,
        "gate": "m12-zephyr-build-only",
        "status": "passed",
        "group": args.group,
        "jobs": args.jobs,
        "board": BOARD_TARGET,
        "scenarios": [scenario for _directory, scenario in selected_suites],
        "m16_role_builds": m16_role_builds,
        "ncs_revision": lock["ncs"]["revision"],
        "zephyr_revision": lock["zephyr"]["revision"],
        "container_digest": lock["linux_toolchain_container"]["digest"],
    }
    (outdir / "m12-build-evidence.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(
        f"M12_ZEPHYR_BUILD_PASS={len(selected_suites)};"
        f"GROUP={args.group};M16_ROLE_BUILDS={len(m16_role_builds)}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (BuildFailure, LOCK_MODULE.LockFailure) as error:
        print(f"M12_ZEPHYR_BUILD_FAIL: {error}", file=sys.stderr)
        raise SystemExit(1) from error
