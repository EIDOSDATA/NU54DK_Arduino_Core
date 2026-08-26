"""! @brief NU54DK M7 Wire와 0x6B LSM6DS3TR-C WHO_AM_I 경로를 안전하게 검증합니다. """

from __future__ import annotations

import argparse
import re
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


HIL_DIRECTORY = Path(__file__).resolve().parent
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
    read_until_sequence,
    validate_hex_image,
    wait_for_flash_result,
)


IMU_I2C_ADDRESS = 0x6B
WHO_AM_I_REGISTER = 0x0F
WHO_AM_I_EXPECTED = 0x6A
READY_TOKEN = b"NUCODE_M7_I2C_READY\r\n"
REQUEST_TOKEN = b"NUCODE_M7_I2C_WHOAMI_RS:6B:0F\r\n"
RESULT_PREFIX = b"NUCODE_M7_I2C_RESULT:"
RESULT_TOKEN = b"NUCODE_M7_I2C_RESULT:6B:0F:6A:RS\r\n"
ERROR_PREFIX = b"NUCODE_M7_I2C_ERROR:"
RESULT_PATTERN = re.compile(
    rb"NUCODE_M7_I2C_RESULT:([0-9A-F]{2}):([0-9A-F]{2}):([0-9A-F]{2}):(RS)"
)


@dataclass(frozen=True)
class ImuIdentityResult:
    """! @brief 고정 WHO_AM_I repeated-start 응답을 구조화합니다. """

    address: int
    register: int
    value: int
    repeated_start: bool


def parse_arguments() -> argparse.Namespace:
    """! @brief 고정 IMU 시험에 필요한 image, probe와 UART 인자만 해석합니다. """

    parser = argparse.ArgumentParser(
        description=(
            "NU54DK M7 image를 기록하고 고정 주소 0x6B의 WHO_AM_I(0x0F)를 "
            "repeated-start로 읽어 0x6A인지 검증합니다."
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
        help=f"UART baud rate(고정 기준값: {DEFAULT_BAUD_RATE})",
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
        "--result-timeout",
        type=float,
        default=10.0,
        help="고정 WHO_AM_I 응답 제한 시간(초)",
    )
    parser.add_argument(
        "--discover-only",
        action="store_true",
        help="MSD와 UART만 탐색하고 flash/I2C 요청 없이 종료",
    )
    return parser.parse_args()


def parse_result_line(line: bytes) -> ImuIdentityResult:
    """! @brief 한 protocol line이 승인된 0x6B repeated-start 결과인지 엄격히 검증합니다. """

    normalized = line.rstrip(b"\r\n")
    match = RESULT_PATTERN.fullmatch(normalized)
    if match is None:
        raise ValueError(f"M7 I2C result 형식이 올바르지 않습니다: {line!r}")

    address = int(match.group(1), 16)
    register = int(match.group(2), 16)
    value = int(match.group(3), 16)
    repeated_start = match.group(4) == b"RS"

    if address != IMU_I2C_ADDRESS:
        raise ValueError(f"승인되지 않은 I2C 주소입니다: 0x{address:02X}")
    if register != WHO_AM_I_REGISTER:
        raise ValueError(f"승인되지 않은 IMU register입니다: 0x{register:02X}")
    if value != WHO_AM_I_EXPECTED:
        raise ValueError(
            "LSM6DS3TR-C WHO_AM_I 불일치: "
            f"기대=0x{WHO_AM_I_EXPECTED:02X}, 실제=0x{value:02X}"
        )
    if not repeated_start:
        raise ValueError("WHO_AM_I 응답에 repeated-start 증거가 없습니다.")

    return ImuIdentityResult(address, register, value, repeated_start)


def flash_image(
    volume: DaplinkVolume, image: Path, timeout_seconds: float
) -> tuple[str, str]:
    """! @brief M7 Intel HEX를 DAPLink MSD에 기록하고 성공 sequence를 반환합니다. """

    if timeout_seconds <= 0:
        raise ValueError("--flash-timeout은 0보다 커야 합니다.")

    previous_sequence = detail_value(volume.details, "Flash Sequence")
    destination = volume.root / "NUCODE_M7.HEX"
    shutil.copyfile(image, destination)
    result_details = wait_for_flash_result(
        volume.root, previous_sequence, timeout_seconds
    )
    sequence = detail_value(result_details, "Flash Sequence") or "unknown"
    byte_count = detail_value(result_details, "Last Flash Bytes") or "unknown"
    return sequence, byte_count


def read_protocol_result(
    serial_port: Any, timeout_seconds: float, initial_data: bytes = b""
) -> ImuIdentityResult:
    """! @brief UART stream에서 첫 M7 result/error line을 찾아 고정 계약으로 판정합니다. """

    if timeout_seconds <= 0:
        raise ValueError("--result-timeout은 0보다 커야 합니다.")

    deadline = time.monotonic() + timeout_seconds
    observed = bytearray(initial_data)
    consumed = 0

    while time.monotonic() < deadline:
        while True:
            newline = observed.find(b"\n", consumed)
            if newline < 0:
                break
            line = bytes(observed[consumed : newline + 1])
            consumed = newline + 1
            stripped = line.rstrip(b"\r\n")
            if stripped.startswith(RESULT_PREFIX):
                return parse_result_line(line)
            if stripped.startswith(ERROR_PREFIX):
                raise RuntimeError(f"target M7 I2C 오류: {stripped!r}")

        waiting = serial_port.in_waiting
        chunk = serial_port.read(waiting if waiting > 0 else 1)
        if chunk:
            observed.extend(chunk)
            if len(observed) > 65536:
                retained = observed[consumed:]
                observed = bytearray(retained[-4096:])
                consumed = 0

    raise TimeoutError(
        "UART에서 M7 I2C result를 찾지 못했습니다. "
        f"observed_tail={bytes(observed[-256:])!r}"
    )


def verify_i2c_whoami(
    serial_module: Any,
    port_name: str,
    baud_rate: int,
    flash_callback: Any,
    ready_timeout: float,
    result_timeout: float,
) -> tuple[str, str, ImuIdentityResult]:
    """! @brief flash 뒤 고정 0x6B/0x0F repeated-start protocol 한 가지만 실행합니다. """

    if baud_rate != DEFAULT_BAUD_RATE:
        raise ValueError(
            f"M7 기준선은 {DEFAULT_BAUD_RATE} baud만 허용합니다: 요청={baud_rate}"
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
            serial_port, READY_TOKEN, ready_timeout
        )

        written = serial_port.write(REQUEST_TOKEN)
        serial_port.flush()
        if written != len(REQUEST_TOKEN):
            raise RuntimeError(
                "고정 M7 I2C 요청 일부만 전송했습니다: "
                f"기대={len(REQUEST_TOKEN)}, 실제={written}"
            )

        result = read_protocol_result(
            serial_port, result_timeout, initial_data=remainder
        )
        return sequence, byte_count, result


def main() -> int:
    """! @brief 장치 탐색 또는 전체 M7 0x6B WHO_AM_I HIL을 실행합니다. """

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

    if arguments.ready_timeout <= 0:
        raise ValueError("--ready-timeout은 0보다 커야 합니다.")
    if arguments.result_timeout <= 0:
        raise ValueError("--result-timeout은 0보다 커야 합니다.")

    image = validate_hex_image(arguments.hex_path)
    sequence, byte_count, result = verify_i2c_whoami(
        serial_module=serial_module,
        port_name=port_name,
        baud_rate=arguments.baud,
        flash_callback=lambda: flash_image(
            volume, image, arguments.flash_timeout
        ),
        ready_timeout=arguments.ready_timeout,
        result_timeout=arguments.result_timeout,
    )
    print(
        "M7 I2C IMU HIL PASS: "
        f"uid={unique_id}, sequence={sequence}, bytes={byte_count}, port={port_name}, "
        f"address=0x{result.address:02X}, register=0x{result.register:02X}, "
        f"value=0x{result.value:02X}, repeated_start={result.repeated_start}"
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print(f"M7 I2C IMU HIL FAIL: {error}", file=sys.stderr)
        sys.exit(1)
