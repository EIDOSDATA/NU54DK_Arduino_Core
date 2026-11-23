"""! @brief 실제 Kconfig 해석과 공통 configure guard의 흐름 제어 경계를 검사합니다. """

from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

import kconfiglib


ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / "zephyr/config/ble.Kconfig"
GUARD = ROOT / "zephyr/cmake/ble_flow_control.cmake"
SCOPE = (
    "NUCODE_ARDUINO_API", "BT", "BT_CONN", "BT_HCI_HOST",
    "HAS_BT_CTLR", "BT_LL_SOFTDEVICE",
)


def sdk_config_block(text: str, symbol: str) -> str:
    """! @brief 고정 SDK의 원형 심볼 정의를 다음 최상위 경계까지 가져옵니다. """
    start = text.index("config " + symbol + "\n")
    boundary = re.search(r"^(?:config |menu |endmenu$|if |endif)", text[start + 1:], re.MULTILINE)
    if boundary is None:
        raise ValueError("SDK config boundary missing: " + symbol)
    end = start + 1 + boundary.start()
    return text[start:end] + "\n"


class BleFlowControlTests(unittest.TestCase):
    """! @brief SDK의 실제 버퍼 default와 사용자 override를 함께 검증합니다. """

    @classmethod
    def setUpClass(cls) -> None:
        """! @brief SDK 입력과 CMake만 준비하며 compiler나 보드는 사용하지 않습니다. """
        cls.sdk = Path(os.environ["ZEPHYR_BASE"]).resolve()
        cls.cmake = shutil.which("cmake")
        if cls.cmake is None:
            raise RuntimeError("cmake is required for the pure configure-guard test")
        common = (cls.sdk / "subsys/bluetooth/common/Kconfig").read_text(encoding="utf-8")
        bluetooth = (cls.sdk / "subsys/bluetooth/Kconfig").read_text(encoding="utf-8")
        cls.sdk_blocks = "\n".join((
            "if BT_CONN\n" + sdk_config_block(bluetooth, "BT_HCI_ACL_FLOW_CONTROL") + "endif\n",
            sdk_config_block(common, "BT_BUF_ACL_RX_COUNT_EXTRA"),
            sdk_config_block(common, "BT_BUF_CMD_TX_COUNT"),
        ))

    def resolve(self, *, extra: int = 2, command: int | None = None,
                overrides: dict[str, str] | None = None) -> dict[str, str]:
        """! @brief 공통 module 정책 뒤에 실제 SDK 정의를 읽고 최종 값을 반환합니다. """
        with tempfile.TemporaryDirectory(prefix="ble-flow-kconfig-") as directory:
            root = Path(directory)
            symbols = SCOPE + ("BT_HCI_RAW", "BT_MESH")
            definitions = "\n".join(
                "config " + name + '\n    bool "' + name + '"\n'
                for name in symbols
            )
            definitions += 'config BT_MAX_CONN\n    int "BT_MAX_CONN"\n    default 2\n'
            kconfig = root / "Kconfig"
            kconfig.write_text(
                'mainmenu "ACL flow-control fixture"\n' + definitions
                + '\nsource "' + POLICY.as_posix() + '"\n' + self.sdk_blocks,
                encoding="utf-8",
            )
            model = kconfiglib.Kconfig(str(kconfig), warn_to_stderr=False)
            values = {name: "y" for name in SCOPE}
            values.update({"BT_HCI_RAW": "n", "BT_MESH": "n"})
            values["BT_BUF_ACL_RX_COUNT_EXTRA"] = str(extra)
            if command is not None:
                values["BT_BUF_CMD_TX_COUNT"] = str(command)
            values.update(overrides or {})
            fragment = root / "prj.conf"
            fragment.write_text(
                "".join("CONFIG_" + name + "=" + value + "\n" for name, value in values.items()),
                encoding="utf-8",
            )
            model.load_config(str(fragment))
            return {
                name: symbol.str_value
                for name, symbol in model.syms.items()
                if symbol.nodes
            }

    def check_guard(self, values: dict[str, str], *, accepted: bool) -> None:
        """! @brief 실제 CMake guard를 script mode로 실행하고 fail-closed 결과를 확인합니다. """
        with tempfile.TemporaryDirectory(prefix="ble-flow-guard-") as directory:
            script = Path(directory) / "guard.cmake"
            lines = ["cmake_minimum_required(VERSION 3.20)"]
            for name, value in sorted(values.items()):
                if value in ("n", ""):
                    continue
                lines.append('set(CONFIG_' + name + ' "' + value + '")')
            lines.append('include("' + GUARD.as_posix() + '")')
            script.write_text("\n".join(lines) + "\n", encoding="utf-8")
            result = subprocess.run(
                [self.cmake, "-P", str(script)], capture_output=True,
                text=True, timeout=20, check=False,
            )
            if accepted:
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            else:
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("[NUCODE:E_BLE_FLOW_CONTROL]", result.stderr)

    def test_profile_and_mesh_resolve_minimum_required_capacity(self) -> None:
        """! @brief #29 EXTRA2와 Mesh EXTRA7은 각각 CMD4와 CMD9를 선택합니다. """
        for extra, count, mesh in ((2, 4, "n"), (7, 9, "y")):
            with self.subTest(extra=extra, mesh=mesh):
                values = self.resolve(extra=extra, overrides={"BT_MESH": mesh})
                self.assertEqual(values["BT_HCI_ACL_FLOW_CONTROL"], "y")
                self.assertEqual(values["BT_BUF_CMD_TX_COUNT"], str(count))
                self.check_guard(values, accepted=True)

    def test_all_supported_extra_counts_use_sdk_minimum(self) -> None:
        """! @brief 실제 Kconfig에서 지원 범위 전체가 EXTRA+2로 해석되는지 확인합니다. """
        for extra in range(1, 63):
            with self.subTest(extra=extra):
                self.assertEqual(self.resolve(extra=extra)["BT_BUF_CMD_TX_COUNT"], str(extra + 2))

    def test_larger_explicit_command_count_is_preserved(self) -> None:
        """! @brief 더 큰 사용자 설정을 공통 default가 덮어쓰지 않습니다. """
        values = self.resolve(extra=7, command=12)
        self.assertEqual(values["BT_BUF_CMD_TX_COUNT"], "12")
        self.check_guard(values, accepted=True)

    def test_undersized_explicit_command_count_is_rejected(self) -> None:
        """! @brief profile와 Mesh의 작은 명시값은 자동 보정하지 않고 거부합니다. """
        for extra, command, mesh in ((2, 3, "n"), (7, 3, "y"), (7, 8, "y")):
            with self.subTest(extra=extra, command=command):
                values = self.resolve(extra=extra, command=command, overrides={"BT_MESH": mesh})
                self.assertEqual(values["BT_BUF_CMD_TX_COUNT"], str(command))
                self.check_guard(values, accepted=False)

    def test_sdk_limit_accepts_62_and_rejects_63_or_larger(self) -> None:
        """! @brief SDK CMD 상한64의 마지막 지원값과 초과 경계를 고정합니다. """
        values = self.resolve(extra=62)
        self.assertEqual(values["BT_BUF_CMD_TX_COUNT"], "64")
        self.check_guard(values, accepted=True)
        for extra in (63, 64, 65535):
            with self.subTest(extra=extra):
                self.check_guard(self.resolve(extra=extra, command=64), accepted=False)

    def test_native_host_only_raw_and_other_controller_keep_sdk_defaults(self) -> None:
        """! @brief 적용 범위 밖 구성은 원형 SDK의 흐름 제어와 CMD default를 유지합니다. """
        cases = (
            ({"NUCODE_ARDUINO_API": "n"}, "n", "1"),
            ({"BT": "n"}, "n", "1"),
            ({"BT_HCI_HOST": "n"}, "n", "1"),
            ({"HAS_BT_CTLR": "n"}, "y", "1"),
            ({"BT_HCI_RAW": "y", "BT_HCI_HOST": "n"}, "y", ""),
            ({"BT_LL_SOFTDEVICE": "n"}, "n", "1"),
        )
        for overrides, flow, command in cases:
            with self.subTest(overrides=overrides):
                values = self.resolve(overrides=overrides)
                self.assertEqual(values["NUCODE_BLE_HOST_ACL_FLOW_CONTROL"], "n")
                self.assertEqual(values["BT_HCI_ACL_FLOW_CONTROL"], flow)
                self.assertEqual(values["BT_BUF_CMD_TX_COUNT"], command)
                self.check_guard(values, accepted=True)

    def test_nonconnection_extra_zero_is_outside_policy(self) -> None:
        """! @brief 비연결 EXTRA0 구성에는 연결형 용량 정책을 적용하지 않습니다. """
        values = self.resolve(extra=0, overrides={"BT_CONN": "n"})
        self.assertEqual(values["BT_BUF_ACL_RX_COUNT_EXTRA"], "0")
        self.assertEqual(values["NUCODE_BLE_HOST_ACL_FLOW_CONTROL"], "n")
        self.assertEqual(values["BT_BUF_CMD_TX_COUNT"], "1")
        self.check_guard(values, accepted=True)

    def test_actual_scope_cannot_bypass_guard_with_disabled_policy(self) -> None:
        """! @brief 정책 심볼 또는 흐름 제어를 바꿔도 실제 적용 범위 검사는 남습니다. """
        values = self.resolve()
        for symbol in ("NUCODE_BLE_HOST_ACL_FLOW_CONTROL", "BT_HCI_ACL_FLOW_CONTROL"):
            with self.subTest(symbol=symbol):
                altered = dict(values)
                altered[symbol] = "n"
                self.check_guard(altered, accepted=False)

    def test_missing_malformed_or_impossible_resolved_counts_are_rejected(self) -> None:
        """! @brief 손상된 최종 수치와 연결형 EXTRA0을 fail-closed로 거부합니다. """
        values = self.resolve()
        for symbol, setting in (
            ("BT_BUF_ACL_RX_COUNT_EXTRA", ""),
            ("BT_BUF_ACL_RX_COUNT_EXTRA", "zero"),
            ("BT_BUF_ACL_RX_COUNT_EXTRA", "0"),
            ("BT_BUF_CMD_TX_COUNT", ""),
            ("BT_BUF_CMD_TX_COUNT", "broken"),
            ("BT_BUF_CMD_TX_COUNT", "65"),
        ):
            with self.subTest(symbol=symbol, setting=setting):
                altered = dict(values)
                altered[symbol] = setting
                self.check_guard(altered, accepted=False)

    def test_out_of_scope_forced_policy_is_rejected(self) -> None:
        """! @brief 적용 범위 밖에 강제로 켠 정책도 최종 구성에서 거부합니다. """
        values = self.resolve(overrides={"NUCODE_ARDUINO_API": "n"})
        values["NUCODE_BLE_HOST_ACL_FLOW_CONTROL"] = "y"
        self.check_guard(values, accepted=False)


if __name__ == "__main__":
    unittest.main()
