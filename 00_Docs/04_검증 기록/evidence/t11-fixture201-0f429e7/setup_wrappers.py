"""! @brief 이전 증거를 보존하고 Fixture 201 전용 실행 입력을 만듭니다. """
from pathlib import Path

work = Path(__file__).resolve().parent
previous = work.parent / 't11-fixture102'
assert not Path('C:/u3d').exists()
for name in ('runtime.py', 'prepare.py', 'run.py', 'postflight.py', 'publish_evidence.py', 'end_checks.ps1'):
    text = (previous / name).read_text(encoding='utf-8-sig')
    text = text.replace('a49cc0dbc1ef8bf5f697106d873bdce55f5911df', '0f429e7ab9b5b8e24f4ff19e47abe60014975547')
    text = text.replace('fixture102', 'fixture201').replace('Fixture 102', 'Fixture 201').replace('C:\\u3b', 'C:\\u3d')
    text = text.replace('t11-fixture201-a49cc0d', 't11-fixture201-0f429e7')
    if name in ('prepare.py', 'run.py'):
        text = text.replace('102', '201')
    target = work / name
    assert not target.exists()
    target.write_text(text, encoding='utf-8', newline='\n')
print('FIXTURE201_WRAPPERS_PREPARED=6')
