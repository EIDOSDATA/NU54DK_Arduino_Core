"""! @brief 이전 원본을 보존하면서 이번 exact Fixture 102 입력에 맞춘 wrapper를 만듭니다. """
from pathlib import Path

work = Path(__file__).resolve().parent
previous = work.parent / 't11-fixture101'
for name in ('runtime.py', 'prepare.py', 'run.py', 'postflight.py', 'audit_results.py', 'publish_evidence.py', 'end_checks.ps1'):
    text = (previous / name).read_text(encoding='utf-8-sig')
    text = text.replace('154324ce7a865522374066ca957ebc98909c7c19', 'a49cc0dbc1ef8bf5f697106d873bdce55f5911df')
    text = text.replace('fixture101', 'fixture102').replace('Fixture 101', 'Fixture 102').replace('C:\\u3a', 'C:\\u3b')
    text = text.replace('t11-fixture102-154324c', 't11-fixture102-a49cc0d')
    if name in ('prepare.py', 'run.py'):
        text = text.replace('101', '102')
    if name == 'audit_results.py':
        text = text.replace("== 101", "== 102").replace("'fixture_id': 101", "'fixture_id': 102")
        text = text.replace('1644', '822').replace('1648', '826').replace('1620', '810').replace('1584', '792')
        text = text.replace('len(coverage) == 12', 'len(coverage) == 6')
        text = text.replace('== 24', '== 12').replace("'cts_deferred_rx': 12", "'cts_deferred_rx': 6").replace("'2': 12", "'2': 6")
    target = work / name
    assert not target.exists()
    target.write_text(text, encoding='utf-8', newline='\n')
print('FIXTURE102_WRAPPERS_PREPARED=7')
