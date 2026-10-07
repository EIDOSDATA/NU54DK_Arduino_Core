#!/usr/bin/env python3
"""! @brief modern direct-HIL의 원시 분모→dispatcher cycle 변환을 검증합니다. """

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys
import unittest


HIL = Path(__file__).resolve().parents[1] / "hil" / "nu54dk"
if str(HIL) not in sys.path:
    sys.path.insert(0, str(HIL))

import m31_df_beacon_run as df  # noqa: E402
import m31_iso_cis_run as cis  # noqa: E402
import m31_iso_combined_run as combined  # noqa: E402
import m32_advertising_run as advertising  # noqa: E402
import m32_ead_run as ead  # noqa: E402
import m32_mesh_management_run as mesh_management  # noqa: E402
import m32_mesh_update_run as mesh_update  # noqa: E402
import m32_nordic_extension_run as nordic  # noqa: E402
import m32_power_path_run as power  # noqa: E402
import m32_privacy_run as privacy  # noqa: E402
import m33_beacon_run as beacon  # noqa: E402
from m33_sdk_risk_common import (  # noqa: E402
    ExactProgrammingFailure,
    cleanup_direct_ports,
    dispatch_attestation,
)


class FakePort:
    """! @brief STOP·close 호출과 예외를 관찰하는 최소 serial 대역입니다. """

    def __init__(self, fail_write: bool = False):
        self.fail_write = fail_write
        self.writes: list[bytes] = []
        self.closed = False

    def write(self, payload: bytes) -> None:
        """! @brief 선택적으로 write 오류를 발생시킵니다. """

        if self.fail_write:
            raise OSError("write")
        self.writes.append(payload)

    def flush(self) -> None:
        """! @brief 실제 serial flush를 대체합니다. """

    def close(self) -> None:
        """! @brief close 실행 여부를 기록합니다. """

        self.closed = True


def assert_cycles(test: unittest.TestCase, records: list[dict], count: int,
                  semantics: tuple[str, ...]) -> None:
    """! @brief cycle 번호와 semantic PASS map을 공통 검증합니다. """

    test.assertEqual([row["cycle"] for row in records], list(range(1, count + 1)))
    test.assertTrue(all(row["status"] == "PASS" for row in records))
    test.assertTrue(all(
        row["semantics"] == {token: "PASS" for token in semantics}
        for row in records
    ))


class ModernDirectAttestationTest(unittest.TestCase):
    """! @brief 각 campaign 고유 분모가 20 cycle을 실제로 지지하는지 확인합니다. """

    def test_iso_and_df_cycles(self) -> None:
        """! @brief ISO/DF strict 측정치와 고유 nonce를 검증합니다. """

        nonces = [f"n{index}" for index in range(20)]
        cis_records = cis.build_dispatch_cycle_records(
            nonces,
            SimpleNamespace(cycles=20, total_sent=2000, total_received=1980,
                            minimum_received=99, invalid_or_lost=20),
        )
        assert_cycles(self, cis_records, 20, cis.SEMANTICS)
        combined_records = combined.build_dispatch_cycle_records(
            nonces,
            SimpleNamespace(cycles=20, peer_sent=2000, cis_received=1980,
                            bis_forwarded=1980, bis_received=1980,
                            minimum_cis_received=99, minimum_bis_received=99,
                            cis_empty_slots=20, bis_empty_slots=20),
        )
        assert_cycles(self, combined_records, 20, combined.SEMANTICS)
        df_records = df.build_dispatch_cycle_records(
            nonces,
            {"cycles": 20, "starts": 20, "stops": 20, "invalid_rejected": 20},
        )
        assert_cycles(self, df_records, 20, df.SEMANTICS)

    def test_power_advertising_privacy_and_ead_cycles(self) -> None:
        """! @brief W04 aggregate가 내부 20 sequence를 정확히 닫는지 확인합니다. """

        assert_cycles(
            self,
            power.build_dispatch_cycle_records(
                {"central": 20, "peripheral": 20}, 60,
                {"power_central": 1.0, "power_peripheral": 2.0, "path": 3.0},
            ),
            20,
            power.SEMANTICS,
        )
        advertiser = {
            "updates": "20", "sets": "3", "over_capacity_rejected": "1",
            "stale_set_rejected": "1",
        }
        scanner = {
            "raw": "600", "unique": "120", "corrupt": "0", "dropped": "0",
            "scan_initiate_conflict_rejected": "1",
        }
        assert_cycles(
            self,
            advertising.build_dispatch_cycle_records({
                "advertiser_a": dict(advertiser),
                "advertiser_b": dict(advertiser),
                "scanner": scanner,
            }),
            20,
            advertising.SEMANTICS,
        )
        identity = {
            "connections": "20", "disconnections": "20",
            "wrong_identity_rejected": "1", "active_list_change_rejected": "1",
        }
        peer = {
            "connections_a": "20", "connections_b": "20",
            "disconnections_a": "20", "disconnections_b": "20",
            "packets": "200", "max_latency_ms": "1000",
        }
        assert_cycles(
            self,
            privacy.build_dispatch_cycle_records(
                {"identity_a": dict(identity), "identity_b": dict(identity),
                 "peer": peer},
                {"identity_a": ("00:00:00:00:00:01", 1),
                 "identity_b": ("00:00:00:00:00:02", 1),
                 "peer": ("00:00:00:00:00:03", 1)},
            ),
            20,
            privacy.SEMANTICS,
        )
        ead_scanner = {
            "raw": "400", "authenticated": "20", "dropped": "0",
            "replay_rejected": "20", "tamper_rejected": "20",
            "wrong_key_rejected": "20", "wrong_iv_rejected": "20",
        }
        assert_cycles(
            self,
            ead.build_dispatch_cycle_records(
                {"advertiser": {"updates": "20"}, "scanner": ead_scanner},
                set(range(20)),
            ),
            20,
            ead.SEMANTICS,
        )

    def test_nordic_mesh_and_beacon_cycles(self) -> None:
        """! @brief Nordic/Mesh/Beacon의 event·target·session 분모를 검증합니다. """

        nordic_base = {
            "qos": "200", "survey": "20", "anchors": "1000", "events": "200",
            "prepares": "200", "iterations": "20", "llpm_interval_us": "1000",
            "max_anchor_gap_us": "5000", "max_event_gap_ms": "5",
            "overflow_observed": "1", "invalid_survey_rejected": "1",
            "invalid_event_task_rejected": "1", "duplicate_reservation_bounded": "1",
            "disabled_callback_quiet": "1", "projection_wrap_pass": "1",
            "acl_controller_experimental": "1", "acl_host_transmit_path": "0",
            "acl_usable": "0", "callback_context": "pass",
        }
        central = dict(nordic_base)
        central["invalid_llpm_rejected"] = "1"
        assert_cycles(
            self,
            nordic.build_dispatch_cycle_records({
                "central": central, "peripheral": dict(nordic_base)
            }),
            20,
            nordic.SEMANTICS,
        )
        management_server = {
            "recovery": "pass", "provisioned": "1", "management_server": "pass"
        }
        management_client = {
            "recovery": "pass", "remote_provisioned": "1", "feature_groups": "7",
            "iterations": "10", "operations": "350", "malformed_rejected": "1",
            "out_of_range_rejected": "1", "replay_rejected": "1",
            "wrong_subnet_rejected": "1", "remote_reports": "1",
        }
        capacities = {role: {"cdb_remote_capacity": 2} for role in mesh_management.ROLES}
        assert_cycles(
            self,
            mesh_management.build_dispatch_cycle_records(
                {"client": management_client, "server": dict(management_server),
                 "target": dict(management_server)}, capacities,
            ),
            20,
            mesh_management.SEMANTICS,
        )
        update_client = {
            "iterations": "10", "chunk_size": "128", "object_digest": "pass",
            "targets": "2", "chunks": "5120", "suspend_resume": "pass",
            "wrong_key_rejected": "1", "object_size": "32768",
        }
        update_target = {
            "iterations": "10", "chunk_size": "128", "object_digest": "pass",
            "chunks": "2560", "bad_digest_rejected": "1",
        }
        update_capacities = {
            role: {"cdb_remote_capacity": 2} for role in mesh_update.ROLES
        }
        assert_cycles(
            self,
            mesh_update.build_dispatch_cycle_records(
                {"blob_client": update_client, "target_a": dict(update_target),
                 "target_b": dict(update_target)}, update_capacities,
            ),
            20,
            mesh_update.SEMANTICS,
        )
        advertiser = {
            "switches": "90", "ibeacon_sequences": "30",
            "eddystone_sequences": "30", "bthome_sequences": "30",
            "codec_negative": "pass",
        }
        observer = {
            "raw": "600", "ibeacon_raw": "150", "eddystone_raw": "150",
            "bthome_raw": "150", "ibeacon_unique": "10",
            "eddystone_unique": "10", "bthome_unique": "10",
            "semantic_errors": "0", "callback_context": "pass",
            "codec_negative": "pass",
        }
        sessions = [
            {"advertiser": dict(advertiser), "observer": dict(observer)}
            for _ in range(2)
        ]
        assert_cycles(
            self, beacon.build_dispatch_cycle_records(sessions), 20, beacon.SEMANTICS
        )

    def test_cleanup_closes_partial_ports_and_attestation_rejects_forgery(self) -> None:
        """! @brief 부분 open 정리와 임의 cycle 자기신고 거부를 검증합니다. """

        good = FakePort()
        bad = FakePort(fail_write=True)
        transcript: list[str] = []
        records = cleanup_direct_ports(
            {"good": good, "bad": bad},
            {"good": b"STOP\n", "bad": b"STOP\n"},
            set(),
            transcript,
        )
        self.assertEqual(records["good"]["stop"], "SENT_NOT_CONFIRMED")
        self.assertTrue(good.closed and bad.closed)
        with self.assertRaises(ExactProgrammingFailure):
            dispatch_attestation(
                "x", "a" * 40, 1, ("semantic",), (), {},
                cycle_records=[{
                    "cycle": 1,
                    "status": "PASS",
                    "semantics": {"semantic": "NOT_RUN"},
                }],
            )

    def test_all_direct_runners_bind_exact_program_readback_and_cleanup(self) -> None:
        """! @brief 11개 runner가 공용 exact/cleanup 경계를 우회하지 않는지 검사합니다. """

        names = (
            "m31_iso_cis_run.py",
            "m31_iso_combined_run.py",
            "m31_df_beacon_run.py",
            "m32_power_path_run.py",
            "m32_advertising_run.py",
            "m32_privacy_run.py",
            "m32_ead_run.py",
            "m32_nordic_extension_run.py",
            "m32_mesh_management_run.py",
            "m32_mesh_update_run.py",
            "m33_beacon_run.py",
        )
        for name in names:
            with self.subTest(name=name):
                source = (HIL / name).read_text(encoding="utf-8")
                self.assertIn("prepare_direct_program(", source)
                self.assertIn("complete_direct_program(", source)
                self.assertIn("cleanup_direct_ports(", source)
                self.assertIn("build_dispatch_cycle_records(", source)
                self.assertIn("dispatch_attestation(", source)


if __name__ == "__main__":
    unittest.main()
