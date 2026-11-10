"""! @brief 실제 CMD→Windows PowerShell 진입에서 모듈 경로와 원형 변조 거부를 검사합니다. """
import hashlib
import importlib
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('host_rc_kit_test',ROOT/'tools/release/host_rc_kit.py')
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)
BUILDER_SPEC = importlib.util.spec_from_file_location('host_rc_kit_test_builder',ROOT/'tools/nu54-builder/src/nu54_builder.py')
BUILDER = importlib.util.module_from_spec(BUILDER_SPEC)
BUILDER_SPEC.loader.exec_module(BUILDER)
OWNED = importlib.import_module(BUILDER.implementation.__name__+'.owned_process')


class HostRcKitTests(unittest.TestCase):
    """! @brief 실제 OS hash만 실행하며 SDK 설치·장치 동작은 하지 않습니다. """
    def test_hash_command_rejects_unsafe_literal_before_process_start(self):
        """! @brief 경로 탈출·따옴표·hash 누락은 batch 생성 전에 거부합니다. """
        for path,digest in (('../escape','a'*64),("a'quote",'a'*64),('archive','bad')):
            with self.subTest(path=path),self.assertRaises(ValueError):
                M.windows_hash_check([(path,digest)])

    @unittest.skipUnless(os.name=='nt','Windows CMD/PowerShell 실제 경로 전용')
    def test_real_cmd_hash_ignores_module_path_and_rejects_tamper(self):
        """! @brief 모듈 검색을 사용할 수 없어도 정상 byte만 통과하고 열린 handle을 남기지 않습니다. """
        with tempfile.TemporaryDirectory(prefix='nu54-rc-kit-') as temporary:
            base = Path(temporary)
            kit = base/'한글 공백! literal'
            kit.mkdir()
            files = []
            for name in ('archive.bin','entry.py'):
                path = kit/name
                path.write_bytes(('fixture '+name).encode())
                files.append((name,hashlib.sha256(path.read_bytes()).hexdigest()))
            batch = base/'hash-check.cmd'
            batch.write_bytes(('@echo off\r\nsetlocal EnableExtensions DisableDelayedExpansion\r\n'
                +M.windows_hash_check(files)+'echo HASH_VERIFY_PASS\r\n').encode('ascii'))
            environment = dict(os.environ)
            environment['KIT'] = str(kit)+os.sep
            trap = base/'empty-modules'
            trap.mkdir()
            environment['PSMODULEPATH'] = str(trap)
            command = [Path(os.environ['SYSTEMROOT'])/'System32/cmd.exe','/d','/c',batch]
            result = OWNED.run_owned(command,cwd=base,environment=environment,capture_directory=base,timeout=30)
            self.assertEqual(result.returncode,0,result.stdout)
            self.assertIn(b'HASH_VERIFY_PASS',result.stdout)
            (kit/'entry.py').write_bytes(b'changed after first check')
            failed = OWNED.run_owned(command,cwd=base,environment=environment,capture_directory=base,timeout=30)
            self.assertEqual(failed.returncode,2,failed.stdout)
            self.assertNotIn(b'HASH_VERIFY_PASS',failed.stdout)


if __name__=='__main__':
    unittest.main()
