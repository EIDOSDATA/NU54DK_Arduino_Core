"""! @brief 새 PC의 실제 도구와 원격 인계 CI를 읽기 전용으로 기록합니다. """
import datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess

from check_pc import REPO, WORK, SDK, PYTHON, LLVM, MINGW, host_environment

def execute(command):
    """! @brief 선택된 명령의 종료 코드와 원문만 보존합니다. """
    result = subprocess.run([str(v) for v in command], cwd=REPO, env=host_environment(),
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return {"command": [str(v) for v in command], "exit_code": result.returncode,
            "output": result.stdout.decode("utf-8", errors="replace")}

tools = [(PYTHON, '--version'), (SDK / 'opt/bin/python.exe', '--version'),
         (MINGW / 'gcc.exe', '--version'), (LLVM / 'ld.lld.exe', '--version'),
         (LLVM / 'clang-format.exe', '--version'), (SDK / 'opt/bin/cmake.exe', '--version'),
         (SDK / 'opt/bin/ninja.exe', '--version'),
         (Path(r'C:\Program Files\Arduino CLI\arduino-cli.exe'), 'version')]
record = {"observed_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
          "source_revision": execute(('git', 'rev-parse', 'HEAD')),
          "initial_revision": 'f42bda55f7b45f7af0a347ecf5f1f516bb34eb6a',
          "initial_worktree_clean": True, "tools": [execute(v) for v in tools],
          "tool_sha256": {str(cmd[0]): hashlib.sha256(cmd[0].read_bytes()).hexdigest() for cmd in tools},
          "host_compiler_flags": ['-fuse-ld=lld'], "security_policy_changed": False,
          "usb": json.loads((WORK / 'new-pc-usb-enumeration.json').read_text(encoding='utf-8-sig')),
          "swd_access": False, "flash": False, "external_wiring_executed": False}
record['git'] = [execute(args) for args in (
    ('git', 'status', '--porcelain'), ('git', 'submodule', 'status', '--recursive'),
    ('git', '-C', r'C:\ncs\v3.4.0\nrf', 'rev-parse', 'HEAD'),
    ('git', '-C', r'C:\ncs\v3.4.0\zephyr', 'rev-parse', 'HEAD'))]
record['prerequisite_script'] = execute(('powershell.exe', '-NoLogo', '-NoProfile', '-File',
    REPO / 'tools/nu54-prerequisites/verify-nordic.ps1', '-PlatformRoot', REPO,
    '-NcsRoot', r'C:\ncs', '-Json'))
(WORK / 'new-pc-environment.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
for run_id, name in ((34096227297, 'build'), (34096227435, 'software')):
    item = execute(('gh', 'run', 'view', str(run_id), '--repo', 'EIDOSDATA/NU54DK_Arduino_Core',
                    '--json', 'jobs,status,conclusion,url,headSha'))
    assert item['exit_code'] == 0, item
    data = json.loads(item['output'])
    data['observed_at_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    (WORK / ('handoff-ci-' + name + '.json')).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(name, data['status'], data['conclusion'], [(j['name'], j['conclusion']) for j in data['jobs']])
