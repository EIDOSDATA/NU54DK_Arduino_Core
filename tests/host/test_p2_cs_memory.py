"""P2 CS 연속 계측의 부하 인자 계약을 검사합니다."""

import argparse
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest import mock


REPOSITORY = Path(__file__).resolve().parents[2]
HIL_DIRECTORY = REPOSITORY / "tests" / "hil" / "nu54dk"
sys.path.insert(0, str(HIL_DIRECTORY))
SPEC = importlib.util.spec_from_file_location(
    "p2_cs_memory_run",
    HIL_DIRECTORY / "p2_cs_memory_run.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class CsLoadArgumentsTest(unittest.TestCase):
    """잘못된 부하 요청은 probe 접근 전에 거부합니다."""

    def test_raw_target_must_be_positive(self):
        """측정할 raw 결과가 없는 실행을 막습니다."""
        for target in (0, -1):
            with self.subTest(target=target):
                with self.assertRaisesRegex(ValueError, "--raw-target"):
                    MODULE.run(argparse.Namespace(raw_target=target, timeout=600))

    def test_timeout_must_be_positive(self):
        """만료 시간이 0 이하인 실행을 막습니다."""
        for timeout in (0, -1):
            with self.subTest(timeout=timeout):
                with self.assertRaisesRegex(ValueError, "--timeout"):
                    MODULE.run(argparse.Namespace(raw_target=100, timeout=timeout))

    def test_failure_cleanup_waits_for_new_stop(self):
        """실패 복구는 이전 STOP 문자열이 아닌 새 응답을 확인합니다."""
        lines = {"initiator": ["P2_STOP role=cs-initiator"]}

        def append_new_stop(streams, pending, values):
            values["initiator"].append("P2_STOP role=cs-initiator")

        with mock.patch.object(MODULE, "read_lines", side_effect=append_new_stop):
            observed = MODULE.wait_for_cleanup_line(
                {}, {}, lines, "initiator", 1,
                "P2_STOP role=cs-initiator", 1.0,
            )
        self.assertTrue(observed)
        self.assertEqual(len(lines["initiator"]), 2)


if __name__ == "__main__":
    unittest.main()
