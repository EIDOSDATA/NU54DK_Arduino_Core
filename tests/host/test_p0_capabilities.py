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
    ~Startup()
    {
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

    def test_capability_requires_one_verified_role(self) -> None:
        """! @brief 역할 종속 capability는 허용 목록 중 하나가 없으면 거부합니다. """
        registry = copy.deepcopy(self.registry)
        registry["roles"] = {
            "role-a": {
                "id": "role-a",
                "capabilities": [],
                "capacities": {},
                "conflicts": [],
            },
            "role-b": {
                "id": "role-b",
                "capabilities": [],
                "capacities": {},
                "conflicts": [],
            },
        }
        registry["capabilities"]["arduino.runtime"]["requires_any_role"] = [
            "role-a",
            "role-b",
        ]
        with self.assertRaisesRegex(
            MODULE.AdapterError, "E_ROLE_REQUIRED.*arduino.runtime.*role-a.*role-b"
        ):
            MODULE.resolve_capabilities(registry, [], [], self.empty_declaration)

        declaration = copy.deepcopy(self.empty_declaration)
        declaration["roles"] = ["role-b"]
        result = MODULE.resolve_capabilities(registry, [], [], declaration)
        runtime = next(
            item for item in result["capabilities"] if item["id"] == "arduino.runtime"
        )
        self.assertEqual(runtime["requires_any_role"], ["role-a", "role-b"])

    def test_verified_ble_role_presets_resolve_exact_features(self) -> None:
        """! @brief 대표 BLE 계열은 검증된 역할과 capacity로만 adaptive 설정됩니다. """
        profile = MODULE.load_configuration_profile(ROOT, "adaptive")
        cases = (
            (
                ["NUCODE_BLE"],
                "ble-gap-nus-dual-role",
                "CONFIG_NUCODE_BLE_NUS=y",
                {"ble.connections": 1},
            ),
            (
                ["NUCODE_BLE"],
                "ble-gatt-nus-dual-role",
                "CONFIG_NUCODE_BLE_GATT=y",
                {"ble.connections": 1},
            ),
            (
                ["NUCODE_BLE"],
                "ble-l2cap-coc-dual-role",
                "CONFIG_NUCODE_BLE_L2CAP=y",
                {"ble.connections": 2, "ble.att-mtu": 512},
            ),
            (
                ["NUCODE_BLE_ISO"],
                "ble-iso-cis-central",
                "CONFIG_NUCODE_BLE_ISO_MODE_CIS_CENTRAL=y",
                {"ble.connections": 2, "ble.iso-streams": 2},
            ),
            (
                ["NUCODE_BLE_ISO"],
                "ble-iso-cis-peripheral",
                "CONFIG_NUCODE_BLE_ISO_MODE_CIS_PERIPHERAL=y",
                {"ble.connections": 2, "ble.iso-streams": 2},
            ),
            (
                ["NUCODE_BLE_ISO"],
                "ble-iso-cis-to-bis-peer",
                "CONFIG_NUCODE_BLE_ISO_MODE_CIS_TO_BIS_PEER=y",
                {"ble.connections": 2, "ble.iso-streams": 2},
            ),
            (
                ["NUCODE_BLE_ISO"],
                "ble-iso-bis-source",
                "CONFIG_NUCODE_BLE_ISO_MODE_BIS_SOURCE=y",
                {"ble.iso-streams": 1},
            ),
            (
                ["NUCODE_BLE_ISO"],
                "ble-iso-bis-receiver",
                "CONFIG_NUCODE_BLE_ISO_MODE_BIS_RECEIVER=y",
                {"ble.iso-streams": 1},
            ),
            (
                ["NUCODE_BLE_ISO"],
                "ble-iso-bis-encrypted-source",
                "CONFIG_NUCODE_BLE_ISO_MODE_BIS_ENCRYPTED_SOURCE=y",
                {"ble.iso-streams": 1},
            ),
            (
                ["NUCODE_BLE_ISO"],
                "ble-iso-bis-encrypted-receiver",
                "CONFIG_NUCODE_BLE_ISO_MODE_BIS_ENCRYPTED_RECEIVER=y",
                {"ble.iso-streams": 1},
            ),
            (
                ["NUCODE_BLE_ISO"],
                "ble-iso-bis-time-source",
                "CONFIG_NUCODE_BLE_ISO_MODE_BIS_TIME_SOURCE=y",
                {"ble.iso-streams": 1},
            ),
            (
                ["NUCODE_BLE_ISO"],
                "ble-iso-bis-time-receiver",
                "CONFIG_NUCODE_BLE_ISO_MODE_BIS_TIME_RECEIVER=y",
                {"ble.iso-streams": 1},
            ),
            (
                ["NUCODE_BLE_ISO"],
                "ble-iso-cis-to-bis-bridge",
                "CONFIG_NUCODE_BLE_ISO_MODE_CIS_TO_BIS_BRIDGE=y",
                {"ble.connections": 1, "ble.iso-streams": 2},
            ),
            (
                ["NUCODE_BLE_ISO"],
                "ble-iso-cis-to-bis-receiver",
                "CONFIG_NUCODE_BLE_ISO_MODE_CIS_TO_BIS_RECEIVER=y",
                {"ble.iso-streams": 1},
            ),
            (
                ["NUCODE_BLE", "NUCODE_BLE_Audio"],
                "ble-audio-unicast-source",
                "CONFIG_BT_BAP_UNICAST_CLIENT=y",
                {"ble.connections": 1, "ble.iso-streams": 1},
            ),
            (
                ["NUCODE_BLE", "NUCODE_BLE_Audio"],
                "ble-audio-unicast-sink",
                "CONFIG_BT_BAP_UNICAST_SERVER=y",
                {"ble.connections": 1, "ble.iso-streams": 1},
            ),
            (
                ["NUCODE_BLE", "NUCODE_BLE_Audio"],
                "ble-audio-unicast-cycle",
                "CONFIG_BT_BAP_UNICAST_CLIENT=y",
                {"ble.connections": 1, "ble.iso-streams": 1},
            ),
            (
                ["NUCODE_BLE", "NUCODE_BLE_Audio"],
                "ble-audio-unicast-duplex-client",
                "CONFIG_BT_BAP_UNICAST_CLIENT_ASE_SRC_COUNT=2",
                {"ble.connections": 1, "ble.iso-streams": 2},
            ),
            (
                ["NUCODE_BLE", "NUCODE_BLE_Audio"],
                "ble-audio-unicast-duplex-server",
                "CONFIG_BT_ASCS_MAX_ASE_SRC_COUNT=1",
                {"ble.connections": 1, "ble.iso-streams": 2},
            ),
            (
                ["NUCODE_BLE", "NUCODE_BLE_Audio"],
                "ble-audio-broadcast-source",
                "CONFIG_BT_BAP_BROADCAST_SOURCE=y",
                {"ble.iso-streams": 1},
            ),
            (
                ["NUCODE_BLE", "NUCODE_BLE_Audio"],
                "ble-audio-broadcast-sink",
                "CONFIG_BT_BAP_BROADCAST_SINK=y",
                {"ble.connections": 1, "ble.iso-streams": 1},
            ),
            (
                ["NUCODE_BLE", "NUCODE_BLE_Audio"],
                "ble-audio-broadcast-delegator-sink",
                "CONFIG_BT_BAP_SCAN_DELEGATOR=y",
                {"ble.connections": 1, "ble.iso-streams": 1},
            ),
            (
                ["NUCODE_BLE", "NUCODE_BLE_Audio"],
                "ble-audio-broadcast-assistant",
                "CONFIG_BT_BAP_BROADCAST_ASSISTANT=y",
                {"ble.connections": 1},
            ),
            (
                ["NUCODE_BLE", "NUCODE_BLE_Audio", "NUCODE_BLE_Security"],
                "ble-audio-hearing-access-server",
                "CONFIG_BT_HAS=y",
                {"ble.connections": 1, "ble.iso-streams": 1},
            ),
            (
                ["NUCODE_BLE", "NUCODE_BLE_Audio", "NUCODE_BLE_Security"],
                "ble-audio-hearing-access-client",
                "CONFIG_BT_HAS_CLIENT=y",
                {"ble.connections": 1},
            ),
            (
                ["NUCODE_BLE", "NUCODE_BLE_Audio", "NUCODE_BLE_Security"],
                "ble-audio-control-device",
                "CONFIG_BT_VCP_VOL_REND=y",
                {"ble.connections": 1},
            ),
            (
                ["NUCODE_BLE", "NUCODE_BLE_Audio", "NUCODE_BLE_Security"],
                "ble-audio-control-controller",
                "CONFIG_BT_VCP_VOL_CTLR=y",
                {"ble.connections": 1},
            ),
            (
                ["NUCODE_BLE", "NUCODE_BLE_Audio", "NUCODE_BLE_Security"],
                "ble-audio-media-player",
                "CONFIG_BT_MCS=y",
                {"ble.connections": 1},
            ),
            (
                ["NUCODE_BLE", "NUCODE_BLE_Audio", "NUCODE_BLE_Security"],
                "ble-audio-media-client",
                "CONFIG_BT_MCC=y",
                {"ble.connections": 1},
            ),
            (
                ["NUCODE_BLE", "NUCODE_BLE_Audio", "NUCODE_BLE_Security"],
                "ble-audio-call-server",
                "CONFIG_BT_CCP_CALL_CONTROL_SERVER=y",
                {"ble.connections": 1},
            ),
            (
                ["NUCODE_BLE", "NUCODE_BLE_Audio", "NUCODE_BLE_Security"],
                "ble-audio-call-client",
                "CONFIG_BT_CCP_CALL_CONTROL_CLIENT=y",
                {"ble.connections": 1},
            ),
            (
                ["NUCODE_BLE_DirectionFinding"],
                "ble-df-cte-beacon",
                "CONFIG_NUCODE_BLE_DF_BEACON=y",
                {},
            ),
            (
                ["NUCODE_BLE", "NUCODE_BLE_DirectionFinding"],
                "ble-df-connected-responder",
                "CONFIG_NUCODE_BLE_DF_RESPONDER=y",
                {"ble.connections": 1},
            ),
            (
                ["NUCODE_BLE", "NUCODE_BLE_ChannelSounding"],
                "ble-cs-ras-initiator",
                "CONFIG_NUCODE_BLE_CS_INITIATOR=y",
                {"ble.connections": 1, "ble.att-mtu": 498},
            ),
            (
                ["NUCODE_BLE", "NUCODE_BLE_ChannelSounding"],
                "ble-cs-ras-reflector",
                "CONFIG_NUCODE_BLE_CS_REFLECTOR=y",
                {"ble.connections": 1},
            ),
        )
        for libraries, role, required_conf, expected_capacities in cases:
            with self.subTest(role=role):
                declaration = copy.deepcopy(self.empty_declaration)
                declaration["roles"] = [role]
                features = MODULE.resolve_library_features(ROOT, profile, libraries)
                result = MODULE.resolve_capabilities(
                    self.registry, [], features, declaration
                )
                self.assertIn(required_conf, result["generated"]["conf"])
                self.assertEqual(
                    {item["id"]: item["value"] for item in result["capacities"]},
                    expected_capacities,
                )
                self.assertEqual(result["roles"], [role])

    def test_iso_role_source_ownership_is_minimal(self) -> None:
        """! @brief 11개 ISO 역할은 공통 facade와 필요한 CIS/BIS backend만 선택합니다. """
        profile = MODULE.load_configuration_profile(ROOT, "adaptive")
        features = MODULE.resolve_library_features(ROOT, profile, ["NUCODE_BLE_ISO"])
        common = "libraries/NUCODE_BLE_ISO/src/NUCODE_BLE_ISO.cpp"
        raw_cis = "libraries/NUCODE_BLE_ISO/src/NUCODE_BLE_ISO_RawCis.cpp"
        raw_bis = "libraries/NUCODE_BLE_ISO/src/NUCODE_BLE_ISO_RawBis.cpp"
        cases = {
            "ble-iso-cis-central": {common, raw_cis},
            "ble-iso-cis-peripheral": {common, raw_cis},
            "ble-iso-cis-to-bis-peer": {common, raw_cis},
            "ble-iso-bis-source": {common, raw_bis},
            "ble-iso-bis-receiver": {common, raw_bis},
            "ble-iso-bis-encrypted-source": {common, raw_bis},
            "ble-iso-bis-encrypted-receiver": {common, raw_bis},
            "ble-iso-bis-time-source": {common, raw_bis},
            "ble-iso-bis-time-receiver": {common, raw_bis},
            "ble-iso-cis-to-bis-bridge": {common, raw_cis, raw_bis},
            "ble-iso-cis-to-bis-receiver": {common, raw_bis},
        }
        for role, expected_sources in cases.items():
            with self.subTest(role=role):
                declaration = copy.deepcopy(self.empty_declaration)
                declaration["roles"] = [role]
                result = MODULE.resolve_capabilities(
                    self.registry, [], features, declaration
                )
                self.assertEqual(
                    set(result["generated"]["sources"]), expected_sources
                )

    def test_audio_role_source_ownership_is_minimal(self) -> None:
        """! @brief 17개 Audio 역할은 공통 facade와 필요한 backend만 선택합니다. """
        profile = MODULE.load_configuration_profile(ROOT, "adaptive")
        features = MODULE.resolve_library_features(
            ROOT, profile, ["NUCODE_BLE", "NUCODE_BLE_Audio"]
        )
        root = "libraries/NUCODE_BLE_Audio/src"
        common = f"{root}/NUCODE_BLE_Audio.cpp"
        client = f"{root}/NUCODE_BLE_Audio_UnicastClient.cpp"
        server = f"{root}/NUCODE_BLE_Audio_UnicastServer.cpp"
        broadcast_source = f"{root}/NUCODE_BLE_Audio_BroadcastSource.cpp"
        broadcast_sink = f"{root}/NUCODE_BLE_Audio_BroadcastSink.cpp"
        assistant = f"{root}/NUCODE_BLE_Audio_BroadcastAssistant.cpp"
        hearing_access = f"{root}/NUCODE_BLE_Audio_HearingAccess.cpp"
        control_device = f"{root}/NUCODE_BLE_Audio_ControlDevice.cpp"
        control_controller = f"{root}/NUCODE_BLE_Audio_ControlController.cpp"
        media_control = f"{root}/NUCODE_BLE_Audio_MediaControl.cpp"
        call_control = f"{root}/NUCODE_BLE_Audio_CallControl.cpp"
        cases = {
            "ble-audio-unicast-source": {common, client},
            "ble-audio-unicast-sink": {common, server},
            "ble-audio-unicast-cycle": {common, client},
            "ble-audio-unicast-duplex-client": {common, client},
            "ble-audio-unicast-duplex-server": {common, server},
            "ble-audio-broadcast-source": {common, broadcast_source},
            "ble-audio-broadcast-sink": {common, broadcast_sink},
            "ble-audio-broadcast-delegator-sink": {common, broadcast_sink},
            "ble-audio-broadcast-assistant": {common, assistant},
            "ble-audio-hearing-access-server": {common, hearing_access},
            "ble-audio-hearing-access-client": {common, hearing_access},
            "ble-audio-control-device": {common, control_device},
            "ble-audio-control-controller": {common, control_controller},
            "ble-audio-media-player": {common, media_control},
            "ble-audio-media-client": {common, media_control},
            "ble-audio-call-server": {common, call_control},
            "ble-audio-call-client": {common, call_control},
        }
        for role, expected_sources in cases.items():
            with self.subTest(role=role):
                declaration = copy.deepcopy(self.empty_declaration)
                declaration["roles"] = [role]
                libraries = ["NUCODE_BLE", "NUCODE_BLE_Audio"]
                if (
                    ("hearing-access" in role)
                    or ("audio-control" in role)
                    or ("audio-media" in role)
                    or ("audio-call" in role)
                ):
                    libraries.append("NUCODE_BLE_Security")
                features = MODULE.resolve_library_features(ROOT, profile, libraries)
                result = MODULE.resolve_capabilities(
                    self.registry, [], features, declaration
                )
                self.assertEqual(
                    {
                        source
                        for source in result["generated"]["sources"]
                        if source.startswith(root)
                    },
                    expected_sources,
                )

    def test_audio_security_source_ownership_is_minimal(self) -> None:
        """! @brief 보안 Audio 역할은 pairing·bond backend만 선택하고 부가 profile을 제외합니다. """
        profile = MODULE.load_configuration_profile(ROOT, "adaptive")
        features = MODULE.resolve_library_features(
            ROOT, profile, ["NUCODE_BLE", "NUCODE_BLE_Audio", "NUCODE_BLE_Security"]
        )
        root = "libraries/NUCODE_BLE_Security/src"
        expected_sources = {
            f"{root}/NUCODE_BLE_Security.cpp",
            f"{root}/internal/security/SecurityBond.cpp",
            f"{root}/internal/security/SecurityOob.cpp",
            f"{root}/internal/security/SecurityPairing.cpp",
        }
        for role in (
            "ble-audio-hearing-access-server",
            "ble-audio-hearing-access-client",
            "ble-audio-control-device",
            "ble-audio-control-controller",
            "ble-audio-media-player",
            "ble-audio-media-client",
            "ble-audio-call-server",
            "ble-audio-call-client",
        ):
            with self.subTest(role=role):
                declaration = copy.deepcopy(self.empty_declaration)
                declaration["roles"] = [role]
                result = MODULE.resolve_capabilities(
                    self.registry, [], features, declaration
                )
                self.assertEqual(
                    {
                        source
                        for source in result["generated"]["sources"]
                        if source.startswith(root)
                    },
                    expected_sources,
                )

    def test_verified_role_presets_are_pairwise_exclusive(self) -> None:
        """! @brief 독립 firmware 역할인 검증 preset의 임의 동시 선택을 거부합니다. """
        roles = list(self.registry["roles"])
        self.assertEqual(len(roles), 35)
        for index, first in enumerate(roles):
            for second in roles[index + 1:]:
                with self.subTest(first=first, second=second):
                    declaration = copy.deepcopy(self.empty_declaration)
                    declaration["roles"] = [first, second]
                    with self.assertRaisesRegex(
                        MODULE.AdapterError, "E_ROLE_CONFLICT"
                    ):
                        MODULE.resolve_capabilities(
                            self.registry, [], [], declaration
                        )

    def test_all_iso_examples_publish_verified_role_declarations(self) -> None:
        """! @brief 공개 ISO 11예제가 각각 하나의 검증된 role sidecar를 제공합니다. """
        examples = {
            "CISCentral": "ble-iso-cis-central",
            "CISPeripheral": "ble-iso-cis-peripheral",
            "CISToBISPeer": "ble-iso-cis-to-bis-peer",
            "BISSource": "ble-iso-bis-source",
            "BISReceiver": "ble-iso-bis-receiver",
            "BISEncryptedSource": "ble-iso-bis-encrypted-source",
            "BISEncryptedReceiver": "ble-iso-bis-encrypted-receiver",
            "BISTimeSource": "ble-iso-bis-time-source",
            "BISTimeReceiver": "ble-iso-bis-time-receiver",
            "CISToBISBridge": "ble-iso-cis-to-bis-bridge",
            "CISToBISReceiver": "ble-iso-cis-to-bis-receiver",
        }
        root = ROOT / "libraries" / "NUCODE_BLE_ISO" / "examples"
        for example, role in examples.items():
            with self.subTest(example=example):
                declaration = MODULE.load_capability_declaration(root / example)
                self.assertEqual(declaration["roles"], [role])
                self.assertEqual(declaration["capabilities"], [])
                self.assertEqual(declaration["capacities"], {})

    def test_audio_bap_examples_publish_verified_role_declarations(self) -> None:
        """! @brief 공개 BAP 9예제가 각각 하나의 검증된 role sidecar를 제공합니다. """
        examples = {
            "BapUnicastSource": "ble-audio-unicast-source",
            "BapUnicastSink": "ble-audio-unicast-sink",
            "BapUnicastCycle": "ble-audio-unicast-cycle",
            "BapUnicastDuplexClient": "ble-audio-unicast-duplex-client",
            "BapUnicastDuplexServer": "ble-audio-unicast-duplex-server",
            "BapBroadcastSource": "ble-audio-broadcast-source",
            "BapBroadcastSink": "ble-audio-broadcast-sink",
            "BapBroadcastDelegatorSink": "ble-audio-broadcast-delegator-sink",
            "BapBroadcastAssistant": "ble-audio-broadcast-assistant",
        }
        root = ROOT / "libraries" / "NUCODE_BLE_Audio" / "examples"
        for example, role in examples.items():
            with self.subTest(example=example):
                declaration = MODULE.load_capability_declaration(root / example)
                self.assertEqual(declaration["roles"], [role])
                self.assertEqual(declaration["capabilities"], [])
                self.assertEqual(declaration["capacities"], {})

    def test_audio_hap_examples_publish_verified_role_declarations(self) -> None:
        """! @brief 공개 HAP 2예제가 각각 하나의 검증된 role sidecar를 제공합니다. """
        examples = {
            "HearingAccessServer": "ble-audio-hearing-access-server",
            "HearingAccessClient": "ble-audio-hearing-access-client",
        }
        root = ROOT / "libraries" / "NUCODE_BLE_Audio" / "examples"
        for example, role in examples.items():
            with self.subTest(example=example):
                declaration = MODULE.load_capability_declaration(root / example)
                self.assertEqual(declaration["roles"], [role])
                self.assertEqual(declaration["capabilities"], [])
                self.assertEqual(declaration["capacities"], {})

    def test_audio_control_examples_publish_verified_role_declarations(self) -> None:
        """! @brief 공개 Audio Control 2예제가 검증된 role sidecar를 제공합니다. """
        examples = {
            "AudioControlDevice": "ble-audio-control-device",
            "AudioControlController": "ble-audio-control-controller",
        }
        root = ROOT / "libraries" / "NUCODE_BLE_Audio" / "examples"
        for example, role in examples.items():
            with self.subTest(example=example):
                declaration = MODULE.load_capability_declaration(root / example)
                self.assertEqual(declaration["roles"], [role])
                self.assertEqual(declaration["capabilities"], [])
                self.assertEqual(declaration["capacities"], {})

    def test_audio_media_examples_publish_verified_role_declarations(self) -> None:
        """! @brief 공개 Media Control 2예제가 검증된 role sidecar를 제공합니다. """
        examples = {
            "MediaControlPlayer": "ble-audio-media-player",
            "MediaControlClient": "ble-audio-media-client",
        }
        root = ROOT / "libraries" / "NUCODE_BLE_Audio" / "examples"
        for example, role in examples.items():
            with self.subTest(example=example):
                declaration = MODULE.load_capability_declaration(root / example)
                self.assertEqual(declaration["roles"], [role])
                self.assertEqual(declaration["capabilities"], [])
                self.assertEqual(declaration["capacities"], {})

    def test_audio_call_examples_publish_verified_role_declarations(self) -> None:
        """! @brief 공개 Call Control 2예제가 검증된 role sidecar를 제공합니다. """
        examples = {
            "CallControlServer": "ble-audio-call-server",
            "CallControlClient": "ble-audio-call-client",
        }
        root = ROOT / "libraries" / "NUCODE_BLE_Audio" / "examples"
        for example, role in examples.items():
            with self.subTest(example=example):
                declaration = MODULE.load_capability_declaration(root / example)
                self.assertEqual(declaration["roles"], [role])
                self.assertEqual(declaration["capabilities"], [])
                self.assertEqual(declaration["capacities"], {})

    def test_ble_feature_without_role_and_role_combination_fail_closed(self) -> None:
        """! @brief BLE role 누락과 검증되지 않은 두 역할 조합을 모두 거부합니다. """
        profile = MODULE.load_configuration_profile(ROOT, "adaptive")
        features = MODULE.resolve_library_features(ROOT, profile, ["NUCODE_BLE"])
        with self.assertRaisesRegex(MODULE.AdapterError, "E_ROLE_REQUIRED"):
            MODULE.resolve_capabilities(
                self.registry, [], features, self.empty_declaration
            )

        declaration = copy.deepcopy(self.empty_declaration)
        declaration["roles"] = [
            "ble-gap-nus-dual-role",
            "ble-gatt-nus-dual-role",
        ]
        with self.assertRaisesRegex(MODULE.AdapterError, "E_ROLE_CONFLICT"):
            MODULE.resolve_capabilities(self.registry, [], features, declaration)

    def test_resolved_sources_filter_unselected_bundled_translation_units(self) -> None:
        """! @brief 선택 역할 밖의 bundled source를 제외하고 provenance를 결정적으로 남깁니다. """
        with tempfile.TemporaryDirectory(prefix="n54-p0-source-filter-") as temporary:
            root = Path(temporary)
            platform = root / "platform"
            source_root = platform / "libraries" / "Fixture" / "src"
            sketch = root / "sketch"
            app = root / "app"
            build = root / "build"
            source_root.mkdir(parents=True)
            sketch.mkdir()
            selected = source_root / "Selected.cpp"
            excluded_a = source_root / "ExcludedA.cpp"
            excluded_b = source_root / "ExcludedB.cpp"
            for source in (selected, excluded_a, excluded_b):
                source.write_text(f"int {source.stem} = 1;\n", encoding="utf-8")
            records = [
                {
                    "source": source.as_posix(),
                    "include_dirs": [source_root.as_posix()],
                }
                for source in (excluded_b, selected, excluded_a)
            ]
            paths = {
                "build_path": build,
                "sketch_root": sketch,
                "platform_root": platform,
                "app": app,
            }
            resolution = {
                "generated": {
                    "source_roots": ["libraries/Fixture/src"],
                    "sources": ["libraries/Fixture/src/Selected.cpp"],
                }
            }
            sources, provenance, _ = MODULE.write_source_manifest(
                paths, records, capability_resolution=resolution
            )
            self.assertEqual(sources, [selected.resolve()])
            self.assertEqual(
                [item["logical_identity"] for item in provenance["excluded_sources"]],
                [
                    "platform:libraries/Fixture/src/ExcludedA.cpp",
                    "platform:libraries/Fixture/src/ExcludedB.cpp",
                ],
            )
            manifest = (app / "sources.cmake").read_text(encoding="utf-8")
            self.assertIn("Selected.cpp", manifest)
            self.assertNotIn("ExcludedA.cpp", manifest)
            self.assertNotIn("ExcludedB.cpp", manifest)
            self.assertIn(
                source_root.resolve(),
                [Path(item["path"]).resolve() for item in provenance["include_roots"]],
            )

    def test_resolved_source_paths_fail_closed(self) -> None:
        """! @brief 손상된 source 해석 결과의 형식과 platform 이탈 경로를 거부합니다. """
        with tempfile.TemporaryDirectory(prefix="n54-p0-source-path-") as temporary:
            root = Path(temporary)
            platform = root / "platform"
            source_root = platform / "libraries" / "Fixture" / "src"
            sketch = root / "sketch"
            source_root.mkdir(parents=True)
            sketch.mkdir()
            paths = {
                "build_path": root / "build",
                "sketch_root": sketch,
                "platform_root": platform,
                "app": root / "app",
            }
            invalid_results = (
                {"generated": {"source_roots": "libraries/Fixture/src", "sources": []}},
                {"generated": {"source_roots": ["../outside"], "sources": []}},
            )
            for resolution in invalid_results:
                with self.subTest(resolution=resolution):
                    with self.assertRaisesRegex(MODULE.AdapterError, "E_CAPABILITY_RESULT"):
                        MODULE.write_source_manifest(
                            paths, [], capability_resolution=resolution
                        )

    def test_registry_rejects_unknown_required_role_reference(self) -> None:
        """! @brief capability의 역할 허용 목록도 registry 참조 무결성에 포함합니다. """
        with tempfile.TemporaryDirectory(prefix="n54-p0-role-ref-") as temporary:
            root = Path(temporary)
            registry_path = root / "variants" / "nu54dk" / "capability-registry.json"
            registry_path.parent.mkdir(parents=True)
            document = json.loads(
                (ROOT / "variants" / "nu54dk" / "capability-registry.json").read_text(
                    encoding="utf-8"
                )
            )
            document["capabilities"][0]["requires_any_role"] = ["missing-role"]
            registry_path.write_text(json.dumps(document), encoding="utf-8")
            for source_root in document["source_roots"]:
                (root / source_root).mkdir(parents=True, exist_ok=True)
            for capability in document["capabilities"]:
                for overlay in capability["overlays"]:
                    overlay_path = root / overlay
                    overlay_path.parent.mkdir(parents=True, exist_ok=True)
                    overlay_path.write_text("", encoding="utf-8")
                for source in capability["sources"]:
                    source_path = root / source
                    if (ROOT / source).is_dir():
                        source_path.mkdir(parents=True, exist_ok=True)
                    else:
                        source_path.parent.mkdir(parents=True, exist_ok=True)
                        source_path.write_text("", encoding="utf-8")
            with self.assertRaisesRegex(
                MODULE.AdapterError, "E_CAPABILITY_REFERENCE.*missing-role"
            ):
                MODULE.load_capability_registry(root)

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
