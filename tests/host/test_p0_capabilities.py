#!/usr/bin/env python3
"""! @brief P0 compiler probe mapping과 capability resolver 계약을 검증합니다. """

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "tools" / "nu54-builder" / "src" / "nu54_builder.py"
SPEC = importlib.util.spec_from_file_location("nu54_builder_p0", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Builder를 불러올 수 없습니다: {MODULE_PATH}")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class P0CapabilityContractTests(unittest.TestCase):
    """! @brief 공개 ID·의존성·충돌·capacity의 fail-closed 경계를 검증합니다. """

    def setUp(self) -> None:
        """! @brief 저장소의 실제 registry를 각 시험의 기준으로 읽습니다. """
        self.registry = MODULE.load_capability_registry(ROOT)
        self.empty_declaration = {
            "schema_version": MODULE.CAPABILITY_DECLARATION_SCHEMA_VERSION,
            "capabilities": [],
            "roles": [],
            "capacities": {},
            "path": None,
        }

    def test_probe_symbol_mapping_uses_stable_capability_ids(self) -> None:
        """! @brief compiler symbol은 공개 capability ID로만 외부화합니다. """
        output = """
                 U SPI
        probe.o: U Wire
                 U analogWrite
                 U unrelatedSymbol
        """
        symbols = MODULE.parse_undefined_symbols(output)
        self.assertEqual(symbols, ["SPI", "Wire", "analogWrite", "unrelatedSymbol"])
        self.assertEqual(
            MODULE.capabilities_for_probe_symbols(self.registry, symbols),
            ["arduino.pwm", "arduino.spi", "arduino.wire"],
        )

    def test_compiler_probe_keeps_reachable_runtime_and_constructor_references(self) -> None:
        """! @brief GC link가 dead call은 버리고 간접·runtime·전역 생성자 요구는 남깁니다. """
        try:
            tools = MODULE.tool_environment(ROOT)
        except MODULE.AdapterError as error:
            self.skipTest(f"고정 cross compiler를 사용할 수 없습니다: {error}")
        with tempfile.TemporaryDirectory(prefix="n54-p0-probe-") as temporary:
            root = Path(temporary)
            sketch = root / "sketch"
            state = root / "build" / "nu54-zephyr"
            sketch.mkdir(parents=True)
            state.mkdir(parents=True)
            main_source = sketch / "main.cpp"
            library_source = sketch / "sensor.cpp"
            main_source.write_text(
                """
#include <Arduino.h>

extern "C" void sensorRead(void);
volatile bool enabled = false;
struct Startup
{
    Startup()
    {
        Serial1.begin(115200);
    }
};
Startup startup;
void deadPath()
{
    Wire.begin();
}
extern "C" void setup(void)
{
    digitalWrite(1, HIGH);
    sensorRead();
    if (enabled)
    {
        analogWrite(2, 3);
    }
}
extern "C" void loop(void)
{
}
""",
                encoding="utf-8",
            )
            library_source.write_text(
                """
#include <Arduino.h>

extern "C" void sensorRead(void)
{
    SPI.begin();
}
""",
                encoding="utf-8",
            )
            records = [
                {
                    "source": source.as_posix(),
                    "language": "cxx",
                    "include_dirs": [sketch.as_posix()],
                }
                for source in (main_source, library_source)
            ]
            paths = {
                "platform_root": ROOT,
                "build_path": root / "build",
                "state_root": state,
                "sketch_root": sketch,
            }
            result = MODULE.run_capability_probe(paths, records, tools, self.registry)
            self.assertEqual(
                result["capabilities"],
                ["arduino.gpio", "arduino.pwm", "arduino.serial1", "arduino.spi"],
            )
            self.assertNotIn("Wire", result["undefined_symbols"])
            self.assertEqual(result["link_mode"], "executable-section-gc")
            self.assertTrue(Path(result["map"]).is_file())

    def test_direct_probe_requirement_adds_transitive_dependencies(self) -> None:
        """! @brief SPI 요구가 GPIO·소유권·API·runtime까지 폐쇄됩니다. """
        result = MODULE.resolve_capabilities(
            self.registry, ["arduino.spi"], [], self.empty_declaration
        )
        identifiers = {item["id"] for item in result["capabilities"]}
        self.assertEqual(
            identifiers,
            {
                "arduino.runtime",
                "arduino.api",
                "arduino.io-ownership",
                "arduino.gpio",
                "arduino.spi",
            },
        )
        spi = next(item for item in result["capabilities"] if item["id"] == "arduino.spi")
        gpio = next(item for item in result["capabilities"] if item["id"] == "arduino.gpio")
        self.assertEqual(spi["reasons"], ["compiler-probe"])
        self.assertEqual(gpio["reasons"], ["dependency:arduino.spi"])
        self.assertIn("CONFIG_GPIO=y", result["generated"]["conf"])
        self.assertIn("CONFIG_SPI=y", result["generated"]["conf"])
        self.assertIn("CONFIG_NUCODE_ARDUINO_SPI=y", result["generated"]["conf"])
        self.assertIn("CONFIG_I2C=n", result["generated"]["disabled_conf"])
        self.assertIn("CONFIG_NUCODE_ARDUINO_WIRE=n", result["generated"]["disabled_conf"])

    def test_adaptive_profile_materializes_resolution_as_single_source(self) -> None:
        """! @brief adaptive profile만 생성 config·overlay·resolution을 적용합니다. """
        profile = MODULE.load_configuration_profile(ROOT, "adaptive")
        self.assertEqual(profile["capability_mode"], "resolved")
        features = MODULE.resolve_library_features(ROOT, profile, ["SPI"])
        result = MODULE.resolve_capabilities(
            self.registry, ["arduino.spi"], features, self.empty_declaration
        )
        with tempfile.TemporaryDirectory(prefix="n54-p0-materialize-") as temporary:
            root = Path(temporary)
            sketch = root / "sketch"
            app = root / "app"
            sketch.mkdir()
            paths = {
                "platform_root": ROOT,
                "sketch_root": sketch,
                "app": app,
                "workspace": root,
            }
            MODULE.materialize_application(
                paths,
                mock.Mock(
                    profile="adaptive",
                    fqbn="nucode:zephyr:nu54dk",
                    board=MODULE.DEFAULT_BOARD,
                ),
                ["SPI"],
                result,
            )
            config = (app / "prj.conf").read_text(encoding="utf-8")
            overlay = (app / "app.overlay").read_text(encoding="utf-8")
            resolved = json.loads(
                (app / "resolved-capabilities.json").read_text(encoding="utf-8")
            )
            self.assertLess(
                config.index("CONFIG_NUCODE_ARDUINO_SPI=n"),
                config.rindex("CONFIG_NUCODE_ARDUINO_SPI=y"),
            )
            self.assertIn("nu54dk-arduino-spi.dtsi", overlay)
            self.assertNotIn("nu54dk-arduino-wire.dtsi", overlay)
            self.assertEqual(resolved, result)

    def test_final_kconfig_validation_rejects_expert_override(self) -> None:
        """! @brief 필수 capability를 끈 expert override를 최종 .config에서 거부합니다. """
        result = MODULE.resolve_capabilities(
            self.registry, ["arduino.spi"], [], self.empty_declaration
        )
        with tempfile.TemporaryDirectory(prefix="n54-p0-final-config-") as temporary:
            build = Path(temporary) / "build"
            config_path = build / "zephyr" / ".config"
            config_path.parent.mkdir(parents=True)
            expected = [
                *result["generated"]["disabled_conf"],
                *result["generated"]["conf"],
            ]
            config_path.write_text("\n".join(expected) + "\n", encoding="utf-8")
            MODULE.validate_resolved_configuration(
                {"zephyr_build": build}, result
            )
            config_path.write_text(
                config_path.read_text(encoding="utf-8").replace(
                    "CONFIG_NUCODE_ARDUINO_SPI=y",
                    "# CONFIG_NUCODE_ARDUINO_SPI is not set",
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                MODULE.AdapterError, "E_CAPABILITY_FINAL_CONFIG.*NUCODE_ARDUINO_SPI"
            ):
                MODULE.validate_resolved_configuration(
                    {"zephyr_build": build}, result
                )

    def test_library_requirement_is_transitive_without_sketch_reference(self) -> None:
        """! @brief library manifest의 간접 PWM 요구를 probe 결과와 합칩니다. """
        result = MODULE.resolve_capabilities(
            self.registry,
            [],
            [{"id": "fixture.sensor", "capabilities": ["arduino.pwm"]}],
            self.empty_declaration,
        )
        pwm = next(item for item in result["capabilities"] if item["id"] == "arduino.pwm")
        self.assertEqual(pwm["reasons"], ["library:fixture.sensor"])

    def test_missing_declaration_has_no_role_or_capacity(self) -> None:
        """! @brief sidecar가 없으면 임의 BLE 역할·용량을 추론하지 않습니다. """
        with tempfile.TemporaryDirectory(prefix="n54-p0-declaration-") as temporary:
            declaration = MODULE.load_capability_declaration(Path(temporary))
        result = MODULE.resolve_capabilities(self.registry, [], [], declaration)
        self.assertEqual(result["roles"], [])
        self.assertEqual(result["capacities"], [])

    def test_unknown_requirement_and_role_fail_closed(self) -> None:
        """! @brief 모르는 요구를 full profile로 되돌리지 않고 중단합니다. """
        with self.assertRaisesRegex(MODULE.AdapterError, "E_CAPABILITY_UNKNOWN"):
            MODULE.resolve_capabilities(
                self.registry, ["arduino.unknown"], [], self.empty_declaration
            )
        declaration = copy.deepcopy(self.empty_declaration)
        declaration["roles"] = ["unknown-role"]
        with self.assertRaisesRegex(MODULE.AdapterError, "E_ROLE_UNKNOWN"):
            MODULE.resolve_capabilities(self.registry, [], [], declaration)

    def test_dependency_cycle_is_rejected_with_trace(self) -> None:
        """! @brief 순환 의존성의 전체 경로를 진단합니다. """
        registry = copy.deepcopy(self.registry)
        registry["capabilities"]["arduino.runtime"]["requires"] = ["arduino.api"]
        with self.assertRaisesRegex(
            MODULE.AdapterError,
            r"E_CAPABILITY_CYCLE.*arduino\.api -> arduino\.runtime -> arduino\.api",
        ):
            MODULE.resolve_capabilities(registry, [], [], self.empty_declaration)

    def test_conflicting_capabilities_are_rejected(self) -> None:
        """! @brief fabric과 Arduino SPI의 자원 충돌을 양방향 선언과 무관하게 거부합니다. """
        declaration = copy.deepcopy(self.empty_declaration)
        declaration["capabilities"] = ["nucode.peripheral-fabric"]
        with self.assertRaisesRegex(MODULE.AdapterError, "E_CAPABILITY_CONFLICT"):
            MODULE.resolve_capabilities(
                self.registry, ["arduino.spi"], [], declaration
            )

    def test_capacity_aggregation_is_explicit_and_bounded(self) -> None:
        """! @brief maximum·sum·identical 의미와 검증 범위를 각각 적용합니다. """
        registry = copy.deepcopy(self.registry)
        registry["roles"] = {
            "role-a": {
                "id": "role-a",
                "capabilities": [],
                "capacities": {
                    "ble.connections": 1,
                    "ble.iso-streams": 1,
                    "ble.att-mtu": 247,
                },
                "conflicts": [],
            },
            "role-b": {
                "id": "role-b",
                "capabilities": [],
                "capacities": {
                    "ble.connections": 2,
                    "ble.iso-streams": 2,
                    "ble.att-mtu": 247,
                },
                "conflicts": [],
            },
        }
        declaration = copy.deepcopy(self.empty_declaration)
        declaration["roles"] = ["role-a", "role-b"]
        result = MODULE.resolve_capabilities(registry, [], [], declaration)
        capacities = {item["id"]: item for item in result["capacities"]}
        self.assertEqual(capacities["ble.connections"]["value"], 2)
        self.assertEqual(capacities["ble.iso-streams"]["value"], 3)
        self.assertEqual(capacities["ble.att-mtu"]["value"], 247)
        self.assertEqual(
            capacities["ble.connections"]["conf"], ["CONFIG_BT_MAX_CONN=2"]
        )
        self.assertIn("CONFIG_BT_ISO_MAX_CHAN=3", result["generated"]["conf"])
        self.assertIn("CONFIG_BT_L2CAP_TX_MTU=247", result["generated"]["conf"])

        registry["roles"]["role-b"]["capacities"]["ble.att-mtu"] = 517
        with self.assertRaisesRegex(MODULE.AdapterError, "E_CAPACITY_CONFLICT"):
            MODULE.resolve_capabilities(registry, [], [], declaration)
        declaration["capacities"] = {"ble.connections": 9}
        registry["roles"]["role-b"]["capacities"]["ble.att-mtu"] = 247
        with self.assertRaisesRegex(MODULE.AdapterError, "E_CAPACITY_RANGE"):
            MODULE.resolve_capabilities(registry, [], [], declaration)

    def test_capacity_kconfig_conflict_fails_closed(self) -> None:
        """! @brief capability와 capacity가 같은 Kconfig에 다른 값을 요구하면 거부합니다. """
        registry = copy.deepcopy(self.registry)
        registry["roles"] = {
            "role-a": {
                "id": "role-a",
                "capabilities": ["arduino.runtime"],
                "capacities": {"ble.connections": 2},
                "conflicts": [],
            }
        }
        registry["capabilities"]["arduino.runtime"]["conf"].append(
            "CONFIG_BT_MAX_CONN=1"
        )
        declaration = copy.deepcopy(self.empty_declaration)
        declaration["roles"] = ["role-a"]
        with self.assertRaisesRegex(
            MODULE.AdapterError, "E_CAPABILITY_CONFIG_CONFLICT.*BT_MAX_CONN"
        ):
            MODULE.resolve_capabilities(registry, [], [], declaration)

    def test_declaration_and_registry_schema_are_strict(self) -> None:
        """! @brief 중복 key·추가 field·잘못된 참조를 모두 거부합니다. """
        with tempfile.TemporaryDirectory(prefix="n54-p0-schema-") as temporary:
            root = Path(temporary)
            declaration_path = root / "nucode-build.json"
            declaration_path.write_text(
                '{"schema_version":1,"schema_version":1,"capabilities":[],"roles":[],"capacities":{}}',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(MODULE.AdapterError, "E_CAPABILITY_DECLARATION"):
                MODULE.load_capability_declaration(root)
            declaration_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "capabilities": [],
                        "roles": [],
                        "capacities": {},
                        "kconfig": ["CONFIG_BT=y"],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(MODULE.AdapterError, "E_CAPABILITY_DECLARATION"):
                MODULE.load_capability_declaration(root)

    def test_resolved_document_is_deterministic_and_atomic(self) -> None:
        """! @brief 같은 입력은 byte가 같은 단일 원본을 만들고 변경 없음을 반환합니다. """
        result = MODULE.resolve_capabilities(
            self.registry, ["arduino.serial", "arduino.time"], [], self.empty_declaration
        )
        with tempfile.TemporaryDirectory(prefix="n54-p0-result-") as temporary:
            path = Path(temporary) / "resolved-capabilities.json"
            self.assertTrue(MODULE.write_resolved_capabilities(path, result))
            first = path.read_bytes()
            self.assertFalse(MODULE.write_resolved_capabilities(path, result))
            self.assertEqual(first, path.read_bytes())


if __name__ == "__main__":
    unittest.main()
