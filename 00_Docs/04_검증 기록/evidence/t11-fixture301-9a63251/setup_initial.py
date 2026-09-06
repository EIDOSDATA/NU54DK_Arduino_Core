"""! @brief 새 Fixture 301 작업 경로와 사용자 확인, 실행 도구를 준비합니다. """
from pathlib import Path
import json

root = Path(__file__).resolve().parent
work = root / 't11-fixture301'
assert not work.exists() and not Path('C:/u3g').exists()
work.mkdir()
source = '9a63251ed6f8b9916d8e49d8210414b21c5c7267'
for name in ('runtime.py', 'prepare.py', 'run.py', 'postflight.py', 'progress.py', 'publish_evidence.py', 'end_checks.ps1', 'stage_audit.py', 'record_final_docs.py'):
    text = (root / 't11-fixture203' / name).read_text(encoding='utf-8-sig')
    text = text.replace('be4920757fd9faf2ea38721d2aa374246a259f29', source)
    text = text.replace('C:\\u3f', 'C:\\u3g').replace('fixture203', 'fixture301').replace('Fixture 203', 'Fixture 301').replace('Fixture_203', 'Fixture_301')
    text = text.replace('t11-fixture301-be49207', 't11-fixture301-9a63251')
    text = text.replace('72_T11_Fixture_301_current_source_SPI', '73_T11_Fixture_301_current_source_TWI')
    if name in ('prepare.py', 'run.py'):
        text = text.replace(', 203)', ', 301)').replace("'203'", "'301'")
    if name == 'progress.py':
        text = text.replace('V04-SPI-', 'V04-TWI-').replace('27252', '1986')
    if name == 'record_final_docs.py':
        text = text.replace('181', '182')
    (work / name).write_text(text, encoding='utf-8', newline='\n')
checkpoint = {'task': 'current-source T11 Fixture 301 only', 'source': source, 'board': 'fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3', 'user_confirmation_recorded_at_utc': '2026-09-06T11:01:21+00:00', 'user_statement': '준비됐어. 301 테스트 시작해', 'confirmation_context': 'User confirmed immediately preceding Fixture 301 instructions: A P2-12 SDA to B P2-25, A P2-11 SCL to B P2-26, P2-30 common GND; old SPI MISO and CSN jumpers removed at both ends, both USB powers removed for rewiring, both DAP UART disconnected and SWD connected, equal I/O voltage and own USB power. Internal target TWIS pullups only; no joined power rails, external resistors or other outputs.', 'confirmation_kind': 'User attestation; physical wiring is not instrumented', 'swd_frequency_hz': 10000000, 'build_root': 'C:/u3g', 'scope': 'Exact pair build/preflight, one canonical full Fixture 301 cycle, original evidence/documents/commit/main push; stop before T12 Fixture 401 wiring', 'status_at_recording': 'preparing'}
(work / 'checkpoint.json').write_text(json.dumps(checkpoint, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
print(work)
