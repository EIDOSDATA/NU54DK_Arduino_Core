"""! @brief 제품 SDK·USB 대신 실제 Python 자식과 손자 process로 소유권 정리를 검사합니다. """
import importlib.util
import _thread
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
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


if __name__ == '__main__':
    unittest.main(verbosity=2)
