"""! @brief 실제 자원 관리자·runtime route의 실패 경계를 Host에서 실행합니다. """
from pathlib import Path
import subprocess
import tempfile
import unittest

from host_compiler import compiler_command

ROOT = Path(__file__).resolve().parents[2]
SCENARIOS = ['cycle', 'guards', 'block', 'alias', 'begin0', 'begin1', 'pinctrl',
             'get', 'commit', 'unwind_put', 'unwind_pinctrl', 'rollback',
             'put_retry', 'restore_pinctrl', 'restore_pin', 'stale_release',
             'stale', 'transfer', 'borrow', 'capacity', 'dma', 'threads']


class ResourceRouteTests(unittest.TestCase):
    def test_production_resource_and_route(self):
        compiler = compiler_command()
        self.assertIsNotNone(compiler)
        with tempfile.TemporaryDirectory(prefix='nu54-r08-') as directory:
            binary = Path(directory) / 'route.exe'
            command = [*compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror', '-pthread',
                       '-DCONFIG_ZTEST=1', '-DCONFIG_NUCODE_ARDUINO_IO_RESOURCE_SLOTS=8']
            for include in ['tests/host/route_stubs', 'tests/host/serial_driver_stubs',
                            'tests/host/serial_fabric_stubs', 'cores/arduino']:
                command.extend(['-I', str(ROOT / include)])
            sources = ['tests/host/r08_resource_route_main.cpp',
                       'cores/arduino/internal/io_resource_manager.cpp',
                       'cores/arduino/internal/RuntimePeripheralRoute.cpp',
                       'cores/arduino/internal/RuntimePeripheralRouteRecovery.cpp',
                       'cores/arduino/internal/resource/IoResourceTable.cpp']
            command.extend(str(ROOT / path) for path in sources)
            command.extend(['-o', str(binary)])
            result = subprocess.run(command, capture_output=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
            for scenario in SCENARIOS:
                with self.subTest(scenario=scenario):
                    result = subprocess.run([str(binary), scenario], capture_output=True, timeout=20)
                    self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))


if __name__ == '__main__':
    unittest.main()
