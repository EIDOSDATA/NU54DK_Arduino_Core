#!/usr/bin/env python3
"""! @brief 외부 PDM/I2S BLE Audio 구현과 profile 계약을 검증합니다. """

from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
BUILDER_PATH = ROOT / "tools" / "nu54-builder" / "src" / "nu54_builder.py"
SPEC = importlib.util.spec_from_file_location("nu54_builder_external_audio", BUILDER_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Builder를 불러올 수 없습니다: {BUILDER_PATH}")
BUILDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILDER)

EXAMPLES = ROOT / "libraries" / "NUCODE_BLE_Audio" / "examples"


class M31ExternalAudioIoTests(unittest.TestCase):
    """! @brief 외부 audio profile·예제·배선 안내를 확인합니다. """

    def test_profile_combines_only_ble_and_peripheral_fabric(self) -> None:
        """! @brief opt-in profile이 BLE와 Fabric을 명시적으로 결합합니다. """
        profile = BUILDER.load_configuration_profile(ROOT, "ble_audio_io")
        self.assertEqual(
            profile["features"], ["gpio", "time", "ble", "peripheral_fabric"]
        )
        self.assertEqual(
            profile["requires_hil"], ["ble", "stream_fabric", "external_audio_io"]
        )
        resolved = BUILDER.resolve_library_features(
            ROOT, profile, ["NUCODE_BLE", "NUCODE_BLE_Audio", "NUCODE_Peripheral_Fabric"]
        )
        self.assertEqual(
            {item["id"] for item in resolved},
            {"nucode.ble.nus", "nucode.ble.audio", "nucode.peripheral.fabric"},
        )

    def test_profile_disables_conflicting_singletons_and_dap_uart(self) -> None:
        """! @brief 직접 IRQ 소유권과 P1.4~P1.7 조건을 fail-closed로 고정합니다. """
        profile = ROOT / "variants" / "nu54dk" / "profiles" / "ble_audio_io"
        configuration = (profile / "prj.conf").read_text(encoding="utf-8")
        for symbol in ("SERIAL", "SERIAL1", "INTERRUPTS", "WIRE", "SPI", "ADC", "PWM"):
            self.assertIn(f"CONFIG_NUCODE_ARDUINO_{symbol}=n", configuration)
        self.assertIn("CONFIG_NUCODE_ARDUINO_DAP_UART_GPIO_PINS=y", configuration)
        overlay = (profile / "app.overlay").read_text(encoding="utf-8")
        self.assertIn("/delete-property/ zephyr,console;", overlay)
        for pin in range(4, 8):
            self.assertIn(f"&arduino_p1_{pin:02d}", overlay)

    def test_public_examples_use_nucode_api_and_real_dma_buffers(self) -> None:
        """! @brief 공개 sketch가 PDM→LC3와 LC3→I2S data path를 구성합니다. """
        microphone = (EXAMPLES / "ExternalPdmMicrophoneSource" / "ExternalPdmMicrophoneSource.ino").read_text(
            encoding="utf-8"
        )
        speaker = (EXAMPLES / "ExternalI2sSpeakerSink" / "ExternalI2sSpeakerSink.ino").read_text(
            encoding="utf-8"
        )
        for source in (microphone, speaker):
            self.assertIn("#include <NUCODE_BLE_Audio.h>", source)
            self.assertIn("#include <NUCODE_Peripheral_Fabric.h>", source)
            self.assertNotIn("#include <zephyr/", source)
            self.assertNotIn("bt_", source)
        for token in (
            "PdmConfiguration",
            "microphone->start(",
            "microphone->queueBuffer(",
            "codec.encode(",
            "audioServer.sendFrame(",
        ):
            self.assertIn(token, microphone)
        for token in (
            "I2sConfiguration",
            "speaker->start(",
            "speaker->queueBuffers(",
            "audioClient.readFrame(",
            "codec.decode(",
        ):
            self.assertIn(token, speaker)

    def test_connection_guide_preserves_physical_not_run_boundary(self) -> None:
        """! @brief 전압·배선·profile·실물 검증 경계가 사용자 안내에 있습니다. """
        guide = (EXAMPLES / "README.md").read_text(encoding="utf-8")
        for token in (
            "external I/O (DAP UART disconnected)",
            "P1.4",
            "P1.5",
            "P1.6",
            "P1.7",
            "16 kHz",
            "16-bit stereo",
            "MCLK",
            "실물 검증",
        ):
            self.assertIn(token, guide)


if __name__ == "__main__":
    unittest.main()
