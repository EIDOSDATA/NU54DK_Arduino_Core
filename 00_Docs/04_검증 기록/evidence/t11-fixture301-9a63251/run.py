"""! @brief 확인된 Fixture 301만 canonical runner와 10 MHz SWD로 한 번 실행합니다. """
from runtime import *
import v04_fixture_run as runner

try:
    raise SystemExit(runner.main(['--dut', UIDS[0], '--peer', UIDS[1], '--build-root', str(BUILD), '--pyocd', str(BUNDLE / 'opt/bin/Scripts/pyocd.exe'), '--fixture', '301', '--swd-frequency-hz', '10000000', '--confirmation', str(WORK / 'confirmation.json'), '--evidence', str(WORK / 'fixture301-attempt1.json'), '--repetitions', '1', '--execute-fixture']))
except Exception as error:
    print('V04_FIXTURE_FAIL: ' + str(error), file=sys.stderr, flush=True)
    raise SystemExit(1)
