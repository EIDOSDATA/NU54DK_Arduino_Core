"""! @brief CONSTLAT 수정의 exact pair 산출물과 실제 설정 변경을 보존합니다. """
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
shutil.copyfile(work.parent / 'r13/u4i-artifact-index.json', work / 'target-artifact-index.json')
shutil.copyfile(Path('C:/u4i/m12-build-evidence.json'), work / 'target-build-evidence.json')
index = json.loads((work / 'target-artifact-index.json').read_text())
prior = json.loads((work.parent / 't12-fixture440-phase/target-artifact-index.json').read_text())
assert len(index['targets']) == 2
rows = []
for role, target in enumerate(index['targets'], 1):
    old = prior['targets'][role - 1]
    assert target['scenario'] == old['scenario'] and target['status'] == 'built-not-run'
    assert target['source_membership_sha256'] == old['source_membership_sha256']
    changed = [name for name, value in target['repository_compiled_sources_sha256'].items() if old['repository_compiled_sources_sha256'].get(name) != value]
    assert changed == ['tests/zephyr/v04_pair_hil/src/signal_hil.cpp'], changed
    for artifact in target['artifacts'].values():
        data = Path(artifact['path']).read_bytes()
        assert hashlib.sha256(data).hexdigest() == artifact['sha256']
    directory = Path(target['artifacts']['zephyr.elf']['path']).parent
    old_directory = Path(old['artifacts']['zephyr.elf']['path']).parent
    config = (directory / '.config').read_text().splitlines()
    old_config = (old_directory / '.config').read_text().splitlines()
    assert 'CONFIG_NRF_SYS_EVENT=y' in config and 'CONFIG_NRFX_POWER=y' in config
    assert '# CONFIG_NRF_SYS_EVENT_IRQ_LATENCY is not set' in config
    assert (directory / 'zephyr.dts').read_bytes() == (old_directory / 'zephyr.dts').read_bytes()
    for source_path, filename in ((Path(target['build_log']['path']), f'role{role}-build.log'),
        (Path(target['identity_records'][0]['file']['path']), f'role{role}-build-record.yml'),
        (directory / '.config', f'role{role}-config.txt'), (directory / 'zephyr.dts', f'role{role}-zephyr.dts')):
        shutil.copyfile(source_path, work / filename)
    rows.append({'role': role, 'changed_translation_units': changed, 'source_membership_identical': True,
        'resolved_dts_identical': True, 'config_added': sorted(set(config) - set(old_config)),
        'config_removed': sorted(set(old_config) - set(config))})
(work / 'build-input-comparison.json').write_text(json.dumps({'source': source, 'prior_source': '7641229dca8c37be7a0d07241d407cb14cbf76ca', 'comparisons': rows}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
print('CONSTLAT_PAIR2_INPUT_AUDIT_PASS;HIL_SOURCE_AND_SYSTEM_EVENT_CONFIG_CHANGED;DTS_UNCHANGED')
