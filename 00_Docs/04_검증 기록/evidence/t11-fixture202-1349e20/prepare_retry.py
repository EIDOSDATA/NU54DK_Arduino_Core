"""! @brief 읽기 전용 응답 회복을 확인한 뒤 단 한 번의 새 실행을 준비합니다. """
from runtime import *
import v04_fixture as fixture
import v04_pair as pair

failed = json.loads((WORK / 'fixture202-attempt1.json').read_text(encoding='utf-8-sig'))
diagnostic = json.loads((WORK / 'probe-diagnostic.json').read_text(encoding='utf-8'))
assert failed['status'] == 'failed' and failed['external_wiring_executed'] is False and failed['results'] == []
assert len(diagnostic['devices']) == 2 and all(row['status'] == 'passed' and row['cpuid'] == '0x411fd210' for row in diagnostic['devices'])
assert all(len(row['com_ports']) == 2 for row in diagnostic['devices'])
images = [pair.inspect_image(REPO, BUILD, role) for role in (1, 2)]
confirmation = json.loads((WORK / 'confirmation.json').read_text(encoding='utf-8'))
fixture.validate_confirmation(confirmation, images, UIDS, 202)
decision = {'source': SOURCE, 'fixture_id': 202, 'failed_attempt': 'fixture202-attempt1.json', 'failure_phase': 'peer sector flash: CMSIS-DAP timeout', 'external_wiring_executed_first_attempt': False, 'functional_results_first_attempt': 0, 'diagnostic': 'probe-diagnostic.json', 'observed_recovery': 'Both exact probes respond to 10 MHz SWD CPUID reads; A SLEEPING, B HALTED, all four COM ports enumerated', 'root_cause': 'unresolved; similar symptom preserved for Fixture 103', 'next_action': 'One new canonical run with unchanged exact images and 10 MHz, still-current original user confirmation, new evidence file', 'maximum_additional_attempts': 1, 'failed_results_reused': False, 'mass_erase_recover_unlock': False}
write_new(WORK / 'retry-decision.json', decision)
target = WORK / 'run-attempt2.py'
assert not target.exists()
target.write_text((WORK / 'run.py').read_text(encoding='utf-8').replace('fixture202-attempt1.json', 'fixture202-attempt2.json'), encoding='utf-8', newline='\n')
target = WORK / 'progress-attempt2.py'
assert not target.exists()
target.write_text((WORK / 'progress.py').read_text(encoding='utf-8').replace('fixture202-attempt1.json', 'fixture202-attempt2.json'), encoding='utf-8', newline='\n')
print('BOUNDED_FRESH_ATTEMPT_PREPARED=1; ORIGINAL_CONFIRMATION_UNCHANGED; SWD_HZ=10000000')
