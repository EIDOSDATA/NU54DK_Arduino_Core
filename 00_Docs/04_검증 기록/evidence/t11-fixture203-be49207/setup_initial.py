"""! @brief Fixture 203 작업을 새 경로에 준비하고 이전 증거를 보존합니다. """
from pathlib import Path
import json

root = Path(__file__).resolve().parent
work = root / 't11-fixture203'
assert not work.exists()
assert not Path('C:/u3f').exists()
work.mkdir()
source = 'be4920757fd9faf2ea38721d2aa374246a259f29'
for name in ('runtime.py', 'prepare.py', 'run.py', 'postflight.py', 'progress.py'):
    value = (root / 't11-fixture202' / name).read_text(encoding='utf-8-sig')
    value = value.replace('1349e208073d0fd7d3b020a5e9facf771b371237', source)
    value = value.replace('C:\\u3e', 'C:\\u3f').replace('Fixture 202', 'Fixture 203')
    value = value.replace('fixture202-', 'fixture203-').replace("'202'", "'203'").replace(', 202)', ', 203)')
    if name == 'progress.py':
        value = value.replace('9084', '27252')
    (work / name).write_text(value, encoding='utf-8', newline='\n')
checkpoint = {
    'task': 'current-source T11 Fixture 203 only',
    'source': source,
    'board': 'fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3',
    'user_confirmation_recorded_at_utc': '2026-09-06T09:37:03+00:00',
    'user_statement': '203 테스트 시작해. 연결 했어.',
    'confirmation_context': 'User confirmed immediately preceding Fixture 203 instructions: A and B P2-12 SCK, P2-11 MOSI, P2-10 MISO, P2-9 CSN, P2-30 GND; power off for rewiring, both DAP UART disconnected and SWD connected, equal I/O voltage, own USB power, no joined power rails, external pullups or other outputs.',
    'confirmation_kind': 'User attestation; physical wiring is not instrumented',
    'swd_frequency_hz': 10000000,
    'build_root': 'C:/u3f',
    'scope': 'Exact clean-source pair build/preflight, one canonical full Fixture 203 cycle, evidence/documents/commit/main push; stop before Fixture 301 wiring',
    'status_at_recording': 'preparing',
}
(work / 'checkpoint.json').write_text(json.dumps(checkpoint, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
print(work)
