"""! @brief 실제 검사 결과를 적은 최종 문서의 추가 링크 검사 log를 보존합니다. """
from pathlib import Path
import hashlib
import json

work = Path(__file__).resolve().parent
destination = Path(r'C:\Users\eidos\GitHub\NU54DK_Arduino_Core\00_Docs\04_검증 기록\evidence\t11-fixture203-be49207')
name = 'gate-docs-final.log'
content = (work / name).read_text(encoding='utf-8-sig').replace('\r\n', '\n')
assert 'M12_GATE_PASS=docs' in content and 'PASS: 181 files' in content
target = destination / name
assert not target.exists()
target.write_bytes(content.encode('utf-8'))
manifest = destination / 'software-verification.json'
verification = json.loads(manifest.read_text(encoding='utf-8'))
assert len(verification['checks']) == 3
verification['checks'].append({'gate': 'docs-final', 'command': 'python -B tools/ci/run_m12_gate.py docs', 'status': 'passed', 'reason': 'Final result paragraphs and evidence links added after initial gates', 'log': name, 'sha256': hashlib.sha256(target.read_bytes()).hexdigest()})
manifest.write_text(json.dumps(verification, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
print('FINAL_DOCUMENTATION_LOG_REGISTERED')
