"""! @brief prepare 실패 뒤 미확인 cleanup과 읽기 전용 해제를 구분 감사합니다. """
from pathlib import Path

work = Path(__file__).resolve().parent
source = (work / 'audit_results.py').read_text(encoding='utf-8')
before = "    assert row['results'] == [{'role': 1, 'result': [0]}, {'role': 2, 'result': [0]}]"
assert source.count(before) == 1
source = source.replace(before, "    assert [item['role'] for item in row['results']] == [1, 2]")
before = "'cleanup_pass': len(cleanups),"
assert source.count(before) == 1
source = source.replace(before, "'cleanup_pass': sum(all(item.get('result') == [0] for item in row['results']) for row in cleanups), 'cleanup_total': len(cleanups), 'cleanup_unproven': [row for row in cleanups if any(item.get('result') != [0] for item in row['results'])],")
exec(compile(source, str(work / 'audit_results.py'), 'exec'))
