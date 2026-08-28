#!/usr/bin/env python3
"""! @brief NU54DK M14 신규 핀을 DAPLink·UART·명시적 버튼 동작으로 검증합니다. """

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
import time
from typing import Any, Sequence


HIL_DIRECTORY = Path(__file__).resolve().parent
REPOSITORY = HIL_DIRECTORY.parents[2]
BOARD_ROOT = REPOSITORY / "board_package" / "NU54DK_Zephyr_DTS"
APPLICATION_SOURCE_ROOT = REPOSITORY / "tests" / "zephyr" / "m14_pin_hil"
CORE_SOURCE_SCOPES = (
    REPOSITORY / "cores" / "arduino",
    REPOSITORY / "dts",
    REPOSITORY / "libraries",
    REPOSITORY / "third_party" / "ArduinoCore-API",
    REPOSITORY / "third_party" / "ArduinoCore-API.provenance.yml",
    REPOSITORY / "variants" / "nu54dk",
    REPOSITORY / "zephyr",
)
BOARD_SOURCE_SCOPE = BOARD_ROOT / "boards" / "nucode" / "nu54dk"
if str(HIL_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(HIL_DIRECTORY))

from m6_serial_echo import (  # noqa: E402
    DEFAULT_BAUD_RATE,
    DEFAULT_BOARD_ID,
    DaplinkVolume,
    detail_value,
    find_daplink_volume,
    find_serial_port,
    import_pyserial,
    normalize_board_id,
    validate_hex_image,
    wait_for_flash_result,
)


READY_TOKEN = b"NUCODE_M14_PIN_HIL_READY:schema=1:action_timeout_ms=30000"
FINAL_PASS_TOKEN = b"NUCODE_M14_PIN_HIL_PASS"
FINAL_FAIL_TOKEN = b"NUCODE_M14_PIN_HIL_FAIL:"
PROTOCOL_PREFIX = b"NUCODE_M14_PIN_HIL_"
ACTION_TIMEOUT_MS = 30000
DEFAULT_RESULT_TIMEOUT_SECONDS = 520.0
MAX_TRANSCRIPT_BYTES = 131072
CORE_REVISION_PATTERN = re.compile(r"^[0-9a-f]{40}$")
BOARD_SUBMODULE_PATH = "board_package/NU54DK_Zephyr_DTS"

LED_PATTERN = re.compile(
    rb"^NUCODE_M14_PIN_HIL_LED:PASS:pin=(PIN_LED[23]):id=([0-9]+):"
    rb"low_read=LOW:high_read=HIGH:final=LOW$"
)
ACTION_PATTERN = re.compile(
    rb"^NUCODE_M14_PIN_HIL_ACTION:pin=(PIN_BUTTON[123]):id=([0-9]+):"
    rb"mode=([A-Z_]+):expected=([A-Z_]+):timeout_ms=([0-9]+)$"
)
INPUT_PATTERN = re.compile(
    rb"^NUCODE_M14_PIN_HIL_INPUT:PASS:pin=(PIN_BUTTON[123]):id=([0-9]+):"
    rb"mode=INPUT_PULLUP:released=HIGH$"
)
EDGE_PATTERN = re.compile(
    rb"^NUCODE_M14_PIN_HIL_EDGE:PASS:pin=(PIN_BUTTON[123]):id=([0-9]+):"
    rb"mode=([A-Z_]+):state=(LOW|HIGH):count=([0-9]+)$"
)
BUTTON_PATTERN = re.compile(
    rb"^NUCODE_M14_PIN_HIL_BUTTON:PASS:pin=(PIN_BUTTON[123]):id=([0-9]+):"
    rb"released=HIGH:pressed=LOW:modes=FALLING,RISING,CHANGE$"
)


class PinHilFailure(RuntimeError):
    """! @brief M14 HIL의 장치·protocol·evidence 계약 실패를 나타냅니다. """


class TranscriptTimeout(TimeoutError):
    """! @brief 제한 시간 동안 수집한 UART byte를 보존하는 timeout입니다. """

    def __init__(self, message: str, transcript: bytes) -> None:
        """! @brief 오류 설명과 수집된 transcript를 함께 저장합니다. """

        super().__init__(message)
        self.transcript = transcript


class TranscriptProtocolFailure(PinHilFailure):
    """! @brief protocol 실패와 원문 UART byte를 함께 보존합니다. """

    def __init__(self, message: str, transcript: bytes) -> None:
        """! @brief protocol 오류 설명과 수집된 transcript를 저장합니다. """

        super().__init__(message)
        self.transcript = transcript


@dataclass(frozen=True)
class LedResult:
    """! @brief 신규 LED 하나의 raw output/readback 결과입니다. """

    logical_name: str
    logical_id: int
    low_read: str = "LOW"
    high_read: str = "HIGH"
    final_state: str = "LOW"


@dataclass(frozen=True)
class ButtonResult:
    """! @brief 신규 버튼 하나의 raw 상태와 edge별 관찰 횟수입니다. """

    logical_name: str
    logical_id: int
    released: str
    pressed: str
    falling_edges: int
    rising_edges: int
    change_press_edges: int
    change_release_edges: int


@dataclass(frozen=True)
class PinHilResult:
    """! @brief 완전한 M14 신규 핀 protocol을 구조화한 결과입니다. """

    leds: tuple[LedResult, ...]
    buttons: tuple[ButtonResult, ...]


## @brief CLI 인자를 생성하며 시험이 아닌 parser unit test에도 고정 계약을 제공합니다.
def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "NU54DK M14 HEX를 DAPLink로 기록하고 화면의 안내에 맞춘 버튼 동작으로 "
            "신규 LED·버튼·interrupt를 검증합니다."
        )
    )
    parser.add_argument("--hex", dest="hex_path")
    parser.add_argument("--board-id", default=DEFAULT_BOARD_ID)
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
        "--acknowledge-manual-actions",
        action="store_true",
        help="세 버튼을 안내 순서대로 직접 누르고 뗄 준비가 되었음을 명시",
    )
    parser.add_argument(
        "--overwrite-evidence",
        action="store_true",
        help="기존 evidence와 transcript를 명시적으로 교체",
    )
    parser.add_argument(
        "--discover-only",
        action="store_true",
        help="MSD와 UART만 탐색하고 flash·핀 시험 없이 종료",
    )
    return parser.parse_args(arguments)


## @brief 파일의 SHA-256을 streaming 방식으로 계산합니다.
def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


## @brief CMake nucode_files_digest와 같은 상대 경로·file SHA 목록 digest를 계산합니다.
def files_digest(base_directory: Path, scopes: Sequence[Path]) -> str:
    input_files: list[Path] = []
    for scope in scopes:
        if scope.is_file():
            input_files.append(scope)
        elif scope.is_dir():
            input_files.extend(path for path in scope.rglob("*") if path.is_file())

    input_files.sort(key=lambda path: path.as_posix())
    if not input_files:
        raise PinHilFailure(f"source digest 입력 파일이 없습니다: {base_directory}")

    digest_input = "".join(
        f"{path.relative_to(base_directory).as_posix()}:{file_sha256(path)}\n"
        for path in input_files
    )
    return hashlib.sha256(digest_input.encode("utf-8")).hexdigest()


## @brief 현재 Core·M14 application·board tree의 build record digest를 계산합니다.
def current_source_digests() -> dict[str, str]:
    return {
        "core_source_sha256": files_digest(REPOSITORY, CORE_SOURCE_SCOPES),
        "application_source_sha256": files_digest(
            APPLICATION_SOURCE_ROOT, (APPLICATION_SOURCE_ROOT,)
        ),
        "board_source_sha256": files_digest(BOARD_ROOT, (BOARD_SOURCE_SCOPE,)),
    }


## @brief 저장소가 기대한 정확한 commit인지 검사하고 현재 revision을 반환합니다.
def git_revision(repository: Path, expected: str | None = None) -> str:
    result = subprocess.run(
        ["git", "-C", str(repository), "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    revision = result.stdout.strip().lower()
    if result.returncode != 0 or CORE_REVISION_PATTERN.fullmatch(revision) is None:
        raise PinHilFailure(f"Git revision을 확인하지 못했습니다: {repository}")
    if expected is not None:
        normalized = expected.strip().lower()
        if CORE_REVISION_PATTERN.fullmatch(normalized) is None:
            raise PinHilFailure("--expected-core-revision은 40자리 소문자 SHA여야 합니다.")
        if revision != normalized:
            raise PinHilFailure(
                f"Core revision 불일치: 기대={normalized}, 실제={revision}"
            )
    return revision


## @brief 부모 commit이 고정한 board submodule gitlink revision을 반환합니다.
def parent_board_revision() -> str:
    result = subprocess.run(
        ["git", "-C", str(REPOSITORY), "rev-parse", f"HEAD:{BOARD_SUBMODULE_PATH}"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    revision = result.stdout.strip().lower()
    if result.returncode != 0 or CORE_REVISION_PATTERN.fullmatch(revision) is None:
        raise PinHilFailure("부모 commit의 board submodule gitlink를 확인하지 못했습니다.")
    return revision


## @brief 현재 board checkout이 부모 commit의 exact gitlink와 같은지 검사합니다.
def validate_board_revision(board_revision: str) -> None:
    expected = parent_board_revision()
    if board_revision != expected:
        raise PinHilFailure(
            "board_package submodule revision이 부모 commit의 gitlink와 다릅니다: "
            f"기대={expected}, 실제={board_revision}"
        )


## @brief HIL과 보드 원본의 tracked/untracked 변경이 없는지 fail-closed 검사합니다.
def validate_source_clean() -> None:
    core_paths = (
        "cores/arduino",
        "dts",
        "libraries",
        "third_party/ArduinoCore-API",
        "third_party/ArduinoCore-API.provenance.yml",
        "variants/nu54dk",
        "zephyr",
        "tests/zephyr/m14_pin_hil",
        "tests/hil/nu54dk/m14_pin_hil.py",
    )
    core = subprocess.run(
        [
            "git",
            "-C",
            str(REPOSITORY),
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            "--",
            *core_paths,
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    board = subprocess.run(
        [
            "git",
            "-C",
            str(BOARD_ROOT),
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if core.returncode != 0 or core.stdout.strip():
        raise PinHilFailure(
            "M14 HIL source에 commit되지 않은 변경이 있습니다. 먼저 commit한 exact "
            f"source로 다시 빌드하십시오: {core.stdout.strip() or core.stderr.strip()}"
        )
    if board.returncode != 0 or board.stdout.strip():
        raise PinHilFailure(
            "board_package submodule이 clean하지 않습니다: "
            f"{board.stdout.strip() or board.stderr.strip()}"
        )


## @brief build record의 단일 quoted scalar를 읽습니다.
def build_record_value(text: str, key: str) -> str:
    match = re.search(rf"^\s*{re.escape(key)}:\s*'([^']+)'\s*$", text, re.MULTILINE)
    if match is None:
        raise PinHilFailure(f"NUCODE build record key가 없습니다: {key}")
    return match.group(1)


## @brief HEX와 함께 생성된 NUCODE build record를 exact revision·target에 결합합니다.
def validate_build_record(
    image: Path, core_revision: str, board_revision: str
) -> dict[str, str]:
    record_path = image.parent.parent / "nucode_arduino_core_build.yml"
    try:
        if record_path.stat().st_size > 16384:
            raise PinHilFailure("NUCODE build record가 허용 크기를 초과했습니다.")
        text = record_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise PinHilFailure(
            f"HEX의 NUCODE build record를 읽지 못했습니다: {record_path}: {error}"
        ) from error
    values = {
        key: build_record_value(text, key)
        for key in (
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
    }
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
            raise PinHilFailure(
                f"NUCODE build record가 exact HIL 계약과 다릅니다: "
                f"{key}={values[key]}, expected={expected_value}"
            )
    source_digests = current_source_digests()
    for key, expected_digest in source_digests.items():
        if re.fullmatch(r"[0-9a-f]{64}", values[key]) is None:
            raise PinHilFailure(f"NUCODE build record digest가 잘못되었습니다: {key}")
        if values[key] != expected_digest:
            raise PinHilFailure(
                "NUCODE build record source digest가 현재 exact source와 다릅니다: "
                f"{key}={values[key]}, expected={expected_digest}"
            )
    values["record_name"] = record_path.name
    values["record_sha256"] = file_sha256(record_path)
    return values


## @brief M14 HEX를 DAPLink MSD로 기록하고 완료 sequence와 byte 수를 반환합니다.
def flash_image(
    volume: DaplinkVolume, image: Path, timeout_seconds: float
) -> tuple[str, str]:
    if timeout_seconds <= 0:
        raise PinHilFailure("--flash-timeout은 0보다 커야 합니다.")
    previous_sequence = detail_value(volume.details, "Flash Sequence")
    shutil.copyfile(image, volume.root / "NUCODE_M14_PIN_HIL.HEX")
    details = wait_for_flash_result(volume.root, previous_sequence, timeout_seconds)
    return (
        detail_value(details, "Flash Sequence") or "unknown",
        detail_value(details, "Last Flash Bytes") or "unknown",
    )


## @brief 최종 PASS/FAIL까지 UART를 실시간 표시하며 제한된 크기로 수집합니다.
def read_transcript(serial_port: Any, timeout_seconds: float) -> bytes:
    if not 60.0 <= timeout_seconds <= 600.0:
        raise PinHilFailure("--result-timeout은 60..600초 범위여야 합니다.")

    deadline = time.monotonic() + timeout_seconds
    observed = bytearray()
    while time.monotonic() < deadline:
        waiting = serial_port.in_waiting
        chunk = serial_port.read(waiting if waiting > 0 else 1)
        if not chunk:
            continue
        observed.extend(chunk)
        sys.stdout.write(chunk.decode("utf-8", errors="replace"))
        sys.stdout.flush()
        if len(observed) > MAX_TRANSCRIPT_BYTES:
            raise TranscriptProtocolFailure(
                "M14 UART transcript가 허용 크기를 초과했습니다.", bytes(observed)
            )

        complete_lines = bytes(observed).replace(b"\r", b"").split(b"\n")[:-1]
        if any(
            line.strip() == FINAL_PASS_TOKEN
            or line.strip().startswith(FINAL_FAIL_TOKEN)
            for line in complete_lines
        ):
            return bytes(observed)

    transcript = bytes(observed)
    raise TranscriptTimeout(
        "UART에서 M14 최종 PASS/FAIL token을 제한 시간 안에 찾지 못했습니다. "
        f"observed_tail={transcript[-512:]!r}",
        transcript,
    )


## @brief 한 protocol line이 기대 정규식·pin 이름·논리 ID와 일치하는지 검증합니다.
def match_pin_line(
    pattern: re.Pattern[bytes], line: bytes, expected_name: str, expected_id: int
) -> re.Match[bytes]:
    match = pattern.fullmatch(line)
    if match is None:
        raise PinHilFailure(f"M14 protocol line 형식이 다릅니다: {line!r}")
    actual_name = match.group(1).decode("ascii")
    actual_id = int(match.group(2), 10)
    if (actual_name, actual_id) != (expected_name, expected_id):
        raise PinHilFailure(
            "M14 protocol pin identity가 다릅니다: "
            f"기대={expected_name}/{expected_id}, 실제={actual_name}/{actual_id}"
        )
    return match


## @brief UART transcript가 정확한 M14 pin·action·edge 순서를 모두 만족하는지 검증합니다.
def parse_transcript(transcript: bytes) -> PinHilResult:
    normalized = transcript.replace(b"\r", b"")
    if FINAL_FAIL_TOKEN in normalized:
        raise PinHilFailure("target이 M14 신규 핀 HIL 실패를 보고했습니다.")
    protocol_lines = [
        line.strip()
        for line in normalized.split(b"\n")
        if line.strip().startswith(PROTOCOL_PREFIX)
    ]
    cursor = 0

    def take(expected: bytes | None = None) -> bytes:
        nonlocal cursor
        if cursor >= len(protocol_lines):
            raise PinHilFailure("M14 protocol line이 중간에 누락되었습니다.")
        line = protocol_lines[cursor]
        cursor += 1
        if expected is not None and line != expected:
            raise PinHilFailure(
                f"M14 protocol 순서/값이 다릅니다: 기대={expected!r}, 실제={line!r}"
            )
        return line

    take(READY_TOKEN)
    take(
        b"NUCODE_M14_PIN_HIL_EXCLUDED:pin=PIN_LED1:id=4:"
        b"owner=PIN_PWM0:evidence=M7_PWM_DRIVER"
    )

    leds: list[LedResult] = []
    for name, logical_id in (("PIN_LED2", 5), ("PIN_LED3", 6)):
        match_pin_line(LED_PATTERN, take(), name, logical_id)
        leds.append(LedResult(logical_name=name, logical_id=logical_id))

    buttons: list[ButtonResult] = []
    action_contract = (
        ("INPUT_PULLUP", "RELEASE_HIGH"),
        ("FALLING", "PRESS_LOW"),
        ("RISING", "RELEASE_HIGH"),
        ("CHANGE_PRESS", "PRESS_LOW"),
        ("CHANGE_RELEASE", "RELEASE_HIGH"),
    )
    edge_contract = (
        ("FALLING", "LOW"),
        ("RISING", "HIGH"),
        ("CHANGE_PRESS", "LOW"),
        ("CHANGE_RELEASE", "HIGH"),
    )
    for name, logical_id in (
        ("PIN_BUTTON1", 7),
        ("PIN_BUTTON2", 8),
        ("PIN_BUTTON3", 9),
    ):
        action = match_pin_line(ACTION_PATTERN, take(), name, logical_id)
        if (
            action.group(3).decode("ascii"),
            action.group(4).decode("ascii"),
            int(action.group(5), 10),
        ) != (*action_contract[0], ACTION_TIMEOUT_MS):
            raise PinHilFailure("INPUT_PULLUP 사용자 동작 계약이 다릅니다.")
        match_pin_line(INPUT_PATTERN, take(), name, logical_id)

        counts: list[int] = []
        for action_expected, edge_expected in zip(
            action_contract[1:], edge_contract, strict=True
        ):
            action = match_pin_line(ACTION_PATTERN, take(), name, logical_id)
            if (
                action.group(3).decode("ascii"),
                action.group(4).decode("ascii"),
                int(action.group(5), 10),
            ) != (*action_expected, ACTION_TIMEOUT_MS):
                raise PinHilFailure(f"{action_expected[0]} 사용자 동작 계약이 다릅니다.")

            edge = match_pin_line(EDGE_PATTERN, take(), name, logical_id)
            actual_edge = (
                edge.group(3).decode("ascii"),
                edge.group(4).decode("ascii"),
            )
            if actual_edge != edge_expected:
                raise PinHilFailure(
                    f"{edge_expected[0]} edge/raw 상태가 다릅니다: {actual_edge}"
                )
            count = int(edge.group(5), 10)
            if count < 1:
                raise PinHilFailure(f"{edge_expected[0]} ISR edge가 관찰되지 않았습니다.")
            counts.append(count)

        if counts[3] <= counts[2]:
            raise PinHilFailure("CHANGE release가 press 뒤 추가 edge를 만들지 않았습니다.")
        match_pin_line(BUTTON_PATTERN, take(), name, logical_id)
        buttons.append(
            ButtonResult(
                logical_name=name,
                logical_id=logical_id,
                released="HIGH",
                pressed="LOW",
                falling_edges=counts[0],
                rising_edges=counts[1],
                change_press_edges=counts[2],
                change_release_edges=counts[3],
            )
        )

    take(FINAL_PASS_TOKEN)
    if cursor != len(protocol_lines):
        raise PinHilFailure(
            f"최종 PASS 뒤 예상하지 않은 M14 protocol line이 있습니다: {protocol_lines[cursor:]!r}"
        )
    return PinHilResult(leds=tuple(leds), buttons=tuple(buttons))


## @brief flash 뒤 UART에서 수동 동작 protocol을 수집하고 구조화합니다.
def verify_pin_hil(
    serial_module: Any,
    port_name: str,
    baud_rate: int,
    flash_callback: Any,
    result_timeout: float,
) -> tuple[str, str, bytes, PinHilResult]:
    if baud_rate != DEFAULT_BAUD_RATE:
        raise PinHilFailure(
            f"M14 기준선은 {DEFAULT_BAUD_RATE} baud만 허용합니다: 요청={baud_rate}"
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
        transcript = read_transcript(serial_port, result_timeout)
    try:
        result = parse_transcript(transcript)
    except PinHilFailure as error:
        raise TranscriptProtocolFailure(str(error), transcript) from error
    return sequence, byte_count, transcript, result


## @brief evidence와 companion transcript 경로의 안전한 신규 생성 조건을 검사합니다.
def prepare_output_paths(
    evidence_argument: str | None, overwrite: bool
) -> tuple[Path, Path]:
    if not evidence_argument:
        raise PinHilFailure("실제 시험에는 --evidence JSON 경로가 필요합니다.")
    evidence = Path(evidence_argument).resolve()
    if evidence.suffix.lower() != ".json":
        raise PinHilFailure("--evidence는 .json 확장자여야 합니다.")
    transcript = evidence.with_suffix(".transcript.log")
    for path in (evidence, transcript):
        if path.exists() and not overwrite:
            raise PinHilFailure(
                f"기존 증적을 자동 덮어쓰지 않습니다: {path}; 새 경로 또는 "
                "--overwrite-evidence를 사용하십시오."
            )
        if path.exists() and not path.is_file():
            raise PinHilFailure(f"증적 경로가 일반 파일이 아닙니다: {path}")
        if path.exists() and overwrite:
            path.unlink()
    evidence.parent.mkdir(parents=True, exist_ok=True)
    return evidence, transcript


## @brief 검증 결과를 artifact·revision·transcript byte identity와 결합합니다.
def build_evidence(
    *,
    core_revision: str,
    board_revision: str,
    board_id: str,
    image: Path,
    flash_sequence: str,
    flash_byte_count: str,
    port_name: str,
    transcript_path: Path,
    transcript: bytes,
    result: PinHilResult,
    build_record: dict[str, str],
    image_size: int,
    image_sha256: str,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "gate": "m14-nu54dk-pin-hil",
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
            "action_timeout_ms": ACTION_TIMEOUT_MS,
            "required_action_order": [
                "각 버튼 RELEASE_HIGH",
                "FALLING PRESS_LOW",
                "RISING RELEASE_HIGH",
                "CHANGE PRESS_LOW",
                "CHANGE RELEASE_HIGH",
            ],
        },
        "excluded_pin": {
            "logical_name": "PIN_LED1",
            "logical_id": 4,
            "owner": "PIN_PWM0",
            "regression_evidence": "M7_PWM_DRIVER",
        },
        "leds": [asdict(item) for item in result.leds],
        "buttons": [asdict(item) for item in result.buttons],
        "transcript": {
            "name": transcript_path.name,
            "size": len(transcript),
            "sha256": hashlib.sha256(transcript).hexdigest(),
        },
    }


## @brief 장치 탐색 또는 전체 M14 신규 pin HIL과 evidence 생성을 수행합니다.
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

    if not args.acknowledge_manual_actions:
        raise PinHilFailure(
            "실제 시험은 --acknowledge-manual-actions가 필요합니다. 화면 안내마다 "
            "PIN_BUTTON1, PIN_BUTTON2, PIN_BUTTON3을 직접 누르고 떼야 합니다."
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
        "M14 수동 fixture 시작: 각 ACTION token 뒤 지정된 버튼만 누르거나 떼십시오. "
        "동작별 제한 시간은 30초입니다. PIN_LED1은 PWM 소유이므로 시험하지 않습니다."
    )
    try:
        sequence, byte_count, transcript, result = verify_pin_hil(
            serial_module=serial_module,
            port_name=port_name,
            baud_rate=args.baud,
            flash_callback=lambda: flash_image(volume, image, args.flash_timeout),
            result_timeout=args.result_timeout,
        )
    except TranscriptTimeout as error:
        transcript_path.write_bytes(error.transcript)
        raise PinHilFailure(
            f"{error}; 실패 transcript={transcript_path}"
        ) from error
    except TranscriptProtocolFailure as error:
        transcript_path.write_bytes(error.transcript)
        raise PinHilFailure(
            f"{error}; 실패 transcript={transcript_path}"
        ) from error

    if image.stat().st_size != image_size or file_sha256(image) != image_sha256:
        transcript_path.write_bytes(transcript)
        raise PinHilFailure("수동 시험 중 HEX byte가 변경되어 PASS 증적 생성을 거부했습니다.")

    transcript_path.write_bytes(transcript)
    evidence = build_evidence(
        core_revision=core_revision,
        board_revision=board_revision,
        board_id=board_id,
        image=image,
        flash_sequence=sequence,
        flash_byte_count=byte_count,
        port_name=port_name,
        transcript_path=transcript_path,
        transcript=transcript,
        result=result,
        build_record=build_record,
        image_size=image_size,
        image_sha256=image_sha256,
    )
    evidence_path.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(
        "M14 pin HIL PASS: "
        f"leds={len(result.leds)}, buttons={len(result.buttons)}, "
        f"evidence={evidence_path}, transcript={transcript_path}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"M14 pin HIL FAIL: {error}", file=sys.stderr)
        raise SystemExit(1) from error
