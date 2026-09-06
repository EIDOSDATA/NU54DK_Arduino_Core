"""! @brief 종료 후에 사용할 증거·검사 도구를 별도 작업 폴더에 준비합니다. """
from pathlib import Path

work = Path(__file__).resolve().parent
previous = work.parent / 't11-fixture202'
for name in ('publish_evidence.py', 'end_checks.ps1', 'stage_audit.py', 'finalize_software.py', 'record_final_docs.py'):
    text = (previous / name).read_text(encoding='utf-8-sig')
    text = text.replace('1349e208073d0fd7d3b020a5e9facf771b371237', 'be4920757fd9faf2ea38721d2aa374246a259f29')
    text = text.replace('fixture202', 'fixture203').replace('Fixture 202', 'Fixture 203').replace('Fixture_202', 'Fixture_203')
    text = text.replace('t11-fixture203-1349e20', 't11-fixture203-be49207').replace('71_T11_Fixture_203', '72_T11_Fixture_203')
    if name in ('finalize_software.py', 'record_final_docs.py'):
        text = text.replace('180', '181')
    if name == 'finalize_software.py':
        text = text.replace('## 다음: Fixture 203 SPI', '## 다음: Fixture 301 TWI').replace('71번 후속', '72번 후속')
    target = work / name
    assert not target.exists()
    target.write_text(text, encoding='utf-8', newline='\n')
print('FIXTURE203_COMPLETION_WRAPPERS_PREPARED=5')
