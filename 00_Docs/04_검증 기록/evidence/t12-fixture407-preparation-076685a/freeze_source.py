"""! @brief Host 차단을 명시한 로컬 source를 고정하여 독립 target build를 준비합니다. """
from pathlib import Path
import json
import re
import subprocess

work = Path(__file__).resolve().parent
repo = Path(r'C:\Users\eidos\GitHub\NU54DK_Arduino_Core')
path = repo / '00_Docs/TODO_v0.4.0.md'
text = path.read_text(encoding='utf-8')
key = '이 TODO 작성 작업의 실행 중 시험'
text, count = re.subn(r'^\| ' + key + r' \|.*$', '| ' + key + ' | 407 준비: signal Python 판정 13개·fixture 12개·style 358·계약 45·Inventory·docs PASS. C++ Host는 Windows Smart App Control의 g++.exe 차단(WinError 4551)으로 미완료. 차단 log 보존, 보안 정책 변경 없음. 독립 exact pair target build를 진행하며 Host gate 통과 전 flash/HIL 금지 |', text, flags=re.M)
assert count == 1
path.write_text(text, encoding='utf-8', newline='\n')
for name in ('README.md', '05_리팩토링_진행_체크리스트.md'):
    path = repo / '00_Docs/01_아두이노 코어 설계/14_리팩토링' / name
    text = path.read_text(encoding='utf-8') + '\n407 준비 Host의 C++ 실행은 Windows Smart App Control이 기존 g++.exe를 차단해 미완료다. Python oracle·fixture·정렬·계약·Inventory·docs는 통과했다. 독립 target build를 진행하되 Host gate가 통과하기 전 407 flash/HIL은 실행하지 않는다.\n'
    path.write_text(text, encoding='utf-8', newline='\n')

def git(*args):
    return subprocess.check_output(['git', '-c', 'core.safecrlf=false', '-c', 'core.quotepath=false', *args], cwd=repo)

paths = [p for p in git('diff', '--name-only', '-z').decode('utf-8').split('\x00') if p]
assert len(paths) == 16 and all(p.startswith(('tests/', '00_Docs/')) for p in paths)
assert not git('ls-files', '--others', '--exclude-standard', '-z')
git('diff', '--check')
git('add', '--', *paths)
git('diff', '--cached', '--check')
log = git('commit', '-m', 'test(hil): prepare input-bias AIN6 fixture 407')
(work / 'source-commit.log').write_bytes(log)
source = git('rev-parse', 'HEAD').decode().strip()
(work / 'source.txt').write_text(source + '\n', encoding='ascii', newline='\n')
assert not git('status', '--porcelain')
print('EXACT_LOCAL_SOURCE=' + source + ';HOST_BLOCKED;HIL_NOT_RUN')
