"""! @brief native CI consumer의 검증 경계·격리 환경·늦은 실패 판정을 검사합니다. """
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import types
import unittest
from unittest import mock
import zipfile

from tests.host.test_host_artifact_semantics import arm_image, ihex

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('host_native_consumer_unit', ROOT / 'tools/ci/host_native_package_consumer.py')
C = importlib.util.module_from_spec(spec)
spec.loader.exec_module(C)
builder_spec = importlib.util.spec_from_file_location('host_native_consumer_unit_builder', ROOT / 'tools/nu54-builder/src/nu54_builder.py')
B = importlib.util.module_from_spec(builder_spec)
builder_spec.loader.exec_module(B)


class HostNativeConsumerTests(unittest.TestCase):
    """! @brief fake SDK fixture를 물리·실제 설치 PASS로 승격하지 않는 단위 검사입니다. """

    def setUp(self):
        """! @brief SDK·작업본 밖의 새 임시 파일만 사용합니다. """
        self.temporary = tempfile.TemporaryDirectory(prefix='native-consumer-unit-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()

    def test_download_verifies_received_bytes_and_preserves_failed_attempt(self):
        """! @brief 고정 hash에 맞는 byte만 승인하고 다른 byte의 실패 파일도 덮어쓰지 않습니다. """
        data = b'official-fixture-archive'
        asset = {'url': 'https://example.invalid/arduino-cli.zip', 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
        with mock.patch.object(C.urllib.request, 'urlopen', return_value=io.BytesIO(data)):
            path = C.download(asset, self.root / 'valid')
        self.assertEqual(path.read_bytes(), data)
        with mock.patch.object(C.urllib.request, 'urlopen', return_value=io.BytesIO(b'X' * len(data))):
            with self.assertRaises(ValueError):
                C.download(asset, self.root / 'bad')
        self.assertEqual((self.root / 'bad/arduino-cli.zip').read_bytes(), b'X' * len(data))
        with self.assertRaises(FileExistsError):
            C.download(asset, self.root / 'bad')

    def test_cli_zip_cannot_escape_the_new_extraction_root(self):
        """! @brief 공식 hash 검사의 뒤에서도 archive 탈출 경로를 허용하지 않습니다. """
        path = self.root / 'unsafe.zip'
        with zipfile.ZipFile(path, 'w') as stream:
            stream.writestr('../escaped.exe', b'bad')
        with self.assertRaises(ValueError):
            C.unpack_cli(path, self.root / 'cli', True)
        self.assertFalse((self.root / 'escaped.exe').exists())

    def test_child_environment_has_no_CI_tokens_or_system_python_fallback(self):
        """! @brief 부모 환경은 유지하고 자식만 고정 도구·state·작업자 경계로 제한합니다. """
        initial_path = os.environ.get('PATH')
        with mock.patch.dict(os.environ, {'GITHUB_TOKEN': 'unit-dummy-only', 'ACTIONS_RUNTIME_TOKEN': 'unit-dummy-only'}):
            environment = C.consumer_environment(self.root, 'windows' if os.name == 'nt' else 'linux', self.root / 'sdk')
            self.assertFalse('GITHUB_TOKEN' in environment, 'CI token이 자식 환경에 남았습니다.')
            self.assertFalse('ACTIONS_RUNTIME_TOKEN' in environment, 'CI token이 자식 환경에 남았습니다.')
            self.assertEqual(os.environ.get('PATH'), initial_path)
        self.assertEqual(environment['NUCODE_BUILD_JOBS'], '2')
        self.assertEqual(environment['NUCODE_PREREQUISITE_STATE_ROOT'], str(self.root / 'state'))
        if os.name != 'nt':
            with self.assertRaises(RuntimeError):
                C.run(['git', '--version'], environment, self.root / 'logs/forbidden.log', 5)
            self.assertIn(b'HOST_FORBIDDEN_SYSTEM_TOOL:git', (self.root / 'logs/forbidden.log').read_bytes())

    def manifest_fixture(self):
        """! @brief source·profile·SDK·artifact가 독립 검증되는 최소 build record를 준비합니다. """
        source = '1' * 40
        fqbn = 'nucode:zephyr:nu54dk:feature_set=standard'
        build = self.root / 'build'
        sketch = self.root / 'sketch'
        build.mkdir()
        sketch.mkdir()
        pins = json.loads((ROOT / 'tools/nu54-prerequisites/platform-pins.json').read_text(encoding='utf-8'))
        artifacts = {}
        for name, data in (('elf', arm_image()), ('hex', (ihex(0, 0, b'ABCD') + ihex(1)).encode())):
            path = build / ('app.' + name)
            path.write_bytes(data)
            artifacts[name] = {'path': str(path), 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
        host = B.describe_host()
        context = {'source_revision': source, 'host': host, 'bundle_id': 'dcbdc366a1'}
        inputs = {'adapter': {'embedded_core_revision': source}, 'board_package': {'revision': pins['board_revision']},
            'ncs': {'nrf_revision': pins['ncs']['revision'], 'zephyr_revision': pins['zephyr']['revision']},
            'toolchain': {'bundle_id': context['bundle_id']}, 'host': host, 'sketch': {'root': str(sketch)},
            'target': {'fqbn': fqbn, 'board': C.EXAMPLES.TARGET_BOARD, 'profile': 'standard', 'sysbuild': False}}
        manifest = {'fqbn': fqbn, 'board': C.EXAMPLES.TARGET_BOARD, 'sysbuild': False,
            'artifacts': artifacts, 'cache': {'input_manifest': inputs},
            'resource_audit': {'flash': {'used_bytes': 4}, 'ram': {'used_bytes': 0}}}
        return manifest, build, sketch, fqbn, context

    def test_inaccessible_OS_admin_file_does_not_abort_the_consumer(self):
        """! @brief macOS weakpass_edit 같은 보호된 관리 파일 조회 실패는 필수 도구 설치 실패가 아닙니다. """
        protected = mock.Mock()
        protected.name = 'weakpass_edit'
        protected.is_file.side_effect = PermissionError('protected system administration entry')
        with mock.patch.object(C.os, 'access', return_value=True):
            self.assertFalse(C.eligible_os_executable(protected))
        protected.name = 'python3'
        protected.is_file.reset_mock()
        self.assertFalse(C.eligible_os_executable(protected))
        protected.is_file.assert_not_called()

    def test_exit_zero_manifest_cannot_hide_wrong_source_bundle_or_artifact(self):
        """! @brief 성공 exit만으로 다른 source·SDK·실제 ELF byte를 승인하지 않습니다. """
        manifest, build, sketch, fqbn, context = self.manifest_fixture()
        self.assertEqual(set(C.validate_compiled(manifest, build, sketch, fqbn, context, B)), {'elf', 'hex'})
        mutations = (
            lambda value: value['cache']['input_manifest']['adapter'].update(embedded_core_revision='2' * 40),
            lambda value: value['cache']['input_manifest']['toolchain'].update(bundle_id='bad-bundle'),
            lambda value: value['cache']['input_manifest']['target'].update(profile='ble'),
            lambda value: value['artifacts']['elf'].update(sha256='0' * 64),
        )
        for mutate in mutations:
            damaged = json.loads(json.dumps(manifest))
            mutate(damaged)
            with self.assertRaises(ValueError):
                C.validate_compiled(damaged, build, sketch, fqbn, context, B)

    def test_late_signature_failure_never_leaves_a_pass_row(self):
        """! @brief ELF 복사 뒤 서명 검증 실패도 최종 FAIL로 남깁니다. """
        files = {}
        for name, body in (('elf', arm_image()), ('hex', (ihex(0, 0, b'ABCD') + ihex(1)).encode()),
                ('bin', b'signed-fixture'), ('boot.hex', (ihex(0, 0, b'BOOT') + ihex(1)).encode())):
            path = self.root / ('fixture-' + name)
            path.write_bytes(body)
            files[name] = path
        def fake_run(command, _environment, log, _timeout):
            """! @brief 실제 설치·서명이 아닌 실패 처리 검사용 자식 경계입니다. """
            log.parent.mkdir(parents=True, exist_ok=True)
            log.write_bytes(b'unit-log')
            if '--verify-image' in command:
                return subprocess.CompletedProcess(command, 0, b'{"status":"FAIL"}')
            build = Path(command[command.index('--build-path') + 1])
            (build / 'fixture.nu54-build.json').write_text(json.dumps({'sysbuild': True,
                'cache': {'input_manifest': {'toolchain': {'compiler': 'unit-compiler'}}}}), encoding='utf-8')
            return subprocess.CompletedProcess(command, 0, b'')
        context = {'signing_fixture': {'public_key_sha256': 'a' * 64}}
        with mock.patch.object(C, 'run', side_effect=fake_run), mock.patch.object(C, 'validate_compiled', return_value=files):
            row = C.compile_one(0, 'Fixture/Example', {'profile': 'secure_ble_dfu', 'directory': self.root},
                Path('unused-cli'), self.root / 'config', self.root, {'NUCODE_DFU_SIGNING_KEY': str(self.root / 'key')},
                context, B, Path('unused-runtime'), self.root, 5)
        self.assertEqual(row['status'], 'FAIL')
        self.assertEqual(row['error_type'], 'ValueError')

    def test_negative_profile_allows_preparation_longer_than_two_minutes(self):
        """! @brief 준비가 120초를 넘겨도 실제 비성공 exit와 profile marker로만 거부를 승인합니다. """
        case = C.EXAMPLES.NEGATIVE_PROFILE_MATRIX[5]
        observed = []
        def delayed_rejection(command, **options):
            """! @brief 대기 없이 CI의 준비 지연과 뒤따르는 실제 거부 경계를 재현합니다. """
            timeout = options['timeout']
            observed.append(timeout)
            self.assertIsInstance(timeout, (int, float))
            self.assertGreater(timeout, 0)
            self.assertLessEqual(timeout, 600)
            if timeout < 121:
                raise subprocess.TimeoutExpired(command, timeout, output=b'[NU54 2/5] configuration preparation')
            return subprocess.CompletedProcess(command, 1, case['marker'].encode())
        with mock.patch.object(C.subprocess, 'run', side_effect=delayed_rejection):
            row = C.compile_negative(5, case, {case['identity']: {'directory': self.root / 'sketch'}},
                Path('unused-cli'), self.root / 'config', {}, self.root / 'delayed')
        self.assertEqual(row['status'], 'PASS', row)
        self.assertEqual(row['actual_exit_code'], 1)
        self.assertTrue(row['expected_rejection'])
        self.assertEqual(len(observed), 1)

    def test_negative_budget_does_not_accept_zero_exit_wrong_marker_or_artifact(self):
        """! @brief 시간 예산과 무관하게 성공 exit·다른 오류·성공 산출물을 거부합니다. """
        case = C.EXAMPLES.NEGATIVE_PROFILE_MATRIX[5]
        for name, exit_code, output, artifact in (
                ('zero', 0, case['marker'].encode(), False),
                ('wrong-marker', 1, b'compiler unavailable', False),
                ('artifact', 1, case['marker'].encode(), True)):
            with self.subTest(name=name):
                def rejected(command, **options):
                    """! @brief 판정 오류를 숨길 수 있는 세 가지 자식 결과를 만듭니다. """
                    if artifact:
                        build = Path(command[command.index('--build-path') + 1])
                        (build / 'unexpected.elf').write_bytes(b'not an allowed rejection')
                    return subprocess.CompletedProcess(command, exit_code, output)
                with mock.patch.object(C.subprocess, 'run', side_effect=rejected):
                    row = C.compile_negative(5, case, {case['identity']: {'directory': self.root / 'sketch'}},
                        Path('unused-cli'), self.root / 'config', {}, self.root / name)
                self.assertEqual(row['status'], 'FAIL')
                self.assertNotIn('expected_rejection', row)

    def test_non_CI_consumer_cannot_begin_an_SDK_installation(self):
        """! @brief CI 전용 controller를 사용자 PC 설치 도구로 오용하지 않습니다. """
        with mock.patch.dict(os.environ, {'GITHUB_ACTIONS': 'false'}), self.assertRaises(ValueError):
            C.setup(types.SimpleNamespace(), self.root)
        self.assertFalse((self.root / 'ncs').exists())


if __name__ == '__main__':
    unittest.main()
