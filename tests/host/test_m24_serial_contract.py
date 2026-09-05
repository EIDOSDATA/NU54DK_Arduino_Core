#!/usr/bin/env python3
"""M24 serial-fabric route, identity and API contract tests."""

from __future__ import annotations

import copy
import importlib.util
import os
from pathlib import Path
import subprocess
import unittest


REPOSITORY = Path(__file__).resolve().parents[2]
SCRIPT = REPOSITORY / "tools" / "peripheral" / "verify_m24_serial_contract.py"
SPEC = importlib.util.spec_from_file_location("nucode_m24_serial_contract", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class M24SerialContractTests(unittest.TestCase):
    """Fail-closed route and future API contract semantics."""

    def setUp(self) -> None:
        self.contract = MODULE.strict_json_object(MODULE.CONTRACT_PATH)

    def test_contract_schema_generated_document_and_exact_ncs_pass(self) -> None:
        MODULE.validate_schema_contract(MODULE.strict_json_object(MODULE.SCHEMA_PATH))
        identities = MODULE.validate_contract(self.contract)
        self.assertEqual(len(identities), 23)
        installed = Path("C:/ncs/v3.4.0")
        if installed.is_dir():
            MODULE.validate_ncs_dts(self.contract, installed)
        result = subprocess.run(
            [os.fspath(Path(os.sys.executable)), os.fspath(SCRIPT)],
            cwd=REPOSITORY,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertIn(
            "M24_SERIAL_CONTRACT_PASS=blocks:5;identities:23;profiles:23;onboard:7;fixture:16",
            result.stdout,
        )

    def test_block_personality_omission_is_rejected(self) -> None:
        mutated = copy.deepcopy(self.contract)
        lookup = {item["id"]: item for item in mutated["blocks"]}
        lookup["serial21"]["personalities"].remove("twis21")
        with self.assertRaisesRegex(MODULE.ContractFailure, "block identity/personality drifted"):
            MODULE.validate_contract(mutated)

    def test_public_alias_or_singleton_identity_drift_is_rejected(self) -> None:
        mutated = copy.deepcopy(self.contract)
        mutated["stable_surface"]["singletons"][1]["identity"] = "uarte21"
        with self.assertRaisesRegex(MODULE.ContractFailure, "stable singleton identity drifted"):
            MODULE.validate_contract(mutated)

        mutated = copy.deepcopy(self.contract)
        mutated["stable_surface"]["forbidden_aliases"].remove("Serial2")
        with self.assertRaisesRegex(MODULE.ContractFailure, "forbidden alias set drifted"):
            MODULE.validate_contract(mutated)

    def test_dedicated_pin_mapping_and_board_conflict_are_rejected_on_drift(self) -> None:
        mutated = copy.deepcopy(self.contract)
        bank = next(item for item in mutated["pin_banks"] if item["id"] == "p2-dedicated20")
        bank["signal_sets"]["spim"]["sck"] = "P2.6"
        with self.assertRaisesRegex(MODULE.ContractFailure, "dedicated signal mapping drifted"):
            MODULE.validate_contract(mutated)

        mutated = copy.deepcopy(self.contract)
        bank = next(item for item in mutated["pin_banks"] if item["id"] == "p2-dedicated21")
        bank["board_status"] = "approved"
        with self.assertRaisesRegex(MODULE.ContractFailure, "pin bank identity/status drifted"):
            MODULE.validate_contract(mutated)

    def test_every_identity_needs_one_approved_hil_profile(self) -> None:
        mutated = copy.deepcopy(self.contract)
        mutated["approved_profiles"] = [
            item for item in mutated["approved_profiles"] if item["identity"] != "spis30"
        ]
        with self.assertRaisesRegex(MODULE.ContractFailure, "exactly one HIL route profile"):
            MODULE.validate_contract(mutated)

    def test_onboard_resources_partition_profiles_and_keep_fixture_boundary(self) -> None:
        resources = {
            item["id"]: item for item in self.contract["test_resources"]
        }
        onboard = {
            identity
            for item in resources.values()
            if item["execution_class"] == "onboard-automatic"
            for identity in item["identities"]
        }
        self.assertEqual(
            onboard,
            {
                "uarte20",
                "uarte21",
                "uarte22",
                "uarte30",
                "twim20",
                "twim21",
                "twim22",
            },
        )
        profiles = {
            item["identity"]: item for item in self.contract["approved_profiles"]
        }
        for identity in ("uarte21", "uarte22"):
            self.assertEqual(profiles[identity]["test_resource"], "dap-vcom-p1")
            self.assertEqual(
                profiles[identity]["pins"],
                {"txd": "P1.4", "rxd": "P1.5", "rts": "P1.6", "cts": "P1.7"},
            )
        for identity in ("twim20", "twim21", "twim22"):
            self.assertEqual(
                profiles[identity]["test_resource"], "pmic-bq25186-i2c"
            )

        mutated = copy.deepcopy(self.contract)
        resource = next(
            item for item in mutated["test_resources"] if item["id"] == "dap-vcom-p1"
        )
        resource["identities"].remove("uarte22")
        with self.assertRaisesRegex(
            MODULE.ContractFailure, "board test resource identity/class drifted"
        ):
            MODULE.validate_contract(mutated)

    def test_unsafe_pin_profile_is_rejected(self) -> None:
        mutated = copy.deepcopy(self.contract)
        profile = next(
            item for item in mutated["approved_profiles"] if item["identity"] == "uarte21"
        )
        profile["pins"]["txd"] = "P1.8"
        with self.assertRaisesRegex(MODULE.ContractFailure, "blocked P1 pin"):
            MODULE.validate_contract(mutated)

        mutated = copy.deepcopy(self.contract)
        profile = next(
            item for item in mutated["approved_profiles"] if item["identity"] == "spim30"
        )
        profile["preconditions"] = ["Serial1 is inactive."]
        with self.assertRaisesRegex(MODULE.ContractFailure, "Serial1/DAP isolation"):
            MODULE.validate_contract(mutated)

    def test_local_board_source_checksum_is_fail_closed(self) -> None:
        mutated = copy.deepcopy(self.contract["sources"])
        source = next(item for item in mutated if item["id"] == "board-schematic")
        source["sha256"] = "0" * 64
        with self.assertRaisesRegex(MODULE.ContractFailure, "checksum mismatch"):
            MODULE.validate_sources(mutated)

    def test_text_source_hash_is_checkout_eol_invariant(self) -> None:
        lf = b"first\nsecond\n"
        crlf = b"first\r\nsecond\r\n"
        cr = b"first\rsecond\r"
        self.assertEqual(MODULE.canonical_source_payload(lf, "lf-normalized"), lf)
        self.assertEqual(MODULE.canonical_source_payload(crlf, "lf-normalized"), lf)
        self.assertEqual(MODULE.canonical_source_payload(cr, "lf-normalized"), lf)
        self.assertNotEqual(MODULE.canonical_source_payload(crlf, "raw"), lf)

    def test_candidate_implementations_remain_internal_until_hil(self) -> None:
        manifest = MODULE.strict_json_object(MODULE.MANIFEST_PATH)
        m24 = {item["id"]: item for item in manifest["instances"] if item["milestone"] == "M24"}
        current = set(MODULE.EXPECTED_SINGLETONS.values())
        self.assertEqual(len(m24), 23)
        for identity, item in m24.items():
            if identity in current:
                continue
            states = item["states"]
            self.assertEqual(states["source"], "implemented", identity)
            self.assertEqual(states["exposure"], "internal", identity)
            self.assertEqual(states["build"], "pass", identity)
            self.assertEqual(states["semantic"], "pass", identity)
            self.assertEqual(states["hil"], "not_run", identity)
            self.assertEqual(states["concurrent_hil"], "not_run", identity)
            self.assertTrue(item["evidence"], identity)

    def test_candidate_header_and_handover_sources_are_required(self) -> None:
        MODULE.validate_surface(self.contract)
        self.assertTrue(MODULE.PUBLIC_HEADER_PATH.is_file())
        self.assertTrue(MODULE.BACKEND_SOURCE_PATH.is_file())
        self.assertTrue(MODULE.ROUTE_SOURCE_PATH.is_file())

    def test_twim_activation_explicitly_enables_nrfx_instance(self) -> None:
        """Source regression only; actual transfers remain an onboard/fixture gate."""
        source = (REPOSITORY / "cores/arduino/TwimFabric.cpp").read_text(encoding="utf-8")
        activation = source.split("SerialFabricResult activateAdapter(", 1)[1].split(
            "SerialFabricResult requestStopAdapter(", 1
        )[0]
        initialized = activation.index("nrfx_twim_init(")
        enabled = activation.index("nrfx_twim_enable(&context->driver);")
        active = activation.index("atomic_set(&context->active, 1);")
        self.assertLess(initialized, enabled)
        self.assertLess(enabled, active)

    def test_spim_hardware_csn_meets_nrf54l15_spis_timing(self) -> None:
        """Source regression only; Fixture 201 proves the physical timing path."""
        source = (REPOSITORY / "cores/arduino/SpimFabric.cpp").read_text(
            encoding="utf-8"
        )
        activation = source.split("SerialFabricResult activateAdapter(", 1)[1].split(
            "SerialFabricResult requestStopAdapter(", 1
        )[0]
        self.assertIn("csn_duration_cycles = 255U", source)
        self.assertNotIn("serial_csn_duration_cycles", source)
        self.assertIn(
            "configuration.use_hw_ss = csn != NRF_SPIM_PIN_NOT_CONNECTED;",
            activation,
        )
        self.assertIn("configuration.ss_duration = csn_duration_cycles;", activation)

    def test_spim_rx_delay_matches_nrf54l15_instance_clock(self) -> None:
        """Source regression only; 8 MHz Fixture 201 proves the physical sample path."""
        source = (REPOSITORY / "cores/arduino/SpimFabric.cpp").read_text(
            encoding="utf-8"
        )
        activation = source.split("SerialFabricResult activateAdapter(", 1)[1].split(
            "SerialFabricResult requestStopAdapter(", 1
        )[0]
        self.assertIn("serial_rx_delay_cycles = 1U", source)
        self.assertIn(
            "instance == 0U ? NRF_SPIM_RXDELAY_DEFAULT : serial_rx_delay_cycles;",
            activation,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
