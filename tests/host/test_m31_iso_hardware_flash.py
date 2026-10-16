#!/usr/bin/env python3
"""! @brief M31 ISO의 sector programming과 비파괴 hardware reset 분리를 검증합니다. """

from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import patch


HIL = Path(__file__).resolve().parents[1] / "hil" / "nu54dk"
if str(HIL) not in sys.path:
    sys.path.insert(0, str(HIL))

import ble_pair_hil_common as common  # noqa: E402
import m31_iso_combined as combined  # noqa: E402


class M31IsoHardwareFlashTests(unittest.TestCase):
    """! @brief flash 완료와 app 재시작을 서로 독립적인 성공 조건으로 검사합니다. """

    def test_legacy_uid_flash_delegates_to_hash_only_backend(self) -> None:
        """! @brief legacy UID가 외부 argv 없이 hash-only backend로 전달되는지 확인합니다. """
        with patch.object(common, "probe_sha256", return_value="b" * 64), \
                patch.object(
                    common,
                    "flash_image_pyocd_sha256",
                    return_value=("pyocd-sector-sw-reset", "274432"),
                ) as flash:
            mode, byte_count = common.flash_image_pyocd(
                "central", "a" * 32, Path("image.hex"), 120.0, hardware_reset=True
            )
        self.assertEqual(("pyocd-sector-sw-reset", "274432"), (mode, byte_count))
        flash.assert_called_once_with(
            "central", "b" * 64, Path("image.hex"), 120.0, defer_reset=False
        )

    def test_programming_does_not_hide_backend_failure(self) -> None:
        """! @brief hash-only backend 실패를 legacy HIL PASS로 올리지 않습니다. """
        with patch.object(common, "probe_sha256", return_value="b" * 64), \
                patch.object(
                    common,
                    "flash_image_pyocd_sha256",
                    side_effect=common.BlePairHilFailure("software reset 실패"),
                ):
            with self.assertRaisesRegex(common.BlePairHilFailure, "software reset 실패"):
                common.flash_image_pyocd(
                    "central", "a" * 32, Path("image.hex"), 120.0, hardware_reset=True
                )

    def test_m32_access_preserving_flash_uses_software_reset_backend(self) -> None:
        """! @brief M32 경로도 hash-only software reset backend를 사용합니다. """
        with patch.object(common, "probe_sha256", return_value="b" * 64), \
                patch.object(
                    common,
                    "flash_image_pyocd_sha256",
                    return_value=("pyocd-sector-sw-reset", "274432"),
                ) as flash:
            mode, byte_count = common.flash_image_pyocd(
                "capability",
                "a" * 32,
                Path("image.hex"),
                120.0,
                hardware_reset=True,
                preserve_nrf54l_access=True,
            )
        self.assertEqual(("pyocd-sector-sw-reset", "274432"), (mode, byte_count))
        flash.assert_called_once_with(
            "capability", "b" * 64, Path("image.hex"), 120.0, defer_reset=False
        )

    def test_combined_exact_requires_software_reset_evidence(self) -> None:
        """! @brief 결합 HIL 완료 승격에서 명시적 software reset 근거를 요구합니다. """
        identity = combined.ExpectedIdentity("a" * 40, "b" * 40, "c" * 40, "d" * 40)
        images = {"peer": "1" * 64, "combined": "2" * 64, "receiver": "3" * 64}
        envelope = {
            "source_clean": True,
            "test_id": "M31-ISO-01:bis_cis_combined",
            "cycles": 20,
            "identity": vars(identity),
            "boards": {
                role: {
                    "image_sha256": images[role],
                    "probe_sha256": str(index) * 64,
                    "flash_mode": "pyocd-sector-sw-reset",
                }
                for index, role in enumerate(images, 4)
            },
            "transcript": b"validated-by-parser",
            "nonces": ["0" * 32] * 20,
        }
        marker = object()
        with patch.object(combined, "parse_combined_transcript", return_value=marker):
            self.assertIs(marker, combined.validate_combined_envelope(envelope, images, identity))
            envelope["boards"]["combined"]["flash_mode"] = "pyocd-sector"
            with self.assertRaisesRegex(combined.M31CombinedFailure, "sector flash"):
                combined.validate_combined_envelope(envelope, images, identity)


if __name__ == "__main__":
    unittest.main()
