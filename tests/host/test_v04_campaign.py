"""v0.4.0 반복·soak campaign의 bounded 실행 계약을 검사합니다."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests/hil/nu54dk"))
import v04_campaign as campaign
from v04_protocol import ProtocolError


class FakeClock:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        return self.value


class CampaignTests(unittest.TestCase):
    def test_repetition_campaign_is_bounded(self):
        clock = FakeClock()
        cycles = []
        records = []

        def run_once(index):
            cycles.append(index)
            clock.value += 2

        result = campaign.run_cycles(
            run_once, lambda name, record: records.append((name, record)),
            repetitions=3, progress_interval_seconds=1, monotonic=clock)
        self.assertEqual(cycles, [1, 2, 3])
        self.assertEqual(result["completed_cycles"], 3)
        self.assertFalse(result["interrupted_duration_reused"])
        self.assertEqual(records[-1][0], "V04-CAMPAIGN-COMPLETE")

    def test_duration_is_fresh_for_each_invocation(self):
        def execute():
            clock = FakeClock()
            cycles = []

            def run_once(index):
                cycles.append(index)
                clock.value += 3

            result = campaign.run_cycles(
                run_once, lambda _name, _record: None, repetitions=1,
                duration_seconds=5, progress_interval_seconds=1,
                monotonic=clock)
            return cycles, result

        first = execute()
        second = execute()
        self.assertEqual(first, second)
        self.assertEqual(first[0], [1, 2])

    def test_invalid_or_unbounded_options_fail_closed(self):
        for values in ((0, 0, 5), (101, 0, 5), (1, -1, 5),
                       (1, 7201, 5), (1, 1, 0), (1, 1, 61)):
            with self.subTest(values=values), self.assertRaises(ProtocolError):
                campaign.validate_options(*values)


if __name__ == "__main__":
    unittest.main()
