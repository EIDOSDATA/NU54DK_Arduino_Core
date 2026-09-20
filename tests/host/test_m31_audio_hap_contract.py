#!/usr/bin/env python3
"""! @brief W03-11 Hearing Access 공개 API와 예제 경계를 검사합니다. """

from __future__ import annotations

import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
HEADER = ROOT / "libraries/NUCODE_BLE_Audio/src/NUCODE_BLE_Audio.h"
BACKEND = ROOT / "libraries/NUCODE_BLE_Audio/src/NUCODE_BLE_Audio_HearingAccess.cpp"
EXAMPLES = ROOT / "libraries/NUCODE_BLE_Audio/examples"
READINESS = ROOT / "variants/nu54dk/m31-ble-readiness.json"


class HearingAccessContractTests(unittest.TestCase):
    """! @brief HAS facade, backend, 예제와 고정 SDK 근거를 대조합니다. """

    def test_public_api_covers_server_client_and_bounded_presets(self) -> None:
        """! @brief server/client가 preset·active index·이름·범위 오류 API를 제공합니다. """
        source = HEADER.read_text(encoding="utf-8")
        for token in (
            "class HearingAccessServer final",
            "class HearingAccessClient final",
            "struct HearingPreset",
            "Error addPreset(",
            "Error setActivePreset(",
            "Error setPresetAvailable(",
            "Error renamePreset(",
            "Error readPresets(",
            "Error nextPreset(",
            "Error previousPreset(",
            "maximum_name_bytes = 40U",
        ):
            self.assertIn(token, source)

    def test_backend_uses_fixed_has_api_and_rejects_invalid_ranges(self) -> None:
        """! @brief Zephyr 호출은 backend에만 있고 index/name 경계가 명시됩니다. """
        source = BACKEND.read_text(encoding="utf-8")
        for token in (
            "bt_has_register",
            "bt_has_preset_register",
            "bt_has_preset_active_set",
            "bt_has_preset_name_change",
            "bt_has_client_discover",
            "bt_has_client_presets_read",
            "bt_has_client_preset_set",
            "bt_has_client_preset_next",
            "bt_has_client_preset_prev",
            "start_index == 0U",
            "index == 0U",
            "-EINVAL",
        ):
            self.assertIn(token, source)

    def test_examples_keep_zephyr_calls_behind_nucode_api(self) -> None:
        """! @brief 공개 sketch에 개발 표식이나 Zephyr 직접 호출이 없습니다. """
        for name in ("HearingAccessServer", "HearingAccessClient"):
            sketch = (EXAMPLES / name / f"{name}.ino").read_text(encoding="utf-8")
            self.assertIn("#include <NUCODE_BLE_Audio.h>", sketch)
            self.assertIn("void setup()", sketch)
            self.assertIn("void loop()", sketch)
            self.assertNotRegex(sketch, r"#include\s*[<\"]zephyr/")
            self.assertNotRegex(sketch, r"\bbt_[a-zA-Z0-9_]+\s*\(")
            self.assertNotRegex(sketch, r"\bk_[a-zA-Z0-9_]+\s*\(")
            self.assertNotRegex(sketch, r"M31|W03")

    def test_role_kconfigs_select_exact_has_capabilities(self) -> None:
        """! @brief 두 역할 Kconfig가 HAS server/client 기능을 분리합니다. """
        server = (EXAMPLES / "HearingAccessServer/prj.conf").read_text(encoding="utf-8")
        client = (EXAMPLES / "HearingAccessClient/prj.conf").read_text(encoding="utf-8")
        self.assertIn("CONFIG_BT_HAS=y", server)
        self.assertIn("CONFIG_BT_HAS_PRESET_COUNT=4", server)
        self.assertIn("CONFIG_BT_HAS_PRESET_NAME_DYNAMIC=y", server)
        self.assertIn("CONFIG_BT_BAP_UNICAST_SERVER=y", server)
        self.assertIn("CONFIG_BT_ASCS_MAX_ASE_SNK_COUNT=1", server)
        self.assertIn("CONFIG_FPU=y", server)
        self.assertIn("CONFIG_LIBLC3=y", server)
        self.assertNotIn("CONFIG_BT_HAS_CLIENT=y", server)
        self.assertIn("CONFIG_BT_HAS_CLIENT=y", client)
        self.assertIn("CONFIG_BT_GATT_AUTO_UPDATE_MTU=y", client)
        self.assertIn("CONFIG_FPU=y", client)
        self.assertIn("CONFIG_LIBLC3=y", client)
        self.assertNotIn("CONFIG_BT_HAS=y", client)

    def test_readiness_keeps_runtime_not_run_until_hil_evidence_exists(self) -> None:
        """! @brief 구현만으로 W03-11 실기 상태를 PASS로 올리지 않습니다. """
        document = json.loads(READINESS.read_text(encoding="utf-8"))
        row = next(item for item in document["audio_groups"] if item["id"] == "W03-11")
        self.assertEqual(row["status"], "NOT_RUN")
        roles = [item for item in document["example_roles"]
                 if item["id"].startswith("W03-11:")]
        self.assertEqual(len(roles), 2)
        self.assertTrue(all(item["runtime_status"] == "NOT_RUN" for item in roles))

    def test_doxygen_and_control_flow_style(self) -> None:
        """! @brief 추가 public 구현의 Doxygen과 중괄호 규칙을 검사합니다. """
        source = BACKEND.read_text(encoding="utf-8")
        self.assertIn("/** @brief", source)
        self.assertIsNone(
            re.search(r"\b(?:if|for|while)\s*\([^\n]+\)\r?\n[ \t]*([^\s{])", source)
        )


if __name__ == "__main__":
    unittest.main()
