"""! @brief M29-W05 robust GATT cache와 database migration source 계약을 검증합니다. """

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
PUBLIC = ROOT / "libraries" / "NUCODE_BLE" / "src" / "NUCODE_BLE_GATT.h"
INTERNAL = ROOT / "libraries" / "NUCODE_BLE" / "src" / "internal" / "gatt"
PROFILE = ROOT / "libraries" / "NUCODE_BLE" / "zephyr" / "ble-nus.conf"
TARGET = ROOT / "tests" / "zephyr" / "m29_ble_cache_hil" / "src" / "main.cpp"
RUNNER = ROOT / "tests" / "hil" / "nu54dk" / "m29_ble_cache.py"
EXAMPLES = ROOT / "libraries" / "NUCODE_BLE_Security" / "examples"


class M29BleCacheTests(unittest.TestCase):
    """! @brief 공개 경계·고정 자원·fail-closed migration 계약을 고정합니다. """

    @classmethod
    def setUpClass(cls) -> None:
        """! @brief 관련 production source를 UTF-8로 한 번 읽습니다. """

        cls.public = PUBLIC.read_text(encoding="utf-8")
        cls.cache = (INTERNAL / "GattCache.cpp").read_text(encoding="utf-8")
        cls.internal = (INTERNAL / "GattInternal.h").read_text(encoding="utf-8")
        cls.profile = PROFILE.read_text(encoding="utf-8")
        cls.target = TARGET.read_text(encoding="utf-8")
        cls.runner = RUNNER.read_text(encoding="utf-8")

    def test_public_api_exposes_revision_hash_and_per_link_cache(self) -> None:
        """! @brief database identity와 link별 cache API가 공개됐는지 검사합니다. """

        for token in (
            "class GattDatabase final",
            "static constexpr std::size_t hash_length = 16U",
            "setRevision(std::uint32_t revision)",
            "hash(std::uint8_t output[hash_length])",
            "discoverCached(BLEConnectionHandle connection",
            "cacheState(BLEConnectionHandle connection)",
            "invalidateCache(BLEConnectionHandle connection)",
            "BLEGattCacheStatistics cacheStatistics()",
            "extern nucode::ble::GattDatabase BLEGattDatabase",
        ):
            self.assertIn(token, self.public)

    def test_cache_storage_is_fixed_and_crc_protected(self) -> None:
        """! @brief cache가 4x84-byte 고정 record이고 동적 컨테이너가 아닌지 검사합니다. """

        for token in (
            "cache_record_length = 84U",
            "maximum_cache_records = 4U",
            "records[maximum_cache_records][cache_record_length]",
            "validCacheRecord(",
            "getLe32(&record[80]) != crc32(record, 80U)",
            "getLe16(&record[8]) != schema_version",
            "::memcmp(&record[17], hash, GattDatabase::hash_length)",
        ):
            self.assertIn(token, self.cache)
        self.assertNotIn("std::vector", self.cache)
        self.assertNotIn("malloc(", self.cache)
        self.assertNotIn("new ", self.cache)

    def test_cache_requires_resolved_bonded_identity(self) -> None:
        """! @brief RPA 주소 자체가 아닌 resolved bonded identity만 허용하는지 검사합니다. """

        self.assertIn("BLEConnection.identityResolved(state.connection_handle)", self.cache)
        self.assertIn("BLEConnection.peerAddress(state.connection_handle)", self.cache)
        self.assertIn("bt_le_bond_exists(BT_ID_DEFAULT, bt_conn_get_dst(connection))", self.cache)
        self.assertIn("return false;\n#endif", self.cache)

    def test_service_changed_clears_handles_before_record_erasure(self) -> None:
        """! @brief Service Changed 수신 즉시 stale handle을 먼저 없애는지 검사합니다. """

        callback_start = self.cache.index("std::uint8_t cacheServiceChanged(")
        callback_end = self.cache.index("void completeCacheDiscovery", callback_start)
        callback = self.cache[callback_start:callback_end]
        self.assertLess(callback.index("clearCachedHandles(*state)"), callback.index("eraseCacheRecords(identity)"))
        self.assertIn("CacheStage::rediscovery_pending", callback)
        self.assertIn("persistent_cache.stale_handle_rejected", callback)
        self.assertIn("BLEGattClientEvent::cache_invalidated", callback)

    def test_standard_robust_cache_handshake_is_complete(self) -> None:
        """! @brief SC/CCC/Client Features/Database Hash 절차가 모두 연결됐는지 검사합니다. """

        for token in (
            "BT_UUID_GATT_SC",
            "BT_UUID_GATT_CCC",
            "BT_UUID_GATT_CLIENT_FEATURES",
            "BT_UUID_GATT_DB_HASH",
            "BT_GATT_CCC_INDICATE",
            "BT_GATT_SUBSCRIBE_FLAG_VOLATILE",
            "BLEGattClientEvent::database_hash_read",
            "BLEGattClientEvent::service_changed",
        ):
            self.assertIn(token, self.cache)
        self.assertIn("remote_database_hash[GattDatabase::hash_length]", self.internal)

    def test_remote_properties_use_explicit_zephyr_conversion(self) -> None:
        """! @brief Zephyr bit를 공개 enum으로 직접 cast하는 회귀를 차단합니다. """

        self.assertIn("publicProperties(characteristic->properties)", self.cache)
        self.assertNotIn(
            "static_cast<BLEProperty>(characteristic->properties)", self.cache
        )

    def test_profile_enables_cache_bond_and_persistent_settings(self) -> None:
        """! @brief production profile에 robust caching과 bond 저장 조건을 검사합니다. """

        for token in (
            "CONFIG_BT_GATT_SERVICE_CHANGED=y",
            "CONFIG_BT_GATT_CACHING=y",
            "CONFIG_BT_SMP=y",
            "CONFIG_BT_BONDABLE=y",
            "CONFIG_BT_SETTINGS=y",
            "CONFIG_SETTINGS=y",
            "CONFIG_SETTINGS_ZMS=y",
            "CONFIG_FLASH=y",
        ):
            self.assertIn(token, self.profile)

    def test_target_and_runner_bind_exact_w05_quantities(self) -> None:
        """! @brief target와 strict runner가 같은 W05 protocol·정량값을 고정하는지 검사합니다. """

        for token in (
            'protocol[] = "M29W05|1"',
            "BLEClient.discoverCached(connection_handle, service_uuid, characteristic_uuid",
            "reconnects == required_reconnects",
            "statistics.corrupt_rejected != 1U",
            "new_value_handle == old_value_handle",
            "service_changed_events != 1U",
            "corrupt_record[84]",
            "bt_le_bond_exists(BT_ID_DEFAULT, bt_conn_get_dst(connection))",
            "settings_subsys_init()",
        ):
            self.assertIn(token, self.target)
        for token in (
            'PROTOCOL = "M29W05|1"',
            "reconnects=20|hash_reads=24",
            "cache_restored=20",
            "corrupt_rejected=1|stale=0",
            '"cache_corruption_accepts": 0',
            '"stale_handle_uses": 0',
        ):
            self.assertIn(token, self.runner)

    def test_examples_pair_before_using_public_cache_api(self) -> None:
        """! @brief 양 role 예제가 bonding·revision·비동기 결과를 빠짐없이 처리합니다. """

        peripheral = (EXAMPLES / "GattCachePeripheral" / "GattCachePeripheral.ino").read_text(
            encoding="utf-8"
        )
        central = (EXAMPLES / "GattCacheCentral" / "GattCacheCentral.ino").read_text(
            encoding="utf-8"
        )
        for token in (
            "BLEGattDatabase.setRevision(databaseRevision)",
            "BLESecurity.requestSecurity()",
            "BLESecurity.acceptPairing(true)",
            "if (!cacheValue.notify(information.connection))",
        ):
            self.assertIn(token, peripheral)
        for token in (
            "BLESecurity.requestSecurity()",
            "BLESecurity.acceptPairing(true)",
            "BLEClient.discoverCached(peerConnection, serviceUuid, valueUuid",
            "BLEGattClientEvent::cache_restored",
            "BLEGattClientEvent::service_changed",
            "BLEGattClientEvent::operation_failed",
        ):
            self.assertIn(token, central)


if __name__ == "__main__":
    unittest.main()
