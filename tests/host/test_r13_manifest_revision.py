"""! @brief 실제 CMake로 Git-less package의 고정 revision 복원과 잘못된 값을 검증합니다. """
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
CORE = '499fde3931248fe44f94bab3dc656bfef5111a38'
BOARD = 'fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3'


class ManifestRevisionTests(unittest.TestCase):
    """! @brief configure와 매 build writer 모두 같은 유효 revision을 복원해야 합니다. """

    def run_cmake(self, *arguments):
        """! @brief mock 없이 설치된 CMake를 실행하고 성공 출력을 확인합니다. """
        cmake = shutil.which('cmake')
        self.assertIsNotNone(cmake)
        result = subprocess.run([cmake, *map(str, arguments)], capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))

    def test_configure_and_live_parsers_validate_full_revision(self):
        """! @brief 40자리 대소문자 SHA와 길이·문자·JSON 오류를 두 실제 함수에서 검증합니다. """
        cases = [
            (json.dumps({'core_revision': CORE}), CORE),
            (json.dumps({'core_revision': CORE.upper()}), CORE),
            (json.dumps({'core_revision': CORE[:-1]}), 'unknown'),
            (json.dumps({'core_revision': CORE + 'a'}), 'unknown'),
            (json.dumps({'core_revision': 'g' + CORE[1:]}), 'unknown'),
            (json.dumps({'core_revision': ' ' + CORE}), 'unknown'),
            (json.dumps({'core_revision': None}), 'unknown'),
            ('{}', 'unknown'),
            ('not JSON', 'unknown'),
        ]
        with tempfile.TemporaryDirectory(prefix='NU54 R13 revision ') as folder:
            root = Path(folder)
            manifest = root / 'release-manifest.json'
            output = root / 'result.txt'
            for name in ['source_provenance.cmake', 'write_build_record.cmake']:
                text = (ROOT / 'zephyr/cmake' / name).read_text(encoding='utf-8')
                start = text.index('function(nucode_release_manifest_revision ')
                end = text.index('endfunction()', start) + len('endfunction()')
                script = root / 'parser.cmake'
                script.write_text(
                    'cmake_minimum_required(VERSION 3.20.0)\n'
                    + text[start:end]
                    + f'\nset(NUCODE_CORE_ROOT "{root.as_posix()}")\n'
                    + f'set(NUCODE_ARDUINO_CORE_ROOT "{root.as_posix()}")\n'
                    + 'nucode_release_manifest_revision(core_revision result)\n'
                    + f'file(WRITE "{output.as_posix()}" "${{result}}")\n',
                    encoding='utf-8',
                )
                for content, expected in cases:
                    with self.subTest(parser=name, manifest=content):
                        manifest.write_text(content, encoding='utf-8')
                        self.run_cmake('-P', script)
                        self.assertEqual(output.read_text(encoding='utf-8'), expected)
                manifest.unlink()
                self.run_cmake('-P', script)
                self.assertEqual(output.read_text(encoding='utf-8'), 'unknown')

    def test_live_writer_restores_core_and_board_from_gitless_manifest(self):
        """! @brief 실제 build record writer가 package의 Core·board SHA를 YAML에 기록합니다. """
        with tempfile.TemporaryDirectory(prefix='NU54 R13 record ') as folder:
            root = Path(folder)
            header = root / 'cores/arduino/internal/CoreIdentity.h'
            header.parent.mkdir(parents=True)
            shutil.copyfile(ROOT / header.relative_to(root), header)
            (root / 'platform.txt').write_text('version=0.0.90\n', encoding='utf-8')
            (root / 'release-manifest.json').write_text(
                json.dumps({'core_revision': CORE, 'board_revision': BOARD.upper()}),
                encoding='utf-8',
            )
            board_root = root / 'board'
            board_root.mkdir()
            output = root / 'record.yml'
            self.run_cmake(
                f'-DNUCODE_CORE_ROOT={root.as_posix()}',
                f'-DNUCODE_APPLICATION_SOURCE_DIR={root.as_posix()}',
                f'-DNUCODE_BOARD_PACKAGE_ROOT={board_root.as_posix()}',
                f'-DNUCODE_BUILD_RECORD={output.as_posix()}',
                '-P', ROOT / 'zephyr/cmake/write_build_record.cmake',
            )
            record = output.read_text(encoding='utf-8')
            self.assertIn(f"core_revision: '{CORE}'", record)
            self.assertIn(f"board_revision: '{BOARD}'", record)


if __name__ == '__main__':
    unittest.main()
