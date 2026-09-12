#!/usr/bin/env python3
"""! @brief M28-W02 고정 2-slot·generation handle의 source 계약을 검증합니다. """

from pathlib import Path
import unittest


REPOSITORY = Path(__file__).resolve().parents[2]
HEADER = REPOSITORY / "libraries" / "NUCODE_BLE" / "src" / "NUCODE_BLE_GAP.h"
INTERNAL = (
    REPOSITORY
    / "libraries"
    / "NUCODE_BLE"
    / "src"
    / "internal"
    / "gap"
    / "GapInternal.h"
)
CONNECTION = INTERNAL.parent / "GapConnection.cpp"
GATT_SERVER = INTERNAL.parents[1] / "gatt" / "GattServer.cpp"
PROFILE = REPOSITORY / "libraries" / "NUCODE_BLE" / "zephyr" / "ble-nus.conf"
TARGET = REPOSITORY / "tests" / "zephyr" / "m28_ble_link_contract"
EXAMPLE = (
    REPOSITORY
    / "libraries"
    / "NUCODE_BLE"
    / "examples"
    / "MixedRoleLinks"
    / "MixedRoleLinks.ino"
)
RUNTIME_TEST = REPOSITORY / "tests" / "host" / "r12_ble_gap_main.cpp"
GATT_RUNTIME_TEST = REPOSITORY / "tests" / "host" / "r12_ble_gatt_main.cpp"


class M28BleLinkTests(unittest.TestCase):
    """! @brief W02 public/internal/target/example 연결을 fail-closed로 고정합니다. """

    def test_public_surface_preserves_legacy_and_adds_opaque_handle(self) -> None:
        """! @brief 기존 singleton과 상세 link API가 함께 선언됐는지 확인합니다. """

        text = HEADER.read_text(encoding="utf-8")
        for token in (
            "class BLEConnectionHandle final",
            "struct BLEEventInfo",
            "enum class BLELinkRole",
            "void onEvent(BLEEventCallback callback",
            "void onEventInfo(BLEEventInfoCallback callback",
            "bool connect(const BLEAddress &address) noexcept",
            "bool connect(const BLEAddress &address,",
            "bool disconnect(BLEConnectionHandle connection) noexcept",
            "std::size_t count() const noexcept",
            "connection_recycled",
            "return 2U;",
            "extern nucode::ble::Device BLEDevice;",
            "extern nucode::ble::Connection BLEConnection;",
        ):
            self.assertIn(token, text)
        self.assertNotIn("struct bt_conn", text)

    def test_internal_state_uses_two_role_slots_and_generation(self) -> None:
        """! @brief 단일 active/pending pointer 회귀와 slot 공유를 거부합니다. """

        header = INTERNAL.read_text(encoding="utf-8")
        source = CONNECTION.read_text(encoding="utf-8")
        for token in (
            "maximum_connection_slots = 2U",
            "central_connection_slot = 0U",
            "peripheral_connection_slot = 1U",
            "ConnectionSlot connection_slots[maximum_connection_slots]",
            "next_connection_generation",
            "MtuExchangeContext",
        ):
            self.assertIn(token, header)
        self.assertNotIn("struct bt_conn *active_connection", header)
        self.assertNotIn("struct bt_conn *pending_connection", header)
        self.assertIn("matchesSlotLocked", source)
        self.assertIn("activeConnectionHandle", source)
        self.assertIn("role == BLELinkRole::central", source)
        self.assertIn("role == BLELinkRole::peripheral", source)

    def test_gatt_server_routes_to_the_subscribed_incoming_link(self) -> None:
        """! @brief mixed role에서 server I/O가 central client slot로 새지 않게 고정합니다. """

        runtime = GATT_RUNTIME_TEST.read_text(encoding="utf-8")
        server = GATT_SERVER.read_text(encoding="utf-8")
        self.assertIn('"mixed_server_route"', runtime)
        self.assertIn("internal::activeConnection(connection)", server)
        self.assertIn("referenceSubscribedConnection", server)
        self.assertIn("BLELinkRole::peripheral", server)

    def test_profile_and_target_fix_the_controller_partition(self) -> None:
        """! @brief production profile과 target image의 2=1+1 구성을 대조합니다. """

        profile = PROFILE.read_text(encoding="utf-8")
        target_config = (TARGET / "prj.conf").read_text(encoding="utf-8")
        for text in (profile, target_config):
            self.assertIn("CONFIG_BT_MAX_CONN=2", text)
            self.assertIn("CONFIG_BT_CREATE_CONN_TIMEOUT=10", text)
            self.assertIn("CONFIG_BT_CTLR_SDC_PERIPHERAL_COUNT=1", text)
        testcase = (TARGET / "testcase.yaml").read_text(encoding="utf-8")
        self.assertIn("nucode.m28.ble_link_contract", testcase)

    def test_runtime_contract_covers_two_links_and_stale_generation(self) -> None:
        """! @brief 실제 production source를 쓰는 Host scenario가 W02 종료 조건을 덮습니다. """

        runtime = RUNTIME_TEST.read_text(encoding="utf-8")
        for scenario in (
            "multi_link",
            "generation",
            "end_two_links",
            "role_callback_guard",
            "recycled",
        ):
            self.assertIn(f'"{scenario}"', runtime)
        self.assertIn("BLEConnection.count() == 2U", runtime)
        self.assertIn("second != first", runtime)
        self.assertIn("first_request->func", runtime)
        self.assertIn("BT_CONN_ROLE_CENTRAL", CONNECTION.read_text(encoding="utf-8"))

    def test_mixed_role_example_uses_detailed_handles(self) -> None:
        """! @brief 예제가 singleton callback 순서가 아닌 handle·role로 link를 구분합니다. """

        text = EXAMPLE.read_text(encoding="utf-8")
        for token in (
            "BLEConnectionHandle centralLink",
            "BLEConnectionHandle peripheralLink",
            "BLEDevice.onEventInfo(onBleEvent)",
            "BLELinkRole::central",
            "BLELinkRole::peripheral",
            "BLEConnection.connect(centralPeerAddress, centralLink)",
        ):
            self.assertIn(token, text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
