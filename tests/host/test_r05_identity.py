"""! @brief source와 설치 version의 CMake/builder/package identity 계약을 검증합니다. """
import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


BUILDER = load('r05_builder', 'tools/nu54-builder/src/nu54_builder.py')
PACKAGE = load('r05_package', 'packaging/boards-manager/nu54_package.py')
DRIFT = load('r05_drift', 'tools/ci/verify_product_identity.py')


class ProductIdentityTests(unittest.TestCase):
    def test_payload_identity_tracks_source_but_allows_package_stamping(self):
        header_path = 'cores/arduino/internal/CoreIdentity.h'
        header = (ROOT / header_path).read_bytes()
        platform = (ROOT / 'platform.txt').read_bytes()
        def digest(version, source):
            return PACKAGE.runtime_payload_sha256([
                (header_path, source, 0o644),
                ('platform.txt', PACKAGE.rewrite_platform_version(platform, version), 0o644)])
        self.assertEqual(digest('0.0.90', header), digest('0.4.0-rc.1', header))
        self.assertNotEqual(digest('0.0.90', header),
                            digest('0.0.90', header.replace(b'0.4.0-dev', b'0.4.1-dev')))

    def test_checkout_drift_is_detected_and_regenerated(self):
        with tempfile.TemporaryDirectory(prefix='NU54 drift ') as folder:
            root = Path(folder)
            header = root / 'cores/arduino/internal/CoreIdentity.h'
            header.parent.mkdir(parents=True)
            shutil.copyfile(ROOT / header.relative_to(root), header)
            (root / 'platform.txt').write_text('name=N\nversion=0.3.0\nrecipe=unchanged\n', encoding='utf-8')
            with self.assertRaises(DRIFT.BUILDER.AdapterError):
                DRIFT.verify(root)
            self.assertEqual(DRIFT.verify(root, True)['package_version'], '0.4.0-dev')
            self.assertEqual((root / 'platform.txt').read_text(),
                             'name=N\nversion=0.4.0-dev\nrecipe=unchanged\n')

    def test_live_build_record_carries_both_versions(self):
        with tempfile.TemporaryDirectory(prefix='NU54 record ') as folder:
            root = Path(folder)
            header = root / 'cores/arduino/internal/CoreIdentity.h'
            header.parent.mkdir(parents=True)
            shutil.copyfile(ROOT / header.relative_to(root), header)
            (root / 'platform.txt').write_text('version=0.0.90\n', encoding='utf-8')
            output = root / 'record.yml'
            process = subprocess.run([shutil.which('cmake'), f'-DNUCODE_CORE_ROOT={root.as_posix()}',
                                      f'-DNUCODE_APPLICATION_SOURCE_DIR={root.as_posix()}',
                                      f'-DNUCODE_BUILD_RECORD={output.as_posix()}',
                                      '-P', str(ROOT / 'zephyr/cmake/write_build_record.cmake')],
                                     capture_output=True, timeout=15)
            self.assertEqual(process.returncode, 0, process.stderr.decode(errors='replace'))
            self.assertIn("source_version: '0.4.0-dev'", output.read_text())
            self.assertIn("package_version: '0.0.90'", output.read_text())

    def test_checkout_identity_and_schema_independence(self):
        identity = BUILDER.load_product_identity(ROOT)
        self.assertEqual(identity, {'source_version': '0.4.0-dev', 'package_version': '0.4.0-dev'})
        self.assertEqual(BUILDER.ADAPTER_VERSION, '0.1.0-dev.m10')
        self.assertEqual((BUILDER.CACHE_SCHEMA_VERSION, BUILDER.ARTIFACT_MANIFEST_SCHEMA_VERSION,
                          BUILDER.SESSION_CONTEXT_SCHEMA_VERSION, BUILDER.SOURCE_RECORD_SCHEMA_VERSION),
                         (1, 2, 2, 2))

    def test_stamped_install_preserves_source_version(self):
        with tempfile.TemporaryDirectory(prefix='NU54 설치 경로 ') as folder:
            platform = Path(folder)
            header = platform / 'cores/arduino/internal/CoreIdentity.h'
            header.parent.mkdir(parents=True)
            shutil.copyfile(ROOT / header.relative_to(platform), header)
            (platform / 'platform.txt').write_bytes(PACKAGE.rewrite_platform_version(
                (ROOT / 'platform.txt').read_bytes(), '0.0.90'))
            self.assertEqual(BUILDER.load_product_identity(platform),
                             {'source_version': '0.4.0-dev', 'package_version': '0.0.90'})
            (platform / 'platform.txt').write_bytes(PACKAGE.rewrite_platform_version(
                (platform / 'platform.txt').read_bytes(), '0.4.0-rc.1'))
            self.assertEqual(BUILDER.load_product_identity(platform)['source_version'], '0.4.0-dev')
            self.assertEqual(BUILDER.load_product_identity(platform)['package_version'], '0.4.0-rc.1')

    def test_cmake_matches_builder_and_rejects_invalid_identity(self):
        cmake = shutil.which('cmake')
        self.assertIsNotNone(cmake)
        with tempfile.TemporaryDirectory(prefix='NU54 identity ') as folder:
            platform = Path(folder)
            header = platform / 'cores/arduino/internal/CoreIdentity.h'
            header.parent.mkdir(parents=True)
            header.write_text('#define NUCODE_CORE_SOURCE_VERSION "0.4.0-dev"\n', encoding='utf-8')
            script = platform / 'identity.cmake'
            output = platform / 'identity.txt'
            script.write_text(f'include("{ROOT.as_posix()}/zephyr/cmake/product_identity.cmake")\n'
                              f'nucode_product_identity("{platform.as_posix()}" source package)\n'
                              f'file(WRITE "{output.as_posix()}" "${{source}}|${{package}}")\n', encoding='utf-8')
            for content in ['version=0.0.90\n', 'version=0.4.0-rc.1\n', 'version=0.4.0+local.1\n',
                            'version=\n', 'name=N\n', 'version=1.2.3\nversion=1.2.3\n', 'version=x/../y\n']:
                with self.subTest(content=content):
                    (platform / 'platform.txt').write_text(content, encoding='utf-8')
                    process = subprocess.run([cmake, '-P', str(script)], capture_output=True, timeout=15)
                    if content.startswith(('version=0.0.90', 'version=0.4.0-rc', 'version=0.4.0+')):
                        self.assertEqual(process.returncode, 0, process.stderr.decode(errors='replace'))
                        identity = BUILDER.load_product_identity(platform)
                        self.assertEqual(output.read_text(), identity['source_version']+'|'+identity['package_version'])
                    else:
                        self.assertNotEqual(process.returncode, 0)
                        with self.assertRaises(BUILDER.AdapterError):
                            BUILDER.load_product_identity(platform)
            (platform / 'platform.txt').write_text('version=0.4.0-dev\n', encoding='utf-8')
            header.write_text('#define NUCODE_CORE_SOURCE_VERSION "bad"\n', encoding='utf-8')
            self.assertNotEqual(subprocess.run([cmake, '-P', str(script)], capture_output=True).returncode, 0)
            with self.assertRaises(BUILDER.AdapterError):
                BUILDER.load_product_identity(platform)


if __name__ == '__main__':
    unittest.main()
