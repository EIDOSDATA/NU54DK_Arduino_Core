"""! @brief 성공한 문서·계약·inventory log와 최종 문서의 근거를 등록합니다. """
from pathlib import Path
import hashlib
import json
import re

work = Path(__file__).resolve().parent
repo = Path(r'C:\Users\eidos\GitHub\NU54DK_Arduino_Core')
destination = repo / '00_Docs/04_검증 기록/evidence/t11-fixture202-1349e20'
checks = []
for gate in ('docs', 'contract', 'inventory'):
    name = f'gate-{gate}.log'
    content = (work / name).read_text(encoding='utf-8-sig').replace('\r\n', '\n')
    assert 'M12_GATE_PASS=' + gate in content
    if gate == 'docs':
        markdown_count = int(re.search(r'PASS: (\d+) files', content).group(1))
        assert markdown_count == 180
    elif gate == 'contract':
        assert 'Ran 45 tests' in content and '\nOK\n' in content
    else:
        assert 'gates:16;blockers:8' in content
    target = destination / name
    assert not target.exists()
    target.write_bytes(content.encode('utf-8'))
    checks.append({'gate': gate, 'command': 'python -B tools/ci/run_m12_gate.py ' + gate, 'status': 'passed', 'log': name, 'sha256': hashlib.sha256(target.read_bytes()).hexdigest()})
verification = {'scope': 'Documentation and evidence changes after Fixture 202, no production code changes', 'checks': checks, 'markdown_files': markdown_count, 'contract_tests': 45, 'readiness_blockers': 8}
target = destination / 'software-verification.json'
assert not target.exists()
target.write_text(json.dumps(verification, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
raw_count = len(json.loads((destination / 'raw-files.json').read_text(encoding='utf-8'))['files'])
record_path = repo / '00_Docs/04_검증 기록/71_T11_Fixture_202_current_source_SPI_회귀.md'
record = record_path.read_text(encoding='utf-8')
section = f'''## 문서와 증거 검증

활성 문서 9개에 결과와 다음 결선을 반영했다. Markdown UTF-8·내부 링크 180개, 계약 45개,
inventory 75개·Serial identity 23개·System capability 16개를 통과했다. Readiness는 필수 16개 중
blocker 8개를 유지한다. [software 검사 기록](evidence/t11-fixture202-1349e20/software-verification.json)에
canonical 명령과 log hash를 보존했다. 제품 코드 변경이 없어 이전 full Host·package·전체 target
결과는 해당 source의 역사 증거로 유지한다.

이번 실행·준비 입력 {raw_count}개를 UTF-8/LF 사본과 원본 byte gzip으로 보존하고 hash·복원 일치·
UID 비공개를 검사했다. 실제 시험 source와 최종 문서 commit을 구분하며 commit·main push와
checkout·board·SDK·작업 프로세스 종료 점검은 최종 작업 산출물에 기록한다.

'''
assert record.count('## 다음: Fixture 203 SPI') == 1
record_path.write_text(record.replace('## 다음: Fixture 203 SPI', section + '## 다음: Fixture 203 SPI'), encoding='utf-8', newline='\n')
todo_path = repo / '00_Docs/TODO_v0.4.0.md'
todo = todo_path.read_text(encoding='utf-8')
before = '이번 pair target 2/2 PASS. 문서·contract·inventory 결과는 71번 후속 검증에 기록.'
assert before in todo
todo_path.write_text(todo.replace(before, '이번 pair target 2/2, Markdown 180, contract 45, inventory 75·Serial 23·System 16 PASS; readiness blocker 8개 유지.'), encoding='utf-8', newline='\n')
print('SOFTWARE_EVIDENCE_REGISTERED=3; RAW_INPUTS=' + str(raw_count))
