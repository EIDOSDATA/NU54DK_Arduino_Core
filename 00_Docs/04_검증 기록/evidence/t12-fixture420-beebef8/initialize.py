"""! @brief 확인된 QDEC 결선과 실제 clean source를 실행 체크포인트에 고정합니다. """
from pathlib import Path
import hashlib
import json
import subprocess

ROOT = Path(r'C:\Users\eidos\GitHub\NU54DK_Arduino_Core')
WORK = Path(__file__).resolve().parent
PREVIOUS = WORK.parent / 't12-fixture408'
SOURCE = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
BASELINE = '393e419f4c855037d4e6221c315f9be808a7d274'
assert SOURCE == 'beebef829de94f92a3a0b6b8b0a6ed2447d3b560'
assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT)
assert not (WORK / 'source.txt').exists() and not Path(r'C:\u3r').exists()
changes = [name for name in subprocess.check_output(['git', 'diff', '--name-only', '-z', BASELINE, SOURCE], cwd=ROOT).decode('utf-8').split('\0') if name]
assert all(path.startswith('00_Docs/') or path in ('README.md', 'tests/hil/nu54dk/README.md') for path in changes)
for name in ('runtime.py', 'prepare.py', 'run.py', 'postflight.py', 'collect_build.py'):
    text = (PREVIOUS / name).read_text(encoding='utf-8').replace('C:\\u3q', 'C:\\u3r').replace('r13/u3q-', 'r13/u3r-')
    if name in ('prepare.py', 'run.py'):
        text = text.replace('408', '420')
    if name == 'collect_build.py':
        text = text.replace('t12-fixture407-run/target-artifact-index.json', 't12-fixture408/target-artifact-index.json')
        text = text.replace('4a64c2562fdd5e9169faecf56b43043a0afec67c', '87b987d9ed50855e0134f2c637c00706572719a5')
    (WORK / name).write_text(text, encoding='utf-8', newline='\n')
(WORK / 'source.txt').write_text(SOURCE + '\n', encoding='ascii', newline='\n')
checkpoint = {'fixture_id': 420, 'source': SOURCE,
    'user_confirmation_recorded_at_utc': '2026-09-06T16:05:26+00:00',
    'confirmation_text': '연결 했어. 시작하자.',
    'wiring': 'A P1.04 P2-12 <-> B P1.14 P4-12; A P1.06 P2-10 <-> B P1.10 P4-8; common GND P2-30; previous A P1.14 removed',
    'confirmed_in_context': 'Both USB disconnected for rewiring, reconnected after; DAP UART disconnected, SWD connected; existing SB/PMIC unchanged; no additional signals or power rails',
    'signal_profile': 'B PWM20/21/22 -> A QDEC20/21, cycles 1/100, state interval 2000us, both directions, debounce off/on; 48 vectors',
    'swd_frequency_hz': 10000000,
    'scope': 'T10/T12 Fixture 420 physical execution, evidence/docs/commit/push; no Fixture 430 until separate wiring confirmation'}
(WORK / 'checkpoint.json').write_text(json.dumps(checkpoint, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
software = WORK.parent / 't12-fixture407-resume/software-validation.json'
payload = {'current_source': SOURCE, 'validated_software_source': BASELINE,
    'changed_paths': changes, 'all_changes_documentation_or_historical_evidence': True,
    'production_build_runner_host_test_fixture_changes': [],
    'prior_software_result': str(software), 'prior_software_result_sha256': hashlib.sha256(software.read_bytes()).hexdigest(),
    'prior_result': json.loads(software.read_text(encoding='utf-8')),
    'decision': 'Preserve full software validation under its original source; rebuild exact pair and execute confirmed QDEC fixture'}
(WORK / 'software-input-comparison.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
print('420_CONFIRMATION_RECORDED=2026-09-06T16:05:26Z;CODE_AND_TEST_DELTA=0;SOURCE=' + SOURCE)
