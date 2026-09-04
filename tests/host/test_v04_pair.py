"""V04 mailbox framing, identity, interruption and exclusive ownership contracts."""
import importlib.util
import json
from pathlib import Path
from contextlib import ExitStack
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, MagicMock, patch

ROOT = Path(__file__).resolve().parents[2]
HIL = ROOT / "tests/hil/nu54dk"
sys.path.insert(0, str(HIL))
import v04_protocol as protocol
import v04_pair as runner


class FakeTarget:
    def __init__(self, corrupt=False):
        self.memory = bytearray(1024)
        self.corrupt = corrupt
    def write32(self, address, value):
        self.memory[address:address+4] = struct.pack("<I", value)
        if address == 0 and value == protocol.MAGIC:
            packet = bytes(self.memory[:128])
            self.memory[256:384] = packet
            if self.corrupt:
                self.memory[256 + 8] ^= 1
    def read32(self, address):
        return struct.unpack("<I", self.memory[address:address+4])[0]
    def write_memory_block8(self, address, data): self.memory[address:address+len(data)] = data
    def read_memory_block8(self, address, count): return self.memory[address:address+count]
    def flush(self): pass


class V04PairTests(unittest.TestCase):
    nonce = bytes(range(16))

    def test_boot_checks_images_and_clears_only_mailbox_markers_before_resume(self):
        image = {"path": Path("candidate.hex"), "elf": Path("candidate.elf"),
                 "sha256": "hex", "elf_sha256": "elf", "role": 1, "core_revision": "a" * 40,
                 "symbols": {"v04_request": 64, "v04_response": 192, "v04_identity": 320}}
        session = MagicMock()
        target = session.target
        target.get_state.return_value.name = "HALTED"
        target.read32.side_effect = lambda address: 0x411FD210 if address == 0xE000ED00 else protocol.MAGIC
        target.read_memory_block8.return_value = struct.pack("<4I", protocol.MAGIC, 1, 1, 0) + b"a" * 40 + bytes(8)
        helper = Mock()
        helper.session_with_chosen_probe.return_value = session
        with patch.object(runner, "sha256_file", side_effect=lambda path: path.suffix[1:]), \
             patch.object(runner, "flash_image", return_value={"mock_only": True}) as flash, ExitStack() as stack:
            device, _ = runner.boot_exact(stack, helper, Path("pyocd.exe"), "a" * 32, image)
            self.assertEqual(device.image, image)
            flash.assert_called_once_with(Path("pyocd.exe"), "a" * 32, Path("candidate.hex"), 120)
        self.assertEqual(target.write32.call_args_list, [unittest.mock.call(64, 0),
                         unittest.mock.call(192, 0), unittest.mock.call(320, 0)])
        options = helper.session_with_chosen_probe.call_args.kwargs
        self.assertTrue(options["no_config"])
        self.assertFalse(options["options"]["auto_unlock"])
        self.assertFalse(options["options"]["resume_on_disconnect"])
        target.reset_and_halt.assert_called_once()
        target.resume.assert_called_once()
        with patch.object(runner, "sha256_file", return_value="changed"), \
             patch.object(runner, "flash_image") as flash, ExitStack() as stack:
            with self.assertRaises(protocol.ProtocolError):
                runner.boot_exact(stack, helper, Path("pyocd.exe"), "a" * 32, image)
            flash.assert_not_called()
    def test_frame_roundtrip(self):
        raw = protocol.encode(self.nonce, 1, 1, 2, [0, 0xffffffff])
        self.assertEqual(protocol.decode(raw, self.nonce, 1, 1, 2), (0, [0, 0xffffffff]))
    def test_stale_role_opcode_nonce_rejected(self):
        raw = protocol.encode(self.nonce, 7, 1, 2)
        for args in ((self.nonce, 8, 1, 2), (self.nonce, 7, 2, 2), (self.nonce, 7, 1, 3), (bytes(16), 7, 1, 2)):
            with self.assertRaises(protocol.ProtocolError): protocol.decode(raw, *args)
    def test_corruption_and_length_rejected(self):
        raw = protocol.encode(self.nonce, 1, 1, 1)
        for bad in (raw[:-1], b"x" + raw, bytes([raw[0] ^ 1]) + raw[1:]):
            with self.assertRaises(protocol.ProtocolError): protocol.decode(bad, self.nonce, 1, 1, 1)
    def test_empty_nonce_and_oversized_values_rejected(self):
        with self.assertRaises(protocol.ProtocolError): protocol.encode(bytes(16), 1, 1, 1)
        with self.assertRaises(protocol.ProtocolError): protocol.encode(self.nonce, 1, 1, 1, range(21))
    def test_same_probe_rejected(self):
        with self.assertRaises(protocol.ProtocolError): protocol.validate_pair("a"*32, "A"*32)
        self.assertEqual(protocol.validate_pair("a"*32, "b"*32), ("a"*32, "b"*32))
    def test_identity_commit_and_role(self):
        raw = struct.pack("<4I", protocol.MAGIC, 1, 1, 0) + b"a"*40 + bytes(8)
        runner.verify_identity(raw, 1, "a"*40)
        for role, commit in ((2, "a"*40), (1, "b"*40)):
            with self.assertRaises(protocol.ProtocolError): runner.verify_identity(raw, role, commit)
    def test_swd_mailbox_commit_and_poison(self):
        image = {"role": 1, "symbols": {"v04_request": 0, "v04_response": 256}}
        device = runner.Device(FakeTarget(), image, self.nonce)
        self.assertEqual(device.command(1, [2, 3]), [2, 3])
        broken = runner.Device(FakeTarget(corrupt=True), image, self.nonce)
        with self.assertRaises(protocol.ProtocolError): broken.command(1)
        self.assertTrue(broken.poisoned)
        with self.assertRaises(protocol.ProtocolError): broken.command(1)
    def test_os_lock_rejects_competing_process_then_releases(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)
            code = "import sys; from pathlib import Path; sys.path.insert(0, sys.argv[1]); from v04_protocol import ProbeLocks;\nwith ProbeLocks(['" + "a"*32 + "'], Path(sys.argv[2])): print('ACQUIRED')"
            command = [sys.executable, "-c", code, str(HIL), str(path)]
            with protocol.ProbeLocks(["a"*32], path):
                result = subprocess.run(command, capture_output=True, timeout=10)
                self.assertNotEqual(result.returncode, 0)
            result = subprocess.run(command, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
    def test_no_external_pin_opcode_or_implicit_flash(self):
        source = (ROOT / "tests/zephyr/v04_pair_hil/src/main.cpp").read_text(encoding="utf-8")
        self.assertNotIn("digitalWrite(", source)
        self.assertIn('"--execute-onboard"', (HIL / "v04_pair.py").read_text(encoding="utf-8"))

    def test_onboard_runner_requires_multi_dma_concurrency_result(self):
        firmware = (ROOT / "tests/zephyr/v04_pair_hil/src/main.cpp").read_text(
            encoding="utf-8")
        host = (HIL / "v04_pair.py").read_text(encoding="utf-8")
        self.assertIn("concurrentAnalogTest", firmware)
        self.assertIn("device.command(5)", host)
        self.assertIn("V04-ANALOG-CONCURRENCY/pwm20-pwm21-saadc", host)
    def test_pmic_pins_released_from_nfc_in_both_images(self):
        for app in ("v04_pair_hil", "m24_twim_onboard_hil"):
            overlay = (ROOT / "tests/zephyr" / app / "app.overlay").read_text(encoding="utf-8")
            self.assertRegex(overlay, r"&uicr\s*\{\s*nfct-pins-as-gpios;")

    def test_evidence_existing_journal_is_preserved_and_result_finalized(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "result.json"
            journal = path.with_suffix(".json.jsonl")
            journal.write_text("old failure\n", encoding="utf-8")
            evidence = {}
            with self.assertRaises(FileExistsError):
                with runner.evidence_session(path, evidence):
                    self.fail("must reject before hardware operations")
            self.assertEqual(json.loads(path.read_text())["status"], "failed")
            self.assertEqual(journal.read_text(), "old failure\n")
            saved = path.read_bytes()
            with self.assertRaises(FileExistsError):
                with runner.evidence_session(path, {}):
                    self.fail("must not reuse an old result")
            self.assertEqual(path.read_bytes(), saved)

    def test_evidence_interrupt_retains_partial_results(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "result.json"
            evidence = {"results": [{"id": "one", "status": "passed"}]}
            with self.assertRaises(KeyboardInterrupt):
                with runner.evidence_session(path, evidence) as log:
                    log.write("partial\n")
                    raise KeyboardInterrupt()
            saved = json.loads(path.read_text())
            self.assertEqual(saved["status"], "interrupted")
            self.assertEqual(saved["results"], evidence["results"])
            self.assertIn("completed_at_utc", saved)

    def test_failure_stop_cannot_hide_failure_or_retry_poisoned_device(self):
        device = Mock(poisoned=False)
        device.command.return_value = [0, 1]
        self.assertEqual(runner.stop_after_uart_failure(device)["status"], "stopped")
        device.command.assert_called_once_with(13, timeout=2)
        device.reset_mock()
        device.poisoned = True
        self.assertEqual(runner.stop_after_uart_failure(device)["status"], "not_attempted")
        device.command.assert_not_called()
        device.poisoned = False
        device.command.side_effect = protocol.ProtocolError("STOP timeout")
        self.assertEqual(runner.stop_after_uart_failure(device)["status"], "unproven")


if __name__ == "__main__": unittest.main()
