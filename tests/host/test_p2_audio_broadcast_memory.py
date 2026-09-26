"""P2 암호화 Audio 방송 부하 인자 계약을 검사합니다."""

import argparse
import importlib.util
from pathlib import Path
import sys
import unittest


REPOSITORY = Path(__file__).resolve().parents[2]
HIL_DIRECTORY = REPOSITORY / "tests" / "hil" / "nu54dk"
sys.path.insert(0, str(HIL_DIRECTORY))
SPEC = importlib.util.spec_from_file_location(
    "p2_audio_broadcast_memory_run",
    HIL_DIRECTORY / "p2_audio_broadcast_memory_run.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class BroadcastLoadArgumentsTest(unittest.TestCase):
    """부적절한 부하 요청은 probe 접근 전에 거부합니다."""

    def test_frame_target_must_be_positive_hundred_multiple(self):
        """UART의 100-frame 집계 경계와 다른 목표를 거부합니다."""
        for frames in (0, -100, 150):
            with self.subTest(frames=frames):
                with self.assertRaisesRegex(ValueError, "--frames"):
                    MODULE.run(argparse.Namespace(frames=frames, timeout=180))

    def test_timeout_must_be_positive(self):
        """무한 또는 즉시 만료되는 실행은 허용하지 않습니다."""
        for timeout in (0, -1):
            with self.subTest(timeout=timeout):
                with self.assertRaisesRegex(ValueError, "--timeout"):
                    MODULE.run(argparse.Namespace(frames=1000, timeout=timeout))


if __name__ == "__main__":
    unittest.main()
