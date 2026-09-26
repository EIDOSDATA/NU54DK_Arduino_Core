"""! @brief P2 Audio 장기 부하 인자의 fail-closed 경계를 검증합니다. """

import argparse
from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hil" / "nu54dk"))
from p2_audio_unicast_memory_run import run


class AudioLoadArgumentsTest(unittest.TestCase):
    """! @brief 실기 접근 전에 잘못된 부하 분모를 거부합니다. """

    def test_frame_target_must_match_report_stride(self):
        """! @brief 100 frame 단위가 아닌 목표를 거부합니다. """

        with self.assertRaises(ValueError):
            run(argparse.Namespace(frame_target=101, timeout=120.0))

    def test_timeout_must_be_positive(self):
        """! @brief 양수가 아닌 시간 제한을 거부합니다. """

        with self.assertRaises(ValueError):
            run(argparse.Namespace(frame_target=1000, timeout=0.0))


if __name__ == "__main__":
    unittest.main()
