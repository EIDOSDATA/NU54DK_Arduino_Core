"""! @brief 실행하지 못한 C linkage build 실패와 두 역할의 원본 로그를 보존합니다. """
from pathlib import Path
import hashlib
import json
import shutil

work = Path(__file__).resolve().parent
build = Path('C:/u4i')
for name in ('twister.json', 'testplan.json'):
    shutil.copyfile(build / name, work / name)
rows = []
for role, scenario in ((1, 'nucode.v04.pair_dut'), (2, 'nucode.v04.pair_peer')):
    directory = build / 'nrf54l15dk_nrf54l15_cpuapp_nu54dk/zephyr_gnu' / scenario / 'v04_pair_hil'
    for path, target in ((directory / 'build.log', work / f'role{role}-build.log'),
        (directory / 'zephyr/.config', work / f'role{role}-config.txt')):
        shutil.copyfile(path, target)
        rows.append({'file': target.name, 'original_path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    assert 'undefined reference' in (directory / 'build.log').read_text(encoding='utf-8')
(work / 'failed-build-summary.json').write_text(json.dumps({'source': (work / 'source.txt').read_text().strip(),
    'target_build_failures': 2, 'cause': 'C++ linkage declared by SDK C-only nrf_sys_event.h; fixed by caller extern C wrapper',
    'flash_executed': False, 'pdm_functional_executed': False, 'files': rows}, indent=2) + '\n', encoding='utf-8', newline='\n')
print('FAILED_LINK_BUILD_EVIDENCE_PRESERVED=2;FLASH_NOT_RUN')
