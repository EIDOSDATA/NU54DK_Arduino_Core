"""! @brief 이전 증거를 보존하고 Fixture 202의 exact 실행 입력을 준비합니다. """
from pathlib import Path

work = Path(__file__).resolve().parent
previous = work.parent / 't11-fixture201'
assert not Path('C:/u3e').exists()
for name in ('runtime.py', 'prepare.py', 'run.py', 'postflight.py', 'publish_evidence.py', 'end_checks.ps1', 'progress.py', 'stage_audit.py', 'finalize_software.py', 'record_final_docs.py'):
    text = (previous / name).read_text(encoding='utf-8-sig')
    text = text.replace('0f429e7ab9b5b8e24f4ff19e47abe60014975547', '1349e208073d0fd7d3b020a5e9facf771b371237')
    text = text.replace('fixture201', 'fixture202').replace('Fixture 201', 'Fixture 202').replace('Fixture_201', 'Fixture_202').replace('C:\\u3d', 'C:\\u3e')
    text = text.replace('t11-fixture202-0f429e7', 't11-fixture202-1349e20').replace('70_T11_Fixture_202', '71_T11_Fixture_202')
    if name in ('prepare.py', 'run.py'):
        text = text.replace(', 201)', ', 202)').replace("'201'", "'202'")
    if name == 'progress.py':
        text = text.replace('18169', '9084')
    if name in ('finalize_software.py', 'record_final_docs.py'):
        text = text.replace('179', '180')
    if name == 'finalize_software.py':
        text = text.replace('## 다음: Fixture 202 SPI', '## 다음: Fixture 203 SPI').replace('70번 후속', '71번 후속')
    target = work / name
    assert not target.exists()
    target.write_text(text, encoding='utf-8', newline='\n')
print('FIXTURE202_WRAPPERS_PREPARED=10')
