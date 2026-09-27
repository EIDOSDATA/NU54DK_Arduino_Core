"""! @brief M31-W01의 서로 다른 잘못된 입력 20개를 fail-closed로 거부합니다. """

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests/hil/nu54dk"))
sys.path.insert(0, str(ROOT / "tests/host"))
from m31_ble_capability import ExpectedIdentity, M31CapabilityFailure, parse_transcript  # noqa: E402
from m31_iso_cis import M31IsoFailure, parse_cis_transcript  # noqa: E402
import test_m31_inventory_contract as INVENTORY_TEST  # noqa: E402
from test_m31_iso_cis import TRANSCRIPT as CIS_TRANSCRIPT, NONCES as CIS_NONCES, IDENTITY as CIS_IDENTITY  # noqa: E402


SPEC = importlib.util.spec_from_file_location("m31_contract_negative", ROOT / "tools/bluetooth/m31_contract.py")
assert SPEC is not None and SPEC.loader is not None
CONTRACT = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = CONTRACT
SPEC.loader.exec_module(CONTRACT)

CAP_ROOT = ROOT / "00_Docs/04_검증 기록/evidence/m31-w01-exact-8c125a22"
CAP_RESULT = json.loads((CAP_ROOT / "m31-cap-default-clean-8c125a22-01.json").read_text(encoding="utf-8"))
CAP_TRANSCRIPT = (CAP_ROOT / "m31-cap-default-clean-8c125a22-01.transcript.log").read_bytes()
CAP_NONCE = CAP_RESULT["nonce"]
CAP_IDENTITY = ExpectedIdentity(**CAP_RESULT["identity"])
READINESS = json.loads((ROOT / "variants/nu54dk/m31-ble-readiness.json").read_text(encoding="utf-8"))


def cap_lines() -> list[str]:
    """! @brief clean SDC의 실제 12줄 원본을 독립 mutation 입력으로 복제합니다. """
    return CAP_TRANSCRIPT.decode("ascii").splitlines()


def cap_bytes(lines: list[str]) -> bytes:
    """! @brief 유한 target protocol line을 다시 byte로 직렬화합니다. """
    return ("\n".join(lines) + "\n").encode("ascii")


class M31NegativeMatrixTests(unittest.TestCase):
    """! @brief source/build/runtime 부당 승격과 stale board 증거를 차단합니다. """

    def test_twenty_distinct_bad_inputs_are_rejected(self) -> None:
        """! @brief 20/20 예상 오류를 하나의 M31-NEG-01 분모로 검사합니다. """
        scenarios = []
        lines = cap_lines()
        wrong_nonce = lines.copy()
        wrong_nonce[1] = wrong_nonce[1].replace(CAP_NONCE, "0" * 32)
        scenarios.append(("stale_nonce", lambda: parse_transcript(cap_bytes(wrong_nonce), CAP_NONCE, CAP_IDENTITY)))
        wrong_revision = lines.copy()
        wrong_revision[2] = wrong_revision[2].replace(CAP_IDENTITY.core, "1" * 40)
        scenarios.append(("wrong_revision", lambda: parse_transcript(cap_bytes(wrong_revision), CAP_NONCE, CAP_IDENTITY)))
        duplicate = lines.copy()
        duplicate.insert(5, duplicate[4])
        scenarios.append(("duplicate_capability", lambda: parse_transcript(cap_bytes(duplicate), CAP_NONCE, CAP_IDENTITY)))
        missing = lines.copy()
        del missing[5]
        scenarios.append(("missing_capability", lambda: parse_transcript(cap_bytes(missing), CAP_NONCE, CAP_IDENTITY)))
        scenarios.append(("non_ascii_uart", lambda: parse_transcript(CAP_TRANSCRIPT + b"\xff", CAP_NONCE, CAP_IDENTITY)))
        scenarios.append(("partial_uart", lambda: parse_transcript(CAP_TRANSCRIPT[:-1], CAP_NONCE, CAP_IDENTITY)))
        wrong_id = lines.copy()
        wrong_id[4] = wrong_id[4].replace("id=cis_central", "id=unknown")
        scenarios.append(("unknown_capability", lambda: parse_transcript(cap_bytes(wrong_id), CAP_NONCE, CAP_IDENTITY)))
        mismatched_bit = lines.copy()
        mismatched_bit[4] = mismatched_bit[4].replace("controller_bit=0", "controller_bit=1")
        scenarios.append(("raw_bit_mismatch", lambda: parse_transcript(cap_bytes(mismatched_bit), CAP_NONCE, CAP_IDENTITY)))
        for bit, label in ((20, "false_sdc_iq_rx"), (21, "false_sdc_aod")):
            changed = lines.copy()
            prefix, raw = changed[3].split("features=", 1)
            data = bytearray.fromhex(raw)
            data[bit // 8] |= 1 << (bit % 8)
            changed[3] = prefix + "features=" + data.hex()
            if bit == 20:
                changed[9] = changed[9].replace("controller_bit=0", "controller_bit=1")
            scenarios.append((label, lambda changed=changed: parse_transcript(cap_bytes(changed), CAP_NONCE, CAP_IDENTITY)))
        INVENTORY = INVENTORY_TEST.MODULE
        inventory_fixture = INVENTORY_TEST.M31InventoryTests()._minimal_doc()
        duplicate_variant = copy.deepcopy(inventory_fixture)
        duplicate_variant["variants"].append(copy.deepcopy(duplicate_variant["variants"][0]))
        duplicate_variant["counts"]["variants"] = 2
        scenarios.append(("duplicate_upstream_variant", lambda: INVENTORY.validate(duplicate_variant)))
        orphan = copy.deepcopy(inventory_fixture)
        orphan["variants"][0]["parent_sample_id"] = "nrf:missing"
        scenarios.append(("orphan_upstream_variant", lambda: INVENTORY.validate(orphan)))
        reasonless = copy.deepcopy(inventory_fixture)
        reasonless["variants"][0]["route"] = "excluded"
        scenarios.append(("reasonless_exclusion", lambda: INVENTORY.validate(reasonless)))
        blocked_followup = copy.deepcopy(inventory_fixture)
        case = blocked_followup["variants"][0]["verification_cases"][0]
        case.update(verification_owner="user", verification_stage="user_follow_up",
                    development_blocker=False, release_blocker=True)
        scenarios.append(("physical_followup_reblocked", lambda: INVENTORY.validate(blocked_followup)))
        source_only_runtime = copy.deepcopy(inventory_fixture)
        source_only_runtime["source_only_features"].append({
            "id": "kconfig:BT_ISO", "runtime": {"status": "PASS"}
        })
        source_only_runtime["counts"]["source_only_features"] = 1
        scenarios.append(("source_only_runtime_promoted", lambda: INVENTORY.validate(source_only_runtime)))
        wrong_count = copy.deepcopy(READINESS)
        wrong_count["counts"]["audio_group_total"] = 10
        scenarios.append(("audio_denominator_drift", lambda: CONTRACT.validate(wrong_count)))
        hidden_implementation = copy.deepcopy(READINESS)
        hidden_implementation["test_families"][0]["cases"][0]["verification_owner"] = "user"
        scenarios.append(("implementation_hidden_as_user", lambda: CONTRACT.validate(hidden_implementation)))
        fake_physical_pass = copy.deepcopy(READINESS)
        fake_physical_pass["follow_up_cases"][0]["status"] = "PASS"
        scenarios.append(("physical_not_run_promoted", lambda: CONTRACT.validate(fake_physical_pass)))
        corrupt_cis = CIS_TRANSCRIPT.replace(b"|received=100|corrupt=0|", b"|received=100|corrupt=1|", 1)
        scenarios.append(("cis_payload_corruption", lambda: parse_cis_transcript(corrupt_cis, CIS_NONCES, CIS_IDENTITY)))
        no_stop_cis = CIS_TRANSCRIPT.replace(b"central: M31ISO|1|STOPPED|", b"central: M31ISO|1|MISSING|", 1)
        scenarios.append(("cis_missing_stop", lambda: parse_cis_transcript(no_stop_cis, CIS_NONCES, CIS_IDENTITY)))
        self.assertEqual(len(scenarios), 20)
        for label, operation in scenarios:
            with self.subTest(label=label):
                with self.assertRaises((ValueError, M31CapabilityFailure, M31IsoFailure)):
                    operation()


if __name__ == "__main__":
    unittest.main()
