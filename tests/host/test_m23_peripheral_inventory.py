#!/usr/bin/env python3
"""M23 peripheral manifest, generated API and ownership contract tests."""

from __future__ import annotations

import copy
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from host_compiler import compiler_command


REPOSITORY = Path(__file__).resolve().parents[2]
SCRIPT = REPOSITORY / "tools" / "peripheral" / "verify_m23_inventory.py"
SPEC = importlib.util.spec_from_file_location("nucode_m23_inventory", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class M23PeripheralInventoryTests(unittest.TestCase):
    """Fail-closed inventory and allocation semantics."""

    def setUp(self) -> None:
        self.manifest = MODULE.strict_json_object(MODULE.MANIFEST_PATH)
        self.instances = MODULE.validate_inventory(self.manifest)

    def test_schema_inventory_sources_and_generated_outputs_pass(self) -> None:
        MODULE.validate_schema_contract(MODULE.strict_json_object(MODULE.SCHEMA_PATH))
        MODULE.validate_repository_sources(self.instances)
        self.assertEqual(len(self.instances), 75)
        self.assertEqual(set(item["id"] for item in self.instances), MODULE.EXPECTED_IDS)
        result = subprocess.run(
            [os.fspath(Path(os.sys.executable)), os.fspath(SCRIPT)],
            cwd=REPOSITORY,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertIn("M23_INVENTORY_PASS=instances:75", result.stdout)

    def test_exhaustive_instance_omission_is_rejected(self) -> None:
        mutated = copy.deepcopy(self.manifest)
        mutated["instances"] = [
            item for item in mutated["instances"] if item["id"] != "twis21"
        ]
        with self.assertRaisesRegex(MODULE.InventoryFailure, "missing=.*twis21"):
            MODULE.validate_inventory(mutated)

    def test_public_object_alias_is_rejected(self) -> None:
        mutated = copy.deepcopy(self.manifest)
        lookup = {item["id"]: item for item in mutated["instances"]}
        lookup["uarte21"]["public_object"] = "Serial1"
        lookup["uarte21"]["public_api"] = ["Nu54HardwareSerial"]
        lookup["uarte21"]["states"]["source"] = "implemented"
        lookup["uarte21"]["states"]["exposure"] = "public"
        with self.assertRaisesRegex(MODULE.InventoryFailure, "alias is forbidden"):
            MODULE.validate_inventory(mutated)

    def test_same_serial_block_personality_set_is_exact(self) -> None:
        mutated = copy.deepcopy(self.manifest)
        lookup = {item["id"]: item for item in mutated["instances"]}
        lookup["spis22"]["sharing_group"] = "serial21"
        with self.assertRaisesRegex(MODULE.InventoryFailure, "serial21 personality set mismatch"):
            MODULE.validate_inventory(mutated)

    def test_pinned_ncs_dts_checksum_and_labels_are_verified(self) -> None:
        installed = Path("C:/ncs/v3.4.0")
        if not installed.is_dir():
            self.skipTest("exact NCS v3.4.0 workspace is not installed")
        MODULE.validate_ncs_dts(self.manifest["identity"], installed)

        with tempfile.TemporaryDirectory() as temporary:
            temporary_root = Path(temporary)
            for source in self.manifest["identity"]["soc_dts_sources"]:
                destination = temporary_root / source["path"]
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(installed / source["path"], destination)
            first = temporary_root / self.manifest["identity"]["soc_dts_sources"][0]["path"]
            first.write_bytes(first.read_bytes() + b"\n")
            with self.assertRaisesRegex(MODULE.InventoryFailure, "checksum mismatch"):
                MODULE.validate_ncs_dts(self.manifest["identity"], temporary_root)

    def test_public_inventory_api_compiles_links_and_runs(self) -> None:
        compiler = compiler_command()
        build_root = REPOSITORY / "build"
        build_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=build_root) as temporary:
            root = Path(temporary)
            harness = root / "m23_inventory.cpp"
            harness.write_text(
                r'''
#include <nucode/PeripheralInventory.h>

#include <cstdint>
#include <cstring>

int main()
{
    using namespace nucode::arduino;
    if (peripheralInventorySize() != 75U || peripheralInventoryAt(75U) != nullptr)
    {
        return 1;
    }
    const auto *serial = findPeripheralByObject("Serial");
    const auto *serial1 = findPeripheralByObject("Serial1");
    const auto *wire = findPeripheralByObject("Wire");
    const auto *spi = findPeripheralByObject("SPI");
    if (serial == nullptr || serial1 == nullptr || wire == nullptr || spi == nullptr ||
        std::strcmp(serial->id, "uarte20") != 0 ||
        std::strcmp(serial1->id, "uarte30") != 0 ||
        std::strcmp(wire->id, "twim22") != 0 ||
        std::strcmp(spi->id, "spim00") != 0 ||
        findPeripheralByObject("Serial2") != nullptr)
    {
        return 2;
    }
    const auto *twis22 = findPeripheral(PeripheralKind::twis, 22U);
    if (twis22 == nullptr || std::strcmp(twis22->sharing_group, "serial22") != 0 ||
        twis22->source_state != PeripheralSourceState::implemented ||
        twis22->exposure_state != PeripheralExposureState::internal ||
        twis22->hil_state != PeripheralVerificationState::pass)
    {
        return 3;
    }
    if (!hasPeripheralDmaCapability(spi->dma_capabilities,
                                    PeripheralDmaCapability::hardware) ||
        !hasPeripheralDmaCapability(spi->dma_capabilities,
                                    PeripheralDmaCapability::synchronous_api) ||
        hasPeripheralDmaCapability(spi->dma_capabilities,
                                   PeripheralDmaCapability::asynchronous_api))
    {
        return 4;
    }
    char text[320]{};
    const auto length = formatPeripheralIdentity(*serial1, text, sizeof(text));
    if (length != std::strlen(text) ||
        std::strstr(text, "NU54:PERIPHERAL:uarte30:kind=uarte:instance=30") == nullptr ||
        std::strstr(text, "block=serial30") == nullptr ||
        std::strstr(text, "object=Serial1") == nullptr ||
        std::strstr(text, "hil=pass:concurrent=partial") == nullptr ||
        formatPeripheralIdentity(*serial1, nullptr, 0U) != length)
    {
        return 5;
    }
    char truncated[8]{};
    if (formatPeripheralIdentity(*serial1, truncated, sizeof(truncated)) != length ||
        truncated[sizeof(truncated) - 1U] != '\0')
    {
        return 6;
    }
    if (std::strcmp(peripheralKindToken(static_cast<PeripheralKind>(0xffU)), "unknown") != 0 ||
        std::strcmp(peripheralRouteStateToken(static_cast<PeripheralRouteState>(0xffU)), "unknown") != 0 ||
        std::strcmp(peripheralSourceStateToken(static_cast<PeripheralSourceState>(0xffU)), "unknown") != 0 ||
        std::strcmp(peripheralExposureStateToken(static_cast<PeripheralExposureState>(0xffU)), "unknown") != 0 ||
        std::strcmp(peripheralVerificationStateToken(
                        static_cast<PeripheralVerificationState>(0xffU)), "unknown") != 0)
    {
        return 7;
    }
    return 0;
}
'''.strip()
                + "\n",
                encoding="utf-8",
            )
            executable = root / ("m23_inventory.exe" if os.name == "nt" else "m23_inventory")
            command = [
                *compiler,
                "-std=c++17",
                f"-I{REPOSITORY / 'cores' / 'arduino'}",
                os.fspath(harness),
                os.fspath(REPOSITORY / "cores" / "arduino" / "peripheral_inventory.cpp"),
                "-o",
                os.fspath(executable),
            ]
            compiled = subprocess.run(command, capture_output=True, text=True, check=False)
            self.assertEqual(compiled.returncode, 0, msg=compiled.stdout + compiled.stderr)
            try:
                executed = subprocess.run(
                    [os.fspath(executable)], capture_output=True, text=True, check=False
                )
            except OSError as error:
                if os.name == "nt" and getattr(error, "winerror", None) == 4551:
                    self.skipTest("Windows Application Control blocked the generated test executable")
                raise
            self.assertEqual(executed.returncode, 0, msg=executed.stdout + executed.stderr)

    def test_common_ownership_contract_lists_dma_and_event_resources(self) -> None:
        header = (
            REPOSITORY / "cores" / "arduino" / "internal" / "IoResourceManager.h"
        ).read_text(encoding="utf-8")
        implementation = (
            REPOSITORY / "cores" / "arduino" / "internal" / "resource" / "IoResourcePolicy.h"
        ).read_text(encoding="utf-8")
        for token in (
            "gpiote_channel", "dppi_channel", "dppi_group", "timer_channel",
            "dma_memory", "interrupt_line", "clock_domain",
        ):
            self.assertIn(token, header)
        self.assertIn("io_resource_lease_capacity = 16U", header)
        self.assertIn("dmaMemoryIoResource", header)
        self.assertIn("overlappingDmaMemory", implementation)
        self.assertIn("resourcesConflict", implementation)

    def test_common_ownership_dma_and_block_semantics_run_on_host(self) -> None:
        compiler = compiler_command()
        build_root = REPOSITORY / "build"
        build_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=build_root) as temporary:
            root = Path(temporary)
            kernel = root / "zephyr" / "kernel.h"
            kernel.parent.mkdir(parents=True, exist_ok=True)
            kernel.write_text(
                r'''
#ifndef ZEPHYR_KERNEL_H_
#define ZEPHYR_KERNEL_H_
struct k_mutex {};
#define K_MUTEX_DEFINE(name) k_mutex name
#define K_FOREVER 0
static inline bool k_is_in_isr() { return false; }
static inline int k_mutex_lock(k_mutex *, int) { return 0; }
static inline int k_mutex_unlock(k_mutex *) { return 0; }
#endif
'''.strip()
                + "\n",
                encoding="utf-8",
            )
            gpio = root / "zephyr" / "drivers" / "gpio.h"
            gpio.parent.mkdir(parents=True, exist_ok=True)
            gpio.write_text(
                r'''
#ifndef ZEPHYR_DRIVERS_GPIO_H_
#define ZEPHYR_DRIVERS_GPIO_H_
#include <stdint.h>
struct gpio_dt_spec { const void *port; uint32_t pin; uint32_t dt_flags; };
#endif
'''.strip()
                + "\n",
                encoding="utf-8",
            )
            harness = root / "m23_ownership.cpp"
            harness.write_text(
                r'''
#include "internal/IoResourceManager.h"

#include <cstdint>

int main()
{
    using namespace nucode::arduino::internal;
    alignas(4) static std::uint8_t memory[128]{};
    static std::uint8_t domain_a;
    static std::uint8_t domain_b;
    resetIoResourceManagerForTest();

    const IoResourceId first[] = {
        peripheralIoResource(IoResourceKind::serial_block, 21U),
        peripheralIoResource(IoResourceKind::dppi_channel, 3U, &domain_a),
        peripheralIoResource(IoResourceKind::timer_channel, 1U, &domain_a),
        dmaMemoryIoResource(&memory[0], 32U),
    };
    IoResourceLease uart{};
    if (reserveIoResources({IoOwnerKind::serial, 21U}, first, 4U,
                           IoAcquirePolicy::exclusive, uart) != IoResourceResult::success ||
        commitIoResources(uart) != IoResourceResult::success)
    {
        return 1;
    }

    const auto same_block = peripheralIoResource(IoResourceKind::serial_block, 21U);
    IoResourceLease personality_conflict{};
    if (reserveIoResources({IoOwnerKind::spi, 21U}, &same_block, 1U,
                           IoAcquirePolicy::exclusive, personality_conflict) !=
        IoResourceResult::conflict)
    {
        return 2;
    }

    const IoResourceId second[] = {
        peripheralIoResource(IoResourceKind::serial_block, 22U),
        peripheralIoResource(IoResourceKind::dppi_channel, 4U, &domain_b),
        peripheralIoResource(IoResourceKind::timer_channel, 2U, &domain_b),
        dmaMemoryIoResource(&memory[32], 32U),
    };
    IoResourceLease wire{};
    if (reserveIoResources({IoOwnerKind::wire, 22U}, second, 4U,
                           IoAcquirePolicy::exclusive, wire) != IoResourceResult::success ||
        commitIoResources(wire) != IoResourceResult::success)
    {
        return 3;
    }

    const auto overlap = dmaMemoryIoResource(&memory[16], 32U);
    IoResourceLease overlap_lease{};
    IoResourceSnapshot conflict{};
    if (reserveIoResources({IoOwnerKind::application, 0U}, &overlap, 1U,
                           IoAcquirePolicy::exclusive, overlap_lease, &conflict) !=
            IoResourceResult::conflict ||
        conflict.state != IoResourceState::active)
    {
        return 4;
    }
    const IoResourceId duplicate_ranges[] = {
        dmaMemoryIoResource(&memory[64], 32U),
        dmaMemoryIoResource(&memory[72], 8U),
    };
    IoResourceLease invalid_batch{};
    if (reserveIoResources({IoOwnerKind::application, 1U}, duplicate_ranges, 2U,
                           IoAcquirePolicy::exclusive, invalid_batch) !=
        IoResourceResult::invalid_argument)
    {
        return 5;
    }
    const IoResourceId invalid_offset = {
        IoResourceKind::dma_memory, &memory[0], 1U, 16U,
    };
    IoResourceLease invalid_offset_lease{};
    if (reserveIoResources({IoOwnerKind::application, 2U}, &invalid_offset, 1U,
                           IoAcquirePolicy::exclusive, invalid_offset_lease) !=
        IoResourceResult::invalid_argument)
    {
        return 6;
    }
    if (releaseIoResources(wire) != IoResourceResult::success ||
        releaseIoResources(uart) != IoResourceResult::success)
    {
        return 7;
    }
    return 0;
}
'''.strip()
                + "\n",
                encoding="utf-8",
            )
            executable = root / ("m23_ownership.exe" if os.name == "nt" else "m23_ownership")
            command = [
                *compiler,
                "-std=c++17",
                "-DCONFIG_ZTEST=1",
                "-DCONFIG_NUCODE_ARDUINO_IO_RESOURCE_SLOTS=48",
                f"-I{root}",
                f"-I{REPOSITORY / 'cores' / 'arduino'}",
                os.fspath(REPOSITORY / "cores/arduino/internal/resource/IoResourceTable.cpp"),
                os.fspath(harness),
                os.fspath(
                    REPOSITORY
                    / "cores"
                    / "arduino"
                    / "internal"
                    / "io_resource_manager.cpp"
                ),
                "-o",
                os.fspath(executable),
            ]
            compiled = subprocess.run(command, capture_output=True, text=True, check=False)
            self.assertEqual(compiled.returncode, 0, msg=compiled.stdout + compiled.stderr)
            try:
                executed = subprocess.run(
                    [os.fspath(executable)], capture_output=True, text=True, check=False
                )
            except OSError as error:
                if os.name == "nt" and getattr(error, "winerror", None) == 4551:
                    self.skipTest("Windows Application Control blocked the generated test executable")
                raise
            self.assertEqual(executed.returncode, 0, msg=executed.stdout + executed.stderr)



if __name__ == "__main__":
    unittest.main(verbosity=2)
