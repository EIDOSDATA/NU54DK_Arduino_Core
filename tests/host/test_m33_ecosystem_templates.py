#!/usr/bin/env python3
"""! @brief 외부 ecosystem template의 credential·placeholder 실패 경계를 검사합니다. """
import base64
import copy
import importlib.util
from pathlib import Path
import unittest
from unittest import mock
import hashlib

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("companion_template", ROOT / "libraries/NUCODE_BLE_Companion/tools/prepare_template.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class TemplateCredentialTests(unittest.TestCase):
    """! @brief 형식이 유효한 시험 전용 scalar와 비허가 입력을 메모리에서 검사합니다. """

    def fixture(self):
        """! @brief cloud 등록·상호운용 증거가 아닌 공개 수학적 시험 값을 만듭니다. """
        return {"schema_version": 1, "use_case": "fast_pair_input", "environment": "test",
                "model_id": "0badc1", "anti_spoofing_key_base64": base64.b64encode((1).to_bytes(32, "big")).decode()}

    def test_valid_test_credentials_require_explicit_opt_in(self):
        """! @brief test 입력은 명시적 선택이 있어야 configuration으로 변환합니다. """
        fixture = self.fixture()
        with self.assertRaises(ValueError):
            MODULE.credentials("fast_pair_input", fixture)
        lines, secrets = MODULE.credentials("fast_pair_input", fixture, True)
        self.assertEqual(len(lines), 2)
        self.assertEqual(len(secrets), 1)

    def test_missing_placeholder_wrong_use_case_and_scalar(self):
        """! @brief 누락·개행 주입·잘못된 EC scalar·placeholder를 모두 거부합니다. """
        for key, value in (("model_id", "000000"), ("model_id", "ffffff"),
                           ("model_id", "123456"), ("model_id", "bad\nCONFIG"),
                           ("use_case", "fast_pair_locator"), ("schema_version", 2),
                           ("anti_spoofing_key_base64", ""),
                           ("anti_spoofing_key_base64", base64.b64encode(bytes(32)).decode()),
                           ("anti_spoofing_key_base64", base64.b64encode(bytes([255] * 32)).decode())):
            with self.subTest(key=key, value=value):
                fixture = self.fixture()
                fixture[key] = value
                with self.assertRaises(ValueError):
                    MODULE.credentials("fast_pair_input", fixture, True)
        fixture = self.fixture()
        del fixture["model_id"]
        with self.assertRaises(ValueError):
            MODULE.credentials("fast_pair_input", fixture, True)

    def test_debug_model_and_key_cannot_be_production(self):
        """! @brief production 선언으로 디버그 model과 반복 key를 승격하지 못합니다. """
        fixture = self.fixture()
        fixture["environment"] = "production"
        for model in ("2a410b", "4a436b", "0badc1"):
            fixture["model_id"] = model
            with self.assertRaises(ValueError):
                MODULE.credentials("fast_pair_input", fixture, True)
        raw = bytes(range(32))
        fixture["anti_spoofing_key_base64"] = base64.b64encode(raw).decode()
        with mock.patch.object(MODULE, "SDK_DEBUG_KEY_HASHES", {hashlib.sha256(raw).hexdigest()}):
            with self.assertRaises(ValueError):
                MODULE.credentials("fast_pair_input", fixture, True)

    def test_mds_credentials_and_command_injection(self):
        """! @brief MDS key와 device ID에 Kconfig·shell 조각을 넣을 수 없습니다. """
        fixture = {"schema_version": 1, "use_case": "mds", "environment": "test",
                   "project_key": "0123456789abcdef0123456789abcdef", "device_id": "local-build-test"}
        lines, secrets = MODULE.credentials("mds", fixture, True)
        self.assertEqual(len(lines), 2)
        self.assertEqual(len(secrets), 1)
        production = copy.deepcopy(fixture)
        production["environment"] = "production"
        production["device_id"] = "my-device-01"
        with self.assertRaises(ValueError):
            MODULE.credentials("mds", production)
        for key, value in (("project_key", "dummy-key"), ("project_key", "0" * 32),
                           ("device_id", 'name"\nCONFIG_BT=n'), ("device_id", "")):
            changed = copy.deepcopy(fixture)
            changed[key] = value
            with self.assertRaises(ValueError):
                MODULE.credentials("mds", changed, True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
