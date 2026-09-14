#!/usr/bin/env python3
"""! @brief Windows WinRT central과 NU54DK GATT server 상호운용을 검증합니다. """

from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict
from datetime import datetime, timezone
from importlib.metadata import version as package_version
import json
from pathlib import Path
import platform
import sys
import threading
import time
from typing import Any, Sequence


HIL_DIRECTORY = Path(__file__).resolve().parent
if str(HIL_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(HIL_DIRECTORY))

from ble_pair_hil_common import (  # noqa: E402
    BOARD_ROOT,
    DEFAULT_BAUD_RATE,
    REPOSITORY,
    BlePairHilFailure,
    PairExecutionFailure,
    RoleExecution,
    build_nonce,
    collect_until_final,
    discover_endpoint,
    file_sha256,
    flash_image,
    git_revision,
    image_record,
    transcript_record,
    validate_board_revision,
    validate_build_record,
    validate_hex_image,
    validate_image_unchanged,
    validate_source_clean,
    wait_peripheral_advertising,
    wait_ready,
    write_start_command,
)
from m20_ble_gatt import parse_peripheral_transcript  # noqa: E402
from m29_ble_windows_gatt_protocol import (  # noqa: E402
    CHARACTERISTIC_UUID,
    PEER_NAME,
    SERVICE_UUID,
    WindowsGattObservation,
    validate_windows_gatt_observation,
)
from m6_serial_echo import import_pyserial  # noqa: E402


APPLICATION_SOURCE_ROOT = REPOSITORY / "tests" / "zephyr" / "m20_ble_gatt_hil"
PROTOCOL_SOURCE = Path(__file__).with_name("m29_ble_windows_gatt_protocol.py")
M20_RUNNER_SOURCE = Path(__file__).with_name("m20_ble_gatt.py")
EVIDENCE_SCHEMA = 1


def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    """! @brief target identity·image·timeout·증거 인자를 선언합니다. """

    parser = argparse.ArgumentParser(
        description="Windows WinRT와 NU54DK M20 GATT peripheral 상호운용을 검증합니다."
    )
    parser.add_argument("--peripheral-hex")
    parser.add_argument("--board-id", required=True)
    parser.add_argument("--volume")
    parser.add_argument("--port", default="auto")
    parser.add_argument("--baud", type=int, default=DEFAULT_BAUD_RATE)
    parser.add_argument("--flash-timeout", type=float, default=45.0)
    parser.add_argument("--result-timeout", type=float, default=180.0)
    parser.add_argument("--scan-timeout", type=float, default=30.0)
    parser.add_argument("--expected-core-revision")
    parser.add_argument("--evidence")
    parser.add_argument("--overwrite-evidence", action="store_true")
    parser.add_argument("--discover-only", action="store_true")
    return parser.parse_args(arguments)


def prepare_output(path_argument: str | None, overwrite: bool) -> tuple[Path, Path]:
    """! @brief 신규 evidence와 raw target transcript 경로를 준비합니다. """

    if not path_argument:
        raise BlePairHilFailure("실제 실행에는 --evidence가 필요합니다.")
    evidence = Path(path_argument).resolve()
    if evidence.suffix.lower() != ".json":
        raise BlePairHilFailure("--evidence는 .json 확장자여야 합니다.")
    transcript = evidence.with_name(f"{evidence.stem}.peripheral.transcript.log")
    existing = [path for path in (evidence, transcript) if path.exists()]
    if existing and not overwrite:
        raise BlePairHilFailure(
            "기존 증적을 덮어쓰지 않습니다: " + ", ".join(str(path) for path in existing)
        )
    if any(not path.is_file() for path in existing):
        raise BlePairHilFailure("기존 증적 경로가 일반 파일이 아닙니다.")
    evidence.parent.mkdir(parents=True, exist_ok=True)
    return evidence, transcript


async def _scan_peer(scanner_type: Any, timeout_seconds: float) -> tuple[Any, Any]:
    """! @brief local name과 service UUID가 함께 맞는 광고 하나를 찾습니다. """

    observed: dict[str, Any] = {}

    def match(device: Any, advertisement: Any) -> bool:
        service_uuids = tuple(value.lower() for value in advertisement.service_uuids)
        if advertisement.local_name == PEER_NAME and SERVICE_UUID in service_uuids:
            observed["advertisement"] = advertisement
            return True
        return False

    device = await scanner_type.find_device_by_filter(match, timeout=timeout_seconds)
    if device is None or "advertisement" not in observed:
        raise BlePairHilFailure("Windows scan에서 고정 name/service UUID peer를 찾지 못했습니다.")
    return device, observed["advertisement"]


async def _receive_value(
    client: Any,
    characteristic: Any,
    expected: bytes,
    *,
    force_indicate: bool,
    timeout_seconds: float,
) -> bytes:
    """! @brief notify 또는 indicate 하나를 등록·수신·해제합니다. """

    values: asyncio.Queue[bytes] = asyncio.Queue()

    def callback(_: Any, data: bytearray) -> None:
        values.put_nowait(bytes(data))

    await client.start_notify(
        characteristic, callback, force_indicate=force_indicate
    )
    try:
        value = await asyncio.wait_for(values.get(), timeout=timeout_seconds)
    finally:
        await client.stop_notify(characteristic)
    if value != expected:
        raise BlePairHilFailure(
            f"Windows 수신 값 불일치: actual={value!r}, expected={expected!r}"
        )
    return value


def _get_characteristic(client: Any) -> tuple[Any, Any]:
    """! @brief exact service·characteristic를 찾고 중복·누락을 거부합니다. """

    service = client.services.get_service(SERVICE_UUID)
    if service is None:
        observed = sorted(str(item.uuid) for item in client.services)
        raise BlePairHilFailure(
            f"Windows GATT discovery에서 service가 누락되었습니다: {observed}"
        )
    characteristic = service.get_characteristic(CHARACTERISTIC_UUID)
    if characteristic is None:
        raise BlePairHilFailure("Windows GATT discovery에서 characteristic이 누락되었습니다.")
    return service, characteristic


async def execute_windows_gatt(
    bleak_scanner: Any,
    bleak_client: Any,
    nonce: str,
    scan_timeout: float,
    result_timeout: float,
) -> WindowsGattObservation:
    """! @brief WinRT에서 두 연결의 고정 GATT operation을 수행합니다. """

    notifications: list[bytes] = []
    indications: list[bytes] = []
    first_advertisement = None
    first_device = None
    first_service = None
    first_characteristic = None
    read_value = b""
    connections = 0
    disconnects = 0

    async with asyncio.timeout(result_timeout):
        for round_number in (1, 2):
            device, advertisement = await _scan_peer(bleak_scanner, scan_timeout)
            if round_number == 1:
                first_device = device
                first_advertisement = advertisement
            async with bleak_client(device, timeout=scan_timeout) as client:
                if not client.is_connected:
                    raise BlePairHilFailure("Windows GATT 연결이 성립하지 않았습니다.")
                connections += 1
                service, characteristic = _get_characteristic(client)
                if round_number == 1:
                    first_service = service
                    first_characteristic = characteristic
                    read_value = bytes(
                        await client.read_gatt_char(characteristic, use_cached=False)
                    )
                    await client.write_gatt_char(characteristic, b"WR", response=True)
                    await client.write_gatt_char(characteristic, b"WC", response=False)
                expected_notification = b"NTF1" if round_number == 1 else b"NTF2"
                notifications.append(
                    await _receive_value(
                        client,
                        characteristic,
                        expected_notification,
                        force_indicate=False,
                        timeout_seconds=scan_timeout,
                    )
                )
                if round_number == 1:
                    indications.append(
                        await _receive_value(
                            client,
                            characteristic,
                            b"IND1",
                            force_indicate=True,
                            timeout_seconds=scan_timeout,
                        )
                    )
            disconnects += 1
            if round_number == 1:
                await asyncio.sleep(1.0)

    if any(
        value is None
        for value in (
            first_device,
            first_advertisement,
            first_service,
            first_characteristic,
        )
    ):
        raise BlePairHilFailure("첫 Windows GATT 관측값이 누락되었습니다.")
    return WindowsGattObservation(
        backend="WinRT",
        platform=platform.system(),
        peer_name=first_advertisement.local_name,
        peer_address=str(first_device.address),
        advertised_service_uuids=tuple(first_advertisement.service_uuids),
        discovered_service_uuid=str(first_service.uuid),
        characteristic_uuid=str(first_characteristic.uuid),
        characteristic_properties=tuple(first_characteristic.properties),
        read_value=read_value,
        write_response_value=b"WR",
        write_command_value=b"WC",
        notification_values=tuple(notifications),
        indication_values=tuple(indications),
        connection_rounds=connections,
        disconnect_rounds=disconnects,
    )


def execute_target(
    serial_module: Any,
    endpoint: Any,
    image: Path,
    nonce: str,
    baud_rate: int,
    flash_timeout: float,
    result_timeout: float,
    scan_timeout: float,
    bleak_scanner: Any,
    bleak_client: Any,
) -> tuple[RoleExecution, WindowsGattObservation]:
    """! @brief target UART·flash와 Windows async GATT session을 한 경계로 실행합니다. """

    if baud_rate != DEFAULT_BAUD_RATE:
        raise BlePairHilFailure(f"기준선은 {DEFAULT_BAUD_RATE} baud만 허용합니다.")
    if not 30.0 <= result_timeout <= 600.0:
        raise BlePairHilFailure("--result-timeout은 30..600초여야 합니다.")
    capture = bytearray()
    pending = bytearray()
    try:
        with serial_module.Serial(
            port=endpoint.port_name,
            baudrate=baud_rate,
            bytesize=serial_module.EIGHTBITS,
            parity=serial_module.PARITY_NONE,
            stopbits=serial_module.STOPBITS_ONE,
            timeout=0.1,
            write_timeout=2.0,
        ) as serial_port:
            serial_port.reset_input_buffer()
            flash_sequence, flash_bytes = flash_image(
                "M20", "peripheral", endpoint.volume, image, flash_timeout
            )
            deadline = time.monotonic() + result_timeout
            wait_ready(
                serial_port, "M20", "peripheral", pending, capture, deadline
            )
            write_start_command(serial_port, "M20", nonce)
            wait_peripheral_advertising(
                serial_port, "M20", nonce, pending, capture, deadline
            )
            observation = asyncio.run(
                execute_windows_gatt(
                    bleak_scanner,
                    bleak_client,
                    nonce,
                    scan_timeout,
                    result_timeout,
                )
            )
            collect_until_final(
                serial_port,
                "M20",
                "peripheral",
                nonce,
                pending,
                capture,
                deadline,
                threading.Event(),
            )
    except Exception as error:
        raise PairExecutionFailure(str(error), bytes(capture), b"") from error
    return RoleExecution(flash_sequence, flash_bytes, bytes(capture)), observation


def json_observation(observation: WindowsGattObservation) -> dict[str, Any]:
    """! @brief bytes field를 lowercase hex로 바꾼 JSON 안전 record를 만듭니다. """

    value = asdict(observation)
    for key in ("read_value", "write_response_value", "write_command_value"):
        value[key] = value[key].hex()
    for key in ("notification_values", "indication_values"):
        value[key] = [item.hex() for item in value[key]]
    return value


def main(arguments: Sequence[str] | None = None) -> int:
    """! @brief Windows cross-vendor GATT gate를 실행하고 증거를 기록합니다. """

    args = parse_arguments(arguments)
    serial_module, list_ports = import_pyserial()
    endpoint = discover_endpoint(args.board_id, args.volume, args.port, list_ports)
    print(
        "M29 Windows GATT discovery SUCCESS: "
        f"peripheral={endpoint.board_id}/{endpoint.port_name}"
    )
    if args.discover_only:
        return 0

    try:
        from bleak import BleakClient, BleakScanner
    except ImportError as error:
        raise BlePairHilFailure("Windows 상호운용 실행에는 bleak가 필요합니다.") from error

    evidence_path, transcript_path = prepare_output(
        args.evidence, args.overwrite_evidence
    )
    image = validate_hex_image(args.peripheral_hex)
    core_revision = git_revision(REPOSITORY, args.expected_core_revision)
    board_revision = git_revision(BOARD_ROOT)
    validate_board_revision(board_revision)
    validate_source_clean(
        "M29-WINDOWS-GATT",
        APPLICATION_SOURCE_ROOT,
        Path(__file__).resolve(),
        (PROTOCOL_SOURCE, M20_RUNNER_SOURCE),
    )
    build_record = validate_build_record(
        image, core_revision, board_revision, APPLICATION_SOURCE_ROOT
    )
    image_size = image.stat().st_size
    image_sha256 = file_sha256(image)
    nonce = build_nonce()
    execution = None
    try:
        execution, observation = execute_target(
            serial_module,
            endpoint,
            image,
            nonce,
            args.baud,
            args.flash_timeout,
            args.result_timeout,
            args.scan_timeout,
            BleakScanner,
            BleakClient,
        )
        validate_image_unchanged(image, image_size, image_sha256)
        target_result = parse_peripheral_transcript(execution.transcript, nonce)
        validate_windows_gatt_observation(observation, nonce)
        transcript_path.write_bytes(execution.transcript)
        evidence = {
            "schema_version": EVIDENCE_SCHEMA,
            "gate": "m29-cross-vendor-windows-gatt-hil",
            "status": "passed",
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "core_revision": core_revision,
            "board_revision": board_revision,
            "board_target": "nrf54l15dk/nrf54l15/cpuapp/nu54dk",
            "nonce": nonce,
            "board": {
                "daplink_uid": endpoint.board_id,
                "msd_root": str(endpoint.volume.root),
                "uart_port": endpoint.port_name,
            },
            "image": image_record(
                image, image_size, image_sha256, execution, build_record
            ),
            "transcript": transcript_record(transcript_path, execution.transcript),
            "target_result": asdict(target_result),
            "windows_observation": json_observation(observation),
            "host": {
                "platform": platform.platform(),
                "bleak_version": package_version("bleak"),
                "backend": "WinRT",
            },
            "coverage": {
                "advertised_service_uuid": True,
                "service_discovery": True,
                "characteristic_discovery": True,
                "nonce_read_bits": 128,
                "write_with_response": True,
                "write_without_response": True,
                "notification_rounds": 2,
                "indication_rounds": 1,
                "disconnect_reconnect_rounds": 2,
            },
            "safety": {
                "external_wiring_required": False,
                "mass_erase_requested": False,
                "pmic_write_executed": False,
            },
        }
        evidence_path.write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except Exception as error:
        if execution is not None:
            transcript_path.write_bytes(execution.transcript)
        elif isinstance(error, PairExecutionFailure):
            transcript_path.write_bytes(error.peripheral_transcript)
        raise
    print(
        "M29 Windows cross-vendor GATT HIL PASS: "
        f"nonce={nonce}, evidence={evidence_path}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (BlePairHilFailure, OSError, TimeoutError) as error:
        print(f"M29 Windows cross-vendor GATT HIL FAIL: {error}", file=sys.stderr)
        raise SystemExit(1) from error
