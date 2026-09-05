"""! @brief 압축 해제 entry의 -I 로딩과 내부 모듈 경계를 검증합니다. """
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'tools/nu54-builder/src'


class BuilderPackageTests(unittest.TestCase):
    def test_extracted_entry_isolated_from_cwd_and_pythonpath(self):
        with tempfile.TemporaryDirectory(prefix='NU54 설치 공백 ') as folder:
            root = Path(folder)
            archive = root / 'entry.zip'
            with zipfile.ZipFile(archive, 'w') as output:
                for path in [SOURCE / 'nu54_builder.py', *sorted((SOURCE / 'nu54_builder_impl').glob('*.py'))]:
                    output.write(path, path.relative_to(SOURCE).as_posix())
            installed = root / '설치본'
            with zipfile.ZipFile(archive) as zipped:
                zipped.extractall(installed)
            outside = root / '외부 작업 폴더'
            outside.mkdir()
            poison = outside / 'nu54_builder_impl'
            poison.mkdir()
            (poison / '__init__.py').write_text('raise RuntimeError("untrusted cwd loaded")\n', encoding='utf-8')
            (outside / 'nu54_builder.py').write_text('raise RuntimeError("untrusted entry loaded")\n', encoding='utf-8')
            environment = dict(os.environ, PYTHONPATH=str(outside), PYTHONUTF8='1')
            for args in [['--help'], ['prepare', '--help'], ['flash', '--help'], ['nonsense']]:
                with self.subTest(args=args):
                    command = [sys.executable, '-I', str(installed / 'nu54_builder.py'), *args]
                    result = subprocess.run(command, cwd=outside, env=environment, capture_output=True, timeout=20)
                    baseline = subprocess.run([sys.executable, '-I', str(SOURCE / 'nu54_builder.py'), *args],
                                              cwd=outside, env=environment, capture_output=True, timeout=20)
                    self.assertEqual((result.returncode, result.stdout, result.stderr),
                                     (baseline.returncode, baseline.stdout, baseline.stderr))
                    self.assertEqual(result.returncode, 2 if args == ['nonsense'] else 0)

    def test_source_package_includes_explicit_models_and_launcher(self):
        from test_r05_identity import BUILDER, PACKAGE
        implementation = BUILDER.implementation
        self.assertTrue(BUILDER.load_configuration_profile.__module__.endswith('.configuration'))
        self.assertTrue(BUILDER.write_source_manifest.__module__.endswith('.source_graph'))
        self.assertTrue(BUILDER.publish_artifact_generation.__module__.endswith('.artifacts'))
        self.assertTrue(BUILDER.build_lock.__module__.endswith('.locking'))
        self.assertTrue(BUILDER.prepare.__module__.endswith('.build'))
        self.assertTrue(BUILDER.flash.__module__.endswith('.upload'))
        self.assertIn('product_identity', implementation.build.BuildContext.__required_keys__)
        self.assertIn('compiler', implementation.environment.ToolEnvironment.__required_keys__)
        self.assertIn('source_inputs', implementation.build.ArtifactManifest.__required_keys__)
        for path in (SOURCE / 'nu54_builder_impl').glob('*.py'):
            self.assertTrue(PACKAGE.include_core_path(path.relative_to(ROOT).as_posix()))
        launcher = (ROOT / 'tools/nu54-builder/nu54-builder.cmd').read_text(encoding='utf-8')
        self.assertIn('-I "%~dp0src\\nu54_builder.py"', launcher)


if __name__ == '__main__':
    unittest.main()
