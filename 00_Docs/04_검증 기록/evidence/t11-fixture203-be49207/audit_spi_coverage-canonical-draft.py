"""! @brief 세 SPI route 결과를 각각의 exact source로 대조하고 합계를 기록합니다. """
from pathlib import Path
import hashlib
import json

work = Path(__file__).resolve().parent
repo = Path(r'C:\Users\eidos\GitHub\NU54DK_Arduino_Core')
records = []
for fixture, source, relative, count in (
    (201, '0f429e7ab9b5b8e24f4ff19e47abe60014975547', 't11-fixture201-0f429e7/results-audit.json', 18169),
    (202, '1349e208073d0fd7d3b020a5e9facf771b371237', 't11-fixture202-1349e20/results-audit.json', 9084),
    (203, 'be4920757fd9faf2ea38721d2aa374246a259f29', None, 27252),
):
    path = repo / '00_Docs/04_검증 기록/evidence' / relative if relative else work / 'results-audit.json'
    audit = json.loads(path.read_text(encoding='utf-8'))
    assert audit['fixture_id'] == fixture and audit['source'] == source and audit['status'] == 'passed'
    assert audit['functional_pass'] == count and audit['independent_plan_ids_match']
    journal_name = f'fixture{fixture}-attempt{1 if fixture == 201 else 2}.json.jsonl'
    journal_raw = (path.parent / journal_name).read_bytes()
    assert hashlib.sha256(journal_raw).hexdigest() == audit['sha256'][journal_name]
    journal = [json.loads(line) for line in journal_raw.decode('utf-8-sig').splitlines()]
    concurrent = [row for row in journal if '/spim00-twim22-concurrent' in row['id']]
    assert len(concurrent) == (1 if fixture == 201 else 0)
    assert all(row['status'] == 'passed' for row in concurrent)
    records.append({'fixture_id': fixture, 'source': source, 'audit_sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'functional_pass': count, 'normal_vectors': audit['normal_vectors'], 'recovery_data_pass': audit['recovery_data_pass'], 'expected_error_pass': audit['expected_error_pass'], 'concurrent_pass': len(concurrent), 'data_pass': audit['data_pass']})
totals = {key: sum(record[key] for record in records) for key in ('functional_pass', 'normal_vectors', 'recovery_data_pass', 'expected_error_pass', 'concurrent_pass', 'data_pass')}
assert totals == {'functional_pass': 54505, 'normal_vectors': 54432, 'recovery_data_pass': 36, 'expected_error_pass': 36, 'concurrent_pass': 1, 'data_pass': 54469}
result = {'status': 'passed', 'scope': 'Three route regressions with separate exact firmware identities; not one frozen-source campaign', 'records': records, 'totals': totals, 'current_source_t11_complete': False, 'remaining_t11_fixture': 301}
with (work / 'spi-coverage-audit.json').open('x', encoding='utf-8', newline='\n') as stream:
    stream.write(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
print(json.dumps(result))
