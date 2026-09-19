#!/usr/bin/env python3
"""! @brief CSIP 공개 API·backend·예제 역할 구성을 고정합니다. """

from pathlib import Path
import importlib.util
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
HEADER = ROOT / "libraries/NUCODE_BLE_Audio/src/NUCODE_BLE_Audio.h"
BACKEND = ROOT / "libraries/NUCODE_BLE_Audio/src/NUCODE_BLE_Audio_Csip.cpp"
EXAMPLES = ROOT / "libraries/NUCODE_BLE_Audio/examples"
SPEC = importlib.util.spec_from_file_location(
    "m31_csip_example_audit", ROOT / "tools/ci/m31_example_audit.py"
)
assert SPEC is not None and SPEC.loader is not None
AUDIT = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = AUDIT
SPEC.loader.exec_module(AUDIT)


class CsipContractTests(unittest.TestCase):
    """! @brief W03-06의 positive·negative·복구 계약을 source 수준에서 검사합니다. """

    def test_public_surface_exposes_member_and_coordinator_flow(self) -> None:
        """! @brief set identity·discovery·rank·lock·release API를 고정합니다. """

        text = HEADER.read_text(encoding="utf-8")
        for token in (
            "struct CsipSetKey",
            "struct CsipMemberConfig",
            "struct CsipMemberInfo",
            "class CsipSetMember final",
            "generateRsi",
            "authorizeSirkRead",
            "setSizeAndRank",
            "forceRelease",
            "class CsipSetCoordinator final",
            "matches(const BLEScanResult &result)",
            "discover(const BLEConnectionHandle &connection)",
            "prepareOrderedAccess",
            "orderedMember",
            "Error lock()",
            "Error release()",
        ):
            self.assertIn(token, text)
        self.assertNotIn("struct bt_", text)

    def test_backend_validates_identity_rank_state_and_peer_loss(self) -> None:
        """! @brief 잘못된 key/rank/state와 stale handle을 fail-closed로 처리합니다. """

        text = BACKEND.read_text(encoding="utf-8")
        for token in (
            "bt_csip_set_coordinator_is_set_member",
            "bt_csip_set_coordinator_discover",
            "bt_csip_set_coordinator_ordered_access",
            "bt_csip_set_coordinator_lock",
            "bt_csip_set_coordinator_release",
            "instance->info.rank == 0U",
            "instance->info.set_size != coordinator_context.expected_members",
            "coordinator_context.members[index].information.rank == instance->info.rank",
            "!BLEConnection.connected(snapshot[index - 1U].connection)",
            "!BLEConnection.connected(pending_connection)",
            "release_remaining = release_remaining || coordinator_context.locked",
            "internal::handleForActiveConnection(connection)",
            "BT_CSIP_READ_SIRK_REQ_RSP_REJECT",
            "bt_le_bond_exists(information.id, information.le.dst)",
            "bt_addr_le_eq(information.le.dst, &authorized_identity)",
            "struct CoordinatorOperation",
            "operation.session == coordinator_context.session",
            "invalidateCoordinatorOperationLocked()",
            "invalidateCoordinatorMember(instance",
            "aggregate_locked",
            "member_context.transitioning",
            "bt_csip_set_member_unregister(instance)",
        ):
            self.assertIn(token, text)
        self.assertNotIn("TEST_SAMPLE_DATA", text)

    def test_examples_require_physical_sirk_approval_and_recover_discovery(self) -> None:
        """! @brief 기본 거부·명시 승인·새 RSI·실패 session 재시작 흐름을 고정합니다. """

        member = (EXAMPLES / "CsipSetMember/CsipSetMember.ino").read_text(encoding="utf-8")
        coordinator = (EXAMPLES / "CsipSetCoordinator/CsipSetCoordinator.ino").read_text(
            encoding="utf-8"
        )
        for token in (
            "physically verify the controller, then send a",
            "setMember.authorizeSirkRead(authorizationCandidate)",
            "Bonded controller identity authorized",
            "Set SIRK read authorization failed",
            "startMemberAdvertising()",
            "setMember.generateRsi(rsi)",
            "로컬 상호운용 시험 전용",
            "고유 비밀",
        ):
            self.assertIn(token, member)
        for token in (
            "recoverDiscovery()",
            "coordinator.end()",
            "BLEConnection.disconnect(links[index])",
            "coordinator.begin(setKey, 2U)",
            "BLEScan.start(true)",
            "CsipStage::failed",
        ):
            self.assertIn(token, coordinator)

    def test_examples_pass_public_boundary_audit(self) -> None:
        """! @brief 두 역할 sketch가 공개 NUCODE API와 역할 Kconfig를 유지합니다. """

        library = ROOT / "libraries/NUCODE_BLE_Audio"
        for name in ("CsipSetMember", "CsipSetCoordinator"):
            sketch = EXAMPLES / name / f"{name}.ino"
            with self.subTest(name=name):
                self.assertEqual(
                    AUDIT.inspect_sketch(library, sketch)["status"], "VISIBLE_CODE"
                )

    def test_coordinator_uses_two_central_controller_partition(self) -> None:
        """! @brief coordinator image에서 host와 controller의 두 central slot을 일치시킵니다. """

        config = (EXAMPLES / "CsipSetCoordinator/prj.conf").read_text(encoding="utf-8")
        for token in (
            "CONFIG_BT_MAX_CONN=2",
            "CONFIG_BT_CTLR_SDC_PERIPHERAL_COUNT=0",
            "CONFIG_NUCODE_BLE_CENTRAL_CONNECTION_SLOTS=2",
            "CONFIG_BT_MAX_PAIRED=2",
            "CONFIG_BT_CSIP_SET_COORDINATOR=y",
        ):
            self.assertIn(token, config)


if __name__ == "__main__":
    unittest.main(verbosity=2)
