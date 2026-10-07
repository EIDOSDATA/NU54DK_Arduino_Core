#!/usr/bin/env python3
"""! @brief 실제 probe 없이 prepare-pair의 권한·mapping·range readback·격리를 검사합니다. """
from argparse import Namespace
from contextlib import contextmanager, ExitStack, redirect_stdout
import copy
import hashlib
import importlib.util
import io
import json
import os
import struct
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("m33_diagnostics_prepare_tested", ROOT / "tools/bluetooth/m33_diagnostics.py")
DIAG = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DIAG)
MDK_EVIDENCE = DIAG.mdk_evidence
UIDS = [f"{index:032x}" for index in (1, 2, 3)]
HASHES = [DIAG.probe_hash(uid) for uid in UIDS]
IDENTITY = DIAG.W02_IDLE_CORE_REVISION + "b" * 64
DEBUG_IDENTITY = {"dp_idcode": 0x6BA02477, "target_id": 0x000C0289,
                  "ahb_ap_idr": 0x84770001, "ahb_ap_csw": 0x40,
                  "ctrl_ap_idr": 0x32880000, "approtect_status": 0}


def hex_record(address, kind, data=b""):
    """! @brief production parser에 전달할 정상 checksum Intel HEX record를 만듭니다. """
    body = bytes((len(data), address >> 8, address & 255, kind)) + data
    return ":" + (body + bytes((-sum(body) & 255,))).hex().upper() + "\n"


def example_hex():
    """! @brief Host 전용 가짜 image이며 실제 machine-code 실행 가능성을 주장하지 않습니다. """
    vector = (0x20002000).to_bytes(4, "little") + (0x101).to_bytes(4, "little")
    return (hex_record(0, 0, vector) + hex_record(0x100, 0, IDENTITY.encode()) + hex_record(0, 1)).encode()


def example_watcher_elf():
    """! @brief 실제 parser에 통과시키는 최소 ARM ELF symbol table이며 실행 image가 아닙니다. """
    names = bytearray(b"\0")
    symbols = bytearray(16)
    for index, (name, size) in enumerate(DIAG.THIRD_IDLE_SYMBOLS.items()):
        offset = len(names)
        names.extend(f"_ZN12_GLOBAL__N_1{len(name)}{name}E".encode() + b"\0")
        symbols.extend(struct.pack("<IIIBBH", offset, 0x20001000 + index * 40, size, 1, 0, 1))
    header = bytearray(52)
    header[:7] = b"\x7fELF\x01\x01\x01"
    struct.pack_into("<H", header, 18, 40)
    table = 52 + len(names) + len(symbols)
    struct.pack_into("<I", header, 32, table)
    struct.pack_into("<HH", header, 46, 40, 3)
    sections = bytes(40) + struct.pack("<10I", 0, 3, 0, 0, 52, len(names), 0, 0, 1, 0)
    sections += struct.pack("<10I", 0, 2, 0, 0, 52 + len(names), len(symbols), 1, 0, 4, 16)
    return bytes(header) + bytes(names) + bytes(symbols) + sections


class FakeTarget:
    """! @brief CPU/RADIO/RRAM 동작을 제한적으로 흉내 내는 순수 Host target. """
    def __init__(self, role, trace):
        self.role, self.trace = role, trace
        self.state, self.radio = "RUNNING", 0
        self.memory = {}
        self.registers = {}
        self.pc, self.sp = 0x20000100, 0x20002000
        self.reset_observed = False
        self.bad_readback = False
        self.disable_stuck = False

    def get_state(self):
        return SimpleNamespace(name=self.state)

    def halt(self):
        self.trace.append((self.role, "halt"))
        self.state = "HALTED"

    def read32(self, address):
        if address == DIAG.DHCSR:
            return (DIAG.DHCSR_HALTED if self.state == "HALTED" else 1) | (DIAG.DHCSR_RESET if self.reset_observed else 0)
        if address == DIAG.RADIO_STATE:
            return self.radio
        return self.registers.get(address, 0)

    def read_core_register(self, name):
        return {"pc": self.pc, "sp": self.sp}[name]

    def write32(self, address, value):
        if (address, value) != (DIAG.RADIO_DISABLE, 1):
            raise AssertionError("허가되지 않은 mock register write")
        self.trace.append((self.role, "disable"))
        if not self.disable_stuck:
            self.radio = 0

    def flush(self):
        self.trace.append((self.role, "flush"))

    def read_memory_block8(self, address, count):
        data = [self.memory.get(address + offset, 255) for offset in range(count)]
        if self.bad_readback:
            data[0] ^= 1
        return data


class FakeBackend:
    """! @brief reset/flash는 mock trace로만 남기며 pyOCD를 import하지 않습니다. """
    def __init__(self):
        self.trace = []
        self.probes = [SimpleNamespace(unique_id=uid) for uid in UIDS]
        self.ports = [SimpleNamespace(device=f"COM{index + 1}", serial_number=uid) for index, uid in enumerate(UIDS)]
        self.targets = [FakeTarget(role, self.trace) for role in DIAG.PREPARATION_ROLES]
        self.identities = [dict(DEBUG_IDENTITY) for _ in UIDS]
        self.fail_discovery = False

    def discover(self):
        self.trace.append(("all", "discover"))
        if self.fail_discovery:
            raise RuntimeError("private raw UID=" + UIDS[0])
        return self.probes, self.ports

    @contextmanager
    def session(self, probe, initialize=True):
        index = UIDS.index(probe.unique_id)
        self.trace.append((DIAG.PREPARATION_ROLES[index], "attach" if initialize else "no-init"))
        yield SimpleNamespace(target=self.targets[index], index=index)

    def identity(self, session):
        return self.identities[session.index]

    def program(self, session, image):
        self.trace.append((DIAG.PREPARATION_ROLES[session.index], "sector-program"))
        for start, data in image["ranges"]:
            session.target.memory.update({start + offset: value for offset, value in enumerate(data)})

    def start(self, session):
        self.trace.append((DIAG.PREPARATION_ROLES[session.index], "authorized-reset-resume"))
        session.target.state = "RUNNING"


class PreparationTests(unittest.TestCase):
    """! @brief mocked PASS와 실제 실물 준비를 구분하며 모든 음성 경로를 fail-closed로 검사합니다. """
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="nu54-diagnostic-prepare-test-")
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.image = self.directory / "mock.hex"
        self.image.write_bytes(example_hex())
        self.args = Namespace(sdk=self.directory / "sdk", output=self.directory / "proof",
                              firmware_identity=IDENTITY, transport="twowire", execute=True,
                              authorize_sector_program=True, authorize_tx_rx_algorithm_reset=True,
                              authorize_third_halt_audit=True, tx_port="COM1", rx_port="COM2",
                              third_idle_fixture=None, third_idle_fixture_sha256="")
        for index, role in enumerate(DIAG.PREPARATION_ROLES):
            setattr(self.args, role + "_probe_sha256", HASHES[index])
            setattr(self.args, role + "_hex", self.image)
            setattr(self.args, role + "_hex_sha256", DIAG.sha256(self.image))
        self.backend = FakeBackend()
        self.addCleanup(patch.stopall)
        patch.object(DIAG, "mdk_evidence", return_value={"fixture": "mock-only"}).start()
        patch.object(DIAG, "source_identity", return_value=IDENTITY).start()
        patch.object(DIAG, "revision", return_value=IDENTITY[:40]).start()
        patch.object(DIAG.tempfile, "gettempdir", return_value=str(self.directory)).start()
        self.create_watcher_fixture()

    def create_watcher_fixture(self):
        """! @brief W02 native final schema를 Host 가짜 자료로 구성하고 live RAM도 별도로 준비합니다. """
        revisions = {"core": IDENTITY[:40], **{key: DIAG.LOCK[key]["revision"] for key in ("board", "ncs", "zephyr")}}
        nonce = "c" * 32
        zero = {key: "0" for key in ("native_links", "links", "pending", "scan", "advertising", "watchdog")}
        stopped = {"role": "watcher", "core": revisions["core"], "nonce": nonce, **zero}
        prefix = "watcher: M33PROFILE|1|"
        transcript = (prefix + "READY|role=watcher|nonce=|core=" + revisions["core"] + "\n" +
                      prefix + "SERVER_STATS|role=watcher|nonce=" + nonce + "|core=" + revisions["core"] + "\n" +
                      prefix + "STOPPED|" + "|".join(key + "=" + value for key, value in stopped.items()) + "\n").encode()
        evidence = {"family": "native", "status": "DEVELOPMENT_PASS", "revisions": revisions,
                    "transcript_sha256": DIAG.digest_bytes(transcript),
                    "cleanup": {"watcher": {**stopped, "serial_close": "PASS"}},
                    "boards": {"watcher": {"probe_sha256": HASHES[2], "image_sha256": DIAG.sha256(self.image)}}}
        blobs = {"evidence": json.dumps(evidence).encode(), "transcript": transcript, "image": example_hex(),
                 "config": b"CONFIG_SOC_NRF54L15_CPUAPP=y\n", "sysbuild": b"SB_CONFIG_FLPRCORE_NONE=y\n",
                 "elf": example_watcher_elf()}
        data = {"schema": DIAG.THIRD_IDLE_SCHEMA, "role": "standard-watcher", "probe_sha256": HASHES[2],
                "revisions": revisions, "nonce": nonce, "files": {}, "after_stopped_actions": ["uart_close"],
                "build_defines": {"M33_PROFILE_FAMILY": "standard", "M33_PROFILE_ROLE": "watcher"},
                "source_files": {name: DIAG.git_blob_sha256(revisions["core"], name)
                                 for name in DIAG.THIRD_IDLE_SOURCES}}
        for kind, raw in blobs.items():
            path = self.directory / (kind + ".bin")
            path.write_bytes(raw)
            data["files"][kind] = {"path": path.name, "sha256": DIAG.digest_bytes(raw)}
        image = DIAG.inspect_hex(self.image, DIAG.sha256(self.image), None)
        data["load_ranges"] = [{"start": address, "length": len(raw), "sha256": DIAG.digest_bytes(raw)}
                               for address, raw in image["ranges"]]
        self.args.third_idle_fixture = self.directory / "w02-idle.json"
        self.args.third_idle_fixture.write_text(json.dumps(data), encoding="utf-8")
        self.args.third_idle_fixture_sha256 = DIAG.sha256(self.args.third_idle_fixture)
        expected = {"nonce": nonce.encode() + b"\0", "started": b"\0", "cleanup_complete": b"\1",
                    "stop_reported": b"\1", "failed": b"\0", "watchdog_channel": b"\xff" * 4}
        target = self.backend.targets[2]
        for address, raw in image["ranges"]:
            target.memory.update({address + offset: byte for offset, byte in enumerate(raw)})
        for name, value in DIAG.watcher_symbols(blobs["elf"]).items():
            target.memory.update({value["address"] + offset: byte for offset, byte in enumerate(expected[name])})

    def prepare(self):
        """! @brief test 출력이 실물 PASS처럼 보이지 않게 mock 결과만 검사합니다. """
        with redirect_stdout(io.StringIO()):
            DIAG.prepare_pair(self.args, self.backend)

    def test_plan_only_never_discovers_probe_or_emits_ready_fixture(self):
        self.args.execute = False
        self.prepare()
        self.assertEqual(self.backend.trace, [])
        self.assertFalse((self.args.output / "fixture.json").exists())
        report = json.loads((self.args.output / "preflight.json").read_text())
        self.assertEqual(report["status"], "NOT_RUN")
        self.assertEqual(report["boards"][0]["sectors"], [0])

    def test_missing_each_authorization_is_rejected_before_probe_access(self):
        for name in ("authorize_sector_program", "authorize_tx_rx_algorithm_reset", "authorize_third_halt_audit"):
            with self.subTest(name=name):
                changed = copy.copy(self.args)
                setattr(changed, name, False)
                with self.assertRaises(ValueError):
                    DIAG.prepare_pair(changed, self.backend)
        self.assertEqual(self.backend.trace, [])

    def test_duplicate_hash_or_port_and_uid_port_are_rejected(self):
        for name, value in (("rx_probe_sha256", HASHES[0]), ("rx_port", "com1"),
                            ("tx_port", "/dev/serial/by-id/" + UIDS[0])):
            changed = copy.copy(self.args)
            setattr(changed, name, value)
            with self.assertRaises(ValueError):
                DIAG.prepare_pair(changed, self.backend)
        self.assertEqual(self.backend.trace, [])

    def test_live_mapping_rejects_wrong_missing_extra_or_duplicate_probe(self):
        for probes in (self.backend.probes[:2], self.backend.probes + [SimpleNamespace(unique_id="f" * 32)],
                       self.backend.probes[:2] + [self.backend.probes[0]]):
            with self.assertRaises(ValueError):
                DIAG.map_live_probes(probes, self.backend.ports, HASHES, ["COM1", "COM2"])
        self.backend.ports[0].serial_number = UIDS[1]
        with self.assertRaises(ValueError):
            DIAG.map_live_probes(self.backend.probes, self.backend.ports, HASHES, ["COM1", "COM2"])

    def test_dp_ap_protection_or_identity_is_not_unlocked(self):
        for key in DEBUG_IDENTITY:
            changed = dict(DEBUG_IDENTITY)
            changed[key] ^= 0xFFFFFFFF
            with self.subTest(key=key), self.assertRaises(ValueError):
                DIAG.validate_debug_identity(changed)
        self.backend.identities[2]["approtect_status"] = 1
        with self.assertRaises(RuntimeError):
            self.prepare()
        self.assertFalse(any(action in ("halt", "sector-program", "disable") for _, action in self.backend.trace))

    def test_hex_sha_checksum_overlap_eof_identity_and_protected_range_reject(self):
        valid = example_hex()
        bad = [valid[:-1] + b"broken\n", valid.replace(b"FF", b"FE", 1),
               (hex_record(0, 4, b"\x00\xff") + hex_record(0xD000, 0, b"\x01") + hex_record(0, 1)).encode(),
               valid.replace(hex_record(0, 1).encode(), hex_record(0, 0, b"\x01").encode() + hex_record(0, 1).encode()),
               valid.replace(hex_record(0, 1).encode(), b""),
               (hex_record(0, 0, b"\x00" * 8) + hex_record(0, 1)).encode()]
        for content in bad:
            self.image.write_bytes(content)
            with self.assertRaises((ValueError, UnicodeError)):
                DIAG.inspect_hex(self.image, DIAG.sha256(self.image), IDENTITY)
        self.image.write_bytes(valid)
        with self.assertRaises(ValueError):
            DIAG.inspect_hex(self.image, "f" * 64, IDENTITY)
        with self.assertRaises(ValueError):
            DIAG.inspect_hex(self.image, DIAG.sha256(self.image), "c" * 104)

    def test_objcopy_segment_and_linear_address_records_are_supported(self):
        original = example_hex().decode()
        for address_record in (hex_record(0, 2, b"\x00\x00"), hex_record(0, 4, b"\x00\x00")):
            for entry_record in (hex_record(0, 3, b"\x00\x00\x01\x01"),
                                 hex_record(0, 5, b"\x00\x00\x01\x01")):
                source = address_record + original.replace(hex_record(0, 1), entry_record + hex_record(0, 1))
                self.image.write_text(source, encoding="ascii")
                self.assertEqual(len(DIAG.inspect_hex(self.image, DIAG.sha256(self.image), IDENTITY)["ranges"]), 2)

    def test_success_records_all_ranges_and_leaves_three_cpus_halted(self):
        self.prepare()
        fixture = DIAG.load_prepared_fixture(self.args.output / "fixture.json", False)
        self.assertTrue(fixture["start_required"])
        self.assertTrue(all(target.state == "HALTED" for target in self.backend.targets))
        self.assertEqual([item for item in self.backend.trace if item[1] == "sector-program"],
                         [("tx", "sector-program"), ("rx", "sector-program")])
        self.assertLess(self.backend.trace.index(("third", "halt")), self.backend.trace.index(("tx", "sector-program")))
        report = json.loads((self.args.output / "preflight.json").read_text())
        self.assertFalse(report["safety"]["auto_unlock"])
        self.assertFalse(report["safety"]["third_reset"])
        self.assertFalse(report["safety"]["third_program"])
        self.assertFalse(report["safety"]["radio_task_writes"])
        self.assertEqual(report["boards"][2]["image_kind"], "intel_hex_file")
        for board in report["boards"]:
            self.assertEqual(len(board["readback"]), 2)
            self.assertTrue(all(row["expected_sha256"] == row["observed_sha256"] for row in board["readback"]))
        self.assertFalse(any(uid in json.dumps(report) for uid in UIDS))

    def test_mismatch_never_emits_fixture_and_cleanup_never_resets(self):
        self.backend.targets[0].registers[DIAG.RADIO_BASE + 0x400] = DIAG.RADIO_PASSIVE_SHORTS
        self.backend.targets[0].bad_readback = True
        with self.assertRaises(RuntimeError):
            self.prepare()
        self.assertFalse((self.args.output / "fixture.json").exists())
        report = json.loads((self.args.output / "preflight.json").read_text())
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["stage"], "program_tx")
        self.assertEqual({item["role"] for item in report["cleanup"]}, {"third", "tx", "rx"})
        self.assertTrue(all(item["halt_read_only_audit"] == "PASS" for item in report["cleanup"]))
        self.assertFalse(any("reset" in action for _, action in self.backend.trace))

    def test_third_active_radio_and_running_cpu_are_not_passed(self):
        third = self.backend.targets[2]
        third.radio = 9
        with self.assertRaises(ValueError):
            DIAG.isolate_radio(third)
        third.radio = 0
        third.state = "RUNNING"
        with self.assertRaises(ValueError):
            DIAG.verify_isolation(third)

    def test_tx_rx_only_accepts_passive_phyend_disable_short(self):
        """! @brief RADIO를 시작할 수 없는 PHYEND→DISABLE만 TX/RX 전환에서 허용합니다. """
        target = self.backend.targets[0]
        target.state = "HALTED"
        target.registers[DIAG.RADIO_BASE + 0x400] = DIAG.RADIO_PASSIVE_SHORTS
        result = DIAG.verify_isolation(target, allowed_shorts=DIAG.RADIO_PASSIVE_SHORTS)
        self.assertEqual(result["registers"][f"0x{DIAG.RADIO_BASE + 0x400:08x}"], DIAG.RADIO_PASSIVE_SHORTS)
        target.registers[DIAG.RADIO_BASE + 0x400] |= 1 << 17
        with self.assertRaises(DIAG.IdleAuditFailure):
            DIAG.verify_isolation(target, allowed_shorts=DIAG.RADIO_PASSIVE_SHORTS)

    def test_readback_short_and_deadline_are_rejected(self):
        target = self.backend.targets[0]
        with patch.object(target, "read_memory_block8", return_value=[]):
            with self.assertRaises(ValueError):
                DIAG.readback_ranges(target, [(0, b"a")])
        with patch.object(DIAG.time, "monotonic", side_effect=[0.0, 121.0]):
            with self.assertRaises(TimeoutError):
                DIAG.readback_ranges(target, [(0, b"a")])

    def test_preflight_hash_transport_and_live_image_are_rechecked(self):
        self.prepare()
        path = self.args.output / "fixture.json"
        fixture = DIAG.load_prepared_fixture(path, False)
        with self.assertRaises(ValueError):
            DIAG.load_prepared_fixture(path, True)
        with ExitStack() as resources:
            sessions, guard = DIAG.open_prepared_pair(resources, path, fixture, self.backend)
            self.assertEqual(len(sessions), 3)
            self.assertFalse(guard.monitor.reset_seen)
        self.backend.targets[1].memory[0] ^= 1
        with ExitStack() as resources, self.assertRaises(ValueError):
            DIAG.open_prepared_pair(resources, path, fixture, self.backend)
        (self.args.output / "preflight.json").write_text("{}")
        with self.assertRaises(ValueError):
            DIAG.load_prepared_fixture(path, False)

    def test_lock_is_shared_with_existing_raw_uid_probe_lock(self):
        spec = importlib.util.spec_from_file_location("existing_probe_lock", ROOT / "tests/hil/nu54dk/v04_protocol.py")
        common = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(common)
        with common.ProbeLocks(UIDS, self.directory / "nu54dk-hil-locks"):
            with self.assertRaises(RuntimeError):
                self.prepare()
        self.assertEqual(self.backend.trace, [])

    def test_changed_safety_policy_is_rejected_even_with_new_evidence_hash(self):
        self.prepare()
        path = self.args.output / "fixture.json"
        preflight = self.args.output / "preflight.json"
        fixture = json.loads(path.read_text())
        original = json.loads(preflight.read_text())
        for key in original["safety"]:
            changed = copy.deepcopy(original)
            changed["safety"][key] = "chip" if key == "erase" else not changed["safety"][key]
            preflight.write_text(json.dumps(changed), encoding="utf-8")
            fixture["preflight_evidence_sha256"] = DIAG.sha256(preflight)
            path.write_text(json.dumps(fixture), encoding="utf-8")
            with self.subTest(key=key), self.assertRaises(ValueError):
                DIAG.load_prepared_fixture(path, False)

    def test_run_preflight_rejects_changed_third_state_without_starting(self):
        self.prepare()
        path = self.args.output / "fixture.json"
        fixture = DIAG.load_prepared_fixture(path, False)
        self.backend.targets[2].radio = 9
        with ExitStack() as resources, self.assertRaises(ValueError):
            DIAG.open_prepared_pair(resources, path, fixture, self.backend)
        self.assertFalse(any("reset" in action for _, action in self.backend.trace))

    def test_mdk_revision_and_register_drift_are_rejected(self):
        with patch.object(DIAG, "revision", return_value="wrong"):
            with self.assertRaises(ValueError):
                MDK_EVIDENCE(self.args.sdk)
        revisions = [DIAG.LOCK[key]["revision"] for key in ("ncs", "zephyr", "board")]
        with patch.object(DIAG, "revision", side_effect=revisions):
            with patch.object(Path, "read_text", return_value="#define NRF_RADIO_S_BASE 0x50089000UL"):
                with self.assertRaises(ValueError):
                    MDK_EVIDENCE(self.args.sdk)

    def test_failure_does_not_publish_raw_uid_or_backend_exception_text(self):
        self.backend.fail_discovery = True
        with self.assertRaises(RuntimeError) as error:
            self.prepare()
        output = (self.args.output / "preflight.json").read_text()
        self.assertNotIn(UIDS[0], output + str(error.exception))
        self.assertNotIn("private raw UID", output)

    def test_backend_safety_options_and_no_automatic_recovery_interface(self):
        self.assertEqual(DIAG.SAFE_SESSION_OPTIONS["frequency"], 500000)
        self.assertFalse(DIAG.SAFE_SESSION_OPTIONS["auto_unlock"])
        self.assertFalse(DIAG.SAFE_SESSION_OPTIONS["resume_on_disconnect"])
        self.assertEqual(DIAG.SAFE_SESSION_OPTIONS["connect_mode"], "attach")
        self.assertEqual(DIAG.SAFE_SESSION_OPTIONS["reset_type"], "sysresetreq")
        self.assertEqual(DIAG.SAFE_SESSION_OPTIONS["flash.timeout.init"], 30.0)
        source = (ROOT / "tools/bluetooth/m33_diagnostics.py").read_text(encoding="utf-8")
        self.assertIn('chip_erase="sector"', source)
        self.assertIn("keep_unwritten=True, no_reset=True", source)
        self.assertNotIn(".mass_erase(", source)
        self.assertNotIn('connect_mode="under-reset"', source)

    def test_every_defined_dppi_route_and_shorts_is_rejected_without_writes(self):
        target = self.backend.targets[2]
        addresses = [DIAG.RADIO_BASE + offset for offset in DIAG.RADIO_SUBSCRIBE + DIAG.RADIO_PUBLISH]
        addresses += [base + offset for base in DIAG.WDT_BASES for offset in DIAG.WDT_ROUTES]
        for address in addresses:
            target.registers = {address: 1 << 31}
            with self.subTest(address=hex(address)), self.assertRaises(ValueError):
                DIAG.isolate_radio(target)
        target.registers = {DIAG.RADIO_BASE + 0x400: 1}
        with self.assertRaises(ValueError):
            DIAG.isolate_radio(target)
        self.assertFalse(any(action in ("disable", "sector-program") for _, action in self.backend.trace))

    def test_watchdog_timeout_or_run_during_halt_is_rejected_without_feed_or_stop(self):
        target = self.backend.targets[2]
        for base in DIAG.WDT_BASES:
            for registers in ({base + 0x100: 1}, {base + 0x400: 1, base + 0x50C: 8}):
                target.registers = registers
                with self.assertRaises(ValueError):
                    DIAG.isolate_radio(target)
            target.registers = {base + 0x400: 1, base + 0x50C: 0}
            self.assertTrue(DIAG.isolate_radio(target)["read_only"])
        self.assertTrue(all(action == "halt" for _, action in self.backend.trace))

    def test_unsafe_pre_audit_on_any_board_prevents_all_program_and_radio_tasks(self):
        for index in range(3):
            self.backend = FakeBackend()
            self.args.output = self.directory / ("unsafe-" + str(index))
            self.backend.targets[index].registers[DIAG.RADIO_BASE + 0x320] = 1 << 31
            with self.assertRaises(RuntimeError):
                self.prepare()
            self.assertFalse(any(action in ("disable", "sector-program", "authorized-reset-resume")
                                 for _, action in self.backend.trace))
            report = json.loads((self.args.output / "preflight.json").read_text())
            self.assertEqual(report["audit_failure"]["kind"], "dppi_enabled")
            self.assertEqual(report["audit_role"], DIAG.PREPARATION_ROLES[index])

    def test_missing_w02_fixture_is_not_run_without_probe_or_program(self):
        self.args.third_idle_fixture = None
        self.prepare()
        self.assertEqual(self.backend.trace, [])
        report = json.loads((self.args.output / "preflight.json").read_text())
        self.assertEqual(report["status"], "NOT_RUN")
        self.assertFalse((self.args.output / "fixture.json").exists())

    def test_wrong_w02_fixture_hash_is_rejected_before_hardware(self):
        self.args.third_idle_fixture_sha256 = "f" * 64
        with self.assertRaises(ValueError):
            self.prepare()
        self.assertEqual(self.backend.trace, [])

    def test_changed_dtm_source_identity_is_rejected_before_hardware(self):
        with patch.object(DIAG, "source_identity", return_value="c" * 104), self.assertRaises(ValueError):
            self.prepare()
        self.assertEqual(self.backend.trace, [])

    def test_same_w02_handoff_is_only_read_back_never_reprovisioned(self):
        self.prepare()
        self.args.output = self.directory / "reused"
        self.backend.trace.clear()
        self.prepare()
        self.assertNotIn(("third", "sector-program"), self.backend.trace)
        fixture = DIAG.load_prepared_fixture(self.args.output / "fixture.json", False)
        self.assertEqual(fixture["boards"][2]["image_kind"], "intel_hex_file")

    def test_register_change_read_failure_or_reset_latches_guard_failure(self):
        target = self.backend.targets[2]
        target.halt()
        baseline = DIAG.verify_isolation(target)
        for cause in ("reset", "register", "read"):
            target.pc, target.reset_observed, target.registers = 0x20000100, False, {}
            guard = DIAG.ThirdGuard(target, baseline)
            if cause == "reset":
                target.reset_observed = True
            elif cause == "register":
                target.registers[DIAG.RADIO_BASE + 0x100] = 1
            with patch.object(target, "read32", side_effect=OSError("mock")) if cause == "read" else ExitStack():
                with self.subTest(cause=cause), self.assertRaises((ValueError, OSError)):
                    guard.check()
            target.pc, target.reset_observed, target.registers = 0x20000100, False, {}
            with self.assertRaises(ValueError):
                guard.check()

    def test_transient_reset_is_not_consumed_by_get_state_or_core_register_reads(self):
        target = self.backend.targets[2]
        target.halt()
        monitor = DIAG.RawResetMonitor(target)
        baseline = DIAG.verify_isolation(target, monitor)
        guard = DIAG.ThirdGuard(target, baseline, monitor)
        original = target.read32
        injected = False
        def transient(address):
            nonlocal injected
            if address != DIAG.DHCSR and not injected:
                target.reset_observed = True
                injected = True
            value = original(address)
            if address == DIAG.DHCSR:
                target.reset_observed = False
            return value
        with patch.object(target, "read32", side_effect=transient), \
                patch.object(target, "get_state", side_effect=AssertionError("would consume reset")) as get_state, \
                patch.object(target, "read_core_register", side_effect=AssertionError("would consume reset")) as core_read:
            with self.assertRaises(DIAG.IdleAuditFailure):
                guard.check()
            self.assertTrue(monitor.reset_seen)
            self.assertFalse(target.reset_observed)
            with self.assertRaises(DIAG.IdleAuditFailure):
                monitor.sample()
            get_state.assert_not_called()
            core_read.assert_not_called()

    def test_third_prepare_and_run_preflight_do_not_use_state_or_core_register_api(self):
        target = self.backend.targets[2]
        with patch.object(target, "get_state", side_effect=AssertionError("forbidden")), \
                patch.object(target, "read_core_register", side_effect=AssertionError("forbidden")):
            self.prepare()
            path = self.args.output / "fixture.json"
            fixture = DIAG.load_prepared_fixture(path, False)
            with ExitStack() as resources:
                _, guard = DIAG.open_prepared_pair(resources, path, fixture, self.backend)
                guard.check()
        self.assertFalse(any(role == "third" and action in ("sector-program", "authorized-reset-resume", "disable")
                             for role, action in self.backend.trace))

    def test_watcher_ram_nonce_started_cleanup_and_watchdog_must_still_match(self):
        watcher = DIAG.load_watcher_fixture(self.args.third_idle_fixture, self.args.third_idle_fixture_sha256, HASHES[2])
        target = self.backend.targets[2]
        target.halt()
        for name, symbol in watcher["symbols"].items():
            address = symbol["address"]
            target.memory[address] ^= 1
            with self.subTest(name=name), self.assertRaises(DIAG.IdleAuditFailure):
                DIAG.verify_watcher_ram(target, watcher, DIAG.RawResetMonitor(target))
            target.memory[address] ^= 1

    def test_w02_schema_source_ranges_and_post_stop_actions_are_fail_closed(self):
        original = json.loads(self.args.third_idle_fixture.read_text())
        for key, value in (("after_stopped_actions", ["reset"]), ("after_stopped_actions", ["program"]),
                           ("after_stopped_actions", ["resume"]), ("after_stopped_actions", []),
                           ("revisions", {}), ("source_files", {}), ("load_ranges", []),
                           ("role", "dtm"), ("probe_sha256", HASHES[1])):
            changed = copy.deepcopy(original)
            changed[key] = value
            self.args.third_idle_fixture.write_text(json.dumps(changed), encoding="utf-8")
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                DIAG.load_watcher_fixture(self.args.third_idle_fixture, DIAG.sha256(self.args.third_idle_fixture), HASHES[2])

    def test_w02_transcript_begin_or_nonzero_stop_and_flpr_child_are_rejected(self):
        fixture_path = self.args.third_idle_fixture
        original = json.loads(fixture_path.read_text())
        transcript_path = self.directory / original["files"]["transcript"]["path"]
        transcript = transcript_path.read_bytes()
        for replacement in (transcript.replace(b"|SERVER_STATS|", b"|BEGIN|"),
                            transcript.replace(b"watchdog=0", b"watchdog=1"),
                            transcript.replace(b"|SERVER_STATS|", b"|START|")):
            changed = copy.deepcopy(original)
            transcript_path.write_bytes(replacement)
            changed["files"]["transcript"]["sha256"] = DIAG.digest_bytes(replacement)
            evidence_path = self.directory / changed["files"]["evidence"]["path"]
            evidence = json.loads(evidence_path.read_text())
            evidence["transcript_sha256"] = DIAG.digest_bytes(replacement)
            evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
            changed["files"]["evidence"]["sha256"] = DIAG.sha256(evidence_path)
            fixture_path.write_text(json.dumps(changed), encoding="utf-8")
            with self.assertRaises(ValueError):
                DIAG.load_watcher_fixture(fixture_path, DIAG.sha256(fixture_path), HASHES[2])
        changed = copy.deepcopy(original)
        sysbuild = self.directory / changed["files"]["sysbuild"]["path"]
        sysbuild.write_text("SB_CONFIG_FLPRCORE_NONE=y\nSB_CONFIG_FLPRCORE_EMPTY=y\n", encoding="utf-8")
        changed["files"]["sysbuild"]["sha256"] = DIAG.sha256(sysbuild)
        fixture_path.write_text(json.dumps(changed), encoding="utf-8")
        with self.assertRaises(ValueError):
            DIAG.load_watcher_fixture(fixture_path, DIAG.sha256(fixture_path), HASHES[2])

    def test_watcher_cleanup_requires_runner_serial_close(self):
        """! @brief target STOPPED와 runner UART close 증거를 구분해 검사합니다. """

        fixture_path = self.args.third_idle_fixture
        original = json.loads(fixture_path.read_text())
        evidence_path = self.directory / original["files"]["evidence"]["path"]
        for serial_close in (None, "FAIL"):
            changed = copy.deepcopy(original)
            evidence = json.loads(evidence_path.read_text())
            if serial_close is None:
                evidence["cleanup"]["watcher"].pop("serial_close")
            else:
                evidence["cleanup"]["watcher"]["serial_close"] = serial_close
            evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
            changed["files"]["evidence"]["sha256"] = DIAG.sha256(evidence_path)
            fixture_path.write_text(json.dumps(changed), encoding="utf-8")
            with self.subTest(serial_close=serial_close), self.assertRaisesRegex(
                    ValueError, "zero-resource"):
                DIAG.load_watcher_fixture(
                    fixture_path, DIAG.sha256(fixture_path), HASHES[2]
                )

    def test_exact_elf_symbol_validation_rejects_wrong_architecture_and_missing_symbols(self):
        valid = example_watcher_elf()
        self.assertEqual(set(DIAG.watcher_symbols(valid)), set(DIAG.THIRD_IDLE_SYMBOLS))
        for malformed in (valid[:20], valid[:18] + b"\0\0" + valid[20:], valid.replace(b"nonceE", b"otherE")):
            with self.assertRaises((ValueError, struct.error)):
                DIAG.watcher_symbols(malformed)

    def test_two_snapshot_value_change_is_not_safe_even_when_en_bit_stays_clear(self):
        target = self.backend.targets[2]
        target.halt()
        original = target.read32
        count = 0

        def changing(address):
            nonlocal count
            if address == DIAG.RADIO_BASE + 0x320:
                count += 1
                return count - 1
            return original(address)
        with patch.object(target, "read32", side_effect=changing), self.assertRaises(ValueError):
            DIAG.verify_isolation(target)

    def test_uart_read_is_bracketed_by_guard_and_wait_is_bounded(self):
        target = self.backend.targets[2]
        target.halt()
        guard = DIAG.ThirdGuard(target, DIAG.verify_isolation(target))
        port = SimpleNamespace(read=lambda size: b"\x80\x00", write=lambda data: None)
        self.assertEqual(DIAG.DtmPort(port, False, guard).stop(), 0)
        self.assertGreaterEqual(guard.checks, 3)
        with patch.object(DIAG.time, "monotonic", side_effect=[0, 0, 0.1, 0.2, 0.3]), patch.object(DIAG.time, "sleep") as sleep:
            guard.wait(0.3)
            self.assertTrue(all(call.args[0] <= 0.1 for call in sleep.call_args_list))

    def test_real_adapter_passes_sector_only_parameters_to_mock_programmer(self):
        adapter = object.__new__(DIAG.PyocdPreparationBackend)
        adapter.programmer_type = MagicMock()
        session = object()
        image = DIAG.inspect_hex(self.image, DIAG.sha256(self.image), IDENTITY)
        adapter.program(session, image)
        adapter.programmer_type.assert_called_once_with(session, chip_erase="sector", smart_flash=False,
                                                        trust_crc=False, keep_unwritten=True, no_reset=True)
        call = adapter.programmer_type.return_value.program.call_args
        self.assertEqual(call.kwargs, {"file_format": "hex"})
        self.assertEqual(call.args[0].getvalue().encode("ascii"), example_hex())

    def test_real_adapter_session_has_no_init_preflight_and_restores_cwd(self):
        trace = []
        dp_registers = {0: DEBUG_IDENTITY["dp_idcode"], 0x24: DEBUG_IDENTITY["target_id"]}
        ap_registers = {0: 0x40, 0xFC: 0x84770001, 0x020000FC: 0x32880000, 0x02000014: 0}

        class Session:
            """! @brief pyOCD Session의 호출 경계만 기록하고 USB에는 접근하지 않습니다. """
            def __init__(self, probe, auto_open, options):
                trace.append(("options", options))
                self.target = SimpleNamespace(
                    dp=SimpleNamespace(connect=lambda: trace.append("dp-connect"),
                                       read_dp=lambda address: dp_registers[address],
                                       read_ap=lambda address: ap_registers[address]),
                    read32=lambda address: {0x00FFC31C: 0x54B15, 0xE000ED00: 0x411FD210}[address])
                self.board = SimpleNamespace(init=lambda: trace.append("board-init"),
                                             uninit=lambda: trace.append("board-uninit"))
                os.chdir(options["project_dir"])

            def open(self, init_board):
                self.init_board = init_board
                trace.append(("open", init_board))

            def close(self):
                trace.append("close")

        probe = type("MockCmsisProbe", (), {"__module__": "pyocd.probe.cmsis_dap_probe"})()
        probe._link = SimpleNamespace(protocol_version=(2, 1, 0), _interface=SimpleNamespace(is_bulk=True))
        adapter = object.__new__(DIAG.PyocdPreparationBackend)
        adapter.session_type = Session
        original = Path.cwd()
        with adapter.session(probe, initialize=False):
            self.assertNotEqual(Path.cwd(), original)
        self.assertEqual(Path.cwd(), original)
        self.assertNotIn("board-init", trace)
        self.assertEqual(trace[1], ("open", False))
        options = trace[0][1]
        self.assertFalse(options["auto_unlock"])
        self.assertFalse(options["resume_on_disconnect"])
        self.assertTrue(options["no_config"])
        with adapter.session(probe):
            self.assertIn("board-init", trace)
        self.assertIn("board-uninit", trace)
        self.assertEqual(Path.cwd(), original)
        probe._link._interface.is_bulk = False
        with self.assertRaises(ValueError):
            with adapter.session(probe):
                self.fail("HID transport must be rejected")
        self.assertEqual(Path.cwd(), original)

    def test_run_start_requires_separate_explicit_authorization(self):
        with self.assertRaises(ValueError):
            DIAG.run_pair(Namespace(authorize_start_tx_rx=False))
        adapter = object.__new__(DIAG.PyocdPreparationBackend)
        adapter.target_type = SimpleNamespace(ResetType=SimpleNamespace(SYSRESETREQ="software-only"))
        target = SimpleNamespace(reset_and_halt=MagicMock(), resume=MagicMock(),
                                 get_state=lambda: SimpleNamespace(name="HALTED"))
        adapter.start(SimpleNamespace(target=target))
        target.reset_and_halt.assert_called_once_with(reset_type="software-only")
        target.resume.assert_called_once()


if __name__ == "__main__":
    unittest.main(verbosity=2)
