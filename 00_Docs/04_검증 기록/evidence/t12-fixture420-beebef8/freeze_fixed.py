"""! @brief 검증된 HIL 변경만 clean commit으로 고정하고 별도 빌드 폴더를 준비합니다. """
from pathlib import Path
import hashlib
import json
import re
import subprocess

ROOT = Path(r'C:\Users\eidos\GitHub\NU54DK_Arduino_Core')
WORK = Path(__file__).resolve().parent
FIXED = WORK.parent / 't12-fixture420-fixed'
assert json.loads((WORK / 'gate-host-fixed.json').read_text(encoding='utf-8'))['returncode'] == 0
assert 'CPP_STYLE_FILES=359; FAILED=0; WRITE=0' in (WORK / 'style-check.log').read_text(encoding='utf-8')
paths = ['00_Docs/TODO_v0.4.0.md', 'tests/host/test_v04_qdec.py', 'tests/zephyr/v04_pair_hil/src/signal_hil.cpp', 'tests/zephyr/v04_pair_hil/src/qdec_waveform.h']
observed = [line[3:] for line in subprocess.check_output(['git', 'status', '--porcelain', '-z'], cwd=ROOT).decode('utf-8').split('\0') if line]
assert set(observed) == set(paths), observed
todo = ROOT / paths[0]
value = todo.read_text(encoding='utf-8').replace('TODO-V04-001 / 3.11', 'TODO-V04-001 / 3.12')
rows = {
    '이번 요청의 실행 범위': '2026-09-06T16:05:26Z 사용자 420 결선 확인. exact beebef8 첫 항목 실패와 같은 결선 진단 보존. T10/T12·T14 HIL generator AB/극성/idle 준비 순서 수정, Host·정렬·pair build와 48-vector 재검증. R11 public core/SDK/board 변경 없음',
    '다음 착수 항목': '**420 수정 source의 exact pair build 후 같은 확인 결선으로 QDEC 48-vector 재검증**',
    '다음 구체적 행동': 'HIL generator만 수정한 clean source로 pair 두 role을 빌드하고 원래 420 확인 시각이 유효한 동안 SWD 10 MHz 실기. 430은 별도 결선 확인까지 대기',
    '다음 작업에 필요한 사용자 행동': '현재 420 결선 유지. 확인 유효기간이 지날 경우 실제 실행 전에 유지 여부를 재확인한다',
    '외부 결선 상태': '420 A P1.04↔B P1.14, A P1.06↔B P1.10, 공통 GND. 2026-09-06T16:05:26Z USB 분리 후 결선 변경·재연결 안내에 대한 사용자 확인. DAP UART 분리/SWD 연결·기존 SB/PMIC 유지. SWD 10 MHz',
}
for key, replacement in rows.items():
    value, count = re.subn(r'^\| ' + re.escape(key) + r' \|.*$', '| ' + key + ' | ' + replacement + ' |', value, flags=re.M)
    assert count == 1
todo.write_text(value, encoding='utf-8', newline='\n')
subprocess.run(['git', 'diff', '--check'], cwd=ROOT, check=True)
subprocess.run(['git', 'add', '--', *paths], cwd=ROOT, check=True)
subprocess.run(['git', 'commit', '-m', 'test(hil): correct QDEC waveform polarity and prepared idle'], cwd=ROOT, check=True)
assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT)
source = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
FIXED.mkdir(exist_ok=False)
(FIXED / 'source.txt').write_text(source + '\n', encoding='ascii')
for name in ('runtime.py', 'prepare.py', 'run.py', 'postflight.py', 'audit_results.py'):
    value = (WORK / name).read_text(encoding='utf-8').replace("BUILD = Path(r'C:\\u3r')", "BUILD = Path(r'C:\\u3s')")
    (FIXED / name).write_text(value, encoding='utf-8', newline='\n')
checkpoint = json.loads((WORK / 'checkpoint.json').read_text(encoding='utf-8'))
checkpoint.update(source=source, prior_failed_source='beebef829de94f92a3a0b6b8b0a6ed2447d3b560', confirmation_reused_without_timestamp_change=True)
(FIXED / 'checkpoint.json').write_text(json.dumps(checkpoint, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
(FIXED / 'source-files.json').write_text(json.dumps({path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in paths}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
print('FIXED_SOURCE=' + source)
