"""! @brief 실패 진단과 교정 후 전체 PASS의 검증 범위·원본을 분리 보존합니다. """
from pathlib import Path
import hashlib
import json
import re
import shutil
import subprocess

WORK = Path(__file__).resolve().parent
ROOT = Path(r'C:\Users\eidos\GitHub\NU54DK_Arduino_Core')
SOURCE = (WORK / 'source.txt').read_text().strip()
assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip() == SOURCE
assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT)

def write_new(path, value):
    """! @brief 기존 증거를 덮어쓰지 않고 JSON을 새로 기록합니다. """
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')

def host_summary(folder, total, groups):
    """! @brief 실제 완료 로그에서 Host 총수와 조건부 skip을 계산합니다. """
    log = (folder / 'gate-host-final.log').read_text(encoding='utf-8')
    record = json.loads((folder / 'gate-host-final.json').read_text())
    assert record['source'] == (folder / 'source.txt').read_text().strip()
    assert not record['dirty'] and record['returncode'] == 0
    counts = list(map(int, re.findall(r'^Ran (\d+) tests? in', log, re.M)))
    skips = [line for line in log.splitlines() if '... skipped ' in line]
    assert sum(counts) == total and len(counts) == groups
    assert len(skips) == 1 and 'NUCODE_M13_CLI_DISCOVERY' in skips[0]
    return {'total': total, 'passed': total - 1, 'skipped': 1, 'groups': groups,
        'skip_reason': skips[0], 'native_compiler_skips': 0}

host = host_summary(WORK, 660, 82)
prior = WORK.parent / 't12-fixture430-timing'
prior_host = host_summary(prior, 659, 81)
assert 'CPP_STYLE_FILES=361; FAILED=0; WRITE=0' in (WORK / 'style.log').read_text()
for gate in ('contract', 'inventory', 'package'):
    row = json.loads((WORK / f'gate-{gate}.json').read_text())
    assert row['source'] == SOURCE and not row['dirty'] and row['returncode'] == 0
    assert f'M12_GATE_PASS={gate}' in (WORK / f'gate-{gate}.log').read_text()
assert 'Ran 45 tests ' in (WORK / 'gate-contract.log').read_text()
assert 'Ran 20 tests ' in (WORK / 'gate-package.log').read_text()
index = json.loads((WORK / 'affected-target-artifact-index.json').read_text())
assert len(index['targets']) == 8 and not index['physical_executed']
affected = []
for number, target in enumerate(index['targets'], 1):
    assert target['status'] == 'built-not-run'
    for name, digest in target['repository_compiled_sources_sha256'].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest
    for artifact in target['artifacts'].values():
        raw = Path(artifact['path']).read_bytes()
        assert len(raw) == artifact['bytes'] and hashlib.sha256(raw).hexdigest() == artifact['sha256']
    log = target['build_log']
    assert hashlib.sha256(Path(log['path']).read_bytes()).hexdigest() == log['sha256']
    shutil.copyfile(log['path'], WORK / f'affected-{number:02d}-build.log')
    for item, record in enumerate(target['identity_records'], 1):
        assert record['identity']['core_revision'] == SOURCE[:12]
        shutil.copyfile(record['file']['path'], WORK / f'affected-{number:02d}-record{item}.yml')
    affected.append(target['scenario'])
post = json.loads((WORK / 'postflight.json').read_text())
assert post['source'] == SOURCE and len(post['devices']) == 2
assert all(d['state'] == 'SLEEPING' and d['identity_status'] == 'passed' and
    d['i2s_enable'] == 0 and set(d['signal_pin_cnf'].values()) == {2} for d in post['devices'])
audit = json.loads((WORK / 'results-audit.json').read_text())
timings = json.loads((WORK / 'timings-audit.json').read_text())
assert audit['status'] == timings['status'] == 'passed' and audit['functional_records'] == 192
partial = json.loads((prior / 'partial-results-audit.json').read_text())
assert partial['audit_status'] == 'passed' and partial['campaign_status'] == 'failed'
write_new(WORK / 'software-summary.json', {'source': SOURCE, 'host': host,
    'contract_tests_passed': 45, 'inventory': 'passed; readiness open blockers remain 8',
    'package_tests_passed': 20, 'style_files': 361, 'style_failed': 0,
    'pair_builds': 2, 'pair_build_seconds': 285.60, 'affected_builds': 8,
    'affected_scenarios': affected, 'affected_build_seconds': 472.83,
    'native_differential_steps': 4000, 'native_reference': 'prior reserve-commit-convert-release algorithm',
    'native_precommit_subsets': ['compact-native-final.json', 'resource-route.json'],
    'full_host_includes_final_committed_native_test': True,
    'internal_core_resource_manager_changed': True, 'public_api_sdk_board_changed': False,
    'fixture430_status': 'passed', 'physical_executed_for_this_source': True,
    'not_reexecuted': ['entire target matrix', 'example compile matrix', 'remote GitHub Actions',
        'current-source T11 external wiring regression', 'T13 concurrency/soak'],
    'readiness_open_blockers': 8})
write_new(prior / 'software-summary.json', {'source': partial['source'], 'host': prior_host,
    'style_files': 360, 'pair_builds': 2, 'pair_build_seconds': 118.85,
    'fixture430_status': 'failed', 'functional_pass': 72, 'failed_cases': 1, 'unexecuted_cases': 119,
    'cleanup_pass': 73, 'postflight_roles_pass': 2,
    'trace_observed_queue_us': [309, 308, 278, 282], 'public_core_changed': False})
write_new(WORK / 'completion-status.json', {'source': SOURCE, 'status': 'fixture430-passed',
    'source_physical_executed': True, 'functional_pass': 192, 'failed_cases': 0, 'unexecuted_cases': 0,
    'cleanup_pass': 192, 'postflight_pass': 2, 'whole_fixture_pass': True,
    'user_unchanged_wiring_confirmation_utc': '2026-09-06T18:35:58Z',
    'confirmation_expires_utc': '2026-09-06T19:05:58Z',
    'last_uploaded_source': SOURCE, 'next_fixture': 440, 'fixture440_executed': False,
    'next_action': 'USB disconnected, change to Fixture440 wiring and obtain new confirmation before signals',
    't12_whole_completed': False, 'background_hardware_tests_running': False})
old = (WORK.parent / 't12-fixture430-final/publish_evidence.py').read_text(encoding='utf-8')
tail = old[old.index('published = []'):]
stages = [('t12-fixture430-timing', partial['source'], 'campaign-failed-72-pass-1-fail-119-not-run-timing-trace'),
    ('t12-fixture430-compact', SOURCE, 'campaign-passed-192-functional-192-cleanup')]
(WORK / 'publish_evidence.py').write_text('from runtime import *\nimport gzip\nstages = ' + repr(stages) + '\n' + tail,
    encoding='utf-8', newline='\n')
print('SOFTWARE660_659PASS_1SKIP;CONTRACT45;PACKAGE20;INVENTORY_PASS;STYLE361;TARGET10;HIL192;PREPARED')
