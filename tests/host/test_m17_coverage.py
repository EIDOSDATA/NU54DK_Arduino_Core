from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = REPO_ROOT / "tools" / "coverage" / "m17_coverage.py"
SPEC = importlib.util.spec_from_file_location("m17_coverage", TOOL_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("M17 coverage 도구를 불러올 수 없습니다.")
M17 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M17)


## @brief JSON test fixture를 UTF-8 deterministic 형식으로 저장합니다.
def write_json(path: Path, value: dict) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


## @brief record 변경 뒤 manifest의 선언 hash를 명시적으로 갱신합니다.
def refresh_record_hash(dataset_root: Path, record_id: str) -> None:
    manifest_path = dataset_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    record_path = dataset_root / "records" / f"{record_id}.json"
    digest = M17._record_sha256(record_path)
    for entry in manifest["records"]:
        if entry["id"] == record_id:
            entry["sha256"] = digest
            break
    else:
        raise AssertionError(f"fixture manifest에 record가 없습니다: {record_id}")
    write_json(manifest_path, manifest)


## @brief M17 coverage schema와 fail-closed 정책의 host 회귀 시험입니다.
class M17CoverageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="nu54-m17-")
        self.dataset_root = Path(self.temporary.name) / "ncs-v3.4.0"
        shutil.copytree(REPO_ROOT / "coverage" / "ncs-v3.4.0", self.dataset_root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def validate_fixture(self) -> tuple[dict, list[dict]]:
        return M17.validate_dataset(
            REPO_ROOT,
            self.dataset_root,
            verify_board_checkout=False,
        )

    def mutate_record(self, record_id: str, mutation) -> None:
        path = self.dataset_root / "records" / f"{record_id}.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        mutation(record)
        write_json(path, record)
        refresh_record_hash(self.dataset_root, record_id)

    def test_repository_dataset_and_generated_outputs_are_current(self) -> None:
        manifest, records = M17.validate_dataset(REPO_ROOT)
        self.assertEqual(manifest["dataset"], "ncs-v3.4.0")
        self.assertEqual(len(records), 9)
        M17.render_outputs(REPO_ROOT, check=True)

    def test_generated_outputs_accept_git_crlf_checkout(self) -> None:
        """! @brief 생성 요약의 Git CRLF checkout을 LF 원본과 동일하게 검증합니다. """
        repository = Path(self.temporary.name) / "render-repository"
        dataset_root = repository / "coverage" / "ncs-v3.4.0"
        shutil.copytree(self.dataset_root, dataset_root)
        generated = dataset_root / "generated"
        for path in generated.iterdir():
            content = path.read_bytes().replace(b"\r\n", b"\n")
            path.write_bytes(content.replace(b"\n", b"\r\n"))
        manifest, records = M17.validate_dataset(
            REPO_ROOT,
            dataset_root,
            verify_board_checkout=False,
        )
        with mock.patch.object(M17, "validate_dataset", return_value=(manifest, records)):
            M17.render_outputs(repository, check=True)

    def test_duplicate_json_key_is_rejected(self) -> None:
        path = Path(self.temporary.name) / "duplicate.json"
        path.write_text('{"schema_version": 1, "schema_version": 1}\n', encoding="utf-8")
        with self.assertRaisesRegex(M17.CoverageError, "중복 JSON key"):
            M17.strict_load_json(path)

    def test_unknown_record_field_is_rejected(self) -> None:
        self.mutate_record("zephyr.sensor-direct", lambda record: record.update({"surprise": True}))
        with self.assertRaisesRegex(M17.CoverageError, r"unknown=\['surprise'\]"):
            self.validate_fixture()

    def test_invalid_enum_is_rejected(self) -> None:
        self.mutate_record("zephyr.sensor-direct", lambda record: record.update({"status": "maybe"}))
        with self.assertRaisesRegex(M17.CoverageError, "허용 목록"):
            self.validate_fixture()

    def test_pass_and_fail_require_evidence(self) -> None:
        """! @brief 완료 결과인 pass와 fail에 evidence가 없으면 거부합니다. """
        for state in ("pass", "fail"):
            with self.subTest(state=state):
                self.mutate_record(
                    "nrf.openthread-cli",
                    lambda record, state=state: record["validation"].update(
                        {"state": state, "evidence": []}
                    ),
                )
                with self.assertRaisesRegex(
                    M17.CoverageError,
                    rf"{state.upper()}에는 최소 한 개의 evidence",
                ):
                    self.validate_fixture()

    def test_planned_and_not_run_reject_evidence(self) -> None:
        """! @brief 미실행 상태인 planned와 not-run에는 evidence를 금지합니다. """
        for state in ("planned", "not-run"):
            with self.subTest(state=state):
                self.mutate_record(
                    "nrf.openthread-cli",
                    lambda record, state=state: record["validation"].update(
                        {
                            "state": state,
                            "evidence": ["tests/host/test_m17_coverage.py"],
                        }
                    ),
                )
                with self.assertRaisesRegex(
                    M17.CoverageError,
                    rf"{state} validation에는 evidence",
                ):
                    self.validate_fixture()

    def test_deferred_failure_is_valid_and_rendered(self) -> None:
        """! @brief deferred 실패는 gate를 막지 않고 evidence와 요약에 명시합니다. """
        self.mutate_record(
            "nrf.openthread-cli",
            lambda record: record["validation"].update(
                {
                    "state": "fail",
                    "evidence": ["tests/host/test_m17_coverage.py"],
                }
            ),
        )
        manifest, records = self.validate_fixture()
        summary = M17.build_summary(manifest, records)
        rendered = M17.render_markdown(summary)
        self.assertEqual(summary["counts"]["validation_state"]["fail"], 3)
        self.assertIn("**build-feasibility:fail**", rendered)

    def test_supported_failure_is_gate_failure(self) -> None:
        """! @brief supported 항목의 evidence가 있는 fail도 coverage gate를 실패시킵니다. """
        self.mutate_record(
            "board.system",
            lambda record: record["validation"].update(
                {
                    "state": "fail",
                    "evidence": ["tests/host/test_m17_coverage.py"],
                }
            ),
        )
        with self.assertRaisesRegex(M17.CoverageError, "supported validation FAIL"):
            self.validate_fixture()

    def test_build_only_failure_is_gate_failure(self) -> None:
        """! @brief build-only 항목의 evidence가 있는 fail은 coverage gate를 실패시킵니다. """
        self.mutate_record(
            "nrf.crypto-rng",
            lambda record: record["validation"].update(
                {
                    "state": "fail",
                    "evidence": ["tests/host/test_m17_coverage.py"],
                }
            ),
        )
        with self.assertRaisesRegex(M17.CoverageError, "build-only validation FAIL"):
            self.validate_fixture()

    def test_manifest_path_traversal_is_rejected(self) -> None:
        path = self.dataset_root / "manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["records"][0]["path"] = "../records/arduino.adafruit-lsm6ds.json"
        write_json(path, manifest)
        with self.assertRaisesRegex(M17.CoverageError, "안전하지 않은 상대 경로"):
            self.validate_fixture()

    def test_windows_drive_paths_are_rejected(self) -> None:
        """! @brief C:/·D:/와 drive-relative 경로를 상대 경로로 해석하지 않습니다. """
        for value in ("C:/escape.json", "D:/escape.json", "C:escape.json"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(M17.CoverageError, "Windows drive"):
                    M17._safe_relative_path(value, "fixture.path")

    def test_resolved_path_outside_root_is_rejected(self) -> None:
        """! @brief symlink 등으로 resolve 결과가 root 밖이면 fail-closed로 거부합니다. """
        root = Path(self.temporary.name) / "contained"
        root.mkdir()
        outside = Path(self.temporary.name) / "outside.json"
        outside.write_text("{}\n", encoding="utf-8")
        link = root / "link.json"
        try:
            link.symlink_to(outside)
        except OSError:
            with self.assertRaisesRegex(M17.CoverageError, "허용 root 밖"):
                M17._resolve_contained(root, "../outside.json", "fixture.path")
        else:
            with self.assertRaisesRegex(M17.CoverageError, "허용 root 밖"):
                M17._resolve_contained(root, "link.json", "fixture.path")

    def test_evidence_drive_path_is_rejected(self) -> None:
        """! @brief evidence에도 Windows absolute·drive-relative 경로를 허용하지 않습니다. """
        self.mutate_record(
            "nrf.openthread-cli",
            lambda record: record["validation"].update(
                {"state": "fail", "evidence": ["C:/outside/evidence.md"]}
            ),
        )
        with self.assertRaisesRegex(M17.CoverageError, "Windows drive"):
            self.validate_fixture()

    def test_manifest_revision_mismatch_is_rejected(self) -> None:
        path = self.dataset_root / "manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["pins"]["ncs"]["revision"] = "0" * 40
        write_json(path, manifest)
        with self.assertRaisesRegex(M17.CoverageError, "NCS lock과 다릅니다"):
            self.validate_fixture()

    def test_record_revision_mismatch_is_rejected(self) -> None:
        self.mutate_record(
            "zephyr.settings-storage",
            lambda record: record["source"].update({"revision": "0" * 40}),
        )
        with self.assertRaisesRegex(M17.CoverageError, "zephyr exact pin"):
            self.validate_fixture()

    def test_manifest_record_hash_mismatch_is_rejected(self) -> None:
        path = self.dataset_root / "records" / "nrf.crypto-rng.json"
        path.write_bytes(path.read_bytes() + b" ")
        with self.assertRaisesRegex(M17.CoverageError, "SHA-256 mismatch"):
            self.validate_fixture()

    def test_manifest_record_hash_accepts_git_crlf_checkout(self) -> None:
        """! @brief Git text 변환으로 생긴 CRLF가 LF 기준 record hash를 바꾸지 않습니다. """
        path = self.dataset_root / "records" / "arduino.adafruit-lsm6ds.json"
        lf_content = path.read_bytes().replace(b"\r\n", b"\n")
        path.write_bytes(lf_content.replace(b"\n", b"\r\n"))
        _, records = self.validate_fixture()
        self.assertIn("arduino.adafruit-lsm6ds", {record["id"] for record in records})

    def test_manifest_record_hash_rejects_content_change_with_crlf(self) -> None:
        """! @brief CRLF checkout에서도 실제 record 내용 변경은 SHA mismatch로 거부합니다. """
        path = self.dataset_root / "records" / "arduino.adafruit-lsm6ds.json"
        lf_content = path.read_bytes().replace(b"\r\n", b"\n")
        changed = lf_content.replace(b"external library compile", b"external library changed", 1)
        path.write_bytes(changed.replace(b"\n", b"\r\n"))
        with self.assertRaisesRegex(M17.CoverageError, "SHA-256 mismatch"):
            self.validate_fixture()

    def test_manifest_record_hash_rejects_bare_cr(self) -> None:
        """! @brief Git의 CRLF 변환이 아닌 단독 CR은 모호한 입력으로 거부합니다. """
        path = self.dataset_root / "records" / "arduino.adafruit-lsm6ds.json"
        content = path.read_bytes().replace(b"\r\n", b"\n")
        path.write_bytes(content.replace(b"\n", b"\r", 1))
        with self.assertRaisesRegex(M17.CoverageError, "단독 CR"):
            self.validate_fixture()

    def test_sensor_wrapper_is_rejected(self) -> None:
        self.mutate_record(
            "zephyr.sensor-direct",
            lambda record: record.update({"route": "arduino-wrapper"}),
        )
        with self.assertRaisesRegex(M17.CoverageError, "sensor wrapper"):
            self.validate_fixture()

    def test_networking_supported_promotion_is_rejected(self) -> None:
        self.mutate_record(
            "nrf.openthread-cli",
            lambda record: record.update({"status": "supported"}),
        )
        with self.assertRaisesRegex(M17.CoverageError, r"feasibility\+deferred"):
            self.validate_fixture()

    def test_external_source_requires_exact_commit(self) -> None:
        self.mutate_record(
            "arduino.adafruit-lsm6ds",
            lambda record: record["source"].update({"revision": "4.7.4"}),
        )
        with self.assertRaisesRegex(M17.CoverageError, "40자리 commit"):
            self.validate_fixture()

    def test_record_path_must_be_derived_from_id(self) -> None:
        path = self.dataset_root / "manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["records"][0]["path"] = "records/board.system.json"
        write_json(path, manifest)
        with self.assertRaisesRegex(M17.CoverageError, "id에서 정확히 유도"):
            self.validate_fixture()

    def test_fixture_validates_without_checkout_probe(self) -> None:
        _, records = self.validate_fixture()
        self.assertEqual(
            {record["id"] for record in records},
            M17.REQUIRED_RECORDS,
        )


if __name__ == "__main__":
    unittest.main()
