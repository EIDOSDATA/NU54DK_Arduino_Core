"""External UART/SPI/TWI preparation. Never opens a probe or implicitly flashes."""
from __future__ import annotations
import hashlib
import itertools
import json
import secrets
import struct
import sys
import time
from pathlib import Path

from v04_protocol import ProtocolError
from v04_uart import payload

CATALOG = Path(__file__).with_name("v04_fixtures.json")
CONSENT = 0x53414645


def fixture_contract(fixture_id):
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    matching = [entry for entry in catalog["fixtures"] if entry["id"] == fixture_id]
    if len(matching) != 1:
        raise ProtocolError("unknown or duplicate fixture")
    return catalog, matching[0]


def confirmation_template(images, uids, fixture_id):
    """현재 image/보드에 묶인 T10 확인서 초안을 만듭니다.

    안전 조건과 사람 확인 필드는 의도적으로 미확인 상태로 둡니다. 따라서 출력된 초안은
    사용자가 실제 결선을 확인해 값을 채우기 전에는 실행 승인이 되지 않습니다.
    """
    catalog, _fixture = fixture_contract(fixture_id)
    if len(images) != 2 or len(uids) != 2 or uids[0].lower() == uids[1].lower():
        raise ProtocolError("two distinct exact boards required")
    return {
        "fixture_id": fixture_id,
        "fixture_revision": catalog["revision"],
        "catalog_sha256": hashlib.sha256(CATALOG.read_bytes()).hexdigest(),
        "core_revision": images[0]["core_revision"],
        "board_revision": catalog["board_revision"],
        "uid_sha256": [hashlib.sha256(uid.lower().encode()).hexdigest() for uid in uids],
        "hex_sha256": [image["sha256"] for image in images],
        "dap_uart_disconnected_both": False,
        "swd_connected_both": False,
        "power_rails_not_joined": False,
        "equal_io_voltage_confirmed": False,
        "common_ground_confirmed": False,
        "links_match_catalog": False,
        "pullups_match_catalog": False,
        "extra_outputs_disconnected": False,
        "confirmed_at_unix": 0,
        "confirmed_by": "",
    }


def validate_confirmation(confirmation, images, uids, fixture_id, now=None):
    """A named, current human confirmation is necessary, not proof of wiring."""
    catalog, fixture = fixture_contract(fixture_id)
    now = time.time() if now is None else now
    if len(images) != 2 or len(uids) != 2 or uids[0].lower() == uids[1].lower():
        raise ProtocolError("two distinct exact boards required")
    expected = {
        "fixture_id": fixture_id, "fixture_revision": catalog["revision"],
        "catalog_sha256": hashlib.sha256(CATALOG.read_bytes()).hexdigest(),
        "core_revision": images[0]["core_revision"], "board_revision": catalog["board_revision"],
        "uid_sha256": [hashlib.sha256(uid.lower().encode()).hexdigest() for uid in uids],
        "hex_sha256": [image["sha256"] for image in images],
        "dap_uart_disconnected_both": True, "swd_connected_both": True,
        "power_rails_not_joined": True, "equal_io_voltage_confirmed": True,
        "common_ground_confirmed": True, "links_match_catalog": True,
        "pullups_match_catalog": True,
        "extra_outputs_disconnected": True,
    }
    if any(image["role"] != role or image["core_revision"] != expected["core_revision"] or
           image["board_revision"] != expected["board_revision"]
           for role, image in enumerate(images, 1)):
        raise ProtocolError("role/source/board mismatch")
    if any(type(confirmation.get(key)) is not type(value) or confirmation.get(key) != value
           for key, value in expected.items()):
        raise ProtocolError("missing, false, stale or foreign fixture confirmation")
    timestamp = confirmation.get("confirmed_at_unix")
    if type(timestamp) not in (int, float) or not 0 <= now - timestamp <= 1800:
        raise ProtocolError("fixture confirmation expired or dated in the future")
    if not isinstance(confirmation.get("confirmed_by"), str) or not confirmation["confirmed_by"].strip():
        raise ProtocolError("human confirmation identity missing")
    return fixture


def vectors(family):
    if family == "uarte":
        for rate, parity, flow, size, buffers in itertools.product(
                (9600, 115200, 1000000), range(2), range(2),
                (1, 2, 31, 32, 255, 512, 1024), (1, 2)):
            if buffers == 1 or size >= 32:
                yield rate, parity, flow, size, 1, buffers
        # HWFC receiver가 RX를 열기 전에는 sender가 CTS에서 멈추고, 100ms 뒤 재개해야 합니다.
        yield 115200, 0, 1, 256, 2, 1
        # Sender 8N1, receiver 8E1 불일치에서 parity/framing 오류를 검출하고 정지합니다.
        yield 115200, 0, 0, 32, 3, 1
        # 시험 generator가 TX 선을 1ms LOW로 유지해 break/framing 오류를 만듭니다.
        yield 115200, 0, 0, 32, 4, 1
        return
    if family == "spi":
        yield from itertools.product((2000000, 4000000, 8000000), range(4), range(2),
                                     (1, 2, 31, 32, 255, 256, 1024), (1, 2, 3), (0, 1, 2))
        # 진행 중 1024-byte 전송을 즉시 취소하고 bounded STOP으로 회수합니다.
        yield 2000000, 0, 0, 1024, 3, 3
        return
    if family == "twi":
        for values in itertools.product((100000, 400000, 1000000), (0,), (0,),
                                        (1, 2, 31, 32, 255, 256), (1, 2, 3),
                                        (0x42, 0x43), (0, 1, 2)):
            rate, mode, lsb, size, direction, address, style = values
            yield rate, mode, lsb, size, direction, address | (style << 8)
        # 등록되지 않은 0x44 주소로 address NACK와 bounded STOP을 검사합니다.
        yield 100000, 0, 0, 32, 1, 0x44 | (3 << 8)
        # 100kHz 256-byte duplex를 시작한 직후 취소하고 buffer를 회수합니다.
        yield 100000, 0, 0, 256, 3, 0x42 | (4 << 8)
        # Peer가 SDA를 LOW로 고정한 실패와 해제 후 recoverBus 성공을 검사합니다.
        yield 100000, 0, 0, 32, 1, 0x42 | (5 << 8)
        # TWIS buffer를 지연해 실제 clock stretching 뒤 정상 완료를 검사합니다.
        yield 100000, 0, 0, 32, 3, 0x42 | (6 << 8)
        return
    raise ProtocolError("unknown fixture family")


def expected_lengths(role, controller_role, size, direction, family, buffers=1,
                     segments=1):
    controller = role == controller_role
    if family == "uarte":
        return (size * buffers, 0) if controller else (0, size * buffers)
    tx = size if direction & (1 if controller else 2) else 0
    rx = size if direction & (2 if controller else 1) else 0
    return tx * segments, (size if family == "spi" else rx) * segments


def wait_status(device, expected, timeout=2):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        words = device.command(22)
        if len(words) != 8 or words[4] or not words[5]:
            raise ProtocolError(f"fixture error/guard failure role={device.image['role']}: {words}")
        if expected(words):
            return words
        time.sleep(.005)
    raise ProtocolError(f"fixture DMA timeout role={device.image['role']}: {words}")


def wait_expected_error(device, timeout=2):
    """오류 주입 case에서 guard를 유지한 실제 firmware error만 기다립니다."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        words = device.command(22)
        if len(words) != 8 or not words[5]:
            raise ProtocolError(f"fixture error case guard/status failure: {words}")
        if words[4]:
            return words
        time.sleep(.005)
    raise ProtocolError(f"expected UART parity/framing error missing: {words}")


def read_received(device, size):
    data = bytearray()
    for offset in range(0, size, 64):
        count = min(64, size - offset)
        words = device.command(24, (offset, count))
        if len(words) != (count + 3) // 4:
            raise ProtocolError("fixture RX snapshot length mismatch")
        data.extend(struct.pack(f"<{len(words)}I", *words)[:count])
    return bytes(data)


def exchange(devices, fixture, controller_role, instances, vector, append, label=""):
    """Devices must already be exact-identity, fresh-session and fixture-armed."""
    rate, mode, lsb, size, direction, address = vector
    seed = secrets.randbits(32)
    controller, peripheral = devices[controller_role - 1], devices[2 - controller_role]
    # Set clock polarity and inactive CS before the peripheral acquires buffers.
    # Preparing the controller does not start a transaction.
    for device in (controller, peripheral):
        role = device.image["role"]
        device.command(18)
        reply = device.command(20, (instances[role - 1], rate, mode, lsb, size, seed, direction, address))
        if reply != [0]:
            raise ProtocolError(f"fixture prepare failed: {reply}")
    deferred_uart = fixture["family"] == "uarte" and direction == 2
    twi_style = address >> 8 if fixture["family"] == "twi" else 0
    deferred_twis = fixture["family"] == "twi" and twi_style == 6
    recovery_twi = fixture["family"] == "twi" and twi_style == 5
    if not deferred_uart and not deferred_twis:
        wait_status(peripheral, lambda words: words[1] == 1)
    start_result = controller.command(21)
    if recovery_twi:
        if len(start_result) != 1 or start_result[0] == 0:
            raise ProtocolError(f"TWI stuck-SDA recovery did not fail: {start_result}")
        if peripheral.command(25) != [0]:
            raise ProtocolError("TWI stuck-SDA release failed")
        released_result = controller.command(26)
        if released_result != [0]:
            raise ProtocolError(f"TWI recovery after SDA release failed: {released_result}")
        for device in devices:
            if device.command(23) != [0, 1]:
                raise ProtocolError("TWI recovery fixture STOP/guard mismatch")
        append(f"V04-TWI-BUS-RECOVERY/{fixture['id']}/{controller_role}/{instances}/{vector}{label}",
               {"seed": seed, "stuck_result": start_result[0],
                "released_result": released_result[0],
                "scope": "stuck-sda-failure-release-recover-and-bounded-stop"})
        for device in devices:
            device.command(18)
        exchange(devices, fixture, controller_role, instances,
                 (100000, 0, 0, 32, 3, 0x42), append,
                 label="/recovery-after-stuck-sda")
        return
    if start_result != [0]:
        raise ProtocolError("fixture controller start failed")
    if deferred_uart:
        time.sleep(.1)
        stalled = controller.command(22)
        if len(stalled) != 8 or stalled[2:] != [0, 0, 0, 1, 0, 0]:
            raise ProtocolError(f"UART CTS did not hold TX for 100ms: {stalled}")
        if peripheral.command(19) != [0]:
            raise ProtocolError("UART deferred receiver start failed")
    if deferred_twis:
        time.sleep(.005)
        stalled = controller.command(22)
        if len(stalled) != 8 or stalled[2] or stalled[3] or stalled[4]:
            raise ProtocolError(f"TWIS did not stretch before buffers arrived: {stalled}")
        if peripheral.command(25) != [0]:
            raise ProtocolError("TWIS delayed buffer queue failed")
        wait_status(peripheral, lambda words: words[1] == 1)
    if fixture["family"] == "spi" and address == 2:
        wait_status(controller, lambda words: tuple(words[2:4]) == (1, 1))
        wait_status(peripheral,
                    lambda words: words[1] == 2 and tuple(words[2:4]) == (1, 1))
        if controller.command(28) != [0]:
            raise ProtocolError("SPIS next buffer handover failed")
    expected_uart_error = fixture["family"] == "uarte" and direction in (3, 4)
    expected_twi_nack = fixture["family"] == "twi" and address >> 8 == 3
    expected_twi_cancel = fixture["family"] == "twi" and address >> 8 == 4
    expected_spi_cancel = fixture["family"] == "spi" and address == 3
    expected_spi_concurrent = fixture["family"] == "spi" and address == 4
    if expected_uart_error or expected_twi_nack or expected_twi_cancel or expected_spi_cancel:
        error_device = peripheral if expected_uart_error else controller
        error_status = wait_expected_error(error_device)
        controller_status = (wait_status(controller, lambda words: words[2] == 1)
                             if expected_uart_error else controller.command(22))
        for device in devices:
            if device.command(23) != [0, 1]:
                raise ProtocolError("expected-error fixture STOP/guard mismatch")
        family = fixture["family"].upper()
        append(f"V04-{family}-EXPECTED-ERROR/{fixture['id']}/{controller_role}/{instances}/{vector}{label}",
               {"seed": seed, "error_status": error_status,
                "controller_status": controller_status,
                "scope": "parity-break-nack-or-cancel-and-bounded-stop"})
        for device in devices:
            device.command(18)
        if fixture["family"] == "uarte":
            recovery_vector = (115200, 0, 0, 32, 1, 1)
        elif fixture["family"] == "spi":
            recovery_vector = (2000000, 0, 0, 32, 3, 0)
        else:
            recovery_vector = (100000, 0, 0, 32, 3, 0x42)
        exchange(devices, fixture, controller_role, instances, recovery_vector, append,
                 label="/recovery-after-error")
        return
    results = []
    concurrent_pmic = None
    if expected_spi_concurrent:
        concurrent_pmic = controller.command(27)
        if len(concurrent_pmic) != 3 or concurrent_pmic[:2] != [0, 0x41]:
            raise ProtocolError(f"SPIM00/TWIM22 concurrent PMIC read failed: {concurrent_pmic}")
    for device in devices:
        role = device.image["role"]
        buffers = address if fixture["family"] == "uarte" else 1
        style = address if fixture["family"] == "spi" else address >> 8
        segments = 2 if fixture["family"] != "uarte" and style == 2 else 1
        tx, rx = expected_lengths(role, controller_role, size, direction,
                                  fixture["family"], buffers, segments)
        if fixture["family"] == "uarte":
            expected_counts = (1, 0) if role == controller_role else (0, (1 << buffers) - 1)
        elif fixture["family"] == "spi" or role == controller_role:
            expected_counts = (segments, segments)
        else:
            expected_counts = (segments * int(tx > 0), segments * int(rx > 0))
        words = wait_status(device, lambda words: tuple(words[2:4]) == expected_counts,
                            timeout=5 if fixture["family"] == "uarte" else 2)
        if words[6:] != [tx, rx]:
            raise ProtocolError(f"fixture DMA amount mismatch: {words}; expected={tx, rx}")
        incoming = read_received(device, rx) if rx else b""
        peer_role = 3 - role
        peer_tx, _ = expected_lengths(peer_role, controller_role, size, direction,
                                      fixture["family"], buffers, segments)
        expected = payload(seed ^ (0 if peer_role == 1 else 0x5a), rx) if peer_tx and rx else bytes([0x96]) * rx
        if incoming != expected:
            raise ProtocolError(f"fixture payload mismatch role={role}; actual={incoming.hex()}; expected={expected.hex()}")
        results.append({"role": role, "status_words": words, "rx_sha256": hashlib.sha256(incoming).hexdigest()})
    for device in devices:
        if device.command(23) != [0, 1]:
            raise ProtocolError("fixture STOP/guard mismatch")
    append(f"V04-{fixture['family'].upper()}-DATA/{fixture['id']}/{controller_role}/{instances}/{vector}{label}",
           {"seed": seed, "results": results,
            "concurrent_pmic": concurrent_pmic,
            "scope": "asynchronous-single-or-double-buffer"})


def run_confirmed(devices, images, uids, confirmation, fixture_id, append):
    """T10 confirmation and the caller's exclusive board locks are required."""
    fixture = validate_confirmation(confirmation, images, uids, fixture_id)
    if len(devices) != 2 or any(device.image != image or device.poisoned
                               for device, image in zip(devices, images)):
        raise ProtocolError("live device identities differ from confirmed images")
    for controller_role in (1, 2):
        try:
            for device in devices:
                if device.command(16, (fixture_id, 1, CONSENT, controller_role)) != [fixture_id, 10000]:
                    raise ProtocolError("fixture arm failed")
            for instances in itertools.product(*fixture["instances"]):
                for vector in vectors(fixture["family"]):
                    exchange(devices, fixture, controller_role, instances, vector, append)
            if fixture_id == 201 and controller_role == 1:
                exchange(devices, fixture, controller_role, (0, 20),
                         (2000000, 0, 0, 1024, 3, 4), append,
                         label="/spim00-twim22-concurrent")
        finally:
            original_error = sys.exception()
            cleanup = []
            for device in devices:
                if device.poisoned:
                    cleanup.append({"role": device.image["role"], "status": "STOP unproven; control poisoned"})
                    continue
                try:
                    result = device.command(17)
                    cleanup.append({"role": device.image["role"], "result": result})
                except BaseException as error:
                    cleanup.append({"role": device.image["role"], "error": str(error)})
            # Cleanup records are not functional PASS records.
            append("V04-FIXTURE-CLEANUP", {"status": "cleanup", "cleanup_only": True, "results": cleanup})
            if any(item.get("result") != [0] for item in cleanup):
                if original_error is not None:
                    original_error.add_note(f"fixture disarm not proven: {cleanup}")
                else:
                    raise ProtocolError(f"fixture disarm not proven: {cleanup}")
