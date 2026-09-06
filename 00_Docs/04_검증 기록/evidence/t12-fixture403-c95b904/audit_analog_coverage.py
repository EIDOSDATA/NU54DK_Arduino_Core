"""! @brief 이전 401/402 원본 gzip과 현재 403의 계획을 대조합니다. """
from pathlib import Path
import gzip
import hashlib
import itertools
import json

work = Path(__file__).resolve().parent
repo = Path(r'C:\Users\eidos\GitHub\NU54DK_Arduino_Core')
records = []
sources = [(401, 'a12e444cfb5ef47471c0e0d436f082acfd200c19'), (402, 'ff483a1bbd2a7f275b2c59126ef0e9af09211872'), (403, 'c95b9049a62e7c911e4b67104a8f36391ab7e168')]
for number, source in sources:
    root = work if number == 403 else repo / f'00_Docs/04_검증 기록/evidence/t12-fixture{number}-{source[:7]}'
    name = f'fixture{number}-attempt1.json.jsonl'
    if number != 403:
        manifest = json.loads((root / 'raw-files.json').read_text(encoding='utf-8'))
        record = next(item for item in manifest['files'] if item['name'] == name)
        raw = gzip.decompress((root / record['original_archive']).read_bytes())
        assert hashlib.sha256(raw).hexdigest() == record['original_sha256']
    else:
        raw = (root / name).read_bytes()
    audit = json.loads((root / 'results-audit.json').read_text(encoding='utf-8'))
    assert audit['status'] == 'passed' and audit['source'] == source and audit['fixture_id'] == number
    assert hashlib.sha256(raw).hexdigest() == audit['hashes'][name]
    rows = [json.loads(line) for line in raw.decode('utf-8-sig').splitlines()]
    functional = [row for row in rows if row['id'].startswith('V04-ANALOG-SIGNAL/')]
    expected = [f'V04-ANALOG-SIGNAL/{number}/2/{vector}/repeat-1' for vector in itertools.product((20,21,22), (32,256), (1021,), (512,), range(4), (1,2))]
    assert [row['id'] for row in functional] == expected and len(set(expected)) == 48
    cleanups = [row for row in rows if row['id'] == 'V04-SIGNAL-CLEANUP/repeat-1']
    assert len(cleanups) == 48 and all(row['results'] == [{'role': 1, 'result': [0]}, {'role': 2, 'result': [0]}] for row in cleanups)
    records.append({'fixture_id': number, 'source': source, 'functional': 48, 'cleanup': 48, 'samples_read': sum(row['receiver_status'][5] for row in functional), 'original_journal_sha256': hashlib.sha256(raw).hexdigest()})
output = {'status': 'passed', 'scope': 'T12 analog partial coverage; distinct exact images preserved', 'fixtures': records, 'functional_total': 144, 'cleanup_total': 144, 'samples_total': sum(row['samples_read'] for row in records), 't12_complete': False, 'remaining_fixtures': [404,408,420,430,440]}
(work / 'analog-coverage-audit.json').write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
print(json.dumps(output))
