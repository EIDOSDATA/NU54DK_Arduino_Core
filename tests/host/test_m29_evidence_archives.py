#!/usr/bin/env python3
"""! @brief M29 raw HIL 증거 archive의 byte 동일성을 검증합니다. """

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import unittest


REPOSITORY = Path(__file__).resolve().parents[2]
EVIDENCE_ROOT = REPOSITORY / "00_Docs" / "04_검증 기록" / "evidence"
ARCHIVES = {
    "m29-w07-ad605bab-windows-gatt-failure": {
        "purpose": "M29 Windows/Intel GATT reconnect failure raw evidence",
        "revision": "ad605babfd935fcd430a8f75b132881d0f8a6f82",
        "result": None,
        "gate": None,
        "files": 1,
    },
    "m29-w07d-16eb8fce-multi": {
        "purpose": "M29-MULTI-01 exact raw HIL evidence",
        "revision": "16eb8fce204f656beb6ed0a0d6f763cc7d492215",
        "result": "m29-w07d-16eb8fce.json",
        "gate": "m29-w07-d-three-board-multi-link-hil",
        "files": 4,
    },
    "m29-w07e-16eb8fce-regression": {
        "purpose": "M29-REG-01 exact raw HIL evidence",
        "revision": "16eb8fce204f656beb6ed0a0d6f763cc7d492215",
        "result": "m29-reg.json",
        "gate": "m29-ble-regression-hil",
        "files": 13,
    },
    "m29-w07-a964ae20-windows-gatt": {
        "purpose": "M29 Windows/Intel cross-vendor GATT exact raw HIL evidence",
        "revision": "a964ae205e237d90149f6d2c0eb0ec6492492a33",
        "result": "result.json",
        "gate": "m29-cross-vendor-windows-gatt-hil",
        "files": 2,
    },
    "m29-w08-ab3f85d3-multi-rerun": {
        "purpose": "M29-W08 refactored target exact three-board rerun evidence",
        "revision": "ab3f85d3cb505f8f82865becfbd8bd0fe8511f27",
        "result": "m29-w08-ab3f85d3.json",
        "gate": "m29-w07-d-three-board-multi-link-hil",
        "files": 4,
    },
}


def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """! @brief JSON 중복 key를 증거 metadata 위조로 거부합니다. """

    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


class M29EvidenceArchiveTests(unittest.TestCase):
    """! @brief Base64 archive를 decode해 원본 크기·SHA·판정을 확인합니다. """

    def test_exact_raw_archives_match_manifests_and_pass_results(self) -> None:
        """! @brief 모든 archive가 원본 byte와 판정을 정확히 보존하는지 검사합니다. """

        for directory, contract in ARCHIVES.items():
            with self.subTest(directory=directory):
                root = EVIDENCE_ROOT / directory
                manifest = json.loads(
                    (root / "manifest.json").read_text(encoding="utf-8"),
                    object_pairs_hook=reject_duplicate_keys,
                )
                self.assertEqual(manifest["schema_version"], 1)
                self.assertEqual(manifest["archive_format"], "base64-rfc4648")
                self.assertEqual(manifest["purpose"], contract["purpose"])
                self.assertEqual(manifest["core_revision"], contract["revision"])
                self.assertEqual(len(manifest["files"]), contract["files"])

                decoded: dict[str, bytes] = {}
                for entry in manifest["files"]:
                    encoded_path = root / entry["archive_file"]
                    encoded = "".join(encoded_path.read_text(encoding="ascii").split())
                    raw = base64.b64decode(encoded, validate=True)
                    self.assertEqual(len(raw), entry["raw_size"])
                    self.assertEqual(hashlib.sha256(raw).hexdigest(), entry["raw_sha256"])
                    decoded[entry["logical_name"]] = raw

                if contract["result"] is not None:
                    result = json.loads(
                        decoded[contract["result"]].decode("utf-8"),
                        object_pairs_hook=reject_duplicate_keys,
                    )
                    self.assertEqual(result["gate"], contract["gate"])
                    self.assertEqual(result["status"], "passed")
                    self.assertEqual(result["core_revision"], contract["revision"])


if __name__ == "__main__":
    unittest.main()
