"""! @brief native package의 실제 pin·원문 고지·recipe·얇은 설치 진입점을 검사합니다. """
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('native_package_host_tests', ROOT / 'packaging/boards-manager/nu54_package.py')
PACKAGE = importlib.util.module_from_spec(spec)
spec.loader.exec_module(PACKAGE)
N = PACKAGE.implementation.inputs.native
VERSION = '0.6.0-host.1'


class NativePackageTests(unittest.TestCase):
    """! @brief source Git 실적과 구분한 metadata·설치 argv·변조 negative 시험입니다. """

    @classmethod
    def setUpClass(cls):
        """! @brief 실제 대조한 세 ABI pin·원문 파일을 독립 package namespace에서 읽습니다. """
        PACKAGE.configure_release_candidates(PACKAGE.RELEASE_CANDIDATE_VERSIONS + (VERSION, '0.6.0-rc.1'))
        cls.pin_data = (ROOT / N.BOOTSTRAP_PATH).read_bytes()
        cls.pins = N.load_bootstrap(cls.pin_data)
        names = [N.BOOTSTRAP_PATH, N.PLATFORM_PINS_PATH, 'tools/nu54-prerequisites/pins.json']
        names += ['tools/nu54-prerequisites/' + row['path'] for row in cls.pins['notice_files']]
        cls.payload = {name: (ROOT / name).read_bytes() for name in names}

    def test_official_assets_define_exact_native_arduino_flavours(self):
        """! @brief upstream ABI와 Arduino host 이름을 혼동하거나 SDK binary를 tool로 넣지 않습니다. """
        pins = N.load_bootstrap(self.pin_data, self.payload)
        tool = N.tool_definition(pins)
        self.assertEqual({row['host'] for row in tool['systems']}, {'x86_64-mingw32', 'x86_64-linux-gnu', 'arm64-apple-darwin'})
        self.assertEqual(N.tool_dependency(pins), [{'packager': 'nucode', 'name': 'nu54-python', 'version': '3.12.16-20261026'}])
        self.assertEqual(len(tool['systems']), 3)
        self.assertTrue(all(row['url'].startswith('https://github.com/astral-sh/python-build-standalone/releases/download/20261026/') for row in tool['systems']))

    def test_registered_host_candidate_sorts_before_rc_without_opening_allowlist(self):
        """! @brief native 시험 후보를 정렬하되 등록하지 않은 version을 자동 승인하지 않습니다. """
        self.assertEqual(sorted(['0.6.0-rc.1', VERSION, '0.5.0'], key=PACKAGE.version_sort_key),
            ['0.5.0', VERSION, '0.6.0-rc.1'])
        with self.assertRaises(PACKAGE.PackageError):
            PACKAGE.version_sort_key('0.6.0-host.2')

    def test_foreign_url_host_executable_size_and_digest_are_rejected(self):
        """! @brief 같은 version 표기만으로 임의 executable·다른 Host·잘못된 asset을 허용하지 않습니다. """
        mutations = (
            lambda value: value['platforms']['linux-x86_64']['archive'].update(url='http://example.invalid/python.tar.gz'),
            lambda value: value['platforms']['macos-arm64'].update(arduino_host='x86_64-apple-darwin'),
            lambda value: value['platforms']['windows-x86_64'].update(executable='../python.exe'),
            lambda value: value['platforms']['linux-x86_64']['archive'].update(size=True),
            lambda value: value['platforms']['linux-x86_64']['archive'].update(sha256='0' * 63),
            lambda value: value['platforms'].pop('macos-arm64'),
        )
        for mutate in mutations:
            value = copy.deepcopy(self.pins)
            mutate(value)
            with self.subTest(pin=value), self.assertRaises(PACKAGE.PackageError):
                N.load_bootstrap(json.dumps(value).encode())

    def test_duplicate_json_and_missing_or_changed_original_notice_fail(self):
        """! @brief 중복 key·고지 누락·실제 byte 손상을 자체 생성 hash와 구분해 거부합니다. """
        with self.assertRaises(PACKAGE.PackageError):
            N.load_bootstrap(b'{"schema_version":1,' + self.pin_data.lstrip()[1:])
        path = 'tools/nu54-prerequisites/' + self.pins['notice_files'][0]['path']
        for replacement in (None, b'changed-license'):
            payload = dict(self.payload)
            if replacement is None:
                payload.pop(path)
            else:
                payload[path] = replacement
            with self.subTest(replacement=replacement), self.assertRaises(PACKAGE.PackageError):
                N.load_bootstrap(self.pin_data, payload)

    def test_changed_ncs_revision_or_missing_platform_is_not_native_pin(self):
        """! @brief metadata 갱신만으로 SDK source를 바꾸거나 OS 행을 생략하지 못합니다. """
        baseline = json.loads(self.payload[N.PLATFORM_PINS_PATH])
        for mutate in (lambda value: value['ncs'].update(revision='0' * 40),
                lambda value: value['platforms'].pop('macos-arm64')):
            pins = copy.deepcopy(baseline)
            mutate(pins)
            with self.assertRaises(PACKAGE.PackageError):
                N.load_platform_pins(json.dumps(pins).encode())

    def test_manifest_binds_actual_notice_and_three_bundle_bytes(self):
        """! @brief Windows 단일 bundle 표기를 OS별 실제 bundle map·manifest hash로 보완합니다. """
        payload = dict(self.payload)
        payload['platform.txt'] = N.rewrite_platform(PACKAGE.rewrite_platform_version((ROOT / 'platform.txt').read_bytes(), VERSION), self.pins)
        for name in ('post_install.bat', 'post_install.sh'):
            payload[name] = N.render_post_install(name, self.pins)
        files = [PACKAGE.SourceFile(path=name, data=data, mode=0o755 if name.endswith('.sh') else 0o644,
            origin='core', git_object=hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest())
            for name, data in sorted(payload.items())]
        manifest = PACKAGE.build_release_manifest(files, VERSION, '1' * 40, '2' * 40)
        self.assertEqual(manifest['toolchain_bundle_ids'], {'windows-x86_64': 'dcbdc366a1', 'linux-x86_64': 'fbf7391cab', 'macos-arm64': 'ccc010f809'})
        self.assertEqual(manifest['platform_prerequisites_sha256'], hashlib.sha256(payload[N.PLATFORM_PINS_PATH]).hexdigest())
        self.assertEqual(manifest['bootstrap_pins_sha256'], hashlib.sha256(self.pin_data).hexdigest())
        external = PACKAGE.build_external_prerequisites(files, VERSION)
        self.assertEqual(len([row for row in external if row['name'].startswith('Bootstrap Python (')]), 3)
        self.assertEqual(len([row for row in external if row['name'].startswith('NCS toolchain bundle (')]), 3)

    def test_archive_bootstrap_reads_and_checks_original_notice(self):
        """! @brief archive를 실행·설치하지 않고 저장된 license 손상을 거부합니다. """
        with tempfile.TemporaryDirectory(prefix='host-native-archive-') as value:
            root = f'nucode-nu54dk-zephyr-{VERSION}/'
            for damaged in (False, True):
                archive = Path(value) / f'notice-{damaged}.zip'
                with zipfile.ZipFile(archive, 'w') as stream:
                    for name, data in self.payload.items():
                        if damaged and name.endswith(self.pins['notice_files'][0]['path']):
                            data += b'changed'
                        stream.writestr(root + name, data)
                if damaged:
                    with self.assertRaises(PACKAGE.PackageError):
                        N.bootstrap_from_archive(archive, VERSION)
                else:
                    self.assertEqual(N.bootstrap_from_archive(archive, VERSION), self.pins)

    @unittest.skipIf(os.name == 'nt', '실제 POSIX argv·종료는 Ubuntu/macOS native에서 검사합니다.')
    def test_posix_post_install_preserves_literal_argv_and_child_exit(self):
        """! @brief 공백·한글·shell 기호를 재해석하지 않고 같은 설치 argv와 실패 code를 반환합니다. """
        with tempfile.TemporaryDirectory(prefix='host-native-argv-') as value:
            root = Path(value)
            platform = root / 'packages/nucode/hardware/zephyr' / VERSION
            platform.mkdir(parents=True)
            entry = platform / 'post_install.sh'
            entry.write_bytes(N.render_post_install(entry.name, self.pins))
            backend = platform / 'tools/nu54-prerequisites/nordic.py'
            backend.parent.mkdir(parents=True)
            backend.write_text('', encoding='utf-8')
            runtime = root / 'packages/nucode/tools/nu54-python' / self.pins['runtime']['tool_version'] / 'bin/python3.12'
            runtime.parent.mkdir(parents=True)
            runtime.write_text('#!/bin/sh\nprintf \'%s\\0\' "$@" > "$HOST_PACKAGE_ARGV_CAPTURE"\nexit 23\n', encoding='utf-8')
            runtime.chmod(0o755)
            capture = root / 'argv.bin'
            install = str(root / '한글 SDK; literal $()')
            cache = str(root / '공백 cache')
            result = subprocess.run(['/bin/sh', str(entry), '--cache-root', cache],
                env={**os.environ, 'NUCODE_NCS_INSTALL_ROOT': install, 'HOST_PACKAGE_ARGV_CAPTURE': str(capture)},
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            self.assertEqual(result.returncode, 23, result.stderr)
            argv = capture.read_bytes().decode().rstrip('\0').split('\0')
            self.assertEqual(argv[:2], ['-I', '-B'])
            self.assertTrue(Path(argv[2]).samefile(backend))
            self.assertEqual(argv[3:], ['install', '--install-root', install, '--cache-root', cache])


if __name__ == '__main__':
    unittest.main()
