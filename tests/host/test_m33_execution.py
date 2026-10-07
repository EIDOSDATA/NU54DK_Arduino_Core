#!/usr/bin/env python3
"""! @brief W06 공통 단계 기록의 중단·재개·손상·이동 계약을 검증합니다. """
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/bluetooth"))
import m33_execution as execution


class ExecutionJournalTests(unittest.TestCase):
    """! @brief 실제 파일과 OS lock을 사용해 완료 증거의 부당 승계를 거부합니다. """

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.calls = []
        self.identity = {"source_revision": "a" * 40, "image_sha256": "b" * 64}

    def execute(self, attempt: Path) -> list[Path]:
        """! @brief 작은 실제 출력 파일을 쓰는 보드 없는 단계입니다. """

        self.calls.append(attempt)
        path = attempt / "output.bin"
        execution.write_new_bytes(path, b"verified bytes")
        return [path]

    def validate(self, attempt: Path) -> None:
        """! @brief file hash 외의 의미 검사 호출도 재개 때 유지합니다. """

        self.assertEqual(b"verified bytes", (attempt / "output.bin").read_bytes())

    def test_atomic_publish_never_overwrites(self) -> None:
        path = self.root / "result.json"
        execution.write_new_json(path, {"status": "PASS"})
        original = path.read_bytes()
        with self.assertRaises(execution.ExecutionFailure):
            execution.write_new_json(path, {"status": "FAIL"})
        self.assertEqual(original, path.read_bytes())

    def test_interruption_before_publish_leaves_no_result(self) -> None:
        path = self.root / "result.json"
        with mock.patch.object(execution.os, "link", side_effect=KeyboardInterrupt), \
                self.assertRaises(KeyboardInterrupt):
            execution.write_new_json(path, {"status": "PASS"})
        self.assertFalse(path.exists())

    def test_competing_writer_is_not_overwritten(self) -> None:
        path = self.root / "result.json"
        original_link = execution.os.link

        def race(source, destination):
            destination.write_bytes(b"competing writer")
            original_link(source, destination)

        with mock.patch.object(execution.os, "link", side_effect=race), \
                self.assertRaises(FileExistsError):
            execution.write_new_json(path, {"status": "PASS"})
        self.assertEqual(b"competing writer", path.read_bytes())

    def test_duplicate_or_partial_json_is_rejected(self) -> None:
        path = self.root / "result.json"
        for raw in ('{"status":"FAIL","status":"PASS"}', '{"status":'):
            with self.subTest(raw=raw):
                path.write_text(raw, encoding="utf-8")
                with self.assertRaises(execution.ExecutionFailure):
                    execution.read_json(path)

    def test_completed_stage_is_revalidated_without_execution(self) -> None:
        journal = execution.StageJournal(self.root, self.identity)
        first = journal.run("build", {}, self.execute, self.validate)
        with mock.patch.object(self, "validate", wraps=self.validate) as validate:
            second = journal.run("build", {}, self.execute, validate)
        self.assertEqual(first, second)
        self.assertEqual(1, len(self.calls))
        validate.assert_called_once_with(first)

    def test_failed_stage_uses_new_attempt_and_preserves_failure(self) -> None:
        journal = execution.StageJournal(self.root, self.identity)

        def fail(attempt):
            execution.write_new_bytes(attempt / "stderr.log", b"specific failure")
            raise execution.ExecutionFailure("TRANSPORT", "transport failure")

        with self.assertRaises(execution.ExecutionFailure):
            journal.run("prepare", {}, fail, self.validate)
        failed = self.root / "prepare/attempt-0001"
        first = (failed / "failure.json").read_bytes()
        completed = journal.run("prepare", {}, self.execute, self.validate)
        self.assertEqual("attempt-0002", completed.name)
        self.assertEqual(first, (failed / "failure.json").read_bytes())
        self.assertEqual(b"specific failure", (failed / "stderr.log").read_bytes())

    def test_keyboard_interrupt_is_recorded_not_passed(self) -> None:
        journal = execution.StageJournal(self.root, self.identity)
        with self.assertRaises(KeyboardInterrupt):
            journal.run("prepare", {}, mock.Mock(side_effect=KeyboardInterrupt), self.validate)
        failed = self.root / "prepare/attempt-0001"
        self.assertEqual("INTERRUPTED", execution.read_json(failed / "failure.json")["category"])
        self.assertFalse((failed / "complete.json").exists())

    def test_corrupt_completed_output_never_retries(self) -> None:
        journal = execution.StageJournal(self.root, self.identity)
        completed = journal.run("build", {}, self.execute, self.validate)
        (completed / "output.bin").write_bytes(b"tampered")
        with self.assertRaisesRegex(execution.ExecutionFailure, "byte/hash drift"):
            journal.run("build", {}, self.execute, self.validate)
        self.assertEqual(1, len(self.calls))

    def test_changed_session_is_rejected(self) -> None:
        execution.StageJournal(self.root, self.identity)
        with self.assertRaisesRegex(execution.ExecutionFailure, "session/input drift"):
            execution.StageJournal(self.root, {**self.identity, "image_sha256": "c" * 64})

    def test_changed_step_inputs_are_rejected(self) -> None:
        journal = execution.StageJournal(self.root, self.identity)
        journal.run("build", {"role": "client"}, self.execute, self.validate)
        with self.assertRaisesRegex(execution.ExecutionFailure, "input drift"):
            journal.run("build", {"role": "peer"}, self.execute, self.validate)

    def test_attempt_gap_is_rejected(self) -> None:
        journal = execution.StageJournal(self.root, self.identity)
        (self.root / "build/attempt-0002").mkdir(parents=True)
        with self.assertRaisesRegex(execution.ExecutionFailure, "sequence"):
            journal.run("build", {}, self.execute, self.validate)

    def test_empty_interrupted_attempt_can_resume(self) -> None:
        journal = execution.StageJournal(self.root, self.identity)
        (self.root / "build/attempt-0001").mkdir(parents=True)
        completed = journal.run("build", {}, self.execute, self.validate)
        self.assertEqual("attempt-0002", completed.name)

    def test_data_without_request_is_rejected(self) -> None:
        journal = execution.StageJournal(self.root, self.identity)
        attempt = self.root / "build/attempt-0001"
        attempt.mkdir(parents=True)
        (attempt / "output.bin").write_bytes(b"unbound data")
        with self.assertRaisesRegex(execution.ExecutionFailure, "without request"):
            journal.run("build", {}, self.execute, self.validate)

    def test_attempt_after_completed_is_rejected(self) -> None:
        journal = execution.StageJournal(self.root, self.identity)
        journal.run("build", {}, self.execute, self.validate)
        (self.root / "build/attempt-0002").mkdir()
        with self.assertRaisesRegex(execution.ExecutionFailure, "follow completion"):
            journal.run("build", {}, self.execute, self.validate)

    def test_integrity_and_safety_failures_block_automatic_resume(self) -> None:
        for category in ("INTEGRITY", "SAFETY"):
            with self.subTest(category=category):
                journal = execution.StageJournal(self.root / category, self.identity)
                with self.assertRaises(execution.ExecutionFailure):
                    journal.run("prepare", {}, mock.Mock(side_effect=
                                execution.ExecutionFailure(category, "must investigate")), self.validate)
                with self.assertRaisesRegex(execution.ExecutionFailure, "investigation"):
                    journal.run("prepare", {}, self.execute, self.validate)
        self.assertEqual([], self.calls)

    def test_relative_receipts_survive_location_move(self) -> None:
        journal = execution.StageJournal(self.root / "old", self.identity)
        journal.run("build", {}, self.execute, self.validate)
        shutil.move(str(self.root / "old"), str(self.root / "new"))
        moved = execution.StageJournal(self.root / "new", self.identity)
        moved.run("build", {}, self.execute, self.validate)
        self.assertEqual(1, len(self.calls))

    def test_reference_path_escape_is_rejected(self) -> None:
        for path in ("../outside", "/outside", "C:/outside", "folder\\outside", "a//b"):
            with self.subTest(path=path), self.assertRaises(execution.ExecutionFailure):
                execution.validate_references(self.root, [{"path": path, "bytes": 0, "sha256": "a" * 64}])

    def test_symlink_receipt_is_rejected(self) -> None:
        source = self.root / "source.bin"
        source.write_bytes(b"source")
        link = self.root / "link.bin"
        try:
            link.symlink_to(source)
        except OSError as error:
            self.skipTest(str(error))
        with self.assertRaises(execution.ExecutionFailure):
            execution.references(self.root, [link])

    def test_lock_is_released_and_excludes_second_process(self) -> None:
        script = (
            "import sys; from pathlib import Path; "
            f"sys.path.insert(0, {str(ROOT / 'tools/bluetooth')!r}); "
            "import m33_execution as e; "
            f"scope=e.exclusive(Path({str(self.root)!r})); scope.__enter__()"
        )
        with execution.exclusive(self.root):
            result = subprocess.run([sys.executable, "-B", "-c", script],
                                    capture_output=True, timeout=15, check=False)
        self.assertNotEqual(0, result.returncode)
        with execution.exclusive(self.root):
            pass

    def test_failure_does_not_serialize_exception_message(self) -> None:
        record = execution.failure_record(ValueError("private raw probe identity"))
        self.assertEqual("INTERNAL", record["category"])
        self.assertNotIn("private", json.dumps(record))

    def test_legacy_validator_failure_is_not_retryable(self) -> None:
        journal = execution.StageJournal(self.root, self.identity)
        with self.assertRaises(execution.ExecutionFailure):
            journal.run("build", {}, self.execute,
                        mock.Mock(side_effect=ValueError("invalid manifest")))
        failure = execution.read_json(self.root / "build/attempt-0001/failure.json")
        self.assertEqual("INTEGRITY", failure["category"])
        with self.assertRaisesRegex(execution.ExecutionFailure, "investigation"):
            journal.run("build", {}, self.execute, self.validate)
        self.assertEqual(1, len(self.calls))


if __name__ == "__main__":
    unittest.main()
