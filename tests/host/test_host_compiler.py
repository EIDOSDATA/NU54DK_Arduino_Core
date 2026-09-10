"""! @brief Host 도구 선택의 경로·인자 보존과 잘못된 환경의 명시적 실패를 검증합니다. """

import unittest
from unittest.mock import patch

from host_compiler import compiler_command, run_executable


class HostCompilerTests(unittest.TestCase):
    def test_explicit_compiler_and_arguments_preserve_spaces(self):
        environment = {"CXX": "C:/Program Files/LLVM/clang++.exe",
                       "NUCODE_HOST_CXX_FLAGS": '["--target=x86_64-w64-windows-gnu", "--sysroot=C:/SDK with spaces"]'}
        with patch.dict("os.environ", environment, clear=True), patch("host_compiler.shutil.which", side_effect=lambda name: name):
            self.assertEqual(compiler_command(), [environment["CXX"], "--target=x86_64-w64-windows-gnu", "--sysroot=C:/SDK with spaces"])

    def test_missing_explicit_compiler_does_not_fall_back_or_skip(self):
        with patch.dict("os.environ", {"CXX": "missing"}, clear=True), patch("host_compiler.shutil.which", return_value=None) as which:
            with self.assertRaisesRegex(AssertionError, "unavailable"):
                compiler_command(optional=True)
            which.assert_called_once_with("missing")

    def test_defaults_preserve_gcc_first_selection(self):
        with patch.dict("os.environ", {}, clear=True), patch("host_compiler.shutil.which", side_effect=lambda name: "/bin/" + name):
            self.assertEqual(compiler_command(), ["/bin/g++"])
            self.assertEqual(compiler_command("c"), ["/bin/gcc"])

    def test_c_flags_are_independent_of_cxx_flags(self):
        environment = {"CC": "clang", "CXX": "clang++", "NUCODE_HOST_CC_FLAGS": '["-target", "x86_64-w64-windows-gnu"]',
                       "NUCODE_HOST_CXX_FLAGS": '["-stdlib=libc++"]'}
        with patch.dict("os.environ", environment, clear=True), patch("host_compiler.shutil.which", side_effect=lambda name: name):
            self.assertEqual(compiler_command("c"), ["clang", "-target", "x86_64-w64-windows-gnu"])

    def test_invalid_flags_are_rejected_without_shell_parsing(self):
        for flags in ('invalid', '{}', '"-O2"', '[1]'):
            with self.subTest(flags=flags), patch.dict("os.environ", {"NUCODE_HOST_CXX_FLAGS": flags}, clear=True), patch("host_compiler.shutil.which", return_value="g++"):
                with self.assertRaisesRegex(AssertionError, "JSON string array"):
                    compiler_command()

    def test_optional_absence_and_invalid_language(self):
        with patch.dict("os.environ", {}, clear=True), patch("host_compiler.shutil.which", return_value=None):
            self.assertIsNone(compiler_command(optional=True))
            with self.assertRaises(AssertionError):
                compiler_command()
            with self.assertRaises(ValueError):
                compiler_command("rust")

    def test_application_control_start_race_is_retried_with_a_bound(self):
        blocked = OSError("blocked")
        blocked.winerror = 4551
        completed = object()
        with patch("host_compiler.os.name", "nt"), \
                patch("host_compiler.subprocess.run", side_effect=[blocked, completed]) as runner, \
                patch("host_compiler.time.sleep") as sleeper:
            self.assertIs(run_executable(["generated.exe"]), completed)
        self.assertEqual(runner.call_count, 2)
        sleeper.assert_called_once_with(0.25)

    def test_non_policy_start_error_is_not_retried(self):
        failure = OSError("missing")
        failure.winerror = 2
        with patch("host_compiler.os.name", "nt"), \
                patch("host_compiler.subprocess.run", side_effect=failure) as runner:
            with self.assertRaises(OSError):
                run_executable(["missing.exe"])
        runner.assert_called_once()


if __name__ == "__main__":
    unittest.main()
