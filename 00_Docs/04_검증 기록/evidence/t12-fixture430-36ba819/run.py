"""! @brief 확인된 Fixture 430만 canonical runner와 10 MHz SWD로 한 번 실행합니다. """
from runtime import *
import v04_signal_run as runner
import v04_signal as signal
import v04_pair as pair
from elftools.elf.elffile import ELFFile

trace_addresses = {}
for role in (1, 2):
    image = pair.inspect_image(REPO, BUILD, role)
    with image['elf'].open('rb') as stream:
        symbols = list(ELFFile(stream).get_section_by_name('.symtab').iter_symbols())
        traces = [s for s in symbols if 'i2s_trace' in s.name and s['st_size'] == 768]
        counts = [s for s in symbols if 'i2s_trace_count' in s.name and s['st_size'] == 4]
        assert len(traces) == len(counts) == 1
        trace_addresses[role] = (int(traces[0]['st_value']), int(counts[0]['st_value']))

original_read_u32 = signal.read_u32
capture_count = 0

def capture_read_u32(device, words):
    """! @brief 정식 runner가 읽은 I2S 원본 word를 추가 명령 없이 별도 보존합니다. """
    global capture_count
    actual = original_read_u32(device, words)
    row = {'read_index': capture_count, 'receiver_role': device.image['role'],
           'requested_words': words, 'raw_words': actual}
    capture.write(json.dumps(row) + '\n')
    capture.flush()
    address, counter = trace_addresses[device.image['role']]
    count = device.target.read32(counter)
    assert count <= 32
    raw_trace = list(device.target.read_memory_block32(address, count * 6))
    timings.write(json.dumps({'read_index': capture_count, 'receiver_role': device.image['role'],
        'entries': [raw_trace[index:index + 6] for index in range(0, len(raw_trace), 6)]}) + '\n')
    timings.flush()
    capture_count += 1
    return actual

capture = (WORK / 'i2s-payloads.jsonl').open('x', encoding='utf-8', newline='\n')
timings = (WORK / 'i2s-timings.jsonl').open('x', encoding='utf-8', newline='\n')
signal.read_u32 = capture_read_u32

try:
    raise SystemExit(runner.main(['--dut', UIDS[0], '--peer', UIDS[1], '--build-root', str(BUILD), '--pyocd', str(BUNDLE / 'opt/bin/Scripts/pyocd.exe'), '--fixture', '430', '--swd-frequency-hz', '10000000', '--confirmation', str(WORK / 'confirmation.json'), '--evidence', str(WORK / 'fixture430-attempt1.json'), '--repetitions', '1', '--execute-fixture']))
except Exception as error:
    print('V04_FIXTURE_FAIL: ' + str(error), file=sys.stderr, flush=True)
    raise SystemExit(1)
finally:
    capture.close()
    timings.close()
