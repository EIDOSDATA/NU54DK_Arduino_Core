"""! @brief M29-W07 Signed Write·EATT opt-in 공개 계약을 검증합니다. """

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
PUBLIC = ROOT / "libraries/NUCODE_BLE/src/NUCODE_BLE_GATT.h"
CLIENT = ROOT / "libraries/NUCODE_BLE/src/internal/gatt/GattClient.cpp"
SESSION = ROOT / "libraries/NUCODE_BLE/src/NUCODE_BLE_GATT.cpp"
SIGNING = ROOT / "libraries/NUCODE_BLE_LegacySigning"
EATT = ROOT / "libraries/NUCODE_BLE_EATT"
HOST_SCENARIO = ROOT / "tests/host/r12_ble_gatt_main.cpp"
HOST_DRIVER = ROOT / "tests/host/test_r12_ble_gatt.py"
TARGET = ROOT / "tests/zephyr/m29_ble_signed_eatt_hil"
ARDUINO_SMOKE = ROOT / "tests/arduino-cli/run_smoke.py"


class M29BleSignedEattTests(unittest.TestCase):
    """! @brief deprecated·experimental 경계와 고정 자원을 fail-closed로 고정합니다. """

    def test_signed_write_is_deprecated_default_off_opt_in(self):
        """! @brief signing을 기본 profile에 넣지 않고 별도 library만 활성화합니다. """
        header = (SIGNING / "src/NUCODE_BLE_LegacySigning.h").read_text(encoding="utf-8")
        feature = (SIGNING / "zephyr/feature.yml").read_text(encoding="utf-8")
        config = (SIGNING / "zephyr/ble-legacy-signing.conf").read_text(encoding="utf-8")
        for token in (
            "deprecated = true",
            "default_enabled = false",
            '"id": "nucode.ble.legacy_signing"',
            "CONFIG_BT_SIGNING=y",
            "CONFIG_BT_SMP_SC_PAIR_ONLY=n",
            "CONFIG_BT_SETTINGS=y",
        ):
            self.assertIn(token, header + feature + config)

    def test_sign_counters_are_persisted_after_stack_completion(self):
        """! @brief CSRK counter는 정상 main-thread와 queue 포화 fallback에서 저장합니다. """
        adapter = (SIGNING / "src/NUCODE_BLE_LegacySigning.cpp").read_text(
            encoding="utf-8"
        )
        session = SESSION.read_text(encoding="utf-8")
        client = CLIENT.read_text(encoding="utf-8")
        for token in (
            "BT_KEYS_LOCAL_CSRK | BT_KEYS_REMOTE_CSRK",
            "keys->local_csrk.cnt",
            "keys->remote_csrk.cnt",
            "bt_keys_store(keys)",
        ):
            self.assertIn(token, adapter)
        self.assertIn("BLEGattClientEvent::signed_write_complete", client + session)
        self.assertIn("nucode_ble_signing_persist(connection)", session)
        self.assertIn("bt_conn_get_security(connection) == BT_SECURITY_L1", session)
        self.assertIn("disconnect 전까지 busy를 유지", session)
        self.assertIn("완료 event 포화 시에도 전송 counter를 저장", client)
        self.assertIn("queue 포화 시에도 수신 counter를 되돌릴 수 없도록", session)

    def test_public_api_preserves_ordinals_and_adds_signed_write(self):
        """! @brief 기존 event ordinal은 유지하고 신규 event는 끝에 추가합니다. """
        text = PUBLIC.read_text(encoding="utf-8")
        self.assertLess(text.index("operation_failed,"), text.index("signed_write_complete,"))
        for token in (
            "authenticated_signed_write",
            "writeSigned(const void *data, std::size_t length)",
            "writeSigned(BLEConnectionHandle connection",
        ):
            self.assertIn(token, text)

    def test_eatt_is_experimental_encrypted_two_bearer_opt_in(self):
        """! @brief EATT build와 runtime 모두 암호화·두 bearer 상한을 강제합니다. """
        header = (EATT / "src/NUCODE_BLE_EATT.h").read_text(encoding="utf-8")
        feature = (EATT / "zephyr/feature.yml").read_text(encoding="utf-8")
        config = (EATT / "zephyr/ble-eatt.conf").read_text(encoding="utf-8")
        client = CLIENT.read_text(encoding="utf-8")
        for token in (
            "experimental = true",
            "default_enabled = false",
            "maximum_bearers_per_connection = 2U",
            '"id": "nucode.ble.eatt"',
            "CONFIG_BT_EATT=y",
            "CONFIG_BT_EATT_MAX=2",
            "CONFIG_BT_EATT_AUTO_CONNECT=n",
            "bt_conn_get_security(connection) < BT_SECURITY_L2",
        ):
            self.assertIn(token, header + feature + config + client)

    def test_eatt_operations_report_selected_bearer(self):
        """! @brief read/write가 enhanced-only를 선택하고 event가 bearer를 복사합니다. """
        public = PUBLIC.read_text(encoding="utf-8")
        client = CLIENT.read_text(encoding="utf-8")
        session = SESSION.read_text(encoding="utf-8")
        for token in (
            "BLEGattBearer bearer",
            "BT_ATT_CHAN_OPT_ENHANCED_ONLY",
            "state->read_parameters.chan_opt = zephyrBearer(bearer)",
            "state->write_parameters.chan_opt = zephyrBearer(bearer)",
            ".bearer = record.bearer",
        ):
            self.assertIn(token, public + client + session)

    def test_host_scenarios_cover_success_negative_and_persistence_failure(self):
        """! @brief production fake stack이 signing과 EATT 오류·성공을 실행합니다. """
        scenario = HOST_SCENARIO.read_text(encoding="utf-8")
        driver = HOST_DRIVER.read_text(encoding="utf-8")
        for token in (
            '"m29_signed_write"',
            '"m29_signed_overflow"',
            '"m29_eatt"',
            "mock_command_signed[0]",
            "signing_persist_result = -EIO",
            "BLEClient.busy()",
            "BLEEatt.connect(observed_handles[0], 2U)",
            "BT_ATT_CHAN_OPT_ENHANCED_ONLY",
        ):
            self.assertIn(token, scenario + driver)

    def test_examples_and_target_make_policy_visible(self):
        """! @brief 사용자 예제와 target build가 opt-in 경고·오류를 숨기지 않습니다. """
        signing_examples = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted((SIGNING / "examples").rglob("*.ino"))
        )
        eatt_examples = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted((EATT / "examples").rglob("*.ino"))
        )
        target = (TARGET / "src/main.cpp").read_text(encoding="utf-8")
        cases = (TARGET / "testcase.yaml").read_text(encoding="utf-8")
        smoke = ARDUINO_SMOKE.read_text(encoding="utf-8")
        for token in (
            "WARNING: Authenticated Signed Write is deprecated legacy opt-in",
            "BLEClient.writeSigned",
            "BLESecurity.requestSecurity()",
        ):
            self.assertIn(token, signing_examples)
        for token in (
            "WARNING: EATT is experimental opt-in",
            "BLEEatt.connect(peer, 2U)",
            "BLEGattBearer::enhanced",
        ):
            self.assertIn(token, eatt_examples)
        self.assertIn('constexpr char protocol[] = "M29W07|1"', target)
        self.assertIn("nucode.m29.ble_signed_eatt_peripheral", cases)
        self.assertIn("nucode.m29.ble_signed_eatt_central", cases)
        for token in (
            '"NUCODE_BLE_LegacySigning"',
            '"nucode.ble.legacy_signing"',
            '"NUCODE_BLE_EATT"',
            '"nucode.ble.eatt"',
        ):
            self.assertIn(token, smoke)

    def test_hil_nonce_fits_legacy_advertising_budget(self):
        """! @brief exact RF nonce가 31-byte legacy 광고 예산을 넘지 않게 고정합니다. """
        target = (TARGET / "src/main.cpp").read_text(encoding="utf-8")
        self.assertIn("legacy_manufacturer_serialized_length", target)
        self.assertIn("Advertising::maximum_payload_length", target)
        self.assertIn("validRfNonce(result)", target)
        self.assertIn("setManufacturerData(company_id, nonce_binary", target)
        self.assertNotIn("BLEAdvertising.addServiceUuid(service_uuid)", target)
        self.assertNotIn("BLEScan.filterServiceUuid(service_uuid)", target)

    def test_hil_discovery_failure_preserves_event_class(self):
        """! @brief discovery event 종류와 완료 뒤 상태 실패를 서로 구분합니다. """
        target = (TARGET / "src/main.cpp").read_text(encoding="utf-8")
        self.assertIn(
            'fail("discovery_event", static_cast<int>(information.event))', target
        )
        self.assertIn('fail("discovery_state")', target)
        self.assertNotIn('fail("discovery_result")', target)

    def test_hil_enters_signing_phase_before_write_completion(self):
        """! @brief 동기성 completion도 discovery event로 오분류하지 않습니다. """
        target = (TARGET / "src/main.cpp").read_text(encoding="utf-8")
        phase_assignment = target.index("phase = Phase::signing;")
        write_start = target.index("BLEClient.writeSigned(connection_handle")
        self.assertLess(phase_assignment, write_start)
        self.assertIn(
            "mode == Mode::sign && phase == Phase::signing &&", target
        )

    def test_hil_reports_link_specific_discovery_failure(self):
        """! @brief 전역 ENOENT보다 뒤따르는 link별 GATT 실패를 판정합니다. """
        target = (TARGET / "src/main.cpp").read_text(encoding="utf-8")
        self.assertIn(
            "phase == Phase::discovering && driver_error == -ENOENT", target
        )
        self.assertIn('fail("gatt_operation", information.status)', target)


if __name__ == "__main__":
    unittest.main(verbosity=2)
