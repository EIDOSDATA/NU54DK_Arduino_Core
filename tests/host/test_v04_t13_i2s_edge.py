"""! @brief I2S 패드 전이 진단의 판정·범위·비정식 상태를 검사합니다. """
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests/hil/nu54dk'))
import v04_t13_cases as cases
import v04_t13_i2s_edge as edge
from v04_protocol import ProtocolError


class I2sEdgeTests(unittest.TestCase):
    def pages(self, role):
        """! @brief 정상 STOP 뒤 role별 20-word 표본을 만듭니다. """
        summary = [0x49324530, role, 1, 0, 0, 64 if role == 1 else 0,
                   4 if role == 1 else 0, 4 if role == 1 else 0,
                   4 if role == 1 else 0, 123 if role == 1 else 0,
                   4096 if role == 1 else 0, 4095 if role == 1 else 0,
                   4095 if role == 1 else 0, 0, 0, 0, 0, 0, 2, 2]
        first = [0x49324531, role, 0, 0, 0, 0, 0, 0, 0, 0,
                 summary[5], 64, 0, 0, 0, 2, 0, 123, 0, 1]
        return [summary, first, [0] * 20]

    def test_only_standalone_i2s20_can_enable_edge_diagnostic(self):
        selected = edge.fixture(next(test for test in cases.cases() if test['id'] == 30))
        self.assertTrue(selected['_i2s_edge_diagnostic'])
        for test in cases.cases():
            if test['id'] != 30:
                with self.subTest(identifier=test['id']), self.assertRaises(ProtocolError):
                    edge.fixture(test)

    def test_normal_dma_requires_physical_and_received_edge_agreement(self):
        for role in (1, 2):
            self.assertTrue(edge.inspect(self.pages(role), role)['diagnostic_only'])
        for index in (10, 11):
            broken = self.pages(2)
            broken[1][index] = 1 if index == 10 else 0
            with self.subTest(role=2, page=1, index=index), self.assertRaises(ProtocolError):
                edge.inspect(broken, 2)
        for index in (0, 2, 3, 4, 5, 6, 7, 8, 13, 17, 19):
            broken = self.pages(1)
            broken[0][index] ^= 1
            with self.subTest(page=0, index=index), self.assertRaises(ProtocolError):
                edge.inspect(broken, 1)
        for index in (0, 1, 2, 10, 11, 12, 14, 18, 19):
            broken = self.pages(1)
            broken[1][index] ^= 1
            with self.subTest(page=1, index=index), self.assertRaises(ProtocolError):
                edge.inspect(broken, 1)

    def test_firmware_uses_hardware_boundary_and_does_not_reconfigure_gpio_for_observer(self):
        source = (ROOT / 'tests/zephyr/v04_t13_hil/src/audio.cpp').read_text(encoding='utf-8')
        self.assertIn('NRF_I2S_EVENT_RXPTRUPD', source)
        self.assertIn('TimerTask::count', source)
        self.assertIn('TimerTask::capture', source)
        self.assertIn('edge.pin_cnf_before != edge.pin_cnf_after', source)
        observer = source[source.index('bool prepareEdgeDiagnostic()'):source.index('bool startEdgeDiagnostic()')]
        self.assertNotIn('nrf_gpio_cfg', observer)
        runner = (ROOT / 'tests/hil/nu54dk/v04_t13_run.py').read_text(encoding='utf-8')
        self.assertIn('device.command(185, (int(edge_diagnostic),)', runner)
        self.assertIn("'diagnostic_only': is_timing or is_i2s_edge", runner)

    def test_first_failure_classifies_physical_internal_and_ambiguous_edges(self):
        pages = self.pages(1)
        pages[0][3:5] = [1, 1]
        pages[0][13:17] = [1, 3500, 4095, 3501]
        pages[1][2] = 1
        pages[1][5:10] = [3500, 4095, 3501, 595, 1]
        pages[2][:2] = [0x49324552, 1]
        self.assertEqual(edge.classify_failure(pages)['cause'], 'physical-pad-or-peer-output')
        pages[0][14:17] = [4096, 4095, 3501]
        pages[1][5:10] = [4096, 4095, 3501, 1, 595]
        self.assertEqual(edge.classify_failure(pages)['cause'], 'i2s-sampling-or-dma-internal')
        pages[0][14:17] = [4096, 4095, 4095]
        pages[1][5:10] = [4096, 4095, 4095, 1, 1]
        self.assertEqual(edge.classify_failure(pages)['cause'], 'ambiguous-transition-count')

    def test_unrelated_failure_is_not_replaced_by_edge_classifier_error(self):
        import v04_t13_run as runner
        selected = next(test for test in cases.cases() if test['id'] == 30)
        rows = []

        def fail(_devices, _group, _duration, _continuity, append, **_kwargs):
            for page in range(3):
                append(f'T13-S/i2s-edge-diagnostic/i2s20/failure/role1/'
                       f'i2s-edge-page{page}', {'words': [0] * 20})
            raise RuntimeError('original failure')

        with mock.patch.object(runner, 'execute_group', side_effect=fail):
            with self.assertRaisesRegex(RuntimeError, 'original failure'):
                edge.execute([], selected, 1, None,
                             lambda identifier, row: rows.append((identifier, row)))
        self.assertEqual(rows[-1][1]['status'], 'unproven')


if __name__ == '__main__':
    unittest.main()
