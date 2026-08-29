#!/usr/bin/env python3
"""! @brief 공식 clean Ubuntu CI M15 artifact의 SW0 System OFF wake를 검증합니다. """

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from typing import Any, Sequence


HIL_DIRECTORY = Path(__file__).resolve().parent
REPOSITORY = HIL_DIRECTORY.parents[2]
BOARD_ROOT = REPOSITORY / "board_package" / "NU54DK_Zephyr_DTS"
APPLICATION_SOURCE_ROOT = REPOSITORY / "tests" / "zephyr" / "m15_wake"
BOARD_SUBMODULE_PATH = "board_package/NU54DK_Zephyr_DTS"
CORE_REVISION_PATTERN = re.compile(r"^[0-9a-f]{40}$")
MAX_TRANSCRIPT_BYTES = 131072
MINIMUM_ENTERING_TO_PROMPT_MS = 2000
DEFAULT_RESULT_TIMEOUT_SECONDS = 240.0

if str(HIL_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(HIL_DIRECTORY))

from m6_serial_echo import (  # noqa: E402
    DEFAULT_BAUD_RATE,
    DaplinkVolume,
    detail_value,
    find_daplink_volume,
    find_serial_port,
    import_pyserial,
    normalize_board_id,
    validate_hex_image,
    wait_for_flash_result,
)
from m14_pin_hil import (  # noqa: E402
    CORE_SOURCE_SCOPES,
    build_record_value,
    file_sha256,
    git_committed_files_digest,
    git_revision,
    parent_board_revision,
    validate_board_revision,
)


READY_TOKEN = (
    b"NUCODE_M15_SYSTEM_OFF_READY:schema=1:command=ARM:"
    b"wake=SW0:gpio=P1.13:active=LOW"
)
REQUEST_TOKEN = (
    b"NUCODE_M15_SYSTEM_OFF_REQUEST:command=ARM:"
    b"wake=SW0:gpio=P1.13:active=LOW"
)
ACTION_TOKEN = (
    b"NUCODE_M15_SYSTEM_OFF_ACTION:wake=SW0:expected=PRESS_LOW:"
    b"host_wait_ms=2000"
)
ENTERING_TOKEN = b"NUCODE_M15_SYSTEM_OFF_ENTERING:mode=BUTTON_WAKE"
WAKE_BOOT_TOKEN = (
    b"NUCODE_M15_SYSTEM_OFF_BOOT:schema=1:phase=WAKE:reset=LOW_POWER_WAKE"
)
WAKE_TOKEN = (
    b"NUCODE_M15_SYSTEM_OFF_WAKE:PASS:source=SW0:gpio=P1.13:active=LOW"
)
FINAL_PASS_TOKEN = b"NUCODE_M15_SYSTEM_OFF_PASS"
FINAL_FAIL_TOKEN = b"NUCODE_M15_SYSTEM_OFF_FAIL:"
PROTOCOL_PREFIX = b"NUCODE_M15_SYSTEM_OFF_"


class SystemOffHilFailure(RuntimeError):
    """! @brief M15 System OFF HIL 계약 위반을 나타냅니다. """


class TranscriptFailure(SystemOffHilFailure):
    """! @brief 실패 원인과 수집된 UART byte를 함께 보존합니다. """

    def __init__(self, message: str, transcript: bytes) -> None:
        """! @brief 오류 설명과 현재까지의 transcript를 저장합니다. """

        super().__init__(message)
        self.transcript = transcript


@dataclass(frozen=True)
class SystemOffResult:
    """! @brief System OFF 진입과 SW0 wake 관찰 결과입니다. """

    wake_source: str = "SW0"
    gpio: str = "P1.13"
    active_level: str = "LOW"
    reset_cause: str = "LOW_POWER_WAKE"


@dataclass(frozen=True)
class CaptureResult:
    """! @brief UART 원문과 ENTERING 요청부터 wake까지의 host 계측값입니다. """

    transcript: bytes
    entering_to_wake_ms: int


## @brief 실제 실행 인자를 생성하고 명시적 장치·수동 동작 승인을 요구합니다.
def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "M15 System OFF image를 정확한 NU54DK에 기록하고 SW0(P1.13) "
            "wake와 low-power reset cause를 검증합니다."
        )
    )
    parser.add_argument("--hex", dest="hex_path")
    parser.add_argument(
        "--board-id",
        required=True,
        help="다중 보드 오선택을 막기 위한 온보드 CMSIS-DAP UID",
    )
    parser.add_argument("--volume")
    parser.add_argument("--port", default="auto")
    parser.add_argument("--baud", type=int, default=DEFAULT_BAUD_RATE)
    parser.add_argument("--flash-timeout", type=float, default=45.0)
    parser.add_argument(
        "--result-timeout", type=float, default=DEFAULT_RESULT_TIMEOUT_SECONDS
    )
    parser.add_argument(
        "--evidence",
        help="PASS JSON evidence 경로(--discover-only가 아니면 필수)",
    )
    parser.add_argument(
        "--expected-core-revision",
        help="시험할 checkout의 기대 40자리 Core commit",
    )
    parser.add_argument(
        "--acknowledge-button-wake",
        action="store_true",
        help="host 안내 뒤 SW0을 한 번 누를 준비가 되었음을 명시",
    )
    parser.add_argument(
        "--overwrite-evidence",
        action="store_true",
        help="기존 evidence와 transcript를 명시적으로 교체",
    )
    parser.add_argument(
        "--discover-only",
        action="store_true",
        help="MSD와 UART만 탐색하고 flash·System OFF 시험 없이 종료",
    )
    return parser.parse_args(arguments)


## @brief 공식 clean Ubuntu CI와 같은 commit blob 기준의 digest를 계산합니다.
def current_source_digests() -> dict[str, str]:
    board_scope = BOARD_ROOT / "boards" / "nucode" / "nu54dk"
    return {
        "core_source_sha256": git_committed_files_digest(
            REPOSITORY, REPOSITORY, CORE_SOURCE_SCOPES
        ),
        "application_source_sha256": git_committed_files_digest(
            REPOSITORY, APPLICATION_SOURCE_ROOT, (APPLICATION_SOURCE_ROOT,)
        ),
        "board_source_sha256": git_committed_files_digest(
            BOARD_ROOT, BOARD_ROOT, (board_scope,)
        ),
    }


## @brief System OFF HIL 입력 source와 board checkout이 clean한지 검사합니다.
def validate_source_clean() -> None:
    core_paths = (
        "cores/arduino",
        "dts",
        "libraries",
        "third_party/ArduinoCore-API",
        "third_party/ArduinoCore-API.provenance.yml",
        "variants/nu54dk",
        "zephyr",
        "tests/zephyr/m15_wake",
        "tests/hil/nu54dk/m15_system_off.py",
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
        raise SystemOffHilFailure(
            "M15 System OFF HIL source에 commit되지 않은 변경이 있습니다: "
            f"{core.stdout.strip() or core.stderr.strip()}"
        )
    if board.returncode != 0 or board.stdout.strip():
        raise SystemOffHilFailure(
            "board_package submodule이 clean하지 않습니다: "
            f"{board.stdout.strip() or board.stderr.strip()}"
        )


## @brief HEX build record를 exact revision, target과 source byte에 결합합니다.
def validate_build_record(
    image: Path, core_revision: str, board_revision: str
) -> dict[str, str]:
    record_path = image.parent.parent / "nucode_arduino_core_build.yml"
    try:
        if record_path.stat().st_size > 16384:
            raise SystemOffHilFailure("NUCODE build record가 허용 크기를 초과했습니다.")
        text = record_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise SystemOffHilFailure(
            f"HEX의 NUCODE build record를 읽지 못했습니다: {record_path}: {error}"
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
    values = {key: build_record_value(text, key) for key in keys}
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
            raise SystemOffHilFailure(
                "NUCODE build record가 exact M15 HIL 계약과 다릅니다: "
                f"{key}={values[key]}, expected={expected_value}"
            )
    for key, expected_digest in current_source_digests().items():
        if re.fullmatch(r"[0-9a-f]{64}", values[key]) is None:
            raise SystemOffHilFailure(f"NUCODE build record digest가 잘못되었습니다: {key}")
        if values[key] != expected_digest:
            raise SystemOffHilFailure(
                "NUCODE build record source digest가 현재 exact source와 다릅니다: "
                f"{key}={values[key]}, expected={expected_digest}"
            )
    values["record_name"] = record_path.name
    values["record_sha256"] = file_sha256(record_path)
    return values


## @brief M15 HEX를 DAPLink MSD로 기록하고 완료 sequence와 byte 수를 반환합니다.
def flash_image(
    volume: DaplinkVolume, image: Path, timeout_seconds: float
) -> tuple[str, str]:
    if timeout_seconds <= 0:
        raise SystemOffHilFailure("--flash-timeout은 0보다 커야 합니다.")
    previous_sequence = detail_value(volume.details, "Flash Sequence")
    shutil.copyfile(image, volume.root / "NUCODE_M15_SYSTEM_OFF.HEX")
    details = wait_for_flash_result(volume.root, previous_sequence, timeout_seconds)
    return (
        detail_value(details, "Flash Sequence") or "unknown",
        detail_value(details, "Last Flash Bytes") or "unknown",
    )


## @brief UART protocol의 정확한 순서와 단일 SW0 wake 결과만 승인합니다.
def parse_transcript(transcript: bytes) -> SystemOffResult:
    normalized = transcript.replace(b"\r", b"")
    if FINAL_FAIL_TOKEN in normalized:
        raise SystemOffHilFailure("target이 M15 System OFF 실패를 보고했습니다.")
    protocol_lines = [
        line.strip()
        for line in normalized.split(b"\n")
        if line.strip().startswith(PROTOCOL_PREFIX)
    ]
    expected = [
        READY_TOKEN,
        REQUEST_TOKEN,
        ACTION_TOKEN,
        ENTERING_TOKEN,
        WAKE_BOOT_TOKEN,
        WAKE_TOKEN,
        FINAL_PASS_TOKEN,
    ]
    if protocol_lines != expected:
        raise SystemOffHilFailure(
            "M15 System OFF protocol 순서/값이 다릅니다: "
            f"expected={expected!r}, actual={protocol_lines!r}"
        )
    return SystemOffResult()


## @brief ENTERING 요청부터 wake까지 최소 안내 간격이 지났는지 검사합니다.
def validate_entering_to_wake_interval(
    entering_at: float | None, wake_at: float | None
) -> int:
    if entering_at is None or wake_at is None or wake_at < entering_at:
        raise SystemOffHilFailure("ENTERING 요청과 wake 시각을 모두 관찰하지 못했습니다.")
    elapsed_ms = int(round((wake_at - entering_at) * 1000.0))
    if elapsed_ms < MINIMUM_ENTERING_TO_PROMPT_MS:
        raise SystemOffHilFailure(
            "SW0을 host의 PRESS NOW 안내보다 먼저 눌렀거나 ENTERING 요청부터 "
            f"wake까지의 간격이 너무 짧습니다: {elapsed_ms}ms"
        )
    return elapsed_ms


## @brief READY 뒤 ARM을 전송하고 System OFF·SW0 wake의 완전한 UART 결과를 수집합니다.
def capture_protocol(
    serial_port: Any,
    timeout_seconds: float,
    *,
    monotonic: Any = time.monotonic,
) -> CaptureResult:
    if not 30.0 <= timeout_seconds <= 600.0:
        raise SystemOffHilFailure("--result-timeout은 30..600초 범위여야 합니다.")

    deadline = monotonic() + timeout_seconds
    observed = bytearray()
    processed_lines = 0
    arm_sent = False
    prompt_emitted = False
    entering_at: float | None = None
    wake_at: float | None = None

    while True:
        now = monotonic()
        if (
            entering_at is not None
            and not prompt_emitted
            and ((now - entering_at) * 1000.0) >= MINIMUM_ENTERING_TO_PROMPT_MS
        ):
            print("M15 PRESS NOW: NU54DK의 SW0(P1.13)을 한 번 누르십시오.")
            prompt_emitted = True
        if now >= deadline:
            break
        waiting = serial_port.in_waiting
        chunk = serial_port.read(waiting if waiting > 0 else 1)
        if not chunk:
            continue
        observed.extend(chunk)
        sys.stdout.write(chunk.decode("utf-8", errors="replace"))
        sys.stdout.flush()
        if len(observed) > MAX_TRANSCRIPT_BYTES:
            raise TranscriptFailure(
                "M15 UART transcript가 허용 크기를 초과했습니다.", bytes(observed)
            )

        complete_lines = bytes(observed).replace(b"\r", b"").split(b"\n")[:-1]
        for line in complete_lines[processed_lines:]:
            token = line.strip()
            if token == READY_TOKEN and not arm_sent:
                serial_port.write(b"ARM\n")
                serial_port.flush()
                arm_sent = True
                print("M15 ARM 명령을 전송했습니다. 아직 SW0을 누르지 마십시오.")
            elif token == ENTERING_TOKEN and entering_at is None:
                entering_at = monotonic()
            elif token == WAKE_BOOT_TOKEN and wake_at is None:
                wake_at = monotonic()
            if token == FINAL_PASS_TOKEN or token.startswith(FINAL_FAIL_TOKEN):
                transcript = bytes(observed)
                try:
                    parse_transcript(transcript)
                    if not arm_sent or not prompt_emitted:
                        raise SystemOffHilFailure(
                            "ARM 전송 또는 PRESS NOW 안내 없이 최종 token이 나타났습니다."
                        )
                    entering_to_wake_ms = validate_entering_to_wake_interval(
                        entering_at, wake_at
                    )
                except SystemOffHilFailure as error:
                    raise TranscriptFailure(str(error), transcript) from error
                return CaptureResult(transcript, entering_to_wake_ms)
        processed_lines = len(complete_lines)

    transcript = bytes(observed)
    raise TranscriptFailure(
        "UART에서 M15 최종 PASS/FAIL token을 제한 시간 안에 찾지 못했습니다. "
        f"observed_tail={transcript[-512:]!r}",
        transcript,
    )


## @brief flash부터 UART 명령·수동 SW0 wake까지 하나의 serial session에서 수행합니다.
def verify_system_off(
    serial_module: Any,
    port_name: str,
    baud_rate: int,
    flash_callback: Any,
    result_timeout: float,
) -> tuple[str, str, CaptureResult, SystemOffResult]:
    if baud_rate != DEFAULT_BAUD_RATE:
        raise SystemOffHilFailure(
            f"M15 기준선은 {DEFAULT_BAUD_RATE} baud만 허용합니다: 요청={baud_rate}"
        )
    with serial_module.Serial(
        port=port_name,
        baudrate=baud_rate,
        bytesize=serial_module.EIGHTBITS,
        parity=serial_module.PARITY_NONE,
        stopbits=serial_module.STOPBITS_ONE,
        timeout=0.1,
        write_timeout=2.0,
    ) as serial_port:
        serial_port.reset_input_buffer()
        sequence, byte_count = flash_callback()
        capture = capture_protocol(serial_port, result_timeout)
    return sequence, byte_count, capture, parse_transcript(capture.transcript)


## @brief evidence와 companion transcript의 신규 생성 조건을 검사합니다.
def prepare_output_paths(
    evidence_argument: str | None, overwrite: bool
) -> tuple[Path, Path]:
    if not evidence_argument:
        raise SystemOffHilFailure("실제 시험에는 --evidence JSON 경로가 필요합니다.")
    evidence = Path(evidence_argument).resolve()
    if evidence.suffix.lower() != ".json":
        raise SystemOffHilFailure("--evidence는 .json 확장자여야 합니다.")
    transcript = evidence.with_suffix(".transcript.log")
    for path in (evidence, transcript):
        if path.exists() and not overwrite:
            raise SystemOffHilFailure(
                f"기존 증적을 자동 덮어쓰지 않습니다: {path}; 새 경로 또는 "
                "--overwrite-evidence를 사용하십시오."
            )
        if path.exists() and not path.is_file():
            raise SystemOffHilFailure(f"증적 경로가 일반 파일이 아닙니다: {path}")
        if path.exists() and overwrite:
            path.unlink()
    evidence.parent.mkdir(parents=True, exist_ok=True)
    return evidence, transcript


## @brief PASS 결과를 source·image·UART byte identity와 결합합니다.
def build_evidence(
    *,
    core_revision: str,
    board_revision: str,
    board_id: str,
    image: Path,
    image_size: int,
    image_sha256: str,
    flash_sequence: str,
    flash_byte_count: str,
    port_name: str,
    transcript_path: Path,
    capture: CaptureResult,
    result: SystemOffResult,
    build_record: dict[str, str],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "gate": "m15-nu54dk-system-off-wake-hil",
        "status": "passed",
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "core_revision": core_revision,
        "board_revision": board_revision,
        "board_target": "nrf54l15dk/nrf54l15/cpuapp/nu54dk",
        "probe": {"type": "CMSIS-DAP-v2", "uid": board_id},
        "serial": {"port": port_name, "baud": DEFAULT_BAUD_RATE},
        "flash": {
            "transport": "DAPLink-MSD",
            "mass_erase_requested": False,
            "recover_requested": False,
            "sequence": flash_sequence,
            "byte_count": flash_byte_count,
        },
        "image": {
            "name": image.name,
            "size": image_size,
            "sha256": image_sha256,
        },
        "build_record": build_record,
        "manual_fixture": {
            "acknowledged": True,
            "action": "SW0_PRESS_LOW",
            "logical_button": "SW0",
            "gpio": "P1.13",
            "host_prompted_after_entering_request": True,
            "minimum_entering_to_prompt_ms": MINIMUM_ENTERING_TO_PROMPT_MS,
        },
        "result": {
            "wake_source": result.wake_source,
            "gpio": result.gpio,
            "active_level": result.active_level,
            "reset_cause": result.reset_cause,
            "observed_entering_to_wake_ms": capture.entering_to_wake_ms,
        },
        "transcript": {
            "name": transcript_path.name,
            "size": len(capture.transcript),
            "sha256": hashlib.sha256(capture.transcript).hexdigest(),
        },
    }


## @brief 장치 탐색 또는 전체 M15 System OFF HIL과 evidence 생성을 수행합니다.
def main(arguments: Sequence[str] | None = None) -> int:
    args = parse_arguments(arguments)
    board_id = normalize_board_id(args.board_id)
    volume = find_daplink_volume(board_id, args.volume)
    serial_module, list_ports = import_pyserial()
    port_name = find_serial_port(board_id, args.port, list_ports)
    print(
        "NU54DK discovery SUCCESS: "
        f"uid={board_id}, volume={volume.root}, port={port_name}, baud={args.baud}"
    )
    if args.discover_only:
        return 0

    if not args.acknowledge_button_wake:
        raise SystemOffHilFailure(
            "실제 시험은 --acknowledge-button-wake가 필요합니다. runner의 PRESS NOW "
            "안내가 나온 뒤에만 SW0(P1.13)을 한 번 눌러야 합니다."
        )
    evidence_path, transcript_path = prepare_output_paths(
        args.evidence, args.overwrite_evidence
    )
    image = validate_hex_image(args.hex_path)
    core_revision = git_revision(REPOSITORY, args.expected_core_revision)
    board_revision = git_revision(BOARD_ROOT)
    validate_board_revision(board_revision)
    validate_source_clean()
    build_record = validate_build_record(image, core_revision, board_revision)
    image_size = image.stat().st_size
    image_sha256 = file_sha256(image)

    print(
        "M15 System OFF HIL 시작: ARM은 runner가 전송합니다. "
        "'M15 PRESS NOW'가 나오기 전에는 SW0을 누르지 마십시오."
    )
    try:
        sequence, byte_count, capture, result = verify_system_off(
            serial_module=serial_module,
            port_name=port_name,
            baud_rate=args.baud,
            flash_callback=lambda: flash_image(volume, image, args.flash_timeout),
            result_timeout=args.result_timeout,
        )
    except TranscriptFailure as error:
        transcript_path.write_bytes(error.transcript)
        raise SystemOffHilFailure(
            f"{error}; 실패 transcript={transcript_path}"
        ) from error

    if image.stat().st_size != image_size or file_sha256(image) != image_sha256:
        transcript_path.write_bytes(capture.transcript)
        raise SystemOffHilFailure("수동 시험 중 HEX byte가 변경되어 PASS 증적 생성을 거부했습니다.")

    transcript_path.write_bytes(capture.transcript)
    evidence = build_evidence(
        core_revision=core_revision,
        board_revision=board_revision,
        board_id=board_id,
        image=image,
        image_size=image_size,
        image_sha256=image_sha256,
        flash_sequence=sequence,
        flash_byte_count=byte_count,
        port_name=port_name,
        transcript_path=transcript_path,
        capture=capture,
        result=result,
        build_record=build_record,
    )
    evidence_path.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(
        "M15 System OFF wake HIL PASS: "
        f"entering_to_wake_ms={capture.entering_to_wake_ms}, evidence={evidence_path}, "
        f"transcript={transcript_path}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"M15 System OFF HIL FAIL: {error}", file=sys.stderr)
        raise SystemExit(1) from error
