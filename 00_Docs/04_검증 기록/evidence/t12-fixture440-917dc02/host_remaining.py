"""! @brief 보안 정책 변경 없이 명시한 LLVM Host 환경에서 canonical 검사를 기록합니다. """
from pathlib import Path
import datetime
import hashlib
import json
import os
import subprocess
import sys

ROOT = Path(r"C:\Users\eidos\GitHub\NU54DK_Arduino_Core")
WORK = Path(__file__).resolve().parent
HOST = Path(r"C:\NU54DEV\venv\host-3.12.10\Scripts\python.exe")
LLVM = Path(r"C:\NU54DEV\tools\LLVM-22.1.8\bin")
MINGW = Path(r"C:\NU54DEV\tools\WinLibs-16.1.0-UCRT\mingw64")
FLAGS = ["--target=x86_64-w64-windows-gnu", f"--sysroot={MINGW.as_posix()}", "-fuse-ld=lld"]
environment = dict(os.environ)
environment.update({"CXX": str(LLVM / "clang++.exe"), "CC": str(LLVM / "clang.exe"),
                    "NUCODE_HOST_CXX_FLAGS": json.dumps(FLAGS), "NUCODE_HOST_CC_FLAGS": json.dumps(FLAGS),
                    "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1",
                    "NUCODE_NCS_ROOT": r"C:\ncs\v3.4.0", "NUCODE_TOOLCHAIN_ROOT": r"C:\ncs\toolchains\dcbdc366a1"})
environment["PATH"] = ';'.join([str(HOST.parent), str(LLVM), str(MINGW / "bin"),
    r"C:\NU54DEV\tools\arduino-cli-1.5.1", r"C:\Program Files\Git\cmd",
    r"C:\Windows\System32\WindowsPowerShell\v1.0", r"C:\Windows\System32", r"C:\Windows"])

import re
prior = (WORK / 'host-all.log').read_text(encoding='utf-8')
attempted = set(re.findall(r'-p (test_[A-Za-z0-9_]+\.py)', prior))
attempted.add('test_v04_pdm_continuous.py')
commands = [(ROOT / 'tests/host', path.name) for path in sorted((ROOT / 'tests/host').glob('test_*.py'))
            if path.name not in attempted and path.name != 'test_m10_packaging.py']
commands += [(ROOT / 'tests/hil/nu54dk', name) for name in
             ('test_ac03_storage.py', 'test_m24_uarte_onboard.py', 'test_m24_twim_onboard.py',
              'test_m25_onboard.py', 'test_m26_onboard.py')]
rows = []
with (WORK / 'host-remaining.log').open('xb') as output:
    for directory, pattern in commands:
        command = [str(HOST), '-B', '-m', 'unittest', 'discover', '-v', '-s', str(directory), '-p', pattern]
        output.write(('PATTERN=' + pattern + '\n').encode())
        output.flush()
        result = subprocess.run(command, cwd=ROOT, env=environment, stdout=output, stderr=subprocess.STDOUT)
        rows.append({'pattern': pattern, 'directory': str(directory), 'returncode': result.returncode})
(WORK / 'host-remaining.json').write_text(json.dumps({'source': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
    'scope': 'Only previously unexecuted groups; original full gate remains blocked by WinError4551',
    'prior_attempts': 'host-all.log, host-retry.log, pdm-related.log, pdm-retry.log', 'groups': rows}, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'groups': len(rows), 'failed_groups': [row for row in rows if row['returncode']]}))
