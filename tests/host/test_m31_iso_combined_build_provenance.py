#!/usr/bin/env python3
"""! @brief M31 combined CIS/BIS 역할별 build provenance 결합을 검증합니다. """

from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
HIL = ROOT / "tests/hil/nu54dk"
if str(HIL) not in sys.path:
    sys.path.insert(0, str(HIL))

import m31_iso_combined_run as combined  # noqa: E402
import m33_sdk_risk_common as common  # noqa: E402


ROLES = ("peer", "combined", "receiver")
APPLICATION_NAMES = {
    "peer": "m31_iso_cis_hil",
    "combined": "m31_iso_combined_hil",
    "receiver": "m31_iso_bis_hil",
}


class CombinedBuildProvenanceTests(unittest.TestCase):
    """! @brief 역할별 source root와 image 교환 거부를 검사합니다. """

    def inputs(self, root: Path) -> dict[str, Path]:
        """! @brief 역할 식별 byte를 가진 합성 image를 만듭니다. """

        images = {}
        for index, role in enumerate(ROLES, 1):
            path = root / f"{role}.hex"
            path.write_bytes(bytes((index,)) * 32)
            images[role] = path
        return images

    def prepare(
        self,
        root: Path,
        images: dict[str, Path],
        application_roots: dict[str, Path],
    ) -> dict[str, dict[str, str]]:
        """! @brief 실제 router를 사용하되 filesystem sidecar만 격리합니다. """

        records = {
            role: {"record_sha256": hashlib.sha256((role + "-record").encode()).hexdigest()}
            for role in ROLES
        }

        def validate(image: Path, _core: str, _board: str, application: Path) -> dict[str, str]:
            role = image.stem
            if role not in APPLICATION_NAMES or application.name != APPLICATION_NAMES[role]:
                raise ValueError("application_source_sha256 mismatch")
            return records[role]

        sidecars = {
            role: {
                "image": root / f"{role}.image.hex",
                "build_record": root / f"{role}.build-record",
                "readback": root / f"{role}.readback.json",
            }
            for role in ROLES
        }
        copied = {
            role: {
                "image_sha256": hashlib.sha256(images[role].read_bytes()).hexdigest(),
                "build_record_sha256": records[images[role].stem]["record_sha256"],
            }
            for role in ROLES
        }
        with mock.patch.object(common, "validate_build_record", side_effect=validate), \
                mock.patch.object(common, "reserve_sidecars", return_value=sidecars), \
                mock.patch.object(common, "copy_program_inputs", return_value=copied):
            _sidecars, result = common.prepare_direct_program(
                root / "native.json",
                ROLES,
                images,
                "1" * 40,
                "2" * 40,
                application_roots,
            )
        return result

    def test_combined_runner_declares_exact_role_roots(self) -> None:
        """! @brief peer/combined/receiver가 실제 CIS/combined/BIS app에 각각 결합됩니다. """

        self.assertEqual(set(combined.APPLICATION_ROOTS), set(ROLES))
        self.assertEqual(
            {role: path.name for role, path in combined.APPLICATION_ROOTS.items()},
            APPLICATION_NAMES,
        )

    def test_correct_role_roots_are_accepted(self) -> None:
        """! @brief 세 image가 자기 application build record로 검증됩니다. """

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            records = self.prepare(root, self.inputs(root), combined.APPLICATION_ROOTS)
            self.assertEqual(set(records), set(ROLES))

    def test_wrong_application_root_is_rejected(self) -> None:
        """! @brief 단일 combined root를 세 역할에 재사용하는 과거 오류를 거부합니다. """

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            wrong = {role: combined.APPLICATION_ROOTS["combined"] for role in ROLES}
            with self.assertRaisesRegex(ValueError, "application_source_sha256"):
                self.prepare(root, self.inputs(root), wrong)

    def test_role_image_record_exchange_is_rejected(self) -> None:
        """! @brief peer와 receiver image/build record를 바꿔 끼우면 거부합니다. """

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            images = self.inputs(root)
            images["peer"], images["receiver"] = images["receiver"], images["peer"]
            with self.assertRaisesRegex(ValueError, "application_source_sha256"):
                self.prepare(root, images, combined.APPLICATION_ROOTS)

    def test_partial_role_root_mapping_is_rejected(self) -> None:
        """! @brief application root mapping에서 한 역할이 빠지면 검증 전에 실패합니다. """

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mapping = dict(combined.APPLICATION_ROOTS)
            mapping.pop("receiver")
            with self.assertRaisesRegex(common.ExactProgrammingFailure, "application role"):
                common.prepare_direct_program(
                    root / "native.json",
                    ROLES,
                    self.inputs(root),
                    "1" * 40,
                    "2" * 40,
                    mapping,
                )


if __name__ == "__main__":
    unittest.main()
