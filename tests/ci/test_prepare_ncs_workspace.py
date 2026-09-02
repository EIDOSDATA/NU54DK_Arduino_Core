#!/usr/bin/env python3
"""! @brief M12 exact NCS workspace bootstrap 계약을 검증합니다. """

from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest import mock


REPOSITORY = Path(__file__).resolve().parents[2]
MODULE_PATH = REPOSITORY / "tools" / "ci" / "prepare_ncs_workspace.py"
SPEC = importlib.util.spec_from_file_location("nu54_m12_workspace_test", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class PrepareNcsWorkspaceTests(unittest.TestCase):
    """! @brief raw commit을 branch처럼 취급하지 않는 bootstrap을 검사합니다. """

    ## @brief 빈 cache에서 exact commit fetch 뒤 local manifest로 west를 초기화합니다.
    def test_bootstrap_fetches_commit_before_local_west_init(self) -> None:
        lock = MODULE.LOCK_MODULE.strict_json_object(MODULE.LOCK_MODULE.LOCK_PATH)
        revision = lock["ncs"]["revision"]
        with tempfile.TemporaryDirectory() as temporary_name:
            workspace = Path(temporary_name) / "workspace"
            commands: list[tuple[tuple[str, ...], Path | None]] = []

            def fake_run(command, *, cwd=None):
                normalized = tuple(str(item) for item in command)
                commands.append((normalized, cwd))
                if normalized[:2] == ("git", "init"):
                    (workspace / "nrf" / ".git").mkdir(parents=True)
                if normalized[:3] == ("west", "init", "-l"):
                    (workspace / ".west").mkdir()
                if normalized[0].endswith("print_toolchain_checksum.sh"):
                    return lock["linux_toolchain_container"]["toolchain_id"]
                return ""

            with (
                mock.patch.object(MODULE, "run_checked", side_effect=fake_run),
                mock.patch.object(MODULE.LOCK_MODULE, "validate_workspace"),
            ):
                MODULE.prepare_workspace(workspace, lock)

        flattened = [command for command, _cwd in commands]
        self.assertIn(("git", "init", str(workspace / "nrf")), flattened)
        self.assertIn(
            ("git", "fetch", "--no-tags", "--depth=1", "origin", revision),
            flattened,
        )
        self.assertIn(("git", "checkout", "--detach", revision), flattened)
        self.assertIn(("west", "init", "-l", str(workspace / "nrf")), flattened)
        self.assertFalse(any("--mr" in command for command in flattened))


if __name__ == "__main__":
    unittest.main(verbosity=2)
