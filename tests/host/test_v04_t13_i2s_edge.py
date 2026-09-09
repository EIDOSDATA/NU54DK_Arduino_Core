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
    def pages(self, role, mode=1):
        """! @brief 정상 STOP 뒤 role별 20-word 표본을 만듭니다. """
        summary = [0x49324530, role, mode, 0, 0, 64 if role == 1 else 0,
                   4 if role == 1 else 0, 4 if role == 1 else 0,
                   4 if role == 1 else 0, 123 if role == 1 else 0,
                   4096 if role == 1 else 0, 4095 if role == 1 else 0,
                   4095 if role == 1 else 0, 0, 0, 0, 0, 0, 2, 2]
        first = [0x49324531, role, 0, 0, 0, 0, 0, 0, 0, 0,
                 summary[5], 64, 0, 0, 0, 2, 0, 123, 0, 1]
        trace = [0] * 20
        if role == 1:
            trace[:4] = [0x49324554, role, 4, summary[5]]
            boundary = 1000
            for index in range(4):
                base = 4 + index * 4
                observed = 4095 + index
                boundary += observed
                trace[base:base + 4] = [boundary, observed, observed, observed]
            total = sum(trace[index] for index in (5, 9, 13, 17))
            summary[14:17] = [total, total, total]
        return [summary, first, trace]

    def test_only_standalone_i2s20_can_enable_edge_diagnostic(self):
        selected = edge.fixture(next(test for test in cases.cases() if test['id'] == 30))
        self.assertEqual(selected['_i2s_edge_diagnostic'], 1)
        swapped = edge.fixture(next(test for test in cases.cases() if test['id'] == 30), 2)
        self.assertEqual(swapped['_i2s_edge_diagnostic'], 2)
        for test in cases.cases():
            if test['id'] != 30:
                with self.subTest(identifier=test['id']), self.assertRaises(ProtocolError):
                    edge.fixture(test)
        with self.assertRaises(ProtocolError):
            edge.fixture(next(test for test in cases.cases() if test['id'] == 30), 3)

    def test_swapped_route_preserves_edge_classification_with_explicit_identity(self):
        pages = self.pages(1, 2)
        pages[0][3:5] = [1, 1]
        pages[0][13:17] = [1, 3500, 4095, 3501]
        pages[1][2] = 1
        pages[1][5:10] = [3500, 4095, 3501, 595, 1]
        pages[2][:2] = [0x49324552, 1]
        result = edge.classify_failure(pages, 2)
        self.assertEqual(result['cause'], 'physical-pad-or-peer-output')
        self.assertEqual(result['route'], 'swapped')

    def test_normal_dma_requires_physical_and_received_edge_agreement(self):
        for role in (1, 2):
            self.assertTrue(edge.inspect(self.pages(role), role)['diagnostic_only'])
        for index in (5, 12, 14, 15, 16):
            broken = self.pages(2)
            broken[0][index] = 1
            with self.subTest(role=2, page=0, index=index), self.assertRaises(ProtocolError):
                edge.inspect(broken, 2)
        for index in (10, 11):
            broken = self.pages(2)
            broken[1][index] = 1 if index == 10 else 0
            with self.subTest(role=2, page=1, index=index), self.assertRaises(ProtocolError):
                edge.inspect(broken, 2)
        for index in (0, 2, 3, 4, 5, 6, 7, 8, 13, 14, 15, 16, 17, 19):
            broken = self.pages(1)
            broken[0][index] ^= 1
            with self.subTest(page=0, index=index), self.assertRaises(ProtocolError):
                edge.inspect(broken, 1)
        for index in (0, 1, 2, 10, 11, 12, 14, 18, 19):
            broken = self.pages(1)
            broken[1][index] ^= 1
            with self.subTest(page=1, index=index), self.assertRaises(ProtocolError):
                edge.inspect(broken, 1)
        for index in (0, 1, 2, 3, 5, 6, 7, 8):
            broken = self.pages(1)
            broken[2][index] ^= 2
            with self.subTest(page=2, index=index), self.assertRaises(ProtocolError):
                edge.inspect(broken, 1)

    def test_four_bounded_intervals_allow_only_aggregate_window_budget(self):
        pages = self.pages(1)
        for index in range(4):
            base = 4 + index * 4
            pages[2][base] += (index + 1) * 2
            pages[2][base + 1] += 2
        pages[0][14] += 8
        self.assertEqual(edge.inspect(pages, 1)['observed_total'], pages[0][14])
        pages[0][14] += 1
        pages[2][16] += 1
        pages[2][17] += 1
        with self.assertRaises(ProtocolError):
            edge.inspect(pages, 1)

    def test_captured_four_buffer_trace_matches_continuous_oracle(self):
        """! @brief 실제 S raw의 내부 경계 1회와 측정창 외곽 2회를 재검증합니다. """
        summary = [0x49324530, 1, 1, 0, 0, 674, 4, 2, 2, 2760711,
                   4104, 4107, 4107, 0, 16359, 16357, 16357, 0, 0, 0]
        first = [0x49324531, 1, 0, 0, 0, 0, 0, 0, 0, 0,
                 674, 674, 0, 0, 0, 0, 0, 2760711, 0, 1]
        trace = [0x49324554, 1, 4, 674,
                 4081, 4081, 4079, 4079,
                 8171, 4090, 4090, 4090,
                 12250, 4079, 4080, 4080,
                 16359, 4109, 4107, 4107]
        result = edge.inspect([summary, first, trace], 1)
        self.assertEqual(result['observed_total'], 16359)
        self.assertEqual(result['received_total'], 16357)

    def test_second_captured_trace_stays_inside_per_interval_budget(self):
        """! @brief 두 번째 S raw의 추가 패드 전이를 연속 창 상한과 함께 고정합니다. """
        summary = [0x49324530, 1, 1, 0, 0, 668, 4, 3, 3, 2736116,
                   4088, 4081, 4081, 0, 16339, 16336, 16336, 0, 0, 0]
        first = [0x49324531, 1, 0, 0, 0, 0, 0, 0, 0, 0,
                 668, 668, 0, 0, 0, 0, 1024, 2736116, 0, 1]
        trace = [0x49324554, 1, 4, 668,
                 4071, 4071, 4070, 4070,
                 8160, 4089, 4088, 4088,
                 12258, 4098, 4096, 4096,
                 16339, 4081, 4081, 4081]
        result = edge.inspect([summary, first, trace], 1)
        self.assertEqual(result['observed_total'] - result['received_total'], 3)

    def test_b_starvation_restart_trace_uses_continuous_total(self):
        """! @brief 경계 귀속이 한 구간에서 3회 달라도 연속 합계가 맞는 실제 raw를 고정합니다. """
        summary = [0x49324530, 1, 1, 0, 0, 673, 4, 2, 2, 2756558,
                   4100, 4095, 4095, 0, 16349, 16347, 16347, 0, 0, 0]
        first = [0x49324531, 1, 0, 0, 0, 0, 0, 0, 0, 0,
                 673, 673, 0, 0, 0, 0, 1024, 2756558, 0, 1]
        trace = [0x49324554, 1, 4, 673,
                 4081, 4081, 4081, 4081,
                 8176, 4095, 4092, 4092,
                 12255, 4079, 4077, 4077,
                 16349, 4094, 4095, 4095]
        result = edge.inspect([summary, first, trace], 1)
        self.assertEqual(result['observed_total'] - result['received_total'], 2)

    def test_firmware_uses_hardware_boundary_and_does_not_reconfigure_gpio_for_observer(self):
        source = (ROOT / 'tests/zephyr/v04_t13_hil/src/audio.cpp').read_text(encoding='utf-8')
        self.assertIn('NRF_I2S_EVENT_RXPTRUPD', source)
        self.assertIn('TimerTask::count', source)
        self.assertIn('TimerTask::capture', source)
        self.assertIn('edge.pin_cnf_before != edge.pin_cnf_after', source)
        self.assertIn('edge.trace_boundary[trace] = edge.last_boundary', source)
        self.assertIn('edge.policy == 2U', source)
        observer = source[source.index('bool prepareEdgeDiagnostic()'):source.index('bool startEdgeDiagnostic()')]
        self.assertNotIn('nrf_gpio_cfg', observer)
        runner = (ROOT / 'tests/hil/nu54dk/v04_t13_run.py').read_text(encoding='utf-8')
        self.assertIn('device.command(185, (edge_diagnostic_mode,)', runner)
        self.assertIn("'diagnostic_only': is_timing or is_i2s_edge", runner)
        engine = (ROOT / 'tests/zephyr/v04_t13_hil/src/engine.cpp').read_text(encoding='utf-8')
        self.assertIn('opcode == 185U && nargs == 1U && args[0] <= 2U', engine)

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
        import v04_t13_stream_fault as stream_faults
        selected = next(test for test in cases.cases() if test['id'] == 30)
        rows = []

        def fail(_devices, _test, _role, _mode, _continuity, append, **_kwargs):
            for page in range(3):
                append(f'T13-S/i2s-edge-diagnostic/i2s20/failure/role1/'
                       f'i2s-edge-page{page}', {'words': [0] * 20})
            raise RuntimeError('original failure')

        with mock.patch.object(stream_faults, 'execute', side_effect=fail) as recovery:
            with self.assertRaisesRegex(RuntimeError, 'original failure'):
                edge.execute([], selected, 1, None,
                             lambda identifier, row: rows.append((identifier, row)))
        self.assertEqual(recovery.call_args.args[2:4], (2, 1))
        self.assertTrue(recovery.call_args.kwargs['preflight'])
        self.assertTrue(recovery.call_args.kwargs['restart_test']['_i2s_edge_diagnostic'])
        self.assertEqual(rows[-1][1]['status'], 'unproven')

    def test_swapped_route_reaches_exact_b_starvation_restart_fixture(self):
        """! @brief 교환 data route가 boolean으로 축소되지 않고 재시작까지 전달됩니다. """
        import v04_t13_stream_fault as stream_faults
        selected = next(test for test in cases.cases() if test['id'] == 30)
        selected = edge.fixture(selected, 2)
        with mock.patch.object(stream_faults, 'execute', side_effect=RuntimeError('stop')) as recovery:
            with self.assertRaisesRegex(RuntimeError, 'stop'):
                edge.execute([], selected, 1, None, lambda *_: None)
        self.assertEqual(recovery.call_args.kwargs['restart_test']['_i2s_edge_diagnostic'], 2)


if __name__ == '__main__':
    unittest.main()
