"""! @brief 새 exact pair와 직전 검증 source의 실제 빌드 입력을 대조합니다. """
from pathlib import Path
import json
import shutil
import subprocess

WORK = Path(__file__).resolve().parent
ROOT = Path(r'C:\Users\eidos\GitHub\NU54DK_Arduino_Core')
SOURCE = (WORK / 'source.txt').read_text().strip()
assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip() == SOURCE
assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT)
for old, new in ((WORK.parent / 'r13/u4b-artifact-index.json', WORK / 'target-artifact-index.json'),
                 (Path(r'C:\u4b\m12-build-evidence.json'), WORK / 'target-build-evidence.json')):
    assert not new.exists()
    shutil.copyfile(old, new)
index = json.loads((WORK / 'target-artifact-index.json').read_text(encoding='utf-8'))
baseline = json.loads((WORK.parent / 't12-fixture430-compact/target-artifact-index.json').read_text(encoding='utf-8'))
assert len(index['targets']) == 2
rows = []
for role, target in enumerate(index['targets'], 1):
    old = next(row for row in baseline['targets'] if row['scenario'] == target['scenario'])
    for key in ('normalized_config_sha256', 'source_membership_sha256'):
        assert target[key] == old[key], (role, key)
    assert all(record['identity']['core_revision'] == SOURCE[:12] for record in target['identity_records'])
    shutil.copyfile(target['build_log']['path'], WORK / f'role{role}-build.log')
    shutil.copyfile(target['identity_records'][0]['file']['path'], WORK / f'role{role}-build-record.yml')
    rows.append({'scenario': target['scenario'], 'source': SOURCE,
                 'repository_translation_units': len(target['repository_compiled_sources_sha256']),
                 'normalized_config_and_membership_unchanged': True,
                 'changed_translation_units': [name for name, digest in target['repository_compiled_sources_sha256'].items() if old['repository_compiled_sources_sha256'].get(name) != digest],
                 'prior_source': '36ba819bbe03280fa82c62ef76b00c87a92c2aff', 'artifacts': target['artifacts']})
(WORK / 'build-input-comparison.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
print('EXACT_RESUME_PAIR_INPUT_AUDIT_PASS=2;SOURCE=' + SOURCE)
