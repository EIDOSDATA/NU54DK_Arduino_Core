"""! @brief GitHub runner가 선택하는 niXman 15.2 UCRT 배포본을 별도 경로에 검증·해제합니다. """
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import urllib.request

work = Path(__file__).parent
url = 'https://github.com/niXman/mingw-builds-binaries/releases/download/15.2.0-rt_v13-rev1/x86_64-15.2.0-release-posix-seh-ucrt-rt_v13-rev1.7z'
expected = '029bd02b5bce7c10fd9476165b3fe178239fe1838ad62516b5c3e0921bb283cf'
archive = work / 'nixman15-rev1.7z'
with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'NU54DK-verification'}), timeout=30) as response, archive.open('xb') as output:
    shutil.copyfileobj(response, output)
assert hashlib.sha256(archive.read_bytes()).hexdigest() == expected
destination = Path('C:/u4ci15n')
assert not destination.exists()
destination.mkdir()
destination = destination.resolve()
names = subprocess.check_output(['tar.exe', '-tf', str(archive)], text=True).splitlines()
for name in names:
    target = (destination / name).resolve()
    assert target.is_relative_to(destination) and target != destination
details = subprocess.check_output(['tar.exe', '-tvf', str(archive)], text=True)
assert ' -> ' not in details and ' link to ' not in details
subprocess.run(['tar.exe', '-xf', str(archive), '-C', str(destination)], check=True)
record = {'url': url, 'archive_sha256': expected, 'archive_bytes': archive.stat().st_size,
          'destination': str(destination), 'files': len(names), 'existing_toolchains_modified': False,
          'runner_install_script': 'https://raw.githubusercontent.com/actions/runner-images/win25-vs2026/20260824.214/images/windows/scripts/build/Install-Mingw64.ps1'}
(work / 'nixman15-reproduction-toolchain.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
print(json.dumps(record))
