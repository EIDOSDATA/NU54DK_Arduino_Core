"""! @brief M30 두 링크 보안 상태·pairing 응답 격리 계약을 검증합니다. """
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
PUBLIC_HEADER = ROOT / "libraries/NUCODE_BLE_Security/src/NUCODE_BLE_Security.h"
INTERNAL_HEADER = (
    ROOT / "libraries/NUCODE_BLE_Security/src/internal/security/SecurityInternal.h"
)
SECURITY_SOURCE = ROOT / "libraries/NUCODE_BLE_Security/src/NUCODE_BLE_Security.cpp"
PAIRING_SOURCE = (
    ROOT / "libraries/NUCODE_BLE_Security/src/internal/security/SecurityPairing.cpp"
)
GAP_SOURCE = ROOT / "libraries/NUCODE_BLE/src/internal/gap/GapConnection.cpp"
PRODUCTION_RUNNER = ROOT / "tests/host/test_r12_ble_security.py"


class M30BleSecurityTests(unittest.TestCase):
    """! @brief W02의 generation별 보안 소유권을 정적·실행 회귀와 연결합니다. """

    def test_public_api_routes_events_and_responses_by_generation(self) -> None:
        """! @brief Sketch가 두 pairing 요청을 정확한 연결로 응답할 수 있어야 합니다. """

        header = PUBLIC_HEADER.read_text(encoding="utf-8")
        self.assertIn("BLEConnectionHandle connection = {};", header)
        for signature in (
            "requestSecurity(BLEConnectionHandle connection)",
            "acceptPairing(BLEConnectionHandle connection, bool accept)",
            "enterPasskey(BLEConnectionHandle connection,",
            "confirmPasskey(BLEConnectionHandle connection, bool accept)",
            "cancelPairing(BLEConnectionHandle connection)",
            "paired(BLEConnectionHandle connection)",
            "bonded(BLEConnectionHandle connection)",
            "bondState(BLEConnectionHandle connection)",
            "currentLevel(BLEConnectionHandle connection)",
        ):
            self.assertIn(signature, header, signature)

    def test_security_and_pairing_use_two_fixed_slots(self) -> None:
        """! @brief heap 없이 link 상태와 사용자 응답 대기를 각각 두 개 보존합니다. """

        internal = INTERNAL_HEADER.read_text(encoding="utf-8")
        pairing = PAIRING_SOURCE.read_text(encoding="utf-8")
        self.assertIn("maximum_security_links = 2U", internal)
        self.assertIn("SecurityLinkState links[maximum_security_links]", internal)
        self.assertIn("PendingState pending_states[maximum_security_links]", internal)
        self.assertIn("pending.handle == handle", pairing)
        self.assertNotIn("new ", pairing)
        self.assertNotIn("malloc(", pairing)

    def test_gap_passes_handle_before_connection_slot_is_recycled(self) -> None:
        """! @brief disconnect 뒤 역추적 없이 기존 generation을 security에 전달합니다. """

        source = GAP_SOURCE.read_text(encoding="utf-8")
        self.assertIn("securityConnected(connection, handle)", source)
        self.assertIn("securityDisconnected(connection, handle)", source)
        self.assertIn("securityChanged(connection, handle, level, error)", source)
        disconnected = source.index("securityDisconnected(connection, handle)")
        unref = source.index("bt_conn_unref(connection)", disconnected)
        self.assertLess(disconnected, unref)

    def test_stale_handle_and_cross_link_isolation_are_executed(self) -> None:
        """! @brief production-linked Host runner가 두 pending과 stale handle을 실행합니다. """

        runner = PRODUCTION_RUNNER.read_text(encoding="utf-8")
        source = SECURITY_SOURCE.read_text(encoding="utf-8")
        self.assertIn("dual_pending_isolation", runner)
        self.assertIn("dual_timeout_isolation", runner)
        self.assertIn("sparse_pending_duplicate", runner)
        self.assertIn("link.handle == handle", source)
        self.assertIn("isActiveConnection(handle, connection)", source)


if __name__ == "__main__":
    unittest.main()
