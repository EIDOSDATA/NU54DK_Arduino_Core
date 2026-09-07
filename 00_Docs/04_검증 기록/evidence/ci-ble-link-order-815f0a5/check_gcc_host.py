"""! @brief clean source의 전체 Host를 GNU 도구와 실제 Windows 짧은 TEMP 경로로 검증합니다. """
from pathlib import Path
import ctypes
import hashlib
import json
import os
import subprocess
import sys

work = Path(__file__).parent.resolve()
repo = Path('C:/Users/eidos/GitHub/NU54DK_Arduino_Core')
assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=repo)
environment = dict(os.environ)
environment.update(json.loads((work / 'host-874658a.json').read_text(encoding='utf-8'))['environment'])
gcc = Path('C:/NU54DEV/tools/WinLibs-16.1.0-UCRT/mingw64/bin')
buffer = ctypes.create_unicode_buffer(32768)
length = ctypes.windll.kernel32.GetShortPathNameW(str(work), buffer, len(buffer))
assert 0 < length < len(buffer) and Path(buffer.value).resolve() == work and Path(buffer.value) != work
environment.update(CC=str(gcc / 'gcc.exe'), CXX=str(gcc / 'g++.exe'), NUCODE_HOST_CC_FLAGS='[]',
                   NUCODE_HOST_CXX_FLAGS='[]', TEMP=buffer.value, TMP=buffer.value,
                   PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1')
environment.pop('PYTHONPATH', None)
command = [sys.executable, '-B', 'tools/ci/run_m12_gate.py', 'host']
source = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip()
log = work / 'host-gcc-final.log'
with log.open('xb') as output:
    result = subprocess.run(command, cwd=repo, env=environment, stdout=output, stderr=subprocess.STDOUT)
record = {'source': source, 'dirty': False, 'command': command, 'returncode': result.returncode,
          'log_sha256': hashlib.sha256(log.read_bytes()).hexdigest(),
          'short_temp': buffer.value, 'compiler': environment['CXX'],
          'gcc_version': subprocess.check_output([environment['CXX'], '--version'], text=True).splitlines()[0],
          'ld_version': subprocess.check_output([str(gcc / 'ld.exe'), '--version'], text=True).splitlines()[0]}
(work / 'host-gcc-final.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(record))
print(log.read_text(encoding='utf-8', errors='replace')[-2000:])
sys.exit(result.returncode)
