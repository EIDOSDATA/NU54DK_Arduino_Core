"""NU54DK M6 Serial echo 펌웨어를 DAPLink와 UART로 자동 검증합니다."""

from __future__ import annotations

import argparse
import re
import secrets
import shutil
import string
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_BOARD_ID = "54153603000528402aae46c5e8e3712a"
DEFAULT_READY_TOKEN = r"NUCODE_M6_SERIAL_READY\r\n"
DEFAULT_ECHO_PREFIX = "NUCODE_M6_ECHO:"
DEFAULT_BAUD_RATE = 115200
MAX_PAYLOAD_BYTES = 64
DAPLINK_TARGET = "nRF54L15"
DAPLINK_VID = 0x0D28
DAPLINK_PID = 0x0204


@dataclass(frozen=True)
class DaplinkVolume:
    """탐색된 DAPLink MSD 볼륨과 DETAILS.TXT 내용을 함께 보관합니다."""

    root: Path
    details: str


def parse_arguments() -> argparse.Namespace:
    """HIL image, probe, UART와 protocol 선택 인자를 해석합니다."""

    parser = argparse.ArgumentParser(
        description=(
            "NU54DK M6 image를 DAPLink MSD로 기록하고 Serial READY/echo를 검증합니다."
        )
    )
    parser.add_argument(
        "--hex",
        dest="hex_path",
        help="기록할 zephyr.hex 경로(--discover-only가 아니면 필수)",
    )
    parser.add_argument(
        "--board-id",
        default=DEFAULT_BOARD_ID,
        help=f"DAPLink Unique ID(기본값: {DEFAULT_BOARD_ID})",
    )
    parser.add_argument(
        "--volume",
        help="DAPLink MSD 루트 강제 지정(예: E:\\); 기본값은 DETAILS.TXT 자동 탐색",
    )
    parser.add_argument(
        "--port",
        default="auto",
        help="UART 포트(예: COM10) 또는 auto(기본값)",
    )
    parser.add_argument(
        "--baud",
        type=int,
        default=DEFAULT_BAUD_RATE,
        help=f"UART baud rate(기본값: {DEFAULT_BAUD_RATE})",
    )
    parser.add_argument(
        "--ready-token",
        default=DEFAULT_READY_TOKEN,
        help=r"boot READY token; \\r, \\n escape 지원",
    )
    parser.add_argument(
        "--echo-prefix",
        default=DEFAULT_ECHO_PREFIX,
        help=r"echo 응답 prefix; \\r, \\n escape 지원",
    )
    parser.add_argument(
        "--payload",
        help="전송할 ASCII payload; 생략하면 실행마다 고유한 값을 생성",
    )
    parser.add_argument(
        "--flash-timeout",
        type=float,
        default=45.0,
        help="DAPLink flash 결과 제한 시간(초)",
    )
    parser.add_argument(
        "--ready-timeout",
        type=float,
        default=20.0,
        help="READY token 제한 시간(초)",
    )
    parser.add_argument(
        "--echo-timeout",
        type=float,
        default=10.0,
        help="echo 응답 제한 시간(초)",
    )
    parser.add_argument(
        "--discover-only",
        action="store_true",
        help="MSD와 UART만 탐색하고 flash/통신 없이 종료",
    )
    return parser.parse_args()


def normalize_board_id(board_id: str) -> str:
    """비교에 사용할 DAPLink Unique ID를 소문자로 정규화합니다."""

    normalized = board_id.strip().lower()
    if not normalized:
        raise ValueError("--board-id는 빈 문자열일 수 없습니다.")
    return normalized


def decode_ascii_argument(value: str, option_name: str) -> bytes:
    r"""CLI 문자열의 \\r, \\n, \\t, \\\\ escape를 안전하게 ASCII로 변환합니다."""

    decoded = bytearray()
    index = 0
    escapes = {"r": 0x0D, "n": 0x0A, "t": 0x09, "\\": 0x5C}

    while index < len(value):
        character = value[index]
        if character == "\\":
            if index + 1 >= len(value) or value[index + 1] not in escapes:
                raise ValueError(
                    f"{option_name}에는 \\r, \\n, \\t, \\\\ escape만 사용할 수 있습니다."
                )
            decoded.append(escapes[value[index + 1]])
            index += 2
            continue

        try:
            decoded.extend(character.encode("ascii"))
        except UnicodeEncodeError as error:
            raise ValueError(f"{option_name}은 ASCII 문자열이어야 합니다.") from error
        index += 1

    if not decoded:
        raise ValueError(f"{option_name}은 빈 문자열일 수 없습니다.")
    if 0 in decoded:
        raise ValueError(f"{option_name}에는 NUL 문자를 사용할 수 없습니다.")
    return bytes(decoded)


def build_payload(explicit_payload: str | None) -> bytes:
    """줄바꿈이 없는 ASCII payload를 검증하거나 고유 payload를 생성합니다."""

    if explicit_payload is None:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        explicit_payload = f"NU54_M6_{timestamp}_{secrets.token_hex(6)}"

    try:
        payload = explicit_payload.encode("ascii")
    except UnicodeEncodeError as error:
        raise ValueError("--payload는 ASCII 문자열이어야 합니다.") from error

    if not payload:
        raise ValueError("--payload는 빈 문자열일 수 없습니다.")
    if b"\r" in payload or b"\n" in payload or b"\x00" in payload:
        raise ValueError("--payload에는 CR, LF, NUL 문자를 사용할 수 없습니다.")
    if len(payload) > MAX_PAYLOAD_BYTES:
        raise ValueError(f"--payload는 {MAX_PAYLOAD_BYTES} byte 이하여야 합니다.")
    return payload


def read_details(root: Path) -> str | None:
    """DAPLink DETAILS.TXT를 읽고 remount 중 오류는 일시적인 부재로 처리합니다."""

    try:
        return (root / "DETAILS.TXT").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def detail_value(details: str, key: str) -> str | None:
    """DETAILS.TXT에서 지정한 단일 key 값을 반환합니다."""

    match = re.search(rf"^{re.escape(key)}:\s*(.+?)\s*$", details, re.MULTILINE)
    return match.group(1) if match else None


def validate_daplink_details(details: str, board_id: str) -> None:
    """선택한 MSD가 요청한 NU54DK DAPLink인지 검증합니다."""

    target = detail_value(details, "Target Detect")
    unique_id = detail_value(details, "Unique ID")
    if target != DAPLINK_TARGET:
        raise RuntimeError(
            f"DAPLink Target Detect 불일치: 기대={DAPLINK_TARGET}, 실제={target or '없음'}"
        )
    if unique_id is None or unique_id.lower() != board_id:
        raise RuntimeError(
            f"DAPLink Unique ID 불일치: 기대={board_id}, 실제={unique_id or '없음'}"
        )


def find_daplink_volume(board_id: str, explicit_volume: str | None) -> DaplinkVolume:
    """드라이브 문자를 고정하지 않고 UID가 일치하는 DAPLink MSD를 찾습니다."""

    if explicit_volume:
        root = Path(explicit_volume).resolve()
        details = read_details(root)
        if details is None:
            raise RuntimeError(f"지정한 볼륨에서 DETAILS.TXT를 읽을 수 없습니다: {root}")
        validate_daplink_details(details, board_id)
        return DaplinkVolume(root=root, details=details)

    candidates: list[DaplinkVolume] = []
    for letter in string.ascii_uppercase:
        root = Path(f"{letter}:/")
        details = read_details(root)
        if details is None:
            continue
        if detail_value(details, "Target Detect") != DAPLINK_TARGET:
            continue
        unique_id = detail_value(details, "Unique ID")
        if unique_id is None or unique_id.lower() != board_id:
            continue
        candidates.append(DaplinkVolume(root=root, details=details))

    if len(candidates) != 1:
        roots = ", ".join(str(candidate.root) for candidate in candidates) or "없음"
        raise RuntimeError(
            "일치하는 NU54DK DAPLink MSD가 정확히 하나여야 합니다. "
            f"발견={len(candidates)}, 후보={roots}"
        )
    return candidates[0]


def import_pyserial() -> tuple[Any, Any]:
    """NCS Python에 포함된 pySerial 본체와 포트 탐색 모듈을 불러옵니다."""

    try:
        import serial
        from serial.tools import list_ports
    except ImportError as error:
        raise RuntimeError(
            "pySerial을 불러올 수 없습니다. NCS Toolchain Python으로 실행하세요: "
            r"C:\ncs\toolchains\dcbdc366a1\opt\bin\python.exe"
        ) from error
    return serial, list_ports


def port_diagnostic(port: Any) -> str:
    """포트 선택 오류에 사용할 간결한 진단 문자열을 생성합니다."""

    return (
        f"{port.device}(serial={port.serial_number or '없음'}, "
        f"location={port.location or '없음'}, hwid={port.hwid or '없음'})"
    )


def is_target_uart_interface(port: Any) -> bool:
    """NU54DK DAPLink에서 검증된 target UART interface 3인지 판정합니다."""

    location = (port.location or "").lower()
    hardware_id = (port.hwid or "").lower()
    return location.endswith(":x.3") or "mi_03" in hardware_id


def find_serial_port(board_id: str, explicit_port: str, list_ports: Any) -> str:
    """UID와 DAPLink USB 정보로 target UART를 찾거나 명시 포트를 검증합니다."""

    ports = list(list_ports.comports())
    if explicit_port.lower() != "auto":
        requested = explicit_port.casefold()
        matches = [port for port in ports if port.device.casefold() == requested]
        if len(matches) != 1:
            available = ", ".join(port.device for port in ports) or "없음"
            raise RuntimeError(
                f"지정한 UART 포트를 찾을 수 없습니다: {explicit_port}, 사용 가능={available}"
            )
        selected_serial = (matches[0].serial_number or "").lower()
        if selected_serial and selected_serial != board_id:
            raise RuntimeError(
                "지정한 UART 포트의 USB serial이 DAPLink UID와 다릅니다: "
                f"port={matches[0].device}, serial={selected_serial}, uid={board_id}"
            )
        return matches[0].device

    candidates = [
        port
        for port in ports
        if (port.serial_number or "").lower() == board_id
        and (port.vid in (None, DAPLINK_VID))
        and (port.pid in (None, DAPLINK_PID))
    ]
    if len(candidates) == 1:
        return candidates[0].device

    target_uart_candidates = [port for port in candidates if is_target_uart_interface(port)]
    if len(target_uart_candidates) == 1:
        return target_uart_candidates[0].device

    diagnostics = "; ".join(port_diagnostic(port) for port in candidates) or "없음"
    raise RuntimeError(
        "target UART를 하나로 결정할 수 없습니다. --port COM10처럼 명시하세요. "
        f"UID 일치 후보={diagnostics}"
    )


def validate_hex_image(hex_path: str | None) -> Path:
    """DAPLink에 기록할 Intel HEX 파일의 기본 형식과 경로를 검증합니다."""

    if not hex_path:
        raise ValueError("--discover-only가 아니면 --hex가 필요합니다.")

    image = Path(hex_path).resolve()
    if not image.is_file():
        raise FileNotFoundError(f"HEX 파일을 찾을 수 없습니다: {image}")
    if image.suffix.lower() != ".hex":
        raise ValueError(f".hex 확장자만 기록할 수 있습니다: {image}")
    if image.stat().st_size == 0:
        raise ValueError(f"빈 HEX 파일은 기록할 수 없습니다: {image}")

    with image.open("rb") as stream:
        first_nonempty = next((line.strip() for line in stream if line.strip()), b"")
    if not first_nonempty.startswith(b":"):
        raise ValueError(f"Intel HEX record로 시작하지 않습니다: {image}")
    return image


def wait_for_flash_result(
    root: Path, previous_sequence: str | None, timeout_seconds: float
) -> str:
    """DAPLink remount와 sequence 증가를 기다리고 SUCCESS 결과를 검증합니다."""

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        details = read_details(root)
        if details is not None:
            result = detail_value(details, "Last Flash Result")
            sequence = detail_value(details, "Flash Sequence")
            sequence_changed = previous_sequence is None or sequence != previous_sequence
            if sequence_changed and result == "SUCCESS":
                return details
            if sequence_changed and result not in (None, "NONE", "SUCCESS"):
                error = detail_value(details, "Last Flash Error") or "알 수 없음"
                raise RuntimeError(f"DAPLink flash 실패: result={result}, error={error}")
        time.sleep(0.2)

    raise TimeoutError(
        f"DAPLink flash SUCCESS를 {timeout_seconds:.1f}초 안에 확인하지 못했습니다."
    )


def flash_image(
    volume: DaplinkVolume, image: Path, timeout_seconds: float
) -> tuple[str, str]:
    """Intel HEX를 MSD에 복사하고 DAPLink가 보고한 성공 sequence를 반환합니다."""

    if timeout_seconds <= 0:
        raise ValueError("--flash-timeout은 0보다 커야 합니다.")

    previous_sequence = detail_value(volume.details, "Flash Sequence")
    destination = volume.root / "NUCODE_M6.HEX"
    shutil.copyfile(image, destination)
    result_details = wait_for_flash_result(
        volume.root, previous_sequence, timeout_seconds
    )
    sequence = detail_value(result_details, "Flash Sequence") or "unknown"
    byte_count = detail_value(result_details, "Last Flash Bytes") or "unknown"
    return sequence, byte_count


def read_until_sequence(
    serial_port: Any,
    expected: bytes,
    timeout_seconds: float,
    initial_data: bytes = b"",
) -> tuple[bytes, bytes]:
    """UART stream에서 byte sequence를 찾고 전체 관찰값과 뒤쪽 잔여값을 반환합니다."""

    if timeout_seconds <= 0:
        raise ValueError("serial timeout은 0보다 커야 합니다.")

    deadline = time.monotonic() + timeout_seconds
    observed = bytearray(initial_data)
    while time.monotonic() < deadline:
        match_index = observed.find(expected)
        if match_index >= 0:
            remainder_index = match_index + len(expected)
            return bytes(observed), bytes(observed[remainder_index:])

        waiting = serial_port.in_waiting
        chunk = serial_port.read(waiting if waiting > 0 else 1)
        if chunk:
            observed.extend(chunk)
            if len(observed) > 65536:
                del observed[: len(observed) - 65536]

    raise TimeoutError(
        f"UART에서 기대 sequence를 {timeout_seconds:.1f}초 안에 찾지 못했습니다. "
        f"expected={expected!r}, observed_tail={bytes(observed[-256:])!r}"
    )


def verify_serial_echo(
    serial_module: Any,
    port_name: str,
    baud_rate: int,
    ready_token: bytes,
    echo_prefix: bytes,
    payload: bytes,
    flash_callback: Any,
    ready_timeout: float,
    echo_timeout: float,
) -> tuple[str, str]:
    """flash 전 UART를 열어 boot token을 보존하고 고유 payload echo를 검증합니다."""

    if baud_rate != DEFAULT_BAUD_RATE:
        raise ValueError(
            f"M6 기준선은 {DEFAULT_BAUD_RATE} baud만 허용합니다: 요청={baud_rate}"
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

        _, remainder = read_until_sequence(
            serial_port, ready_token, ready_timeout
        )
        request = payload + b"\r\n"
        expected_echo = echo_prefix + payload + b"\r\n"
        written = serial_port.write(request)
        serial_port.flush()
        if written != len(request):
            raise RuntimeError(
                f"UART payload 일부만 전송했습니다: 기대={len(request)}, 실제={written}"
            )

        read_until_sequence(
            serial_port,
            expected_echo,
            echo_timeout,
            initial_data=remainder,
        )
        return sequence, byte_count


def main() -> int:
    """장치 탐색 또는 전체 M6 flash/Serial echo HIL을 실행합니다."""

    arguments = parse_arguments()
    board_id = normalize_board_id(arguments.board_id)
    volume = find_daplink_volume(board_id, arguments.volume)
    serial_module, list_ports = import_pyserial()
    port_name = find_serial_port(board_id, arguments.port, list_ports)

    unique_id = detail_value(volume.details, "Unique ID") or "unknown"
    print(
        "NU54DK discovery SUCCESS: "
        f"uid={unique_id}, volume={volume.root}, port={port_name}, baud={arguments.baud}"
    )
    if arguments.discover_only:
        return 0

    if arguments.flash_timeout <= 0:
        raise ValueError("--flash-timeout은 0보다 커야 합니다.")
    if arguments.ready_timeout <= 0:
        raise ValueError("--ready-timeout은 0보다 커야 합니다.")
    if arguments.echo_timeout <= 0:
        raise ValueError("--echo-timeout은 0보다 커야 합니다.")

    image = validate_hex_image(arguments.hex_path)
    ready_token = decode_ascii_argument(arguments.ready_token, "--ready-token")
    echo_prefix = decode_ascii_argument(arguments.echo_prefix, "--echo-prefix")
    payload = build_payload(arguments.payload)

    sequence, byte_count = verify_serial_echo(
        serial_module=serial_module,
        port_name=port_name,
        baud_rate=arguments.baud,
        ready_token=ready_token,
        echo_prefix=echo_prefix,
        payload=payload,
        flash_callback=lambda: flash_image(
            volume, image, arguments.flash_timeout
        ),
        ready_timeout=arguments.ready_timeout,
        echo_timeout=arguments.echo_timeout,
    )
    print(
        "M6 Serial HIL PASS: "
        f"uid={unique_id}, sequence={sequence}, bytes={byte_count}, "
        f"port={port_name}, payload={payload.decode('ascii')}"
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print(f"M6 Serial HIL FAIL: {error}", file=sys.stderr)
        sys.exit(1)
