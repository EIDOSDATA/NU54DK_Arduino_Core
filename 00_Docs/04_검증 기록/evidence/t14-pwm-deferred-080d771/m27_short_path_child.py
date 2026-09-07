from pathlib import Path
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
