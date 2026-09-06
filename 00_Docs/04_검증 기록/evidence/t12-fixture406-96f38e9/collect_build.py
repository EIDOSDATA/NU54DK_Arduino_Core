"""! @brief exact pair build와 이전 제품 코드의 변경 범위를 고정합니다. """
from pathlib import Path
import hashlib
import json
import shutil
import subprocess

work = Path(__file__).resolve().parent
repo = Path(r'C:\Users\eidos\GitHub\NU54DK_Arduino_Core')
build = Path(r'C:\u3m')
source = (work / 'source.txt').read_text(encoding='ascii').strip()
assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip() == source
assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=repo, text=True).strip()
for old, new in ((work.parent / 'r13/u3m-artifact-index.json', work / 'target-artifact-index.json'),
                 (build / 'm12-build-evidence.json', work / 'target-build-evidence.json')):
    assert not new.exists()
    shutil.copyfile(old, new)
index = json.loads((work / 'target-artifact-index.json').read_text(encoding='utf-8'))
old = json.loads((work.parent / 't12-fixture405/target-artifact-index.json').read_text(encoding='utf-8'))
rows = []
for before, after in zip(old['targets'], index['targets']):
    assert before['scenario'] == after['scenario']
    b, a = before['repository_compiled_sources_sha256'], after['repository_compiled_sources_sha256']
    assert set(a) == set(b)
    changed = [p for p in sorted(a) if a[p] != b[p]]
    assert changed == ['tests/zephyr/v04_pair_hil/src/signal_hil.cpp']
    rows.append({'scenario': after['scenario'], 'compiled_membership_unchanged': True,
                 'changed_compiled_inputs': changed, 'unchanged_compiled_inputs': len(a) - len(changed)})
product_delta = subprocess.check_output(['git', 'diff', '--name-only', '9fc12bfbdafbb8a4450ed6cc61ca97b9c1efd220', source,
    '--', 'cores', 'variants', 'libraries', 'board_package', 'tools', 'zephyr', 'platform.txt', 'boards.txt'], cwd=repo, text=True)
assert not product_delta.strip()
payload = {'source': source, 'prior_fixture405_source': '9fc12bfbdafbb8a4450ed6cc61ca97b9c1efd220',
           'product_build_tool_board_delta': [], 'pair_builds': rows,
           'physical_claim': '406 must run on these new images; prior fixture results retain their original source identity'}
(work / 'build-input-comparison.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print('EXACT_PAIR_BUILD_INPUT_AUDIT_PASS=2')
