"""! @brief 실제 CMD→Windows PowerShell 진입에서 모듈 경로와 원형 변조 거부를 검사합니다. """
import hashlib
import importlib
import importlib.util
import io
import json
import os
from pathlib import Path
import platform
import shutil
import sys
import tarfile
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


@unittest.skipUnless(sys.platform=='linux' and platform.machine()=='x86_64','Linux 실제 sh/tar 진입 전용')
class PosixRcKitTests(unittest.TestCase):
    """! @brief 실제 archive 추출·재진입·원형 거부를 SDK와 장치 없이 검사합니다. """
    def prepare(self, base):
        """! @brief 배포 archive와 같은 python 루트에 실행 가능한 시험 runtime을 만듭니다. """
        kit = base/'한글 공백 kit'
        archive = kit/'payload/current/bootstrap-tools/runtime.tar.bz2'
        archive.parent.mkdir(parents=True)
        executable = b'#!/bin/sh\nprintf "RUNTIME_EXECUTED\\n"\nprintf "%s\\n" "$@"\n'
        with tarfile.open(archive,'w:bz2') as stream:
            member = tarfile.TarInfo('python/bin/python3.12')
            member.mode,member.size = 0o755,len(executable)
            stream.addfile(member,io.BytesIO(executable))
        entry = kit/'source/tools/release/host_rc_entry.py'
        entry.parent.mkdir(parents=True)
        entry.write_bytes(b'entry fixture')
        bootstrap = json.loads((ROOT/'tools/nu54-prerequisites/bootstrap-pins.json').read_text(encoding='utf-8'))
        for key in ('linux-x86_64','macos-arm64'):
            bootstrap['platforms'][key]['arduino_archive'] = dict(filename=archive.name,sha256=M.sha(archive))
        starter = kit/'START.sh'
        starter.write_text(M.posix_starter(bootstrap,M.sha(entry)),encoding='utf-8')
        return kit,archive,entry,starter

    def run_starter(self, base, starter, environment=None):
        """! @brief 실제 POSIX shell을 제한 시간과 종료 증거를 갖춰 호출합니다. """
        return OWNED.run_owned(['/bin/sh',starter,'--work-root',base/'work space','plan'],
            cwd=base,environment=environment or dict(os.environ),capture_directory=base,timeout=30)

    def test_archive_root_launches_cold_and_warm_and_rejects_tamper(self):
        """! @brief python 하위 실행 파일을 처음과 재진입 때 찾고 변조 원형은 실행하지 않습니다. """
        with tempfile.TemporaryDirectory(prefix='nu54-posix-kit-') as temporary:
            base = Path(temporary)
            kit,archive,entry,starter = self.prepare(base)
            for attempt in ('cold','warm'):
                with self.subTest(attempt=attempt):
                    result = self.run_starter(base,starter)
                    self.assertEqual(result.returncode,0,result.stdout)
                    self.assertIn(b'RUNTIME_EXECUTED\n',result.stdout)
                    self.assertIn(str(base/'work space').encode(),result.stdout)
            for path in (archive,entry):
                with self.subTest(tampered=path.name):
                    original = path.read_bytes()
                    path.write_bytes(original+b'changed')
                    result = self.run_starter(base,starter)
                    self.assertEqual(result.returncode,2,result.stdout)
                    self.assertNotIn(b'RUNTIME_EXECUTED',result.stdout)
                    path.write_bytes(original)

    def test_missing_bzip2_and_partial_runtime_fail_before_execution(self):
        """! @brief 누락 의존성은 추출 전에 안내하고 이전 실패 디렉터리는 보존합니다. """
        with tempfile.TemporaryDirectory(prefix='nu54-posix-kit-') as temporary:
            base = Path(temporary)
            kit,archive,entry,starter = self.prepare(base)
            commands = base/'commands'
            commands.mkdir()
            for name in ('dirname','uname','sha256sum','cut'):
                (commands/name).symlink_to(shutil.which(name))
            environment = dict(os.environ,PATH=str(commands))
            result = self.run_starter(base,starter,environment)
            self.assertEqual(result.returncode,2,result.stdout)
            self.assertIn(b'Install the Ubuntu bzip2 package',result.stdout)
            runtime = kit/'runtime-linux-x86_64'
            self.assertFalse(runtime.exists())
            runtime.mkdir()
            marker = runtime/'original-failure'
            marker.write_bytes(b'preserve')
            executable = runtime/'python/bin/python3.12'
            executable.parent.mkdir(parents=True)
            executable.write_bytes(b'#!/bin/sh\necho INCOMPLETE_RUNTIME_EXECUTED\n')
            executable.chmod(0o755)
            result = self.run_starter(base,starter)
            self.assertEqual(result.returncode,2,result.stdout)
            self.assertIn(b'Incomplete runtime exists',result.stdout)
            self.assertNotIn(b'INCOMPLETE_RUNTIME_EXECUTED',result.stdout)
            self.assertEqual(marker.read_bytes(),b'preserve')


if __name__=='__main__':
    unittest.main()
