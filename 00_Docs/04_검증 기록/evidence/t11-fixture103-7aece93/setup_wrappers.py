"""! @brief 원본을 보존하면서 exact Fixture 103용 실행·감사 wrapper를 준비합니다. """
from pathlib import Path

work = Path(__file__).resolve().parent
previous = work.parent / 't11-fixture102'
for name in ('runtime.py', 'prepare.py', 'run.py', 'postflight.py', 'audit_results.py', 'publish_evidence.py', 'end_checks.ps1', 'stage_audit.py'):
    text = (previous / name).read_text(encoding='utf-8-sig')
    text = text.replace('a49cc0dbc1ef8bf5f697106d873bdce55f5911df', '7aece93395f0d74272816894a18c2c5e3f1a2abe')
    text = text.replace('fixture102', 'fixture103').replace('Fixture 102', 'Fixture 103').replace('C:\\u3b', 'C:\\u3c')
    text = text.replace('t11-fixture103-a49cc0d', 't11-fixture103-7aece93')
    text = text.replace('68_T11_Fixture_102_current_source_UART_회귀.md', '69_T11_Fixture_103_current_source_UART_회귀.md')
    if name in ('prepare.py', 'run.py'):
        text = text.replace('102', '103')
    if name == 'audit_results.py':
        text = text.replace('== 102', '== 103').replace("'fixture_id': 102", "'fixture_id': 103")
        text = text.replace('822', '2466').replace('826', '2470').replace('810', '2430').replace('792', '2376')
        text = text.replace('len(coverage) == 6', 'len(coverage) == 18')
        text = text.replace('== 12', '== 36').replace("'cts_deferred_rx': 6", "'cts_deferred_rx': 18").replace("'2': 6", "'2': 18")
    target = work / name
    assert not target.exists()
    target.write_text(text, encoding='utf-8', newline='\n')
print('FIXTURE103_WRAPPERS_PREPARED=8')
