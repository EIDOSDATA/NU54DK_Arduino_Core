"""External fixture preparation tests; no probe, port or physical I/O is used."""
import copy
import hashlib
import json
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests/hil/nu54dk"))
import v04_fixture as fixture
import v04_fixture_run as runner
from v04_protocol import ProtocolError


class FixtureTests(unittest.TestCase):
    def test_transfer_scope_matches_encoded_controller_style(self):
        """! @brief style와 I2C address encoding을 독립적인 기대값으로 검증합니다. """
        for family, encoded in (("spi", 1), ("twi", 0x142)):
            with self.subTest(family=family, encoded=encoded):
                self.assertEqual(fixture.transfer_scope(family, encoded),
                                 "synchronous-single-buffer")
        for family, encoded in (("spi", 0), ("spi", 2), ("twi", 0x42),
                                ("twi", 0x242), ("uarte", 1), ("uarte", 0x142)):
            with self.subTest(family=family, encoded=encoded):
                self.assertEqual(fixture.transfer_scope(family, encoded),
                                 "asynchronous-single-or-double-buffer")

    def test_cli_cannot_implicitly_execute_or_omit_confirmation(self):
        command = ["--dut", "a" * 32, "--peer", "b" * 32, "--build-root", "unused",
                   "--pyocd", "unused", "--fixture", "201"]
        self.assertFalse(runner.arguments(command).execute_fixture)
        with self.assertRaises(ProtocolError):
            runner.arguments(command + ["--execute-fixture"])

    def confirmation(self, fixture_id=201):
        catalog, _ = fixture.fixture_contract(fixture_id)
        self.uids = ["a" * 32, "b" * 32]
        self.images = [{"role": role, "core_revision": "c" * 40,
                        "board_revision": catalog["board_revision"], "sha256": str(role) * 64}
                       for role in (1, 2)]
        return {"fixture_id": fixture_id, "fixture_revision": catalog["revision"],
                "catalog_sha256": hashlib.sha256(fixture.CATALOG.read_bytes()).hexdigest(),
                "core_revision": "c" * 40, "board_revision": catalog["board_revision"],
                "uid_sha256": [hashlib.sha256(uid.encode()).hexdigest() for uid in self.uids],
                "hex_sha256": [image["sha256"] for image in self.images],
                "dap_uart_disconnected_both": True, "swd_connected_both": True,
                "power_rails_not_joined": True, "equal_io_voltage_confirmed": True,
                "common_ground_confirmed": True, "links_match_catalog": True,
                "pullups_match_catalog": True,
                "extra_outputs_disconnected": True, "confirmed_at_unix": 1000,
                "confirmed_by": "Host mock only"}

    def test_confirmation_rejects_every_missing_condition(self):
        confirmation = self.confirmation()
        self.assertEqual(fixture.validate_confirmation(confirmation, self.images, self.uids, 201, 1001)["id"], 201)
        for field in confirmation:
            bad = {key: value for key, value in confirmation.items() if key != field}
            with self.subTest(field=field), self.assertRaises(ProtocolError):
                fixture.validate_confirmation(bad, self.images, self.uids, 201, 1001)
        confirmation["dap_uart_disconnected_both"] = 1
        with self.assertRaises(ProtocolError):
            fixture.validate_confirmation(confirmation, self.images, self.uids, 201, 1001)
        with self.assertRaises(ProtocolError):
            json.loads('{"confirmed": false, "confirmed": true}', object_pairs_hook=runner.unique_fields)

    def test_generated_confirmation_is_bound_but_not_approved(self):
        approved = self.confirmation()
        template = fixture.confirmation_template(self.images, self.uids, 201)
        for field in ("fixture_id", "fixture_revision", "catalog_sha256",
                      "core_revision", "board_revision", "uid_sha256", "hex_sha256"):
            self.assertEqual(template[field], approved[field])
        self.assertEqual(template["confirmed_at_unix"], 0)
        self.assertEqual(template["confirmed_by"], "")
        self.assertFalse(any(template[field] for field in (
            "dap_uart_disconnected_both", "swd_connected_both",
            "power_rails_not_joined", "equal_io_voltage_confirmed",
            "common_ground_confirmed", "links_match_catalog",
            "pullups_match_catalog", "extra_outputs_disconnected")))
        with self.assertRaises(ProtocolError):
            fixture.validate_confirmation(template, self.images, self.uids, 201, 1001)

    def test_foreign_image_role_uid_and_expiry_rejected(self):
        confirmation = self.confirmation()
        for now in (999, 2801):
            with self.assertRaises(ProtocolError):
                fixture.validate_confirmation(confirmation, self.images, self.uids, 201, now)
        for field, value in (("role", 1), ("sha256", "f" * 64), ("core_revision", "f" * 40)):
            images = copy.deepcopy(self.images)
            images[1][field] = value
            with self.subTest(field=field), self.assertRaises(ProtocolError):
                fixture.validate_confirmation(confirmation, images, self.uids, 201, 1001)
        with self.assertRaises(ProtocolError):
            fixture.validate_confirmation(confirmation, self.images, self.uids[::-1], 201, 1001)
        with self.assertRaises(ProtocolError):
            fixture.validate_confirmation(confirmation, [], [], 201, 1001)

    def test_twi_requires_explicit_catalog_pullup_confirmation(self):
        confirmation = self.confirmation(301)
        self.assertEqual(fixture.validate_confirmation(
            confirmation, self.images, self.uids, 301, 1001)["family"], "twi")
        confirmation["pullups_match_catalog"] = False
        with self.assertRaises(ProtocolError):
            fixture.validate_confirmation(confirmation, self.images, self.uids, 301, 1001)

    def test_twi_fixture_uses_internal_pullups_without_external_resistors(self):
        catalog, twi = fixture.fixture_contract(301)
        self.assertEqual(catalog["revision"], 2)
        self.assertTrue(all("내부 pull-up" in pullup for pullup in twi["pullups"]))
        self.assertIn("외부 pull-up 저항", twi["pullups"][0])
        source = (ROOT / "tests/zephyr/v04_pair_hil/src/fixture_hil.cpp").read_text(
            encoding="utf-8")
        self.assertIn("const bool use_internal_pullups = gate.fixture() == 301U;", source)
        self.assertIn("twis->configure({0x42, 0x43, use_internal_pullups})", source)

    def test_user_confirmed_connector_pinmap_is_complete_and_locked(self):
        path = ROOT / "tests/hil/nu54dk/nu54dk_connector_pinmap.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["authority"], "user-manual-transcription")
        self.assertEqual(payload["confirmed_at"], "2026-09-05")
        self.assertEqual(set(map(int, payload["connectors"]["P2"])), set(range(1, 31)))
        self.assertEqual(set(map(int, payload["connectors"]["P4"])), set(range(1, 31)))
        self.assertEqual(payload["connectors"]["P2"]["27"], "SWDCLK")
        self.assertEqual(payload["connectors"]["P2"]["28"], "SWDIO")
        canonical = json.dumps(payload["connectors"], sort_keys=True,
                               separators=(",", ":")).encode()
        self.assertEqual(hashlib.sha256(canonical).hexdigest(),
                         "6e0ea1045ac0c09b7275c44f7232c9a3375fa2e9e8a9e4b269447cd02e1c45da")

    def test_catalog_connector_pin_map_and_no_forbidden_nets(self):
        catalog = json.loads(fixture.CATALOG.read_text(encoding="utf-8"))
        pinmap_path = ROOT / "tests/hil/nu54dk/nu54dk_connector_pinmap.json"
        pinmap = json.loads(pinmap_path.read_text(encoding="utf-8"))["connectors"]

        def normalize(net):
            if net.startswith("P") and "." in net:
                port, pin = net.split(".")
                return f"{port}.{int(pin)}"
            return net

        pins = {(connector, int(pin)): normalize(net)
                for connector, entries in pinmap.items()
                for pin, net in entries.items()}
        allowed = {("P2", 9), ("P2", 10), ("P2", 11), ("P2", 12),
                   ("P2", 17), ("P2", 19), ("P2", 25), ("P2", 26),
                   ("P2", 30), ("P4", 4), ("P4", 5), ("P4", 8),
                   ("P4", 12), ("P4", 19), ("P4", 20), ("P4", 21)}
        self.assertEqual({entry["id"] for entry in catalog["fixtures"]},
                         {101, 102, 103, 201, 202, 203, 301,
                          401, 402, 403, 404, 408, 420, 430, 440})
        for entry in catalog["fixtures"]:
            for role in ("dut", "peer"):
                endpoints = [tuple(link[role]) for link in entry["links"]]
                self.assertEqual(len(set(endpoints)), len(endpoints))
                for connector, pin, net in endpoints:
                    self.assertIn((connector, pin), allowed)
                    self.assertEqual(pins[(connector, pin)], net)
                self.assertIn(("P2", 30, "GND"), endpoints)

    def test_vectors_and_transfer_direction_are_explicit(self):
        uart_vectors = list(fixture.vectors("uarte"))
        spi_vectors = list(fixture.vectors("spi"))
        twi_vectors = list(fixture.vectors("twi"))
        self.assertEqual(len(uart_vectors), 135)
        self.assertEqual(len(spi_vectors), 1513)
        self.assertEqual(len(twi_vectors), 328)
        self.assertIn((115200, 0, 1, 256, 2, 1), uart_vectors)
        self.assertIn((115200, 0, 0, 32, 3, 1), uart_vectors)
        self.assertIn((115200, 0, 0, 32, 4, 1), uart_vectors)
        self.assertIn((2000000, 0, 0, 1024, 3, 3), spi_vectors)
        self.assertIn((100000, 0, 0, 32, 1, 0x44 | (3 << 8)), twi_vectors)
        self.assertIn((100000, 0, 0, 256, 3, 0x42 | (4 << 8)), twi_vectors)
        self.assertIn((100000, 0, 0, 32, 1, 0x42 | (5 << 8)), twi_vectors)
        self.assertIn((100000, 0, 0, 32, 3, 0x42 | (6 << 8)), twi_vectors)
        source = (ROOT / "tests/hil/nu54dk/v04_fixture.py").read_text(
            encoding="utf-8")
        self.assertIn("spim00-twim22-concurrent", source)
        self.assertIn("controller.command(27)", source)
        for controller in (1, 2):
            other = 3 - controller
            self.assertEqual(fixture.expected_lengths(controller, controller, 32, 1, "spi"), (32, 32))
            self.assertEqual(fixture.expected_lengths(other, controller, 32, 1, "spi"), (0, 32))
            self.assertEqual(fixture.expected_lengths(controller, controller, 32, 1, "twi"), (32, 0))
            self.assertEqual(fixture.expected_lengths(other, controller, 32, 1, "twi"), (0, 32))
            self.assertEqual(fixture.expected_lengths(controller, controller, 32, 1,
                                                       "uarte", 2), (64, 0))
            self.assertEqual(fixture.expected_lengths(other, controller, 32, 1,
                                                       "uarte", 2), (0, 64))

    def test_expected_error_recovery_ids_keep_the_error_cause(self):
        self.assertEqual(fixture.recovery_label("uarte", 3, 1),
                         "/recovery-after-parity-mismatch")
        self.assertEqual(fixture.recovery_label("uarte", 4, 1),
                         "/recovery-after-break")
        self.assertEqual(fixture.recovery_label("spi", 3, 3),
                         "/recovery-after-cancel")
        self.assertEqual(fixture.recovery_label("twi", 1, 0x44 | (3 << 8)),
                         "/recovery-after-nack")
        self.assertEqual(fixture.recovery_label("twi", 3, 0x42 | (4 << 8)),
                         "/recovery-after-cancel")

    def test_spi_split_buffer_waits_for_peer_rearm_before_second_segment(self):
        class Device:
            def __init__(self, role, trace):
                self.image = {"role": role}
                self.role = role
                self.trace = trace
                self.status_count = 0
                self.seed = 0
                self.commands = []

            def command(self, opcode, values=(), timeout=10):
                del timeout
                self.commands.append(opcode)
                self.trace.append((self.role, opcode))
                if opcode == 18:
                    return []
                if opcode == 20:
                    self.seed = values[5]
                    return [0]
                if opcode == 21 or opcode == 28:
                    return [0]
                if opcode == 22:
                    self.status_count += 1
                    if self.role == 1:
                        completed = 1 if self.status_count == 1 else 2
                        return [1, 0, completed, completed, 0, 1,
                                completed * 4, completed * 4]
                    if self.status_count == 1:
                        return [1, 1, 0, 0, 0, 1, 0, 0]
                    completed = 1 if self.status_count == 2 else 2
                    return [1, 2, completed, completed, 0, 1,
                            completed * 4, completed * 4]
                if opcode == 24:
                    offset, count = values
                    peer_role = 3 - self.role
                    incoming = fixture.payload(self.seed ^ (0 if peer_role == 1 else 0x5a), 8)
                    chunk = incoming[offset:offset + count]
                    chunk += bytes((-len(chunk)) % 4)
                    return list(struct.unpack(f"<{len(chunk) // 4}I", chunk))
                if opcode == 23:
                    return [0, 1]
                raise AssertionError(f"unexpected opcode: {opcode}")

        trace = []
        devices = [Device(1, trace), Device(2, trace)]
        results = []
        fixture.exchange(devices, {"id": 201, "family": "spi"}, 1, (0, 20),
                         (2000000, 0, 0, 4, 3, 2),
                         lambda case_id, result: results.append((case_id, result)))
        self.assertIn(28, devices[0].commands)
        self.assertNotIn(28, devices[1].commands)
        second_start = trace.index((1, 28))
        self.assertEqual(trace[second_start - 2:second_start], [(2, 18), (1, 18)])
        self.assertEqual(len(results), 1)
        dispatch = (ROOT / "tests/zephyr/v04_pair_hil/src/main.cpp").read_text(
            encoding="utf-8")
        self.assertIn("opcode >= 16 && opcode <= 28", dispatch)


if __name__ == "__main__":
    unittest.main()
