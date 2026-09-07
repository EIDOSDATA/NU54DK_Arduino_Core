"""! @brief 새 PC의 고정 도구로 원본 gate 로그와 입력 식별자를 보존합니다. """
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

REPO = Path(r"C:\Users\eidos\GitHub\NU54DK_Arduino_Core")
WORK = Path(__file__).resolve().parent
SDK = Path(r"C:\ncs\toolchains\dcbdc366a1")
PYTHON = REPO / ".venv/Scripts/python.exe"
LLVM = Path(r"C:\Program Files\LLVM\bin")
MINGW = next(Path(os.environ["LOCALAPPDATA"]).glob("Microsoft/WinGet/Packages/BrechtSanders.WinLibs.MCF.UCRT_*/mingw64/bin"))

def run(name, command, environment):
    """! @brief shell 없이 실행하고 성공·실패를 모두 저장합니다. """
    start = datetime.datetime.now(datetime.timezone.utc).isoformat()
    logfile = WORK / (name + ".log")
    with logfile.open("xb") as stream:
        result = subprocess.run([str(v) for v in command], cwd=REPO, env=environment,
                                stdout=stream, stderr=subprocess.STDOUT, check=False)
    record = {"name": name, "command": [str(v) for v in command], "started_at": start,
              "finished_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "exit_code": result.returncode, "log_sha256": hashlib.sha256(logfile.read_bytes()).hexdigest()}
    (WORK / (name + ".json")).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(record), flush=True)
    return result.returncode

def host_environment():
    """! @brief Host 컴파일러·LLD와 고정 NCS의 CMake/Ninja만 자식 환경에 선택합니다. """
    env = dict(os.environ)
    env["PATH"] = os.pathsep.join(map(str, (PYTHON.parent, LLVM, SDK / "opt/bin", MINGW))) + os.pathsep + env["PATH"]
    env.update(CC=str(MINGW / "gcc.exe"), CXX=str(MINGW / "g++.exe"),
               NUCODE_HOST_CC_FLAGS='["-fuse-ld=lld"]', NUCODE_HOST_CXX_FLAGS='["-fuse-ld=lld"]',
               NUCODE_NCS_ROOT=r"C:\ncs\v3.4.0", NUCODE_TOOLCHAIN_ROOT=str(SDK), PYTHONUTF8="1")
    return env

if __name__ == "__main__":
    env = host_environment()
    prefix = sys.argv[1]
    for gate in sys.argv[2:]:
        if gate == "target":
            sys.path.insert(0, str(REPO / "tools/nu54-builder/src"))
            from nu54_builder_impl.environment import apply_toolchain_environment
            target_env = apply_toolchain_environment(SDK)
            target_env["PATH"] = os.pathsep.join(str(v) for v in (
                SDK / "mingw64/bin", SDK / "bin", SDK / "opt/bin", SDK / "opt/bin/Scripts",
                SDK / "opt/zephyr-sdk/gnu/arm-zephyr-eabi/bin", Path(r"C:\Program Files\Git\cmd"),
                Path(r"C:\Windows\System32"), Path(r"C:\Windows")))
            target_env["PYTHONUTF8"] = "1"
            run(prefix + "-target", (SDK / "opt/bin/python.exe", "-B", REPO / "tools/ci/run_zephyr_build.py",
                "--workspace", r"C:\ncs\v3.4.0", "--outdir", os.environ.get("V04_BUILD_OUT", r"C:\pcv04"), "--group", "v0.4.0",
                "--suite", "nucode.v04.pair_dut", "--suite", "nucode.v04.pair_peer", "--jobs", "2"), target_env)
        elif gate == "examples":
            run(prefix + "-examples", (PYTHON, "-B", REPO / "tools/ci/run_m12_gate.py", "examples",
                "--arduino-cli", r"C:\Program Files\Arduino CLI\arduino-cli.exe"), env)
        else:
            run(prefix + "-" + gate, (PYTHON, "-B", REPO / "tools/ci/run_m12_gate.py", gate), env)
