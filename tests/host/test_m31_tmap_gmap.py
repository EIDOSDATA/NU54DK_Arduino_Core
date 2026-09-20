#!/usr/bin/env python3
"""! @brief TMAP·GMAP 공개 역할 API와 역할별 profile 계약을 검사합니다. """

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
AUDIO = ROOT / "libraries/NUCODE_BLE_Audio"
EXAMPLES = AUDIO / "examples"


TMAP_EXAMPLES = {
    "TelephonyMediaGateway": (
        ("call_gateway", "unicast_media_sender"),
        ("CONFIG_BT_CAP_INITIATOR=y", "CONFIG_BT_BAP_UNICAST_CLIENT=y",
         "CONFIG_BT_VCP_VOL_CTLR=y", "CONFIG_BT_MCS=y", "CONFIG_BT_TBS=y"),
    ),
    "TelephonyMediaTerminal": (
        ("call_terminal", "unicast_media_receiver"),
        ("CONFIG_BT_CAP_ACCEPTOR=y", "CONFIG_BT_BAP_UNICAST_SERVER=y",
         "CONFIG_BT_VCP_VOL_REND=y", "CONFIG_BT_MCC=y"),
    ),
    "TelephonyMediaBroadcaster": (
        ("broadcast_media_sender",),
        ("CONFIG_BT_CAP_INITIATOR=y", "CONFIG_BT_BAP_BROADCAST_SOURCE=y"),
    ),
    "TelephonyMediaReceiver": (
        ("broadcast_media_receiver",),
        ("CONFIG_BT_CAP_ACCEPTOR=y", "CONFIG_BT_BAP_BROADCAST_SINK=y",
         "CONFIG_BT_VCP_VOL_REND=y"),
    ),
}

GMAP_EXAMPLES = {
    "GamingAudioGateway": (
        "unicast_game_gateway",
        ("CONFIG_BT_CAP_INITIATOR=y", "CONFIG_BT_BAP_UNICAST_CLIENT=y",
         "CONFIG_BT_VCP_VOL_CTLR=y"),
    ),
    "GamingAudioTerminal": (
        "unicast_game_terminal",
        ("CONFIG_BT_CAP_ACCEPTOR=y", "CONFIG_BT_BAP_UNICAST_SERVER=y"),
    ),
    "GamingAudioBroadcaster": (
        "broadcast_game_sender",
        ("CONFIG_BT_CAP_INITIATOR=y", "CONFIG_BT_BAP_BROADCAST_SOURCE=y",
         "CONFIG_BT_BAP_BROADCAST_ASSISTANT=y"),
    ),
    "GamingAudioReceiver": (
        "broadcast_game_receiver",
        ("CONFIG_BT_CAP_ACCEPTOR=y", "CONFIG_BT_BAP_BROADCAST_SINK=y",
         "CONFIG_BT_VCP_VOL_REND=y"),
    ),
}

STREAM_FLOWS = {
    "TelephonyMediaGateway": (
        "UnicastClient", "Lc3Codec", "audioSource.begin(", "audioSource.poll(",
        "codec.encode(", "audioSource.sendFrame(", "audioSource.stop(",
    ),
    "TelephonyMediaTerminal": (
        "UnicastServer", "Lc3Codec", "audioSink.begin(", "audioSink.readFrame(",
        "codec.decode(", "audioSink.end(",
    ),
    "TelephonyMediaBroadcaster": (
        "BroadcastSource", "Lc3Codec", "audioSource.begin(", "codec.encode(",
        "audioSource.sendFrame(", "audioSource.end(",
    ),
    "TelephonyMediaReceiver": (
        "BroadcastSink", "Lc3Codec", "audioSink.begin(", "audioSink.poll(",
        "audioSink.readFrame(", "codec.decode(", "audioSink.end(",
    ),
    "GamingAudioGateway": (
        "UnicastClient", "Lc3Codec", "audioSource.begin(", "audioSource.poll(",
        "codec.encode(", "audioSource.sendFrame(", "audioSource.stop(",
    ),
    "GamingAudioTerminal": (
        "UnicastServer", "Lc3Codec", "audioSink.begin(", "audioSink.readFrame(",
        "codec.decode(", "audioSink.end(",
    ),
    "GamingAudioBroadcaster": (
        "BroadcastSource", "Lc3Codec", "audioSource.begin(", "codec.encode(",
        "audioSource.sendFrame(", "audioSource.end(",
    ),
    "GamingAudioReceiver": (
        "BroadcastSink", "Lc3Codec", "audioSink.begin(", "audioSink.poll(",
        "audioSink.readFrame(", "codec.decode(", "audioSink.end(",
    ),
}


class TmapGmapContractTests(unittest.TestCase):
    """! @brief 역할 누락, 잘못된 dependency와 공개 경계 회귀를 거부합니다. """

    def test_public_header_has_all_roles_without_zephyr_types(self) -> None:
        """! @brief 열 역할과 고정 크기 공개 결과를 모두 노출합니다. """
        header = (AUDIO / "src/NUCODE_BLE_Audio.h").read_text(encoding="utf-8")
        for role in (
            "call_gateway", "call_terminal", "unicast_media_sender",
            "unicast_media_receiver", "broadcast_media_sender",
            "broadcast_media_receiver", "unicast_game_gateway",
            "unicast_game_terminal", "broadcast_game_sender",
            "broadcast_game_receiver",
        ):
            self.assertRegex(header, rf"\b{role}\b")
        for declaration in (
            "class TelephonyMediaRoles final", "struct GamingAudioFeatures",
            "struct GamingAudioPeer", "class GamingAudioRoles final",
        ):
            self.assertIn(declaration, header)
        self.assertNotRegex(header, r"#\s*include\s*[<\"]zephyr/")
        self.assertNotRegex(header, r"\bbt_[A-Za-z0-9_]+")

    def test_backend_uses_exact_profile_services_and_stale_handle_guards(self) -> None:
        """! @brief upstream TMAS/GMAS와 exact generation 연결 검사를 고정합니다. """
        source = (AUDIO / "src/NUCODE_BLE_Audio_ProfileRoles.cpp").read_text(
            encoding="utf-8"
        )
        for token in (
            "bt_tmap_register(", "bt_tmap_discover(", "bt_tmap_set_role(",
            "bt_gmap_register(", "bt_gmap_discover(", "bt_gmap_cb_register(",
            "internal::referenceConnection(connection)",
            "internal::handleForActiveConnection(connection)",
            "handle != tmap_context.connection", "handle != gmap_context.connection",
            "!BLEConnection.connected(connection)",
        ):
            self.assertIn(token, source)
        self.assertIn("supportsTmapRoles", source)
        self.assertIn("supportsGmapRoles", source)
        self.assertIn("validGmapFeatures", source)
        self.assertIn("return Error::unsupported;", source)
        self.assertIn("return Error::invalid_argument;", source)

    def test_tmap_role_examples_have_exact_service_dependencies(self) -> None:
        """! @brief 여섯 TMAP 역할의 sketch와 필수 service 조합을 검사합니다. """
        seen = set()
        for name, (roles, options) in TMAP_EXAMPLES.items():
            sketch = (EXAMPLES / name / f"{name}.ino").read_text(encoding="utf-8")
            config = (EXAMPLES / name / "prj.conf").read_text(encoding="utf-8")
            self.assertIn("CONFIG_BT_TMAP=y", config)
            self.assertIn("CONFIG_UTF8=y", config)
            self.assertIn("profile.begin(", sketch)
            self.assertIn("profile.poll(", sketch)
            self.assertIn("'r'", sketch)
            self.assertIn("'x'", sketch)
            for role in roles:
                self.assertIn(f"TelephonyMediaRole::{role}", sketch)
                seen.add(role)
            for option in options:
                self.assertIn(option, config)
            self.assertNotRegex(sketch, r"#\s*include\s*[<\"]zephyr/")
        self.assertEqual(len(seen), 6)

    def test_gmap_role_examples_have_exact_service_dependencies(self) -> None:
        """! @brief 네 GMAP 역할과 각 역할의 CAP/BAP/VCP dependency를 검사합니다. """
        seen = set()
        for name, (role, options) in GMAP_EXAMPLES.items():
            sketch = (EXAMPLES / name / f"{name}.ino").read_text(encoding="utf-8")
            config = (EXAMPLES / name / "prj.conf").read_text(encoding="utf-8")
            self.assertIn("CONFIG_BT_GMAP=y", config)
            self.assertIn("CONFIG_UTF8=y", config)
            self.assertIn(f"GamingAudioRole::{role}", sketch)
            self.assertIn("profile.begin(", sketch)
            self.assertIn("profile.poll(", sketch)
            self.assertIn("'r'", sketch)
            self.assertIn("'x'", sketch)
            self.assertIn("'q'", sketch)
            self.assertIn("Invalid GMAP feature rejected", sketch)
            self.assertIn("Error::invalid_argument", sketch)
            for option in options:
                self.assertIn(option, config)
            self.assertNotRegex(sketch, r"#\s*include\s*[<\"]zephyr/")
            seen.add(role)
        self.assertEqual(len(seen), 4)

    def test_upstream_role_contract_is_present_in_locked_sdk(self) -> None:
        """! @brief 고정 SDK source와 example metadata를 다른 target 결과로 대체하지 않습니다. """
        zephyr = Path("C:/ncs/v3.4.0/zephyr")
        if not zephyr.is_dir():
            self.skipTest("고정 NCS v3.4.0 checkout이 없습니다")
        tmap = (zephyr / "include/zephyr/bluetooth/audio/tmap.h").read_text(
            encoding="utf-8"
        )
        gmap = (zephyr / "include/zephyr/bluetooth/audio/gmap.h").read_text(
            encoding="utf-8"
        )
        for role in ("CG", "CT", "UMS", "UMR", "BMS", "BMR"):
            self.assertIn(f"BT_TMAP_ROLE_{role}", tmap)
        for role in ("UGG", "UGT", "BGS", "BGR"):
            self.assertIn(f"BT_GMAP_ROLE_{role}", gmap)
        for sample in ("tmap_central", "tmap_peripheral", "tmap_bms", "tmap_bmr"):
            metadata = (zephyr / f"samples/bluetooth/{sample}/sample.yaml").read_text(
                encoding="utf-8"
            )
            self.assertIn("native_sim", metadata)
            self.assertNotIn("nrf54l15dk", metadata)

    def test_role_examples_drive_real_bap_stream_procedures(self) -> None:
        """! @brief 역할 검색만으로 완료 처리하지 않고 공개 BAP 흐름을 고정합니다. """
        for name, tokens in STREAM_FLOWS.items():
            sketch = (EXAMPLES / name / f"{name}.ino").read_text(encoding="utf-8")
            self.assertIn("'s'", sketch)
            self.assertIn("'r'", sketch)
            self.assertIn("'x'", sketch)
            for token in tokens:
                self.assertIn(token, sketch)

    def test_public_examples_do_not_expose_development_identifiers(self) -> None:
        """! @brief 공개 surface에서 milestone 및 Zephyr 직접 호출을 거부합니다. """
        names = tuple(TMAP_EXAMPLES) + tuple(GMAP_EXAMPLES)
        for name in names:
            sketch = (EXAMPLES / name / f"{name}.ino").read_text(encoding="utf-8")
            self.assertNotRegex(sketch, r"\bM[0-9]{2}[A-Za-z0-9_]*")
            self.assertNotRegex(sketch, r"\b(?:bt|k|device)_[A-Za-z0-9_]+\s*\(")


if __name__ == "__main__":
    unittest.main()
