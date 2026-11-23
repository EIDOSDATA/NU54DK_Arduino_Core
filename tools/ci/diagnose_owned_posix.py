"""! @brief 고정 C10의 macOS 정리 실패를 판정 변경 없이 제한된 진단으로 기록합니다. """
from argparse import ArgumentParser
from datetime import datetime, timezone
import errno
import importlib.util
import json
import os
from pathlib import Path
import platform
import signal
import subprocess
import sys
import time
import unittest
from unittest import mock

SOURCE = '4890f697ab80dfed3cff62bd42acc42b0f3e1a34'


def group_rows(pgid):
    """! @brief argv·환경·다른 그룹 출력 없이 이번 소유 PGID의 상태만 반환합니다. """
    try:
        result = subprocess.run(['/bin/ps', '-axo', 'pid=,ppid=,pgid=,uid=,stat='],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=3)
    except (OSError, subprocess.TimeoutExpired) as error:
        return dict(status='UNCONFIRMED', error_type=type(error).__name__)
    if result.returncode != 0:
        return dict(status='UNCONFIRMED', exit_code=result.returncode)
    rows = []
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) == 5 and fields[2].isdigit() and int(fields[2]) == pgid:
            rows.append(dict(pid=int(fields[0]), ppid=int(fields[1]), pgid=int(fields[2]),
                uid=int(fields[3]), state=fields[4]))
    return dict(status='OBSERVED_AFTER_SIGNAL', members=rows)


def main():
    """! @brief 원형 시험10회와 zombie-only 그룹1회를 구분하고 이전 FAIL을 대체하지 않습니다. """
    parser = ArgumentParser()
    parser.add_argument('--repository', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = args.repository.resolve()
    actual = subprocess.run(['git', '-C', str(root), 'rev-parse', 'HEAD'],
        capture_output=True, text=True, check=True).stdout.strip()
    if actual != SOURCE or sys.platform != 'darwin':
        raise ValueError('고정 C10 source와 실제 macOS 환경이 필요합니다.')
    args.output.mkdir(parents=True, exist_ok=False)
    spec = importlib.util.spec_from_file_location('diagnostic_original_test', root/'tests/host/test_host_owned_process.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    record = dict(kind='DIAGNOSTIC_ONLY_NOT_PRODUCT_PASS', source_revision=actual,
        observed_utc=datetime.now(timezone.utc).isoformat(), host=platform.platform(),
        python=sys.version, sdk_or_USB_actions=False, original_failure_preserved=True, cases=[])
    original_killpg = os.killpg
    events = []

    def observed_killpg(pgid, signum):
        """! @brief 원형 signal과 예외를 그대로 전달하고 오류 단계·errno만 추가 관측합니다. """
        event = dict(pgid=pgid, signal=int(signum), monotonic=time.monotonic())
        try:
            result = original_killpg(pgid, signum)
        except OSError as error:
            event.update(error_type=type(error).__name__, errno=error.errno,
                group_after_error=group_rows(pgid))
            events.append(event)
            raise
        events.append(event)
        return result

    for number in range(10):
        events = []
        case = module.OwnedProcessTests('test_normal_leader_exit_also_cleans_a_remaining_grandchild')
        result = unittest.TestResult()
        with mock.patch.object(module.M.os, 'killpg', side_effect=observed_killpg):
            case.run(result)
        record['cases'].append(dict(number=number, test=case.id(), success=result.wasSuccessful(),
            errors=[detail for _, detail in result.errors], failures=[detail for _, detail in result.failures],
            signal_events=events))
        with (args.output/f'original-case-{number:02d}.json').open('x', encoding='utf-8') as stream:
            json.dump(record['cases'][-1], stream, indent=2)

    #! @brief 자체 종료한 시험용 leader를 회수하기 전의 zombie-only 경계를 한 번 관측합니다.
    zombie = subprocess.Popen([sys.executable, '-I', '-B', '-c', 'raise SystemExit(0)'],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True)
    boundary = dict(pgid=zombie.pid, status='ZOMBIE_NOT_OBSERVED')
    try:
        deadline = time.monotonic()+3
        while time.monotonic() < deadline:
            observed = group_rows(zombie.pid)
            members = observed.get('members', [])
            if members and all(row['state'].startswith('Z') for row in members):
                boundary.update(status='ZOMBIE_ONLY_OBSERVED', before=observed)
                try:
                    original_killpg(zombie.pid, signal.SIGKILL)
                except OSError as error:
                    boundary.update(error_type=type(error).__name__, errno=error.errno,
                        EPERM=error.errno == errno.EPERM)
                else:
                    boundary['signal_returned_success'] = True
                break
            time.sleep(0.01)
    finally:
        try:
            zombie.wait(timeout=5)
        except subprocess.TimeoutExpired:
            zombie.kill()
            zombie.wait(timeout=5)
        boundary['leader_reaped'] = zombie.returncode is not None
        boundary['after_reap'] = group_rows(zombie.pid)
    record['controlled_zombie_boundary'] = boundary
    record['diagnostic_failures'] = sum(not row['success'] for row in record['cases'])
    record['finished_utc'] = datetime.now(timezone.utc).isoformat()
    with (args.output/'diagnostic.json').open('x', encoding='utf-8') as stream:
        json.dump(record, stream, indent=2)
    print(json.dumps(dict(status=record['kind'], original_cases=10,
        diagnostic_failures=record['diagnostic_failures'], zombie_boundary=boundary)))


if __name__ == '__main__':
    main()
