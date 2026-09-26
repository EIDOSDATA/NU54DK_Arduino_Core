"""! @brief adaptive unicast source의 재연결 scan API 계약을 고정합니다. """

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
DECLARED_SOURCES = (
    ("BapUnicastSource", "ble-audio-unicast-source"),
    ("BapUnicastCycle", "ble-audio-unicast-cycle"),
    ("BapUnicastDuplexClient", "ble-audio-unicast-duplex-client"),
    ("CapUnicastInitiator", "ble-audio-cap-unicast-initiator"),
)
EXAMPLES = ROOT / "libraries/NUCODE_BLE_Audio/examples"
TEST_SOURCE = ROOT / "tests/arduino-cli/p2_audio_unicast_source/p2_audio_unicast_source.ino"
EXTERNAL_SOURCE = EXAMPLES / "ExternalI2sSpeakerSink/ExternalI2sSpeakerSink.ino"


class P2AudioUnicastAdaptiveScanTests(unittest.TestCase):
    """! @brief EXT_ADV가 없는 역할에서도 초기·재연결 scan을 유지합니다. """

    def test_declared_sources_reuse_legacy_scan_for_reconnect(self) -> None:
        """! @brief 선언된 source의 역할과 재연결 scan 조건을 대조합니다. """

        for name, expected_role in DECLARED_SOURCES:
            path = EXAMPLES / name / f"{name}.ino"
            with self.subTest(path=path):
                source = path.read_text(encoding="utf-8")
                role = json.loads(path.with_name("nucode-build.json").read_text(
                    encoding="utf-8"
                ))["roles"]
                self.assertEqual(role, [expected_role])
                self.assertIn(
                    "if (!BLEScan.running() && !BLEScan.start(true))", source
                )
                self.assertGreaterEqual(source.count("BLEScan.start(true)"), 2)
                self.assertNotIn("BLEScan.startExtended(", source)

    def test_hil_source_reuses_legacy_scan_for_reconnect(self) -> None:
        """! @brief HIL source에도 동일한 공개 scan 경로를 요구합니다. """

        source = TEST_SOURCE.read_text(encoding="utf-8")
        self.assertIn("if (!BLEScan.running() && !BLEScan.start(true))", source)
        self.assertGreaterEqual(source.count("BLEScan.start(true)"), 2)
        self.assertNotIn("BLEScan.startExtended(", source)

    def test_external_i2s_example_does_not_require_extended_scan(self) -> None:
        """! @brief 외장 I2S 예제의 재연결도 일반 scan을 유지합니다. """

        source = EXTERNAL_SOURCE.read_text(encoding="utf-8")
        self.assertIn("if (!BLEScan.running())", source)
        self.assertIn("static_cast<void>(BLEScan.start(true));", source)
        self.assertNotIn("BLEScan.startExtended(", source)


if __name__ == "__main__":
    unittest.main()
