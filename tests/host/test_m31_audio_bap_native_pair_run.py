#!/usr/bin/env python3
"""! @brief M31 BAP pair 재시작의 익명 probe identity 계약을 검증합니다. """

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


REPOSITORY = Path(__file__).resolve().parents[2]
HIL = REPOSITORY / "tests" / "hil" / "nu54dk"
if str(HIL) not in sys.path:
    sys.path.insert(0, str(HIL))
RUNNER = HIL / "m31_audio_bap_native_pair_run.py"
SPEC = importlib.util.spec_from_file_location("m31_audio_bap_native_pair_run", RUNNER)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class M31AudioBapNativePairRunTests(unittest.TestCase):
    """! @brief raw UID 대신 CLI로 검증한 SHA-256만 reset helper에 전달함을 고정합니다. """

    def test_reset_pair_uses_server_then_client_probe_sha256(self) -> None:
        """! @brief 두 역할의 익명 identity와 reset 순서를 보존합니다. """

        client = "1" * 64
        server = "2" * 64
        with patch.object(MODULE, "hardware_reset") as reset:
            MODULE.reset_pair(client, server)
        self.assertEqual(
            [call.args[0] for call in reset.call_args_list],
            [server, client],
        )


if __name__ == "__main__":
    unittest.main()
