"""! @brief 실제 Windows TEMP 짧은 별칭에서 R06 재현과 전체 Host를 기록합니다. """
from pathlib import Path
import ctypes
import hashlib
import json
import os
import subprocess
import sys

work = Path(__file__).parent.resolve()
repo = Path('C:/Users/eidos/GitHub/NU54DK_Arduino_Core')
environment = dict(os.environ)
environment.update(json.loads((work / 'host-874658a.json').read_text(encoding='utf-8'))['environment'])
buffer = ctypes.create_unicode_buffer(32768)
length = ctypes.windll.kernel32.GetShortPathNameW(str(work), buffer, len(buffer))
assert 0 < length < len(buffer)
short = buffer.value
assert Path(short).resolve() == work and Path(short) != work
environment.update(TEMP=short, TMP=short, PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1')
environment.pop('PYTHONPATH', None)
mode = sys.argv[1]
if mode == 'r06-before':
    child = """from pathlib import Path
import subprocess
import sys
repo = Path('C:/Users/eidos/GitHub/NU54DK_Arduino_Core')
path = repo / 'tests/host/test_r06_windows_recipe.py'
source = subprocess.check_output(['git', 'show', '1f050f4:tests/host/test_r06_windows_recipe.py'], cwd=repo).decode('utf-8')
sys.path.insert(0, str(path.parent))
sys.argv = [str(path)]
globals()['__file__'] = str(path)
exec(compile(source, str(path), 'exec'))
"""
    command = [sys.executable, '-B', '-c', child]
elif mode == 'r06-after':
    command = [sys.executable, '-B', '-m', 'unittest', 'discover', '-v', '-s', 'tests/host', '-p', 'test_r06_windows_recipe.py']
elif mode in ('host', 'host-clean'):
    command = [sys.executable, '-B', 'tools/ci/run_m12_gate.py', 'host']
else:
    raise ValueError(mode)
log = work / ('ci-short-temp-' + mode + '.log')
with log.open('xb') as output:
    result = subprocess.run(command, cwd=repo, env=environment, stdout=output, stderr=subprocess.STDOUT)
raw = log.read_bytes()
record = {'parent_source': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip(),
          'source_mode': mode, 'dirty': bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=repo)),
          'short_temp': short, 'resolved_temp': str(work), 'returncode': result.returncode,
          'command': command, 'log_sha256': hashlib.sha256(raw).hexdigest(),
          'test_source_sha256': {name: hashlib.sha256((repo / 'tests/host' / name).read_bytes()).hexdigest()
                                 for name in ('test_m14_core_contract.py', 'test_r06_windows_recipe.py')}}
(work / ('ci-short-temp-' + mode + '.json')).write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(raw.decode('utf-8', errors='replace')[-4500:])
if mode == 'r06-before':
    assert result.returncode == 1 and b'AssertionError:' in raw
else:
    assert result.returncode == 0
