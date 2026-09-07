"""! @brief 문서 HEAD의 exact pair와 이전 실행 코드·설정의 동등성을 확인합니다. """
from pathlib import Path
import hashlib
import json
import shutil
import subprocess

work = Path(__file__).resolve().parent
repo = Path(r'C:\Users\eidos\GitHub\NU54DK_Arduino_Core')
source = (work / 'source.txt').read_text().strip()
prior_source = '917dc0284b1185d23eeef3f8df31bd3498f78408'
assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip() == source
assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=repo)
shutil.copyfile(work.parent / 'r13/u4m-artifact-index.json', work / 'target-artifact-index.json')
shutil.copyfile(Path('C:/u4m/m12-build-evidence.json'), work / 'target-build-evidence.json')
index = json.loads((work / 'target-artifact-index.json').read_text())
prior = json.loads((work.parent / 't12-fixture440-continuous/target-artifact-index.json').read_text())
assert len(index['targets']) == len(prior['targets']) == 2
rows = []
for role, target in enumerate(index['targets'], 1):
    old = prior['targets'][role - 1]
    assert target['scenario'] == old['scenario'] and target['status'] == 'built-not-run'
    assert target['source_membership_sha256'] == old['source_membership_sha256']
    assert target['normalized_config_sha256'] == old['normalized_config_sha256']
    differences = []
    for name, digest in target['repository_compiled_sources_sha256'].items():
        if old['repository_compiled_sources_sha256'][name] != digest:
            differences.append(name)
            assert name == 'tests/zephyr/v04_pair_hil/src/main.cpp'
            snapshot = work.parent / 't12-fixture440-continuous/main-before-newline-format.cpp'
            assert hashlib.sha256(snapshot.read_bytes()).hexdigest() == old['repository_compiled_sources_sha256'][name]
            assert snapshot.read_bytes().replace(b'\r\n', b'\n') == (repo / name).read_bytes().replace(b'\r\n', b'\n')
        assert subprocess.check_output(['git', 'show', prior_source + ':' + name], cwd=repo) == subprocess.check_output(['git', 'show', source + ':' + name], cwd=repo)
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
        'git_source_blobs_identical': True, 'raw_newline_only_differences': differences,
        'membership_identical': True, 'config_identical': True, 'dts_identical': True})
for name in ('tests/zephyr/v04_pair_hil/src/pdm_continuous.h', 'tests/hil/nu54dk/v04_pdm_continuous.py',
             'tests/hil/nu54dk/v04_signal.py', 'tests/hil/nu54dk/v04_signal_run.py', 'tests/host/test_v04_pdm_continuous.py'):
    assert subprocess.check_output(['git', 'show', prior_source + ':' + name], cwd=repo) == subprocess.check_output(['git', 'show', source + ':' + name], cwd=repo)
(work / 'build-input-comparison.json').write_text(json.dumps({'source': source, 'prior_source': prior_source,
    'comparisons': rows, 'continuous_helper_runner_tests_identical': True,
    'old_full_host_status': 'blocked; not promoted by this build or hardware run'}, indent=2) + '\n', encoding='utf-8')
print('EXACT_PAIR2_INPUT_EQUIVALENCE_PASS')
