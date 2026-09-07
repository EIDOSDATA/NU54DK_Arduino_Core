"""! @brief 실제 GNU와 LLVM으로 BLE 기본·대체 weak 구현의 수명주기를 대조합니다. """
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys

work = Path(__file__).parent
repo = Path('C:/Users/eidos/GitHub/NU54DK_Arduino_Core')
mode = sys.argv[1]
environment = dict(os.environ)
environment.update(json.loads((work / 'host-874658a.json').read_text(encoding='utf-8'))['environment'])
environment.update(PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1')
if mode == 'gcc':
    root = Path('C:/NU54DEV/tools/WinLibs-16.1.0-UCRT/mingw64/bin')
    environment.update(CXX=str(root / 'g++.exe'), CC=str(root / 'gcc.exe'),
                       NUCODE_HOST_CXX_FLAGS='[]', NUCODE_HOST_CC_FLAGS='[]')
elif mode != 'llvm':
    raise ValueError(mode)
command = [sys.executable, '-B', '-m', 'unittest', 'discover', '-v', '-s', 'tests/host', '-p', 'test_r12_ble_*.py']
result = subprocess.run(command, cwd=repo, env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
log = work / ('r12-link-order-' + mode + '.log')
log.write_bytes(result.stdout)
record = {'compiler': environment['CXX'], 'command': command, 'returncode': result.returncode,
          'log_sha256': hashlib.sha256(result.stdout).hexdigest(),
          'parent_source': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip(),
          'source_sha256': {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in (repo / 'tests/host').glob('test_r12_ble_*.py')}}
(work / ('r12-link-order-' + mode + '.json')).write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(result.stdout.decode('utf-8', errors='replace')[-4000:])
sys.exit(result.returncode)
