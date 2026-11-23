"""! @brief 실제 자식 실행으로 upload timeout·부분 출력·비식별 log·중단 경계를 검증합니다. """
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('host_upload_process_builder', ROOT/'tools/nu54-builder/src/nu54_builder.py')
BUILDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILDER)
UPLOAD = BUILDER.implementation.upload


class HostUploadProcessTests(unittest.TestCase):
    """! @brief USB를 열지 않고 실제 Python 실행기와 제품 log 경로를 검사합니다. """
    def setUp(self):
        """! @brief 각 attempt는 독립된 출력 폴더를 사용합니다. """
        temporary = tempfile.TemporaryDirectory(prefix='nu54-upload-process-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.log = self.root/'logs/flash.log'
        self.uid = 'FIXTURE_PRIVATE_PROBE_0123456789'

    def run_child(self, code, timeout=3):
        """! @brief SDK 대신 현재 절대 Python을 제품 flash 실행기에 전달합니다. """
        console = io.StringIO()
        with contextlib.redirect_stdout(console):
            UPLOAD.run_flash_process([sys.executable,'-I','-X','utf8','-B','-c',code,self.uid],
                cwd=self.root,environment=dict(os.environ),log_path=self.log,runner='pyocd',
                probe_id=self.uid,hex_path=self.root/'fixture.hex',hex_sha256='1'*64,
                timeout_seconds=timeout)
        return console.getvalue()

    def test_success_preserves_output_and_logs_cleanup_without_raw_UID(self):
        """! @brief 정상 종료도 실제 자식 정리와 UID 비식별을 기록합니다. """
        console = self.run_child('import sys; print("한글 "+sys.argv[1],flush=True)')
        text = self.log.read_text(encoding='utf-8')
        self.assertIn('process_outcome=EXITED',text)
        self.assertIn('exit_code=0',text)
        self.assertIn('cleanup=',text)
        self.assertNotIn(self.uid,text+console)
        self.assertIn('한글',console)

    def test_nonzero_exit_preserves_failure_log(self):
        """! @brief child7은 성공이나 timeout으로 바뀌지 않습니다. """
        with self.assertRaises(BUILDER.AdapterError):
            self.run_child('import sys; print("runner failed",flush=True); sys.exit(7)')
        text = self.log.read_text(encoding='utf-8')
        self.assertIn('exit_code=7',text)
        self.assertIn('runner failed',text)
        self.assertNotIn(self.uid,text)

    def test_timeout_keeps_partial_log_and_never_reports_exit0(self):
        """! @brief 실제 timeout 후 부분 출력과 cleanup을 먼저 저장합니다. """
        with self.assertRaisesRegex(BUILDER.AdapterError,'E_FLASH_TIMEOUT'):
            self.run_child('import time; print("partial ready",flush=True); time.sleep(10)',0.7)
        text = self.log.read_text(encoding='utf-8')
        self.assertIn('process_outcome=TIMEOUT',text)
        self.assertIn('partial ready',text)
        self.assertIn('exit_code=None',text)
        self.assertNotIn(self.uid,text)
        self.assertNotIn('exit_code=0',text)

    def test_invalid_timeout_is_rejected_before_environment_or_probe_access(self):
        """! @brief 무한·음수·bool 제한은 도구·장치에 접근하기 전에 거부합니다. """
        for timeout in (float('nan'),float('inf'),0,-1,True,1801):
            args = type('Args',(),{'timeout_seconds':timeout})()
            with self.subTest(timeout=timeout),mock.patch.object(UPLOAD,'tool_environment') as environment:
                with self.assertRaisesRegex(BUILDER.AdapterError,'E_FLASH_TIMEOUT_OPTION'):
                    UPLOAD.flash(args)
                environment.assert_not_called()

    def test_probe_digest_selects_only_one_exact_identity(self):
        """! @brief 누락·중복·원문 UID는 자동 첫 probe로 대체하지 않습니다. """
        digest = UPLOAD.probe_id_sha256(self.uid)
        self.assertEqual(UPLOAD.select_pyocd_probe_digest(digest,[self.uid,'OTHER-FIXTURE']),self.uid)
        for requested,values in ((self.uid,[self.uid]),(digest,[]),(digest,[self.uid,self.uid])):
            with self.subTest(requested=requested),self.assertRaisesRegex(BUILDER.AdapterError,'E_PROBE_SHA256'):
                UPLOAD.select_pyocd_probe_digest(requested,values)

    def test_jlink_backend_opt_in_requires_explicit_identity_before_environment(self):
        """! @brief 조건부 backend는 단일 probe 자동 선택으로 승인되지 않습니다. """
        for runner in ('pyocd','jlink'):
            args = type('Args',(),{'timeout_seconds':30,'runner':runner,'allow_jlink_backend':True,
                'probe_sha256':None,'probe_id':None})()
            with self.subTest(runner=runner),mock.patch.dict(os.environ,{'NUCODE_PROBE_UID':''}),mock.patch.object(UPLOAD,'tool_environment') as environment:
                with self.assertRaisesRegex(BUILDER.AdapterError,'E_PROBE_BACKEND'):
                    UPLOAD.flash(args)
                environment.assert_not_called()

    def test_cleanup_fault_log_keeps_partial_output_and_unconfirmed_status(self):
        """! @brief 정리 실패는 upload PASS가 되지 않고 UID를 숨긴 부분 log로 남습니다. """
        failure = UPLOAD.OwnedExecutionError(('partial '+self.uid).encode(),'RuntimeError')
        with mock.patch.object(UPLOAD,'run_owned',side_effect=failure),self.assertRaises(BUILDER.AdapterError):
            self.run_child('raise SystemExit(0)')
        text = self.log.read_text(encoding='utf-8')
        self.assertIn('START_OR_CLEANUP_FAILURE',text)
        self.assertIn('UNCONFIRMED',text)
        self.assertIn('partial',text)
        self.assertNotIn(self.uid,text)
        self.assertNotIn('exit_code=0',text)


if __name__ == '__main__':
    unittest.main()
