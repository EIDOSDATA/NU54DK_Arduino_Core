"""! @brief 승인 범위의 문서·증거만 stage하고 Git에 저장될 원본 byte/hash를 검사합니다. """
from pathlib import Path
import gzip
import hashlib
import json
import subprocess

repo = Path(r'C:\Users\eidos\GitHub\NU54DK_Arduino_Core')
work = Path(__file__).resolve().parent
destination = '00_Docs/04_검증 기록/evidence/t11-fixture203-be49207'
documents = ['README.md', '00_Docs/README.md', '00_Docs/TODO_v0.4.0.md', '00_Docs/01_아두이노 코어 설계/02_구현_로드맵.md', '00_Docs/01_아두이노 코어 설계/14_리팩토링/README.md', '00_Docs/01_아두이노 코어 설계/14_리팩토링/05_리팩토링_진행_체크리스트.md', '00_Docs/04_검증 기록/README.md', '00_Docs/04_검증 기록/72_T11_Fixture_203_current_source_SPI_회귀.md', 'tests/hil/nu54dk/README.md']

def git(*arguments):
    result = subprocess.run(['git', '-c', 'core.quotepath=false', *arguments], cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode:
        raise RuntimeError(result.stderr.decode('utf-8', 'replace'))
    return result.stdout

assert git('rev-parse', 'HEAD').decode().strip() == 'be4920757fd9faf2ea38721d2aa374246a259f29'
git('add', '--', *documents, destination)
paths = [p for p in git('diff', '--cached', '--name-only', '-z').decode('utf-8').split('\x00') if p]
assert len(paths) >= 63, len(paths)
assert all(p in documents or p.startswith(destination + '/') for p in paths)
assert git('diff', '--name-only', '-z') == b'', 'Unstaged tracked changes remain'
assert git('ls-files', '--others', '--exclude-standard', '-z') == b'', 'Unexpected untracked files remain'
git('diff', '--cached', '--check')
manifest = json.loads(git('show', ':' + destination + '/raw-files.json'))
assert len(paths) == len(documents) + 2 * len(manifest['files']) + 7
for record in manifest['files']:
    canonical = git('show', ':' + destination + '/' + record['name'])
    raw = gzip.decompress(git('show', ':' + destination + '/' + record['original_archive']))
    assert hashlib.sha256(canonical).hexdigest() == record['normalized_sha256']
    assert hashlib.sha256(raw).hexdigest() == record['original_sha256']
    assert raw == (work / record['name']).read_bytes()
    assert canonical == raw.decode('utf-8-sig').replace('\r\n', '\n').encode('utf-8')
software = json.loads(git('show', ':' + destination + '/software-verification.json'))
for record in software['checks']:
    assert hashlib.sha256(git('show', ':' + destination + '/' + record['log'])).hexdigest() == record['sha256']
result = {'status': 'passed', 'source': 'be4920757fd9faf2ea38721d2aa374246a259f29', 'staged_files': len(paths), 'documents': len(documents), 'evidence_files': len(paths) - len(documents), 'raw_inputs_roundtrip': len(manifest['files']), 'software_log_hashes': len(software['checks']), 'product_code_changed': False, 'unstaged_changes': False, 'unexpected_untracked_files': False}
(work / 'staged-evidence-audit.json').write_bytes((json.dumps(result, indent=2) + '\n').encode('utf-8'))
(work / 'changed-files.txt').write_bytes(('\n'.join(paths) + '\n').encode('utf-8'))
print(json.dumps(result))
