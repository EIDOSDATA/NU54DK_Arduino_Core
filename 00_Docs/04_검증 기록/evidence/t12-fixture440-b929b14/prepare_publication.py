"""! @brief 동일 software 입력과 새 440 결선 분리 실패 증거를 보존합니다. """
from pathlib import Path
import hashlib
import json
import shutil
import subprocess

WORK = Path(__file__).resolve().parent
ROOT = Path(r'C:\Users\eidos\GitHub\NU54DK_Arduino_Core')
SOURCE = (WORK / 'source.txt').read_text().strip()
assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip() == SOURCE
assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT)
prior = WORK.parent / 't12-fixture440-final'
old_index = json.loads((prior / 'target-artifact-index.json').read_text())
index = json.loads((WORK / 'target-artifact-index.json').read_text())
assert len(index['targets']) == len(old_index['targets']) == 2
comparisons = []
for role, target in enumerate(index['targets'], 1):
    old = old_index['targets'][role - 1]
    assert target['scenario'] == old['scenario'] and target['status'] == 'built-not-run'
    for key in ('normalized_config_sha256', 'source_membership_sha256', 'repository_compiled_sources_sha256'):
        assert target[key] == old[key]
    for artifact in target['artifacts'].values():
        raw = Path(artifact['path']).read_bytes()
        assert len(raw) == artifact['bytes'] and hashlib.sha256(raw).hexdigest() == artifact['sha256']
    dt = Path(target['artifacts']['zephyr.elf']['path']).with_name('zephyr.dts')
    old_dt = prior / f'role{role}-zephyr.dts'
    assert dt.read_bytes() == old_dt.read_bytes()
    shutil.copyfile(dt, WORK / f'role{role}-zephyr.dts')
    comparisons.append({'role': role, 'translation_units_identical': len(target['repository_compiled_sources_sha256']),
        'normalized_config_identical': True, 'source_membership_identical': True,
        'resolved_dts_bytes_identical': True, 'runtime_identity_expected_to_change': True,
        'dts_sha256': hashlib.sha256(dt.read_bytes()).hexdigest()})
paths = ['tests/hil/nu54dk/v04_signal.py', 'tests/hil/nu54dk/v04_signal_run.py',
    'tests/hil/nu54dk/v04_fixture.py', 'tests/hil/nu54dk/v04_pair.py', 'tests/hil/nu54dk/v04_fixtures.json']
changed = subprocess.check_output(['git', 'diff', '--name-only', 'ea4e25a', SOURCE, '--', 'cores', 'variants', 'zephyr', 'tests', 'tools', 'dts'], cwd=ROOT, text=True).splitlines()
assert changed == ['tests/hil/nu54dk/README.md']
summary = {'source': SOURCE, 'pair_builds': 2, 'pair_build_seconds': 122.39,
    'comparison_source': 'ea4e25a035dbc9219e417bf2a2056ce6f9a2e09c', 'comparisons': comparisons,
    'canonical_runner_sha256': {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in paths},
    'public_core_sdk_board_changed': False, 'new_host_or_style_run': False,
    'prior_source_host': {'passed': 660, 'skipped': 1, 'groups': 82, 'native_compiler_skips': 0},
    'prior_source_style_files': 361, 'new_physical_result': 'clock/gate separation requirement failed',
    'pdm_functional_gate_completed': False}
with (WORK / 'software-summary.json').open('x', encoding='utf-8', newline='\n') as output:
    output.write(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
tail = (prior / 'publish_evidence.py').read_text(encoding='utf-8')
tail = tail[tail.index('published = []'):]
stages = [('t12-fixture440-trace', SOURCE, 'clock-gate-electrically-coupled-user-inspection-required-pdm-incomplete')]
(WORK / 'publish_evidence.py').write_text('from runtime import *\nimport gzip\nstages = ' + repr(stages) + '\n' + tail,
    encoding='utf-8', newline='\n')
print('PAIR2_CURRENT_SOURCE;42TU_CONFIG_DTS_RUNNER_UNCHANGED;NET_ISOLATION_FAILED')
