"""V04 mailbox framing, identity, interruption and exclusive ownership contracts."""
import importlib.util
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

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
    def test_pmic_pins_released_from_nfc_in_both_images(self):
        for app in ("v04_pair_hil", "m24_twim_onboard_hil"):
            overlay = (ROOT / "tests/zephyr" / app / "app.overlay").read_text(encoding="utf-8")
            self.assertRegex(overlay, r"&uicr\s*\{\s*nfct-pins-as-gpios;")


if __name__ == "__main__": unittest.main()
