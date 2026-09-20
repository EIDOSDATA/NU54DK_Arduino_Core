#!/usr/bin/env python3
"""! @brief 실제 PBP source/sink C++ backend를 stub stack 위에서 실행합니다. """

from pathlib import Path
import subprocess
import tempfile
import unittest

from host_compiler import compiler_command, run_executable


ROOT = Path(__file__).resolve().parents[2]
STUBS = ROOT / "tests/host/pbp_runtime_stubs"
SCENARIOS = (
    "m31_pbp_sink_runtime_main.cpp",
    "m31_pbp_source_runtime_main.cpp",
)


class M31PbpRuntimeTests(unittest.TestCase):
    """! @brief PBP callback, BASE 선택과 end/rebegin 경계를 실제 C++로 검증합니다. """

    def test_production_pbp_backends_execute_against_stub_stack(self) -> None:
        """! @brief production translation unit을 포함한 두 실행 파일을 빌드·실행합니다. """
        compiler = compiler_command()
        self.assertIsNotNone(compiler)
        with tempfile.TemporaryDirectory(prefix="nu54-m31-pbp-") as directory:
            temporary = Path(directory)
            for scenario in SCENARIOS:
                with self.subTest(scenario=scenario):
                    binary = temporary / f"{Path(scenario).stem}.exe"
                    command = [
                        *compiler,
                        "-std=gnu++20",
                        "-Wall",
                        "-Wextra",
                        "-Werror",
                        "-Wno-missing-field-initializers",
                        "-Wno-class-memaccess",
                        "-pthread",
                        "-ffunction-sections",
                        "-fdata-sections",
                        "-Wl,--gc-sections",
                        "-include",
                        str(STUBS / "pbp_runtime_stubs.h"),
                        "-I",
                        str(STUBS),
                        "-I",
                        str(ROOT / "libraries/NUCODE_BLE_Audio/src"),
                        str(ROOT / "tests/host" / scenario),
                        "-o",
                        str(binary),
                    ]
                    compiled = subprocess.run(
                        command, capture_output=True, timeout=60
                    )
                    self.assertEqual(
                        compiled.returncode,
                        0,
                        compiled.stderr.decode(errors="replace"),
                    )
                    executed = run_executable(
                        [str(binary)], capture_output=True, timeout=15
                    )
                    self.assertEqual(
                        executed.returncode,
                        0,
                        executed.stderr.decode(errors="replace"),
                    )


if __name__ == "__main__":
    unittest.main()
