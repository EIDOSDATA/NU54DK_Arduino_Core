#!/usr/bin/env python3
"""! @brief 고정 SDK 진단 template build와 유한 DTM 두 보드 검증 도구. """
from __future__ import annotations

import argparse
from contextlib import ExitStack, contextmanager, redirect_stderr, redirect_stdout
import hashlib
import io
import json
import logging
import os
from pathlib import Path
import re
import shutil
import subprocess
import struct
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = ROOT / "templates/bluetooth/diagnostics"
LOCK = json.loads((ROOT / "tools/ci/ncs-3.4.0.lock.json").read_text(encoding="utf-8"))
BOARD = "nrf54l15dk/nrf54l15/cpuapp/nu54dk"
IDENTITY_FILES = ("CMakeLists.txt", "Kconfig", "prj.conf", "hci.conf", "app.overlay", "src/main.c", "src/protocol.h")
## @brief NCS 3.4.0 MDK nrf54l15_global.h/types.h의 secure RADIO 주소와 write-only task입니다.
RADIO_DISABLE = 0x5008A010
RADIO_STATE = 0x5008A520
RADIO_DISABLED = 0
RADIO_BASE = 0x5008A000
## @brief W02 SoftDevice STOP 뒤 남을 수 있는 PHYEND→DISABLE shortcut이며 radio를 시작하지 않습니다.
RADIO_PASSIVE_SHORTS = 1 << 19
RADIO_SUBSCRIBE = (0x100, 0x104, 0x108, 0x10C, 0x110, 0x114, 0x118, 0x11C, 0x120,
                   0x124, 0x128, 0x12C, 0x138, 0x13C, 0x16C, 0x1A0, 0x1A4)
RADIO_PUBLISH = (0x300, 0x304, 0x308, 0x30C, 0x310, 0x314, 0x318, 0x31C, 0x320,
                 0x324, 0x328, 0x32C, 0x330, 0x338, 0x33C, 0x340, 0x344, 0x348,
                 0x34C, 0x350, 0x354, 0x358, 0x35C, 0x3B0, 0x3BC, 0x3C0, 0x3C8)
WDT_BASES = (0x50108000, 0x50109000)
WDT_ROUTES = (0x80, 0x84, 0x180, 0x184)
DHCSR = 0xE000EDF0
DHCSR_RESET = 1 << 25
DHCSR_HALTED = (1 << 17) | 3
AUDIT_INTERVAL = 0.1
THIRD_IDLE_SCHEMA = "nucode-m33-w04-third-idle-v1"
## @brief Host fixture가 사용하는 과거 W02 기준이며 실제 준비는 항상 current revision을 요구합니다.
W02_IDLE_CORE_REVISION = "4ebd49521d4a6578beac91ebddbd1bf39d679db4"
THIRD_IDLE_FILES = ("evidence", "transcript", "image", "config", "sysbuild", "elf")
THIRD_IDLE_SOURCES = tuple("tests/zephyr/m33_profile_hil/" + name for name in
                           ("CMakeLists.txt", "prj.conf", "app.overlay", "src/main.cpp"))
THIRD_IDLE_SYMBOLS = {"nonce": 33, "started": 1, "cleanup_complete": 1,
                      "stop_reported": 1, "failed": 1, "watchdog_channel": 4}
## @brief board loaderless application 영역만 허용하며 FS/settings/UICR는 program하지 않습니다.
APPLICATION_END = 0x16C000
FLASH_SECTOR = 0x1000
PREPARATION_ROLES = ("tx", "rx", "third")
SAFE_SESSION_OPTIONS = {
    "target_override": "nrf54l", "frequency": 500000, "connect_mode": "attach",
    "auto_unlock": False, "resume_on_disconnect": False, "no_config": True,
    "cmsis_dap.prefer_v1": False, "cmsis_dap.limit_packets": True,
    "smart_flash": False, "hide_programming_progress": True,
    "cache.enable_memory": False, "cache.enable_register": False,
    "reset_type": "sysresetreq", "flash.timeout.init": 30.0,
    "flash.timeout.program": 10.0,
    "flash.timeout.erase_sector": 10.0,
}
## @brief pyOCD의 process 전역 cwd·logging·stream 상태를 병렬 session 사이에서 보호합니다.
_PRIVATE_DEBUG_LOCK = threading.RLock()
ROUTES = {
    "dtm_twowire": ("nrf/samples/bluetooth/direct_test_mode", "template", "DAPLink VCOM 19200 8N1; 3초 RF lease"),
    "dtm_hci": ("nrf/samples/bluetooth/direct_test_mode", "template", "DAPLink VCOM H4 115200 8N1; 진단 command만 허용"),
    "controller": ("zephyr/samples/bluetooth/hci_uart", "template", "UART30 H4 raw controller; Host stack과 독점"),
    "uart": ("zephyr/samples/bluetooth/hci_uart", "template", "UART30 1M TX/RX/RTS/CTS; 외부 H4 Host 결선 필요"),
    "async": ("zephyr/samples/bluetooth/hci_uart_async", "template", "UART30 async 1M TX/RX/RTS/CTS; 외부 H4 Host 필요"),
    "threewire": ("zephyr/samples/bluetooth/hci_uart_3wire", "template", "UART30 H5 1M TX/RX/GND; H5 peer 필요"),
    "lpuart": ("nrf/samples/bluetooth/hci_lpuart", "template", "UART30 1M TX/RX/REQ/RDY; nordic,nrf-sw-lpuart peer 필요"),
    "spi": ("zephyr/samples/bluetooth/hci_spi", "template", "SPIS00 SCK/MOSI/MISO/CS/IRQ/GND; 전용 외부 Host 필요"),
    "power_control": ("zephyr/samples/bluetooth/hci_pwr_ctrl", "template", "고정 native 동적 TX power sample; Arduino RssiPowerControl 예제도 제공"),
    "scan_request": ("zephyr/samples/bluetooth/hci_vs_scan_req", "template", "SDC 표준 extended advertising scanned callback 대체 경로; active scanner 필요"),
    "power_profiling": ("nrf/samples/bluetooth/peripheral_power_profiling", "template", "NFC 제외; 버튼 광고/notification; 정밀 전력계 측정은 사용자 후속"),
    "usb": ("zephyr/samples/bluetooth/hci_usb", "excluded", "nRF54L15에 native USB device controller 없음; DAPLink USB는 SoC HCI USB가 아님"),
    "ipc": ("zephyr/samples/bluetooth/hci_ipc", "excluded", "고정 sample platform_allow는 nRF5340 cpunet; NU54DK application/SDC 배치와 다름"),
    "rpc": ("nrf/samples/bluetooth/rpc_host", "excluded", "고정 sample은 nRF5340 cpunet Bluetooth RPC 서버; HCI wire transport가 아님"),
    "legacy_scan_vendor": ("zephyr/samples/bluetooth/hci_vs_scan_req", "excluded", "legacy scan-request vendor opcode는 Zephyr LL 경로; 고정 SDC에서는 표준 extended callback 사용"),
}


def sha256(path: Path) -> str:
    """! @brief 실제 byte hash를 계산한다. """
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_blob_hashes(commit: str, name: str) -> set[str]:
    """! @brief 고정 commit source의 Git/LF와 Windows checkout/CRLF hash를 반환합니다. """
    relative = Path(name)
    if (not re.fullmatch(r"[0-9a-f]{40}", commit) or relative.is_absolute() or ".." in relative.parts or
            relative.as_posix() != name):
        raise ValueError("source snapshot 경로 또는 revision 불일치")
    raw = subprocess.check_output(["git", "-C", str(ROOT), "show", commit + ":" + name])
    return {digest_bytes(raw), digest_bytes(raw.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))}


def git_blob_sha256(commit: str, name: str) -> str:
    """! @brief Host test fixture용 canonical Git blob hash를 반환합니다. """
    relative = Path(name)
    if (not re.fullmatch(r"[0-9a-f]{40}", commit) or relative.is_absolute() or ".." in relative.parts or
            relative.as_posix() != name):
        raise ValueError("source snapshot 경로 또는 revision 불일치")
    raw = subprocess.check_output(["git", "-C", str(ROOT), "show", commit + ":" + name])
    return digest_bytes(raw)


def revision(path: Path) -> str:
    """! @brief 실제 checkout SHA를 읽는다. """
    return subprocess.check_output(
        ["git", "-C", str(path), "rev-parse", "HEAD"], text=True,
        timeout=30,
    ).strip()


def checkout_clean(path: Path) -> bool:
    """! @brief 추적·미추적 변경을 포함한 checkout clean 상태를 검사합니다. """

    return not subprocess.check_output(
        ["git", "-C", str(path), "status", "--porcelain=v1",
         "--untracked-files=all"], text=True, timeout=30,
    ).strip()


def validate_locked_sources(sdk: Path) -> dict[str, str]:
    """! @brief Core·NCS 3.4.0·Zephyr·board revision과 clean 상태를 고정합니다. """

    paths = {
        "core": ROOT,
        "ncs": sdk / "nrf",
        "zephyr": sdk / "zephyr",
        "board": ROOT / "board_package/NU54DK_Zephyr_DTS",
    }
    revisions = {name: revision(path) for name, path in paths.items()}
    expected = {name: LOCK[name]["revision"] for name in ("ncs", "zephyr", "board")}
    if any(revisions[name] != value for name, value in expected.items()):
        raise ValueError("고정 NCS 3.4.0/Zephyr/board revision과 다릅니다")
    if any(not checkout_clean(path) for path in paths.values()):
        raise ValueError("진단 build source checkout에 변경이 있습니다")
    return revisions


def _tree_manifest(root: Path, prefix: str) -> dict[str, str]:
    """! @brief route가 소비하는 source tree의 파일별 SHA-256을 만듭니다. """

    return {
        prefix + "/" + path.relative_to(root).as_posix(): sha256(path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def route_source_manifest(route: str, sdk: Path) -> dict[str, str]:
    """! @brief controller/scan-request의 local wrapper와 upstream source를 결합합니다. """

    if route == "controller":
        local = _tree_manifest(TEMPLATES / "controller", "templates/controller")
        upstream = _tree_manifest(
            sdk / "zephyr/samples/bluetooth/hci_uart", "zephyr/hci_uart"
        )
    elif route == "scan_request":
        local = _tree_manifest(TEMPLATES / "scan_request", "templates/scan_request")
        local.update({
            "templates/controller/src/main.c": sha256(
                TEMPLATES / "controller/src/main.c"
            )
        })
        upstream = _tree_manifest(
            sdk / "zephyr/samples/bluetooth/hci_vs_scan_req",
            "zephyr/hci_vs_scan_req",
        )
    elif route.startswith("dtm_"):
        local = _tree_manifest(TEMPLATES / "dtm", "templates/dtm")
        upstream = _tree_manifest(
            sdk / ROUTES[route][0], ROUTES[route][0]
        )
    elif route in ("uart", "async", "threewire", "lpuart", "spi"):
        local = _tree_manifest(TEMPLATES / "controller", "templates/controller")
        upstream = _tree_manifest(
            sdk / ROUTES[route][0], ROUTES[route][0]
        )
    elif route in ROUTES and ROUTES[route][1] != "excluded":
        local = _tree_manifest(TEMPLATES / "upstream", "templates/upstream")
        upstream = _tree_manifest(
            sdk / ROUTES[route][0], ROUTES[route][0]
        )
    else:
        raise ValueError("지원하지 않는 진단 route입니다")
    local.update(upstream)
    return local


def source_identity() -> str:
    """! @brief CMake와 같은 순서의 source hash를 만들어 실물 identity와 대조한다. """
    source = "".join(f"{name}:{sha256(TEMPLATES / 'dtm' / name)}\n" for name in IDENTITY_FILES)
    return revision(ROOT) + hashlib.sha256(source.encode()).hexdigest()


def build_plan(route: str, sdk: Path, toolchain: Path, output: Path) -> list[str]:
    """! @brief transport별로 선택된 source/config/overlay를 명시한 build argv를 만든다. """
    if route not in ROUTES or ROUTES[route][1] == "excluded":
        raise ValueError("고정 NU54DK에 적용할 수 없는 transport입니다")
    options = [f"-DBOARD_ROOT={(ROOT / 'board_package/NU54DK_Zephyr_DTS').as_posix()}", "-DUSE_CCACHE=0",
               "-UCONFIG_MBEDTLS_CONFIG_FILE", "-UCONFIG_TF_PSA_CRYPTO_CONFIG_FILE", "-UCONFIG_TF_PSA_CRYPTO_USER_CONFIG_FILE"]
    if route.startswith("dtm_"):
        source = TEMPLATES / "dtm"
        if route == "dtm_hci":
            options.append(f"-DEXTRA_CONF_FILE={(source / 'hci.conf').as_posix()}")
    elif route == "scan_request":
        source = TEMPLATES / "scan_request"
    elif route in ("controller", "uart", "async", "threewire", "lpuart", "spi"):
        source = TEMPLATES / "controller"
        transport = "uart" if route == "controller" else route
        if route != "controller":
            options.append(f"-DEXTRA_CONF_FILE={(source / (route + '.conf')).as_posix()}")
        options.append(f"-DDIAGNOSTIC_TRANSPORT={transport}")
        overlays = [source / "app.overlay"]
        if transport in ("threewire", "lpuart", "spi"):
            overlays.append(source / (transport + ".overlay"))
        options.append("-DDTC_OVERLAY_FILE=" + ";".join(path.as_posix() for path in overlays))
    else:
        source = sdk / ROUTES[route][0]
        support = TEMPLATES / "upstream"
        configs = [support / "bounded.conf"]
        if route == "power_profiling":
            configs.append(support / "power_profiling.conf")
        options.extend(("-DEXTRA_CONF_FILE=" + ";".join(path.as_posix() for path in configs),
                        f"-DDTC_OVERLAY_FILE={(support / 'board.overlay').as_posix()}",
                        f"-DCMAKE_PROJECT_INCLUDE={(support / 'guard.cmake').as_posix()}"))
    python = toolchain / "opt/bin/python.exe"
    return [str(python), "-I", "-m", "west", "build", "--no-sysbuild", "--pristine=never", "-b", BOARD, "-d", str(output), str(source), "--", *options]


def validate_release_build_manifest(manifest: dict, output: Path,
                                    sdk: Path, toolchain: Path) -> None:
    """! @brief W06 controller/scan-request build의 actual byte·argv·source를 재검증합니다. """

    locked = validate_locked_sources(sdk)
    expected_top = {
        "source_revision", "source_clean", "dtm_identity", "board_revision",
        "ncs_revision", "zephyr_revision", "toolchain_bundle_id", "sdk_root",
        "toolchain_root", "results",
    }
    if (set(manifest) != expected_top or manifest["source_clean"] is not True or
            manifest["source_revision"] != locked["core"] or
            manifest["dtm_identity"] != source_identity() or
            manifest["board_revision"] != LOCK["board"]["revision"] or
            manifest["ncs_revision"] != LOCK["ncs"]["revision"] or
            manifest["zephyr_revision"] != LOCK["zephyr"]["revision"] or
            manifest["toolchain_bundle_id"] != LOCK["windows_toolchain"]["bundle_id"] or
            Path(manifest["sdk_root"]).resolve() != sdk.resolve() or
            Path(manifest["toolchain_root"]).resolve() != toolchain.resolve()):
        raise ValueError("진단 release build identity 불일치")
    rows = manifest.get("results")
    if (not isinstance(rows, list) or
            [row.get("route") for row in rows] != ["controller", "scan_request"]):
        raise ValueError("진단 release build route 분모 불일치")
    expected_keys = {
        "route", "status", "exit_code", "dtm_identity", "log_sha256",
        "image_sha256", "config_sha256", "elf_sha256", "nm", "command",
        "command_sha256", "source_files", "build_root_mode", "runtime",
    }
    for row in rows:
        route = row["route"]
        directory = output / route / "zephyr"
        log = output / f"{route}.log"
        image = directory / "zephyr.hex"
        config = directory / ".config"
        elf = directory / "zephyr.elf"
        nm_reference = row.get("nm")
        if (set(row) != expected_keys or row["status"] != "PASS" or
                row["exit_code"] != 0 or row["dtm_identity"] is not None or
                row["runtime"] != "NOT_RUN" or row["build_root_mode"] != "fresh" or
                row["command"] != build_plan(route, sdk, toolchain, output / route) or
                row["command_sha256"] != digest_bytes(json.dumps(
                    row["command"], separators=(",", ":")
                ).encode("utf-8")) or
                row["source_files"] != route_source_manifest(route, sdk) or
                not all(path.is_file() and path.stat().st_size > 0
                        for path in (log, image, config, elf)) or
                sha256(log) != row["log_sha256"] or
                sha256(image) != row["image_sha256"] or
                sha256(config) != row["config_sha256"] or
                sha256(elf) != row["elf_sha256"] or
                not isinstance(nm_reference, dict) or
                set(nm_reference) != {"path", "sha256", "exit_code"} or
                Path(nm_reference["path"]).name != nm_reference["path"] or
                nm_reference["exit_code"] != 0):
            raise ValueError(f"진단 {route} exact build provenance 불일치")
        nm_log = output / nm_reference["path"]
        if (not nm_log.is_file() or sha256(nm_log) != nm_reference["sha256"] or
                "nucode_upstream_main" not in nm_log.read_text(
                    encoding="utf-8", errors="replace")):
            raise ValueError(f"진단 {route} nm provenance 불일치")
        configuration = config.read_text(encoding="utf-8")
        common = ("CONFIG_WATCHDOG=y", "CONFIG_BT_LL_SOFTDEVICE=y")
        forbidden = ("CONFIG_NUCODE_ARDUINO_CORE=y", "CONFIG_BT_LL_SW_SPLIT=y")
        route_required = (("CONFIG_BT_HCI_RAW=y",) if route == "controller" else
                          ("CONFIG_BT_HCI_HOST=y", "CONFIG_BT_EXT_ADV=y",
                           "CONFIG_BT_BROADCASTER=y"))
        if (any(value not in configuration for value in (*common, *route_required)) or
                any(value in configuration for value in forbidden)):
            raise ValueError(f"진단 {route} route config 불일치")
        inspect_hex(image, row["image_sha256"], None)


def build(args: argparse.Namespace) -> None:
    """! @brief 고정 SDK identity 검사 후 빈 directory에서만 build하고 증거를 저장한다. """
    protected = tuple(
        path.resolve() for path in (ROOT, args.sdk, args.toolchain)
    )
    output_root = args.output.resolve()

    def overlaps(first: Path, second: Path) -> bool:
        """! @brief resolve된 두 경로의 동일·상위·하위 중첩을 판정합니다. """
        return (first == second or first.is_relative_to(second) or
                second.is_relative_to(first))

    if any(overlaps(output_root, path) for path in protected):
        raise ValueError("진단 build output은 source/SDK/toolchain과 겹치지 않아야 합니다")
    reuse_root = None
    if args.reuse_build_root is not None:
        reuse_root = args.reuse_build_root.resolve()
        if (not reuse_root.is_dir() or
                any(overlaps(reuse_root, path) for path in protected) or
                overlaps(reuse_root, output_root)):
            raise ValueError(
                "재사용 build root는 source/SDK/toolchain/output과 겹치지 않는 기존 외부 경로여야 합니다"
            )
        for route in args.routes:
            route_root = (reuse_root / route).resolve()
            if (not route_root.is_relative_to(reuse_root) or
                    any(overlaps(route_root, path) for path in protected) or
                    overlaps(route_root, output_root)):
                raise ValueError("재사용 route build root가 보호 경로로 이탈했습니다")
    locked = validate_locked_sources(args.sdk)
    if args.jobs < 1 or args.jobs > 2:
        raise ValueError("진단 build jobs는 1~2여야 합니다")
    if args.toolchain.name != LOCK["windows_toolchain"]["bundle_id"]:
        raise ValueError("고정 Windows toolchain bundle과 다릅니다")
    if args.output.exists():
        raise ValueError("기존 결과를 보존합니다. 새 output 경로가 필요합니다")
    args.output.mkdir(parents=True)
    environment = dict(os.environ)
    for variable in json.loads((args.toolchain / "environment.json").read_text(encoding="utf-8-sig"))["env_vars"]:
        name = variable["key"]
        if variable["type"] == "relative_paths":
            values = [str((args.toolchain / value).resolve()) for value in variable["values"]]
            if variable.get("existing_value_treatment") == "prepend_to" and environment.get(name):
                values.append(environment[name])
            environment[name] = os.pathsep.join(values)
        elif variable["type"] == "string":
            environment[name] = variable["value"]
    environment["ZEPHYR_BASE"] = str(args.sdk / "zephyr")
    environment["PYTHONUTF8"] = "1"
    environment["CMAKE_BUILD_PARALLEL_LEVEL"] = str(args.jobs)
    results = []
    for route in args.routes:
        candidate_identity = source_identity()
        route_sources = route_source_manifest(route, args.sdk)
        output = (reuse_root / route).resolve() if reuse_root else args.output / route
        if reuse_root is not None:
            cache = output / "CMakeCache.txt"
            if not cache.is_file() or "nrf54l15/cpuapp/nu54dk" not in cache.read_text(encoding="utf-8"):
                raise ValueError("동일 NU54DK target의 기존 build directory가 아닙니다")
            previous_image = output / "zephyr/zephyr.hex"
            if previous_image.is_file():
                shutil.copyfile(previous_image, args.output / (route + ".previous.hex"))
        log = args.output / (route + ".log")
        command = build_plan(route, args.sdk, args.toolchain, output)
        with log.open("w", encoding="utf-8") as stream:
            completed = subprocess.run(command, cwd=args.sdk, env=environment, stdout=stream, stderr=subprocess.STDOUT, timeout=1200, check=False)
        image = output / "zephyr/zephyr.hex"
        config = output / "zephyr/.config"
        elf = output / "zephyr/zephyr.elf"
        passed = completed.returncode == 0 and image.is_file() and config.is_file() and elf.is_file()
        nm_log = args.output / (route + ".nm.log")
        symbols = None
        if passed:
            resolved = config.read_text(encoding="utf-8")
            if ("CONFIG_WATCHDOG=y" not in resolved or "CONFIG_NUCODE_ARDUINO_CORE=y" in resolved or
                    "CONFIG_BT_LL_SOFTDEVICE=y" not in resolved or "CONFIG_BT_LL_SW_SPLIT=y" in resolved):
                passed = False
            if route.startswith("dtm_") or route in ("controller", "uart", "async", "threewire", "lpuart", "spi"):
                if any(f"CONFIG_{feature}=y" in resolved for feature in ("UART_CONSOLE", "PRINTK", "LOG", "BT_HCI_HOST")):
                    passed = False
            if route == "controller" and "CONFIG_BT_HCI_RAW=y" not in resolved:
                passed = False
            if route == "scan_request" and any(option not in resolved for option in (
                    "CONFIG_BT_HCI_HOST=y", "CONFIG_BT_EXT_ADV=y",
                    "CONFIG_BT_BROADCASTER=y")):
                passed = False
            if not route.startswith("dtm_"):
                nm = args.toolchain / "opt/zephyr-sdk/gnu/arm-zephyr-eabi/bin/arm-zephyr-eabi-nm.exe"
                symbols = subprocess.run(
                    [str(nm), str(elf)], capture_output=True, check=False,
                    text=True, env=environment, timeout=30,
                )
                nm_log.write_text(symbols.stdout + symbols.stderr, encoding="utf-8")
                if symbols.returncode != 0 or "nucode_upstream_main" not in symbols.stdout:
                    passed = False
        if (candidate_identity != source_identity() or
                route_sources != route_source_manifest(route, args.sdk) or
                locked != validate_locked_sources(args.sdk)):
            passed = False
        results.append({"route": route, "status": "PASS" if passed else "FAIL", "exit_code": completed.returncode,
                        "dtm_identity": candidate_identity if route.startswith("dtm_") else None,
                        "log_sha256": sha256(log), "image_sha256": sha256(image) if image.is_file() else None,
                        "config_sha256": sha256(config) if config.is_file() else None,
                        "elf_sha256": sha256(elf) if elf.is_file() else None,
                        "nm": ({"path": nm_log.name, "sha256": sha256(nm_log),
                                "exit_code": symbols.returncode}
                               if symbols is not None and nm_log.is_file() else None),
                        "command": command,
                        "command_sha256": digest_bytes(json.dumps(
                            command, separators=(",", ":")
                        ).encode("utf-8")),
                        "source_files": route_sources,
                        "build_root_mode": ("reused" if reuse_root is not None else "fresh"),
                        "runtime": "NOT_RUN"})
        print(f"M33_DIAG_BUILD_{results[-1]['status']}={route}", flush=True)
    final_locked = validate_locked_sources(args.sdk)
    if final_locked != locked:
        raise ValueError("진단 build 도중 source lock이 변경됐습니다")
    manifest = {"source_revision": locked["core"], "source_clean": True,
                "dtm_identity": source_identity(),
                "board_revision": locked["board"],
                "ncs_revision": locked["ncs"], "zephyr_revision": locked["zephyr"],
                "toolchain_bundle_id": args.toolchain.name,
                "sdk_root": str(args.sdk.resolve()),
                "toolchain_root": str(args.toolchain.resolve()),
                "results": results}
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.routes == ["controller", "scan_request"] and reuse_root is None:
        validate_release_build_manifest(manifest, args.output, args.sdk, args.toolchain)
    if any(result["status"] != "PASS" for result in results):
        raise RuntimeError("실패 build는 원본 로그와 함께 보존했습니다")


def packet_count(event: bytes) -> int:
    """! @brief status 응답을 RX count로 오인하지 않도록 reporting bit를 검사한다. """
    if len(event) != 2 or not event[0] & 0x80:
        raise ValueError("DTM packet reporting event가 아닙니다")
    return int.from_bytes(event, "big") & 0x7fff


class DtmPort:
    """! @brief 이미 exact mapping된 전용 UART의 유한 command/response 세션. """
    def __init__(self, serial_port, h4: bool, guard=None):
        self.serial = serial_port
        self.h4 = h4
        self.guard = guard
        self.transcript: list[dict] = []

    def read(self, size: int) -> bytes:
        """! @brief partial response는 PASS 대신 timeout으로 처리한다. """
        if self.guard is None:
            result = self.serial.read(size)
        else:
            result = bytearray()
            deadline = time.monotonic() + 1.5
            while len(result) < size:
                self.guard.check()
                result.extend(self.serial.read(size - len(result)))
                self.guard.check()
                if time.monotonic() >= deadline and len(result) < size:
                    raise TimeoutError("진단 response deadline")
            result = bytes(result)
        if len(result) != size:
            raise TimeoutError(f"진단 response 길이 {len(result)}/{size}")
        return result

    def hci(self, opcode: int, parameters: bytes = b"") -> bytes:
        """! @brief H4 opcode·length·status가 일치하는 response만 수용한다. """
        if self.guard is not None:
            self.guard.check()
        command = b"\x01" + opcode.to_bytes(2, "little") + bytes([len(parameters)]) + parameters
        self.serial.write(command)
        header = self.read(3)
        if header[:2] != b"\x04\x0e":
            raise ValueError("예상하지 않은 H4 response 또는 UART debug 혼입")
        payload = self.read(header[2])
        self.transcript.append({"tx": command.hex(), "rx": (header + payload).hex()})
        if len(payload) < 4 or payload[0] != 1 or int.from_bytes(payload[1:3], "little") != opcode:
            raise ValueError("stale/mismatched HCI command complete")
        return payload[3:]

    def twowire(self, command: int) -> bytes:
        """! @brief 두 command byte는 한 write로 전송한다. """
        if self.guard is not None:
            self.guard.check()
        data = command.to_bytes(2, "big")
        self.serial.write(data)
        result = self.read(2)
        self.transcript.append({"tx": data.hex(), "rx": result.hex()})
        return result

    def identity(self) -> str:
        """! @brief RF 시작 전에 실제 실행 source identity를 읽는다. """
        if self.h4:
            result = self.hci(0xfc80)
            if len(result) != 105 or result[0] != 0:
                raise ValueError("HCI firmware identity 불일치")
            return result[1:].decode("ascii")
        result = bytearray()
        for index in range(104):
            event = int.from_bytes(self.twowire(0x3f00 | index), "big")
            if event & 0x8001 or (event >> 1) > 127:
                raise ValueError("DTM firmware identity 불일치")
            result.append(event >> 1)
        return result.decode("ascii")

    def stop(self) -> int:
        """! @brief Test End를 명시적으로 보내 실제 controller counter를 반환한다. """
        if self.h4:
            result = self.hci(0x201f)
            if len(result) != 3 or result[0] != 0:
                raise ValueError("HCI Test End 실패")
            return int.from_bytes(result[1:], "little")
        return packet_count(self.twowire(0xc000))

    def automatic_stop(self) -> int:
        """! @brief 3초 firmware lease 종료 event를 실제로 수신한다. """
        if self.h4:
            header = self.read(3)
            payload = self.read(header[2])
            event = header + payload
            if len(event) != 9 or event[:7] != bytes.fromhex("040e06011f2000"):
                raise ValueError("HCI 자동 STOP event가 아닙니다")
            self.transcript.append({"rx_auto_stop": event.hex()})
            return int.from_bytes(event[7:], "little")
        event = self.read(2)
        self.transcript.append({"rx_auto_stop": event.hex()})
        return packet_count(event)

    def start(self, transmit: bool, channel: int, phy: int) -> None:
        """! @brief 알려진 PRBS9 37-byte와 1M/2M PHY로 유한 무선 시험을 시작한다. """
        if channel not in (0, 19, 39) or phy not in (1, 2):
            raise ValueError("고정 시험 channel/PHY 밖의 입력")
        if self.h4:
            opcode = 0x2034 if transmit else 0x2033
            parameters = bytes((channel, 37, 0, phy)) if transmit else bytes((channel, phy, 0))
            if self.hci(opcode, parameters) != b"\x00":
                raise ValueError("HCI DTM 시작 실패")
        else:
            if self.twowire(0x0200 | (phy * 4)) != b"\x00\x00":
                raise ValueError("DTM PHY 설정 실패")
            command = (0x8000 | (channel << 8) | (37 << 2)) if transmit else (0x4000 | (channel << 8))
            if self.twowire(command) != b"\x00\x00":
                raise ValueError("DTM 시작 실패")

    def negative(self) -> None:
        """! @brief 잘못된 channel/length/command와 active 중 재시작을 실물에서 거부한다. """
        if self.h4:
            for opcode, parameters, status in ((0x201d, b"\x28", 0x12), (0x201e, b"\x00", 0x12),
                                                (0xffff, b"", 0x01)):
                if self.hci(opcode, parameters) != bytes([status]):
                    raise ValueError("HCI negative가 예상 오류를 반환하지 않았습니다")
        else:
            for command in (0x6800, 0xa800, 0x06ff):
                if self.twowire(command) != b"\x00\x01":
                    raise ValueError("DTM negative가 거부되지 않았습니다")
        self.start(False, 19, 1)
        if self.h4:
            refused = self.hci(0x201d, b"\x13") == b"\x0c"
        else:
            refused = self.twowire(0x5300) == b"\x00\x01"
        if not refused:
            raise ValueError("active RADIO 재시작을 거부하지 않았습니다")
        self.stop()


def digest_bytes(data: bytes) -> str:
    """! @brief raw UID나 readback 원문 대신 증거용 SHA-256만 반환합니다. """
    return hashlib.sha256(data).hexdigest()


def probe_hash(uid: str) -> str:
    """! @brief 공용 ProbeLocks와 같은 lower-case ASCII UID hash를 사용합니다. """
    normalized = uid.strip().lower()
    if not re.fullmatch(r"[0-9a-f]{32}", normalized):
        raise ValueError("정확한 DAPLink UID 형식이 아닙니다")
    return digest_bytes(normalized.encode("ascii"))


def mdk_evidence(sdk: Path) -> dict:
    """! @brief 고정 NCS MDK에서 주소·task 접근 속성·Disabled 값을 직접 대조합니다. """
    if (revision(sdk / "nrf") != LOCK["ncs"]["revision"] or
            revision(sdk / "zephyr") != LOCK["zephyr"]["revision"] or
            revision(ROOT / "board_package/NU54DK_Zephyr_DTS") != LOCK["board"]["revision"]):
        raise ValueError("고정 NCS/Zephyr/board revision과 다릅니다")
    directory = sdk / "modules/hal/nordic/nrfx/bsp/stable/mdk"
    checks = {
        "nrf54l15_global.h": (r"#define\s+NRF_RADIO_S_BASE\s+0x5008A000UL",
                              r"#define\s+NRF_FICR_NS_BASE\s+0x00FFC000UL",
                              r"#define\s+NRF_WDT30_S_BASE\s+0x50108000UL",
                              r"#define\s+NRF_WDT31_S_BASE\s+0x50109000UL"),
        "nrf54l15_types.h": (r"__OM\s+uint32_t\s+TASKS_DISABLE;[^\n]*0x00000010[^\n]*Disable RADIO",
                              r"__IM\s+uint32_t\s+STATE;[^\n]*0x00000520[^\n]*Current radio state",
                              r"RADIO_STATE_STATE_Disabled\s+\(0x0UL\)",
                              r"RADIO_SHORTS_ResetValue\s+\(0x00000000UL\)",
                              r"RADIO_SHORTS_PHYEND_DISABLE_Pos\s+\(19UL\)",
                             r"__IM\s+uint32_t\s+PART;[^\n]*0x0000001C[^\n]*Part code",
                             r"__IOM\s+NRF_FICR_INFO_Type\s+INFO;[^\n]*0x00000300[^\n]*Device info",
                             r"FICR_INFO_PART_PART_N54L15\s+\(0x00054B15UL\)"),
        "nrf54l15_xxaa_application_memory.h": (r"NRF_MEMORY_FLASH_BASE\s+0x00000000",
                                               r"NRF_MEMORY_FLASH_SIZE\s+0x0017D000"),
    }
    files = []
    for name, patterns in checks.items():
        path = directory / name
        content = path.read_text(encoding="utf-8")
        if not all(re.search(pattern, content) for pattern in patterns):
            raise ValueError("고정 MDK register 정의와 다릅니다")
        files.append({"path": path.relative_to(sdk).as_posix(), "sha256": sha256(path)})
    types = (directory / "nrf54l15_types.h").read_text(encoding="utf-8")
    for peripheral, subscribe, publish in (("RADIO", RADIO_SUBSCRIBE, RADIO_PUBLISH),
                                           ("WDT", WDT_ROUTES[:2], WDT_ROUTES[2:])):
        end = types.index("} NRF_" + peripheral + "_Type;")
        body = types[types.rfind("typedef struct", 0, end):end]
        fields = {name: int(offset, 16) for name, offset in re.findall(
            r"uint32_t\s+(\w+);[^\n]*\(@ (0x[0-9A-F]+)\)", body)}
        for prefix, expected in (("SUBSCRIBE_", subscribe), ("PUBLISH_", publish)):
            if sorted(value for name, value in fields.items() if name.startswith(prefix)) != list(expected):
                raise ValueError("고정 MDK DPPI register 집합과 다릅니다")
            for name in (name for name in fields if name.startswith(prefix)):
                if not re.search(peripheral + "_" + name + r"_EN_Pos\s+\(31UL\)", types):
                    raise ValueError("고정 MDK DPPI EN 위치와 다릅니다")
        fixed = {"SHORTS": 0x400, "STATE": 0x520} if peripheral == "RADIO" else {
            "EVENTS_TIMEOUT": 0x100, "RUNSTATUS": 0x400, "CONFIG": 0x50C}
        if any(fields.get(name) != value for name, value in fixed.items()):
            raise ValueError("고정 MDK audit register 주소와 다릅니다")
    if not re.search(r"WDT_CONFIG_HALT_Pos\s+\(3UL\)", types):
        raise ValueError("고정 MDK WDT HALT bit와 다릅니다")
    cmsis = sdk / "modules/hal/cmsis/CMSIS/Core/Include/core_cm33.h"
    core = cmsis.read_text(encoding="utf-8")
    for pattern in (r"CoreDebug_BASE\s+\(0xE000EDF0UL\)", r"CoreDebug_DHCSR_S_RESET_ST_Pos\s+25U",
                    r"CoreDebug_DHCSR_S_HALT_Pos\s+17U", r"CoreDebug_DHCSR_C_HALT_Pos\s+1U",
                    r"CoreDebug_DHCSR_C_DEBUGEN_Pos\s+0U"):
        if not re.search(pattern, core):
            raise ValueError("고정 CMSIS DHCSR 정의와 다릅니다")
    files.append({"path": cmsis.relative_to(sdk).as_posix(), "sha256": sha256(cmsis)})
    return {"ncs_revision": LOCK["ncs"]["revision"], "zephyr_revision": LOCK["zephyr"]["revision"],
            "board_revision": LOCK["board"]["revision"], "files": files,
            "radio_tasks_disable": RADIO_DISABLE, "task_access": "write-only; trigger=1; no task readback",
            "radio_state": RADIO_STATE, "disabled": RADIO_DISABLED,
            "ficr_part": 0x00FFC31C, "expected_part": 0x54B15,
            "radio_subscribe_offsets": RADIO_SUBSCRIBE, "radio_publish_offsets": RADIO_PUBLISH,
            "wdt_bases": WDT_BASES, "wdt_route_offsets": WDT_ROUTES,
            "reset_observation": "single raw DHCSR consumer with sticky software latch; RESETREAS not used",
            "dp_ap_reference": "tests/hil/nu54dk/m28_ble_3board.py; pyocd/target/family/target_nRF54L.py"}


def inspect_hex(path: Path, expected_sha: str, identity: str | None) -> dict:
    """! @brief checksum·중복·영역·identity를 검증하고 프로그램할 exact byte를 고정합니다. """
    raw = path.read_bytes()
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha) or digest_bytes(raw) != expected_sha:
        raise ValueError("승인된 exact HEX SHA와 다릅니다")
    memory = {}
    base = 0
    ended = False
    for line in raw.decode("ascii").splitlines():
        if ended or not line.startswith(":"):
            raise ValueError("HEX EOF/record 형식 오류")
        record = bytes.fromhex(line[1:])
        if len(record) < 5 or len(record) != record[0] + 5 or sum(record) & 255:
            raise ValueError("HEX checksum/length 오류")
        count, address, kind = record[0], int.from_bytes(record[1:3], "big"), record[3]
        data = record[4:-1]
        if kind == 0:
            start = base + address
            if not count or not 0 <= start < start + count <= APPLICATION_END:
                raise ValueError("application 밖의 HEX data는 허용하지 않습니다")
            for offset, byte in enumerate(data):
                if start + offset in memory:
                    raise ValueError("겹치는 HEX record")
                memory[start + offset] = byte
        elif kind == 1 and count == 0 and address == 0:
            ended = True
        elif kind == 4 and count == 2 and address == 0:
            base = int.from_bytes(data, "big") << 16
        elif kind == 2 and count == 2 and address == 0:
            base = int.from_bytes(data, "big") << 4
        elif kind == 3 and count == 4 and address == 0:
            entry = (int.from_bytes(data[:2], "big") << 4) + int.from_bytes(data[2:], "big")
            if not 0 <= entry < APPLICATION_END:
                raise ValueError("application 밖의 segment start address")
        elif kind == 5 and count == 4 and address == 0:
            if not 0 <= int.from_bytes(data, "big") < APPLICATION_END:
                raise ValueError("application 밖의 start address")
        else:
            raise ValueError("지원하지 않는 HEX record")
    if not ended or any(address not in memory for address in range(8)):
        raise ValueError("EOF 또는 application vector 누락")
    ranges = []
    for address in sorted(memory):
        if not ranges or address != ranges[-1][0] + len(ranges[-1][1]):
            ranges.append((address, bytearray()))
        ranges[-1][1].append(memory[address])
    if identity is not None and (not re.fullmatch(r"[0-9a-f]{104}", identity) or
                                 not any(identity.encode() in data for _, data in ranges)):
        raise ValueError("HEX에 exact DTM firmware identity가 없습니다")
    vector = bytes(memory[index] for index in range(8))
    stack, entry = int.from_bytes(vector[:4], "little"), int.from_bytes(vector[4:], "little")
    if not 0x20000000 < stack <= 0x20040000 or stack % 8 or not entry & 1 or entry >= APPLICATION_END:
        raise ValueError("nRF54L15 application vector가 아닙니다")
    return {"sha256": expected_sha, "raw": raw, "ranges": [(start, bytes(data)) for start, data in ranges]}


def image_plan(image: dict) -> dict:
    """! @brief HEX hash와 binary range hash를 혼동하지 않도록 별도 기록합니다. """
    return {"image_sha256": image["sha256"], "image_kind": "intel_hex_file",
            "ranges": [{"start": start, "length": len(data), "expected_sha256": digest_bytes(data)}
                       for start, data in image["ranges"]],
            "sectors": sorted({address // FLASH_SECTOR * FLASH_SECTOR
                               for start, data in image["ranges"]
                               for address in range(start, start + len(data))})}


def validate_debug_identity(values: dict) -> None:
    """! @brief target 초기화 전에 DP/AP identity와 보호 해제를 읽기로만 판정합니다. """
    expected = {"dp_idcode": 0x6BA02477, "ahb_ap_idr": 0x84770001,
                "ctrl_ap_idr": 0x32880000, "approtect_status": 0}
    if any(values.get(key) != value for key, value in expected.items()):
        raise ValueError("DP/AP identity 또는 보호 상태 불일치")
    target_id = values.get("target_id", 0)
    if target_id & 0xFFF != 0x289 or target_id & 0xF0000 != 0xC0000 or not values.get("ahb_ap_csw", 0) & 0x40:
        raise ValueError("Nordic nRF54L TARGETID/AHB 접근 상태 불일치")


def map_live_probes(probes: list, ports: list, hashes: list[str], serial_ports: list[str]) -> list:
    """! @brief 현재 세 USB probe와 두 VCOM의 full UID 대응만 받아 suffix 추정을 금지합니다. """
    mapped = {}
    for probe in probes:
        identity = probe_hash(probe.unique_id)
        if identity in mapped:
            raise ValueError("중복 USB probe identity")
        mapped[identity] = probe
    if set(mapped) != set(hashes):
        raise ValueError("현재 probe 3개와 지정 SHA가 정확히 일치하지 않습니다")
    for identity, port_name in zip(hashes, serial_ports):
        matches = [port for port in ports if port.device.casefold() == port_name.casefold()]
        if len(matches) != 1 or not matches[0].serial_number or probe_hash(matches[0].serial_number) != identity:
            raise ValueError("현재 VCOM serial_number와 probe SHA가 일치하지 않습니다")
    return [mapped[identity] for identity in hashes]


class PyocdPreparationBackend:
    """! @brief 실행 명시 승인 후에만 import하며 raw UID/log를 증거에 노출하지 않는 adapter. """
    def __init__(self):
        from pyocd.core.helpers import ConnectHelper
        from pyocd.core.session import Session
        from pyocd.core.target import Target
        from pyocd.flash.file_programmer import FileProgrammer
        from serial.tools import list_ports
        self.helper, self.session_type, self.target_type = ConnectHelper, Session, Target
        self.programmer_type, self.list_ports = FileProgrammer, list_ports

    def discover(self):
        """! @brief USB 목록만 열거하고 실제 SWD 접근은 lock 이후 session에서 수행합니다. """
        return self.helper.get_all_connected_probes(blocking=False), list(self.list_ports.comports())

    @contextmanager
    def session(self, probe, initialize=True):
        """! @brief 빈 project directory로 임의 pyocd.yaml/user script 실행을 차단합니다. """
        current = Path.cwd()
        with tempfile.TemporaryDirectory(prefix="nu54-diagnostic-pyocd-") as temporary:
            session = None
            initialized = False
            try:
                if type(probe).__module__ != "pyocd.probe.cmsis_dap_probe":
                    raise ValueError("CMSIS-DAP probe가 아닙니다")
                session = self.session_type(probe, auto_open=False,
                                            options=dict(SAFE_SESSION_OPTIONS, project_dir=temporary))
                session.open(init_board=False)
                link = getattr(probe, "_link", None)
                interface = getattr(link, "_interface", None)
                if not link or link.protocol_version[0] < 2 or not getattr(interface, "is_bulk", False):
                    raise ValueError("CMSIS-DAP v2가 아닙니다")
                session.target.dp.connect()
                if initialize:
                    validate_debug_identity(self.identity(session))
                    ## @brief full init은 attach + auto_unlock=false이며 reset/halt fallback이 없습니다.
                    initialized = True
                    session.board.init()
                    if session.target.read32(0x00FFC31C) != 0x54B15 or session.target.read32(0xE000ED00) != 0x411FD210:
                        raise ValueError("nRF54L15/CPU part identity 불일치")
                yield session
            finally:
                try:
                    if session is not None:
                        try:
                            if initialized:
                                session.board.uninit()
                        finally:
                            session.close()
                finally:
                    os.chdir(current)

    def identity(self, session):
        """! @brief initdp/readdp/readap과 동일한 읽기이며 CTRL-AP reset/erase에는 쓰지 않습니다. """
        dp = session.target.dp
        return {"dp_idcode": dp.read_dp(0), "target_id": dp.read_dp(0x24),
                "ahb_ap_idr": dp.read_ap(0xFC), "ahb_ap_csw": dp.read_ap(0),
                "ctrl_ap_idr": dp.read_ap(0x020000FC), "approtect_status": dp.read_ap(0x02000014)}

    def program(self, session, image):
        """! @brief 허가된 algorithm reset 외 추가 reset을 금지하며 sector 이외 mode는 노출하지 않습니다. """
        self.programmer_type(session, chip_erase="sector", smart_flash=False, trust_crc=False,
                             keep_unwritten=True, no_reset=True).program(
                                 io.StringIO(image["raw"].decode("ascii")), file_format="hex")

    def start(self, session):
        """! @brief 명시적 run 승인 경로에서만 SYSRESETREQ를 사용하고 hardware reset으로 우회하지 않습니다. """
        session.target.reset_and_halt(reset_type=self.target_type.ResetType.SYSRESETREQ)
        if session.target.get_state().name != "HALTED":
            raise ValueError("명시적 software reset 후 halt 실패")
        session.target.resume()


@contextmanager
def private_debug_output():
    """! @brief backend 예외/log/print에 포함될 수 있는 raw UID를 공개 출력에 전달하지 않습니다. """

    with _PRIVATE_DEBUG_LOCK:
        previous = logging.root.manager.disable
        try:
            logging.disable(logging.CRITICAL)
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                yield
        finally:
            logging.disable(previous)


class IdleAuditFailure(ValueError):
    """! @brief UID 없는 정수 register 증거만 보존하는 fail-closed audit 오류. """
    def __init__(self, kind: str, observed: dict):
        super().__init__("read-only idle audit failed")
        self.evidence = {"kind": kind, "observed": observed}


class RawResetMonitor:
    """! @brief DHCSR의 유일한 소비 경로이며 순간 reset bit를 software에 영구 latch합니다. """
    def __init__(self, target):
        self.target = target
        self.reset_seen = False

    def sample(self, require_halted=True):
        """! @brief get_state/core-register API를 쓰지 않고 raw DHCSR만 읽습니다. """
        value = self.target.read32(DHCSR)
        self.reset_seen = self.reset_seen or bool(value & DHCSR_RESET)
        if self.reset_seen or (require_halted and value & DHCSR_HALTED != DHCSR_HALTED):
            raise IdleAuditFailure("dhcsr_reset_or_not_halted", {"address": DHCSR, "value": value,
                                                                 "reset_latched": self.reset_seen})
        return value


def halt_and_wait(target, monitor=None, timeout=1.0):
    """! @brief reset 상태를 놓치지 않고 debugger halt 반영을 유한 시간 기다립니다. """
    monitor = monitor or RawResetMonitor(target)
    monitor.sample(require_halted=False)
    target.halt()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = monitor.sample(require_halted=False)
        if value & DHCSR_HALTED == DHCSR_HALTED:
            return monitor
        time.sleep(0.01)
    raise IdleAuditFailure("halt_timeout", {"address": DHCSR, "timeout_seconds": timeout})


def wait_for_target_state(target, accepted, timeout=1.0):
    """! @brief debugger 상태 전이를 유한 시간 기다리고 비정상 상태를 즉시 거부합니다. """
    accepted = frozenset(accepted)
    if not accepted or not accepted <= {"RUNNING", "SLEEPING", "HALTED"}:
        raise ValueError("허용할 debugger 상태가 잘못됐습니다")
    deadline = time.monotonic() + timeout
    observed = []
    while True:
        state = target.get_state().name
        if not observed or observed[-1] != state:
            observed.append(state)
        if state in accepted:
            return state
        if state in {"RESET", "LOCKUP"}:
            raise IdleAuditFailure(
                "target_state_invalid",
                {"state": state, "accepted": sorted(accepted), "observed": observed},
            )
        if time.monotonic() >= deadline:
            raise IdleAuditFailure(
                "target_state_timeout",
                {
                    "state": state,
                    "accepted": sorted(accepted),
                    "observed": observed,
                    "timeout_seconds": timeout,
                },
            )
        time.sleep(0.01)


def verify_isolation(target, monitor=None, allowed_shorts=0) -> dict:
    """! @brief 알려진 lifecycle과 별개로 모든 defined RADIO/WDT 경로를 읽기 전용 검사합니다. """
    monitor = monitor or RawResetMonitor(target)
    def snapshot():
        """! @brief DHCSR를 먼저 읽어 reset 관측을 소비하는 get_state 호출을 피합니다. """
        dhcsr = monitor.sample()
        values = {"dhcsr_halt": dhcsr & DHCSR_HALTED}
        routes = [RADIO_BASE + offset for offset in RADIO_SUBSCRIBE + RADIO_PUBLISH]
        routes += [base + offset for base in WDT_BASES for offset in WDT_ROUTES]
        for address in routes:
            value = target.read32(address)
            values[f"0x{address:08x}"] = value
            if value & (1 << 31):
                raise IdleAuditFailure("dppi_enabled", {"address": address, "value": value})
        shorts_address = RADIO_BASE + 0x400
        shorts = target.read32(shorts_address)
        values[f"0x{shorts_address:08x}"] = shorts
        if shorts & ~allowed_shorts:
            raise IdleAuditFailure("active_or_unknown_shorts", {"address": shorts_address, "value": shorts,
                                                                  "allowed_mask": allowed_shorts})
        for address in (RADIO_STATE, *(base + 0x100 for base in WDT_BASES)):
            value = target.read32(address)
            values[f"0x{address:08x}"] = value
            if value != 0:
                raise IdleAuditFailure("radio_state_or_timeout", {"address": address, "value": value})
        for base in WDT_BASES:
            running, config = target.read32(base + 0x400), target.read32(base + 0x50C)
            values[f"0x{base + 0x400:08x}"] = running
            values[f"0x{base + 0x50C:08x}"] = config
            if running & 1 and config & 8:
                raise IdleAuditFailure("watchdog_runs_during_halt", {"base": base, "runstatus": running, "config": config})
        monitor.sample()
        return values
    first, second = snapshot(), snapshot()
    if first != second:
        raise IdleAuditFailure("audit_values_changed", {"first": first, "second": second})
    return {"cpu": "HALTED", "radio_state_address": RADIO_STATE, "radio_state": RADIO_DISABLED,
            "registers": first, "reset_observed": False, "read_only": True}


def isolate_radio(target, allowed_shorts=0) -> dict:
    """! @brief halt 이후 strict idle audit만 수행하고 unknown DPPI에 DISABLE event를 주입하지 않습니다. """
    monitor = halt_and_wait(target)
    return dict(verify_isolation(target, monitor, allowed_shorts=allowed_shorts),
                task_written=False, reset_performed=False)


class ThirdGuard:
    """! @brief exact image/lifecycle 승인 후 매 command·대기 구간의 register 변화를 거부합니다. """
    def __init__(self, target, baseline, monitor=None, watcher=None):
        self.target, self.baseline = target, baseline
        self.monitor = monitor or RawResetMonitor(target)
        self.watcher = watcher
        self.failed = False
        self.checks = 0

    def check(self):
        """! @brief 실패를 latch하여 순간 복귀나 RESETREAS 값으로 성공을 되살리지 않습니다. """
        if self.failed:
            raise ValueError("third guard는 이전 실패 이후 재사용할 수 없습니다")
        try:
            observed = verify_isolation(self.target, self.monitor)
            if self.watcher is not None:
                observed["watcher_ram"] = verify_watcher_ram(self.target, self.watcher, self.monitor)
            if observed != self.baseline:
                raise IdleAuditFailure("third_lifecycle_changed", observed)
            self.checks += 1
            return observed
        except Exception:
            self.failed = True
            raise

    def wait(self, seconds):
        """! @brief 명령 lease 관측 대기에도 최대 100 ms 간격으로 audit를 예약합니다. """
        deadline = time.monotonic() + seconds
        while True:
            self.check()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            time.sleep(min(AUDIT_INTERVAL, remaining))


def readback_ranges(target, ranges: list[tuple[int, bytes]], timeout=120.0, monitor=None) -> list[dict]:
    """! @brief 실제 programmed byte 전체를 bounded chunk로 비교하고 범위별 hash만 공개합니다. """
    records = []
    deadline = time.monotonic() + timeout
    for start, expected in ranges:
        observed = bytearray()
        for offset in range(0, len(expected), 4096):
            if time.monotonic() >= deadline:
                raise TimeoutError("programmed range readback timeout")
            count = min(4096, len(expected) - offset)
            if monitor is not None:
                monitor.sample()
            block = bytes(target.read_memory_block8(start + offset, count))
            if monitor is not None:
                monitor.sample()
            if len(block) != count:
                raise ValueError("짧은 readback")
            observed.extend(block)
        if bytes(observed) != expected:
            raise ValueError("programmed range byte mismatch")
        records.append({"start": start, "length": len(expected), "expected_sha256": digest_bytes(expected),
                        "observed_sha256": digest_bytes(observed), "status": "PASS"})
    return records


def watcher_symbols(raw: bytes) -> dict:
    """! @brief exact ARM ELF32 symbol table에서 watcher RAM 주소·크기를 직접 대조합니다. """
    if len(raw) < 52 or raw[:7] != b"\x7fELF\x01\x01\x01" or struct.unpack_from("<H", raw, 18)[0] != 40:
        raise ValueError("ARM little-endian ELF32가 아닙니다")
    offset = struct.unpack_from("<I", raw, 32)[0]
    entry_size, count = struct.unpack_from("<HH", raw, 46)
    if entry_size != 40 or offset + count * 40 > len(raw):
        raise ValueError("ELF section table 범위 오류")
    sections = [struct.unpack_from("<10I", raw, offset + index * 40) for index in range(count)]
    symbols = {}
    for section in sections:
        if section[1] != 2:
            continue
        if section[9] != 16 or section[4] + section[5] > len(raw) or section[6] >= count:
            raise ValueError("ELF symbol table 범위 오류")
        strings = sections[section[6]]
        names = raw[strings[4]:strings[4] + strings[5]]
        for start in range(section[4], section[4] + section[5], 16):
            name_offset, address, size, info, _, _ = struct.unpack_from("<IIIBBH", raw, start)
            name = names[name_offset:].split(b"\0", 1)[0].decode("ascii", errors="strict")
            for wanted, expected_size in THIRD_IDLE_SYMBOLS.items():
                if name == f"_ZN12_GLOBAL__N_1{len(wanted)}{wanted}E":
                    if wanted in symbols or size != expected_size or info & 15 != 1 or not 0x20000000 <= address < address + size <= 0x20040000:
                        raise ValueError("watcher RAM symbol identity/범위 오류")
                    symbols[wanted] = {"symbol": name, "address": address, "size": size}
    if set(symbols) != set(THIRD_IDLE_SYMBOLS):
        raise ValueError("필수 watcher lifecycle symbol 누락")
    return symbols


def validate_watcher_stopped_evidence(stopped: dict, evidence: dict) -> None:
    """! @brief target STOPPED와 runner UART close 증거를 구분해 검사합니다. """

    cleanup = evidence.get("cleanup", {}).get("watcher")
    if (any(stopped.get(key) != "0" for key in
            ("native_links", "links", "pending", "scan", "advertising", "watchdog")) or
            not isinstance(cleanup, dict) or cleanup.get("serial_close") != "PASS" or
            {key: value for key, value in cleanup.items() if key != "serial_close"} != stopped):
        raise ValueError("watcher fresh STOPPED zero-resource 증거 불일치")


def load_watcher_fixture(path: Path, expected_hash: str, probe: str) -> dict:
    """! @brief W02 native final의 fresh 미시작 watcher 증거만 받아 임의 idle 선언을 거부합니다. """
    if not re.fullmatch(r"[0-9a-f]{64}", expected_hash) or sha256(path) != expected_hash:
        raise ValueError("W02 third fixture exact hash 불일치")
    data = json.loads(path.read_text(encoding="utf-8"))
    if (data.get("schema") != THIRD_IDLE_SCHEMA or data.get("role") != "standard-watcher" or
            data.get("probe_sha256") != probe or not re.fullmatch(r"[0-9a-f]{32}", data.get("nonce", "")) or
            data.get("build_defines") != {"M33_PROFILE_FAMILY": "standard", "M33_PROFILE_ROLE": "watcher"}):
        raise ValueError("W02 standard-watcher identity 불일치")
    revisions = data.get("revisions")
    locked = {key: LOCK[key]["revision"] for key in ("board", "ncs", "zephyr")}
    if (not isinstance(revisions, dict) or revisions.get("core") != revision(ROOT) or
            any(revisions.get(key) != value for key, value in locked.items())):
        raise ValueError("W02 full source/SDK revision 불일치")
    sources = data.get("source_files", {})
    if not set(THIRD_IDLE_SOURCES).issubset(sources):
        raise ValueError("watcher 실제 source hash 누락")
    for name, digest in sources.items():
        if digest not in git_blob_hashes(revisions["core"], name):
            raise ValueError("watcher source snapshot 불일치")
    actions = data.get("after_stopped_actions")
    if not isinstance(actions, list) or not actions or any(action not in ("uart_close", "debugger_halt", "read_only_audit") for action in actions):
        raise ValueError("STOPPED 이후 reset/program/resume 부재 증거 불일치")
    blobs, paths = {}, {}
    for kind in THIRD_IDLE_FILES:
        descriptor = data["files"][kind]
        file = (path.parent / descriptor["path"]).resolve()
        raw = file.read_bytes()
        if not re.fullmatch(r"[0-9a-f]{64}", descriptor["sha256"]) or digest_bytes(raw) != descriptor["sha256"]:
            raise ValueError("watcher 근거 파일 hash 불일치")
        blobs[kind], paths[kind] = raw, file
    sysbuild = blobs["sysbuild"].decode("utf-8")
    selected = re.findall(r"^(SB_CONFIG_FLPRCORE_\w+)=y\r?$", sysbuild, re.MULTILINE)
    if selected != ["SB_CONFIG_FLPRCORE_NONE"]:
        raise ValueError("SB_CONFIG_FLPRCORE_NONE=y가 유일한 FLPR 선택이어야 합니다")
    config = blobs["config"].decode("utf-8")
    if not re.search(r"^CONFIG_SOC_NRF54L15_CPUAPP=y\r?$", config, re.MULTILINE):
        raise ValueError("watcher application config 불일치")
    evidence = json.loads(blobs["evidence"])
    if (evidence.get("family") != "native" or evidence.get("status") not in ("PASS", "DEVELOPMENT_PASS") or
            evidence.get("revisions") != revisions or evidence.get("transcript_sha256") != digest_bytes(blobs["transcript"]) or
            evidence.get("boards", {}).get("watcher", {}).get("probe_sha256") != probe or
            evidence["boards"]["watcher"].get("image_sha256") != data["files"]["image"]["sha256"]):
        raise ValueError("W02 native final 결과와 watcher 불일치")
    records = []
    for line in blobs["transcript"].decode("ascii").splitlines():
        if not line.startswith("watcher: "):
            continue
        pieces = line[len("watcher: "):].split("|")
        if len(pieces) < 4 or pieces[:2] != ["M33PROFILE", "1"]:
            raise ValueError("watcher transcript protocol 불일치")
        values = {}
        for field in pieces[3:]:
            key, value = field.split("=", 1)
            if key in values:
                raise ValueError("중복 watcher transcript field")
            values[key] = value
        if values.get("role") != "watcher" or values.get("core") != revisions["core"]:
            raise ValueError("watcher transcript role/revision 불일치")
        records.append((pieces[2], values))
    if ([kind for kind, _ in records] != ["READY", "SERVER_STATS", "STOPPED"] or
            records[0][1].get("nonce") != "" or records[1][1].get("nonce") != data["nonce"] or
            records[-1][1].get("nonce") != data["nonce"]):
        raise ValueError("fresh watcher READY/STOPPED 순서 불일치 또는 BEGIN/START 존재")
    stopped = records[-1][1]
    validate_watcher_stopped_evidence(stopped, evidence)
    image = inspect_hex(paths["image"], data["files"]["image"]["sha256"], None)
    ranges = [{"start": start, "length": len(raw), "sha256": digest_bytes(raw)} for start, raw in image["ranges"]]
    if data.get("load_ranges") != ranges or not any(revisions["core"].encode() in raw for _, raw in image["ranges"]):
        raise ValueError("watcher full load range/revision 불일치")
    return {"data": data, "blobs": blobs, "image": image, "symbols": watcher_symbols(blobs["elf"]),
            "fixture_sha256": expected_hash}


def verify_watcher_ram(target, watcher: dict, monitor: RawResetMonitor) -> list[dict]:
    """! @brief exact ELF symbol과 현재 fresh nonce/미시작/STOP 완료 RAM을 읽기 전용 결합합니다. """
    expected = {"nonce": watcher["data"]["nonce"].encode("ascii") + b"\0", "started": b"\0",
                "cleanup_complete": b"\1", "stop_reported": b"\1", "failed": b"\0", "watchdog_channel": b"\xff" * 4}
    records = []
    for name, symbol in watcher["symbols"].items():
        monitor.sample()
        observed = bytes(target.read_memory_block8(symbol["address"], symbol["size"]))
        monitor.sample()
        if observed != expected[name]:
            raise IdleAuditFailure("watcher_ram_lifecycle_mismatch", {"symbol": name, "address": symbol["address"]})
        records.append({**symbol, "name": name, "read_sha256": digest_bytes(observed),
                        "read_value": observed[:-1].decode("ascii") if name == "nonce" else
                                      int.from_bytes(observed, "little", signed=name == "watchdog_channel"),
                        "expected_sha256": digest_bytes(expected[name]), "status": "PASS",
                        "elf_sha256": watcher["data"]["files"]["elf"]["sha256"],
                        "image_sha256": watcher["image"]["sha256"],
                        "source_revision": watcher["data"]["revisions"]["core"]})
    return records


def archive_watcher_fixture(watcher: dict, output: Path) -> dict:
    """! @brief 검증한 원본 bytes를 보존하며 run에서 같은 근거를 다시 읽게 합니다. """
    data = dict(watcher["data"], files={})
    for kind, raw in watcher["blobs"].items():
        name = "third-" + kind + ".bin"
        (output / name).write_bytes(raw)
        data["files"][kind] = {"path": name, "sha256": digest_bytes(raw)}
    path = output / "third-idle-fixture.json"
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return {"path": path.name, "sha256": sha256(path), "source_fixture_sha256": watcher["fixture_sha256"]}


def prepare_pair(args: argparse.Namespace, backend=None) -> None:
    """! @brief 기본은 local plan-only이며 execute와 세 명시적 동의 없이는 probe를 열지 않습니다. """
    args.output = args.output.resolve()
    args.sdk = args.sdk.resolve()
    hashes = [getattr(args, role + "_probe_sha256") for role in PREPARATION_ROLES]
    ports = [args.tx_port, args.rx_port]
    if len(set(hashes)) != 3 or any(not re.fullmatch(r"[0-9a-f]{64}", value) for value in hashes):
        raise ValueError("서로 다른 exact probe SHA 3개가 필요합니다")
    if (not all(ports) or len({port.casefold() for port in ports}) != 2 or
            any(re.search(r"[0-9a-fA-F]{32}", port) for port in ports)):
        raise ValueError("서로 다른 explicit TX/RX port가 필요합니다")
    if args.execute and not all((args.authorize_sector_program, args.authorize_tx_rx_algorithm_reset,
                                 args.authorize_third_halt_audit)):
        raise ValueError("TX/RX sector program/algorithm reset/third halt·audit 명시적 승인이 필요합니다")
    evidence = mdk_evidence(args.sdk)
    if args.firmware_identity != source_identity():
        raise ValueError("현재 DTM source identity와 다릅니다")
    images = [inspect_hex(getattr(args, role + "_hex"), getattr(args, role + "_hex_sha256"),
                          args.firmware_identity) for role in ("tx", "rx")]
    watcher = None
    if args.third_idle_fixture and args.third_idle_fixture.is_file():
        watcher = load_watcher_fixture(args.third_idle_fixture.resolve(), args.third_idle_fixture_sha256, hashes[2])
    if args.output.exists():
        raise ValueError("기존 준비 증거를 덮어쓰지 않습니다")
    args.output.mkdir(parents=True)
    report = {"schema_version": 1, "preparation_version": 3, "status": "NOT_RUN", "mode": "execute" if args.execute else "plan-only",
              "created_at_utc": datetime.now(timezone.utc).isoformat(), "sdk_evidence": evidence,
              "firmware_identity": args.firmware_identity, "transport": args.transport,
              "safety": {"erase": "sector_only", "auto_unlock": False, "mass_erase": False,
                         "recover": False, "resume_on_disconnect": False,
                          "third_program": False, "third_reset": False, "third_resume": False,
                          "radio_task_writes": False, "wdt_writes": False,
                          "tx_rx_passive_shorts_mask": RADIO_PASSIVE_SHORTS,
                          "soft_reset_is_full_chip_initialization": False},
              "boards": [dict(role=role, probe_sha256=identity,
                              **({"port": ports[index], **image_plan(images[index])} if index < 2 else {}))
                         for index, (role, identity) in enumerate(zip(PREPARATION_ROLES, hashes))],
              "stage": "local_plan", "runtime": "NOT_RUN", "cleanup": []}
    preflight = args.output / "preflight.json"
    if watcher is None:
        report["reason"] = "W02 native final fresh standard-watcher fixture required; regenerate with the authorized W02 runner"
        report["stage"] = "missing_w02_idle_fixture"
    else:
        report["boards"][2].update(image_plan(watcher["image"]))
    if not args.execute or watcher is None:
        preflight.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("M33_DIAG_PREPARE=NOT_RUN; PROBE_ACCESS=NONE; W02_IDLE_FIXTURE=" + ("VALID" if watcher else "REQUIRED"))
        return
    sessions = []
    mutated = set()
    monitor = None
    try:
        with ExitStack() as resources:
            resources.enter_context(HashedProbeLocks(hashes))
            resources.enter_context(private_debug_output())
            backend = backend or PyocdPreparationBackend()
            report["stage"] = "live_mapping"
            probes, live_ports = backend.discover()
            mapped = map_live_probes(probes, live_ports, hashes, ports)
            report["stage"] = "dp_ap_preflight"
            for index, probe in enumerate(mapped):
                with backend.session(probe, initialize=False) as session:
                    identity = backend.identity(session)
                    validate_debug_identity(identity)
                    report["boards"][index]["debug_identity"] = identity
            for probe in mapped:
                sessions.append(resources.enter_context(backend.session(probe)))
            try:
                ## @brief 세 보드가 모두 strict safe-idle이 아니면 program/reset/RADIO task를 실행하지 않습니다.
                report["stage"] = "all_boards_read_only_pre_audit"
                for index, session in enumerate(sessions):
                    report["audit_role"] = PREPARATION_ROLES[index]
                    mutated.add(index)
                    if index == 2:
                        monitor = RawResetMonitor(session.target)
                        halt_and_wait(session.target, monitor)
                        report["boards"][index]["pre_audit"] = verify_isolation(session.target, monitor)
                    else:
                        report["boards"][index]["pre_audit"] = isolate_radio(
                            session.target, allowed_shorts=RADIO_PASSIVE_SHORTS)
                report.pop("audit_role", None)
                report["stage"] = "w02_fresh_stopped_watcher"
                report["boards"][2]["readback"] = readback_ranges(sessions[2].target, watcher["image"]["ranges"], monitor=monitor)
                baseline = verify_isolation(sessions[2].target, monitor)
                baseline["watcher_ram"] = verify_watcher_ram(sessions[2].target, watcher, monitor)
                guard = ThirdGuard(sessions[2].target, baseline, monitor, watcher)
                report["third_idle"] = archive_watcher_fixture(watcher, args.output)
                report["third_lifecycle"] = {"origin": THIRD_IDLE_SCHEMA, "nonce": watcher["data"]["nonce"],
                                             "reset_program_resume_after_stopped": False}
                for index, image in enumerate(images):
                    report["stage"] = "program_" + PREPARATION_ROLES[index]
                    guard.check()
                    isolate_radio(sessions[index].target, allowed_shorts=RADIO_PASSIVE_SHORTS)
                    backend.program(sessions[index], image)
                    sessions[index].target.halt()
                    if sessions[index].target.get_state().name != "HALTED":
                        raise ValueError("program 이후 halt 불일치")
                    report["boards"][index]["readback"] = readback_ranges(sessions[index].target, image["ranges"])
                    ## @brief run-pair가 byte identity를 다시 검증하도록 exact HEX만 증거 폴더에 보관합니다.
                    (args.output / (PREPARATION_ROLES[index] + ".hex")).write_bytes(image["raw"])
                    guard.check()
                report["program_receipt"] = {
                    "schema_version": 1,
                    "kind": "m33_dtm_same_process_program_readback",
                    "source_revision": revision(ROOT),
                    "transport": args.transport,
                    "backend": "pyocd-sector-no-reset",
                    "roles": [
                        {
                            "role": PREPARATION_ROLES[index],
                            "probe_sha256": hashes[index],
                            "image_sha256": report["boards"][index]["image_sha256"],
                            "ranges": report["boards"][index]["ranges"],
                            "readback": report["boards"][index]["readback"],
                        }
                        for index in range(2)
                    ],
                }
                report["third_final"] = guard.check()
                report["status"] = "PREPARED"
                report["stage"] = "prepared_halted"
            finally:
                if report["status"] != "PREPARED":
                    for index in sorted(mutated):
                        try:
                            if index == 2:
                                verify_isolation(sessions[index].target, monitor)
                            else:
                                cleanup_monitor = halt_and_wait(sessions[index].target)
                                verify_isolation(sessions[index].target, cleanup_monitor,
                                                 allowed_shorts=RADIO_PASSIVE_SHORTS)
                            report["cleanup"].append({"role": PREPARATION_ROLES[index], "halt_read_only_audit": "PASS"})
                        except Exception:
                            report["cleanup"].append({"role": PREPARATION_ROLES[index], "halt_read_only_audit": "FAIL"})
    except Exception as error:
        report["status"] = "FAIL"
        ## @brief 예외 문자열에는 raw UID가 포함될 수 있어 type과 안전한 stage만 보존합니다.
        report["error_type"] = type(error).__name__
        if isinstance(error, IdleAuditFailure):
            report["audit_failure"] = error.evidence
    finally:
        preflight.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if report["status"] != "PREPARED":
        raise RuntimeError("DTM 준비 실패. preflight의 stage와 cleanup을 확인하고 자동 재시도하지 마세요") from None
    fixture = {"schema_version": 1, "preparation_version": 3, "firmware_identity": args.firmware_identity,
               "transport": args.transport, "third_board_state": "halted_verified", "third_radio_state": "disabled_verified",
               "third_guard_baseline": report["third_final"], "third_idle": report["third_idle"],
               "preflight_evidence_sha256": sha256(preflight), "start_required": True,
               "boards": report["boards"]}
    validate_fixture(fixture)
    (args.output / "fixture.json").write_text(json.dumps(fixture, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("M33_DIAG_PREPARE=PREPARED; TX_RX=HALTED; THIRD=KNOWN_SAFE_HALTED; RUNTIME=NOT_RUN")


class HashedProbeLocks:
    """! @brief 기존 HIL과 같은 hash 파일에 OS lock을 걸어 probe 동시 사용을 차단한다. """
    def __init__(self, hashes: list[str]):
        self.hashes = sorted(hashes)
        self.streams = []

    def __enter__(self):
        directory = Path(tempfile.gettempdir()) / "nu54dk-hil-locks"
        directory.mkdir(parents=True, exist_ok=True)
        try:
            for identity in self.hashes:
                stream = (directory / (identity + ".lock")).open("a+b")
                try:
                    if stream.seek(0, os.SEEK_END) == 0:
                        stream.write(b"0")
                        stream.flush()
                    stream.seek(0)
                    if os.name == "nt":
                        import msvcrt
                        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except Exception:
                    stream.close()
                    raise RuntimeError("probe가 이미 다른 HIL에서 사용 중입니다")
                self.streams.append(stream)
        except Exception:
            self.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, *_):
        for stream in reversed(self.streams):
            stream.close()
        self.streams.clear()


def validate_fixture(data: dict) -> None:
    """! @brief 3개 익명 probe·port·image와 세 번째 RF 격리 증거를 요구한다. """
    if (data.get("schema_version") != 1 or data.get("third_board_state") != "halted_verified" or
            data.get("third_radio_state") != "disabled_verified"):
        raise ValueError("세 번째 보드 CPU halt와 RADIO disabled 확인 증거가 필요합니다")
    boards = data.get("boards", [])
    if len(boards) != 3 or len({item.get("probe_sha256") for item in boards}) != 3:
        raise ValueError("서로 다른 3개 probe hash가 필요합니다")
    for item in boards:
        if not re.fullmatch(r"[0-9a-f]{64}", item.get("probe_sha256", "")) or not re.fullmatch(r"[0-9a-f]{64}", item.get("image_sha256", "")):
            raise ValueError("probe/image SHA-256이 필요합니다")
    if len({item.get("port") for item in boards[:2]}) != 2 or not all(item.get("port") for item in boards[:2]):
        raise ValueError("TX/RX serial port는 명시적으로 달라야 합니다")
    if not re.fullmatch(r"[0-9a-f]{104}", data.get("firmware_identity", "")):
        raise ValueError("실제 build의 firmware identity가 필요합니다")
    if not re.fullmatch(r"[0-9a-f]{64}", data.get("preflight_evidence_sha256", "")):
        raise ValueError("직전 debugger mapping/image/세 번째 보드 halt 증거 hash가 필요합니다")


def load_prepared_fixture(path: Path, h4: bool) -> dict:
    """! @brief 준비 증거와 fixture의 byte hash·내용을 결합하며 수동 선언만으로 실행하지 않습니다. """
    fixture = json.loads(path.read_text(encoding="utf-8"))
    validate_fixture(fixture)
    if fixture.get("preparation_version") != 3 or fixture.get("start_required") is not True:
        raise ValueError("prepare-pair가 생성한 halted fixture가 필요합니다")
    preflight = path.parent / "preflight.json"
    if not preflight.is_file() or sha256(preflight) != fixture["preflight_evidence_sha256"]:
        raise ValueError("실제 preflight 파일/hash 불일치")
    report = json.loads(preflight.read_text(encoding="utf-8"))
    expected_safety = {"erase": "sector_only", "auto_unlock": False, "mass_erase": False,
                       "recover": False, "resume_on_disconnect": False,
                       "third_program": False, "third_reset": False, "third_resume": False,
                       "radio_task_writes": False, "wdt_writes": False,
                       "tx_rx_passive_shorts_mask": RADIO_PASSIVE_SHORTS,
                       "soft_reset_is_full_chip_initialization": False}
    if (report.get("status") != "PREPARED" or report.get("mode") != "execute" or
            report.get("boards") != fixture["boards"] or
            report.get("firmware_identity") != fixture["firmware_identity"] or
            report.get("transport") != fixture.get("transport") or
            fixture.get("transport") != ("h4" if h4 else "twowire") or
            report.get("safety") != expected_safety or
            report.get("third_final") != fixture.get("third_guard_baseline") or
            report.get("third_lifecycle", {}).get("origin") != THIRD_IDLE_SCHEMA or
            report.get("third_lifecycle", {}).get("reset_program_resume_after_stopped") is not False or
            report.get("third_idle") != fixture.get("third_idle")):
        raise ValueError("실제 준비 결과/transport/safety가 fixture와 다릅니다")
    idle = fixture["third_idle"]
    load_watcher_fixture(path.parent / idle["path"], idle["sha256"], fixture["boards"][2]["probe_sha256"])
    return fixture


def open_prepared_pair(resources, path: Path, fixture: dict, backend):
    """! @brief 기존 lock 안에서 매 실행마다 mapping·identity·image·third 격리를 재확인합니다. """
    hashes = [item["probe_sha256"] for item in fixture["boards"]]
    ports = [item["port"] for item in fixture["boards"][:2]]
    probes, live_ports = backend.discover()
    mapped = map_live_probes(probes, live_ports, hashes, ports)
    for probe in mapped:
        with backend.session(probe, initialize=False) as session:
            validate_debug_identity(backend.identity(session))
    sessions = [resources.enter_context(backend.session(probe)) for probe in mapped]
    idle = fixture["third_idle"]
    watcher = load_watcher_fixture(path.parent / idle["path"], idle["sha256"], hashes[2])
    monitor = RawResetMonitor(sessions[2].target)
    guard = ThirdGuard(sessions[2].target, fixture["third_guard_baseline"], monitor, watcher)
    guard.check()
    for index, role in enumerate(("tx", "rx")):
        if sessions[index].target.get_state().name != "HALTED":
            raise ValueError("prepare 이후 TX/RX 상태가 바뀌었습니다")
        image = inspect_hex(path.parent / (role + ".hex"), fixture["boards"][index]["image_sha256"],
                            fixture["firmware_identity"])
        readback_ranges(sessions[index].target, image["ranges"])
    readback_ranges(sessions[2].target, watcher["image"]["ranges"], monitor=monitor)
    guard.check()
    return sessions, guard


def run_pair(args: argparse.Namespace) -> None:
    """! @brief flash 없이 두 exact image를 역할 교대하며 검사하고 양쪽 STOP을 보존한다. """
    if not args.authorize_start_tx_rx:
        raise ValueError("TX/RX만 software reset-halt-resume할 명시적 승인이 필요합니다")
    args.fixture = args.fixture.resolve()
    args.output = args.output.resolve()
    fixture = load_prepared_fixture(args.fixture, args.h4)
    import serial
    if args.output.exists():
        raise ValueError("기존 증거를 덮어쓰지 않습니다")
    args.output.mkdir(parents=True)
    report = {"test_id": "M33-DIAG-01", "status": "FAIL", "fixture_sha256": sha256(args.fixture),
              "startup_settle_ms": 1000, "cases": [], "negative": [], "cleanup": []}
    ports = []
    try:
        with ExitStack() as resources:
            resources.enter_context(HashedProbeLocks([item["probe_sha256"] for item in fixture["boards"]]))
            resources.enter_context(private_debug_output())
            backend = PyocdPreparationBackend()
            sessions, guard = open_prepared_pair(resources, args.fixture, fixture, backend)
            try:
                for index, board in enumerate(fixture["boards"][:2]):
                    port = resources.enter_context(serial.Serial(board["port"], 115200 if args.h4 else 19200,
                                                                  timeout=AUDIT_INTERVAL, write_timeout=AUDIT_INTERVAL))
                    endpoint = DtmPort(port, args.h4, guard)
                    ports.append(endpoint)
                    guard.check()
                    backend.start(sessions[index])
                    ## @brief SDC raw controller와 UARTE polling loop가 준비되기 전에 첫 frame을 보내지 않습니다.
                    guard.wait(1.0)
                    port.reset_input_buffer()
                    guard.check()
                    if endpoint.identity() != fixture["firmware_identity"]:
                        raise ValueError("실물 firmware identity가 준비된 image와 다릅니다")
                    endpoint.stop()
                for index, endpoint in enumerate(ports):
                    guard.check()
                    endpoint.negative()
                    endpoint.start(False, 19, 1)
                    guard.wait(3.2)
                    endpoint.automatic_stop()
                    endpoint.stop()
                    report["negative"].append({"role": index, "range_length_busy": "PASS", "firmware_lease": "PASS"})
                for tx in (0, 1):
                    rx = 1 - tx
                    for phy in (1, 2):
                        for channel in (0, 19, 39):
                            guard.check()
                            ports[rx].start(False, channel, phy)
                            ports[tx].start(True, channel, phy)
                            started = time.monotonic()
                            guard.wait(0.5)
                            ports[tx].stop()
                            elapsed_ms = round((time.monotonic() - started) * 1000)
                            received = ports[rx].stop()
                            guard.check()
                            passed = 50 <= received <= 2000 and 450 <= elapsed_ms <= 1500
                            report["cases"].append({"tx_role": tx, "rx_role": rx, "phy": phy, "channel": channel,
                                                    "payload": "PRBS9-37", "duration_ms": 500, "received": received,
                                                    "observed_tx_ms": elapsed_ms,
                                                    "status": "PASS" if passed else "FAIL"})
                            if not passed:
                                raise ValueError("RX packet count가 고정 50..2000 범위 밖입니다")
                report["status"] = "PASS"
            finally:
                for index, endpoint in enumerate(ports):
                    try:
                        ## @brief guard 실패 후에도 RF STOP 전송을 시도하되 새 RF 시작은 허용하지 않습니다.
                        endpoint.guard = None
                        endpoint.serial.timeout = 1.5
                        endpoint.stop()
                        report["cleanup"].append({"role": index, "stop": "PASS"})
                    except Exception as error:
                        report["cleanup"].append({"role": index, "stop": "FAIL", "error_type": type(error).__name__})
                        report["status"] = "FAIL"
                try:
                    report["third_final"] = guard.check()
                    report["third_audit_checks"] = guard.checks
                except Exception:
                    report["third_final"] = {"status": "FAIL"}
                    report["status"] = "FAIL"
    except Exception as error:
        report["error_type"] = type(error).__name__
        if isinstance(error, IdleAuditFailure):
            report["audit_failure"] = error.evidence
        report["status"] = "FAIL"
    finally:
        report["transcripts"] = [port.transcript for port in ports]
        (args.output / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if report["status"] != "PASS" or len(report["cases"]) != 12 or len(report["cleanup"]) != 2:
        raise RuntimeError("DTM 시험 또는 양쪽 STOP이 실패했습니다. RF lease와 watchdog은 firmware에서 유지합니다")
    print("M33_DIAG_PAIR_PASS=12; STOP=2; RF_METROLOGY=NOT_RUN")


def main() -> None:
    """! @brief 목록 조회/build/실물 실행의 부작용 경계를 명령별로 분리한다. """
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    commands.add_parser("inventory")
    builder = commands.add_parser("build")
    builder.add_argument("--sdk", type=Path, required=True)
    builder.add_argument("--toolchain", type=Path, required=True)
    builder.add_argument("--output", type=Path, required=True)
    builder.add_argument("--reuse-build-root", type=Path,
                         help="수정 source 재검증용 기존 build root. 이전 HEX는 새 output에 보존한다")
    builder.add_argument("--jobs", type=int, choices=range(1, 3), default=2)
    builder.add_argument("--routes", nargs="+", choices=[name for name, value in ROUTES.items() if value[1] != "excluded"], default=["dtm_twowire", "dtm_hci"])
    preparer = commands.add_parser("prepare-pair", help="기본 local plan-only; 명시적 execute 승인 전 probe 접근 없음")
    preparer.add_argument("--sdk", type=Path, required=True)
    preparer.add_argument("--output", type=Path, required=True)
    preparer.add_argument("--firmware-identity", required=True)
    preparer.add_argument("--transport", choices=("twowire", "h4"), required=True)
    for role in PREPARATION_ROLES:
        preparer.add_argument("--" + role + "-probe-sha256", required=True)
        if role != "third":
            preparer.add_argument("--" + role + "-port", required=True)
            preparer.add_argument("--" + role + "-hex", type=Path, required=True)
            preparer.add_argument("--" + role + "-hex-sha256", required=True)
    preparer.add_argument("--execute", action="store_true")
    preparer.add_argument("--authorize-sector-program", action="store_true")
    preparer.add_argument("--authorize-tx-rx-algorithm-reset", action="store_true",
                          help="flash algorithm의 TX/RX software reset 허용; third reset이나 recover 허용이 아님")
    preparer.add_argument("--authorize-third-halt-audit", action="store_true")
    preparer.add_argument("--third-idle-fixture", type=Path,
                          help="W02 native final fresh 미시작 standard-watcher 증거; 없으면 NOT_RUN")
    preparer.add_argument("--third-idle-fixture-sha256", default="")
    runner = commands.add_parser("run-pair")
    runner.add_argument("--fixture", type=Path, required=True)
    runner.add_argument("--output", type=Path, required=True)
    runner.add_argument("--h4", action="store_true")
    runner.add_argument("--authorize-start-tx-rx", action="store_true")
    args = parser.parse_args()
    if args.action == "inventory":
        print(json.dumps({name: {"source": value[0], "route": value[1], "reason": value[2]} for name, value in ROUTES.items()}, ensure_ascii=False, indent=2))
    elif args.action == "build":
        build(args)
    elif args.action == "prepare-pair":
        prepare_pair(args)
    else:
        run_pair(args)


if __name__ == "__main__":
    main()
