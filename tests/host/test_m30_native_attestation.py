#!/usr/bin/env python3
"""! @brief M30 native raw 분모와 dispatcher attestation 변환을 검증합니다. """

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
from types import SimpleNamespace
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
HIL = ROOT / "tests/hil/nu54dk"
if str(HIL) not in sys.path:
    sys.path.insert(0, str(HIL))

import m30_native_attestation as adapter  # noqa: E402
import m30_ble_dfu as dfu  # noqa: E402


def line(kind: str, fields: dict[str, object]) -> bytes:
    """! @brief 테스트용 canonical protocol record를 만듭니다. """

    suffix = "|".join(f"{key}={value}" for key, value in fields.items())
    return f"{kind}|{suffix}\n".encode("ascii")


class M30NativeAttestationTests(unittest.TestCase):
    """! @brief 축소·위조 raw record를 fail-closed로 거부하는지 검사합니다. """

    def test_pair_derives_fifty_unique_raw_cycles(self) -> None:
        """! @brief 5 capability x 10회의 CLEAR·START·PASS를 모두 요구합니다. """

        contracts = (
            ("no_input_output", "just_works", 2, 0, 0),
            ("display_keyboard", "passkey_entry", 4, 1, 2),
            ("keyboard_display", "passkey_entry", 4, 2, 1),
            ("display_yes_no", "numeric_comparison", 4, 3, 3),
            ("keyboard_display_full", "numeric_comparison", 4, 4, 4),
        )
        captures = {role: bytearray() for role in adapter.ROLES}
        cases = []
        for case_index, contract in enumerate(contracts):
            name, method, level, peripheral_io, central_io = contract
            rounds = []
            for round_index in range(1, 11):
                nonce = f"{case_index * 10 + round_index:032x}"
                rounds.append({
                    "round": round_index,
                    "nonce_sha256": hashlib.sha256(nonce.encode("ascii")).hexdigest(),
                    "method": method,
                    "security_level": level,
                    "key_size": 16,
                    "unexpected_auth_failures": 0,
                })
                for role, io_value in (
                    ("peripheral", peripheral_io),
                    ("central", central_io),
                ):
                    common = {"role": role, "case": name, "round": round_index}
                    captures[role].extend(line("M30PAIR|1|CLEARED", {
                        **common, "bond_count": 0, "nonce": nonce,
                    }))
                    captures[role].extend(line("M30PAIR|1|STARTED", {
                        **common, "io": io_value, "nonce": nonce,
                    }))
                    captures[role].extend(line("M30PAIR|1|PASS", {
                        **common, "method": method, "level": level, "key_size": 16,
                        "paired": 1, "unexpected_auth_failures": 0, "nonce": nonce,
                    }))
                    if round_index == 10:
                        captures[role].extend(line("M30PAIR|1|CLEARED", {
                            **common, "bond_count": 0, "nonce": nonce,
                        }))
            cases.append({
                "case": name,
                "method": method,
                "peripheral_io": peripheral_io,
                "central_io": central_io,
                "rounds": rounds,
            })
        records = adapter.build_pair_cycle_records(
            cases,
            {role: bytes(value) for role, value in captures.items()},
            [{role: "PASS" for role in adapter.ROLES} for _case in cases],
        )
        self.assertEqual(len(records), 50)
        broken_cleanup = [
            {role: "PASS" for role in adapter.ROLES} for _case in cases
        ]
        broken_cleanup[0]["central"] = "FAIL"
        with self.assertRaises(adapter.M30AttestationFailure):
            adapter.build_pair_cycle_records(
                cases,
                {role: bytes(value) for role, value in captures.items()},
                broken_cleanup,
            )
        captures["central"] = captures["central"].replace(
            b"|paired=1|", b"|paired=0|", 1
        )
        with self.assertRaises(adapter.M30AttestationFailure):
            adapter.build_pair_cycle_records(
                cases,
                {role: bytes(value) for role, value in captures.items()},
                [{role: "PASS" for role in adapter.ROLES} for _case in cases],
            )

    def test_oob_derives_twenty_crc_rejection_cycles(self) -> None:
        """! @brief frame hash·CRC 거부·SC L4·bond clear를 한 nonce로 묶습니다. """

        captures = {role: bytearray() for role in adapter.ROLES}
        rounds = []
        for index in range(1, 21):
            nonce = f"{index:032x}"
            digests = {
                role: hashlib.sha256(f"{role}:{index}".encode("ascii")).hexdigest()
                for role in adapter.ROLES
            }
            rounds.append({
                "round": index,
                "nonce_sha256": hashlib.sha256(nonce.encode("ascii")).hexdigest(),
                "peripheral_frame_sha256": digests["peripheral"],
                "central_frame_sha256": digests["central"],
                "security_level": 4,
                "key_size": 16,
                "mismatch_attempts": 2,
                "mismatch_accepts": 0,
            })
            for role in adapter.ROLES:
                common = {"role": role, "round": index}
                records = (
                    ("CLEARED", {**common, "bond_count": 0, "nonce": nonce}),
                    ("LOCAL", {**common, "frame_sha256": digests[role], "nonce": nonce}),
                    ("REJECTED", {**common, "class": "crc", "nonce": nonce}),
                    ("ARMED", {**common, "nonce": nonce}),
                    ("STARTED", {**common, "nonce": nonce}),
                    ("PASS", {
                        **common, "method": "oob", "level": 4, "key_size": 16,
                        "sc": 1, "oob": 1, "nonce": nonce,
                    }),
                )
                for kind, fields in records:
                    captures[role].extend(line(f"M30OOB|1|{kind}", fields))
                if index == 20:
                    captures[role].extend(line("M30OOB|1|CLEARED", {
                        **common, "bond_count": 0, "nonce": nonce,
                    }))
        records = adapter.build_oob_cycle_records(
            rounds,
            {role: bytes(value) for role, value in captures.items()},
            {role: "PASS" for role in adapter.ROLES},
        )
        self.assertEqual(len(records), 20)
        rounds[0]["mismatch_accepts"] = 1
        with self.assertRaises(adapter.M30AttestationFailure):
            adapter.build_oob_cycle_records(
                rounds,
                {role: bytes(value) for role, value in captures.items()},
                {role: "PASS" for role in adapter.ROLES},
            )

    def test_bond_and_profile_aggregates_reject_reduced_denominators(self) -> None:
        """! @brief 20 reconnect와 100 operation aggregate를 raw record에 결합합니다. """

        nonce = "ab" * 16
        revision = "c" * 40
        bond_captures = {role: bytearray() for role in adapter.ROLES}
        bond_results = {}
        for role in adapter.ROLES:
            identity = {"role": role, "nonce": nonce, "core": revision}
            for _reset in range(2):
                bond_captures[role].extend(line("M30BOND|1|RESETTING", {
                    "role": role, "warm": 1, "core": revision,
                }))
            bond_captures[role].extend(line("M30BOND|1|MIGRATE_REBOOT", {
                **identity, "schema": 1, "warm": 1,
            }))
            for count in range(1, 21):
                bond_captures[role].extend(line("M30BOND|1|RECONNECT", {
                    **identity, "count": count,
                }))
            bond_captures[role].extend(line("M30BOND|1|STALE_REJECTED", {
                **identity, "accepted": 0, "reason": 1,
            }))
            result_fields = {
                **identity,
                "bonded_reconnects": 20,
                "migration": 1,
                "stale_key_accepts": 0,
                "new_pairings": 0,
                "bond_count": 0 if role == "peripheral" else 1,
                "callback_context": "pass",
            }
            if role == "peripheral":
                result_fields["privacy_rotations"] = 3
            bond_captures[role].extend(line("M30BOND|1|RESULT", result_fields))
            bond_results[role] = SimpleNamespace(
                role=role,
                reconnects=20,
                rotations=3 if role == "peripheral" else 0,
                migration=1,
                stale_key_accepts=0,
                new_pairings=0,
                final_bond_count=0 if role == "peripheral" else 1,
            )
        bond_captures["peripheral"].extend(line("M30BOND|1|STALE_ERASED", {
            "role": "peripheral", "bond_count": 0, "nonce": nonce, "core": revision,
        }))
        bond_captures["peripheral"].extend(line("M30BOND|1|RPA", {
            "role": "peripheral", "rotations": 3, "nonce": nonce, "core": revision,
        }))
        bond = adapter.build_bond_cycle_records(
            bond_results,
            {role: bytes(value) for role, value in bond_captures.items()},
            nonce,
            revision,
            {role: "PASS" for role in adapter.ROLES},
        )
        self.assertEqual(len(bond), 20)

        profile_captures = {role: bytearray() for role in adapter.ROLES}
        profile_results = {}
        for role in adapter.ROLES:
            identity = {"role": role, "nonce": nonce, "core": revision}
            profile_captures[role].extend(line("M30PROFILE|1|BEGIN", identity))
            gate = (
                ("RUNNING", {**identity, "operations": 100})
                if role == "peripheral"
                else ("READY", {**identity, "catalog": 7, "dis_reads": 100})
            )
            profile_captures[role].extend(
                line(f"M30PROFILE|1|{gate[0]}", gate[1])
            )
            error = "driver_errors" if role == "peripheral" else "payload_errors"
            profile_captures[role].extend(line("M30PROFILE|1|RESULT", {
                **identity, "catalog": 7, "operations": 100, error: 0,
            }))
            profile_results[role] = SimpleNamespace(
                role=role, catalog=7, operations=100,
                payload_errors=0, driver_errors=0,
            )
        profiles = adapter.build_profile_cycle_records(
            profile_results,
            {role: bytes(value) for role, value in profile_captures.items()},
            nonce,
            revision,
            {role: "PASS" for role in adapter.ROLES},
        )
        self.assertEqual(len(profiles), 100)
        profile_results["central"].operations = 99
        with self.assertRaises(adapter.M30AttestationFailure):
            adapter.build_profile_cycle_records(
                profile_results,
                {role: bytes(value) for role, value in profile_captures.items()},
                nonce,
                revision,
                {role: "PASS" for role in adapter.ROLES},
            )

    def test_dfu_requires_all_negative_classes_and_l4_raw_link(self) -> None:
        """! @brief 5 x 20 negative와 signed update·rollback·L4를 함께 요구합니다. """

        classes = {
            name: {
                "attempts": 20,
                "upload_requests": 20,
                "state_rejects": 0,
                "boot_rejects": 20,
                "invalid_accepts": 0,
                "records": [],
            }
            for name in ("unsigned", "wrong_key", "corrupt", "truncated", "downgrade")
        }
        results = {
            "M30-DFU-01": {
                "status": "passed", "updates": 10,
                "hash_mismatches": 0, "unconfirmed_boots": 0,
            },
            "M30-DFU-NEG-01": {
                "status": "passed", "classes": classes, "invalid_accepts": 0,
                "unconfirmed_first_boots": 1, "rollback_accepts": 0,
                "recovered_version": [10, 0, 0, 0],
            },
        }
        rows = [
            {
                "path": f"candidate-{index + 1}.bin",
                "class": "positive" if index < 10 else "pending",
                "size": 1,
                "sha256": f"{index + 1:064x}",
                "image_hash": f"{index + 101:064x}",
                "version": [index + 1, 0, 0, 0],
            }
            for index in range(16)
        ]
        candidates = {
            "positive": rows[:10],
            "negative": dict(zip(classes, rows[10:15], strict=True)),
            "unconfirmed": rows[15],
        }
        expected_versions = {
            "unsigned": [20, 0, 0, 0],
            "wrong_key": [20, 0, 0, 1],
            "corrupt": [20, 0, 0, 2],
            "truncated": [20, 0, 0, 3],
            "downgrade": [9, 0, 0, 0],
        }
        for name, candidate in candidates["negative"].items():
            candidate["class"] = name
            candidate["version"] = expected_versions[name]
        candidates["unconfirmed"]["class"] = "rollback"
        candidates["unconfirmed"]["version"] = [11, 0, 0, 0]
        nonce = "12" * 16
        revision = "d" * 40
        captures = {
            role: line("M30DFU|1|LINK", {
                "role": role, "level": 4, "key_size": 16, "smp": 1,
                "nonce": nonce, "core": revision,
            })
            for role in adapter.ROLES
        }
        results["M30-DFU-01"]["records"] = [
            {
                "update": index,
                "candidate_sha256": rows[index - 1]["sha256"],
                "candidate_image_hash": rows[index - 1]["image_hash"],
                "version": [index, 0, 0, 0],
                "upload_requests": 1,
                "active": True,
                "confirmed": True,
            }
            for index in range(1, 11)
        ]
        for name, row in classes.items():
            candidate = candidates["negative"][name]
            row["records"] = [
                {
                    "attempt": attempt,
                    "class": name,
                    "candidate_sha256": candidate["sha256"],
                    "candidate_image_hash": candidate["image_hash"],
                    "upload_requests": 1,
                    "request_error_group": None,
                    "request_error_code": 0,
                    "outcome": "boot_rejected",
                    "recovered_version": [10, 0, 0, 0],
                    "active_candidate": False,
                }
                for attempt in range(1, 21)
            ]
        results["M30-DFU-NEG-01"]["rollback_record"] = {
            "candidate_sha256": rows[15]["sha256"],
            "candidate_image_hash": rows[15]["image_hash"],
            "first_boot_version": [11, 0, 0, 0],
            "recovered_version": [10, 0, 0, 0],
            "rollback_accepts": 0,
        }
        erased_hash = hashlib.sha256(b"\xff" * 729088).hexdigest()
        records = adapter.build_dfu_cycle_records(
            results,
            candidates,
            captures,
            nonce,
            revision,
            {role: "PASS" for role in adapter.ROLES},
            {
                "mode": "nrf54l-rram-fill-verified",
                "start": 794624,
                "end_exclusive": 1523712,
                "bytes": 729088,
                "erase_value": "0xff",
                "verified_words": 182272,
                "expected_sha256": erased_hash,
                "observed_sha256": erased_hash,
                "readback_backend": "pyocd-live-target",
            },
        )
        self.assertEqual(records, adapter.dfu_typed_denominator())

        wrong_key = classes["wrong_key"]["records"][0]
        for field, value in (
            ("request_error_code", 7),
            ("outcome", "state_rejected"),
            ("candidate_image_hash", "f" * 64),
        ):
            original = wrong_key[field]
            wrong_key[field] = value
            with self.subTest(field=field):
                with self.assertRaises(adapter.M30AttestationFailure):
                    adapter.build_dfu_cycle_records(
                        results,
                        candidates,
                        captures,
                        nonce,
                        revision,
                        {role: "PASS" for role in adapter.ROLES},
                        {
                            "mode": "nrf54l-rram-fill-verified",
                            "start": 794624,
                            "end_exclusive": 1523712,
                            "bytes": 729088,
                            "erase_value": "0xff",
                            "verified_words": 182272,
                            "expected_sha256": erased_hash,
                            "observed_sha256": erased_hash,
                            "readback_backend": "pyocd-live-target",
                        },
                    )
            wrong_key[field] = original

        with self.assertRaises(adapter.M30AttestationFailure):
            adapter.build_dfu_cycle_records(
                results,
                candidates,
                captures,
                nonce,
                revision,
                {role: "PASS" for role in adapter.ROLES},
                {
                    "mode": "nrf54l-rram-fill-verified",
                    "start": 794625,
                    "end_exclusive": 1523712,
                    "bytes": 729088,
                    "erase_value": "0xff",
                    "verified_words": 182272,
                    "expected_sha256": erased_hash,
                    "observed_sha256": erased_hash,
                    "readback_backend": "pyocd-live-target",
                },
            )
        del classes["wrong_key"]
        with self.assertRaises(adapter.M30AttestationFailure):
            adapter.build_dfu_cycle_records(
                results,
                candidates,
                captures,
                nonce,
                revision,
                {role: "PASS" for role in adapter.ROLES},
                {
                    "mode": "nrf54l-rram-fill-verified",
                    "start": 794624,
                    "end_exclusive": 1523712,
                    "bytes": 729088,
                    "erase_value": "0xff",
                    "verified_words": 182272,
                    "expected_sha256": erased_hash,
                    "observed_sha256": erased_hash,
                    "readback_backend": "pyocd-live-target",
                },
            )

    def test_all_five_runners_expose_direct_images_and_native_attestation(self) -> None:
        """! @brief dispatcher가 각 role의 현재 HEX와 child attestation을 찾을 수 있습니다. """

        runners = (
            "m30_ble_pair.py",
            "m30_ble_oob.py",
            "m30_ble_bond.py",
            "m30_ble_profile.py",
            "m30_ble_dfu.py",
        )
        for name in runners:
            with self.subTest(name=name):
                source = (HIL / name).read_text(encoding="utf-8")
                self.assertIn('parser.add_argument("--peripheral-image")', source)
                self.assertIn('parser.add_argument("--central-image")', source)
                self.assertIn("complete_program_phase(", source)
                if name == "m30_ble_dfu.py":
                    self.assertIn("preserve_dfu_candidates(", source)
                    self.assertIn('"typed_denominator": typed_denominator', source)
                else:
                    self.assertIn("make_dispatch_attestation(", source)

    def test_dfu_typed_denominator_is_not_flattened_to_twenty(self) -> None:
        """! @brief 정상·5종 부정·rollback·cleanup이 독립 분모인지 검사합니다. """

        denominator = adapter.dfu_typed_denominator()
        groups = {row["name"]: row["count"] for row in denominator["groups"]}
        self.assertEqual(denominator["total_primary_cycles"], 10)
        self.assertEqual(groups["signed_update"], 10)
        for name in (
            "unsigned_rejection",
            "wrong_key_rejection",
            "corrupt_rejection",
            "truncated_rejection",
            "downgrade_rejection",
        ):
            self.assertEqual(groups[name], 20)
        self.assertEqual(groups["rollback"], 1)
        self.assertEqual(groups["secondary_slot_cleanup"], 1)
        self.assertNotIn("dispatch_cycle_records", denominator)

    def test_dfu_candidates_are_copied_adjacent_before_ephemeral_cleanup(self) -> None:
        """! @brief 16개 candidate가 임시 원본 삭제 뒤에도 인접 byte로 남습니다. """

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def artifact(index: int) -> SimpleNamespace:
                path = root / f"source-{index}.bin"
                payload = f"candidate-{index}".encode("ascii")
                path.write_bytes(payload)
                return SimpleNamespace(
                    path=path,
                    size=len(payload),
                    sha256=hashlib.sha256(payload).hexdigest(),
                    version=(index, 0, 0, 0),
                    image_hash=hashlib.sha256(b"image" + payload).digest(),
                )

            artifacts = [artifact(index) for index in range(1, 17)]
            negative_names = (
                "unsigned", "wrong_key", "corrupt", "truncated", "downgrade"
            )
            evidence = root / "result.json"
            records = adapter.preserve_dfu_candidates(
                evidence,
                artifacts[:10],
                dict(zip(negative_names, artifacts[10:15], strict=True)),
                artifacts[15],
            )
            rows = (
                records["positive"]
                + list(records["negative"].values())
                + [records["unconfirmed"]]
            )
            self.assertEqual(len(rows), 16)
            for row in rows:
                path = root / row["path"]
                self.assertTrue(path.is_file())
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), row["sha256"])

    def test_dfu_partial_open_closes_first_uart(self) -> None:
        """! @brief 두 번째 UART open 실패가 첫 번째 handle을 누출하지 않습니다. """

        class FakePort:
            def __init__(self) -> None:
                self.is_open = True

            def __enter__(self) -> FakePort:
                return self

            def __exit__(self, *_arguments: object) -> None:
                self.is_open = False

            def reset_input_buffer(self) -> None:
                return None

        class FakeSerialModule:
            EIGHTBITS = 8
            PARITY_NONE = "N"
            STOPBITS_ONE = 1

            def __init__(self) -> None:
                self.port = FakePort()
                self.calls = 0

            def Serial(self, *_arguments: object, **_keywords: object) -> FakePort:
                self.calls += 1
                if self.calls == 2:
                    raise OSError("second port refused")
                return self.port

        serial_module = FakeSerialModule()
        session = dfu.DfuSession(
            serial_module,
            SimpleNamespace(port_name="COM1"),
            SimpleNamespace(port_name="COM2"),
            115200,
            "12" * 16,
            "a" * 40,
        )
        with self.assertRaises(OSError):
            session.__enter__()
        self.assertFalse(serial_module.port.is_open)
        self.assertEqual(session.cleanup, {"peripheral": "PASS"})

    def test_mcuboot_candidate_identity_comes_from_adjacent_bytes(self) -> None:
        """! @brief candidate JSON이 아니라 header·SHA TLV byte를 신뢰합니다. """

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "candidate.bin"
            header = bytearray(0x800)
            struct.pack_into("<IIHHII", header, 0, 0x96F3B83D, 0, 0x800, 0, 4, 0)
            struct.pack_into("<BBHI", header, 20, 20, 0, 0, 1)
            image_hash = bytes(range(32))
            tlv = struct.pack("<HHBBH", 0x6907, 40, 0x10, 0, 32) + image_hash
            path.write_bytes(bytes(header) + b"data" + tlv)
            version, observed_hash = adapter._mcuboot_candidate_identity(path)
            self.assertEqual(version, [20, 0, 0, 1])
            self.assertEqual(observed_hash, image_hash.hex())

            data = bytearray(path.read_bytes())
            data[0] ^= 0x01
            path.write_bytes(data)
            with self.assertRaises(adapter.M30AttestationFailure):
                adapter._mcuboot_candidate_identity(path)

    def test_program_phase_rebuilds_every_adjacent_byte_range(self) -> None:
        """! @brief phase validator가 image 전체 range와 sidecar hash를 재검증합니다. """

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            native_path = root / "native.json"
            image = root / "phase.peripheral.image.hex"
            build_record = root / "phase.peripheral.build-record"
            readback_path = root / "phase.peripheral.readback.json"
            image.write_text(
                ":020000040000FA\n"
                ":080000000102030405060708D4\n"
                ":00000001FF\n",
                encoding="ascii",
            )
            build_record.write_bytes(b"exact-build-record\n")
            raw = bytes(range(1, 9))
            digest = hashlib.sha256(raw).hexdigest()
            probe = hashlib.sha256(b"probe-1").hexdigest()
            readback = {
                "schema_version": 1,
                "kind": "m33_exact_program_readback",
                "status": "PASS",
                "role": "peripheral",
                "probe_sha256": probe,
                "image_sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
                "backend": "pyocd-live-target",
                "halted": True,
                "resumed": True,
                "pre_state": "RUNNING",
                "post_state": "RUNNING",
                "restored": True,
                "ranges": [{
                    "start": 0,
                    "length": len(raw),
                    "expected_sha256": digest,
                    "observed_sha256": digest,
                    "status": "PASS",
                }],
            }
            readback_path.write_text(
                json.dumps(readback, sort_keys=True), encoding="utf-8"
            )

            def reference(path: Path) -> dict[str, str]:
                """! @brief 인접 test byte의 basename과 digest를 반환합니다. """

                return {
                    "path": path.name,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }

            native = {
                "core_revision": "a" * 40,
                "board_revision": "b" * 40,
                "program_phases": [{
                    "phase": "phase",
                    "hardware": [{
                        "role": "peripheral",
                        "probe_sha256": probe,
                        "image": reference(image),
                        "build_record": reference(build_record),
                        "build_identity": {
                            "core_revision": "a" * 12,
                            "core_source_sha256": "1" * 64,
                            "application_source_sha256": "2" * 64,
                            "board_revision": "b" * 12,
                            "board_source_sha256": "3" * 64,
                            "ncs_revision": "99553055607b",
                            "zephyr_revision": "bf801e4e3d19",
                            "board": "nrf54l15dk",
                            "board_qualifiers": "nrf54l15/cpuapp/nu54dk",
                            "toolchain_variant": "zephyr",
                            "cxx_compiler": "GNU 14.3.0",
                            "record_sha256": hashlib.sha256(
                                build_record.read_bytes()
                            ).hexdigest(),
                        },
                        "flash": {
                            "mode": "pyocd-sector-test",
                            "programmed_bytes": 8,
                            "erase": "sector",
                            "auto_unlock": False,
                            "mass_erase": False,
                            "automatic_recover": False,
                        },
                        "readback": reference(readback_path),
                    }],
                }],
            }
            adapter.validate_program_phases(
                native, native_path, {"phase": ("peripheral",)}
            )

            identity = native["program_phases"][0]["hardware"][0][
                "build_identity"
            ]
            identity["core_revision"] = "c" * 12
            with self.assertRaises(adapter.M30AttestationFailure):
                adapter.validate_program_phases(
                    native, native_path, {"phase": ("peripheral",)}
                )
            identity["core_revision"] = "a" * 12

            readback["ranges"][0]["length"] = 7
            readback_path.write_text(
                json.dumps(readback, sort_keys=True), encoding="utf-8"
            )
            native["program_phases"][0]["hardware"][0]["readback"] = reference(
                readback_path
            )
            with self.assertRaises(adapter.M30AttestationFailure):
                adapter.validate_program_phases(
                    native, native_path, {"phase": ("peripheral",)}
                )


if __name__ == "__main__":
    unittest.main()
