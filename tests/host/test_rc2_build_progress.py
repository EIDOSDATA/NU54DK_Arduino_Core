#!/usr/bin/env python3
"""! @brief RC2 build 진행률, log와 병렬 작업자 정책을 검증합니다. """

from __future__ import annotations

from contextlib import redirect_stderr
from io import StringIO
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest


MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "tools"
    / "nu54-builder"
    / "src"
    / "nu54_builder.py"
)
MODULE_SPEC = importlib.util.spec_from_file_location("nu54_builder_rc2_progress", MODULE_PATH)
if MODULE_SPEC is None or MODULE_SPEC.loader is None:
    raise RuntimeError(f"nu54-builder module을 불러올 수 없습니다: {MODULE_PATH}")
MODULE = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(MODULE)
PROGRESS = MODULE.implementation.progress


class Rc2BuildProgressTests(unittest.TestCase):
    """! @brief 작업자 계산과 진행 명령 계약을 검증합니다. """

    def test_worker_count_respects_cpu_memory_and_override(self) -> None:
        """! @brief 자동 작업자는 CPU/RAM 중 작은 값이며 override를 우선합니다. """

        self.assertEqual(
            PROGRESS.build_worker_count(cpu_count=16, memory_bytes=8 * 1024 ** 3),
            4,
        )
        self.assertEqual(
            PROGRESS.build_worker_count(
                cpu_count=2, memory_bytes=4 * 1024 ** 3, override="7"
            ),
            7,
        )
        with self.assertRaisesRegex(MODULE.AdapterError, "E_BUILD_JOBS"):
            PROGRESS.build_worker_count(override="0")

    def test_build_environment_isolated_and_utf8(self) -> None:
        """! @brief child 환경만 병렬화와 UTF-8 설정을 받는지 검증합니다. """

        source = {"PATH": "fixture"}
        result = PROGRESS.build_environment(source, 3)
        self.assertEqual(source, {"PATH": "fixture"})
        self.assertEqual(result["CMAKE_BUILD_PARALLEL_LEVEL"], "3")
        self.assertEqual(result["NINJA_STATUS"], "[%f/%t] ")
        self.assertEqual(result["PYTHONIOENCODING"], "utf-8")

    def test_progress_command_keeps_full_log_and_target_counts(self) -> None:
        """! @brief 압축 console과 별개로 전체 UTF-8 출력과 target 수를 보존합니다. """

        program = (
            "import time; "
            "print('[1/3] 첫 대상', flush=True); "
            "time.sleep(0.04); "
            "print('[2/3] 둘째 대상', flush=True); "
            "time.sleep(0.04); "
            "print('[3/3] 완료', flush=True)"
        )
        with tempfile.TemporaryDirectory(prefix="nu54-rc2-progress-") as directory:
            root = Path(directory)
            log = root / "logs" / "build.log"
            console = StringIO()
            with redirect_stderr(console):
                result = PROGRESS.run_progress_command(
                    (sys.executable, "-c", program),
                    cwd=root,
                    environment=dict(os.environ, PYTHONIOENCODING="utf-8"),
                    log_path=log,
                    stage="시험 build",
                    worker_count=2,
                    heartbeat_seconds=0.01,
                )
            content = log.read_text(encoding="utf-8")
            self.assertEqual(result.completed_targets, 3)
            self.assertEqual(result.total_targets, 3)
            self.assertEqual(result.worker_count, 2)
            self.assertIn("첫 대상", content)
            self.assertIn("둘째 대상", content)
            self.assertIn("완료", content)
            self.assertIn("시험 build", console.getvalue())


if __name__ == "__main__":
    unittest.main()
