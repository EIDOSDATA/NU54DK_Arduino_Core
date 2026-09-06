"""! @brief 두 exact build의 실제 입력과 변경 영향·실기 결과를 대조합니다. """
from pathlib import Path
import hashlib
import json
import subprocess
work = Path(__file__).resolve().parent
repo = Path(r'C:\Users\eidos\GitHub\NU54DK_Arduino_Core')
def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))
first = read(work.parent / 'r13/u2a-artifact-index.json')
second = read(work.parent / 'r13/u2b-artifact-index.json')
old = {row['scenario']: row for row in first['targets']}
comparisons = []
for row in second['targets']:
    prior = old[row['scenario']]
    matched = {key: row[key] == prior[key] for key in ('repository_compiled_sources_sha256', 'normalized_config_sha256', 'source_membership_sha256', 'memory_bytes')}
    assert all(matched.values()), (row['scenario'], matched)
    comparisons.append({'scenario': row['scenario'], **matched})
changed = subprocess.check_output(['git', '-C', str(repo), 'diff', '--name-only', '-z', '18a7cbec9cceed38d6c866131afdac9e6ffbc4b8', '373d98da055b83e86b039448965d630e8d546497'], text=True, encoding='utf-8').strip('\0').split('\0')
assert all(path.startswith(('00_Docs/', 'tests/hil/nu54dk/')) for path in changed)
result = {'first_source': '18a7cbec9cceed38d6c866131afdac9e6ffbc4b8', 'corrected_source': '373d98da055b83e86b039448965d630e8d546497', 'changed_files': changed, 'product_source_changed': False, 'compiled_input_config_memory_comparisons': comparisons, 'ble_hil_source': '18a7cbec9cceed38d6c866131afdac9e6ffbc4b8', 'ble_runtime_and_runner_unchanged_by_idle_fix': True}
(work / 'build-comparison.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
for name in ('u2a', 'u2b'):
    (work / (name + '-artifact-index.json')).write_bytes((work.parent / 'r13' / (name + '-artifact-index.json')).read_bytes())
print('BUILD_SOURCE_CONFIG_MEMORY_EQUIVALENCE_PASS=' + str(len(comparisons)))
