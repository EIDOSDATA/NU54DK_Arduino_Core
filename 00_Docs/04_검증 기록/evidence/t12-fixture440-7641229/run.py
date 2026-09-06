"""! @brief 확인된 440 전체 계획을 실행하고 canonical 수신 원본을 그대로 보존합니다. """
from runtime import *
import v04_signal_run as runner
import v04_signal as signal
import v04_pair as pair
from diagnostic_template import install
trace = install(pair, WORK / "setup-trace.jsonl")

original_boot = pair.boot_exact
startup_pins = []
def record_boot(*args, **kwargs):
    """! @brief 정식 boot 뒤 읽기만 하여 원래 핀 설정을 기록합니다. """
    device, flash = original_boot(*args, **kwargs)
    startup_pins.append({'role': device.image['role'], 'pin_cnf': {
        str(pin): device.target.read32(0x500D8280 + pin * 4) for pin in (4, 5, 6, 7)}})
    if len(startup_pins) == 2:
        write_new(WORK / 'startup-pins.json', {'source': SOURCE, 'devices': startup_pins,
            'extra_fixture_commands': False, 'capture': 'passive read immediately after canonical boot'})
    return device, flash
pair.boot_exact = record_boot

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
    trace.close()
