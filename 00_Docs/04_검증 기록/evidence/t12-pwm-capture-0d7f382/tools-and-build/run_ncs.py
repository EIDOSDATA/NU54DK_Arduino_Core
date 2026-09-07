"""! @brief 임시 진단·사전 점검 스크립트에 고정 NCS 자식 환경을 적용합니다. """
import os
import subprocess
import sys
from check_pc import REPO, WORK, SDK
sys.path.insert(0, str(REPO / 'tools/nu54-builder/src'))
from nu54_builder_impl.environment import apply_toolchain_environment
env = apply_toolchain_environment(SDK)
env['PATH'] = os.pathsep.join(str(SDK / p) for p in ('mingw64/bin', 'bin', 'opt/bin', 'opt/bin/Scripts')) + os.pathsep + r'C:\Program Files\Git\cmd;C:\Windows\System32;C:\Windows'
env['PYTHONUTF8'] = '1'
script = (WORK / sys.argv[1]).resolve()
assert script.parent == WORK and script.suffix == '.py'
sys.exit(subprocess.run([str(SDK / 'opt/bin/python.exe'), '-B', str(script), *sys.argv[2:]], env=env).returncode)
