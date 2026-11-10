"""! @brief HOST-W05의 실제 파일 경로·권한·native lock 의미를 검사합니다. """
import contextlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unicodedata
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
ENTRY = ROOT / 'tools/nu54-builder/src/nu54_builder.py'
spec = importlib.util.spec_from_file_location('host_w05_builder_tests', ENTRY)
B = importlib.util.module_from_spec(spec)
spec.loader.exec_module(B)
H, P, E, L, C = (getattr(B.implementation, name) for name in ('host', 'paths', 'environment', 'locking', 'common'))


class HostPathLockTests(unittest.TestCase):
    """! @brief mock 완료가 아닌 파일 생성·권한·별도 process 회귀입니다. """

    def setUp(self):
        """! @brief 기존 SDK·cache와 격리된 새 임시 root를 준비합니다. """
        self.temporary = tempfile.TemporaryDirectory(prefix='nu54-host-w05-')
        self.addCleanup(self.temporary.cleanup)
        self.root = C.canonical_path(self.temporary.name)

    def test_relative_existing_cache_is_rejected_before_cwd_resolution(self):
        """! @brief 같은 이름의 실제 directory가 있어도 상대 override는 거부합니다. """
        (self.root / 'relative').mkdir()
        with contextlib.chdir(self.root):
            for value in ('relative', '', '   '):
                with self.subTest(value=value), self.assertRaisesRegex(C.AdapterError, 'E_HOST_PATH'):
                    P.local_cache_root(value)
        with self.assertRaisesRegex(C.AdapterError, 'E_CACHE_ROOT'):
            P.local_cache_root(self.root.anchor)

    def test_xdg_relative_and_foreign_drive_are_rejected_but_empty_uses_default(self):
        """! @brief POSIX override는 절대 경로여야 하며 빈 XDG는 기본값입니다. """
        linux = H.describe_host(system_name='Linux', machine='x86_64', distribution='ubuntu', version='24.04')
        home = Path('/host-w05-test-home')
        for value in ('relative', 'C:/ncs/cache', r'\\server\share'):
            with self.subTest(value=value), self.assertRaisesRegex(C.AdapterError, 'E_HOST_PATH'):
                H.user_cache_root(linux, {'XDG_CACHE_HOME': value}, home)
        self.assertEqual(H.user_cache_root(linux, {'XDG_CACHE_HOME': ''}, home), C.canonical_path(home) / '.cache')

    def test_explicit_sdk_toolchain_and_state_overrides_cannot_be_relative_or_empty(self):
        """! @brief SDK 탐색의 명시 override를 조용히 기본값으로 바꾸지 않습니다. """
        calls = (
            ('NUCODE_NCS_ROOT', E.discover_ncs_root),
            ('NUCODE_TOOLCHAIN_ROOT', lambda: E.discover_toolchain_root(self.root / 'sdk')),
            ('NUCODE_PREREQUISITE_STATE_ROOT', E.prerequisite_state_root),
            ('NUCODE_BUILD_CACHE_ROOT', P.build_cache_root),
        )
        for name, call in calls:
            for value in ('relative', ''):
                with self.subTest(variable=name, value=value), mock.patch.dict(os.environ, {name: value}):
                    with self.assertRaises(C.AdapterError):
                        call()

    def test_unicode_space_cache_can_write_without_leaving_probe_files(self):
        """! @brief 실제 공백·한글 cache에서 write 검사를 하고 임시 파일을 반환합니다. """
        path = self.root / '공백 cache' / '한글 경로'
        self.assertEqual(P.ensure_writable_cache_root(path), C.canonical_path(path))
        self.assertEqual(list(path.iterdir()), [])
        not_directory = self.root / 'ordinary-file'
        not_directory.write_bytes(b'preserve')
        with self.assertRaisesRegex(C.AdapterError, 'E_CACHE_PERMISSION'):
            P.ensure_writable_cache_root(not_directory)
        self.assertEqual(not_directory.read_bytes(), b'preserve')

    def test_owned_cache_symlink_resolves_to_same_writable_directory(self):
        """! @brief 사용자 cache root의 symlink는 같은 실제 객체로 처리합니다. """
        target = self.root / '실제 cache'
        target.mkdir(mode=0o700)
        link = self.root / 'cache-link'
        try:
            link.symlink_to(target, target_is_directory=True)
        except OSError:
            self.skipTest('현재 Host에서 비관리자 symlink 생성이 허용되지 않습니다.')
        self.assertEqual(P.ensure_writable_cache_root(link), C.canonical_path(target))

    def test_long_unicode_cache_keeps_atomic_file_and_lock_semantics(self):
        """! @brief 260자를 넘는 실제 경로에서도 교체·잠금·해제와 파일 byte를 보존합니다. """
        path = self.root
        while len(str(path)) <= 280:
            path = path / '공백 cache 한글 0123456789'
        root = P.ensure_writable_cache_root(path)
        document = root / 'state.json'
        C.atomic_write_json(document, {'generation': 1})
        with L.build_lock(root, operation='long-path-regression', timeout_seconds=1):
            C.atomic_write_json(document, {'generation': 2, '한글': '보존'})
            self.assertTrue((root / '.adapter.lock').is_file())
        self.assertEqual(json.loads(document.read_text(encoding='utf-8')), {'generation': 2, '한글': '보존'})
        self.assertEqual([entry.name for entry in root.iterdir()], ['state.json'])

    @unittest.skipIf(os.name == 'nt', 'POSIX mode 검사는 native Ubuntu/macOS에서 수행합니다.')
    def test_group_writable_cache_is_rejected_without_changing_permissions(self):
        """! @brief 기존 권한을 바꾸거나 공유 cache를 자동 승인하지 않습니다. """
        path = self.root / 'shared'
        path.mkdir()
        path.chmod(0o777)
        try:
            with self.assertRaisesRegex(C.AdapterError, 'E_CACHE_PERMISSION'):
                P.ensure_writable_cache_root(path)
            self.assertEqual(path.stat().st_mode & 0o777, 0o777)
        finally:
            path.chmod(0o700)

    @unittest.skipIf(os.name == 'nt', 'POSIX read-only 검사는 native Ubuntu/macOS에서 수행합니다.')
    def test_read_only_cache_fails_for_unprivileged_user(self):
        """! @brief 실제 쓰기 권한 없는 directory가 ready cache로 승인되지 않습니다. """
        if os.geteuid() == 0:
            self.skipTest('root 권한에서는 일반 사용자의 write 거부를 재현하지 않습니다.')
        path = self.root / 'read-only'
        path.mkdir()
        path.chmod(0o500)
        try:
            with self.assertRaisesRegex(C.AdapterError, 'E_CACHE_PERMISSION'):
                P.ensure_writable_cache_root(path)
        finally:
            path.chmod(0o700)

    def test_case_alias_and_distinct_unicode_names_follow_real_filesystem(self):
        """! @brief 실제 같은 파일과 서로 다른 이름을 Unicode casefold로 합치지 않습니다. """
        first = self.root / 'straße.txt'
        second = self.root / 'strasse.txt'
        first.write_bytes(b'first')
        second.write_bytes(b'second')
        if first.samefile(second):
            self.assertEqual(C.path_key(first), C.path_key(second))
        else:
            self.assertNotEqual(C.path_key(first), C.path_key(second))
            self.assertEqual(first.read_bytes(), b'first')
        folder = self.root / 'ActualCase'
        folder.mkdir()
        alias = self.root / 'actualcase'
        if alias.exists() and alias.samefile(folder):
            self.assertEqual(C.path_key(folder), C.path_key(alias))
            self.assertEqual(L.operating_system_lock_identity(folder), L.operating_system_lock_identity(alias))

    def test_unicode_normalization_uses_actual_file_identity(self):
        """! @brief APFS의 Unicode alias와 Linux/NTFS의 별도 이름을 구분합니다. """
        first = self.root / '한글.txt'
        other = self.root / unicodedata.normalize('NFD', first.name)
        first.write_bytes(b'first')
        if other.exists() and first.samefile(other):
            self.assertEqual(C.path_key(first), C.path_key(other))
        else:
            other.write_bytes(b'other')
            self.assertNotEqual(C.path_key(first), C.path_key(other))

    def test_case_sensitive_tree_hash_does_not_depend_on_creation_order(self):
        """! @brief case만 다른 두 실제 파일도 생성 순서와 무관한 tree hash를 얻습니다. """
        left, right = self.root / 'left', self.root / 'right'
        left.mkdir()
        right.mkdir()
        for name in ('Foo.h', 'foo.h'):
            (left / name).write_bytes(name.encode())
        if (left / 'Foo.h').samefile(left / 'foo.h'):
            self.skipTest('현재 파일시스템은 case만 다른 두 이름을 분리하지 않습니다.')
        for name in ('foo.h', 'Foo.h'):
            (right / name).write_bytes(name.encode())
        self.assertEqual(C.tree_content_sha256(left, ('.',)), C.tree_content_sha256(right, ('.',)))

    def test_toolchain_environment_rejects_escape_types_and_duplicate_keys(self):
        """! @brief 환경 선언의 외부 경로·모호한 JSON·다른 형식을 실행 전에 거부합니다. """
        toolchain = self.root / 'toolchain'
        toolchain.mkdir()
        path = toolchain / 'environment.json'
        for entry in (
            {'key': 'PATH', 'type': 'relative_paths', 'values': ['../outside']},
            {'key': 'PATH', 'type': 'relative_paths', 'values': [str(self.root)]},
            {'key': 'PATH', 'type': 'relative_paths', 'values': 'bin'},
            {'key': 'PATH', 'type': 'unknown', 'value': 'outside'},
        ):
            path.write_text(json.dumps({'env_vars': [entry]}), encoding='utf-8')
            with self.subTest(entry=entry), self.assertRaisesRegex(C.AdapterError, 'E_TOOL_ENVIRONMENT'):
                E.apply_toolchain_environment(toolchain)
        path.write_text('{"env_vars":[],"env_vars":[]}', encoding='utf-8')
        with self.assertRaises(C.AdapterError):
            E.apply_toolchain_environment(toolchain)

    def test_toolchain_environment_keeps_argv_path_and_filters_parent_flags(self):
        """! @brief 내부 PATH를 명시적으로 결합하며 부모 compiler flag를 섞지 않습니다. """
        toolchain = self.root / '도구 chain'
        toolchain.mkdir()
        (toolchain / 'environment.json').write_text(json.dumps({'env_vars': [
            {'key': 'PATH', 'type': 'relative_paths', 'values': ['bin'], 'existing_value_treatment': 'prepend_to'}
        ]}), encoding='utf-8')
        with mock.patch.dict(os.environ, {'CFLAGS': 'parent-poison', 'PATH': 'parent-path'}):
            environment = E.apply_toolchain_environment(toolchain)
        self.assertEqual(environment['PATH'], str(C.canonical_path(toolchain / 'bin')) + os.pathsep + 'parent-path')
        self.assertNotIn('CFLAGS', environment)

    def test_empty_path_and_external_tools_do_not_replace_bundle_programs(self):
        """! @brief 빈 PATH에서도 고정 도구를 찾고 외부 PATH의 대체 실행 파일은 거부합니다. """
        toolchain = self.root / 'toolchain'
        python = toolchain / H.executable_candidates('python')[0]
        python.parent.mkdir(parents=True)
        python.write_bytes(b'bundle-fixture')
        python.chmod(0o755)
        (toolchain / 'environment.json').write_text('{"env_vars":[]}', encoding='utf-8')
        with mock.patch.dict(os.environ, {'PATH': ''}):
            self.assertEqual(H.resolve_toolchain_executable(toolchain, 'python'), C.canonical_path(python))
        outside = self.root / 'external-bin'
        outside.mkdir()
        fake_west = outside / ('west.exe' if os.name == 'nt' else 'west')
        fake_west.write_bytes(b'outside-fixture')
        fake_west.chmod(0o755)
        with mock.patch.dict(os.environ, {'PATH': str(outside)}):
            with self.assertRaisesRegex(C.AdapterError, 'E_TOOL_EXECUTABLE'):
                H.resolve_toolchain_executable(toolchain, 'west')

    def test_bundle_symlink_cannot_redirect_environment_outside_root(self):
        """! @brief 겉보기 상대 경로인 symlink도 bundle 외부이면 거부합니다. """
        toolchain, outside = self.root / 'toolchain', self.root / 'outside'
        toolchain.mkdir()
        outside.mkdir()
        try:
            (toolchain / 'bin').symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest('현재 Host에서 비관리자 symlink 생성이 허용되지 않습니다.')
        (toolchain / 'environment.json').write_text(json.dumps({'env_vars': [
            {'key': 'PATH', 'type': 'relative_paths', 'values': ['bin']}
        ]}), encoding='utf-8')
        with self.assertRaisesRegex(C.AdapterError, 'E_TOOL_ENVIRONMENT'):
            E.apply_toolchain_environment(toolchain)

    @unittest.skipIf(os.name == 'nt', 'POSIX lock 파일 검사는 native Ubuntu/macOS에서 수행합니다.')
    def test_lock_directory_and_file_reject_writable_mode_and_symlink(self):
        """! @brief native lock을 외부 파일이나 다른 사용자 쓰기 경로로 유도하지 않습니다. """
        with mock.patch.object(L, 'POSIX_LOCK_ROOT', self.root):
            directory = L.posix_lock_directory()
            directory.chmod(0o777)
            try:
                with self.assertRaisesRegex(C.AdapterError, 'E_LOCK_PERMISSION'):
                    L.posix_lock_directory()
            finally:
                directory.chmod(0o700)
            outside = self.root / 'preserve'
            outside.write_bytes(b'original')
            root = self.root / 'cache'
            identity = L.operating_system_lock_identity(root)
            (directory / (identity + '.lock')).symlink_to(outside)
            with self.assertRaisesRegex(C.AdapterError, 'E_LOCK_PERMISSION'):
                with L.operating_system_lock(root, 0.1):
                    self.fail('symlink lock이 획득됐습니다.')
            self.assertEqual(outside.read_bytes(), b'original')

    @unittest.skipIf(os.name == 'nt', 'POSIX FIFO 안전 검사는 native Ubuntu/macOS에서 수행합니다.')
    def test_path_normalization_does_not_open_fifo(self):
        """! @brief 경로 정규화가 device나 FIFO를 열어 대기하지 않습니다. """
        path = self.root / 'pipe'
        os.mkfifo(path)
        with mock.patch.object(C.os, 'open', side_effect=AssertionError('FIFO를 열면 안 됩니다.')):
            self.assertEqual(C.canonical_path(path), self.root / 'pipe')

    def test_native_lock_serializes_processes_with_different_tmp_roots(self):
        """! @brief TMP가 달라도 같은 실제 cache의 두 process는 배타적입니다. """
        child_code = '''"""! @brief TMP별 process의 native lock을 검사합니다. """
import importlib.util
from pathlib import Path
import sys
spec = importlib.util.spec_from_file_location('host_w05_child', sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
try:
    with module.build_lock(Path(sys.argv[2]), timeout_seconds=0.15):
        if sys.argv[3] == 'hold':
            Path(sys.argv[4]).write_text('ready', encoding='utf-8')
            sys.stdin.readline()
        else:
            raise SystemExit(3)
except module.AdapterError as error:
    if sys.argv[3] == 'try' and '대기 시간이 초과' in str(error):
        print('EXPECTED_BUSY')
    else:
        raise
'''
        cache, marker = self.root / '공통 cache', self.root / 'ready'
        environments = []
        for name in ('tmp-first', 'tmp-second'):
            folder = self.root / name
            folder.mkdir()
            environments.append(dict(os.environ, TMP=str(folder), TEMP=str(folder), TMPDIR=str(folder)))
        command = [sys.executable, '-B', '-I', '-c', child_code, str(ENTRY), str(cache)]
        process = subprocess.Popen([*command, 'hold', str(marker)], env=environments[0],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            deadline = time.monotonic() + 5
            while not marker.exists() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertTrue(marker.exists(), '첫 native lock의 진입을 확인하지 못했습니다.')
            result = subprocess.run([*command, 'try', str(marker)], env=environments[1], capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('EXPECTED_BUSY', result.stdout)
            _stdout, stderr = process.communicate('release\n', timeout=5)
            self.assertEqual(process.returncode, 0, stderr)
        finally:
            if process.poll() is None:
                process.kill()
            process.communicate(timeout=5)
        with L.build_lock(cache, timeout_seconds=1):
            self.assertTrue((cache / '.adapter.lock').is_file())


if __name__ == '__main__':
    unittest.main()
