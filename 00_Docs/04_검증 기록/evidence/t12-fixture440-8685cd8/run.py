"""! @brief 확인된 440 전체 계획을 실행하고 canonical 수신 원본을 그대로 보존합니다. """
from runtime import *
import v04_signal_run as runner
import v04_signal as signal

original_read = signal.read_u16
capture_count = 0

def capture_read(device, samples):
    """! @brief 추가 장치 명령 없이 정식 runner의 PDM sample을 복사합니다. """
    global capture_count
    actual = original_read(device, samples)
    capture.write(json.dumps({'read_index': capture_count, 'receiver_role': device.image['role'],
        'requested_samples': samples, 'samples': actual}) + '\n')
    capture.flush()
    capture_count += 1
    return actual

capture = (WORK / 'pdm-samples.jsonl').open('x', encoding='utf-8', newline='\n')
signal.read_u16 = capture_read
try:
    raise SystemExit(runner.main(['--dut', UIDS[0], '--peer', UIDS[1], '--build-root', str(BUILD),
        '--pyocd', str(BUNDLE / 'opt/bin/Scripts/pyocd.exe'), '--fixture', '440',
        '--swd-frequency-hz', '10000000', '--confirmation', str(WORK / 'confirmation.json'),
        '--evidence', str(WORK / 'fixture440-attempt1.json'), '--repetitions', '1', '--execute-fixture']))
except Exception as error:
    print('V04_FIXTURE_FAIL: ' + str(error), file=sys.stderr, flush=True)
    raise SystemExit(1)
finally:
    capture.close()
