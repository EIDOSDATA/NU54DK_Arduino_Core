"""! @brief 실패한 동일 TWIM22 image의 SWD 상태와 한 번의 재시작 frame을 계측합니다. """
from runtime import *
from contextlib import ExitStack
from datetime import datetime, timezone
import time
import serial
from elftools.elf.elffile import ELFFile
import m24_twim_onboard as runner
from onboard_start import reset_halted_start

image = next(BUILD.glob('**/nucode.m24.twim22_hil/m24_twim_onboard_hil/zephyr/zephyr.elf'))
with image.open('rb') as stream:
    table = ELFFile(stream).get_section_by_name('.symtab')
    symbols = {name: table.get_symbol_by_name(name)[0]['st_value'] for name in ('m24_twim_stage', 'm24_twim_result')}
def read_state():
    session = ConnectHelper.session_with_chosen_probe(unique_id=UIDS[0], target_override='nrf54l', frequency=1000000, blocking=False, no_config=True, options={'auto_unlock': False, 'connect_mode': 'attach', 'resume_on_disconnect': False})
    with session:
        return {'cpuid': hex(session.target.read32(0xE000ED00)), 'state': session.target.get_state().name, **{name: session.target.read32(address) for name, address in symbols.items()}}
result = {'type': 'bounded-diagnostic-not-formal-suite', 'source': SOURCE, 'probe_id_sha256': HASHES[0], 'reason': 'TWIM22 canonical READY contained 34 bytes; inspect exact wire frame and firmware stage without another flash', 'flash_executed': False, 'before': read_state(), 'created_at_utc': datetime.now(timezone.utc).isoformat()}
with ExitStack() as stack:
    streams = {port: stack.enter_context(serial.Serial(port, 115200, timeout=0, write_timeout=2, rtscts=False)) for port in ('COM5', 'COM6')}
    result['controlled_start'] = reset_halted_start(streams, UIDS[0])
    captures = {port: bytearray() for port in streams}
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        for port, stream in streams.items():
            captures[port].extend(stream.read(stream.in_waiting))
        time.sleep(0.01)
    result['ready_hex'] = {port: bytes(data).hex() for port, data in captures.items()}
    try:
        port = runner.choose_exact_port({port: bytes(data) for port, data in captures.items()}, runner.ready_frame(22))
        streams[port].write(runner.command_frame(22))
        selected, received = runner.collect_frame(streams, None, 3)
        result['response_hex'] = {port: data.hex() for port, data in received.items()}
        result['validated_result'] = runner.validate_result_frame(received[selected], 22)
        result['diagnostic_status'] = 'passed'
    except Exception as error:
        result['diagnostic_status'] = 'failed'
        result['error'] = str(error)
result['after'] = read_state()
write_new(WORK / 'twim22-a-diagnostic.json', result)
print(json.dumps(result, ensure_ascii=False))
