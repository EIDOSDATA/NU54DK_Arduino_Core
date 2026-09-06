"""! @brief 실제 production Fabric과 fake nrfx의 thread/STOP 경계를 검증합니다. """
from pathlib import Path
import subprocess
import tempfile
import unittest

from host_compiler import compiler_command
ROOT=Path(__file__).resolve().parents[2]


class FabricDriverTests(unittest.TestCase):
    def test_analog_production(self):
        self.run_driver('analog',['pwm_timeout','other_progress','overflow','deadline','saadc_timeout','repeat',
                                 'snapshot','release_failure','stop_queue_full','pwm_commit_failure','saadc_commit_failure',
                                 'saadc_queue_commit_failure'])

    def test_stream_production(self):
        self.run_driver('stream',['i2s_timeout','pdm_timeout','other_progress','overflow','deadline','repeat',
                                 'snapshot','stale_stop','stop_queue_full','release_failure','pdm_metadata',
                                 'i2s_commit_failure','pdm_commit_failure','pdm_buffer_failure'])

    def run_driver(self,driver,scenarios):
        compiler=compiler_command()
        self.assertIsNotNone(compiler)
        with tempfile.TemporaryDirectory(prefix='nu54-r03-') as folder:
            binary=Path(folder)/(driver+'.exe')
            args=[*compiler,'-std=c++17','-Wall','-Wextra','-Werror','-pthread',
                  '-DCONFIG_SERIAL=0','-DTEST_UART_STATUS=0']
            for directory in ['tests/host/fabric_driver_stubs','tests/host/serial_driver_stubs',
                              'tests/host/serial_fabric_stubs','cores/arduino']:
                args.extend(['-I',str(ROOT/directory)])
            args.extend([str(ROOT/f'tests/host/r03_{driver}_driver_main.cpp'),'-o',str(binary)])
            result=subprocess.run(args,capture_output=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stderr.decode(errors='replace'))
            for scenario in scenarios:
                with self.subTest(scenario=scenario):
                    result=subprocess.run([str(binary),scenario],capture_output=True,timeout=10)
                    self.assertEqual(result.returncode,0,result.stderr.decode(errors='replace'))


if __name__=='__main__':
    unittest.main()
