"""! @brief 두 probe의 읽기 응답 회복을 확인한 뒤 한 번의 새 실행만 준비합니다. """
from runtime import *
import v04_fixture as fixture
import v04_pair as pair

failed = json.loads((WORK / 'fixture408-attempt1.json').read_text(encoding='utf-8'))
diagnostic = json.loads((WORK / 'probe-diagnostic.json').read_text(encoding='utf-8'))
assert failed['status'] == 'failed' and failed['external_wiring_executed'] is False and failed['results'] == []
assert len(diagnostic['devices']) == 2
assert all(row['status'] == 'passed' and row['cpuid'] == '0x411fd210' and len(row['com_ports']) == 2 for row in diagnostic['devices'])
assert [row['state'] for row in diagnostic['devices']] == ['HALTED', 'SLEEPING']
images = [pair.inspect_image(REPO, BUILD, role) for role in (1, 2)]
confirmation = json.loads((WORK / 'confirmation.json').read_text(encoding='utf-8'))
fixture.validate_confirmation(confirmation, images, UIDS, 408)
write_new(WORK / 'retry-decision.json', {'source': SOURCE, 'fixture_id': 408,
    'failed_attempt': 'fixture408-attempt1.json', 'failure_phase': 'DUT sector flash CMSIS-DAP timeout',
    'functional_results_first_attempt': 0, 'external_wiring_executed_first_attempt': False,
    'diagnostic': 'probe-diagnostic.json', 'observed_recovery': 'Both exact probes read expected CPUID at 10 MHz; A HALTED, B SLEEPING; four COM ports remain',
    'root_cause': 'unresolved; similar historical timeouts do not establish common root cause',
    'next_action': 'One complete new canonical run with same source/images/SWD and original confirmation timestamp',
    'maximum_additional_attempts': 1, 'failed_results_reused': False, 'mass_erase_recover_unlock': False})
target = WORK / 'run-attempt2.py'
assert not target.exists()
target.write_text((WORK / 'run.py').read_text(encoding='utf-8').replace('fixture408-attempt1.json', 'fixture408-attempt2.json'), encoding='utf-8', newline='\n')
audit = WORK / 'audit_results.py'
audit.write_text(audit.read_text(encoding='utf-8').replace('fixture408-attempt1.json', 'fixture408-attempt2.json').replace("'attempt': 1", "'attempt': 2"), encoding='utf-8', newline='\n')
print('BOUNDED_FRESH_ATTEMPT_PREPARED=1;ORIGINAL_CONFIRMATION_UNCHANGED;SWD_HZ=10000000')
