"""! @brief 일곱 current-source 통신 fixture의 원본 journal과 합계를 대조합니다. """
from pathlib import Path
import gzip
import hashlib
import json

work = Path(__file__).resolve().parent
base = Path(r'C:\Users\eidos\GitHub\NU54DK_Arduino_Core\00_Docs\04_검증 기록\evidence')
comparison = json.loads((work / 'build-input-comparison.json').read_text(encoding='utf-8'))
assert comparison['status'] == 'passed' and len(comparison['previous_fixtures']) == 6
records = []
for fixture, short, attempt, count in ((101, '154324c', 1, 1644), (102, 'a49cc0d', 1, 822), (103, '7aece93', 2, 2466), (201, '0f429e7', 1, 18169), (202, '1349e20', 2, 9084), (203, 'be49207', 2, 27252), (301, '9a63251', 1, 1986)):
    root = work if fixture == 301 else base / f't11-fixture{fixture}-{short}'
    audit_path = root / 'results-audit.json'
    audit = json.loads(audit_path.read_text(encoding='utf-8'))
    assert audit['status'] == 'passed' and audit['source'].startswith(short)
    assert audit['functional_pass'] == count and audit['functional_ids_unique'] and audit['journal_matches_final_json']
    name = f'fixture{fixture}-attempt{attempt}.json.jsonl'
    raw = (root / name).read_bytes() if fixture == 301 else gzip.decompress((root / (name + '.raw.gz')).read_bytes())
    assert hashlib.sha256(raw).hexdigest() == audit['sha256'][name]
    journal = [json.loads(line) for line in raw.decode('utf-8-sig').splitlines()]
    functional = [row for row in journal if row['status'] == 'passed' and row['id'].startswith(('V04-UARTE-', 'V04-SPI-', 'V04-TWI-'))]
    assert len(functional) == count and len({row['id'] for row in functional}) == count
    cleanup = [row for row in journal if row['id'] == 'V04-FIXTURE-CLEANUP']
    assert len(cleanup) == 2 and all(all(item.get('result') == [0] for item in row['results']) for row in cleanup)
    records.append({'fixture_id': fixture, 'source': audit['source'], 'functional_pass': count, 'cleanup_records': 2, 'audit_sha256': hashlib.sha256(audit_path.read_bytes()).hexdigest(), 'original_journal_sha256': hashlib.sha256(raw).hexdigest()})
totals = {'uart_functional_pass': sum(row['functional_pass'] for row in records[:3]), 'spi_functional_pass': sum(row['functional_pass'] for row in records[3:6]), 'twi_functional_pass': records[-1]['functional_pass'], 'functional_pass': sum(row['functional_pass'] for row in records), 'cleanup_records': 14}
assert totals == {'uart_functional_pass': 4932, 'spi_functional_pass': 54505, 'twi_functional_pass': 1986, 'functional_pass': 61423, 'cleanup_records': 14}
result = {'status': 'passed', 'scope': 'Approved single communication routes after R00-R13 with matching compiled inputs; exact embedded source identity preserved per fixture', 'records': records, 'totals': totals, 'current_source_t11_complete': True, 'next_physical_fixture': 401, 'm24_release_gate_promoted': False, 't12_t15_or_release_complete': False}
with (work / 't11-coverage-audit.json').open('x', encoding='utf-8', newline='\n') as stream:
    stream.write(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
print(json.dumps(result))
