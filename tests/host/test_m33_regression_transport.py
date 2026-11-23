"""! @brief 기존 Host 분모와 분리해 J-Link 저장 증거의 typed 경계를 검증합니다. """
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import test_m33_regression as baseline

MODULE = baseline.MODULE
validate_soak = baseline.validate_soak


class RegressionTransportTests(unittest.TestCase):
    """! @brief 기존 TestCase를 상속하지 않고 순수 fixture helper만 조합합니다. """

    def jlink_soak_fixture(self, base):
        """! @brief 같은 exact 증거를 명시된 J-Link transport와 receipt hash로 결합합니다. """
        path, document = baseline.RegressionTests().soak_fixture(base)
        transport = {"kind": "jlink-swd", "fixture_sha256": "a" * 64,
                     "dll_sha256": "b" * 64, "board": "nrf54l15dk"}
        del document["safety"]["cmsis_dap"]
        document["safety"]["transport"] = dict(transport)
        for role, board in document["boards"].items():
            board["transport"] = dict(transport)
            board["volume"] = None
            reference = document["images"][role]["flash_record"]
            flash_path = base / reference["path"]
            flash = MODULE.read_json(flash_path)
            del flash["cmsis_dap"]
            flash["transport"] = dict(transport)
            flash_path.write_text(json.dumps(flash), encoding="utf-8")
            reference["sha256"] = MODULE.digest(flash_path)
            document["execution_receipt"]["roles"][role]["flash_record_sha256"] = reference["sha256"]
        receipt = document["execution_receipt"]
        payload = {key: value for key, value in receipt.items() if key != "sha256"}
        receipt["sha256"] = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        path.write_text(json.dumps(document), encoding="utf-8")
        return path, document

    def test_soak_jlink_transport_requires_bound_typed_evidence(self):
        """! @brief J-Link는 flash·역할·safety의 같은 descriptor에서만 통과합니다. """
        with tempfile.TemporaryDirectory() as temporary:
            path, document = self.jlink_soak_fixture(Path(temporary))
            self.assertEqual("SCHEMA_VALID", validate_soak(
                path, document["identity"]["core"], allow_fixture=True)["status"])
            for mutation in ("fixture", "dll", "board", "missing", "mixed", "volume"):
                with self.subTest(mutation=mutation):
                    changed = copy.deepcopy(document)
                    if mutation == "fixture":
                        changed["boards"]["central"]["transport"]["fixture_sha256"] = "c" * 64
                    elif mutation == "dll":
                        changed["safety"]["transport"]["dll_sha256"] = "d" * 64
                    elif mutation == "board":
                        changed["safety"]["transport"]["board"] = "unknown"
                    elif mutation == "missing":
                        del changed["boards"]["central"]["transport"]
                    elif mutation == "mixed":
                        changed["safety"]["cmsis_dap"] = "v2-only"
                    else:
                        changed["boards"]["central"]["volume"] = "Z:/"
                    path.write_text(json.dumps(changed), encoding="utf-8")
                    with self.assertRaises(ValueError):
                        validate_soak(path, document["identity"]["core"], allow_fixture=True)

    def test_flash_transport_descriptor_rejects_untyped_or_mixed_claims(self):
        """! @brief 모호한 transport·불완전 hash·혼합 CMSIS 표기는 저장 증거로 인정하지 않습니다. """
        descriptor = {"kind": "jlink-swd", "fixture_sha256": "a" * 64,
                      "dll_sha256": "b" * 64, "board": "nrf54l15dk"}
        self.assertEqual({"kind": "cmsis-dap-v2"},
                         MODULE.evidence_transport({"cmsis_dap": "v2-only"}))
        self.assertEqual(descriptor, MODULE.evidence_transport({"transport": descriptor}))
        for invalid in (None, "jlink-swd", {"kind": "jlink-swd"},
                        {**descriptor, "kind": "anything"},
                        {**descriptor, "fixture_sha256": "a" * 63},
                        {**descriptor, "dll_sha256": "B" * 64},
                        {**descriptor, "extra": True}, {"kind": "cmsis-dap-v2"}):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                MODULE.evidence_transport({"transport": invalid})
        with self.assertRaises(ValueError):
            MODULE.evidence_transport({"transport": descriptor, "cmsis_dap": "v2-only"})


if __name__ == "__main__":
    unittest.main()
