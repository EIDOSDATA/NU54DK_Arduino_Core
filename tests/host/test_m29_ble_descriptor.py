"""! @brief M29-W04 descriptor·authorization·read-multiple source 계약을 검증합니다. """

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
PUBLIC = ROOT / "libraries" / "NUCODE_BLE" / "src" / "NUCODE_BLE_GATT.h"
INTERNAL = ROOT / "libraries" / "NUCODE_BLE" / "src" / "internal" / "gatt"
PROFILE = ROOT / "libraries" / "NUCODE_BLE" / "zephyr" / "ble-nus.conf"
TARGET = ROOT / "tests" / "zephyr" / "m29_ble_descriptor_hil" / "src" / "main.cpp"
RUNNER = ROOT / "tests" / "hil" / "nu54dk" / "m29_ble_descriptor.py"
EXAMPLES = ROOT / "libraries" / "NUCODE_BLE" / "examples"


class M29BleDescriptorTests(unittest.TestCase):
    """! @brief W04의 공개 경계와 고정 자원 구현을 fail-closed로 고정합니다. """

    @classmethod
    def setUpClass(cls) -> None:
        """! @brief 관련 production source를 UTF-8로 한 번 읽습니다. """

        cls.public = PUBLIC.read_text(encoding="utf-8")
        cls.database = (INTERNAL / "GattDatabase.cpp").read_text(encoding="utf-8")
        cls.server = (INTERNAL / "GattServer.cpp").read_text(encoding="utf-8")
        cls.client = (INTERNAL / "GattClient.cpp").read_text(encoding="utf-8")
        cls.internal = (INTERNAL / "GattInternal.h").read_text(encoding="utf-8")
        cls.profile = PROFILE.read_text(encoding="utf-8")

    def test_public_descriptor_is_bounded_to_four_per_characteristic(self) -> None:
        """! @brief descriptor 객체와 characteristic당 4개 상한을 검사합니다. """

        self.assertIn("class BLEDescriptor final", self.public)
        self.assertIn("maximum_descriptors = 4U", self.public)
        self.assertIn("addDescriptor(BLEDescriptor &descriptor)", self.public)
        self.assertIn("descriptor_count_", self.public)
        self.assertNotIn("std::vector", self.public)

    def test_authorization_is_synchronous_and_result_is_deferred(self) -> None:
        """! @brief Bluetooth 판정과 main-thread 결과 event가 분리됐는지 검사합니다. """

        self.assertIn("using BLEGattAuthorizationCallback = bool (*)", self.public)
        self.assertIn("BLECharacteristicEvent::authorization_allowed", self.server)
        self.assertIn("BLECharacteristicEvent::authorization_denied", self.server)
        self.assertIn("BT_ATT_ERR_AUTHORIZATION", self.server)
        self.assertIn("queueServerEvent", self.server)

    def test_descriptor_attributes_use_exact_owner_and_permissions(self) -> None:
        """! @brief 각 descriptor attribute가 고정 owner·read/write handler를 갖는지 검사합니다. """

        self.assertIn("descriptor_attribute.user_data = descriptor", self.database)
        self.assertIn("? descriptorRead", self.database)
        self.assertIn("? descriptorWrite", self.database)
        self.assertIn("descriptor_attribute_index", self.internal)
        self.assertIn("findDescriptorOwner", self.server)
        self.assertIn("prior_descriptor", self.database)

    def test_read_multiple_copies_up_to_four_handles(self) -> None:
        """! @brief client가 caller pointer를 보존하지 않고 4개 handle을 복사하는지 검사합니다. """

        self.assertIn("readMultiple(BLEConnectionHandle connection", self.public)
        self.assertIn("count < 2U || count > maximum_descriptors", self.client)
        self.assertIn("::memcpy(state->read_handles, handles", self.client)
        self.assertIn("multiple.handles = state->read_handles", self.client)
        self.assertIn("read_multiple_complete", self.client)

    def test_descriptor_discovery_is_per_link_and_generation_checked(self) -> None:
        """! @brief descriptor cache가 link context 안에 있고 stale callback을 거부하는지 검사합니다. """

        self.assertIn("remote_descriptors[maximum_descriptors]", self.internal)
        self.assertIn("descriptor_boundary_ready", self.internal)
        self.assertIn("descriptorBoundaryDiscovered", self.client)
        self.assertIn("continueDescriptorDiscovery", self.client)
        self.assertIn("validClientOperation(*state, connection)", self.client)
        self.assertIn("currentGattConnection(*state, connection)", self.client)
        self.assertIn("descriptor_discovery_complete", self.client)

    def test_notify_indicate_and_profile_bind_exact_w04_contract(self) -> None:
        """! @brief link 지정 전송 overload와 read-multiple Kconfig를 검사합니다. """

        self.assertIn("notify(BLEConnectionHandle connection)", self.public)
        self.assertIn("indicate(BLEConnectionHandle connection)", self.public)
        self.assertIn("internal::referenceConnection(connection_handle)", self.server)
        self.assertIn("notification_data[maximum_characteristics]", self.internal)
        self.assertIn("slot->notification_data[index]", self.server)
        self.assertIn("CONFIG_BT_GATT_READ_MULTIPLE=y", self.profile)

    def test_target_and_runner_bind_exact_w04_protocol(self) -> None:
        """! @brief target 정량값과 strict runner가 같은 W04 protocol을 쓰는지 검사합니다. """

        target = TARGET.read_text(encoding="utf-8")
        runner = RUNNER.read_text(encoding="utf-8")
        for token in (
            'protocol[] = "M29W04|1"',
            "authorization_checks != 402U",
            "authorization_allowed_events != 401U",
            "completed_reads != required_iterations",
            "BLEClient.readMultiple(connection_handle, descriptor_handles, descriptor_count)",
            "phase == Phase::rejecting && driver_error == -EIO",
        ):
            self.assertIn(token, target)
        self.assertIn('PROTOCOL = "M29W04|1"', runner)
        self.assertIn('"m29_desc_01_status": "passed"', runner)
        self.assertIn('additional_paths=(HIL_DIRECTORY / "m29_ble_long.py",)', runner)

    def test_w04_examples_check_asynchronous_results(self) -> None:
        """! @brief 두 예제가 시작 실패와 비동기 결과를 명시적으로 처리하는지 검사합니다. """

        descriptor = (EXAMPLES / "GattDescriptors" / "GattDescriptors.ino").read_text(
            encoding="utf-8"
        )
        authorization = (
            EXAMPLES / "GattAuthorization" / "GattAuthorization.ino"
        ).read_text(encoding="utf-8")
        self.assertIn("BLEClient.readMultiple(peer, descriptorHandles, 4U)", descriptor)
        self.assertIn("BLEGattClientEvent::read_multiple_complete", descriptor)
        self.assertIn("BLEGattClientEvent::operation_failed", descriptor)
        self.assertIn("onAuthorize(authorizeValue)", authorization)
        self.assertIn("BLECharacteristicEvent::authorization_denied", authorization)
        self.assertIn("if (!running)", authorization)


if __name__ == "__main__":
    unittest.main()
