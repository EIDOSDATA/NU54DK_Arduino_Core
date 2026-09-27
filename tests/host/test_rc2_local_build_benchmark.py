#!/usr/bin/env python3
"""! @brief RC2 로컬 성능 계측기의 secure DFU key 경계를 검사합니다. """

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "tools" / "ci" / "rc2_local_build_benchmark.py"
SPEC = importlib.util.spec_from_file_location("rc2_local_build_benchmark", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class Rc2LocalBuildBenchmarkTests(unittest.TestCase):
    """! @brief private key가 workspace 밖에 생기거나 재사용되지 않게 검사합니다. """

    def test_ephemeral_key_is_created_inside_workspace(self) -> None:
        """! @brief 명시 OpenSSL만 사용해 격리 경로에 새 P-256 key를 생성합니다. """

        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            openssl = workspace / "openssl.exe"
            openssl.write_bytes(b"fixture")

            def run_stub(command, **_arguments):
                key = Path(command[-1])
                key.write_text("fixture-key", encoding="ascii")
                return SimpleNamespace(returncode=0)

            with mock.patch.object(MODULE.subprocess, "run", side_effect=run_stub) as invoked:
                key = MODULE.create_ephemeral_signing_key(workspace, openssl)
        self.assertEqual("ephemeral-ecdsa-p256.pem", key.name)
        self.assertIn("private", key.parts)
        command = invoked.call_args.args[0]
        self.assertIn("prime256v1", command)
        self.assertEqual(key, Path(command[-1]))

    def test_missing_openssl_is_rejected_before_key_creation(self) -> None:
        """! @brief 존재하지 않는 OpenSSL 경로를 host fallback으로 바꾸지 않습니다. """

        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            with self.assertRaisesRegex(MODULE.Rc2BenchmarkFailure, "OpenSSL"):
                MODULE.create_ephemeral_signing_key(workspace, workspace / "missing.exe")
        self.assertFalse((workspace / "private").exists())


if __name__ == "__main__":
    unittest.main()
