"""! @brief M14의 단독 module 실행과 전체 Host의 discovery 실행을 같은 컴파일러로 대조합니다. """
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys

work = Path(__file__).parent
repo = Path('C:/Users/eidos/GitHub/NU54DK_Arduino_Core')
previous = json.loads((work / 'host-874658a.json').read_text(encoding='utf-8'))
environment = dict(os.environ)
environment.update(previous['environment'])
environment.update(PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1')
environment.pop('PYTHONPATH', None)
commands = {
    'module': [sys.executable, '-B', '-m', 'unittest', '-v', 'tests.host.test_m14_core_contract'],
    'discovery': [sys.executable, '-B', '-m', 'unittest', 'discover', '-v', '-s', 'tests/host', '-p', 'test_m14_core_contract.py'],
}
results = []
for mode, command in commands.items():
    result = subprocess.run(command, cwd=repo, env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    log = work / ('m14-' + mode + '-after.log')
    log.write_bytes(result.stdout)
    results.append({'mode': mode, 'command': command, 'returncode': result.returncode,
                    'log_sha256': hashlib.sha256(result.stdout).hexdigest()})
    print(result.stdout.decode('utf-8', errors='replace')[-1500:])
record = {'parent_source': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip(),
          'test_source_sha256': hashlib.sha256((repo / 'tests/host/test_m14_core_contract.py').read_bytes()).hexdigest(),
          'PYTHONPATH_removed': True, 'results': results}
(work / 'm14-entrypoints.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
sys.exit(int(any(row['returncode'] for row in results)))
