"""! @brief 명시한 MinGW 배포본으로 현재 BLE 세 시험의 링크 결과를 기록합니다. """
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys

work = Path(__file__).parent
repo = Path('C:/Users/eidos/GitHub/NU54DK_Arduino_Core')
tool, label = Path(sys.argv[1]), sys.argv[2]
flags = ['-fuse-ld=lld'] if len(sys.argv) > 3 and sys.argv[3] == 'lld' else []
environment = dict(os.environ)
environment.update(CXX=str(tool / 'g++.exe'), CC=str(tool / 'gcc.exe'), NUCODE_HOST_CXX_FLAGS=json.dumps(flags),
                   NUCODE_HOST_CC_FLAGS=json.dumps(flags), PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1')
environment['PATH'] = str(tool) + ';C:/NU54DEV/tools/LLVM-22.1.8/bin;C:/ncs/toolchains/dcbdc366a1/opt/bin;' + environment['PATH']
command = [sys.executable, '-B', '-m', 'unittest', 'discover', '-v', '-s', 'tests/host', '-p', 'test_r12_ble_*.py']
result = subprocess.run(command, cwd=repo, env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
(work / (label + '.log')).write_bytes(result.stdout)
record = {'source': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip(),
          'dirty': bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=repo)),
          'command': command, 'compiler': environment['CXX'], 'flags': flags, 'returncode': result.returncode,
          'log_sha256': hashlib.sha256(result.stdout).hexdigest(),
          'gcc_version': subprocess.check_output([str(tool / 'g++.exe'), '--version'], text=True).splitlines()[0],
          'ld_version': subprocess.check_output([str(tool / 'ld.exe'), '--version'], text=True).splitlines()[0]}
(work / (label + '.json')).write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
print(json.dumps(record))
print(result.stdout.decode('utf-8', errors='replace')[-5000:])
