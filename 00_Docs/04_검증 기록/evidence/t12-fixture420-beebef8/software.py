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
mode, label = sys.argv[1:3]
if mode == "subset":
    command = [str(HOST), "-B", "-m", "unittest", "discover", "-v", "-s", "tests/host", "-p", sys.argv[3]]
elif mode == "gate":
    command = [str(HOST), "-B", "tools/ci/run_m12_gate.py", sys.argv[3]]
else:
    raise ValueError(mode)
log = WORK / (label + ".log")
assert not log.exists(), log
record = {"started_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
          "command": command, "environment": {key: environment[key] for key in ("CC", "CXX", "NUCODE_HOST_CC_FLAGS", "NUCODE_HOST_CXX_FLAGS", "PATH")},
          "source": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
          "dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT)),
          "compiler_sha256": {name: hashlib.sha256((LLVM / name).read_bytes()).hexdigest() for name in ("clang.exe", "clang++.exe", "ld.lld.exe")}}
with log.open("wb") as output:
    result = subprocess.run(command, cwd=ROOT, env=environment, stdout=output, stderr=subprocess.STDOUT)
record.update(returncode=result.returncode, ended_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
              log_sha256=hashlib.sha256(log.read_bytes()).hexdigest())
(WORK / (label + ".json")).write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"log": str(log), "returncode": result.returncode}))
print(log.read_text(encoding="utf-8", errors="replace")[-6500:])
sys.exit(result.returncode)
