"""! @brief 문서 커밋 뒤 동일한 컴파일 입력과 새 exact image를 대조합니다. """
from pathlib import Path
import hashlib
import json
import shutil
import subprocess

work = Path(__file__).resolve().parent
repo = Path(r'C:\Users\eidos\GitHub\NU54DK_Arduino_Core')
source = (work / 'source.txt').read_text().strip()
assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip() == source
assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=repo)
shutil.copyfile(work.parent / 'r13/u4k-artifact-index.json', work / 'target-artifact-index.json')
shutil.copyfile(Path('C:/u4k/m12-build-evidence.json'), work / 'target-build-evidence.json')
index = json.loads((work / 'target-artifact-index.json').read_text())
prior = json.loads((work.parent / 't12-fixture440-constlat-link/target-artifact-index.json').read_text())
assert len(index['targets']) == len(prior['targets']) == 2
rows = []
for role, target in enumerate(index['targets'], 1):
    old = prior['targets'][role - 1]
    assert target['scenario'] == old['scenario'] and target['status'] == 'built-not-run'
    assert target['repository_compiled_sources_sha256'] == old['repository_compiled_sources_sha256']
    assert target['source_membership_sha256'] == old['source_membership_sha256']
    assert target['normalized_config_sha256'] == old['normalized_config_sha256']
    for artifact in target['artifacts'].values():
        assert hashlib.sha256(Path(artifact['path']).read_bytes()).hexdigest() == artifact['sha256']
    directory = Path(target['artifacts']['zephyr.elf']['path']).parent
    old_directory = Path(old['artifacts']['zephyr.elf']['path']).parent
    assert (directory / 'zephyr.dts').read_bytes() == (old_directory / 'zephyr.dts').read_bytes()
    for origin, filename in ((Path(target['build_log']['path']), f'role{role}-build.log'),
        (Path(target['identity_records'][0]['file']['path']), f'role{role}-build-record.yml'),
        (directory / '.config', f'role{role}-config.txt'), (directory / 'zephyr.dts', f'role{role}-zephyr.dts')):
        shutil.copyfile(origin, work / filename)
    rows.append({'role': role, 'repository_translation_units': len(target['repository_compiled_sources_sha256']),
        'repository_inputs_identical': True, 'membership_identical': True, 'config_identical': True, 'dts_identical': True})
(work / 'build-input-comparison.json').write_text(json.dumps({'source': source,
    'prior_source': 'e9d264c502488754fbda2eabcf174764f703e37d', 'comparisons': rows}, indent=2) + '\n', encoding='utf-8')
print('EXACT_PAIR2_AND_INPUT_EQUIVALENCE_PASS')
