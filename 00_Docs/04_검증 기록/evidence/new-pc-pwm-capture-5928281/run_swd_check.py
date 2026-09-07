"""! @brief NCS 전용 DLL 환경에서 읽기 진단을 실행합니다. """
import os
import subprocess
import sys
from check_pc import REPO, WORK, SDK
sys.path.insert(0, str(REPO / 'tools/nu54-builder/src'))
from nu54_builder_impl.environment import apply_toolchain_environment
env = apply_toolchain_environment(SDK)
env['PATH'] = os.pathsep.join(str(SDK / p) for p in ('mingw64/bin', 'bin', 'opt/bin', 'opt/bin/Scripts')) + os.pathsep + r'C:\Windows\System32;C:\Windows'
env['PYTHONUTF8'] = '1'
result = subprocess.run([str(SDK / 'opt/bin/python.exe'), '-B', str(WORK / 'check_current_swd.py')], env=env)
sys.exit(result.returncode)
