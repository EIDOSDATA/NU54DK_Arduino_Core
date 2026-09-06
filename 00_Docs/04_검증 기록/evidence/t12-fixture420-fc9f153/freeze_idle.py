"""! @brief START 전 취소 실패를 보존하고 GPIO idle 수정 source를 고정합니다. """
from pathlib import Path
import json
import subprocess

ROOT = Path(r'C:\Users\eidos\GitHub\NU54DK_Arduino_Core')
WORK = Path(__file__).resolve().parent
FINAL = WORK.parent / 't12-fixture420-final'
assert 'CPP_STYLE_FILES=359; FAILED=0; WRITE=0' in (WORK / 'style-idle-check.log').read_text(encoding='utf-8')
assert json.loads((WORK / 'gate-signal-idle.json').read_text(encoding='utf-8'))['returncode'] == 0
todo = ROOT / '00_Docs/TODO_v0.4.0.md'
value = todo.read_text(encoding='utf-8')
value = value.replace('## 2. 현재 재개 체크포인트', '## 2. 현재 재개 체크포인트\n\n420 추가 교정: fc9f153은 정방향/역방향 48개를 통과했으나 START 전 취소에서 B PWM20 STOP timeout(status 730)을 발견했다. 420은 GPIO LOW를 저장·복원하는 준비 상태로 변경하고 PWM은 START에서만 실행한다. STOP timeout 상태도 후속 stopAll에서 재확인한다. 실패 원본과 48 PASS를 분리 보존하고 수정 source에서 48개 및 준비 취소 6개를 재검증한다. public PwmSequenceFabric start_via_task의 미시작 STOP 동작은 별도 T14 재현 이슈로 남긴다.\n', 1)
todo.write_text(value, encoding='utf-8', newline='\n')
paths = ['00_Docs/TODO_v0.4.0.md', 'tests/zephyr/v04_pair_hil/src/signal_hil.cpp']
changed = [entry[3:] for entry in subprocess.check_output(['git', 'status', '--porcelain', '-z'], cwd=ROOT).decode('utf-8').split('\0') if entry]
assert set(changed) == set(paths), changed
subprocess.run(['git', 'diff', '--check'], cwd=ROOT, check=True)
subprocess.run(['git', 'add', '--', *paths], cwd=ROOT, check=True)
subprocess.run(['git', 'commit', '-m', 'test(hil): make QDEC prepared cancellation restore idle pins'], cwd=ROOT, check=True)
assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT)
source = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
FINAL.mkdir(exist_ok=False)
(FINAL / 'source.txt').write_text(source + '\n', encoding='ascii')
for name in ('runtime.py', 'prepare.py', 'run.py', 'postflight.py', 'audit_results.py', 'prepared_cancel.py', 'collect_build.py', 'software.py'):
    value = (WORK / name).read_text(encoding='utf-8').replace('u3s', 'u3t')
    (FINAL / name).write_text(value, encoding='utf-8', newline='\n')
checkpoint = json.loads((WORK / 'checkpoint.json').read_text(encoding='utf-8'))
checkpoint.update(source=source, prior_functional_pass_cancel_failed_source='fc9f1536e2caf4efee387c1a69b3a4c9e24adf3b')
(FINAL / 'checkpoint.json').write_text(json.dumps(checkpoint, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
print('FINAL_SOURCE=' + source)
