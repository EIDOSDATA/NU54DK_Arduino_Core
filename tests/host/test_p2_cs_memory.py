"""P2 CS 연속 계측의 부하 인자 계약을 검사합니다."""

import argparse
import importlib.util
from pathlib import Path
import sys
import tempfile
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

    def test_forward_counter_loss_is_observed_not_rejected(self):
        """! @brief 간헐 전진 누락은 증거에 남기되 합격을 막지 않습니다. """
        gaps = []
        MODULE.record_counter_transition(None, 65534, gaps)
        MODULE.record_counter_transition(65534, 1, gaps)
        self.assertEqual(gaps, [{"before": 65534, "after": 1}])

    def test_duplicate_or_backward_counter_is_invalid(self):
        """! @brief 누락 제외 정책이 중복·역행 raw까지 허용하지 않습니다. """
        for previous, current in ((10, 10), (10, 9), (0, 65535)):
            with self.subTest(previous=previous, current=current):
                with self.assertRaisesRegex(RuntimeError, "counter"):
                    MODULE.record_counter_transition(previous, current, [])

    def test_valid_raw_with_counter_loss_passes(self):
        """! @brief 유효 raw·양측 종료 뒤 간헐 누락만으로 HOLD하지 않습니다. """

        class FakeSerial:
            def __init__(self, port, baudrate, timeout):
                self.port = port

            def write(self, data):
                return len(data)

            def close(self):
                return None

        def ready(streams, pending, lines, role, expected, timeout):
            lines[role].append(expected)

        def raw(streams, pending, lines):
            if not any(line.startswith("CS_RAW ") for line in lines["initiator"]):
                for counter in (1, 3):
                    lines["initiator"].append(
                        f"CS_RAW counter={counter} local=10 peer=10 rtt=5 "
                        "tone=5 valid_rtt=5 distance_m=1.0"
                    )

        def stopped(streams, pending, lines, role, start, expected, timeout):
            lines[role].append(expected)
            if expected == "P2_STOP role=cs-initiator":
                lines[role].append("P2_CS_STATS completed=2")

        with tempfile.TemporaryDirectory() as temporary:
            image = Path(temporary) / "image.hex"
            image.write_bytes(b"test image")
            arguments = argparse.Namespace(
                raw_target=2, timeout=1.0,
                initiator_uid="initiator", reflector_uid="reflector",
                initiator_app="IAPP", initiator_aux="IAUX",
                reflector_app="RAPP", reflector_aux="RAUX",
                initiator_hex=image, reflector_hex=image,
                output=Path(temporary) / "evidence.json", require_causes=False,
            )
            probes = [mock.Mock(unique_id=uid) for uid in ("initiator", "reflector")]
            with (mock.patch.object(MODULE, "require_mapping"),
                  mock.patch.object(MODULE.ConnectHelper, "get_all_connected_probes",
                                    return_value=probes),
                  mock.patch.object(MODULE.serial, "Serial", FakeSerial),
                  mock.patch.object(MODULE, "reset_halted_start", return_value={}),
                  mock.patch.object(MODULE, "wait_for_line", side_effect=ready),
                  mock.patch.object(MODULE, "read_lines", side_effect=raw),
                  mock.patch.object(MODULE, "wait_for_new_line", side_effect=stopped)):
                evidence = MODULE.run(arguments)
            self.assertEqual(evidence["result"], "PASS")
            self.assertEqual(evidence["counter_gap_policy"], "observe_only")
            self.assertEqual(evidence["counter_gaps"], [{"before": 1, "after": 3}])


if __name__ == "__main__":
    unittest.main()
