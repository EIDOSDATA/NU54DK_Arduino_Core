"""! @brief 수정 source의 exact pair와 변경된 HIL translation unit을 대조합니다. """
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
for old, new in ((WORK.parent / 'r13/u3s-artifact-index.json', WORK / 'target-artifact-index.json'),
                 (Path(r'C:\u3s\m12-build-evidence.json'), WORK / 'target-build-evidence.json')):
    assert not new.exists()
    shutil.copyfile(old, new)
index = json.loads((WORK / 'target-artifact-index.json').read_text(encoding='utf-8'))
baseline = json.loads((WORK.parent / 't12-fixture420/target-artifact-index.json').read_text(encoding='utf-8'))
assert len(index['targets']) == 2
rows = []
for role, target in enumerate(index['targets'], 1):
    old = next(row for row in baseline['targets'] if row['scenario'] == target['scenario'])
    current_sources = target['repository_compiled_sources_sha256']
    prior_sources = old['repository_compiled_sources_sha256']
    assert current_sources.keys() == prior_sources.keys()
    changed = [path for path in current_sources if current_sources[path] != prior_sources[path]]
    assert changed == ['tests/zephyr/v04_pair_hil/src/signal_hil.cpp'], changed
    assert target['normalized_config_sha256'] == old['normalized_config_sha256']
    assert target['source_membership_sha256'] == old['source_membership_sha256']
    assert all(record['identity']['core_revision'] == SOURCE[:12] for record in target['identity_records'])
    shutil.copyfile(target['build_log']['path'], WORK / f'role{role}-build.log')
    shutil.copyfile(target['identity_records'][0]['file']['path'], WORK / f'role{role}-build-record.yml')
    rows.append({'scenario': target['scenario'], 'source': SOURCE, 'changed_translation_units': changed,
                 'repository_translation_units': len(current_sources), 'normalized_config_and_membership_unchanged': True,
                 'qdec_waveform_header_sha256': hashlib.sha256((ROOT / 'tests/zephyr/v04_pair_hil/src/qdec_waveform.h').read_bytes()).hexdigest(),
                 'prior_source': 'beebef829de94f92a3a0b6b8b0a6ed2447d3b560', 'artifacts': target['artifacts']})
(WORK / 'build-input-comparison.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
print('EXACT_FIXED_PAIR_BUILD_INPUT_AUDIT_PASS=2;SOURCE=' + SOURCE)
