"""! @brief 확인된 Fixture 430만 canonical runner와 10 MHz SWD로 한 번 실행합니다. """
from runtime import *
import v04_signal_run as runner
import v04_signal as signal

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
    capture_count += 1
    return actual

capture = (WORK / 'i2s-payloads.jsonl').open('x', encoding='utf-8', newline='\n')
signal.read_u32 = capture_read_u32

try:
    raise SystemExit(runner.main(['--dut', UIDS[0], '--peer', UIDS[1], '--build-root', str(BUILD), '--pyocd', str(BUNDLE / 'opt/bin/Scripts/pyocd.exe'), '--fixture', '430', '--swd-frequency-hz', '10000000', '--confirmation', str(WORK / 'confirmation.json'), '--evidence', str(WORK / 'fixture430-attempt1.json'), '--repetitions', '1', '--execute-fixture']))
except Exception as error:
    print('V04_FIXTURE_FAIL: ' + str(error), file=sys.stderr, flush=True)
    raise SystemExit(1)
finally:
    capture.close()
