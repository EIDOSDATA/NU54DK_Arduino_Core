"""M31-W04 연결 CTE raw IQ HIL 판정의 경계를 검사합니다."""

import importlib.util
from pathlib import Path
import sys
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = REPO_ROOT / "tests/hil/nu54dk/m31_df_connected_rx_run.py"
SPEC = importlib.util.spec_from_file_location("m31_df_connected_rx_run", RUNNER_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def base_record():
    """명령 수락과 Host gate 동기화가 끝난 최소 기록을 만듭니다."""
    return {
        "receiver_lines": [
            "DF_CONN|CONNECTED|error=0",
            "DF_CONN|ANT_INFO|count=1|max_pattern=12|max_cte=20",
            "DF_CONN|AOA_RX_ENABLE|code=-22",
            "DF_CONN|RAW_RX_PARAM|code=0",
            MODULE.HOST_STATE_ARMED,
            "DF_CONN|RAW_REQUEST|code=0",
        ],
        "responder_lines": ["CTE responses enabled on connected peer"],
        "iq_reports": 0,
        "iq_samples": 0,
        "iq_event_counters": [],
        "host_iq_callbacks": 0,
        "host_gate_drops": 0,
        "iq_packet_status_counts": {},
    }


class ConnectedRawIqClassificationTest(unittest.TestCase):
    """Controller command·event·Host callback·sample을 독립 판정합니다."""

    def test_command_acceptance_without_event_remains_hold(self):
        """HCI 명령 성공만으로 raw IQ PASS가 되지 않아야 합니다."""
        record = base_record()
        MODULE.classify(record)
        self.assertEqual("HOLD", record["status"])
        self.assertEqual("PASS", record["path_results"][
            "connected_controller_commands"
        ])
        self.assertEqual("HOLD", record["path_results"][
            "connected_controller_iq_event"
        ])
        self.assertEqual("NOT RUN", record["path_results"][
            "connectionless_raw_iq_samples"
        ])

    def test_host_callback_without_valid_samples_remains_hold(self):
        """Controller event callback에 sample이 없으면 HOLD를 유지합니다."""
        record = base_record()
        line = (
            "DF_CONN|IQ|error=0|count=0|type=1|status=255|sample_type=0|"
            "slot=2|event=10|channel=7|i0=0|q0=0|rssi=-450"
        )
        MODULE.record_iq_line(record, line)
        MODULE.classify(record)
        self.assertEqual(1, record["host_iq_callbacks"])
        self.assertEqual(0, record["iq_reports"])
        self.assertEqual("PASS", record["path_results"][
            "connected_host_callback"
        ])
        self.assertEqual("HOLD", record["raw_iq_rx"])

    def test_twenty_valid_sample_reports_pass_connected_raw_iq_only(self):
        """유효 callback 20개만 connected raw IQ PASS를 만듭니다."""
        record = base_record()
        for event in range(20):
            line = (
                "DF_CONN|IQ|error=0|count=45|type=1|status=0|sample_type=0|"
                f"slot=2|event={event}|channel={event % 37}|"
                "i0=-1|q0=2|rssi=-430"
            )
            MODULE.record_iq_line(record, line)
        MODULE.classify(record)
        self.assertEqual("PASS", record["status"])
        self.assertEqual(900, record["iq_samples"])
        self.assertEqual("PASS", record["path_results"][
            "connected_raw_iq_samples"
        ])
        self.assertEqual("NOT RUN", record["path_results"][
            "antenna_switching"
        ])
        self.assertEqual("NOT RUN", record["path_results"][
            "angle_measurement"
        ])


if __name__ == "__main__":
    unittest.main()
