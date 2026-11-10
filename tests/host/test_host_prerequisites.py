"""! @brief HOST-W04의 고정 자산·명령·부분 설치 거부를 검증합니다. """
from __future__ import annotations

import copy
import hashlib
import importlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('host_w04_builder', ROOT / 'tools/nu54-builder/src/nu54_builder.py')
BUILDER = importlib.util.module_from_spec(spec)
spec.loader.exec_module(BUILDER)
P = importlib.import_module(BUILDER.implementation.__name__ + '.prerequisites')


class HostPrerequisiteTests(unittest.TestCase):
    """! @brief 모의 보드 PASS가 아닌 설치 backend의 positive·negative 계약입니다. """

    def setUp(self):
        """! @brief 새 임시 경로와 원형 platform pin을 준비합니다. """
        self.temporary = tempfile.TemporaryDirectory(prefix='nu54-host-w04-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.manifest = P.load_manifest()

    def test_fixed_versions_and_three_distinct_bundles(self):
        """! @brief SDK는 같고 OS별 bundle은 공식 고정 값임을 확인합니다. """
        self.assertEqual({key: pin['toolchain']['bundle_id'] for key, pin in self.manifest['platforms'].items()}, P.BUNDLES)
        legacy = json.loads((ROOT / 'tools/nu54-prerequisites/pins.json').read_text())
        windows = self.manifest['platforms']['windows-x86_64']
        self.assertEqual(windows['nrfutil']['executable']['sha256'], legacy['nrfutil']['sha256'])
        self.assertEqual(self.manifest['ncs']['revision'], legacy['ncs']['revision'])

    def test_duplicate_json_and_wrong_sdk_revision_are_rejected(self):
        """! @brief 중복 pin과 다른 SDK가 설치 전에 거부됩니다. """
        path = self.root / 'pins.json'
        path.write_text('{"schema_version":1,"schema_version":1}')
        with self.assertRaisesRegex(P.AdapterError, 'E_HOST_JSON'):
            P.load_manifest(path)
        changed = copy.deepcopy(self.manifest)
        changed['ncs']['revision'] = '0' * 40
        path.write_text(json.dumps(changed))
        with self.assertRaisesRegex(P.AdapterError, 'E_HOST_SDK_PIN'):
            P.load_manifest(path)

    def test_unsupported_os_architecture_and_emulation_are_rejected(self):
        """! @brief native Ubuntu AMD64 외 Linux와 emulation을 승인하지 않습니다. """
        for arguments in (
            dict(system_name='Linux', machine='arm64', distribution='ubuntu', version='24.04'),
            dict(system_name='Linux', machine='x86_64', distribution='debian', version='13'),
            dict(system_name='Darwin', machine='arm64', version='26', native=False),
        ):
            with self.subTest(arguments=arguments), self.assertRaises(P.AdapterError):
                P.select_platform(self.manifest, BUILDER.describe_host(**arguments))

    def test_relative_root_and_non_official_asset_fail_closed(self):
        """! @brief CWD 의존 경로와 검증되지 않은 배포 주소를 거부합니다. """
        for value in ('', 'relative/path'):
            with self.assertRaisesRegex(P.AdapterError, 'E_HOST_PATH'):
                P.absolute_root(value)
        asset = {'url': 'https://example.com/tool', 'sha256': 'a' * 64, 'size': 1}
        with self.assertRaisesRegex(P.AdapterError, 'E_HOST_ASSET_URL'):
            P.validate_asset(asset)

    def test_actual_wsl_host_is_not_native_supported(self):
        """! @brief 실제 Host 탐색에서 WSL을 native Ubuntu 지원으로 오인하지 않습니다. """
        host = BUILDER.implementation.host
        with mock.patch.object(host.platform, 'system', return_value='Linux'), \
             mock.patch.object(host.platform, 'machine', return_value='x86_64'), \
             mock.patch.object(host.platform, 'release', return_value='5.15.0-microsoft-standard-WSL2'), \
             mock.patch.object(host, 'linux_release', return_value=('ubuntu', '24.04')):
            descriptor = host.describe_host()
        self.assertFalse(descriptor['native'])
        self.assertFalse(descriptor['supported'])

    def test_macos_sdk_root_is_fixed_without_changing_permissions(self):
        """! @brief macOS 고정 위치와 사용자 권한 준비 경계를 유지합니다. """
        pin = self.manifest['platforms']['macos-arm64']
        with self.assertRaisesRegex(P.AdapterError, 'E_HOST_INSTALL_ROOT'):
            P.roots(pin, self.root / 'state', self.root / 'sdk')

    def test_download_verifies_bytes_and_does_not_publish_partial_file(self):
        """! @brief 손상된 다운로드는 cache 완료 파일이 되지 않습니다. """
        data = b'official-fixed-bytes'
        asset = {'url': 'https://files.nordicsemi.com/pinned-tool', 'sha256': hashlib.sha256(data).hexdigest(), 'size': len(data)}
        def response(payload):
            """! @brief HTTPS 응답을 byte 단위로 대체합니다. """
            stream = io.BytesIO(payload)
            stream.geturl = lambda: asset['url']
            return stream
        cache = self.root / 'cache'
        with mock.patch.object(P.urllib.request, 'urlopen', return_value=response(b'truncated')):
            with self.assertRaisesRegex(P.AdapterError, 'E_HOST_DOWNLOAD_HASH'):
                P.checked_download(asset, cache)
        self.assertEqual(list(cache.iterdir()), [])
        with mock.patch.object(P.urllib.request, 'urlopen', return_value=response(data)):
            path = P.checked_download(asset, cache)
        self.assertEqual(path.read_bytes(), data)
        path.write_bytes(b'changed')
        with self.assertRaisesRegex(P.AdapterError, 'E_HOST_DOWNLOAD_HASH'):
            P.checked_download(asset, cache)

    def test_failed_command_and_timeout_cannot_be_success(self):
        """! @brief 실행 실패·timeout은 호출자에게 오류로 전달합니다. """
        with mock.patch.object(P.subprocess, 'run', return_value=subprocess.CompletedProcess(['tool'], 7, 'original failure')):
            with self.assertRaisesRegex(P.AdapterError, 'code=7.*original failure'):
                P.run(['tool'], {})
        with mock.patch.object(P.subprocess, 'run', side_effect=subprocess.TimeoutExpired(['tool'], 1)):
            with self.assertRaisesRegex(P.AdapterError, 'E_HOST_COMMAND'):
                P.run(['tool'], {}, 1)

    def test_wrong_bootstrap_core_cannot_create_ready_marker(self):
        """! @brief core9가 관측되면 SDK 설치·ready 승격 전 거부합니다. """
        key = 'windows-x86_64'
        data = b'launcher-fixture'
        fixture = self.root / 'fixture'
        fixture.write_bytes(data)
        document = copy.deepcopy(self.manifest)
        document['platforms'][key]['nrfutil']['executable']['sha256'] = hashlib.sha256(data).hexdigest()
        state = self.root / 'state'
        with mock.patch.object(P, 'checked_download', return_value=fixture), mock.patch.object(P, 'run', return_value='nrfutil 9.0.0'):
            with self.assertRaisesRegex(P.AdapterError, 'E_HOST_TOOL_VERSION'):
                P.bootstrap(document, key, state, self.root / 'cache')
        self.assertFalse((state / 'ready.json').exists())

    def test_official_multiline_version_and_wrong_architecture_noise(self):
        """! @brief 실제 8.2.1 다중 행 출력은 허용하고 core9·다른 Host·잡음은 거부합니다. """
        target = 'x86_64-pc-windows-msvc'
        original = ('nrfutil 8.2.1 (350d1fd 2026-08-11)\n'
            'commit-hash: 350d1fdcdf82d30c115ebb08bdbb9717937f37ac\n'
            'commit-date: 2026-08-11\nhost: ' + target + '\n'
            'build-timestamp: 2026-08-11T14:43:47.659864572Z\nclassification: nrf-external\n')
        P.verify_version_output(original, 'nrfutil', '8.2.1', target)
        for changed in (original.replace('8.2.1', '9.0.0'), original + 'unexpected output\n',
                        original.replace(target, 'aarch64-apple-darwin')):
            with self.subTest(output=changed), self.assertRaises(P.AdapterError):
                P.verify_version_output(changed, 'nrfutil', '8.2.1', target)

    def test_plan_has_no_install_or_network_side_effects(self):
        """! @brief 계획 조회는 환경 설치나 SDK 검증 실적으로 바뀌지 않습니다. """
        with mock.patch.object(P, 'checked_download', side_effect=AssertionError('network forbidden')):
            with mock.patch.object(P, 'run', side_effect=AssertionError('execution forbidden')):
                install = Path('/opt/nordic/ncs') if sys.platform == 'darwin' else self.root / 'sdk'
                self.assertEqual(P.main(['plan', '--state-root', str(self.root / 'state'), '--install-root', str(install)]), 0)
        self.assertFalse((self.root / 'state').exists())


if __name__ == '__main__':
    unittest.main()
