#!/usr/bin/env python3
"""! @brief M22 고정 gate의 명령 allowlist와 UID redaction을 검증합니다. """

from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest


REPOSITORY = Path(__file__).resolve().parents[2]
PATH = REPOSITORY / "tools" / "release" / "run_m22_fixed_gate.py"
SPEC = importlib.util.spec_from_file_location("run_m22_fixed_gate", PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"M22 fixed gate를 읽지 못했습니다: {PATH}")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class M22FixedGateTests(unittest.TestCase):
    """! @brief host/example/upload 명령이 고정 구조인지 확인합니다. """

    def parser(self, *values: str):
        """! @brief 공통 evidence/log 인자를 포함한 parser 결과를 만듭니다. """

        return MODULE.build_parser().parse_args(
            [*values, "--evidence", "evidence.json", "--log", "gate.log"]
        )

    def test_host_gate_is_exact_unittest_discovery(self) -> None:
        """! @brief host gate가 임의 test command를 받지 않습니다. """

        command = MODULE.fixed_command(self.parser("host"))
        self.assertEqual(command[1:4], ["-m", "unittest", "discover"])
        self.assertEqual(command[-2:], ["-p", "test_*.py"])

    def test_package_examples_delegates_all_isolated_roots(self) -> None:
        """! @brief 설치본 예제 gate에 SDK/toolchain/cache/forbid root를 모두 넘깁니다. """

        args = self.parser(
            "package-examples",
            "--arduino-cli", "cli.exe",
            "--config", "config.yaml",
            "--platform-root", "platform",
            "--build-root", "build",
            "--ncs-root", "ncs",
            "--toolchain-root", "toolchain",
            "--cache-root", "cache",
            "--detail-evidence", "examples.json",
            "--forbid-root", r"C:\ncs",
        )
        command = MODULE.fixed_command(args)
        self.assertIn("run_m22_package_examples.py", command[1])
        for flag in ("--platform-root", "--ncs-root", "--toolchain-root", "--cache-root", "--forbid-root"):
            self.assertIn(flag, command)

    def test_rc_upload_requires_exact_uid_but_redacts_it(self) -> None:
        """! @brief RC upload는 pyOCD 1회와 UID를 강제하되 공개 문구에서 지웁니다. """

        uid = "0123456789ABCDEF"
        args = self.parser(
            "rc-upload",
            "--arduino-cli", "cli.exe",
            "--workspace", "workspace",
            "--platform-root", "platform",
            "--core-revision", "a" * 40,
            "--runtime-payload-sha256", "b" * 64,
            "--probe-id", uid,
        )
        command = MODULE.fixed_command(args)
        self.assertEqual(command[command.index("--repetitions") + 1], "1")
        self.assertEqual(command[command.index("--runner") + 1], "pyocd")
        self.assertIn(uid, command)
        self.assertNotIn(uid, MODULE.redact_text(f"probe={uid}", (uid,)))

    def test_rc_upload_without_uid_fails_closed(self) -> None:
        """! @brief 다중 probe 환경에서 암묵 선택을 허용하지 않습니다. """

        args = self.parser(
            "rc-upload",
            "--arduino-cli", "cli.exe",
            "--workspace", "workspace",
            "--platform-root", "platform",
            "--core-revision", "a" * 40,
            "--runtime-payload-sha256", "b" * 64,
        )
        with self.assertRaisesRegex(MODULE.M22GateFailure, "probe UID"):
            MODULE.fixed_command(args)


if __name__ == "__main__":
    unittest.main()
