"""! @brief M32-W10 지원 공존 조합과 외부 1-wire 계약을 검사합니다. """

from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
LIBRARY = ROOT / "libraries/NUCODE_Radio_Coexistence"
PROFILES = ROOT / "variants/nu54dk/profiles"


class M32CoexistenceContractTests(unittest.TestCase):
    """! @brief 공존 telemetry, profile, 예제와 결선 경계를 고정합니다. """

    def test_public_api_exposes_bounded_per_protocol_telemetry(self) -> None:
        """! @brief protocol별 sequence/hash/drop/지연/복구 snapshot을 요구합니다. """
        header = (LIBRARY / "src/NUCODE_Radio_Coexistence.h").read_text(
            encoding="utf-8"
        )
        for token in (
            "enum class Protocol",
            "struct ServiceStatistics",
            "sequence_errors",
            "hash_errors",
            "timeslot_failures",
            "starvation_events",
            "maximum_service_gap_ms",
            "recordRestart",
            "beginOneWire",
            "setExternalGrant",
            "radioEventCount",
            "NUCODECoexistence",
        ):
            with self.subTest(token=token):
                self.assertIn(token, header)
        self.assertNotIn("#include <zephyr/", header)

    def test_backend_is_fixed_storage_and_uses_mpsl_ready_channel(self) -> None:
        """! @brief heap 없이 IRQ snapshot과 1-wire READY 계수를 구현합니다. """
        backend = (LIBRARY / "src/NUCODE_Radio_Coexistence.cpp").read_text(
            encoding="utf-8"
        )
        for token in (
            "irq_lock()",
            "k_uptime_get_32()",
            "last_service_ms_[index] = 0U",
            "MPSL_DPPI_RADIO_PUBLISH_READY_CHANNEL_IDX",
            "nrf_egu_subscribe_set",
            "NRF_DT_GPIOS_TO_PSEL",
            "setExternalGrant(false)",
        ):
            with self.subTest(token=token):
                self.assertIn(token, backend)
        self.assertNotIn("malloc(", backend)
        self.assertNotIn("new ", backend)

    def test_four_profiles_encode_supported_controller_ownership(self) -> None:
        """! @brief 각 조합의 MPSL/controller 설정과 HIL 요구를 고정합니다. """
        expected = {
            "coexistence_ble_mesh": ("CONFIG_BT_EXT_ADV_MAX_ADV_SET=6", "mesh"),
            "coexistence_ble_154": ("CONFIG_MPSL=y", "ieee802154_radio"),
            "coexistence_ble_esb": ("CONFIG_ESB_MPSL_TIMESLOT=y", "esb_radio"),
            "external_coexistence": ("CONFIG_MPSL_CX_1WIRE=y", "external_coexistence"),
        }
        for profile_id, (configuration, hil_requirement) in expected.items():
            with self.subTest(profile=profile_id):
                profile_root = PROFILES / profile_id
                profile = json.loads(
                    (profile_root / "profile.json").read_text(encoding="utf-8")
                )
                self.assertEqual(profile["id"], profile_id)
                self.assertIn("ble", profile["features"])
                self.assertIn("radio", profile["features"])
                self.assertIn(hil_requirement, profile["requires_hil"])
                self.assertIn(
                    configuration,
                    (profile_root / "prj.conf").read_text(encoding="utf-8"),
                )

    def test_one_wire_overlay_avoids_dap_uart_pins(self) -> None:
        """! @brief 실물 결선은 P1.10/P1.14만 사용하고 DAP UART P1.4~P1.7을 피합니다. """
        overlay = (PROFILES / "external_coexistence/app.overlay").read_text(
            encoding="utf-8"
        )
        self.assertIn("<&gpio1 10 GPIO_ACTIVE_HIGH>", overlay)
        self.assertIn("<&gpio1 14 GPIO_ACTIVE_HIGH>", overlay)
        self.assertIn("coex = <&nrf_radio_coex>", overlay)
        self.assertNotIn("<&gpio1 4", overlay)
        self.assertNotIn("<&gpio1 7", overlay)

    def test_library_features_allow_only_dedicated_coexistence_profiles(self) -> None:
        """! @brief 조합별 feature graph가 direct radio double ownership을 계속 거부합니다. """
        coexistence = json.loads(
            (LIBRARY / "zephyr/feature.yml").read_text(encoding="utf-8")
        )
        self.assertEqual(coexistence["requires"], ["ble", "radio"])
        self.assertEqual(len(coexistence["compatible_profiles"]), 4)

        radio154 = json.loads(
            (
                ROOT
                / "libraries/NUCODE_Radio_IEEE802154/zephyr/feature.yml"
            ).read_text(encoding="utf-8")
        )
        esb = json.loads(
            (ROOT / "libraries/NUCODE_Radio_ESB/zephyr/feature.yml").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(radio154["conflicts"], ["radio-owner"])
        self.assertEqual(esb["conflicts"], ["radio-owner"])

    def test_three_board_examples_and_one_wire_template_are_registered(self) -> None:
        """! @brief 세 보드 조합 3개와 외부 결선 template의 metadata를 고정합니다. """
        metadata = json.loads(
            (ROOT / "libraries/example-metadata.json").read_text(encoding="utf-8")
        )["examples"]
        for name, profile in (
            ("BleMeshCoexistence", "coexistence_ble_mesh"),
            ("Ble154Coexistence", "coexistence_ble_154"),
            ("BleEsbCoexistence", "coexistence_ble_esb"),
        ):
            identity = f"NUCODE_Radio_Coexistence/{name}"
            with self.subTest(identity=identity):
                self.assertEqual(metadata[identity]["recommended_profile"], profile)
                self.assertEqual(metadata[identity]["board_count"], 3)

        external = metadata[
            "NUCODE_Radio_Coexistence/RadioCoexistenceOneWire"
        ]
        self.assertEqual(external["recommended_profile"], "external_coexistence")
        self.assertIn("P1.10", external["conditions"][0])
        self.assertIn("P1.14", external["conditions"][0])


if __name__ == "__main__":
    unittest.main()
