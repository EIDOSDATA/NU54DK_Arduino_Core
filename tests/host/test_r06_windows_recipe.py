"""! @brief Windows recipe의 공백 launcher 경로와 Python exit 전달을 검증합니다. """
from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


@unittest.skipUnless(os.name == 'nt', 'Windows command recipe contract')
class WindowsRecipeTests(unittest.TestCase):
    def test_copy_rejects_cache_junction_to_another_directory(self):
        from test_r05_identity import BUILDER
        with tempfile.TemporaryDirectory(prefix='nu54-r06-junction-') as folder:
            root = Path(folder)
            installed = root / '설치 공백'
            installed.mkdir()
            (installed / 'release-manifest.json').write_text('{}', encoding='utf-8')
            workspace = root / 'cache'
            workspace.mkdir()
            outside = root / 'outside'
            outside.mkdir()
            sentinel = outside / 'keep.txt'
            sentinel.write_bytes(b'preserve outside cache')
            alias = workspace / 'platform'
            environment = dict(os.environ, NU54_TEST_COPY_ALIAS=str(alias), NU54_TEST_COPY_TARGET=str(outside))
            command = ['powershell.exe', '-NoProfile', '-NonInteractive', '-Command',
                       'New-Item -ItemType Junction -Path $env:NU54_TEST_COPY_ALIAS -Target $env:NU54_TEST_COPY_TARGET | Out-Null']
            subprocess.run(command, env=environment, check=True, capture_output=True, timeout=20)
            try:
                self.assertTrue(alias.is_junction())
                with self.assertRaisesRegex(BUILDER.AdapterError, 'E_PLATFORM_COPY_PATH'):
                    BUILDER.implementation.build.materialize_installed_platform(
                        {'platform_root': installed, 'workspace': workspace})
                self.assertEqual(sentinel.read_bytes(), b'preserve outside cache')
                self.assertEqual(sorted(p.name for p in outside.iterdir()), ['keep.txt'])
            finally:
                # Junction 자체만 제거하며 연결 대상 디렉터리는 보존합니다.
                if alias.is_junction():
                    alias.rmdir()

    def test_package_copy_preserves_identity_recovers_bytes_and_rejects_extra_files(self):
        from test_r05_identity import BUILDER
        copy_module = BUILDER.implementation.build
        helper = sys.modules[copy_module.platform_build_root.__module__]
        with tempfile.TemporaryDirectory(prefix='nu54-r06-copy-') as folder:
            root = Path(folder)
            installed = root / '설치 공백'
            installed.mkdir()
            (installed / 'release-manifest.json').write_text('{"schema_version": 1}', encoding='utf-8')
            source = installed / 'libraries/Test/src/Test.cpp'
            source.parent.mkdir(parents=True)
            source.write_bytes(b'int identity = 54;\n')
            workspace = root / 'cache'
            paths = {'platform_root': installed, 'workspace': workspace}
            copy_module.materialize_installed_platform(paths)
            mirror = helper.platform_compiled_path(source, paths)
            self.assertEqual(mirror.read_bytes(), source.read_bytes())
            self.assertEqual(paths['platform_root'], installed)
            self.assertEqual(helper.platform_compiled_path(root / 'external.cpp', paths), root / 'external.cpp')
            mirror.write_bytes(b'corrupted')
            copy_module.materialize_installed_platform(paths)
            self.assertEqual(mirror.read_bytes(), source.read_bytes())
            build = root / 'arduino-build'
            sketch = root / 'sketch'
            sketch.mkdir()
            source_paths = dict(paths, build_path=build, sketch_root=sketch, app=workspace / 'app')
            _, provenance, _ = BUILDER.write_source_manifest(source_paths,
                [{'source': str(source), 'include_dirs': [str(source.parent)]}])
            self.assertEqual(provenance['sources'][0]['source_path'], source.as_posix())
            self.assertEqual(provenance['sources'][0]['compiled_path'], mirror.as_posix())
            self.assertEqual(provenance['sources'][0]['sha256'], BUILDER.file_sha256(mirror))
            expected = {'platform_build_copy': {'content': BUILDER.tree_content_sha256(installed, ('.',))}}
            helper.validate_platform_copy(paths, expected)
            source.write_bytes(b'changed after key calculation')
            with self.assertRaisesRegex(BUILDER.AdapterError, 'E_PLATFORM_COPY_STALE'):
                helper.validate_platform_copy(paths, expected)
            copy_module.materialize_installed_platform(paths)
            with self.assertRaisesRegex(BUILDER.AdapterError, 'E_PLATFORM_COPY_STALE'):
                helper.validate_platform_copy(paths, expected)
            (workspace / 'platform/extra.cpp').write_bytes(b'unexpected')
            with self.assertRaisesRegex(BUILDER.AdapterError, 'E_PLATFORM_COPY_INTEGRITY'):
                copy_module.materialize_installed_platform(paths)
            with self.assertRaisesRegex(BUILDER.AdapterError, 'E_SDK_BUILD_PATH'):
                helper.platform_build_root(dict(paths, workspace=root / 'cache space'))

    def test_checkout_and_ascii_install_keep_original_build_root(self):
        from test_r05_identity import BUILDER
        helper = BUILDER.implementation.build
        with tempfile.TemporaryDirectory(prefix='nu54-r06-root-') as folder:
            root = Path(folder)
            (root / 'release-manifest.json').write_text('{}', encoding='utf-8')
            self.assertEqual(helper.platform_build_root({'platform_root': root}), root)
            checkout = root / '체크아웃 공백'
            (checkout / '.git').mkdir(parents=True)
            (checkout / 'release-manifest.json').write_text('{}', encoding='utf-8')
            self.assertEqual(helper.platform_build_root({'platform_root': checkout}), checkout)

    def test_installed_command_preserves_quoted_paths_and_exit(self):
        properties = dict(line.split('=', 1) for line in
                          (ROOT / 'platform.txt').read_text(encoding='utf-8').splitlines()
                          if line and not line.startswith('#') and '=' in line)
        with tempfile.TemporaryDirectory(prefix='NU54 설치 공백 ') as directory:
            installed = Path(directory) / '설치본'
            shutil.copytree(ROOT / 'tools/nu54-builder', installed / 'tools/nu54-builder',
                            ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
            outside = Path(directory) / '외부 작업 공백'
            outside.mkdir()
            prefix = properties.get('nu54.builder.windows', properties['nu54.builder'])
            prefix = prefix.replace('{runtime.platform.path}', installed.as_posix())
            if not prefix.lower().startswith('cmd.exe '):
                prefix = 'cmd.exe /c ' + prefix
            environment = dict(os.environ, NUCODE_PYTHON=sys.executable, PYTHONPATH=str(outside))
            for arguments, expected in [('prepare --help', 0), ('nonsense', 2)]:
                with self.subTest(arguments=arguments):
                    command = prefix + ' ' + arguments + ' --platform-root "' + str(installed) + '"'
                    result = subprocess.run(command, cwd=outside, env=environment,
                                            capture_output=True, encoding='utf-8', timeout=30)
                    self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
                    self.assertIn('usage: nu54-builder', result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
