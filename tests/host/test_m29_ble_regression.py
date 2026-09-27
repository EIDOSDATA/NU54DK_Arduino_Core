#!/usr/bin/env python3
"""! @brief M29-REG-01 증거 집계기의 fail-closed 경계를 검증합니다. """

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
HIL = ROOT / "tests" / "hil" / "nu54dk"
if str(HIL) not in sys.path:
    sys.path.insert(0, str(HIL))

from m29_ble_regression_protocol import (  # noqa: E402
    BOARD_TARGET,
    GROUP_CONTRACTS,
    GROUP_ORDER,
    RegressionEvidenceFailure,
    validate_regression_session,
)


CORE_REVISION = "1" * 40
BOARD_REVISION = "2" * 40
UIDS = ("a" * 32, "b" * 32, "c" * 32)


class M29BleRegressionTests(unittest.TestCase):
    """! @brief 정상 네 회귀군과 identity·원본·coverage 위반 거부를 검사합니다. """

    def setUp(self) -> None:
        """! @brief 시험별 임시 증거 묶음을 만듭니다. """

        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        pairs = {
            "m19": (UIDS[0], UIDS[2]),
            "m20": (UIDS[1], UIDS[2]),
            "m21": (UIDS[0], UIDS[1]),
            "m28": (UIDS[1], UIDS[0]),
        }
        self.paths = {
            group: self._write_group(group, pairs[group], index + 1)
            for index, group in enumerate(GROUP_ORDER)
        }

    def tearDown(self) -> None:
        """! @brief 임시 증거 묶음을 제거합니다. """

        self.temporary.cleanup()

    @staticmethod
    def _digest(data: bytes) -> str:
        """! @brief 시험 transcript bytes의 SHA-256을 반환합니다. """

        return hashlib.sha256(data).hexdigest()

    def _write_group(
        self, group: str, uids: tuple[str, str], nonce_index: int
    ) -> Path:
        """! @brief 실제 runner schema와 같은 최소 PASS 증거를 기록합니다. """

        path = self.root / f"{group}.json"
        peripheral = f"{group}-peripheral\n".encode("ascii")
        central = f"{group}-central\n".encode("ascii")
        peripheral_path = path.with_name(f"{path.stem}.peripheral.transcript.log")
        central_path = path.with_name(f"{path.stem}.central.transcript.log")
        peripheral_path.write_bytes(peripheral)
        central_path.write_bytes(central)
        if group == "m21":
            transcripts = {
                "peripheral_sha256": self._digest(peripheral),
                "central_sha256": self._digest(central),
            }
        else:
            transcripts = {
                "peripheral": {
                    "name": peripheral_path.name,
                    "size": len(peripheral),
                    "sha256": self._digest(peripheral),
                },
                "central": {
                    "name": central_path.name,
                    "size": len(central),
                    "sha256": self._digest(central),
                },
            }
        data = {
            "schema_version": GROUP_CONTRACTS[group]["schema_version"],
            "gate": GROUP_CONTRACTS[group]["gate"],
            "status": "passed",
            "core_revision": CORE_REVISION,
            "board_revision": BOARD_REVISION,
            "board_target": BOARD_TARGET,
            "nonce": f"{nonce_index:032x}",
            "boards": {
                "peripheral": {"daplink_uid": uids[0]},
                "central": {"daplink_uid": uids[1]},
            },
            "transcripts": transcripts,
            "coverage": copy.deepcopy(GROUP_CONTRACTS[group]["coverage"]),
            "safety": copy.deepcopy(GROUP_CONTRACTS[group]["safety"]),
        }
        if group == "m21":
            del data["board_target"]
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def _read(self, group: str) -> dict:
        """! @brief 지정 회귀군 JSON을 읽습니다. """

        return json.loads(self.paths[group].read_text(encoding="utf-8"))

    def _write(self, group: str, value: dict) -> None:
        """! @brief 변경한 회귀군 JSON을 기록합니다. """

        self.paths[group].write_text(json.dumps(value), encoding="utf-8")

    def assert_rejected(self) -> None:
        """! @brief 현재 묶음이 aggregate 검증에서 거부되는지 확인합니다. """

        with self.assertRaises(RegressionEvidenceFailure):
            validate_regression_session(self.paths, CORE_REVISION, BOARD_REVISION)

    def test_accepts_exact_four_groups_and_three_boards(self) -> None:
        results = validate_regression_session(
            self.paths, CORE_REVISION, BOARD_REVISION
        )
        self.assertEqual(tuple(results), GROUP_ORDER)
        self.assertEqual(
            {uid for result in results.values() for uid in result.board_uids},
            set(UIDS),
        )

    def test_rejects_missing_group(self) -> None:
        del self.paths["m28"]
        self.assert_rejected()

    def test_rejects_duplicate_evidence_path(self) -> None:
        self.paths["m28"] = self.paths["m19"]
        self.assert_rejected()

    def test_rejects_wrong_gate(self) -> None:
        data = self._read("m19")
        data["gate"] = "m19-candidate"
        self._write("m19", data)
        self.assert_rejected()

    def test_rejects_failed_status(self) -> None:
        data = self._read("m20")
        data["status"] = "failed"
        self._write("m20", data)
        self.assert_rejected()

    def test_rejects_wrong_core_revision(self) -> None:
        data = self._read("m21")
        data["core_revision"] = "3" * 40
        self._write("m21", data)
        self.assert_rejected()

    def test_rejects_wrong_board_revision(self) -> None:
        data = self._read("m28")
        data["board_revision"] = "4" * 40
        self._write("m28", data)
        self.assert_rejected()

    def test_rejects_wrong_board_target(self) -> None:
        data = self._read("m19")
        data["board_target"] = "nrf54l15dk/default"
        self._write("m19", data)
        self.assert_rejected()

    def test_rejects_duplicate_nonce(self) -> None:
        data = self._read("m20")
        data["nonce"] = self._read("m19")["nonce"]
        self._write("m20", data)
        self.assert_rejected()

    def test_rejects_duplicate_role_uid(self) -> None:
        data = self._read("m21")
        data["boards"]["central"]["daplink_uid"] = data["boards"]["peripheral"][
            "daplink_uid"
        ]
        self._write("m21", data)
        self.assert_rejected()

    def test_rejects_two_board_union(self) -> None:
        for group in GROUP_ORDER:
            data = self._read(group)
            data["boards"]["peripheral"]["daplink_uid"] = UIDS[0]
            data["boards"]["central"]["daplink_uid"] = UIDS[1]
            self._write(group, data)
        self.assert_rejected()

    def test_rejects_four_board_union(self) -> None:
        data = self._read("m28")
        data["boards"]["central"]["daplink_uid"] = "d" * 32
        self._write("m28", data)
        self.assert_rejected()

    def test_rejects_missing_transcript(self) -> None:
        self.paths["m19"].with_name("m19.central.transcript.log").unlink()
        self.assert_rejected()

    def test_rejects_modified_transcript(self) -> None:
        self.paths["m20"].with_name("m20.peripheral.transcript.log").write_bytes(
            b"modified\n"
        )
        self.assert_rejected()

    def test_rejects_wrong_coverage_value_and_type(self) -> None:
        data = self._read("m28")
        data["coverage"]["extended_reports"] = True
        self._write("m28", data)
        self.assert_rejected()

    def test_rejects_unsafe_mass_erase(self) -> None:
        data = self._read("m21")
        data["safety"]["mass_erase_requested"] = True
        self._write("m21", data)
        self.assert_rejected()

    def test_rejects_duplicate_json_key(self) -> None:
        raw = self.paths["m19"].read_text(encoding="utf-8")
        self.paths["m19"].write_text(
            raw.replace('{"schema_version": 1', '{"schema_version": 1, "schema_version": 1'),
            encoding="utf-8",
        )
        self.assert_rejected()


if __name__ == "__main__":
    unittest.main()
