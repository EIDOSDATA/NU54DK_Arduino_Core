"""! @brief M32-W09 단독 IEEE 802.15.4와 ESB 공개 계약을 검사합니다. """

from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
RADIO154 = ROOT / "libraries/NUCODE_Radio_IEEE802154"
ESB = ROOT / "libraries/NUCODE_Radio_ESB"


class M32StandaloneRadioContractTests(unittest.TestCase):
    """! @brief 단독 radio의 bounded lifecycle과 검증 profile을 고정합니다. """

    def test_public_headers_expose_sequence_hash_ack_and_stop(self) -> None:
        """! @brief 두 공개 API가 raw SDK type 없이 공통 관측값을 제공합니다. """
        for library, header_name, global_name in (
            (RADIO154, "NUCODE_Radio_IEEE802154.h", "NUCODERadio154"),
            (ESB, "NUCODE_Radio_ESB.h", "NUCODEEsb"),
        ):
            header = (library / "src" / header_name).read_text(encoding="utf-8")
            for token in (
                "struct Configuration", "struct Packet", "struct Statistics",
                "sequence", "hash_valid", "tx_acknowledged", "tx_failed",
                "begin(", "send(", "cancel()", "stop()", "lastDriverError",
                global_name,
            ):
                with self.subTest(library=library.name, token=token):
                    self.assertIn(token, header)
            self.assertNotIn("#include <zephyr/", header)
            self.assertNotIn("struct esb_", header)

    def test_radio154_backend_returns_buffers_and_bounds_retry(self) -> None:
        """! @brief ACK, 재전송, 수신 buffer 반환과 deinit 경계를 요구합니다. """
        backend = (RADIO154 / "src/NUCODE_Radio_IEEE802154.cpp").read_text(
            encoding="utf-8"
        )
        for token in (
            "nrf_802154_transmit_raw", "NRF_802154_TX_ERROR_NO_ACK",
            "k_work_reschedule", "nrf_802154_buffer_free_raw",
            "nrf_802154_auto_ack_set(true)", "nrf_802154_sleep()",
            "nrf_802154_reinit()", "k_msgq_put", "packetHash",
        ):
            with self.subTest(token=token):
                self.assertIn(token, backend)
        self.assertNotIn("malloc(", backend)
        self.assertNotIn("new ", backend)

    def test_esb_backend_uses_hardware_ack_retry_and_fifo_cleanup(self) -> None:
        """! @brief PTX/PRX ACK와 bounded STOP이 실제 ESB API에 연결됩니다. """
        backend = (ESB / "src/NUCODE_Radio_ESB.cpp").read_text(encoding="utf-8")
        for token in (
            "ESB_PROTOCOL_ESB_DPL", "retransmit_count", "ESB_EVENT_TX_SUCCESS",
            "ESB_EVENT_TX_FAILED", "esb_read_rx_payload", "esb_suspend()",
            "esb_flush_tx()", "esb_flush_rx()", "esb_disable()", "packetHash",
            "result == -EALREADY", "waitForIdle(state.configuration.stop_timeout_ms)",
            "state.driver_error = -ETIMEDOUT",
        ):
            with self.subTest(token=token):
                self.assertIn(token, backend)
        self.assertNotIn("malloc(", backend)
        self.assertNotIn("new ", backend)

    def test_dedicated_profiles_forbid_cross_radio_ownership(self) -> None:
        """! @brief 각 단독 profile과 feature가 다른 RADIO backend를 거부합니다. """
        profile154 = json.loads(
            (ROOT / "variants/nu54dk/profiles/radio_ieee802154/profile.json").read_text(
                encoding="utf-8"
            )
        )
        profile_esb = json.loads(
            (ROOT / "variants/nu54dk/profiles/radio_esb/profile.json").read_text(
                encoding="utf-8"
            )
        )
        feature154 = json.loads((RADIO154 / "zephyr/feature.yml").read_text(encoding="utf-8"))
        feature_esb = json.loads((ESB / "zephyr/feature.yml").read_text(encoding="utf-8"))
        self.assertEqual(feature154["conflicts"], ["radio-owner"])
        self.assertEqual(feature_esb["conflicts"], ["radio-owner"])
        self.assertEqual(
            feature154["compatible_profiles"],
            ["radio_ieee802154", "coexistence_ble_154"],
        )
        self.assertEqual(
            feature_esb["compatible_profiles"],
            ["radio_esb", "coexistence_ble_esb"],
        )
        self.assertEqual(profile154["features"], ["gpio", "time", "serial", "radio"])
        self.assertEqual(profile_esb["features"], ["gpio", "time", "serial", "radio"])

    def test_four_verification_examples_are_registered(self) -> None:
        """! @brief 두 protocol의 송수신 역할과 권장 profile을 metadata에 고정합니다. """
        metadata = json.loads(
            (ROOT / "libraries/example-metadata.json").read_text(encoding="utf-8")
        )["examples"]
        expected = {
            "NUCODE_Radio_IEEE802154/Radio154Transmitter": "radio_ieee802154",
            "NUCODE_Radio_IEEE802154/Radio154Receiver": "radio_ieee802154",
            "NUCODE_Radio_ESB/EsbPtx": "radio_esb",
            "NUCODE_Radio_ESB/EsbPrx": "radio_esb",
        }
        for identity, profile in expected.items():
            with self.subTest(identity=identity):
                self.assertEqual(metadata[identity]["recommended_profile"], profile)
                self.assertEqual(metadata[identity]["board_count"], 2)


if __name__ == "__main__":
    unittest.main()
