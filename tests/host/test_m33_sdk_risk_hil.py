#!/usr/bin/env python3
"""! @brief M33 SDK 위험 회귀 runner의 fail-closed 분모를 검사합니다. """

from __future__ import annotations

import copy
from contextlib import contextmanager, nullcontext
import importlib.util
from pathlib import Path
import sys
import tempfile
from unittest import mock
from types import SimpleNamespace
import unittest


ROOT = Path(__file__).resolve().parents[2]
TIMING_PATH = ROOT / "tests/hil/nu54dk/m32_timing_feature_run.py"
TIMING_SPEC = importlib.util.spec_from_file_location(
    "m33_sdk_risk_timing", TIMING_PATH
)
TIMING = importlib.util.module_from_spec(TIMING_SPEC)
TIMING_SPEC.loader.exec_module(TIMING)
CIS_PATH = ROOT / "tests/hil/nu54dk/m33_cis_acl_risk_run.py"
CIS_SPEC = importlib.util.spec_from_file_location("m33_cis_acl_risk", CIS_PATH)
CIS = importlib.util.module_from_spec(CIS_SPEC)
CIS_SPEC.loader.exec_module(CIS)
MESH_PATH = ROOT / "tests/hil/nu54dk/m32_mesh_run.py"
MESH_SPEC = importlib.util.spec_from_file_location("m33_mesh_friend_clear", MESH_PATH)
MESH = importlib.util.module_from_spec(MESH_SPEC)
MESH_SPEC.loader.exec_module(MESH)
MDFU_PATH = ROOT / "tests/hil/nu54dk/m32_mesh_dfu_run.py"
MDFU_SPEC = importlib.util.spec_from_file_location("m33_mcuboot_watchdog", MDFU_PATH)
MDFU = importlib.util.module_from_spec(MDFU_SPEC)
sys.modules[MDFU_SPEC.name] = MDFU
MDFU_SPEC.loader.exec_module(MDFU)
BIS_PATH = ROOT / "tests/hil/nu54dk/m31_iso_bis_run.py"
BIS_SPEC = importlib.util.spec_from_file_location("m33_bis_noise_risk", BIS_PATH)
BIS = importlib.util.module_from_spec(BIS_SPEC)
BIS_SPEC.loader.exec_module(BIS)
CS_PATH = ROOT / "tests/hil/nu54dk/m33_cs_acl_radio_risk_run.py"
CS_SPEC = importlib.util.spec_from_file_location("m33_cs_acl_radio_risk", CS_PATH)
CS = importlib.util.module_from_spec(CS_SPEC)
CS_SPEC.loader.exec_module(CS)
import m33_sdk_risk_common as COMMON
import m33_diagnostics as DIAGNOSTICS


class FakePort:
    """! @brief cleanup 명령과 close를 메모리에서 관찰하는 최소 serial입니다. """

    def __init__(self, lines=(), close_error: bool = False):
        self.lines = [line.encode("ascii") + b"\n" for line in lines]
        self.writes: list[bytes] = []
        self.close_error = close_error

    def write(self, payload: bytes) -> int:
        """! @brief 전송 byte를 저장합니다. """
        self.writes.append(payload)
        return len(payload)

    def flush(self) -> None:
        """! @brief 실제 buffering이 없으므로 성공합니다. """

    def readline(self) -> bytes:
        """! @brief 준비된 protocol line을 순서대로 반환합니다. """
        return self.lines.pop(0) if self.lines else b""

    def close(self) -> None:
        """! @brief 요청된 경우 close 실패를 재현합니다. """
        if self.close_error:
            raise OSError("close failed")


class FakeReadbackTarget:
    """! @brief readback 전후 CPU 상태와 halt/resume 호출을 기록합니다. """

    def __init__(self, state: str, halt_delay_reads: int = 0):
        self.state = state
        self.halt_calls = 0
        self.resume_calls = 0
        self.halt_delay_reads = halt_delay_reads
        self.pending_halt_reads = 0
        self.dhcsr_reads = 0

    def get_state(self):
        """! @brief 현재 CPU 상태를 pyOCD state 모양으로 반환합니다. """
        return SimpleNamespace(name=self.state)

    def halt(self) -> None:
        """! @brief CPU를 halt 상태로 전환합니다. """
        self.halt_calls += 1
        self.pending_halt_reads = self.halt_delay_reads
        if self.pending_halt_reads == 0:
            self.state = "HALTED"

    def read32(self, address: int) -> int:
        """! @brief halt acknowledgement가 늦는 DHCSR를 재현합니다. """
        if address != DIAGNOSTICS.DHCSR:
            raise AssertionError("예상하지 않은 register read")
        self.dhcsr_reads += 1
        if self.pending_halt_reads > 0:
            self.pending_halt_reads -= 1
            if self.pending_halt_reads == 0:
                self.state = "HALTED"
        return (
            DIAGNOSTICS.DHCSR_HALTED
            if self.state == "HALTED"
            else 0
        )

    def resume(self) -> None:
        """! @brief CPU를 running 상태로 전환합니다. """
        self.resume_calls += 1
        self.state = "RUNNING"


class FakeReadbackBackend:
    """! @brief 단일 probe와 target을 제공하는 readback backend입니다. """

    target: FakeReadbackTarget
    uid = "0123456789abcdef"

    def discover(self):
        """! @brief raw UID가 메모리 내부에서만 쓰이는 probe를 반환합니다. """
        return [SimpleNamespace(unique_id=self.uid)], []

    @contextmanager
    def session(self, _probe):
        """! @brief 가짜 target session을 반환합니다. """
        yield SimpleNamespace(target=self.target)


class ReadbackStateRestorationTests(unittest.TestCase):
    """! @brief live readback이 실행 전 CPU 상태를 정확히 복원하는지 검사합니다. """

    def _run(
        self,
        state: str,
        halt_delay_reads: int = 0,
        halt_timeout: float = 1.0,
    ) -> tuple[dict, FakeReadbackTarget]:
        """! @brief 지정 상태에서 한 역할 readback을 실행합니다. """
        target = FakeReadbackTarget(state, halt_delay_reads)
        FakeReadbackBackend.target = target
        probe_hash = COMMON.hashlib.sha256(
            FakeReadbackBackend.uid.encode("ascii")
        ).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "image.hex"
            image.write_text(":00000001FF\n", encoding="ascii")
            readback = root / "readback.json"
            def readback_ranges(_target, _ranges, monitor=None):
                """! @brief readback 중에도 halt monitor가 호출되는지 검사합니다. """
                if monitor is not None:
                    monitor.sample()
                return [{
                    "start": 0,
                    "length": 1,
                    "expected_sha256": "a" * 64,
                    "observed_sha256": "a" * 64,
                    "status": "PASS",
                }]

            fake_diagnostics = SimpleNamespace(
                IdleAuditFailure=DIAGNOSTICS.IdleAuditFailure,
                PyocdPreparationBackend=FakeReadbackBackend,
                halt_and_wait=lambda value: DIAGNOSTICS.halt_and_wait(
                    value, timeout=halt_timeout
                ),
                private_debug_output=lambda: nullcontext(),
                readback_ranges=readback_ranges,
                wait_for_target_state=DIAGNOSTICS.wait_for_target_state,
            )
            with mock.patch.object(COMMON, "_load_pyocd_site_packages"), \
                    mock.patch.object(COMMON, "intel_hex_ranges", return_value=[(0, b"x")]), \
                    mock.patch.dict(sys.modules, {"m33_diagnostics": fake_diagnostics}):
                records, _receipt = COMMON.readback_programmed_images(
                    {"role": FakeReadbackBackend.uid},
                    {"role": probe_hash},
                    {"role": image},
                    {"role": {"readback": readback}},
                )
        return records["role"], target

    def test_running_target_is_resumed_and_recorded_as_restored(self) -> None:
        """! @brief 원래 실행 가능 상태인 target은 readback 뒤 resume합니다. """
        record, target = self._run("RUNNING")
        self.assertEqual((record["pre_state"], record["post_state"]),
                         ("RUNNING", "RUNNING"))
        self.assertTrue(record["resumed"])
        self.assertTrue(record["restored"])
        self.assertEqual((target.halt_calls, target.resume_calls), (1, 1))

        delayed_record, delayed_target = self._run(
            "RUNNING", halt_delay_reads=2
        )
        self.assertEqual(
            (delayed_record["pre_state"], delayed_record["post_state"]),
            ("RUNNING", "RUNNING"),
        )
        self.assertTrue(delayed_record["restored"])
        self.assertEqual(
            (delayed_target.halt_calls, delayed_target.resume_calls),
            (1, 1),
        )
        self.assertGreaterEqual(delayed_target.dhcsr_reads, 4)

        with self.assertRaisesRegex(
            COMMON.ExactProgrammingFailure,
            "readback halt failed: halt_timeout",
        ):
            self._run(
                "RUNNING", halt_delay_reads=1000, halt_timeout=0.0
            )
        timeout_target = FakeReadbackBackend.target
        self.assertEqual(
            (timeout_target.halt_calls, timeout_target.resume_calls),
            (1, 1),
        )
        self.assertEqual(timeout_target.state, "RUNNING")

        sleeping_record, sleeping_target = self._run("SLEEPING")
        self.assertEqual(
            (sleeping_record["pre_state"], sleeping_record["post_state"]),
            ("SLEEPING", "RUNNING"),
        )
        self.assertTrue(sleeping_record["resumed"])
        self.assertTrue(sleeping_record["restored"])
        self.assertEqual(
            (sleeping_target.halt_calls, sleeping_target.resume_calls),
            (1, 1),
        )

    def test_halted_target_remains_halted_without_resume(self) -> None:
        """! @brief runner cleanup이 남긴 HALTED 상태를 증거 수집이 깨지 않습니다. """
        record, target = self._run("HALTED")
        self.assertEqual((record["pre_state"], record["post_state"]),
                         ("HALTED", "HALTED"))
        self.assertFalse(record["resumed"])
        self.assertTrue(record["restored"])
        self.assertEqual((target.halt_calls, target.resume_calls), (1, 0))


def timing_results() -> dict[str, dict[str, str]]:
    """! @brief 실제 firmware RESULT와 같은 정상 timing 분모를 만듭니다. """
    common = {
        "subrate": "20",
        "subrate_ack": "20",
        "subrate_increase_ack": "10",
        "boundary": "20",
        "rate": "20",
        "feature": "20",
        "sca": "10",
        "callback_context": "pass",
        "packet_gap_ms": "20",
        "procedure_gap_ms": "2000",
        "min_interval_us": "750",
    }
    return {
        "central": {
            **common,
            "tx": "2000",
            "rx": "0",
            "frame": "20",
            "channel": "20",
        },
        "peripheral": {
            **common,
            "tx": "0",
            "rx": "2000",
            "frame": "2",
            "channel": "0",
        },
    }


class SubrateAckRiskTests(unittest.TestCase):
    """! @brief DRGN-29270의 ACK·latency·payload 관측 경계를 검사합니다. """

    def test_exact_ack_and_boundary_denominators_are_required(self) -> None:
        """! @brief 양 역할 20 ACK·10 증가·20 payload만 후보 결과로 수락합니다. """
        self.assertEqual(
            TIMING.validate_timing_results(timing_results()),
            {
                "issue": "DRGN-29270",
                "acknowledged_transitions": 40,
                "increased_latency_timeout_acknowledgements": 20,
                "boundary_payloads": 40,
            },
        )
        for role in TIMING.ROLES:
            for field, value in (
                ("subrate_ack", "19"),
                ("subrate_increase_ack", "9"),
                ("boundary", "19"),
            ):
                with self.subTest(role=role, field=field):
                    changed = copy.deepcopy(timing_results())
                    changed[role][field] = value
                    with self.assertRaises(TIMING.TimingFeatureExecutionFailure):
                        TIMING.validate_timing_results(changed)

    def test_firmware_exercises_increased_latency_timeout_before_payload(self) -> None:
        """! @brief 시험 image가 고정 증가값과 ACK 경계 payload를 실제 요청하는지 검사합니다. """
        source = (
            ROOT / "tests/zephyr/m32_ble_timing_hil/src/main.cpp"
        ).read_text(encoding="utf-8")
        self.assertIn("parameters.maximum_peripheral_latency = increased ? 3U : 0U", source)
        self.assertIn("parameters.supervision_timeout_10ms = increased ? 800U : 400U", source)
        self.assertIn("BLEConnection.requestSubrate(connection_handle, parameters)", source)
        self.assertIn("sendBoundaryPacket()", source)
        self.assertIn("validSubrateAck(subrate_changes, result)", source)
        self.assertIn('fail("subrate_ack_order")', source)

    def test_subrate_ack_accepts_lower_legal_latency_and_rejects_excess(self) -> None:
        """! @brief max latency 요청을 exact 결과값으로 오해하지 않게 경계를 고정합니다. """
        self.assertTrue(TIMING.valid_subrate_ack(1, 0, 4, 0, 2, 800))
        self.assertTrue(TIMING.valid_subrate_ack(1, 0, 4, 0, 3, 800))
        self.assertTrue(TIMING.valid_subrate_ack(1, 0, 4, 0, 0, 800))
        self.assertFalse(TIMING.valid_subrate_ack(1, 0, 4, 0, 4, 800))
        self.assertFalse(TIMING.valid_subrate_ack(1, 0, 4, 0, -1, 800))
        self.assertFalse(TIMING.valid_subrate_ack(1, 0, 4, 0, 2, 400))
        self.assertTrue(TIMING.valid_subrate_ack(0, 0, 2, 0, 0, 400))
        source = (
            ROOT / "tests/zephyr/m32_ble_timing_hil/src/main.cpp"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "result.peripheral_latency <= expected.maximum_peripheral_latency",
            source,
        )
        self.assertNotIn(
            "result.peripheral_latency == expected.maximum_peripheral_latency",
            source,
        )


class CisAclRiskTests(unittest.TestCase):
    """! @brief DRGN-29446의 active CIS·NSE·부하·ACL 종료 경계를 검사합니다. """

    def records(self, identity, nonce):
        """! @brief 양 역할의 정상 risk record 열을 만듭니다. """
        output = {}
        for role in CIS.ROLES:
            output[role] = [
                {"event": "BEGIN", "nonce": nonce, "role": role},
                {"event": "IDENTITY", "nonce": nonce, **vars(identity)},
                {"event": "ACL_CONNECTED", "nonce": nonce},
                {"event": "ISO_CONNECTED", "nonce": nonce},
                {"event": "RISK_ACTIVE", "nonce": nonce, "role": role,
                 "nse": "3", "load_ticks": "12", "payloads": "25"},
                {"event": "ISO_DISCONNECTED", "nonce": nonce, "reason": "19"},
                {"event": "ACL_DISCONNECTED", "nonce": nonce, "reason": "19"},
                {"event": "RISK_STOPPED", "nonce": nonce, "role": role,
                 "tx": "30" if role == "central" else "0",
                 "rx": "0" if role == "central" else "29",
                 "nse": "3", "load_ticks": "13", "acl_first": "1"},
            ]
        return output

    def test_active_cis_acl_first_teardown_is_fail_closed(self) -> None:
        """! @brief NSE>1·부하·미완료 payload·ACL 우선·양 역할 종료를 모두 요구합니다. """
        identity = CIS.ExpectedIdentity("a" * 40, "b" * 40, "c" * 40, "d" * 40)
        nonce = "0123456789abcdef" * 2
        records = self.records(identity, nonce)
        metrics = CIS.validate_cycle(records, nonce, identity)
        self.assertEqual(metrics["central"]["nse"], 3)
        self.assertEqual(metrics["peripheral"]["payloads_before_abort"], 25)
        for role, index, field, value in (
            ("central", 4, "nse", "1"),
            ("central", 4, "load_ticks", "9"),
            ("peripheral", 4, "payloads", "100"),
            ("peripheral", 7, "acl_first", "0"),
        ):
            with self.subTest(role=role, field=field):
                changed = copy.deepcopy(records)
                changed[role][index][field] = value
                with self.assertRaises(CIS.CisAclRiskFailure):
                    CIS.validate_cycle(changed, nonce, identity)

    def test_firmware_has_distinct_risk_commands_and_cpu_load(self) -> None:
        """! @brief 정상 20-cycle protocol과 분리된 위험 경로만 ACL을 먼저 종료합니다. """
        source = (
            ROOT / "tests/zephyr/m31_iso_cis_hil/src/main.cpp"
        ).read_text(encoding="utf-8")
        self.assertIn('"M31ISO|1|START_RISK|nonce="', source)
        self.assertIn('"M31ISO|1|ABORT_ACL|nonce="', source)
        self.assertIn("risk_information.max_subevent <= 1U", source)
        self.assertIn("k_busy_wait(2000U)", source)
        self.assertIn("if (!acl_first && central_role", source)
        self.assertIn("peer_acl_first_teardown", source)
        for state in (
            "started",
            "finished",
            "stopping",
            "risk_mode",
            "risk_ready_printed",
            "acl_first_teardown",
            "negotiated_nse",
            "stop_start_ms",
        ):
            self.assertIn(f"atomic_t {state} = ATOMIC_INIT(0);", source)
        self.assertIn("atomic_cas(&finished, 0, 1)", source)
        self.assertIn("atomic_get(&risk_ready_printed)", source)
        runner = (
            ROOT / "tests/hil/nu54dk/m33_cis_acl_risk_run.py"
        ).read_text(encoding="utf-8")
        self.assertIn('ports["central"].write(abort)', runner)
        self.assertNotIn('ports["peripheral"].write(abort)', runner)


class MeshFriendClearRiskTests(unittest.TestCase):
    """! @brief TTL=0 Friend Clear Confirm의 실제 callback·시간 경계를 검사합니다. """

    def test_both_mesh_nodes_require_confirm_before_first_retry(self) -> None:
        """! @brief node만 1초 이내 PASS를 요구하고 provisioner는 비적용으로 분리합니다. """
        for role in ("node_a", "node_b"):
            self.assertEqual(
                MESH._validate_friend_clear(
                    role,
                    {"cleanup": "pass", "friend_clear": "pass",
                     "friend_clear_peer_ack": "pass", "friend_clear_ms": "999"},
                ),
                {"status": "pass", "latency_ms": 999},
            )
            for field, value in (("friend_clear", "not_run"),
                                 ("friend_clear_peer_ack", "not_run"),
                                 ("friend_clear_ms", "1001")):
                with self.subTest(role=role, field=field):
                    record = {"cleanup": "pass", "friend_clear": "pass",
                              "friend_clear_peer_ack": "pass",
                              "friend_clear_ms": "100"}
                    record[field] = value
                    with self.assertRaises(MESH.MeshExecutionFailure):
                        MESH._validate_friend_clear(role, record)
        self.assertEqual(
            MESH._validate_friend_clear(
                "provisioner",
                {"cleanup": "pass", "friend_clear": "not_applicable",
                 "friend_clear_ms": "0"},
            )["status"],
            "not_applicable",
        )

    def test_firmware_waits_for_lpn_and_friend_termination_callbacks(self) -> None:
        """! @brief LPN Confirm과 Friend 수신을 양쪽 callback으로 관측한 뒤 suspend합니다. """
        source = (
            ROOT / "tests/zephyr/m32_mesh_hil/src/main.cpp"
        ).read_text(encoding="utf-8")
        self.assertIn("BT_MESH_FRIEND_CB_DEFINE", source)
        self.assertIn("BT_MESH_LPN_CB_DEFINE", source)
        self.assertIn("friend_clear_confirm_timeout_ms = 1000", source)
        self.assertIn("atomic_get(&friendship_terminated) == 0", source)
        self.assertIn('fail("friend_clear_confirm_timeout")', source)
        self.assertIn("|FRIEND_CLEAR_PEER|role=node_b", source)
        self.assertIn("peer_ack_prefix", source)
        self.assertIn("atomic_get(&friend_clear_peer_acknowledged) == 0", source)
        self.assertLess(
            source.index("atomic_get(&friend_clear_peer_acknowledged) == 0"),
            source.index("NUCODEMesh.setFeature(Feature::friend_node, false)"),
        )
        self.assertIn("bt_mesh_suspend()", source)
        for state in (
            "stop_requested",
            "friendship_established",
            "friendship_terminated",
            "feature_disable_requested",
            "friend_clear_latency_ms",
            "friend_clear_peer_acknowledged",
        ):
            self.assertIn(f"atomic_t {state} = ATOMIC_INIT(0);", source)
        runner = (
            ROOT / "tests/hil/nu54dk/m32_mesh_run.py"
        ).read_text(encoding="utf-8")
        self.assertIn(
            'for role in ("node_a", "node_b", "provisioner"):',
            runner,
        )


class CleanupFailClosedTests(unittest.TestCase):
    """! @brief 예외 뒤 STOP과 partial close가 증거 없이 성공하지 않게 합니다. """

    def test_cis_cleanup_requires_disconnect_and_stopped_on_both_roles(self) -> None:
        """! @brief ABORT 뒤 두 역할의 해제·정지 record를 모두 요구합니다. """
        nonce = "a" * 32
        ports = {
            role: FakePort((
                f"M31ISO|1|ACL_DISCONNECTED|nonce={nonce}|reason=19",
                f"M31ISO|1|RISK_STOPPED|nonce={nonce}|role={role}",
            ))
            for role in CIS.ROLES
        }
        result = CIS.cleanup_active_session(ports, nonce, [], timeout_seconds=0.1)
        self.assertEqual(result["status"], "PASS")
        self.assertTrue(result["abort_acl_sent"])

    def test_timing_mesh_bis_cleanup_records_exact_stop(self) -> None:
        """! @brief 각 protocol STOP이 role·nonce·revision에 결합되는지 검사합니다. """
        nonce = "b" * 32
        core = "c" * 40
        timing_ports = {
            role: FakePort((
                f"M32TIM|1|STOPPED|role={role}|nonce={nonce}|core={core}",
            ))
            for role in TIMING.ROLES
        }
        self.assertEqual(
            TIMING.cleanup_ports(timing_ports, nonce, core, [], 0.1)["status"],
            "PASS",
        )
        mesh_ports = {
            "provisioner": FakePort((
                f"M32MESH|1|STOPPED|role=provisioner|nonce={nonce}|core={core}"
                "|cleanup=pass|friend_clear=not_applicable|friend_clear_ms=0",
            )),
            "node_a": FakePort((
                f"M32MESH|1|FRIEND_CLEAR_LOCAL|role=node_a|friend_clear_ms=1"
                f"|nonce={nonce}|core={core}",
                f"M32MESH|1|STOPPED|role=node_a|nonce={nonce}|core={core}"
                "|cleanup=pass|friend_clear=pass|friend_clear_peer_ack=pass"
                "|friend_clear_ms=1",
            )),
            "node_b": FakePort((
                f"M32MESH|1|FRIEND_CLEAR_PEER|role=node_b|friend_clear_ms=1"
                f"|nonce={nonce}|core={core}",
                f"M32MESH|1|STOPPED|role=node_b|nonce={nonce}|core={core}"
                "|cleanup=pass|friend_clear=pass|friend_clear_peer_ack=pass"
                "|friend_clear_ms=1",
            )),
        }
        mesh_cleanup = MESH.cleanup_ports(mesh_ports, nonce, core, [], 0.1)
        self.assertEqual(mesh_cleanup["status"], "PASS")
        self.assertTrue(mesh_cleanup["friend_peer_callback"])
        self.assertTrue(mesh_cleanup["peer_ack_sent"])
        bis_ports = {
            role: FakePort((f"M31BIS|1|STOPPED|nonce={nonce}|role={role}",))
            for role in BIS.ROLES
        }
        self.assertEqual(
            BIS.cleanup_active_session(bis_ports, nonce, [], 0.1)["status"],
            "PASS",
        )
        dfu_ports = {
            role: FakePort((
                f"M32MDFU|1|STOPPED|role={role}|nonce={nonce}|core={core}"
                "|cleanup=pass",
            ))
            for role in MDFU.ROLES
        }
        self.assertEqual(
            MDFU.cleanup_ports(
                dfu_ports,
                nonce,
                core,
                [],
                required=True,
                timeout_seconds=0.1,
            )["status"],
            "PASS",
        )

    def test_cs_cleanup_and_partial_close_fail_closed(self) -> None:
        """! @brief CS s/d/s와 close 오류가 구조화된 FAIL로 남는지 검사합니다. """
        streams = {role: FakePort() for role in CS.ROLES}
        lines = {role: [] for role in CS.ROLES}

        def populate(_streams, _pending, observed):
            observed["initiator"].extend((
                "P2_STOP role=cs-initiator",
                "CS initiator disconnected",
            ))
            observed["reflector"].extend((
                "P2_STOP role=cs-reflector",
                "CS reflector disconnected",
            ))

        with mock.patch.object(CS, "read_lines", side_effect=populate):
            cleanup = CS.cleanup_active_session(
                streams,
                {role: bytearray() for role in CS.ROLES},
                lines,
                0.1,
            )
        self.assertEqual(cleanup["status"], "PASS")
        close = CS.close_serial_handles(
            {"initiator": FakePort(close_error=True)},
            {"reflector": FakePort()},
        )
        self.assertTrue(close["initiator_app"].startswith("FAIL:"))
        self.assertEqual(close["reflector_aux"], "PASS")

    def test_string_or_arbitrary_hash_cannot_replace_live_readback_receipt(self) -> None:
        """! @brief 직렬화 문자열을 same-process program receipt로 수락하지 않습니다. """
        with self.assertRaises(COMMON.ExactProgrammingFailure):
            COMMON.validate_programming_receipt(
                "verified",
                ("role",),
                {"role": {"status": "PASS", "ranges": []}},
            )


class McubootWatchdogRiskTests(unittest.TestCase):
    """! @brief MCUboot feed 설정과 실제 활성 watchdog 증거를 혼동하지 않게 합니다. """

    def test_disabled_application_watchdog_is_not_applicable_not_pass(self) -> None:
        """! @brief boot feed가 켜져도 app WDT가 꺼져 있으면 PASS로 승격하지 않습니다. """
        result = MDFU.classify_mcuboot_watchdog(
            "# CONFIG_WATCHDOG is not set\n",
            "CONFIG_BOOT_WATCHDOG_FEED=y\n",
        )
        self.assertEqual(result["status"], "NOT_APPLICABLE")
        self.assertTrue(result["boot_feed_configured"])
        self.assertFalse(result["active_watchdog_proven"])

    def test_active_watchdog_requires_runtime_erase_swap_hash_attestation(self) -> None:
        """! @brief driver 활성만으로 성공하지 않고 세 MCUboot 구간과 reset 0을 요구합니다. """
        application = "CONFIG_WATCHDOG=y\nCONFIG_WDT_NRFX=y\n"
        boot = "CONFIG_BOOT_WATCHDOG_FEED_NRFX_WDT=y\n"
        self.assertEqual(
            MDFU.classify_mcuboot_watchdog(application, boot)["status"],
            "NOT_RUN",
        )
        attestation = {
            "watchdog_active": True,
            "erase_observed": True,
            "swap_observed": True,
            "hash_observed": True,
            "unexpected_watchdog_resets": 0,
            "timeout_ms": 1500,
        }
        self.assertEqual(
            MDFU.classify_mcuboot_watchdog(application, boot, attestation)["status"],
            "PASS",
        )
        for key in ("erase_observed", "swap_observed", "hash_observed"):
            changed = dict(attestation)
            changed[key] = False
            with self.subTest(key=key):
                with self.assertRaises(MDFU.MeshDfuFailure):
                    MDFU.classify_mcuboot_watchdog(application, boot, changed)
        with self.assertRaisesRegex(MDFU.MeshDfuFailure, "no MCUboot feed"):
            MDFU.classify_mcuboot_watchdog(application, "", attestation)


class BisNoiseRiskTests(unittest.TestCase):
    """! @brief bounded BIS baseline을 noisy-RF 실기로 잘못 승격하지 않게 합니다. """

    def test_bounded_loss_pass_keeps_controlled_noise_not_run(self) -> None:
        """! @brief 20회·cycle당 최대 1 loss도 noisy-RF PASS가 아님을 고정합니다. """
        result = BIS.classify_bis_noise_risk(
            SimpleNamespace(
                cycles=20,
                total_sent=2000,
                total_received=1980,
                minimum_received=99,
            )
        )
        self.assertEqual(result["bounded_baseline"], "PASS")
        self.assertEqual(result["controlled_noisy_rf"], "NOT_RUN")
        self.assertEqual(result["overall_status"], "NOT_RUN")
        self.assertFalse(result["not_run_is_pass"])
        for field, value in (("cycles", 19), ("total_received", 1979),
                             ("minimum_received", 98)):
            measurement = {
                "cycles": 20,
                "total_sent": 2000,
                "total_received": 1980,
                "minimum_received": 99,
            }
            measurement[field] = value
            with self.subTest(field=field):
                self.assertEqual(
                    BIS.classify_bis_noise_risk(SimpleNamespace(**measurement)),
                    {
                        "issue": "DRGN-29320",
                        "bounded_baseline": "FAIL",
                        "baseline_cycles": measurement["cycles"],
                        "baseline_sent": measurement["total_sent"],
                        "baseline_received": measurement["total_received"],
                        "allowed_loss_per_cycle": 1,
                        "controlled_noisy_rf": "NOT_RUN",
                        "overall_status": "FAIL",
                        "not_run_is_pass": False,
                    },
                )

    def test_aggregate_requires_baseline_and_both_typed_negative_phases(self) -> None:
        """! @brief 20+2+2 실제 raw 범위가 모두 있을 때만 dispatch 후보가 됩니다. """

        transcript = [
            "source: M31BIS|1|READY|role=source",
            "receiver: M31BIS|1|READY|role=receiver",
        ]
        records = []
        offset = 0
        for phase, count in (
            ("baseline", 20),
            ("wrong_broadcast_code", 2),
            ("sync_loss", 2),
        ):
            cycles = []
            for cycle in range(1, count + 1):
                nonce = f"{offset + cycle:032x}"
                start = len(transcript) + 1
                transcript.extend(
                    (
                        f"source: M31BIS|1|BEGIN|nonce={nonce}|role=source",
                        f"receiver: M31BIS|1|BEGIN|nonce={nonce}|role=receiver",
                    )
                )
                if phase == "wrong_broadcast_code" and cycle == 1:
                    transcript.append(
                        f"receiver: M31BIS|1|BAD_CODE_REJECTED|nonce={nonce}"
                    )
                if phase == "sync_loss" and cycle == 1:
                    transcript.append(f"receiver: M31BIS|1|SYNC_LOST|nonce={nonce}")
                transcript.extend(
                    (
                        f"source: M31BIS|1|STOPPED|nonce={nonce}|role=source",
                        f"receiver: M31BIS|1|STOPPED|nonce={nonce}|role=receiver",
                    )
                )
                end = len(transcript)
                raw = ("\n".join(transcript[start - 1:end]) + "\n").encode("ascii")
                cycles.append(
                    {
                        "cycle": cycle,
                        "nonce": nonce,
                        "status": "PASS",
                        "transcript_line_start": start,
                        "transcript_line_end": end,
                        "transcript_sha256": BIS.hashlib.sha256(raw).hexdigest(),
                    }
                )
            measurement = (
                {
                    "cycles": 20,
                    "total_sent": 2000,
                    "total_received": 2000,
                    "minimum_received": 100,
                    "empty_slots": 0,
                }
                if phase == "baseline"
                else {
                    "negative_class": phase,
                    "cycles": 2,
                    "rejected_payloads": 0,
                    "recovery_sent": 100,
                    "recovery_received": 100,
                    "recovery_empty_slots": 0,
                }
            )
            phase_raw = (
                "\n".join(
                    transcript[:2]
                    + transcript[
                        cycles[0]["transcript_line_start"] - 1:
                        cycles[-1]["transcript_line_end"]
                    ]
                )
                + "\n"
            ).encode("ascii")
            records.append(
                {
                    "phase": phase,
                    "status": "PASS",
                    "cycles": count,
                    "nonces": [row["nonce"] for row in cycles],
                    "transcript_sha256": BIS.hashlib.sha256(phase_raw).hexdigest(),
                    "measurement": measurement,
                    "cycle_records": cycles,
                }
            )
            offset += count
        BIS.validate_aggregate_phase_records(records, transcript)
        records[1]["cycles"] = 1
        with self.assertRaisesRegex(BIS.BisExecutionFailure, "denominator"):
            BIS.validate_aggregate_phase_records(records, transcript)
        source = BIS_PATH.read_text(encoding="utf-8")
        self.assertIn(
            '(("baseline", 20), ("wrong_broadcast_code", 2), ("sync_loss", 2))',
            source,
        )
        self.assertIn('dispatch_attestation(\n                    "m31_iso_bis"', source)


class CsAclRadioRiskTests(unittest.TestCase):
    """! @brief DRGN-29669의 active CS·scan·ACL 종료·복구 경계를 검사합니다. """

    def cycle_lines(self, cycle: int = 1) -> dict[str, list[str]]:
        """! @brief 한 회의 정상 target transcript 구간을 만듭니다. """

        return {
            "initiator": [
                f"P2_CS_RISK_ACTIVE cycle={cycle} radio=scan acl=connected",
                f"P2_CS_RISK_ABORT cycle={cycle} radio=scan acl=disconnect-requested",
                f"P2_CS_RISK_DISCONNECTED cycle={cycle} radio_scan=1",
                "CS initiator disconnected",
                "CS initiator connected; securing",
                "CS procedures requested",
            ],
            "reflector": [
                "CS reflector disconnected",
                "CS reflector connected",
                "CS reflector secure L2",
                "CS reflector config ready",
                "CS procedures enabled",
            ],
        }

    def test_active_cs_scan_acl_teardown_requires_exact_recovery(self) -> None:
        """! @brief scan 활성 callback과 양 역할 해제·재활성을 모두 요구합니다. """

        result = CS.validate_cycle(self.cycle_lines(), 1)
        self.assertTrue(result["radio_active_at_disconnect_callback"])
        self.assertEqual(result["automatic_recovery"], "cs_active")
        for role, index, value in (
            ("initiator", 2, "P2_CS_RISK_DISCONNECTED cycle=1 radio_scan=0"),
            ("initiator", 3, "CS initiator connected; securing"),
            ("reflector", 4, "CS procedures disabled"),
        ):
            with self.subTest(role=role, index=index):
                lines = self.cycle_lines()
                lines[role][index] = value
                with self.assertRaises(CS.CsAclRadioRiskFailure):
                    CS.validate_cycle(lines, 1)

    def test_target_holds_scan_overlap_before_active_acl_disconnect(self) -> None:
        """! @brief 시험 image가 scan을 100 ms 이상 겹치고 callback에서 확인하는지 검사합니다. """

        source = (
            ROOT / "tests/arduino-cli/p2_cs_initiator/p2_cs_initiator.ino"
        ).read_text(encoding="utf-8")
        self.assertIn("riskRadioOverlapMs = 100UL", source)
        self.assertIn("if (riskScanActive)", source)
        self.assertIn("!BLEScan.running() && !BLEScan.start(true)", source)
        self.assertIn("BLEConnection.disconnect(peer)", source)
        self.assertIn('Serial.println(BLEScan.running() ? 1 : 0)', source)
        self.assertIn('"P2_CS_RISK_ACTIVE cycle="', source)
        self.assertIn('"P2_CS_RISK_ABORT cycle="', source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
