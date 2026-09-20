#!/usr/bin/env python3
"""! @brief MCP/MCS와 CCP/TBS 공개 API·예제·고정 SDK 계약을 검사합니다. """

from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
HEADER = ROOT / "libraries/NUCODE_BLE_Audio/src/NUCODE_BLE_Audio.h"
MEDIA = ROOT / "libraries/NUCODE_BLE_Audio/src/NUCODE_BLE_Audio_MediaControl.cpp"
CALL = ROOT / "libraries/NUCODE_BLE_Audio/src/NUCODE_BLE_Audio_CallControl.cpp"
EXAMPLES = ROOT / "libraries/NUCODE_BLE_Audio/examples"
SDK = Path("C:/ncs/v3.4.0/zephyr")


class MediaCallControlContractTests(unittest.TestCase):
    """! @brief W03-09 역할과 fail-closed 경계를 검사합니다. """

    def test_public_api_has_all_four_roles(self) -> None:
        """! @brief player/controller와 call server/client facade를 고정합니다. """
        text = HEADER.read_text(encoding="utf-8")
        for token in (
            "class MediaControlPlayer final", "class MediaControlClient final",
            "class CallControlServer final", "class CallControlClient final",
            "struct MediaSnapshot", "struct CallSnapshot", "enum class MediaCommand",
            "Error commandOpcode(std::uint8_t opcode) noexcept",
        ):
            self.assertIn(token, text)
        self.assertNotIn("zephyr/", text)
        self.assertNotRegex(text, r"\bbt_[A-Za-z0-9_]+")

    def test_media_backend_uses_real_mcs_mcc_and_object_paths(self) -> None:
        """! @brief 합성 성공 stub가 아닌 고정 SDK profile 호출을 확인합니다. """
        text = MEDIA.read_text(encoding="utf-8")
        for token in (
            "media_proxy_pl_init()", "bt_mcc_discover_mcs", "bt_mcc_read_track_title",
            "bt_mcc_read_track_position", "bt_mcc_read_opcodes_supported",
            "bt_mcc_send_cmd", "bt_mcc_set_current_track_obj_id", "commandOpcode",
            "internal::referenceConnection(connection)", "BT_CONN_CB_DEFINE",
        ):
            self.assertIn(token, text)
        self.assertIn("object_id > 0xffffffffffffULL", text)

    def test_call_backend_uses_ccp_server_and_tbs_client(self) -> None:
        """! @brief GTBS 등록·통지·control point와 state read를 고정합니다. """
        text = CALL.read_text(encoding="utf-8")
        for token in (
            "bt_ccp_call_control_server_register_bearer",
            "bt_ccp_call_control_server_unregister_bearer",
            "bt_tbs_remote_incoming", "bt_tbs_remote_answer",
            "bt_tbs_client_discover", "bt_tbs_client_read_call_state",
            "bt_tbs_client_originate_call", "bt_tbs_client_accept_call",
            "bt_tbs_client_hold_call", "bt_tbs_client_retrieve_call",
            "bt_tbs_client_terminate_call", "BT_CONN_CB_DEFINE",
        ):
            self.assertIn(token, text)
        self.assertIn("BT_TBS_RESULT_CODE_STATE_MISMATCH", text)

    def test_call_server_normalizes_single_uri_scheme_for_fixed_sdk(self) -> None:
        """! @brief 고정 SDK가 단일 URI scheme도 검색하도록 종단 구분자를 보장합니다. """
        text = CALL.read_text(encoding="utf-8")
        self.assertIn("void copySchemeList(", text)
        self.assertIn("destination[length - 1U] != ','", text)
        self.assertIn("copySchemeList(callServer.schemes, uri_schemes);", text)
        self.assertIn("char schemes[maximumSchemeLength + 2U]", text)

    def test_role_examples_have_user_visible_commands_and_profiles(self) -> None:
        """! @brief 네 역할의 Arduino 흐름과 Kconfig를 함께 검사합니다. """
        expectations = {
            "MediaControlPlayer": ("player.begin(", "CONFIG_BT_MCS=y"),
            "MediaControlClient": ("controller.command(", "CONFIG_BT_MCC=y"),
            "CallControlServer": ("callServer.incoming(", "CONFIG_BT_CCP_CALL_CONTROL_SERVER=y"),
            "CallControlClient": ("callClient.originate(", "CONFIG_BT_CCP_CALL_CONTROL_CLIENT=y"),
        }
        for name, (flow, option) in expectations.items():
            sketch = (EXAMPLES / name / f"{name}.ino").read_text(encoding="utf-8")
            config = (EXAMPLES / name / "prj.conf").read_text(encoding="utf-8")
            self.assertIn("void setup()", sketch)
            self.assertIn("void loop()", sketch)
            self.assertIn(flow, sketch)
            self.assertIn(option, config)
            self.assertNotIn("#include <zephyr/", sketch)
            self.assertNotRegex(sketch, r"\bbt_[A-Za-z0-9_]+\s*\(")

        media_client = (EXAMPLES / "MediaControlClient/MediaControlClient.ino").read_text(
            encoding="utf-8"
        )
        call_client = (EXAMPLES / "CallControlClient/CallControlClient.ino").read_text(
            encoding="utf-8"
        )
        for token in (
            "MEDIA_NEG_OPCODE", "MEDIA_NEG_STALE_OBJECT", "complete=1 normal_ops=",
            "rejected=1", 'report("MEDIA_RECOVERY", controller.refresh())',
        ):
            self.assertIn(token, media_client)
        for token in (
            "CALL_NEG_STALE_INDEX", "CALL_NEG_INVALID_TRANSITION",
            "complete=1 normal_ops=", "rejected=1",
        ):
            self.assertIn(token, call_client)

    def test_media_player_reserves_objects_and_notification_buffers(self) -> None:
        """! @brief MPL 객체와 연속 상태·명령 통지에 필요한 pool을 확보합니다. """
        config = (EXAMPLES / "MediaControlPlayer/prj.conf").read_text(encoding="utf-8")
        self.assertIn("CONFIG_BT_OTS_MAX_OBJ_CNT=0x14", config)
        self.assertIn("CONFIG_BT_ATT_TX_COUNT=12", config)
        self.assertNotIn("CONFIG_BT_OTS_MAX_INST_CNT=2", config)

    def test_fixed_sdk_sources_and_metadata_are_present(self) -> None:
        """! @brief 고정 checkout의 source와 nRF54 allowlist 부재를 정확히 유지합니다. """
        required = (
            "include/zephyr/bluetooth/audio/mcc.h",
            "include/zephyr/bluetooth/audio/mcs.h",
            "include/zephyr/bluetooth/audio/tbs.h",
            "include/zephyr/bluetooth/audio/ccp.h",
            "samples/bluetooth/ccp_call_control_client/sample.yaml",
            "samples/bluetooth/ccp_call_control_server/sample.yaml",
            "samples/bluetooth/tmap_central/src/mcp_server.c",
            "samples/bluetooth/tmap_peripheral/src/mcp_ctlr.c",
        )
        for relative in required:
            self.assertTrue((SDK / relative).is_file(), relative)
        for sample in ("ccp_call_control_client", "ccp_call_control_server"):
            metadata = (SDK / f"samples/bluetooth/{sample}/sample.yaml").read_text(
                encoding="utf-8"
            )
            self.assertNotIn("nrf54l15dk", metadata)

    def test_negative_contract_rejects_invalid_identifiers(self) -> None:
        """! @brief stale/invalid object와 call index가 stack 호출 전에 거부됩니다. """
        media = MEDIA.read_text(encoding="utf-8")
        call = CALL.read_text(encoding="utf-8")
        self.assertIn("(object_id == 0U)", media)
        self.assertIn("if (call_index == 0U)", call)
        self.assertIn("maximumUriLength", call)
        self.assertIn("RemoteControlStage::operating", media)
        self.assertIn("RemoteControlStage::operating", call)


if __name__ == "__main__":
    unittest.main()
