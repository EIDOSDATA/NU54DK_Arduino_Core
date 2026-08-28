#!/usr/bin/env python3
"""! @brief NU54DK 전용 M7 실제 SPI loopback, ADC와 PWM HIL을 DAPLink/UART로 자동 검증합니다. """

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
    validate_hex_image,
    wait_for_flash_result,
)


READY_TOKEN = b"NUCODE_M7_PERIPHERAL_HIL_READY"
FINAL_PASS_TOKEN = b"NUCODE_M7_PERIPHERAL_HIL_PASS"
FINAL_FAIL_TOKEN = b"NUCODE_M7_PERIPHERAL_HIL_FAIL"
DRIVER_FAIL_MARKER = b"_DRIVER:FAIL:"
SPI_LOOPBACK_FAIL_TOKEN = b"NUCODE_M7_SPI_LOOPBACK:FAIL:"
PWM_PASS_TOKEN = b"NUCODE_M7_PWM_DRIVER:PASS:duty=0,128,255"
SPI_PATTERN = re.compile(
    rb"^NUCODE_M7_SPI_LOOPBACK:PASS:frequency=4000000:bytes=([0-9]+):"
    rb"pattern=MUL37_ADD5A$",
    re.MULTILINE,
)
ADC_PATTERN = re.compile(
    rb"^NUCODE_M7_ADC_DRIVER:PASS:raw=([0-9]+)$",
    re.MULTILINE,
)


@dataclass(frozen=True)
class PeripheralHilResult:
    """! @brief 실제 driver HIL transcript에서 승인된 관찰값을 구조화합니다. """

    spi_byte_count: int
    adc_raw: int


def parse_arguments() -> argparse.Namespace:
    """! @brief 고정 주변장치 HIL에 필요한 image, probe와 UART 인자만 해석합니다. """

    parser = argparse.ArgumentParser(
        description=(
            "NU54DK M7 image를 DAPLink MSD로 기록하고 실제 SPI 4 MHz loopback, "
            "A0 raw read와 PWM 0/128/255 driver 호출 token을 검증합니다."
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
        "--result-timeout",
        type=float,
        default=30.0,
        help="주변장치 HIL 최종 token 제한 시간(초)",
    )
    parser.add_argument(
        "--discover-only",
        action="store_true",
        help="MSD와 UART만 탐색하고 flash/주변장치 시험 없이 종료",
    )
    return parser.parse_args()


def parse_transcript(transcript: bytes) -> PeripheralHilResult:
    """! @brief UART transcript가 제한된 driver 성공 계약을 모두 만족하는지 검증합니다. """

    normalized = transcript.replace(b"\r", b"")
    if FINAL_FAIL_TOKEN in normalized:
        raise RuntimeError("target이 M7 주변장치 driver HIL 실패를 보고했습니다.")
    if DRIVER_FAIL_MARKER in normalized:
        raise RuntimeError("target이 하나 이상의 M7 driver 실패를 보고했습니다.")
    if SPI_LOOPBACK_FAIL_TOKEN in normalized:
        raise RuntimeError("target이 M7 SPI 물리 loopback 불일치를 보고했습니다.")
    for required in (READY_TOKEN, PWM_PASS_TOKEN, FINAL_PASS_TOKEN):
        if required not in normalized:
            raise ValueError(f"필수 M7 HIL token이 없습니다: {required!r}")

    spi_match = SPI_PATTERN.search(normalized)
    if spi_match is None:
        raise ValueError("4 MHz SPI loopback 성공 token이 없습니다.")
    spi_byte_count = int(spi_match.group(1), 10)
    if spi_byte_count != 40:
        raise ValueError(f"SPI loopback byte 수가 다릅니다: {spi_byte_count}")

    adc_match = ADC_PATTERN.search(normalized)
    if adc_match is None:
        raise ValueError("A0 ADC driver 성공 token이 없습니다.")
    adc_raw = int(adc_match.group(1), 10)
    if not 0 <= adc_raw <= 4095:
        raise ValueError(f"A0 12-bit raw 범위를 벗어났습니다: {adc_raw}")

    return PeripheralHilResult(spi_byte_count=spi_byte_count, adc_raw=adc_raw)


def flash_image(
    volume: DaplinkVolume, image: Path, timeout_seconds: float
) -> tuple[str, str]:
    """! @brief M7 주변장치 HIL HEX를 DAPLink MSD에 기록하고 성공 결과를 반환합니다. """

    if timeout_seconds <= 0:
        raise ValueError("--flash-timeout은 0보다 커야 합니다.")

    previous_sequence = detail_value(volume.details, "Flash Sequence")
    destination = volume.root / "NUCODE_M7_PERIPHERAL.HEX"
    shutil.copyfile(image, destination)
    result_details = wait_for_flash_result(
        volume.root, previous_sequence, timeout_seconds
    )
    sequence = detail_value(result_details, "Flash Sequence") or "unknown"
    byte_count = detail_value(result_details, "Last Flash Bytes") or "unknown"
    return sequence, byte_count


def read_transcript(serial_port: Any, timeout_seconds: float) -> bytes:
    """! @brief UART에서 최종 PASS/FAIL token까지의 제한된 transcript를 수집합니다. """

    if timeout_seconds <= 0:
        raise ValueError("--result-timeout은 0보다 커야 합니다.")

    deadline = time.monotonic() + timeout_seconds
    observed = bytearray()
    while time.monotonic() < deadline:
        waiting = serial_port.in_waiting
        chunk = serial_port.read(waiting if waiting > 0 else 1)
        if chunk:
            observed.extend(chunk)
            if FINAL_FAIL_TOKEN in observed:
                raise RuntimeError(
                    "target이 M7 주변장치 HIL 실패를 보고했습니다: "
                    f"{bytes(observed[-1024:])!r}"
                )
            if FINAL_PASS_TOKEN in observed:
                return bytes(observed)
            if len(observed) > 65536:
                del observed[: len(observed) - 65536]

    raise TimeoutError(
        "UART에서 M7 주변장치 HIL 최종 token을 찾지 못했습니다. "
        f"observed_tail={bytes(observed[-1024:])!r}"
    )


def verify_peripheral_hil(
    serial_module: Any,
    port_name: str,
    baud_rate: int,
    flash_callback: Any,
    result_timeout: float,
) -> tuple[str, str, PeripheralHilResult]:
    """! @brief flash 뒤 실제 주변장치 driver 성공 token을 한 번 수집하고 판정합니다. """

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
        result = parse_transcript(read_transcript(serial_port, result_timeout))
        return sequence, byte_count, result


def main() -> int:
    """! @brief 장치 탐색 또는 전체 M7 주변장치 driver HIL을 실행합니다. """

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

    image = validate_hex_image(arguments.hex_path)
    sequence, byte_count, result = verify_peripheral_hil(
        serial_module=serial_module,
        port_name=port_name,
        baud_rate=arguments.baud,
        flash_callback=lambda: flash_image(
            volume, image, arguments.flash_timeout
        ),
        result_timeout=arguments.result_timeout,
    )
    print(
        "M7 peripheral HIL PASS: "
        f"uid={unique_id}, sequence={sequence}, bytes={byte_count}, port={port_name}, "
        f"spi_frequency=4000000, spi_loopback_bytes={result.spi_byte_count}, "
        f"adc_raw={result.adc_raw}, pwm_duty=0,128,255"
    )
    print(
        "범위: SPI MOSI/MISO 40-byte data 일치를 검증했으며 ADC 전압 정확도와 "
        "PWM 외부 파형은 검증하지 않았습니다."
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print(f"M7 peripheral driver HIL FAIL: {error}", file=sys.stderr)
        sys.exit(1)
