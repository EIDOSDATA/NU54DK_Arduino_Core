#!/usr/bin/env python3
"""! @brief 생성기의 자체 기대값과 별개로 drift·비결정성·경로 실패를 주입합니다. """
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("r13_generated", ROOT / "tools/peripheral/verify_generated.py")
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class GeneratedContractTests(unittest.TestCase):
    """! @brief 원본 생성기를 호출하지 않는 독립 byte oracle와 부정 사례입니다. """

    def test_nondeterministic_or_omitted_generation_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for first, second in [({}, {}), ({"a": "one"}, {"a": "two"}), ({"a": "one"}, {})]:
                with self.subTest(first=first, second=second), self.assertRaises(MODULE.GenerationFailure):
                    MODULE.verify_outputs(first, second, root)

    def test_changed_missing_or_outside_output_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "known.txt").write_text("independent oracle\n")
            for output in [{"known.txt": "changed\n"}, {"missing.txt": "absent\n"}, {"../outside.txt": "escape\n"}]:
                with self.subTest(output=output), self.assertRaises(MODULE.GenerationFailure):
                    MODULE.verify_outputs(output, output, root)

    def test_checkout_crlf_preserves_utf8_lf_contract(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "known.txt").write_bytes(b"independent oracle\r\n")
            output = {"known.txt": "independent oracle\n"}
            records = MODULE.verify_outputs(output, output, root)
            self.assertEqual(records["known.txt"]["bytes_utf8_lf"], 19)


if __name__ == "__main__":
    unittest.main(verbosity=2)
