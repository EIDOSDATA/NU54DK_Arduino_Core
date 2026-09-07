"""! @brief 교정 source의 canonical nojumper target을 새 root에서 빌드합니다. """
import importlib.util
import os
from pathlib import Path
import subprocess
import sys

repo = Path('C:/Users/eidos/GitHub/NU54DK_Arduino_Core')
bundle = Path('C:/ncs/toolchains/dcbdc366a1')
work = Path(__file__).parent.with_name('t12-internal-nojumper-874658a')
spec = importlib.util.spec_from_file_location('nojumper_build_environment', repo / 'tools/nu54-builder/src/nu54_builder.py')
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
os.environ['PATH'] = os.pathsep.join([str(Path(os.environ['SystemRoot']) / 'System32'), os.environ['SystemRoot'], 'C:/Program Files/Git/cmd'])
environment = module.apply_toolchain_environment(bundle)
environment['PATH'] = str(work.parent / 'r00/bin') + os.pathsep + environment['PATH']
environment.update({'PYTHONUTF8': '1', 'PYTHONDONTWRITEBYTECODE': '1', 'NUCODE_NCS_ROOT': 'C:/ncs/v3.4.0', 'NUCODE_TOOLCHAIN_ROOT': str(bundle)})
for key in ('CC', 'CXX'):
    environment.pop(key, None)
assert not Path('C:/nj28').exists()
command = [str(bundle / 'opt/bin/python.exe'), '-B', str(repo / 'tools/ci/run_zephyr_build.py'),
           '--workspace', 'C:/ncs/v3.4.0', '--outdir', 'C:/nj28', '--suite', 'nucode.m25.nojumper_hil', '--jobs', '2']
with (work / 'target-build.log').open('xb') as log:
    result = subprocess.run(command, cwd=repo, env=environment, stdout=log, stderr=subprocess.STDOUT)
print('NOJUMPER_CORRECTED_BUILD_EXIT=' + str(result.returncode), flush=True)
raise SystemExit(result.returncode)
