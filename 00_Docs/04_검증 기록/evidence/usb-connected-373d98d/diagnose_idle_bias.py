"""! @brief 비선택 P0 TX의 원래 입력 설정과 임시 pull-up의 영향을 비교합니다. """
from runtime import *
from contextlib import ExitStack
import serial
import time
from datetime import datetime, timezone
import m24_uarte_onboard as runner
from v04_protocol import ProbeLocks

# nrf54l15_global.h NRF_P0_S_BASE + nrf54l15_types.h PIN_CNF[0].
address = 0x5010A080
result = {'type': 'bounded-idle-bias-diagnostic-not-formal-suite', 'source': SOURCE, 'probe_id_sha256': HASHES[1], 'created_at_utc': datetime.now(timezone.utc).isoformat(), 'flash_executed': False, 'flow_control_executed': False, 'register': hex(address), 'observations': []}
with ProbeLocks([UIDS[1]]), ExitStack() as stack:
    session = stack.enter_context(ConnectHelper.session_with_chosen_probe(unique_id=UIDS[1], target_override='nrf54l', frequency=10000000, blocking=False, no_config=True, options={'auto_unlock': False, 'connect_mode': 'attach', 'resume_on_disconnect': False}))
    original = session.target.read32(address)
    result['original_pin_cnf'] = hex(original)
    assert original & 1 == 0, 'Non-selected P0 TX must remain an input'
    streams = {port: stack.enter_context(serial.Serial(port, 115200, timeout=0, write_timeout=2, rtscts=False)) for port in ('COM7', 'COM8')}
    payload = hashlib.sha256(b'connected-idle-bias-diagnostic').digest()
    try:
        for mode, value in [('original', original), ('temporary-input-pullup', (original & ~0xC) | 0xC)]:
            session.target.write32(address, value)
            session.target.flush()
            time.sleep(0.1)
            for stream in streams.values():
                stream.reset_input_buffer()
                stream.reset_output_buffer()
                stream.write(payload)
                stream.flush()
            captures = {port: bytearray() for port in streams}
            deadline = time.monotonic() + 0.5
            while time.monotonic() < deadline:
                for port, stream in streams.items():
                    captures[port].extend(stream.read(stream.in_waiting))
                time.sleep(0.005)
            frozen = {port: bytes(data) for port, data in captures.items()}
            item = {'mode': mode, 'pin_cnf': hex(session.target.read32(address)), 'received_hex': {port: data.hex() for port, data in frozen.items()}, 'expected_hex': payload[::-1].hex()}
            try:
                item['selected_port'] = runner.choose_unique_response(frozen, payload[::-1])
                item['exact_oracle'] = 'passed'
            except Exception as error:
                item['exact_oracle'] = 'failed'
                item['error'] = str(error)
            result['observations'].append(item)
    finally:
        session.target.write32(address, original)
        session.target.flush()
        result['restored_pin_cnf'] = hex(session.target.read32(address))
        assert session.target.read32(address) == original
write_new(WORK / 'idle-bias-b-diagnostic.json', result)
print(json.dumps(result, ensure_ascii=False))
