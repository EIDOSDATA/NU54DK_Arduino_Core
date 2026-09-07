"""! @brief Windows 8.3 TEMP를 사용해 원격 M27 fixture 실패와 resolve 교정을 재현합니다. """
from pathlib import Path
import ctypes
import hashlib
import json
import os
import subprocess
import sys

work = Path(__file__).parent.resolve()
repo = Path('C:/Users/eidos/GitHub/NU54DK_Arduino_Core')
buffer = ctypes.create_unicode_buffer(32768)
length = ctypes.windll.kernel32.GetShortPathNameW(str(work), buffer, len(buffer))
assert 0 < length < len(buffer)
short = buffer.value
assert Path(short).resolve() == work
assert Path(short) != work, 'Windows did not provide a distinct short alias; do not claim reproduction'
driver = work / 'm27_short_path_child.py'
driver.write_text('''from pathlib import Path
import subprocess
import sys
repo = Path('C:/Users/eidos/GitHub/NU54DK_Arduino_Core')
path = repo / 'tests/host/test_m27_package_examples.py'
if sys.argv[1] == 'before':
    source = subprocess.check_output(['git', 'show', 'f17e603:tests/host/test_m27_package_examples.py'], cwd=repo).decode('utf-8')
else:
    source = path.read_text(encoding='utf-8')
sys.argv = [str(path)]
globals()['__file__'] = str(path)
exec(compile(source, str(path), 'exec'))
''', encoding='utf-8')
records = []
for mode, expected in (('before', 1), ('after', 0)):
    path = work / ('m27-short-path-' + mode + '.log')
    with path.open('xb') as log:
        result = subprocess.run([sys.executable, '-B', str(driver), mode], cwd=repo,
                                env={**os.environ, 'TEMP': short, 'TMP': short, 'PYTHONUTF8': '1'},
                                stdout=log, stderr=subprocess.STDOUT)
    raw = path.read_bytes()
    assert result.returncode == expected, (mode, result.returncode)
    if mode == 'before':
        assert b'is not in the subpath of' in raw
    records.append({'mode': mode, 'returncode': result.returncode, 'log': str(path), 'log_sha256': hashlib.sha256(raw).hexdigest()})
payload = {'source_after': '874658a16db18b283ab7f1b2835111aaf34b42fd', 'source_before': 'f17e603fe101a2296398f160cb81a29a54f15671',
           'short_temp_path': short, 'resolved_temp_path': str(work), 'same_filesystem_directory': True,
           'status': 'before-failed-after-passed', 'runs': records, 'hardware_access': False}
(work / 'm27-short-path-reproduction.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print('M27_ACTUAL_WINDOWS_SHORT_PATH_BEFORE_FAIL_AFTER_5_PASS')
