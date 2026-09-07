"""! @brief 원격 runner와 같은 계열의 MinGW 15.2/Binutils 2.46을 격리 경로에 검증·해제합니다. """
from pathlib import Path
import hashlib
import json
import shutil
import urllib.request
import zipfile

work = Path(__file__).parent
url = 'https://github.com/brechtsanders/winlibs_mingw/releases/download/15.2.0posix-14.0.0-ucrt-r7/winlibs-x86_64-posix-seh-gcc-15.2.0-mingw-w64ucrt-14.0.0-r7.zip'
expected = 'cb2fbad6162540cdf5e1facdce08d4dac359e8cf64f7f696a99274291763b815'
archive = work / 'mingw15-r7.zip'
with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'NU54DK-verification'}), timeout=30) as response, archive.open('xb') as output:
    shutil.copyfileobj(response, output)
assert hashlib.sha256(archive.read_bytes()).hexdigest() == expected
destination = Path('C:/u4ci15')
assert not destination.exists()
destination.mkdir()
destination = destination.resolve()
with zipfile.ZipFile(archive) as source:
    for entry in source.infolist():
        target = (destination / entry.filename).resolve()
        assert target.is_relative_to(destination) and target != destination
        assert (entry.external_attr >> 16) & 0o170000 != 0o120000
    source.extractall(destination)
record = {'url': url, 'archive_sha256': expected, 'archive_bytes': archive.stat().st_size,
          'destination': str(destination), 'existing_toolchains_modified': False,
          'reference_image': 'win25-vs2026/20260824.214; MinGW15.*, UCRT, Binutils2.46'}
(work / 'mingw15-reproduction-toolchain.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
print(json.dumps(record))
