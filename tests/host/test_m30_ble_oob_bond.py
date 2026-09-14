"""! @brief M30-W03 OOB frame/NDEF와 bond metadata migration 계약을 검증합니다. """
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
PUBLIC_HEADER = ROOT / "libraries/NUCODE_BLE_Security/src/NUCODE_BLE_Security.h"
INTERNAL_HEADER = (
    ROOT / "libraries/NUCODE_BLE_Security/src/internal/security/SecurityInternal.h"
)
OOB_SOURCE = (
    ROOT / "libraries/NUCODE_BLE_Security/src/internal/security/SecurityOob.cpp"
)
BOND_SOURCE = (
    ROOT / "libraries/NUCODE_BLE_Security/src/internal/security/SecurityBond.cpp"
)
PAIRING_SOURCE = (
    ROOT / "libraries/NUCODE_BLE_Security/src/internal/security/SecurityPairing.cpp"
)
KCONFIG = ROOT / "zephyr/config/ble.Kconfig"
PRODUCTION_RUNNER = ROOT / "tests/host/test_r12_ble_security.py"


class M30BleOobBondTests(unittest.TestCase):
    """! @brief W03의 bounded carrier와 fail-closed key 수명주기를 고정합니다. """

    def test_public_oob_record_and_two_carrier_codecs_are_bounded(self) -> None:
        """! @brief 유선과 NFC가 같은 canonical record와 192-byte 상한을 사용합니다. """

        header = PUBLIC_HEADER.read_text(encoding="utf-8")
        for token in (
            "struct SecureConnectionsOobRecord",
            "PeerAddress identity = {};",
            "PeerAddress pairing_address = {};",
            "std::uint8_t random[16] = {};",
            "std::uint8_t confirm[16] = {};",
            "std::uint8_t session_nonce[16] = {};",
            "maximum_frame_bytes = 192U",
            "maximum_ndef_bytes = 192U",
            "createLocalOob(OobRole role",
            "setRemoteOob(OobRole local_role",
            "clearOob(OobRole role)",
        ):
            self.assertIn(token, header, token)

    def test_oob_is_two_slot_crc_and_exact_link_fail_closed(self) -> None:
        """! @brief OOB material은 heap 없이 역할별 두 slot과 exact 주소로 제한됩니다. """

        internal = INTERNAL_HEADER.read_text(encoding="utf-8")
        source = OOB_SOURCE.read_text(encoding="utf-8")
        self.assertIn("OobSlot slots[maximum_security_links]", internal)
        self.assertIn("frame_bytes = 74U", PUBLIC_HEADER.read_text(encoding="utf-8"))
        for token in (
            "crc32(buffer, frame_crc_offset)",
            "bt_le_oob_get_local(BT_ID_DEFAULT, &native)",
            "bt_le_oob_set_sc_data(connection",
            "sameAddress(snapshot.local.pairing_address, local_address)",
            "sameAddress(snapshot.remote.pairing_address, remote_address)",
            "bt_conn_auth_cancel(connection)",
        ):
            self.assertIn(token, source, token)
        self.assertNotIn("new ", source)
        self.assertNotIn("malloc(", source)

    def test_nfc_adapter_is_default_off_and_does_not_claim_rf(self) -> None:
        """! @brief NDEF adapter는 opt-in serialization이며 NFCT를 직접 켜지 않습니다. """

        kconfig = KCONFIG.read_text(encoding="utf-8")
        source = OOB_SOURCE.read_text(encoding="utf-8")
        self.assertIn("config NUCODE_BLE_NFC_OOB_ADAPTER", kconfig)
        self.assertIn("default n", kconfig)
        self.assertIn('ndef_mime_type[] = "application/vnd.bluetooth.le.oob"', source)
        self.assertNotIn("nrfx_nfct", source)
        self.assertNotIn("nfc_t4t", source)

    def test_bond_metadata_is_four_slot_versioned_and_fail_closed(self) -> None:
        """! @brief resolved identity·16-byte SC·DB revision을 네 record에서 검사합니다. """

        internal = INTERNAL_HEADER.read_text(encoding="utf-8")
        source = BOND_SOURCE.read_text(encoding="utf-8")
        self.assertIn("maximum_bond_records = 4U", internal)
        self.assertIn("BondMetadataSnapshot metadata[maximum_bond_records]", internal)
        for token in (
            "legacy_metadata_schema = 1U",
            "current_metadata_schema = 2U",
            "settings_load_one",
            "settings_save_one",
            "settings_delete",
            "record[13] != 16U",
            "metadata.database_revision != database_revision",
            "isResolvablePrivateAddress(peer)",
            "bt_unpair(BT_ID_DEFAULT, &peer)",
            "BT_SECURITY_FLAG_SC",
            "BT_SECURITY_FLAG_OOB",
        ):
            self.assertIn(token, source, token)

    def test_production_host_executes_oob_and_migration_negatives(self) -> None:
        """! @brief production source가 정상·mismatch·legacy·future·truncated를 실행합니다. """

        runner = PRODUCTION_RUNNER.read_text(encoding="utf-8")
        pairing = PAIRING_SOURCE.read_text(encoding="utf-8")
        for scenario in (
            "oob_codec",
            "oob_pairing",
            "oob_mismatch",
            "bond_legacy_migration",
            "bond_future_rejected",
            "bond_truncated_rejected",
        ):
            self.assertIn(scenario, runner)
        self.assertIn("persistBondMetadata(connection)", pairing)


if __name__ == "__main__":
    unittest.main()
