"""! @brief source별 실패와 실제 부분 통과를 구분하여 430 원본 보존을 준비합니다. """
from pathlib import Path
import json
import re

WORK = Path(__file__).resolve().parent
SOURCE = (WORK / 'source.txt').read_text().strip()
host = (WORK / 'gate-host-final.log').read_text(encoding='utf-8')
host_record = json.loads((WORK / 'gate-host-final.json').read_text(encoding='utf-8'))
assert host_record['source'] == SOURCE and not host_record['dirty'] and host_record['returncode'] == 0
total = sum(map(int, re.findall(r'^Ran (\d+) tests? in', host, flags=re.M)))
skips = [line for line in host.splitlines() if '... skipped ' in line]
assert total == 659 and len(skips) == 1 and 'NUCODE_M13_CLI_DISCOVERY' in skips[0]
assert 'CPP_STYLE_FILES=360; FAILED=0; WRITE=0' in (WORK / 'style.log').read_text()
post = json.loads((WORK / 'postflight.json').read_text())
assert len(post['devices']) == 2 and all(d['state'] == 'SLEEPING' and d['i2s_enable'] == 0 and set(d['signal_pin_cnf'].values()) == {2} for d in post['devices'])
audit = json.loads((WORK / 'partial-results-audit.json').read_text())
assert audit['audit_status'] == 'passed' and audit['campaign_status'] == 'failed' and audit['functional_records'] == 72
diagnostic = json.loads((WORK.parent / 't12-fixture430-fixed/startup-diagnostic.json').read_text())
assert len(diagnostic['cases']) == 24 and not diagnostic['functional_pass_claimed']
assert all(c['cleanup'] == [{'role': 1, 'reply': [0]}, {'role': 2, 'reply': [0]}] for c in diagnostic['cases'])
for name, value in {
    'software-summary.json': {'source': SOURCE, 'host': {'total': total, 'passed': total - 1, 'skipped': 1,
        'groups': 81, 'skip_reason': skips[0], 'native_compiler_skips': 0}, 'style_files': 360,
        'style_failed': 0, 'exact_pair_built': 2, 'target_build_seconds': 120.55,
        'prior_source_host': {'source': 'c4611822d5a1180741989a351112b8784d610d5d', 'total': 658, 'passed': 657, 'skipped': 1},
        'physical_executed_for_this_source': True, 'fixture430_status': 'failed',
        'not_reexecuted': ['full target matrix', 'package gate', 'example compile matrix', 'remote GitHub Actions'],
        'public_core_sdk_board_changes': False, 'readiness_open_blockers': 8},
    'completion-status.json': {'source': SOURCE, 'status': 'fixture430-failed-awaiting-unchanged-wiring-reconfirmation',
        'source_physical_executed': True, 'functional_pass': 72, 'failed_cases': 1, 'unexecuted_cases': 119,
        'cleanup_pass': 73, 'postflight_pass': 2, 'whole_fixture_pass': False,
        'failed_vector': [48000, 24, 0, 32, 1, 324508639], 'failed_controller_role': 1,
        'error': 'signal firmware error role=1: [1, 1, 1, 0, 128, 32, 32, 1]',
        'original_confirmation_utc': '2026-09-06T17:43:49Z', 'confirmation_expired_utc': '2026-09-06T18:13:49Z',
        'reconfirmation_requested': True, 'reconfirmation_received': False, 'next_fixture': 430,
        'last_uploaded_source': SOURCE, 'next_action': 'Localize short-buffer underrun timing; fresh unchanged430 confirmation before any new signals; clean HEAD pair and full 192 rerun; no accumulation of partial PASS',
        'fixture440_executed': False, 'background_hardware_tests_running': False}
}.items():
    with (WORK / name).open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
old = (WORK.parent / 't12-fixture420-final/publish_evidence.py').read_text(encoding='utf-8')
tail = old[old.index('published = []'):].replace('t12-fixture420-', 't12-fixture430-')
stages = [('t12-fixture430', '56a88a5c9b9c68055fccfa9b185a7f1cb6aa4a73', 'first-vector-underrun-failed'),
          ('t12-fixture430-fixed', 'c4611822d5a1180741989a351112b8784d610d5d', 'first-vector-packing-failed-plus24-diagnostics'),
          ('t12-fixture430-final', SOURCE, 'campaign-failed-72-pass-1-fail-119-not-run')]
(WORK / 'publish_evidence.py').write_text('from runtime import *\nimport gzip\nstages = ' + repr(stages) + '\n' + tail, encoding='utf-8', newline='\n')
print('SOFTWARE659_AND_PARTIAL72_AUDIT_PREPARED')
