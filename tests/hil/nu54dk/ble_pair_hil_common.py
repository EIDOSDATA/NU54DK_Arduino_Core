#!/usr/bin/env python3
"""! @brief M19/M20 두 보드 BLE HIL의 장치·image·UART 공통 경계를 제공합니다. """

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
import hashlib
import re
import secrets
import shutil
import subprocess
import threading
import time
from typing import Any


HIL_DIRECTORY = Path(__file__).resolve().parent
REPOSITORY = HIL_DIRECTORY.parents[2]
BOARD_ROOT = REPOSITORY / "board_package" / "NU54DK_Zephyr_DTS"

from m6_serial_echo import (  # noqa: E402
    DEFAULT_BAUD_RATE,
    DaplinkVolume,
    detail_value,
    find_daplink_volume,
    find_serial_port,
    normalize_board_id,
    validate_hex_image,
    wait_for_flash_result,
)
from m14_pin_hil import (  # noqa: E402
    CORE_SOURCE_SCOPES,
    build_record_value,
    file_sha256,
    files_digest,
    git_revision,
    validate_board_revision,
)


NONCE_PATTERN = re.compile(r"^[0-9a-f]{32}$")
MAX_TRANSCRIPT_BYTES = 262144
DEFAULT_RESULT_TIMEOUT_SECONDS = 180.0


class BlePairHilFailure(RuntimeError):
    """! @brief M19/M20 pair HIL의 fail-closed 오류를 나타냅니다. """


class PairExecutionFailure(BlePairHilFailure):
    """! @brief 실행 오류와 실패 시점까지의 두 raw transcript를 보존합니다. """

    def __init__(
        self, message: str, peripheral_transcript: bytes, central_transcript: bytes
    ) -> None:
        super().__init__(message)
        self.peripheral_transcript = peripheral_transcript
        self.central_transcript = central_transcript


@dataclass(frozen=True)
class RoleEndpoint:
    """! @brief 한 role에 결합한 DAPLink UID·MSD·UART endpoint입니다. """

    board_id: str
    volume: DaplinkVolume
    port_name: str


@dataclass(frozen=True)
class RoleExecution:
    """! @brief 한 role의 flash 결과와 raw transcript입니다. """

    flash_sequence: str
    flash_bytes: str
    transcript: bytes


@dataclass(frozen=True)
class PairExecution:
    """! @brief 두 role의 동시 실행 결과입니다. """

    peripheral: RoleExecution
    central: RoleExecution


## @brief 동일 실행에 쓸 32자리 소문자 nonce를 검증하거나 생성합니다.
def build_nonce(explicit_nonce: str | None = None) -> str:
    nonce = explicit_nonce if explicit_nonce is not None else secrets.token_hex(16)
    if NONCE_PATTERN.fullmatch(nonce) is None:
        raise BlePairHilFailure("BLE pair nonce는 32자리 소문자 hex여야 합니다.")
    return nonce


## @brief 한 UID로 DAPLink MSD와 target UART를 함께 찾습니다.
def discover_endpoint(
    board_id: str,
    explicit_volume: str | None,
    explicit_port: str,
    list_ports: Any,
) -> RoleEndpoint:
    normalized = normalize_board_id(board_id)
    return RoleEndpoint(
        normalized,
        find_daplink_volume(normalized, explicit_volume),
        find_serial_port(normalized, explicit_port, list_ports),
    )


## @brief 두 role이 서로 다른 UID·MSD·UART인지 검사합니다.
def validate_pair_identity(peripheral: RoleEndpoint, central: RoleEndpoint) -> None:
    if peripheral.board_id == central.board_id:
        raise BlePairHilFailure("peripheral과 central DAPLink UID가 같습니다.")
    if peripheral.volume.root.resolve() == central.volume.root.resolve():
        raise BlePairHilFailure("peripheral과 central DAPLink MSD가 같습니다.")
    if peripheral.port_name.casefold() == central.port_name.casefold():
        raise BlePairHilFailure("peripheral과 central UART가 같습니다.")


## @brief exact-commit HIL 입력 source와 board checkout이 clean인지 검사합니다.
def validate_source_clean(
    milestone: str, application_root: Path, runner_path: Path
) -> None:
    core_paths = (
        "cores/arduino",
        "dts",
        "libraries/NUCODE_BLE",
        "third_party/ArduinoCore-API",
        "third_party/ArduinoCore-API.provenance.yml",
        "variants/nu54dk",
        "zephyr",
        str(application_root.relative_to(REPOSITORY)),
        str(runner_path.relative_to(REPOSITORY)),
        "tests/hil/nu54dk/ble_pair_hil_common.py",
        "tests/hil/nu54dk/m14_pin_hil.py",
        "tests/hil/nu54dk/m6_serial_echo.py",
    )
    core = subprocess.run(
        (
            "git",
            "-C",
            str(REPOSITORY),
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            "--",
            *core_paths,
        ),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    board = subprocess.run(
        (
            "git",
            "-C",
            str(BOARD_ROOT),
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        ),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if core.returncode != 0 or core.stdout.strip():
        raise BlePairHilFailure(
            f"{milestone} HIL source에 commit되지 않은 변경이 있습니다: "
            f"{core.stdout.strip() or core.stderr.strip()}"
        )
    if board.returncode != 0 or board.stdout.strip():
        raise BlePairHilFailure(
            "board_package submodule이 clean하지 않습니다: "
            f"{board.stdout.strip() or board.stderr.strip()}"
        )


## @brief build record와 비교할 현재 source byte digest를 계산합니다.
def current_source_digests(application_root: Path) -> dict[str, str]:
    board_scope = BOARD_ROOT / "boards" / "nucode" / "nu54dk"
    return {
        "core_source_sha256": files_digest(REPOSITORY, CORE_SOURCE_SCOPES),
        "application_source_sha256": files_digest(
            application_root, (application_root,)
        ),
        "board_source_sha256": files_digest(BOARD_ROOT, (board_scope,)),
    }


## @brief HEX build record를 exact revision·target·source byte와 결합합니다.
def validate_build_record(
    image: Path,
    core_revision: str,
    board_revision: str,
    application_root: Path,
) -> dict[str, str]:
    record_path = image.parent.parent / "nucode_arduino_core_build.yml"
    try:
        if record_path.stat().st_size > 16384:
            raise BlePairHilFailure("NUCODE build record 크기가 허용 범위를 넘었습니다.")
        record_text = record_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise BlePairHilFailure(
            f"HEX build record를 읽지 못했습니다: {record_path}: {error}"
        ) from error

    keys = (
        "core_revision",
        "core_source_sha256",
        "application_source_sha256",
        "board_revision",
        "board_source_sha256",
        "ncs_revision",
        "zephyr_revision",
        "board",
        "board_qualifiers",
    )
    values = {key: build_record_value(record_text, key) for key in keys}
    expected = {
        "core_revision": core_revision[:12],
        "board_revision": board_revision[:12],
        "ncs_revision": "99553055607b",
        "zephyr_revision": "bf801e4e3d19",
        "board": "nrf54l15dk",
        "board_qualifiers": "nrf54l15/cpuapp/nu54dk",
    }
    for key, expected_value in expected.items():
        if values[key] != expected_value:
            raise BlePairHilFailure(
                f"build record 불일치: {key}={values[key]}, expected={expected_value}"
            )
    for key, expected_digest in current_source_digests(application_root).items():
        if not re.fullmatch(r"[0-9a-f]{64}", values[key]):
            raise BlePairHilFailure(f"build record digest 형식 오류: {key}")
        if values[key] != expected_digest:
            raise BlePairHilFailure(
                f"build record source 불일치: {key}={values[key]}, "
                f"expected={expected_digest}"
            )
    values["record_name"] = record_path.name
    values["record_sha256"] = file_sha256(record_path)
    return values


## @brief evidence와 두 raw transcript의 신규 출력 경로를 준비합니다.
def prepare_output_paths(
    evidence_argument: str | None, overwrite: bool
) -> tuple[Path, Path, Path]:
    if not evidence_argument:
        raise BlePairHilFailure("실제 실행에는 --evidence가 필요합니다.")
    evidence = Path(evidence_argument).resolve()
    if evidence.suffix.lower() != ".json":
        raise BlePairHilFailure("--evidence는 .json 파일이어야 합니다.")
    peripheral = evidence.with_name(f"{evidence.stem}.peripheral.transcript.log")
    central = evidence.with_name(f"{evidence.stem}.central.transcript.log")
    paths = (evidence, peripheral, central)
    existing = [path for path in paths if path.exists()]
    if existing and not overwrite:
        raise BlePairHilFailure(
            "기존 증적을 덮어쓰지 않습니다: "
            + ", ".join(str(path) for path in existing)
        )
    for path in existing:
        if not path.is_file():
            raise BlePairHilFailure(f"증적 경로가 일반 파일이 아닙니다: {path}")
    evidence.parent.mkdir(parents=True, exist_ok=True)
    if overwrite:
        for path in existing:
            path.unlink()
    return paths


## @brief 한 role image를 지정 DAPLink MSD에 기록합니다.
def flash_image(
    milestone: str,
    role: str,
    volume: DaplinkVolume,
    image: Path,
    timeout_seconds: float,
) -> tuple[str, str]:
    if timeout_seconds <= 0:
        raise BlePairHilFailure("--flash-timeout은 0보다 커야 합니다.")
    previous_sequence = detail_value(volume.details, "Flash Sequence")
    destination = volume.root / f"NUCODE_{milestone}_{role.upper()}.HEX"
    shutil.copyfile(image, destination)
    details = wait_for_flash_result(volume.root, previous_sequence, timeout_seconds)
    return (
        detail_value(details, "Flash Sequence") or "unknown",
        detail_value(details, "Last Flash Bytes") or "unknown",
    )


## @brief bounded UART capture에서 newline 하나를 읽습니다.
def read_line(
    serial_port: Any,
    pending: bytearray,
    raw_capture: bytearray,
    deadline: float,
    *,
    stop_event: threading.Event | None = None,
) -> bytes:
    while time.monotonic() < deadline:
        if stop_event is not None and stop_event.is_set():
            raise BlePairHilFailure("다른 role 실패로 UART 수집을 중단했습니다.")
        newline = pending.find(b"\n")
        if newline >= 0:
            line = bytes(pending[:newline]).rstrip(b"\r")
            del pending[: newline + 1]
            return line
        waiting = getattr(serial_port, "in_waiting", 0)
        chunk = serial_port.read(waiting if waiting > 0 else 1)
        if chunk:
            pending.extend(chunk)
            raw_capture.extend(chunk)
            if len(raw_capture) > MAX_TRANSCRIPT_BYTES:
                raise BlePairHilFailure("UART transcript가 허용 크기를 넘었습니다.")
    raise TimeoutError("UART line을 제한 시간 안에 읽지 못했습니다.")


## @brief role의 exact READY token까지 수집합니다.
def wait_ready(
    serial_port: Any,
    milestone: str,
    role: str,
    pending: bytearray,
    capture: bytearray,
    deadline: float,
) -> None:
    prefix = f"NUCODE_{milestone}_".encode("ascii")
    fail_prefix = f"NUCODE_{milestone}_FAIL:".encode("ascii")
    expected = f"NUCODE_{milestone}_READY:role={role}".encode("ascii")
    while True:
        line = read_line(serial_port, pending, capture, deadline)
        if line.startswith(fail_prefix):
            raise BlePairHilFailure(f"{role} target 실패: {line!r}")
        if line.startswith(prefix) and line != expected:
            raise BlePairHilFailure(
                f"{role} READY 앞 stale protocol token입니다: {line!r}"
            )
        if line == expected:
            return


## @brief 양쪽 role에 동일 nonce의 start command를 기록합니다.
def write_start_command(serial_port: Any, milestone: str, nonce: str) -> None:
    request = f"NUCODE_{milestone}_START:{nonce}\r\n".encode("ascii")
    written = serial_port.write(request)
    serial_port.flush()
    if written != len(request):
        raise BlePairHilFailure("BLE pair 시작 command가 일부만 기록됐습니다.")


## @brief peripheral 광고 확인 뒤 central scan 시작을 허용합니다.
def wait_peripheral_advertising(
    serial_port: Any,
    milestone: str,
    nonce: str,
    pending: bytearray,
    capture: bytearray,
    deadline: float,
) -> None:
    prefix = f"NUCODE_{milestone}_".encode("ascii")
    fail_prefix = f"NUCODE_{milestone}_FAIL:".encode("ascii")
    expected = (
        f"NUCODE_{milestone}_PERIPHERAL:ADVERTISE:PASS:nonce={nonce}"
    ).encode("ascii")
    while True:
        line = read_line(serial_port, pending, capture, deadline)
        if line.startswith(fail_prefix):
            raise BlePairHilFailure(f"peripheral target 실패: {line!r}")
        if line.startswith(prefix) and line != expected:
            raise BlePairHilFailure(
                f"광고 전 stale protocol token입니다: {line!r}"
            )
        if line == expected:
            return


## @brief 한 role의 현재 nonce FINAL까지 UART를 독립 수집합니다.
def collect_until_final(
    serial_port: Any,
    milestone: str,
    role: str,
    nonce: str,
    pending: bytearray,
    capture: bytearray,
    deadline: float,
    stop_event: threading.Event,
) -> None:
    final_prefix = f"NUCODE_{milestone}_{role.upper()}:FINAL:PASS:".encode(
        "ascii"
    )
    fail_prefix = f"NUCODE_{milestone}_FAIL:".encode("ascii")
    nonce_suffix = f":nonce={nonce}".encode("ascii")
    try:
        while True:
            line = read_line(
                serial_port, pending, capture, deadline, stop_event=stop_event
            )
            if line:
                print(f"[{role}] {line.decode('utf-8', errors='backslashreplace')}")
            if line.startswith(fail_prefix):
                raise BlePairHilFailure(f"{role} target 실패: {line!r}")
            if line.startswith(final_prefix):
                if not line.endswith(nonce_suffix):
                    raise BlePairHilFailure(f"{role} FINAL nonce 불일치: {line!r}")
                return
    except Exception:
        stop_event.set()
        raise


## @brief flash 전 UART를 열어 두 role의 전체 boot transcript를 보존합니다.
def execute_pair(
    *,
    serial_module: Any,
    milestone: str,
    peripheral_endpoint: RoleEndpoint,
    central_endpoint: RoleEndpoint,
    peripheral_image: Path,
    central_image: Path,
    nonce: str,
    baud_rate: int,
    flash_timeout: float,
    result_timeout: float,
) -> PairExecution:
    if baud_rate != DEFAULT_BAUD_RATE:
        raise BlePairHilFailure(f"기준선은 {DEFAULT_BAUD_RATE} baud만 허용합니다.")
    if not 30.0 <= result_timeout <= 600.0:
        raise BlePairHilFailure("--result-timeout은 30..600초여야 합니다.")

    captures = {"peripheral": bytearray(), "central": bytearray()}
    pending = {"peripheral": bytearray(), "central": bytearray()}
    flashes = {
        "peripheral": ("not-started", "unknown"),
        "central": ("not-started", "unknown"),
    }
    try:
        with ExitStack() as stack:
            ports = {}
            for role, endpoint in (
                ("peripheral", peripheral_endpoint),
                ("central", central_endpoint),
            ):
                ports[role] = stack.enter_context(
                    serial_module.Serial(
                        port=endpoint.port_name,
                        baudrate=baud_rate,
                        bytesize=serial_module.EIGHTBITS,
                        parity=serial_module.PARITY_NONE,
                        stopbits=serial_module.STOPBITS_ONE,
                        timeout=0.1,
                        write_timeout=2.0,
                    )
                )
                ports[role].reset_input_buffer()

            flashes["peripheral"] = flash_image(
                milestone,
                "peripheral",
                peripheral_endpoint.volume,
                peripheral_image,
                flash_timeout,
            )
            flashes["central"] = flash_image(
                milestone,
                "central",
                central_endpoint.volume,
                central_image,
                flash_timeout,
            )
            deadline = time.monotonic() + result_timeout
            for role in ("peripheral", "central"):
                wait_ready(
                    ports[role], milestone, role, pending[role], captures[role], deadline
                )
            write_start_command(ports["peripheral"], milestone, nonce)
            wait_peripheral_advertising(
                ports["peripheral"],
                milestone,
                nonce,
                pending["peripheral"],
                captures["peripheral"],
                deadline,
            )
            write_start_command(ports["central"], milestone, nonce)

            stop_event = threading.Event()
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [
                    executor.submit(
                        collect_until_final,
                        ports[role],
                        milestone,
                        role,
                        nonce,
                        pending[role],
                        captures[role],
                        deadline,
                        stop_event,
                    )
                    for role in ("peripheral", "central")
                ]
                try:
                    for future in futures:
                        future.result()
                except Exception:
                    stop_event.set()
                    raise
    except Exception as error:
        raise PairExecutionFailure(
            str(error), bytes(captures["peripheral"]), bytes(captures["central"])
        ) from error

    return PairExecution(
        RoleExecution(*flashes["peripheral"], bytes(captures["peripheral"])),
        RoleExecution(*flashes["central"], bytes(captures["central"])),
    )


## @brief milestone protocol line만 추출하고 stale nonce·FAIL을 거부합니다.
def protocol_lines(transcript: bytes, milestone: str, nonce: str) -> list[bytes]:
    nonce = build_nonce(nonce)
    prefix = f"NUCODE_{milestone}_".encode("ascii")
    ready_prefix = f"NUCODE_{milestone}_READY:".encode("ascii")
    fail_prefix = f"NUCODE_{milestone}_FAIL:".encode("ascii")
    expected_suffix = f":nonce={nonce}".encode("ascii")
    lines = [
        line.strip()
        for line in transcript.replace(b"\r", b"").split(b"\n")
        if line.strip().startswith(prefix)
    ]
    for line in lines:
        if line.startswith(fail_prefix):
            raise BlePairHilFailure(f"target 실패 token입니다: {line!r}")
        if line.startswith(ready_prefix):
            continue
        if not line.endswith(expected_suffix):
            raise BlePairHilFailure(f"stale 또는 다른 nonce token입니다: {line!r}")
    return lines


## @brief strict parser의 다음 exact line을 소비합니다.
def take_exact(lines: list[bytes], cursor: int, expected: bytes) -> int:
    if cursor >= len(lines):
        raise BlePairHilFailure(f"protocol line 누락: {expected!r}")
    if lines[cursor] != expected:
        raise BlePairHilFailure(
            f"protocol 순서/값 불일치: 기대={expected!r}, 실제={lines[cursor]!r}"
        )
    return cursor + 1


## @brief 시험 중 image byte 불변성을 재검사합니다.
def validate_image_unchanged(image: Path, size: int, sha256: str) -> None:
    if image.stat().st_size != size or file_sha256(image) != sha256:
        raise BlePairHilFailure("시험 중 HEX byte가 변경됐습니다.")


## @brief 실패 시점의 두 transcript를 출력 경로에 보존합니다.
def save_failure_transcripts(
    peripheral_path: Path, central_path: Path, error: Exception
) -> bool:
    if not isinstance(error, PairExecutionFailure):
        return False
    peripheral_path.write_bytes(error.peripheral_transcript)
    central_path.write_bytes(error.central_transcript)
    return True


## @brief raw transcript를 evidence용 identity record로 바꿉니다.
def transcript_record(path: Path, raw: bytes) -> dict[str, Any]:
    return {
        "name": path.name,
        "size": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


## @brief image를 build/flash identity record로 바꿉니다.
def image_record(
    image: Path,
    size: int,
    sha256: str,
    execution: RoleExecution,
    build_record: dict[str, str],
) -> dict[str, Any]:
    return {
        "name": image.name,
        "size": size,
        "sha256": sha256,
        "flash_sequence": execution.flash_sequence,
        "flash_bytes": execution.flash_bytes,
        "build_record": build_record,
    }


__all__ = [
    "BOARD_ROOT",
    "DEFAULT_BAUD_RATE",
    "DEFAULT_RESULT_TIMEOUT_SECONDS",
    "REPOSITORY",
    "BlePairHilFailure",
    "PairExecutionFailure",
    "RoleEndpoint",
    "build_nonce",
    "discover_endpoint",
    "execute_pair",
    "file_sha256",
    "git_revision",
    "image_record",
    "prepare_output_paths",
    "protocol_lines",
    "save_failure_transcripts",
    "take_exact",
    "transcript_record",
    "validate_board_revision",
    "validate_build_record",
    "validate_hex_image",
    "validate_image_unchanged",
    "validate_pair_identity",
    "validate_source_clean",
]
