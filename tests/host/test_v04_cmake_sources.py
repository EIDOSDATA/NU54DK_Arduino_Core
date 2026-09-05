"""! @brief 실제 Core CMake의 personality source 소속과 단일 등록을 검증합니다. """

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
PERSONALITIES = ("UARTE", "SPIM", "SPIS", "TWIM", "TWIS")


class CoreSourceMembershipTests(unittest.TestCase):
    """! @brief 다른 Zephyr library 문맥에서 Core module을 포함하는 구성 회귀입니다. """

    def test_personality_sources_belong_only_to_named_core(self):
        cmake = shutil.which("cmake")
        self.assertIsNotNone(cmake)
        matrix = [(), *[(name,) for name in PERSONALITIES], PERSONALITIES]
        with tempfile.TemporaryDirectory(prefix="nu54-r01-cmake-") as temporary:
            root = Path(temporary)
            (root / "dummy.cpp").write_text("int sentinel;\n", encoding="utf-8")
            harness = """
cmake_minimum_required(VERSION 3.20)
project(r01 LANGUAGES CXX)
add_library(inherited STATIC dummy.cpp)
set(ZEPHYR_CURRENT_LIBRARY inherited)
macro(zephyr_library_named name)
  add_library(${name} STATIC)
  set(ZEPHYR_CURRENT_LIBRARY ${name})
endmacro()
function(zephyr_library_sources)
  target_sources(${ZEPHYR_CURRENT_LIBRARY} PRIVATE ${ARGN})
endfunction()
function(zephyr_include_directories)
endfunction()
function(zephyr_system_include_directories)
endfunction()
function(build_info)
endfunction()
set(CONFIG_NUCODE_ARDUINO_CORE TRUE)
set(CONFIG_BOARD_NRF54L15DK_NRF54L15_CPUAPP_NU54DK TRUE)
set(CONFIG_NUCODE_ARDUINO_SERIAL_FABRIC TRUE)
set(APPLICATION_SOURCE_DIR "${CMAKE_CURRENT_SOURCE_DIR}")
include("@ROOT@/zephyr/CMakeLists.txt")
get_target_property(core_sources nucode_arduino_core SOURCES)
get_target_property(inherited_sources inherited SOURCES)
file(WRITE "${CMAKE_BINARY_DIR}/core.txt" "${core_sources}")
file(WRITE "${CMAKE_BINARY_DIR}/inherited.txt" "${inherited_sources}")
"""
            (root / "CMakeLists.txt").write_text(harness.replace("@ROOT@", ROOT.as_posix()), encoding="utf-8")
            for index, enabled in enumerate(matrix):
                with self.subTest(enabled=enabled):
                    output = root / f"build-{index}"
                    command = [cmake, "-S", str(root), "-B", str(output), "-G", "Ninja"]
                    command += [f"-DCONFIG_NUCODE_ARDUINO_SERIAL_FABRIC_{name}={'ON' if name in enabled else 'OFF'}" for name in PERSONALITIES]
                    result = subprocess.run(command, capture_output=True, text=True, timeout=90)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    core = (output / "core.txt").read_text(encoding="utf-8").split(";")
                    inherited = (output / "inherited.txt").read_text(encoding="utf-8").split(";")
                    for name in PERSONALITIES:
                        source = (ROOT / f"cores/arduino/{name.title()}Fabric.cpp").as_posix()
                        self.assertEqual(core.count(source), int(name in enabled), f"{name}: core={core}; inherited={inherited}")
                        self.assertNotIn(source, inherited)


if __name__ == "__main__":
    unittest.main()
