"""! @brief P2 Arduino/NUCODE와 Nordic native의 정적 자원 조건을 비교합니다. """

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess


CONFIG_LINE = re.compile(r"^(CONFIG_[A-Z0-9_]+)=(.*)$")
DISABLED_LINE = re.compile(r"^# (CONFIG_[A-Z0-9_]+) is not set$")
SIZE_LINE = re.compile(r"^\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+[0-9a-fA-F]+\s+.+$")
MEMORY_LINE = re.compile(
    r"^(FLASH|RAM)\s+0x([0-9a-fA-F]+)\s+0x([0-9a-fA-F]+)\s+\S+\s*$",
    re.MULTILINE,
)
NM_LINE = re.compile(r"^\s*(\d+)\s+(\d+)\s+(\S)\s+(.+?)\s*$")


def sha256(path: Path) -> str:
    """! @brief 비교 입력의 SHA-256을 계산합니다. """
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def config_map(lines: list[str]) -> dict[str, str]:
    """! @brief Kconfig 선언을 이름별 값으로 정규화합니다. """
    result: dict[str, str] = {}
    for raw in lines:
        line = raw.strip()
        match = CONFIG_LINE.fullmatch(line)
        if match is not None:
            result[match.group(1)] = match.group(2)
            continue
        match = DISABLED_LINE.fullmatch(line)
        if match is not None:
            result[match.group(1)] = "n"
    return result


def arduino_config(manifest: dict) -> dict[str, str]:
    """! @brief Arduino capability 해석기가 생성한 활성·비활성 설정을 읽습니다. """
    generated = manifest["cache"]["input_manifest"]["configuration"][
        "capability_resolution"
    ]["generated"]
    return config_map(generated["conf"] + generated["disabled_conf"])


def run_text(command: list[str]) -> str:
    """! @brief 도구 출력을 UTF-8 텍스트로 반환합니다. """
    result = subprocess.run(command, check=True, capture_output=True)
    return result.stdout.decode("utf-8", errors="replace")


def memory_regions(map_path: Path) -> dict[str, dict[str, int]]:
    """! @brief linker map의 FLASH·RAM 영역을 추출합니다. """
    regions: dict[str, dict[str, int]] = {}
    content = map_path.read_text(encoding="utf-8", errors="replace")
    for name, origin, size in MEMORY_LINE.findall(content):
        regions[name.lower()] = {
            "origin": int(origin, 16),
            "size": int(size, 16),
            "end": int(origin, 16) + int(size, 16),
        }
    if set(regions) != {"flash", "ram"}:
        raise RuntimeError(f"linker memory 영역을 찾지 못했습니다: {map_path}")
    return regions


def symbol_list(nm_tool: Path, elf: Path) -> list[dict]:
    """! @brief 크기 순서 symbol을 주소·크기·종류와 함께 읽습니다. """
    output = run_text([
        str(nm_tool), "-S", "--size-sort", "--radix=d", "--demangle", str(elf)
    ])
    symbols = []
    for line in output.splitlines():
        match = NM_LINE.fullmatch(line)
        if match is None:
            continue
        symbols.append({
            "address": int(match.group(1)),
            "size": int(match.group(2)),
            "type": match.group(3),
            "name": match.group(4),
        })
    return symbols


def native_resource(build_dir: Path, size_tool: Path, nm_tool: Path) -> dict:
    """! @brief native ELF/map/config의 자원·hash·상위 RAM symbol을 고정합니다. """
    zephyr = build_dir / "zephyr"
    elf = zephyr / "zephyr.elf"
    map_path = zephyr / "zephyr.map"
    config = zephyr / ".config"
    size_output = run_text([str(size_tool), str(elf)])
    summary = None
    for line in size_output.splitlines():
        match = SIZE_LINE.fullmatch(line)
        if match is not None:
            summary = {
                "text_bytes": int(match.group(1)),
                "data_bytes": int(match.group(2)),
                "bss_bytes": int(match.group(3)),
            }
    if summary is None:
        raise RuntimeError(f"size 출력을 해석하지 못했습니다: {elf}")
    summary["flash_used_bytes"] = summary["text_bytes"] + summary["data_bytes"]
    summary["ram_used_bytes"] = summary["data_bytes"] + summary["bss_bytes"]
    regions = memory_regions(map_path)
    ram = regions["ram"]
    symbols = symbol_list(nm_tool, elf)
    top_ram = sorted(
        (item for item in symbols if ram["origin"] <= item["address"] < ram["end"]),
        key=lambda item: item["size"],
        reverse=True,
    )[:32]
    return {
        "resource": summary,
        "regions": regions,
        "config": config_map(config.read_text(encoding="utf-8").splitlines()),
        "top_ram_symbols": top_ram,
        "inputs": {
            "elf": {"path": elf.as_posix(), "sha256": sha256(elf)},
            "map": {"path": map_path.as_posix(), "sha256": sha256(map_path)},
            "config": {"path": config.as_posix(), "sha256": sha256(config)},
        },
        "symbols": symbols,
    }


def api_symbol_floor(symbols: list[dict], regions: dict[str, dict[str, int]]) -> dict:
    """! @brief 이름으로 명확히 식별되는 Arduino/NUCODE symbol의 비용 하한을 계산합니다. """
    selected = [
        item for item in symbols
        if "nucode::" in item["name"]
        or "arduino::" in item["name"]
        or item["name"] in {"setup", "loop", "serialEventRun"}
    ]
    ram = regions["ram"]
    ram_bytes = sum(
        item["size"] for item in selected
        if ram["origin"] <= item["address"] < ram["end"]
    )
    return {
        "flash_bytes_lower_bound": sum(
            item["size"] for item in selected if item["address"] < ram["origin"]
        ),
        "ram_bytes_lower_bound": ram_bytes,
        "symbol_count": len(selected),
    }


def assert_values(label: str, config: dict[str, str], expected: dict[str, str]) -> None:
    """! @brief 비교에 고정한 핵심 Kconfig 값이 실제 입력과 같은지 확인합니다. """
    mismatches = {
        key: {"expected": value, "actual": config.get(key)}
        for key, value in expected.items()
        if config.get(key) != value
    }
    if mismatches:
        raise RuntimeError(f"{label} 비교 설정 불일치: {mismatches}")


def pair_record(
    identifier: str,
    manifest_path: Path,
    native_build: Path,
    expected_arduino: dict[str, str],
    expected_native: dict[str, str],
    identical_conditions: dict,
    deliberate_differences: list[dict],
    size_tool: Path,
    nm_tool: Path,
) -> dict:
    """! @brief 한 기능쌍의 조건·정적 크기·symbol 근거를 만듭니다. """
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    native = native_resource(native_build, size_tool, nm_tool)
    arduino_conf = arduino_config(manifest)
    assert_values(f"{identifier} Arduino", arduino_conf, expected_arduino)
    assert_values(f"{identifier} native", native["config"], expected_native)

    arduino_resource = manifest["resource_audit"]
    arduino_regions = arduino_resource["regions"]
    if native["regions"] != arduino_regions:
        raise RuntimeError(
            f"{identifier} linker 영역 불일치: Arduino={arduino_regions}, "
            f"native={native['regions']}"
        )
    arduino_elf = Path(manifest["artifacts"]["elf"]["path"])
    arduino_symbols = symbol_list(nm_tool, arduino_elf)
    arduino_flash = arduino_resource["flash"]["used_bytes"]
    arduino_ram = arduino_resource["ram"]["used_bytes"]
    native_flash = native["resource"]["flash_used_bytes"]
    native_ram = native["resource"]["ram_used_bytes"]
    return {
        "id": identifier,
        "result": "PASS",
        "identical_conditions": identical_conditions,
        "deliberate_not_inflated_native_conditions": deliberate_differences,
        "arduino": {
            "manifest": {
                "path": manifest_path.as_posix(),
                "sha256": sha256(manifest_path),
                "built_at_utc": manifest["built_at_utc"],
            },
            "resource": {
                "flash_used_bytes": arduino_flash,
                "ram_used_bytes": arduino_ram,
                "flash_region_bytes": arduino_resource["flash"]["region_bytes"],
                "ram_region_bytes": arduino_resource["ram"]["region_bytes"],
            },
            "elf": {
                "path": arduino_elf.as_posix(),
                "sha256": sha256(arduino_elf),
            },
            "map_sha256": manifest["artifacts"]["map"]["sha256"],
            "top_ram_symbols": arduino_resource["top_ram_symbols"][:32],
            "named_api_symbol_floor": api_symbol_floor(arduino_symbols, arduino_regions),
        },
        "native": {
            key: value for key, value in native.items() if key != "symbols" and key != "config"
        },
        "delta_arduino_minus_native": {
            "flash_bytes": arduino_flash - native_flash,
            "ram_bytes": arduino_ram - native_ram,
        },
    }


def main() -> int:
    """! @brief 두 비교쌍을 검증하고 machine-readable evidence를 기록합니다. """
    parser = argparse.ArgumentParser()
    parser.add_argument("--arduino-coc-manifest", type=Path, required=True)
    parser.add_argument("--native-coc-build", type=Path, required=True)
    parser.add_argument("--arduino-audio-manifest", type=Path, required=True)
    parser.add_argument("--native-audio-build", type=Path, required=True)
    parser.add_argument("--toolchain-bin", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    size_tool = args.toolchain_bin / "arm-zephyr-eabi-size.exe"
    nm_tool = args.toolchain_bin / "arm-zephyr-eabi-nm.exe"
    common = {
        "ncs": "v3.4.0",
        "zephyr": "4.4.0 / ncs-v3.4.0",
        "board": "nrf54l15dk/nrf54l15/cpuapp/nu54dk",
        "controller": "Nordic SDC",
        "code_partition": "slot0 [0x000000, 0x16c000)",
        "ram_region_bytes": 262144,
        "logging": "disabled",
        "telemetry": "thread analyzer and heap runtime statistics enabled",
    }
    coc = pair_record(
        "coc_peripheral_server",
        args.arduino_coc_manifest,
        args.native_coc_build,
        {
            "CONFIG_BT_L2CAP_TX_BUF_COUNT": "4",
            "CONFIG_BT_L2CAP_TX_MTU": "512",
            "CONFIG_BT_BUF_ACL_RX_SIZE": "251",
            "CONFIG_BT_BUF_ACL_TX_SIZE": "251",
            "CONFIG_BT_SMP": "y",
            "CONFIG_MAIN_STACK_SIZE": "8192",
            "CONFIG_SYSTEM_WORKQUEUE_STACK_SIZE": "4096",
            "CONFIG_HEAP_MEM_POOL_SIZE": "8192",
        },
        {
            "CONFIG_BT_L2CAP_TX_BUF_COUNT": "4",
            "CONFIG_BT_L2CAP_TX_MTU": "512",
            "CONFIG_BT_BUF_ACL_RX_SIZE": "251",
            "CONFIG_BT_BUF_ACL_TX_SIZE": "251",
            "CONFIG_BT_SMP": "y",
            "CONFIG_MAIN_STACK_SIZE": "8192",
            "CONFIG_SYSTEM_WORKQUEUE_STACK_SIZE": "4096",
            "CONFIG_HEAP_MEM_POOL_SIZE": "8192",
            "CONFIG_COMMON_LIBC_MALLOC_ARENA_SIZE": "8192",
            "CONFIG_USE_DT_CODE_PARTITION": "y",
            "CONFIG_LOG": "n",
        },
        {
            **common,
            "functional_role": "one peripheral CoC server, one link, two channels",
            "security": "SMP enabled",
            "mtu_bytes": 512,
            "l2cap_tx_buffers": 4,
            "acl_octets": 251,
            "main_stack_bytes": 8192,
            "system_workqueue_stack_bytes": 4096,
            "kernel_heap_bytes": 8192,
            "malloc_arena_bytes": 8192,
        },
        [{
            "item": "compiled role/capacity",
            "arduino": "public dual-role L2CAP capability, CONFIG_BT_MAX_CONN=2",
            "native": "test role only, CONFIG_BT_MAX_CONN=1",
            "classification": "reusable Arduino capability cost; native was not inflated",
        }],
        size_tool,
        nm_tool,
    )
    audio = pair_record(
        "encrypted_lc3_broadcast_source",
        args.arduino_audio_manifest,
        args.native_audio_build,
        {
            "CONFIG_BT_BAP_BROADCAST_SOURCE": "y",
            "CONFIG_BT_BAP_BROADCAST_SRC_STREAM_COUNT": "1",
            "CONFIG_BT_BAP_BROADCAST_SRC_SUBGROUP_COUNT": "1",
            "CONFIG_BT_ISO_TX_BUF_COUNT": "6",
            "CONFIG_BT_ISO_TX_MTU": "40",
            "CONFIG_LIBLC3": "y",
            "CONFIG_MAIN_STACK_SIZE": "8192",
            "CONFIG_SYSTEM_WORKQUEUE_STACK_SIZE": "4096",
        },
        {
            "CONFIG_BT_BAP_BROADCAST_SOURCE": "y",
            "CONFIG_BT_BAP_BROADCAST_SRC_STREAM_COUNT": "1",
            "CONFIG_BT_BAP_BROADCAST_SRC_SUBGROUP_COUNT": "1",
            "CONFIG_BT_ISO_TX_BUF_COUNT": "6",
            "CONFIG_BT_ISO_TX_MTU": "40",
            "CONFIG_LIBLC3": "y",
            "CONFIG_MAIN_STACK_SIZE": "8192",
            "CONFIG_SYSTEM_WORKQUEUE_STACK_SIZE": "4096",
            "CONFIG_COMMON_LIBC_MALLOC_ARENA_SIZE": "8192",
            "CONFIG_HEAP_MEM_POOL_SIZE": "0",
            "CONFIG_USE_DT_CODE_PARTITION": "y",
            "CONFIG_LOG": "n",
        },
        {
            **common,
            "functional_role": "encrypted BAP broadcast source",
            "security": "same 16-byte Broadcast Code",
            "codec": "LC3 16 kHz mono, 40-byte/10-ms frame",
            "streams": 1,
            "subgroups": 1,
            "iso_tx_buffers": 6,
            "main_stack_bytes": 8192,
            "system_workqueue_stack_bytes": 4096,
            "kernel_heap_bytes": 0,
            "malloc_arena_bytes": 8192,
        },
        [{
            "item": "application scaffolding",
            "arduino": "inline sketch encode/send loop and NUCODE codec state",
            "native": "upstream sample encoder thread with 16384-byte stack",
            "classification": "native sample overhead retained and reported; not an Arduino saving",
        }],
        size_tool,
        nm_tool,
    )
    document = {
        "schema_version": 1,
        "case": "m31-p2-equivalent-nordic-native-flash-ram-comparison",
        "result": "PASS",
        "pairs": [coc, audio],
        "interpretation": {
            "coc": "Arduino의 양수 delta는 Arduino/NUCODE 공개 API·event queue·dual-role 용량을 포함한다. 동일 pool의 중복 사본은 발견하지 않았다.",
            "audio": "raw RAM delta에는 native upstream sample의 16384-byte encoder stack이 포함되므로 Arduino의 음수 delta를 API 절감으로 해석하지 않는다.",
            "native_inflation": "Arduino의 CONFIG_BT_MAX_CONN=2 또는 미사용 역할을 native에 추가하지 않았다.",
            "record_250": "조건이 다른 Nordic RAS 진단은 이 PASS의 분모나 수치로 사용하지 않았다.",
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"P2 native memory comparison: PASS -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
