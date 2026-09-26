"""! @brief M8 debug 경로의 probe 비공개·unlock 차단 계약을 검사합니다. """

from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "tests" / "hil" / "nu54dk" / "m8_debug.py"
SPEC = importlib.util.spec_from_file_location("m8_debug_safety", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class M8DebugSafetyTests(unittest.TestCase):
    """! @brief debugserver의 비파괴 option과 evidence redaction을 검사합니다. """

    def test_probe_hash_is_case_normalized(self) -> None:
        """! @brief DAPLink UID의 대소문자 표기는 같은 공개 identity가 됩니다. """
        self.assertEqual(MODULE.probe_sha256("ABC123"), MODULE.probe_sha256("abc123"))

    def test_debugserver_log_redacts_raw_probe(self) -> None:
        """! @brief debugserver log에 raw UID를 남기지 않습니다. """
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "debugserver.log"
            log.write_text("probe=ABC123\nselected abc123\n", encoding="utf-8")
            MODULE.redact_probe_log(log, "AbC123")
            text = log.read_text(encoding="utf-8")
        self.assertNotIn("abc123", text.casefold())
        self.assertEqual(2, text.count("<redacted-probe-id>"))

    def test_debug_source_disables_auto_unlock_and_raw_evidence(self) -> None:
        """! @brief debug attach도 auto unlock을 끄고 hash만 기록합니다. """
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertIn('"-I",\n        "-m",\n        "pyocd"', source)
        self.assertIn('"gdbserver"', source)
        self.assertIn('"-Oauto_unlock=false"', source)
        self.assertNotIn('"west",', source)
        self.assertIn('"probe_sha256": hashed_probe', source)
        self.assertNotIn('"probe_id": args.probe_id', source)


if __name__ == "__main__":
    unittest.main()
