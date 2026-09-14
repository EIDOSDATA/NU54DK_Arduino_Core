#!/usr/bin/env python3
"""! @brief M30-POWER-01 준비와 실제 USB 전원 손실 복구 HIL을 실행합니다. """

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile
import time
from typing import Any, Callable, Sequence


HIL_DIRECTORY = Path(__file__).resolve().parent
if str(HIL_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(HIL_DIRECTORY))

from ble_pair_hil_common import (  # noqa: E402
    BOARD_ROOT,
    BlePairHilFailure,
    DEFAULT_BAUD_RATE,
    REPOSITORY,
    RoleEndpoint,
    discover_endpoint,
    file_sha256,
    flash_image_pyocd,
    git_revision,
    validate_board_revision,
    validate_image_unchanged,
    validate_pair_identity,
    validate_source_clean,
)
from m30_ble_dfu import (  # noqa: E402
    APPLICATION_ROOT,
    BASE_VERSION,
    DfuSession,
    ImageArtifact,
    MAX_SMP_PACKET,
    M30DfuFailure,
    PeripheralBuild,
    artifact_evidence,
    cbor_encode,
    collect_central_build,
    collect_peripheral_build,
    endpoint_evidence,
    run_imgtool,
    validate_boot,
)
from m30_mcuboot import (  # noqa: E402
    M30BootFailure,
    erase_secondary_slot,
    validate_private_key,
)
from m6_serial_echo import (  # noqa: E402
    DAPLINK_TARGET,
    detail_value,
    import_pyserial,
    is_target_uart_interface,
    read_details,
)


MILESTONE = "M30"
RUNNER_PATH = Path(__file__).resolve()
DFU_RUNNER_PATH = HIL_DIRECTORY / "m30_ble_dfu.py"
BOOT_RUNNER_PATH = HIL_DIRECTORY / "m30_mcuboot.py"
PROTOCOL_VERSION = 1
INJECTION_POINTS = (
    "slot1_transfer",
    "image_validation_write",
    "mcuboot_test_swap",
    "new_image_first_boot",
)
CUTS_PER_POINT = 3
TOTAL_CUTS = len(INJECTION_POINTS) * CUTS_PER_POINT
CONFIRMED_VERSION = (40, 0, 0, 0)
UNCONFIRMED_VERSION = (41, 0, 0, 0)
RETRY_VERSION = (42, 0, 0, 0)
STORAGE_OFFSET = 0x174000
STORAGE_SIZE = 0x9000
POWER_STATE_PATTERN = re.compile(
    rb"^M30POWER\|1\|STATE\|bond_count=(\d+)\|rejected_bonds=(\d+)"
    rb"\|bonded=(\d+)\|settings_valid=(\d+)$"
)
WINDOW_PATTERN = re.compile(
    rb"^M30POWER\|1\|WINDOW\|point=(image_validation_write|mcuboot_test_swap)$"
)


class M30PowerFailure(RuntimeError):
    """! @brief M30-POWER-01 준비·전원 cycle·복구 검증 실패입니다. """


@dataclass(frozen=True)
class Presence:
    """! @brief DUT DAPLink MSD와 target UART의 동시 존재 상태입니다. """

    volume: bool
    port: bool

    @property
    def complete(self) -> bool:
        """! @brief MSD와 target UART가 모두 존재하는지 반환합니다. """

        return self.volume and self.port

    @property
    def absent(self) -> bool:
        """! @brief MSD와 target UART가 모두 사라졌는지 반환합니다. """

        return not self.volume and not self.port


@dataclass(frozen=True)
class PhysicalCycle:
    """! @brief 실제 USB 소실·복귀에서 측정한 시간 증거입니다. """

    absent_after_seconds: float
    absent_stable_seconds: float
    restored_after_seconds: float


def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    """! @brief 두 보드·세 build·명시적 실행 mode와 출력 경로를 고정합니다. """

    parser = argparse.ArgumentParser(
        description="M30-POWER-01 준비 또는 4지점 x 3회 실제 USB 전원 손실 HIL"
    )
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--discover-only", action="store_true")
    modes.add_argument("--prepare-only", action="store_true")
    modes.add_argument("--execute-power-cuts", action="store_true")
    parser.add_argument("--flash-preflight", action="store_true")
    parser.add_argument("--reset-bond-storage", action="store_true")
    parser.add_argument("--confirmed-build-outdir", required=True)
    parser.add_argument("--unconfirmed-build-outdir", required=True)
    parser.add_argument("--central-build-outdir", required=True)
    parser.add_argument("--peripheral-board-id", required=True)
    parser.add_argument("--central-board-id", required=True)
    parser.add_argument("--peripheral-volume")
    parser.add_argument("--central-volume")
    parser.add_argument("--peripheral-port", default="auto")
    parser.add_argument("--central-port", default="auto")
    parser.add_argument("--baud", type=int, default=DEFAULT_BAUD_RATE)
    parser.add_argument("--flash-timeout", type=float, default=120.0)
    parser.add_argument("--phase-timeout", type=float, default=1800.0)
    parser.add_argument("--power-cycle-timeout", type=float, default=120.0)
    parser.add_argument("--window-cut-timeout", type=float, default=12.0)
    parser.add_argument("--absence-stable", type=float, default=0.75)
    parser.add_argument("--trust-signing-key", required=True)
    parser.add_argument("--imgtool-python", required=True)
    parser.add_argument("--imgtool", required=True)
    parser.add_argument("--expected-core-revision")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--journal")
    parser.add_argument("--evidence")
    parser.add_argument("--nonce")
    parser.add_argument("--overwrite-manifest", action="store_true")
    return parser.parse_args(arguments)


def validate_options(args: argparse.Namespace) -> None:
    """! @brief mode별 필수값과 M30의 유한 timeout 경계를 검사합니다. """

    if not (args.discover_only or args.prepare_only or args.execute_power_cuts):
        raise M30PowerFailure("실행 mode 하나를 명시해야 합니다.")
    if args.flash_preflight and not args.prepare_only:
        raise M30PowerFailure("--flash-preflight는 --prepare-only와 함께 사용해야 합니다.")
    if args.reset_bond_storage and not (args.prepare_only and args.flash_preflight):
        raise M30PowerFailure(
            "--reset-bond-storage는 --prepare-only --flash-preflight와 함께 사용해야 합니다."
        )
    if args.execute_power_cuts and (not args.journal or not args.evidence):
        raise M30PowerFailure("실제 전원 시험에는 --journal과 --evidence가 필요합니다.")
    if not 120.0 <= args.phase_timeout <= 1800.0:
        raise M30PowerFailure("--phase-timeout은 120..1800초여야 합니다.")
    if args.flash_timeout <= 0.0 or args.power_cycle_timeout <= 0.0:
        raise M30PowerFailure("flash·power cycle timeout은 0보다 커야 합니다.")
    if not 0.5 <= args.absence_stable <= 5.0:
        raise M30PowerFailure("--absence-stable은 0.5..5.0초여야 합니다.")
    if not 2.0 <= args.window_cut_timeout < 15.0:
        raise M30PowerFailure("--window-cut-timeout은 2초 이상 15초 미만이어야 합니다.")


def build_nonce(explicit: str | None, index: int = 0) -> str:
    """! @brief 실행·attempt별 128-bit nonce를 검증하거나 생성합니다. """

    if explicit is None:
        return os.urandom(16).hex()
    if re.fullmatch(r"[0-9a-f]{32}", explicit) is None:
        raise M30PowerFailure("--nonce는 32자리 소문자 hex여야 합니다.")
    digest = hashlib.sha256(f"{explicit}:{index}".encode("ascii")).hexdigest()
    return digest[:32]


def collect_power_build(
    argument: str, core_revision: str, trust_key: Path, auto_confirm: int
) -> PeripheralBuild:
    """! @brief 일반 DFU exact 검증에 전원 target·MCUboot hook identity를 추가합니다. """

    build = collect_peripheral_build(argument, core_revision, trust_key, auto_confirm)
    app_ninja = (build.root / "m30_ble_dfu_hil/build.ninja").read_text(
        encoding="utf-8", errors="strict"
    )
    boot_configuration = (build.root / "mcuboot/zephyr/.config").read_text(
        encoding="utf-8", errors="strict"
    )
    if "NUCODE_M30_DFU_POWER_HIL=1" not in app_ninja:
        raise M30PowerFailure("Peripheral build에 M30 전원 HIL define이 없습니다.")
    for token in (
        "CONFIG_MCUBOOT_ACTION_HOOKS=y",
        "CONFIG_NUCODE_M30_POWER_HIL_MCUBOOT=y",
    ):
        if token not in boot_configuration:
            raise M30PowerFailure(f"MCUboot 전원 HIL 설정이 없습니다: {token}")
    return build


def create_power_candidates(
    confirmed: PeripheralBuild,
    unconfirmed: PeripheralBuild,
    trust_key: Path,
    imgtool_python: Path,
    imgtool: Path,
    directory: Path,
) -> dict[str, ImageArtifact]:
    """! @brief confirmed·unconfirmed·retry용 exact signed image 세 개를 생성합니다. """

    return {
        "confirmed": run_imgtool(
            confirmed.raw_bin,
            directory / "m30-power-confirmed-v40.bin",
            CONFIRMED_VERSION,
            40,
            imgtool_python,
            imgtool,
            trust_key,
        ),
        "unconfirmed": run_imgtool(
            unconfirmed.raw_bin,
            directory / "m30-power-unconfirmed-v41.bin",
            UNCONFIRMED_VERSION,
            41,
            imgtool_python,
            imgtool,
            trust_key,
        ),
        "retry": run_imgtool(
            confirmed.raw_bin,
            directory / "m30-power-retry-v42.bin",
            RETRY_VERSION,
            42,
            imgtool_python,
            imgtool,
            trust_key,
        ),
    }


def daplink_identity(endpoint: RoleEndpoint) -> dict[str, str]:
    """! @brief raw UID 없이 DAPLink firmware·target identity를 기록합니다. """

    result = endpoint_evidence(endpoint)
    result.update(
        {
            "target_detect": detail_value(endpoint.volume.details, "Target Detect")
            or "unknown",
            "daplink_version": detail_value(endpoint.volume.details, "Version")
            or "unknown",
            "daplink_git_sha": detail_value(
                endpoint.volume.details, "Git Commit SHA"
            )
            or "unknown",
        }
    )
    return result


def manifest_document(
    core_revision: str,
    board_revision: str,
    peripheral: RoleEndpoint,
    central: RoleEndpoint,
    confirmed: PeripheralBuild,
    unconfirmed: PeripheralBuild,
    central_build: Any,
    candidates: dict[str, ImageArtifact],
    preflight: dict[str, Any],
) -> dict[str, Any]:
    """! @brief 실제 cut 전 단계만 나타내는 redacted 2보드 manifest를 만듭니다. """

    return {
        "schema_version": PROTOCOL_VERSION,
        "test_id": "M30-POWER-01",
        "status": "blocked_human_power_cut",
        "power_hil": "not_run",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "core_revision": core_revision,
        "board_revision": board_revision,
        "boards": {
            "peripheral_dut": daplink_identity(peripheral),
            "central_relay": daplink_identity(central),
        },
        "injection_plan": [
            {"point": point, "cuts": CUTS_PER_POINT} for point in INJECTION_POINTS
        ],
        "criteria": {
            "injection_points": len(INJECTION_POINTS),
            "cuts_per_point": CUTS_PER_POINT,
            "total_physical_cuts": TOTAL_CUTS,
            "recovery_failures": 0,
            "invalid_image_boots": 0,
        },
        "images": {
            name: artifact_evidence(artifact)
            for name, artifact in candidates.items()
        },
        "bootloader": {
            "name": confirmed.boot_hex.name,
            "size": confirmed.boot_hex.stat().st_size,
            "sha256": file_sha256(confirmed.boot_hex),
            "swap_observation_hook": True,
            "window_seconds": 15,
        },
        "central_image": {
            "name": central_build.image.name,
            "size": central_build.image.stat().st_size,
            "sha256": file_sha256(central_build.image),
        },
        "trust_public_key_source_sha256": confirmed.public_key_sha256,
        "build_records": {
            "confirmed": confirmed.record,
            "unconfirmed": unconfirmed.record,
            "central": central_build.record,
        },
        "runner": {
            "name": RUNNER_PATH.name,
            "sha256": file_sha256(RUNNER_PATH),
        },
        "preflight": preflight,
        "safety": {
            "physical_power_cuts": 0,
            "reset_substitution_allowed": False,
            "mass_erase_or_recover": False,
            "requires_msd_and_uart_absence": True,
            "raw_probe_uids_stored": False,
        },
        "next_action": "execute runner and physically disconnect DUT target USB at first armed window",
    }


def write_new_json(path: Path, document: dict[str, Any], overwrite: bool) -> None:
    """! @brief 명시적 허용 없이는 기존 manifest를 덮어쓰지 않습니다. """

    path = path.resolve()
    if path.suffix.casefold() != ".json":
        raise M30PowerFailure("JSON 출력 경로의 확장자가 .json이 아닙니다.")
    if path.exists() and not overwrite:
        raise M30PowerFailure(f"기존 파일을 덮어쓰지 않습니다: {path}")
    if path.exists() and not path.is_file():
        raise M30PowerFailure(f"출력 경로가 일반 파일이 아닙니다: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def load_json(path: Path, label: str) -> dict[str, Any]:
    """! @brief bounded JSON object를 읽습니다. """

    try:
        if path.stat().st_size > 2 * 1024 * 1024:
            raise M30PowerFailure(f"{label} 크기가 허용 범위를 넘습니다.")
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise M30PowerFailure(f"{label}를 읽지 못했습니다: {error}") from error
    if not isinstance(document, dict):
        raise M30PowerFailure(f"{label}가 JSON object가 아닙니다.")
    return document


def atomic_write_json(path: Path, document: dict[str, Any]) -> None:
    """! @brief 전원 시험 journal을 같은 directory의 임시 파일로 원자 교체합니다. """

    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def initial_journal(manifest_path: Path, core_revision: str) -> dict[str, Any]:
    """! @brief 중복 계수를 막는 신규 실행 journal을 생성합니다. """

    return {
        "schema_version": PROTOCOL_VERSION,
        "test_id": "M30-POWER-01",
        "status": "in_progress",
        "core_revision": core_revision,
        "manifest_sha256": file_sha256(manifest_path),
        "completed_attempts": [],
        "current_attempt": None,
        "physical_cuts": 0,
    }


def validate_journal(
    journal: dict[str, Any], manifest_path: Path, core_revision: str
) -> None:
    """! @brief revision·manifest·순서가 다른 resume를 거부합니다. """

    if journal.get("schema_version") != PROTOCOL_VERSION:
        raise M30PowerFailure("journal schema가 다릅니다.")
    if journal.get("core_revision") != core_revision:
        raise M30PowerFailure("journal Core revision이 다릅니다.")
    if journal.get("manifest_sha256") != file_sha256(manifest_path):
        raise M30PowerFailure("journal manifest identity가 다릅니다.")
    completed = journal.get("completed_attempts")
    if not isinstance(completed, list) or len(completed) > TOTAL_CUTS:
        raise M30PowerFailure("journal 완료 attempt 배열이 잘못됐습니다.")
    expected = [
        (point, attempt)
        for point in INJECTION_POINTS
        for attempt in range(1, CUTS_PER_POINT + 1)
    ]
    observed = [(item.get("point"), item.get("attempt")) for item in completed]
    if observed != expected[: len(observed)]:
        raise M30PowerFailure("journal attempt 순서가 고정 계획과 다릅니다.")
    if journal.get("physical_cuts") != len(completed):
        raise M30PowerFailure("journal 실제 cut 수와 완료 attempt 수가 다릅니다.")
    if journal.get("current_attempt") is not None:
        raise M30PowerFailure(
            "이전 실행이 armed 또는 recovery 중 중단됐습니다. 중복 계수 방지를 위해 수동 audit가 필요합니다."
        )


def presence(endpoint: RoleEndpoint, list_ports: Any) -> Presence:
    """! @brief exact UID의 DAPLink MSD와 target UART를 독립적으로 탐색합니다. """

    details = read_details(endpoint.volume.root)
    volume_present = (
        details is not None
        and detail_value(details, "Target Detect") == DAPLINK_TARGET
        and (detail_value(details, "Unique ID") or "").casefold()
        == endpoint.board_id.casefold()
    )
    port_present = False
    for port in list_ports.comports():
        if port.device.casefold() != endpoint.port_name.casefold():
            continue
        serial_number = (port.serial_number or "").casefold()
        if serial_number != endpoint.board_id.casefold():
            continue
        if is_target_uart_interface(port):
            port_present = True
            break
    return Presence(volume_present, port_present)


def wait_for_physical_cycle(
    sample: Callable[[], Presence],
    disappearance_timeout: float,
    restoration_timeout: float,
    stable_seconds: float,
) -> PhysicalCycle:
    """! @brief MSD+UART 동시 소실과 동일 endpoint 복귀만 실제 power cycle로 인정합니다. """

    started = time.monotonic()
    if not sample().complete:
        raise M30PowerFailure("arm 시점에 DUT MSD와 target UART가 모두 존재하지 않습니다.")
    absent_since: float | None = None
    absent_confirmed: float | None = None
    while time.monotonic() - started < disappearance_timeout:
        current = sample()
        now = time.monotonic()
        if current.absent:
            if absent_since is None:
                absent_since = now
            if now - absent_since >= stable_seconds:
                absent_confirmed = now
                break
        else:
            absent_since = None
        time.sleep(0.1)
    if absent_since is None or absent_confirmed is None:
        raise M30PowerFailure(
            "DUT MSD와 target UART의 동시 소실을 관찰하지 못했습니다. reset은 전원 차단 증거가 아닙니다."
        )
    restored_since: float | None = None
    restoration_started = time.monotonic()
    while time.monotonic() - restoration_started < restoration_timeout:
        current = sample()
        now = time.monotonic()
        if current.complete:
            if restored_since is None:
                restored_since = now
            if now - restored_since >= stable_seconds:
                return PhysicalCycle(
                    round(absent_since - started, 3),
                    round(absent_confirmed - absent_since, 3),
                    round(now - started, 3),
                )
        else:
            restored_since = None
        time.sleep(0.1)
    raise M30PowerFailure("동일 DUT MSD와 target UART가 제한 시간 안에 복귀하지 않았습니다.")


def upload_request(artifact: ImageArtifact, data: bytes, offset: int) -> dict[str, Any]:
    """! @brief ATT MTU에 맞는 다음 canonical SMP upload payload를 만듭니다. """

    chunk_length = min(216, len(data) - offset)
    while chunk_length > 0:
        request: dict[str, Any] = {
            "image": 0,
            "data": data[offset : offset + chunk_length],
            "off": offset,
        }
        if offset == 0:
            request["len"] = len(data)
            request["sha"] = bytes.fromhex(artifact.sha256)
        if len(cbor_encode(request)) + 8 <= MAX_SMP_PACKET:
            return request
        chunk_length -= 16
    raise M30PowerFailure("SMP upload chunk를 ATT MTU에 맞출 수 없습니다.")


def send_raw_transaction(
    session: DfuSession,
    operation: int,
    group: int,
    command_id: int,
    payload: dict[str, Any],
) -> None:
    """! @brief 응답 전 전원 소실을 허용하는 단일 SMP request를 전송합니다. """

    encoded = cbor_encode(payload)
    sequence = session.sequence
    session.sequence = (session.sequence + 1) & 0xFF
    first = (1 << 3) | operation
    packet = struct.pack(
        ">BBHHBB", first, 0, len(encoded), group, sequence, command_id
    ) + encoded
    if len(packet) > MAX_SMP_PACKET:
        raise M30PowerFailure("raw SMP request가 ATT payload를 넘습니다.")
    session.send_line("central", f"M30DFU|1|TX|{packet.hex()}")


def upload_until(
    session: DfuSession,
    artifact: ImageArtifact,
    deadline: float,
    stop: str,
) -> tuple[int, dict[str, Any]]:
    """! @brief transfer 중간 또는 마지막 request 직전까지 image를 전송합니다. """

    data = artifact.path.read_bytes()
    offset = 0
    requests = 0
    while offset < len(data):
        request = upload_request(artifact, data, offset)
        next_end = offset + len(request["data"])
        if stop == "middle" and offset > 0 and next_end >= len(data) // 3:
            return offset, request
        if stop == "before_final" and next_end == len(data):
            return offset, request
        response = session.require_success(
            session.transaction(2, 1, 1, request, deadline), "power image upload"
        )
        next_offset = response.get("off")
        if not isinstance(next_offset, int) or not offset < next_offset <= len(data):
            raise M30PowerFailure("power upload offset가 진행하지 않습니다.")
        offset = next_offset
        requests += 1
    raise M30PowerFailure("요청한 전원 주입 지점 전에 upload가 끝났습니다.")


def wait_window(session: DfuSession, expected: str, deadline: float) -> None:
    """! @brief target 또는 MCUboot가 보고한 exact 전원 관찰 창을 기다립니다. """

    while time.monotonic() < deadline:
        line = session.checked_line("peripheral", deadline)
        match = WINDOW_PATTERN.fullmatch(line)
        if match is None:
            continue
        observed = match.group(1).decode("ascii")
        if observed != expected:
            raise M30PowerFailure(
                f"전원 관찰 창 순서가 다릅니다: {observed}, expected={expected}"
            )
        return
    raise M30PowerFailure(f"{expected} 전원 관찰 창을 보지 못했습니다.")


def read_power_state(
    session: DfuSession, deadline: float, require_restored_bond: bool
) -> dict[str, int]:
    """! @brief settings·bond 구조와 복원된 bond를 protocol로 검증합니다. """

    session.send_line("peripheral", "M30POWER|1|STATE?")
    while time.monotonic() < deadline:
        line = session.checked_line("peripheral", deadline)
        match = POWER_STATE_PATTERN.fullmatch(line)
        if match is None:
            continue
        values = [int(value) for value in match.groups()]
        result = {
            "bond_count": values[0],
            "rejected_bonds": values[1],
            "bonded": values[2],
            "settings_valid": values[3],
        }
        if not 1 <= result["bond_count"] <= 4:
            raise M30PowerFailure(f"bond record 수가 구조 범위를 벗어났습니다: {result}")
        if result["rejected_bonds"] != 0 or result["settings_valid"] != 1:
            raise M30PowerFailure(f"settings 또는 bond 구조가 유효하지 않습니다: {result}")
        if require_restored_bond and result["bonded"] != 1:
            raise M30PowerFailure(f"전원 복구 뒤 저장 bond가 복원되지 않았습니다: {result}")
        return result
    raise M30PowerFailure("M30POWER STATE 응답 timeout")


def validate_storage_partition(build_root: Path) -> None:
    """! @brief build devicetree의 storage 범위가 고정 erase 범위와 같은지 검사합니다. """

    candidates = (
        build_root / "m30_ble_dfu_hil/zephyr/zephyr.dts",
        build_root / "zephyr/zephyr.dts",
    )
    devicetree = next((path for path in candidates if path.is_file()), None)
    if devicetree is None:
        raise M30PowerFailure("build devicetree에서 storage partition을 확인할 수 없습니다.")
    source = devicetree.read_text(encoding="utf-8", errors="strict")
    pattern = re.compile(
        rf"storage_partition:\s+partition@{STORAGE_OFFSET:x}\s*\{{.*?"
        rf"reg\s*=\s*<\s*0x{STORAGE_OFFSET:x}\s+0x{STORAGE_SIZE:x}\s*>;",
        re.DOTALL,
    )
    if pattern.search(source) is None:
        raise M30PowerFailure("build devicetree의 storage partition 범위가 다릅니다.")


def reset_bond_storage(board_id: str, timeout_seconds: float) -> None:
    """! @brief RRAM storage exact 범위를 0xff로 기록하고 다시 읽어 검증합니다. """

    program = f"""
import sys
from pyocd.core.helpers import ConnectHelper

session = ConnectHelper.session_with_chosen_probe(
    unique_id=sys.argv[1],
    target_override="nrf54l",
    frequency=500000,
    options={{
        "auto_unlock": False,
        "cmsis_dap.limit_packets": True,
        "hide_programming_progress": True,
    }},
)
if session is None:
    raise RuntimeError("exact probe session을 열 수 없습니다.")
with session:
    target = session.target
    region = target.memory_map.get_region_for_address(
        {STORAGE_OFFSET}, target.selected_core.node_name
    )
    if region is None or region.flash is None:
        raise RuntimeError("storage flash algorithm을 찾을 수 없습니다.")
    flash = region.flash
    flash.init(flash.Operation.PROGRAM)
    try:
        for address in range(
            {STORAGE_OFFSET}, {STORAGE_OFFSET + STORAGE_SIZE}, {0x1000}
        ):
            flash.program_page(address, bytes([255]) * {0x1000})
    finally:
        flash.cleanup()
    target.reset()
    observed = session.target.read_memory_block8({STORAGE_OFFSET}, {STORAGE_SIZE})
    if len(observed) != {STORAGE_SIZE} or any(value != 255 for value in observed):
        raise RuntimeError("storage 0xff readback 검증에 실패했습니다.")
print("M30_STORAGE_RESET_PASS={STORAGE_SIZE}")
"""
    command = (sys.executable, "-I", "-c", program, board_id)
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise M30PowerFailure(f"bond storage exact reset 실패: {error}") from error
    output = result.stdout + result.stderr
    if result.returncode != 0 or f"M30_STORAGE_RESET_PASS={STORAGE_SIZE}".encode() not in output:
        safe_output = output.decode("utf-8", errors="backslashreplace").replace(
            board_id, "[redacted]"
        )
        raise M30PowerFailure(f"bond storage exact reset 실패: {safe_output}")


def reopen_peripheral(session: DfuSession) -> None:
    """! @brief 재연결된 동일 target UART를 기존 BLE session에 다시 엽니다. """

    endpoint = session.endpoints["peripheral"]
    port = session.stack.enter_context(
        session.serial_module.Serial(
            endpoint.port_name,
            baudrate=session.baud,
            bytesize=session.serial_module.EIGHTBITS,
            parity=session.serial_module.PARITY_NONE,
            stopbits=session.serial_module.STOPBITS_ONE,
            timeout=0.05,
            write_timeout=2.0,
        )
    )
    port.reset_input_buffer()
    session.ports["peripheral"] = port
    session.pending["peripheral"].clear()


def close_peripheral_for_cycle(session: DfuSession) -> None:
    """! @brief Windows가 실제 UART 제거를 관찰하도록 DUT handle만 닫습니다. """

    session.ports["peripheral"].close()


def normalize_boards(
    peripheral: RoleEndpoint,
    central: RoleEndpoint,
    confirmed: PeripheralBuild,
    central_build: Any,
    flash_timeout: float,
) -> dict[str, Any]:
    """! @brief sector erase만 사용해 매 attempt의 confirmed baseline을 복원합니다. """

    erase_secondary_slot(peripheral.board_id, flash_timeout)
    return {
        "peripheral_bootloader": flash_image_pyocd(
            "power-peripheral-bootloader",
            peripheral.board_id,
            confirmed.boot_hex,
            flash_timeout,
        ),
        "peripheral_primary": flash_image_pyocd(
            "power-peripheral-primary",
            peripheral.board_id,
            confirmed.signed_hex,
            flash_timeout,
        ),
        "central": flash_image_pyocd(
            "power-central-relay",
            central.board_id,
            central_build.image,
            flash_timeout,
        ),
    }


def verify_retry(
    session: DfuSession, retry: ImageArtifact, deadline: float
) -> dict[str, Any]:
    """! @brief 복구 뒤 slot 1 전체 재전송·hash state·sector erase 가능성을 검증합니다. """

    session.erase_secondary(deadline)
    requests = session.upload(retry, deadline)
    state = session.state_for_hash(retry.image_hash, deadline)
    if state is None or state.get("bootable") is not True:
        raise M30PowerFailure("복구 뒤 DFU retry image가 bootable state에 없습니다.")
    session.erase_secondary(deadline)
    return {"requests": requests, "image_hash": retry.image_hash.hex()}


def validate_recovery_boot(point: str, record: Any) -> None:
    """! @brief 주입 지점별 허용된 confirmed image만 복구 boot로 인정합니다. """

    if point == "mcuboot_test_swap" and record.version == CONFIRMED_VERSION:
        validate_boot(record, CONFIRMED_VERSION, confirmed=1, auto_confirm=1)
        return
    validate_boot(record, BASE_VERSION, confirmed=1, auto_confirm=1)


def arm_point(
    session: DfuSession,
    point: str,
    confirmed_candidate: ImageArtifact,
    unconfirmed_candidate: ImageArtifact,
    deadline: float,
) -> None:
    """! @brief 한 injection point를 실제 USB 차단만 남은 상태로 만듭니다. """

    if point == "slot1_transfer":
        offset, _request = upload_until(
            session, confirmed_candidate, deadline, "middle"
        )
        print(
            f"M30_POWER_ARMED=slot1_transfer;offset={offset};ACTION=DISCONNECT_DUT_TARGET_USB",
            flush=True,
        )
        return
    if point == "image_validation_write":
        _offset, final_request = upload_until(
            session, confirmed_candidate, deadline, "before_final"
        )
        send_raw_transaction(session, 2, 1, 1, final_request)
        wait_window(session, point, min(deadline, time.monotonic() + 30.0))
        print(
            "M30_POWER_ARMED=image_validation_write;ACTION=DISCONNECT_DUT_TARGET_USB",
            flush=True,
        )
        return

    candidate = (
        unconfirmed_candidate
        if point == "new_image_first_boot"
        else confirmed_candidate
    )
    session.upload(candidate, deadline)
    session.require_success(
        session.request_test(candidate.image_hash, deadline),
        f"{point} test request",
    )
    if point == "mcuboot_test_swap":
        send_raw_transaction(session, 2, 0, 5, {})
        wait_window(session, point, min(deadline, time.monotonic() + 45.0))
        print(
            "M30_POWER_ARMED=mcuboot_test_swap;ACTION=DISCONNECT_DUT_TARGET_USB",
            flush=True,
        )
        return
    first_boot = session.reset_and_reconnect(deadline)
    validate_boot(
        first_boot, UNCONFIRMED_VERSION, confirmed=0, auto_confirm=0
    )
    print(
        "M30_POWER_ARMED=new_image_first_boot;ACTION=DISCONNECT_DUT_TARGET_USB",
        flush=True,
    )


def preflight(
    serial_module: Any,
    peripheral: RoleEndpoint,
    central: RoleEndpoint,
    confirmed: PeripheralBuild,
    central_build: Any,
    candidates: dict[str, ImageArtifact],
    args: argparse.Namespace,
    core_revision: str,
) -> dict[str, Any]:
    """! @brief 실제 cut 없이 flash·L4·settings·DFU retry 준비 상태를 검증합니다. """

    storage_reset = {
        "performed": False,
        "boards": 0,
        "offset": STORAGE_OFFSET,
        "size": STORAGE_SIZE,
    }
    if args.reset_bond_storage:
        validate_storage_partition(confirmed.root)
        validate_storage_partition(central_build.root)
        reset_bond_storage(peripheral.board_id, args.flash_timeout)
        reset_bond_storage(central.board_id, args.flash_timeout)
        storage_reset["performed"] = True
        storage_reset["boards"] = 2
    flash_results = normalize_boards(
        peripheral,
        central,
        confirmed,
        central_build,
        args.flash_timeout,
    )
    with DfuSession(
        serial_module,
        peripheral,
        central,
        args.baud,
        build_nonce(args.nonce),
        core_revision,
    ) as session:
        deadline = time.monotonic() + min(args.phase_timeout, 600.0)
        boot = session.connect_initial(deadline)
        validate_boot(boot, BASE_VERSION, confirmed=1, auto_confirm=1)
        state = read_power_state(session, deadline, False)
        retry = verify_retry(session, candidates["retry"], deadline)
    return {
        "status": "passed",
        "flash_backend": "pyocd-exact-sector",
        "flash_results": flash_results,
        "security_level": 4,
        "encryption_key_bytes": 16,
        "state": state,
        "dfu_retry": retry,
        "bond_storage_reset": storage_reset,
        "physical_power_cuts": 0,
    }


def validate_manifest(
    manifest: dict[str, Any],
    expected: dict[str, Any],
) -> None:
    """! @brief 실행 시점 manifest의 revision·board·image identity를 재검증합니다. """

    for key in (
        "schema_version",
        "test_id",
        "core_revision",
        "board_revision",
        "runner",
    ):
        if manifest.get(key) != expected.get(key):
            raise M30PowerFailure(f"manifest {key} identity가 다릅니다.")
    if manifest.get("status") != "blocked_human_power_cut":
        raise M30PowerFailure("manifest가 실제 cut 직전 blocked 상태가 아닙니다.")
    if manifest.get("power_hil") != "not_run":
        raise M30PowerFailure("이미 실행된 power manifest를 재사용할 수 없습니다.")
    if manifest.get("boards") != expected.get("boards"):
        raise M30PowerFailure("manifest 2보드 endpoint identity가 다릅니다.")
    if manifest.get("images") != expected.get("images"):
        raise M30PowerFailure("manifest candidate identity가 다릅니다.")
    if manifest.get("bootloader") != expected.get("bootloader"):
        raise M30PowerFailure("manifest MCUboot identity가 다릅니다.")
    if manifest.get("central_image") != expected.get("central_image"):
        raise M30PowerFailure("manifest Central image identity가 다릅니다.")


def execute_power_hil(
    serial_module: Any,
    list_ports: Any,
    peripheral: RoleEndpoint,
    central: RoleEndpoint,
    confirmed: PeripheralBuild,
    central_build: Any,
    candidates: dict[str, ImageArtifact],
    args: argparse.Namespace,
    core_revision: str,
    manifest_path: Path,
) -> None:
    """! @brief 고정 순서 12회 실제 cut과 복구·settings·DFU retry를 실행합니다. """

    journal_path = Path(args.journal).resolve()
    evidence_path = Path(args.evidence).resolve()
    if evidence_path.exists():
        raise M30PowerFailure("기존 최종 power evidence를 덮어쓰지 않습니다.")
    if journal_path.exists():
        journal = load_json(journal_path, "power journal")
        validate_journal(journal, manifest_path, core_revision)
    else:
        journal = initial_journal(manifest_path, core_revision)
        atomic_write_json(journal_path, journal)
    plan = [
        (point, attempt)
        for point in INJECTION_POINTS
        for attempt in range(1, CUTS_PER_POINT + 1)
    ]
    started = time.monotonic()
    for index, (point, attempt) in enumerate(
        plan[len(journal["completed_attempts"]) :],
        start=len(journal["completed_attempts"]),
    ):
        if time.monotonic() - started >= args.phase_timeout:
            raise M30PowerFailure("M30-POWER-01 전체 1800초 timeout을 넘었습니다.")
        flash_results = normalize_boards(
            peripheral,
            central,
            confirmed,
            central_build,
            args.flash_timeout,
        )
        nonce = build_nonce(args.nonce, index)
        with DfuSession(
            serial_module,
            peripheral,
            central,
            args.baud,
            nonce,
            core_revision,
        ) as session:
            deadline = started + args.phase_timeout
            baseline = session.connect_initial(deadline)
            validate_boot(baseline, BASE_VERSION, confirmed=1, auto_confirm=1)
            arm_point(
                session,
                point,
                candidates["confirmed"],
                candidates["unconfirmed"],
                deadline,
            )
            journal["current_attempt"] = {
                "point": point,
                "attempt": attempt,
                "status": "armed",
                "physical_cycle_observed": False,
            }
            atomic_write_json(journal_path, journal)
            close_peripheral_for_cycle(session)
            cut_timeout = (
                args.window_cut_timeout
                if point in ("image_validation_write", "mcuboot_test_swap")
                else args.power_cycle_timeout
            )
            cycle = wait_for_physical_cycle(
                lambda: presence(peripheral, list_ports),
                cut_timeout,
                args.power_cycle_timeout,
                args.absence_stable,
            )
            journal["current_attempt"]["status"] = "recovery_pending"
            journal["current_attempt"]["physical_cycle_observed"] = True
            journal["current_attempt"]["cycle"] = cycle.__dict__
            atomic_write_json(journal_path, journal)
            reopen_peripheral(session)
            recovered = session.reconnect(deadline)
            validate_recovery_boot(point, recovered)
            state = read_power_state(session, deadline, True)
            retry = verify_retry(session, candidates["retry"], deadline)
            completed = {
                "point": point,
                "attempt": attempt,
                "status": "passed",
                "cycle": cycle.__dict__,
                "recovered_version": list(recovered.version),
                "settings": state,
                "dfu_retry": retry,
                "flash_results": flash_results,
            }
            journal["completed_attempts"].append(completed)
            journal["physical_cuts"] = len(journal["completed_attempts"])
            journal["current_attempt"] = None
            atomic_write_json(journal_path, journal)
            print(
                f"M30_POWER_RECOVERY_PASS={point}:{attempt}/{CUTS_PER_POINT}",
                flush=True,
            )
    journal["status"] = "passed"
    atomic_write_json(journal_path, journal)
    evidence = {
        "schema_version": PROTOCOL_VERSION,
        "test_id": "M30-POWER-01",
        "status": "passed",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "core_revision": core_revision,
        "manifest_sha256": file_sha256(manifest_path),
        "boards": 2,
        "physical_power_cuts": TOTAL_CUTS,
        "injection_points": len(INJECTION_POINTS),
        "cuts_per_point": CUTS_PER_POINT,
        "recovery_failures": 0,
        "invalid_image_boots": 0,
        "attempts": journal["completed_attempts"],
        "reset_substitution": False,
        "mass_erase_or_recover": False,
    }
    write_new_json(evidence_path, evidence, False)
    print("M30_POWER_HIL_PASS=4x3;RECOVERY_FAILURES=0;INVALID_BOOTS=0")


def main(arguments: Sequence[str] | None = None) -> int:
    """! @brief 탐색·prepare-only·명시적 실제 전원 시험 중 하나를 실행합니다. """

    args = parse_arguments(arguments)
    validate_options(args)
    serial_module, list_ports = import_pyserial()
    peripheral = discover_endpoint(
        args.peripheral_board_id,
        args.peripheral_volume,
        args.peripheral_port,
        list_ports,
    )
    central = discover_endpoint(
        args.central_board_id,
        args.central_volume,
        args.central_port,
        list_ports,
    )
    validate_pair_identity(peripheral, central)
    if args.discover_only:
        print("M30_POWER_DISCOVERY_PASS=2")
        return 0

    validate_source_clean(
        MILESTONE,
        APPLICATION_ROOT,
        RUNNER_PATH,
        (DFU_RUNNER_PATH, BOOT_RUNNER_PATH),
    )
    repository_revision = git_revision(REPOSITORY)
    core_revision = args.expected_core_revision or repository_revision
    if re.fullmatch(r"[0-9a-f]{40}", core_revision) is None:
        raise M30PowerFailure("--expected-core-revision은 full lowercase SHA-1이어야 합니다.")
    board_revision = git_revision(BOARD_ROOT)
    validate_board_revision(board_revision)
    trust_key = validate_private_key(args.trust_signing_key, "trust signing key")
    confirmed = collect_power_build(
        args.confirmed_build_outdir, core_revision, trust_key, 1
    )
    unconfirmed = collect_power_build(
        args.unconfirmed_build_outdir, core_revision, trust_key, 0
    )
    central_build = collect_central_build(args.central_build_outdir, core_revision)
    if confirmed.public_key_sha256 != unconfirmed.public_key_sha256:
        raise M30PowerFailure("confirmed와 unconfirmed MCUboot public key가 다릅니다.")
    if file_sha256(confirmed.boot_hex) != file_sha256(unconfirmed.boot_hex):
        raise M30PowerFailure("confirmed와 unconfirmed MCUboot image가 다릅니다.")
    immutable = {
        path.resolve(): (path.stat().st_size, file_sha256(path))
        for path in (
            confirmed.boot_hex,
            confirmed.signed_hex,
            confirmed.raw_bin,
            unconfirmed.boot_hex,
            unconfirmed.signed_hex,
            unconfirmed.raw_bin,
            central_build.image,
        )
    }
    imgtool_python = Path(args.imgtool_python).resolve()
    imgtool = Path(args.imgtool).resolve()
    manifest_path = Path(args.manifest).resolve()
    with tempfile.TemporaryDirectory(prefix="n54-m30-power-") as temporary:
        candidates = create_power_candidates(
            confirmed,
            unconfirmed,
            trust_key,
            imgtool_python,
            imgtool,
            Path(temporary),
        )
        preflight_result: dict[str, Any] = {
            "status": "not_run",
            "physical_power_cuts": 0,
        }
        if args.prepare_only and args.flash_preflight:
            preflight_result = preflight(
                serial_module,
                peripheral,
                central,
                confirmed,
                central_build,
                candidates,
                args,
                core_revision,
            )
        expected_manifest = manifest_document(
            core_revision,
            board_revision,
            peripheral,
            central,
            confirmed,
            unconfirmed,
            central_build,
            candidates,
            preflight_result,
        )
        if args.prepare_only:
            write_new_json(
                manifest_path, expected_manifest, args.overwrite_manifest
            )
            print(
                "M30_POWER_PREPARE_PASS=2;POINTS=4;CUTS_PER_POINT=3;PHYSICAL_CUTS=0"
            )
        else:
            manifest = load_json(manifest_path, "power manifest")
            validate_manifest(manifest, expected_manifest)
            execute_power_hil(
                serial_module,
                list_ports,
                peripheral,
                central,
                confirmed,
                central_build,
                candidates,
                args,
                core_revision,
                manifest_path,
            )
    for path, (size, digest) in immutable.items():
        validate_image_unchanged(path, size, digest)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        M30PowerFailure,
        M30DfuFailure,
        M30BootFailure,
        BlePairHilFailure,
    ) as error:
        print(f"M30_POWER_HIL_FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
