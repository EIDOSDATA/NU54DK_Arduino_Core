"""! @brief 제품 SDK·USB 대신 실제 Python 자식과 손자 process로 소유권 정리를 검사합니다. """
import importlib.util
from contextlib import ExitStack
import errno
import _thread
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('host_owned_process',ROOT/'tools/nu54-builder/src/nu54_builder_impl/owned_process.py')
M = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = M
spec.loader.exec_module(M)


class OwnedProcessTests(unittest.TestCase):
    """! @brief 모든 process는 시험용 Python이며 최대10초 안에 자체 종료합니다. """
    def setUp(self):
        """! @brief 새 D 폴더와 명시한 UTF-8 환경만 사용합니다. """
        temporary = tempfile.TemporaryDirectory(prefix='nu54-owned-')
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.environment = dict(os.environ,PYTHONIOENCODING='utf-8',PYTHONDONTWRITEBYTECODE='1')

    def run_python(self, code, *arguments, timeout=5):
        """! @brief 실제 child를 shell 없이 실행합니다. """
        return M.run_owned([sys.executable,'-I','-X','utf8','-B','-c',code,*arguments],cwd=self.base,
            environment=self.environment,capture_directory=self.base,timeout=timeout)

    def pulse_code(self, path):
        """! @brief 자식이 살아 있으면 파일 크기가 늘어나는 독립 관측점을 만듭니다. """
        return ('import pathlib,time\n'
            f'path=pathlib.Path({str(path)!r})\n'
            'deadline=time.monotonic()+10\n'
            'while time.monotonic()<deadline:\n'
            '    with path.open("ab") as stream:\n'
            '        stream.write(b"heartbeat\\n")\n'
            '    time.sleep(0.03)\n')

    def parent_code(self, pulse, wait):
        """! @brief 손자를 실제 실행한 뒤 대기하거나 leader만 먼저 종료합니다. """
        return ('import os,pathlib,subprocess,sys,time\n'
            f'pulse=pathlib.Path({str(pulse)!r})\n'
            f'child={self.pulse_code(pulse)!r}\n'
            'flags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0\n'
            'process=subprocess.Popen([sys.executable,"-I","-X","utf8","-B","-c",child],creationflags=flags)\n'
            'deadline=time.monotonic()+3\n'
            'while not pulse.exists() and time.monotonic()<deadline:\n'
            '    time.sleep(0.01)\n'
            'print("GRANDCHILD_STARTED",flush=True)\n'
            + ('time.sleep(10)\n' if wait else 'sys.exit(0)\n'))

    def assert_stopped(self, path):
        """! @brief PID 존재 여부 대신 실제 작업 진행이 멈췄는지 관찰합니다. """
        self.assertTrue(path.is_file())
        self.assertGreater(path.stat().st_size,0)
        before = path.stat().st_size
        time.sleep(0.25)
        self.assertEqual(path.stat().st_size,before)

    def test_argv_unicode_environment_and_stderr_are_preserved(self):
        """! @brief 공백·한글·shell 특수 문자를 재해석하지 않습니다. """
        self.environment['OWNED_UNIT_VALUE'] = '한글 환경'
        values = ['a b','한글','; literal','$(literal)']
        result = self.run_python('import json,os,sys; print(json.dumps([sys.argv[1:],os.environ["OWNED_UNIT_VALUE"]],ensure_ascii=False)); print("stderr",file=sys.stderr)',*values)
        lines = result.stdout.decode('utf-8').splitlines()
        self.assertEqual(json.loads(next(line for line in lines if line.startswith('['))),[values,'한글 환경'])
        self.assertIn('stderr',lines)
        self.assertEqual(result.returncode,0)
        self.assertGreater(result.pid,0)

    def test_actual_nonzero_exit_is_not_timeout_or_success(self):
        """! @brief 원형 child exit7과 부분 출력을 보존합니다. """
        result = self.run_python('import sys; print("expected failure",flush=True); sys.exit(7)')
        self.assertEqual(result.returncode,7)
        self.assertIn(b'expected failure',result.stdout)

    def test_cleanup_fault_preserves_partial_bytes_without_success_claim(self):
        """! @brief 정리 실패 주입에서도 부분 출력과 미확인 상태를 숨기지 않습니다. """
        def fault(command,cwd,environment,capture,timeout):
            """! @brief 실제 OS 오류를 주장하지 않고 수집 경로만 검증합니다. """
            capture.write(b'partial before cleanup fault')
            raise RuntimeError('fixture-sensitive-value')
        name = '_windows' if os.name=='nt' else '_posix'
        with mock.patch.object(M,name,side_effect=fault),self.assertRaises(M.OwnedExecutionError) as caught:
            self.run_python('raise SystemExit(0)')
        self.assertIn(b'partial before cleanup fault',caught.exception.output)
        self.assertEqual(caught.exception.cleanup['status'],'UNCONFIRMED')
        self.assertNotIn('fixture-sensitive-value',str(caught.exception))

    def test_timeout_preserves_partial_output_and_cleanup(self):
        """! @brief 시간 초과를 정상 종료로 바꾸지 않습니다. """
        with self.assertRaises(M.OwnedTimeout) as caught:
            self.run_python('import time; print("ready",flush=True); time.sleep(10)','fixture-sensitive-value',timeout=0.8)
        self.assertIn(b'ready',caught.exception.output)
        self.assertGreater(caught.exception.pid,0)
        self.assertNotIn('fixture-sensitive-value',str(caught.exception))
        if os.name == 'nt':
            self.assertEqual(caught.exception.cleanup['active_processes_after'],0)
        else:
            self.assertTrue(caught.exception.cleanup['leader_reaped'])

    def test_timeout_stops_actual_grandchild_but_not_unrelated_process(self):
        """! @brief 다른 process는 계속 작동하고 이번 호출의 손자만 정리됩니다. """
        unrelated = self.base/'unrelated.txt'
        child = self.base/'owned.txt'
        flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        other = subprocess.Popen([sys.executable,'-I','-X','utf8','-B','-c',self.pulse_code(unrelated)],
            cwd=self.base,env=self.environment,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=flags)
        try:
            with self.assertRaises(M.OwnedTimeout) as caught:
                self.run_python(self.parent_code(child,True),timeout=2)
            self.assertIn(b'GRANDCHILD_STARTED',caught.exception.output)
            self.assert_stopped(child)
            before = unrelated.stat().st_size
            time.sleep(0.15)
            self.assertGreater(unrelated.stat().st_size,before)
            self.assertIsNone(other.poll())
        finally:
            other.terminate()
            other.wait(timeout=5)

    def test_normal_leader_exit_also_cleans_a_remaining_grandchild(self):
        """! @brief leader가 먼저 exit0이어도 열린 손자를 남기지 않습니다. """
        child = self.base/'remaining.txt'
        result = self.run_python(self.parent_code(child,False))
        self.assertEqual(result.returncode,0)
        self.assertIn(b'GRANDCHILD_STARTED',result.stdout)
        self.assert_stopped(child)

    def test_python_interrupt_keeps_partial_output_and_stops_actual_grandchild(self):
        """! @brief 중단을 전달한 뒤 긴 timeout까지 기다리거나 손자를 남기지 않습니다. """
        child = self.base/'interrupted.txt'
        stop = threading.Event()

        def signal_when_ready():
            """! @brief 실제 손자의 출력이 시작된 경우에만 시험 process의 main thread를 중단합니다. """
            deadline = time.monotonic()+4
            while not stop.wait(0.01) and time.monotonic()<deadline:
                if child.is_file() and child.stat().st_size>0:
                    _thread.interrupt_main()
                    return

        worker = threading.Thread(target=signal_when_ready)
        worker.start()
        started = time.monotonic()
        try:
            with self.assertRaises(M.OwnedInterrupted) as caught:
                self.run_python('print("INTERRUPT_READY",flush=True)\n'+self.parent_code(child,True),timeout=6)
            self.assertLess(time.monotonic()-started,4.5)
            self.assertIn(b'INTERRUPT_READY',caught.exception.output)
            self.assert_stopped(child)
            if os.name == 'nt':
                self.assertEqual(caught.exception.cleanup['active_processes_after'],0)
        finally:
            stop.set()
            worker.join(timeout=5)

    def test_invalid_timeout_and_relative_executable_are_rejected(self):
        """! @brief 잘못된 입력은 child 생성 전에 거부합니다. """
        for timeout in (0,-1,float('inf'),float('nan'),True,1801):
            with self.subTest(timeout=timeout),self.assertRaises(ValueError):
                self.run_python('raise SystemExit(99)',timeout=timeout)
        with self.assertRaises(ValueError):
            M.run_owned(['python','-c','raise SystemExit(99)'],cwd=self.base,
                environment=self.environment,capture_directory=self.base,timeout=1)


class DarwinCleanupBoundaryTests(unittest.TestCase):
    """! @brief 실제 종료 신호 없이 Darwin 오류 경계와 원형 실행 판정을 검사합니다. """
    def observe(self, signals, *, platform='darwin', waits=None, clock=None):
        """! @brief 고정 가상 PGID만 사용하고 실제 Popen과 killpg를 모두 차단합니다. """
        with tempfile.TemporaryDirectory(prefix='nu54-darwin-') as directory, ExitStack() as stack:
            base = Path(directory)
            child = mock.Mock(pid=43210)
            child.wait.side_effect = waits or [0, 0, 0]

            def started(*arguments, **options):
                """! @brief 정리 실패 전의 원형 부분 출력 보존도 확인합니다. """
                options['stdout'].write(b'original partial output')
                return child

            stack.enter_context(mock.patch.object(M.subprocess, 'Popen', side_effect=started))
            kill = stack.enter_context(mock.patch.object(M.os, 'killpg', side_effect=signals, create=True))
            stack.enter_context(mock.patch.object(M.signal, 'SIGKILL', 9, create=True))
            stack.enter_context(mock.patch.object(M, 'sys', SimpleNamespace(platform=platform)))
            stack.enter_context(mock.patch.object(M, '_windows', side_effect=M._posix))
            sleep = stack.enter_context(mock.patch.object(M.time, 'sleep'))
            if clock is not None:
                stack.enter_context(mock.patch.object(M.time, 'monotonic', side_effect=clock))
            try:
                outcome = M.run_owned([sys.executable, '-c', 'unused'], cwd=base,
                    environment={}, capture_directory=base, timeout=1)
            except (M.OwnedExecutionError, M.OwnedTimeout, M.OwnedInterrupted) as error:
                outcome = error
            return outcome, kill.call_args_list, sleep.call_args_list

    def test_darwin_eperm_requires_actual_absence_and_preserves_exit_and_output(self):
        """! @brief EPERM 뒤 실제 ESRCH일 때만 원형 exit0·exit7을 각각 반환합니다. """
        for code in (0, 7):
            with self.subTest(code=code):
                result, calls, _ = self.observe([None, PermissionError(errno.EPERM, 'fixture'),
                    PermissionError(errno.EPERM, 'fixture'), ProcessLookupError(errno.ESRCH, 'fixture')],
                    waits=[code, code, code])
                self.assertIsInstance(result, M.OwnedResult)
                self.assertEqual((result.returncode, result.stdout, result.pid),
                    (code, b'original partial output', 43210))
                self.assertTrue(result.cleanup['darwin_sigkill_eperm_group_absent'])
                self.assertEqual(calls, [mock.call(43210, 15), mock.call(43210, 9),
                    mock.call(43210, 0), mock.call(43210, 0)])

    def test_live_group_or_unrelated_observation_error_remains_failure(self):
        """! @brief 살아 있는 그룹 또는 EPERM·ESRCH 외의 조회 오류는 수락하지 않습니다. """
        for observation in (None, PermissionError(errno.EACCES, 'fixture'), OSError(errno.EIO, 'fixture')):
            with self.subTest(observation=observation):
                result, calls, _ = self.observe([None, PermissionError(errno.EPERM, 'fixture'), observation])
                self.assertIsInstance(result, M.OwnedExecutionError)
                self.assertEqual(result.error_type, 'PermissionError')
                self.assertEqual(result.cleanup['status'], 'UNCONFIRMED')
                self.assertEqual(result.output, b'original partial output')
                self.assertEqual(calls[-1], mock.call(43210, 0))

    def test_persistent_eperm_exhausts_the_bounded_observation(self):
        """! @brief 0.5초 이후 추가 조회나 종료 신호 없이 원래 실패를 전달합니다. """
        result, calls, sleeps = self.observe([None, PermissionError(errno.EPERM, 'fixture'),
            PermissionError(errno.EPERM, 'fixture')], clock=[0, 0, 0, 0.5])
        self.assertIsInstance(result, M.OwnedExecutionError)
        self.assertEqual(len(calls), 3)
        self.assertEqual(sleeps, [mock.call(0.01)])

    def test_other_platform_errno_and_term_failures_do_not_enter_observation(self):
        """! @brief Linux·다른 errno·SIGTERM 실패는 기존 오류 경로를 유지합니다. """
        cases = [('linux', [None, PermissionError(errno.EPERM, 'fixture')]),
            ('darwin', [None, PermissionError(errno.EACCES, 'fixture')]),
            ('darwin', [PermissionError(errno.EPERM, 'fixture')])]
        for platform, signals in cases:
            with self.subTest(platform=platform, count=len(signals)):
                result, calls, _ = self.observe(signals, platform=platform)
                self.assertIsInstance(result, M.OwnedExecutionError)
                self.assertFalse(any(call.args[1] == 0 for call in calls))

    def test_existing_absent_group_path_has_no_darwin_recovery_claim(self):
        """! @brief 기존 ESRCH 정상 경로에 새 회복 증거를 붙이지 않습니다. """
        result, calls, _ = self.observe([ProcessLookupError(errno.ESRCH, 'fixture'),
            ProcessLookupError(errno.ESRCH, 'fixture')])
        self.assertIsInstance(result, M.OwnedResult)
        self.assertNotIn('darwin_sigkill_eperm_group_absent', result.cleanup)
        self.assertEqual(len(calls), 2)

    def test_group_absence_does_not_turn_timeout_or_interrupt_into_success(self):
        """! @brief 실제 그룹 부재 확인 뒤에도 원형 timeout·중단 판정과 출력을 유지합니다. """
        for original, expected in ((subprocess.TimeoutExpired('unused', 1), M.OwnedTimeout),
                (KeyboardInterrupt(), M.OwnedInterrupted)):
            with self.subTest(expected=expected):
                result, _, _ = self.observe([None, PermissionError(errno.EPERM, 'fixture'),
                    ProcessLookupError(errno.ESRCH, 'fixture')], waits=[original, 0, 0])
                self.assertIsInstance(result, expected)
                self.assertEqual(result.output, b'original partial output')
                self.assertEqual(result.pid, 43210)
                self.assertTrue(result.cleanup['darwin_sigkill_eperm_group_absent'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
