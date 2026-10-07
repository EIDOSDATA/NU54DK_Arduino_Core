#!/usr/bin/env python3
"""! @brief standalone radio와 coexistence native attestation을 검증합니다. """

from __future__ import annotations

from pathlib import Path
import sys
import unittest


REPOSITORY = Path(__file__).resolve().parents[2]
HIL = REPOSITORY / "tests" / "hil" / "nu54dk"
if str(HIL) not in sys.path:
    sys.path.insert(0, str(HIL))

import m32_coexistence_run as coexistence  # noqa: E402
import m32_standalone_radio_run as standalone  # noqa: E402


def cleanup(roles: tuple[str, ...]) -> dict[str, dict[str, str]]:
    """! @brief 성공한 STOP·serial close record를 만듭니다. """

    return {
        role: {"stop": "PASS", "serial_close": "PASS"}
        for role in roles
    }


def standalone_phase(protocol: str, dut_probe: str) -> dict:
    """! @brief 지정 단독 radio의 유효 raw denominator를 만듭니다. """

    transmit_role, receive_role = standalone.PROTOCOLS[protocol]["roles"]
    negative = (
        "invalid_channel_rejected"
        if protocol == "radio154"
        else "invalid_rate_rejected"
    )
    transmit = {
        "requested": "2000",
        "acknowledged": "1980",
        "max_latency_ms": "100",
        "iterations": "20",
        "invalid_length_rejected": "1",
        negative: "1",
    }
    receive = {
        "unique": "1980",
        "corrupt": "0",
        "dropped": "0",
        "iterations": "20",
        "invalid_length_rejected": "1",
        negative: "1",
    }
    results = {transmit_role: transmit, receive_role: receive}
    return {
        "results": results,
        "denominator": standalone._validate_result(protocol, results),
        "cleanup": cleanup((transmit_role, receive_role)),
        "probe_mapping": {"dut": dut_probe, "peer": "peer-probe"},
    }


def coexistence_phase(scenario: str) -> dict:
    """! @brief 한 공존 scenario의 유효 raw result와 cleanup을 만듭니다. """

    roles = coexistence.SCENARIOS[scenario]
    dut = {
        "iterations": "20",
        "ble_received": "3920",
        "radio_received": "3920",
        "ble_loss": "80",
        "radio_loss": "80",
        "ble_corrupt": "0",
        "radio_corrupt": "0",
        "starvation": "0",
        "ble_restarts": "1",
        "radio_restarts": "1",
        "ble_gap_ms": "500",
        "radio_gap_ms": "500",
    }
    if scenario != "ble_mesh":
        dut["double_owner_rejected"] = "1"
    ble_peer = {
        "iterations": "20",
        "sent": "4000",
        "reconnects": "1",
        "write_failures": "0",
    }
    if scenario == "ble_mesh":
        radio_peer = {
            "iterations": "20",
            "sent": "4000",
            "acknowledged": "4000",
            "restarts": "1",
            "failures": "0",
            "configuration_retries": "3",
            "acknowledgment_retries": "80",
        }
    else:
        radio_peer = {
            "iterations": "20",
            "sent": "4000",
            "acknowledged": "3920",
            "failures": "80",
            "restarts": "1",
            "invalid_configuration_rejected": "1",
            "invalid_length_rejected": "1",
            "double_owner_rejected": "1",
        }
    return {
        "results": {
            "dut": dut,
            roles[1]: radio_peer,
            "ble_peer": ble_peer,
        },
        "cleanup": cleanup(roles),
    }


class M32RadioAttestationTest(unittest.TestCase):
    """! @brief raw counter·role swap·cleanup 없는 synthetic PASS를 거부합니다. """

    def test_standalone_twenty_cycles_require_both_radios_and_role_swap(self) -> None:
        """! @brief 802.15.4와 ESB의 실제 분모 및 probe 방향 교대를 검증합니다. """

        phases = {
            "radio154": standalone_phase("radio154", "first-probe"),
            "esb": standalone_phase("esb", "second-probe"),
        }
        records = standalone.build_dispatch_cycle_records(phases)
        self.assertEqual([row["cycle"] for row in records], list(range(1, 21)))
        self.assertTrue(all(
            row["semantics"] == {
                token: "PASS" for token in standalone.SEMANTICS
            }
            for row in records
        ))
        phases["esb"]["probe_mapping"]["dut"] = "first-probe"
        with self.assertRaisesRegex(standalone.StandaloneRadioFailure, "role swap"):
            standalone.build_dispatch_cycle_records(phases)

    def test_standalone_rejects_missing_cleanup_and_packet_loss(self) -> None:
        """! @brief STOP 누락과 허용치를 넘은 packet loss를 거부합니다. """

        phases = {
            "radio154": standalone_phase("radio154", "first-probe"),
            "esb": standalone_phase("esb", "second-probe"),
        }
        phases["radio154"]["cleanup"]["receiver"]["stop"] = "NOT_CONFIRMED"
        with self.assertRaisesRegex(standalone.StandaloneRadioFailure, "cleanup"):
            standalone.build_dispatch_cycle_records(phases)
        phases["radio154"] = standalone_phase("radio154", "first-probe")
        phases["radio154"]["results"]["receiver"]["unique"] = "1979"
        with self.assertRaisesRegex(standalone.StandaloneRadioFailure, "loss limit"):
            standalone.build_dispatch_cycle_records(phases)

    def test_coexistence_twenty_cycles_revalidate_all_three_scenarios(self) -> None:
        """! @brief BLE+154/ESB/Mesh 세 raw result를 모두 재판정합니다. """

        phases = {
            scenario: coexistence_phase(scenario)
            for scenario in coexistence.SCENARIOS
        }
        records = coexistence.build_dispatch_cycle_records(phases)
        self.assertEqual([row["cycle"] for row in records], list(range(1, 21)))
        self.assertTrue(all(
            row["semantics"] == {
                token: "PASS" for token in coexistence.SEMANTICS
            }
            for row in records
        ))
        phases["ble_esb"]["results"]["dut"]["starvation"] = "1"
        with self.assertRaisesRegex(coexistence.CoexistenceFailure, "starvation"):
            coexistence.build_dispatch_cycle_records(phases)

    def test_coexistence_rejects_partial_cleanup(self) -> None:
        """! @brief 한 role의 STOP 미확인도 전체 campaign PASS로 승격하지 않습니다. """

        phases = {
            scenario: coexistence_phase(scenario)
            for scenario in coexistence.SCENARIOS
        }
        phases["ble_mesh"]["cleanup"]["mesh_peer"]["serial_close"] = "ERROR"
        with self.assertRaisesRegex(coexistence.CoexistenceFailure, "cleanup"):
            coexistence.build_dispatch_cycle_records(phases)

    def test_runners_bind_phase_readback_and_safe_flash(self) -> None:
        """! @brief 순차 재flash마다 exact readback과 비파괴 sector 조건을 고정합니다. """

        standalone_source = (HIL / "m32_standalone_radio_run.py").read_text(
            encoding="utf-8"
        )
        coexistence_source = (HIL / "m32_coexistence_run.py").read_text(
            encoding="utf-8"
        )
        for source in (standalone_source, coexistence_source):
            self.assertIn("prepare_direct_program(", source)
            self.assertIn("complete_direct_program(", source)
            self.assertIn("cleanup_direct_ports(", source)
            self.assertIn("dispatch_attestation(", source)
            self.assertNotIn("mass erase", source.lower())
            self.assertNotIn("auto_unlock=True", source)
        self.assertIn('for role in ("transmitter", "prx")', standalone_source)
        self.assertIn('for role in ("receiver", "ptx")', standalone_source)


if __name__ == "__main__":
    unittest.main()
