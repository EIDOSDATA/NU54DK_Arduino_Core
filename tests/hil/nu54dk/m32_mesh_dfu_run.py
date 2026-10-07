#!/usr/bin/env python3
"""! @brief 세 NU54DK에서 signed Mesh DFU 5회와 MCUboot rollback을 검증합니다. """

from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import sys
import time
from typing import Any, Sequence


HIL = Path(__file__).resolve().parent
REPOSITORY = HIL.parents[2]
if str(HIL) not in sys.path:
    sys.path.insert(0, str(HIL))

from ble_pair_hil_common import (  # noqa: E402
    BOARD_ROOT,
    clear_nrf54l_rram_pyocd_sha256,
    erase_nrf54l_rram_pyocd_sha256,
    file_sha256,
    flash_binary_pyocd_sha256,
    flash_image_pyocd_sha256,
    git_revision,
    reset_target_pyocd_sha256,
    validate_board_revision,
    validate_build_record,
    validate_image_unchanged,
    validate_source_clean,
)
from m33_sdk_risk_common import (  # noqa: E402
    copy_program_inputs,
    dispatch_attestation,
    exact_program_evidence,
    readback_programmed_images,
    require_exact_clean_source,
    reserve_sidecars,
    validate_programming_receipt,
)
from m6_serial_echo import import_pyserial  # noqa: E402
from m32_ble_capability_run import (  # noqa: E402
    collect_register_identity_sha256,
    discover,
)
from v04_protocol import ProbeLocks  # noqa: E402


MILESTONE = "M32"
APPLICATION_ROOT = REPOSITORY / "tests/zephyr/m32_mesh_dfu_hil"
RUNNER_PATH = Path(__file__).resolve()
APPLICATION_DOMAIN = "m32_mesh_dfu_hil"
BOOT_DOMAIN = "mcuboot"
ROLES = ("distributor", "target_a", "target_b")
PROTOCOL = "M32MDFU|1"
MCUBOOT_MAGIC = 0x96F3B83D
SLOT1_OFFSET = 794624
SLOT1_SIZE = 729088
SLOT1_END = SLOT1_OFFSET + SLOT1_SIZE
BASE_VERSION = (0, 0, 0, 0)
CANDIDATE_VERSION = (2, 0, 0, 0)
ITERATION_TARGET = 5
TARGET_RESULT_DENOMINATOR = 10
REMOTE_NODE_TARGET = 2
SETTINGS_STORAGE_START = 0x174000
SETTINGS_STORAGE_SIZE = 0x9000

_active_attempt: dict[str, Any] | None = None


class MeshDfuFailure(RuntimeError):
    """! @brief build·V2 probe·DFU·rollback 계약 실패입니다. """


def validate_capacity(values: dict[str, str]) -> dict[str, int]:
    """! @brief CDB node slot이 local Distributor와 두 Target을 수용하는지 확인합니다. """

    node_slots = integer(values, "cdb_node_slots")
    local_slots = integer(values, "cdb_local_slots")
    remote_capacity = node_slots - local_slots
    if local_slots != 1 or remote_capacity < REMOTE_NODE_TARGET:
        raise MeshDfuFailure(
            "CDB remote node capacity mismatch: "
            f"required={REMOTE_NODE_TARGET}, actual={remote_capacity}"
        )
    return {
        "cdb_node_slots": node_slots,
        "cdb_local_slots": local_slots,
        "cdb_remote_capacity": remote_capacity,
    }


def reject_target_fault(role: str, line: str) -> None:
    """! @brief Zephyr fatal·stack fault를 긴 DFU timeout 전에 즉시 거부합니다. """

    lowered = line.lower()
    if any(
        marker in lowered
        for marker in ("stack overflow", "fatal error", "usage fault", "hard fault")
    ):
        raise MeshDfuFailure(f"{role} target fault: {line[:120]}")


@dataclass(frozen=True)
class ImageInput:
    """! @brief 실행 중 변경을 금지한 image byte identity입니다. """

    path: Path
    size: int
    sha256: str
    version: tuple[int, int, int, int] | None


@dataclass(frozen=True)
class BuildInput:
    """! @brief 한 역할의 exact sysbuild 산출물입니다. """

    role: str
    root: Path
    boot_hex: ImageInput
    signed_hex: ImageInput
    signed_bin: ImageInput
    raw_bin: ImageInput
    public_key_sha256: str
    build_record: dict[str, str]
    candidate_sha256: str | None
    candidate_size: int | None


def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    """! @brief 네 sysbuild·세 익명 probe·외부 key·증적 경로를 선언합니다. """

    parser = argparse.ArgumentParser(
        description="M32-MDFU-01 signed Distributor→두 Target과 rollback을 검증합니다."
    )
    for role in ROLES:
        option = role.replace("_", "-")
        parser.add_argument(f"--probe-{option}-sha256", required=True)
        parser.add_argument(f"--build-{option}", required=True, type=Path)
    parser.add_argument("--build-candidate", required=True, type=Path)
    parser.add_argument("--signing-key", required=True, type=Path)
    parser.add_argument("--output-prefix", required=True, type=Path)
    parser.add_argument("--flash-timeout", type=float, default=180.0)
    parser.add_argument("--result-timeout", type=float, default=10800.0)
    return parser.parse_args(arguments)


def path_is_within(path: Path, parent: Path) -> bool:
    """! @brief symlink 해석 뒤 path가 parent 내부인지 판정합니다. """

    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def validate_private_key(argument: Path) -> Path:
    """! @brief 저장소 밖 P-256 private-key PEM만 허용합니다. """

    path = argument.resolve()
    if not path.is_file() or path.suffix.casefold() != ".pem":
        raise MeshDfuFailure("--signing-key가 외부 PEM 파일이 아닙니다")
    if path_is_within(path, REPOSITORY):
        raise MeshDfuFailure("signing key를 저장소 내부에 둘 수 없습니다")
    payload = path.read_bytes()
    if not any(
        marker in payload
        for marker in (b"-----BEGIN PRIVATE KEY-----", b"-----BEGIN EC PRIVATE KEY-----")
    ):
        raise MeshDfuFailure("signing key에 private-key PEM header가 없습니다")
    return path


def parse_mcuboot_version(path: Path) -> tuple[int, int, int, int] | None:
    """! @brief MCUboot v1 header의 semantic version을 읽습니다. """

    header = path.read_bytes()[:32]
    if len(header) < 32:
        raise MeshDfuFailure(f"image가 MCUboot header보다 작습니다: {path}")
    if struct.unpack_from("<I", header, 0)[0] != MCUBOOT_MAGIC:
        return None
    if struct.unpack_from("<H", header, 8)[0] != 0x800:
        raise MeshDfuFailure(f"MCUboot header size가 0x800이 아닙니다: {path}")
    return struct.unpack_from("<BBHI", header, 20)


def immutable_image(
    path: Path, expected_version: tuple[int, int, int, int] | None
) -> ImageInput:
    """! @brief image 존재·slot 상한·version·hash를 한 번에 고정합니다. """

    path = path.resolve()
    if not path.is_file() or path.stat().st_size <= 0:
        raise MeshDfuFailure(f"image가 없습니다: {path}")
    if path.suffix.casefold() == ".bin" and path.stat().st_size > SLOT1_SIZE:
        raise MeshDfuFailure(f"image가 secondary slot보다 큽니다: {path}")
    version = parse_mcuboot_version(path) if path.suffix.casefold() == ".bin" else None
    if version != expected_version:
        raise MeshDfuFailure(
            f"image version 불일치: {path.name}: {version}, expected={expected_version}"
        )
    return ImageInput(path, path.stat().st_size, file_sha256(path), version)


def require_tokens(path: Path, tokens: Sequence[str]) -> str:
    """! @brief 생성 설정에서 필수 보안 token을 확인합니다. """

    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise MeshDfuFailure(f"생성 설정을 읽지 못했습니다: {path}: {error}") from error
    for token in tokens:
        if token not in text:
            raise MeshDfuFailure(f"생성 설정 token이 없습니다: {token}")
    return text


def classify_mcuboot_watchdog(
    application_config: str,
    boot_config: str,
    runtime_attestation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """! @brief 실제 활성 WDT 여부와 MCUboot feed 실행 증거를 분리해 판정합니다. """

    feed_enabled = (
        "CONFIG_BOOT_WATCHDOG_FEED=y" in boot_config
        or "CONFIG_BOOT_WATCHDOG_FEED_NRFX_WDT=y" in boot_config
    )
    watchdog_driver_enabled = (
        "CONFIG_WATCHDOG=y" in application_config
        and "CONFIG_WDT_NRFX=y" in application_config
    )
    if not watchdog_driver_enabled:
        return {
            "status": "NOT_APPLICABLE",
            "condition": "application_watchdog_not_enabled",
            "boot_feed_configured": feed_enabled,
            "active_watchdog_proven": False,
        }
    if runtime_attestation is None:
        return {
            "status": "NOT_RUN",
            "condition": "active_watchdog_runtime_attestation_required",
            "boot_feed_configured": feed_enabled,
            "active_watchdog_proven": False,
        }
    required = {
        "watchdog_active": True,
        "erase_observed": True,
        "swap_observed": True,
        "hash_observed": True,
        "unexpected_watchdog_resets": 0,
    }
    if any(runtime_attestation.get(key) != value for key, value in required.items()):
        raise MeshDfuFailure("active MCUboot watchdog runtime attestation mismatch")
    timeout_ms = runtime_attestation.get("timeout_ms")
    if not isinstance(timeout_ms, int) or timeout_ms < 1:
        raise MeshDfuFailure("active MCUboot watchdog timeout missing")
    if not feed_enabled:
        raise MeshDfuFailure("active watchdog image has no MCUboot feed configuration")
    return {
        "status": "PASS",
        "condition": "active_watchdog_erase_swap_hash",
        "boot_feed_configured": True,
        "active_watchdog_proven": True,
        "timeout_ms": timeout_ms,
    }


def build_watchdog_classification(build: "BuildInput") -> dict[str, Any]:
    """! @brief exact sysbuild의 app/MCUboot 설정을 읽어 적용 조건을 분류합니다. """

    application_config = require_tokens(build.root / APPLICATION_DOMAIN / "zephyr/.config", ())
    boot_config = require_tokens(build.root / BOOT_DOMAIN / "zephyr/.config", ())
    classification = classify_mcuboot_watchdog(application_config, boot_config)
    if classification["status"] == "NOT_RUN":
        raise MeshDfuFailure(
            "활성 WDT 구성이지만 erase/swap/hash runtime attestation이 없습니다"
        )
    return classification


def config_symbol(text: str, symbol: str) -> str:
    """! @brief exact Kconfig byte에서 y 또는 비활성 n을 중복 없이 읽습니다. """

    enabled = re.findall(rf"(?m)^{re.escape(symbol)}=y$", text)
    disabled = re.findall(
        rf"(?m)^(?:{re.escape(symbol)}=n|# {re.escape(symbol)} is not set)$",
        text,
    )
    if len(enabled) + len(disabled) != 1:
        raise MeshDfuFailure(f"{symbol} exact 설정을 판정할 수 없습니다")
    return "y" if enabled else "n"


def copy_watchdog_condition_evidence(
    native_path: Path,
    builds: dict[str, "BuildInput"],
    classifications: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """! @brief 네 sysbuild의 실제 .config와 build record byte를 인접 증거로 복사합니다. """

    if set(builds) != set(ROLES) | {"candidate"} or set(classifications) != set(builds):
        raise MeshDfuFailure("watchdog build denominator mismatch")
    records: dict[str, dict[str, Any]] = {}
    for role, build in builds.items():
        if classifications[role].get("status") != "NOT_APPLICABLE" or \
                classifications[role].get("condition") != "application_watchdog_not_enabled":
            raise MeshDfuFailure("active watchdog condition cannot be attested as N/A")
        application_source = build.root / APPLICATION_DOMAIN / "zephyr/.config"
        boot_source = build.root / BOOT_DOMAIN / "zephyr/.config"
        build_record_source = (
            build.signed_hex.path.parent.parent / build.build_record["record_name"]
        )
        sources = {
            "application_config": application_source,
            "mcuboot_config": boot_source,
            "build_record": build_record_source,
        }
        copied: dict[str, dict[str, str]] = {}
        for label, source in sources.items():
            destination = native_path.with_name(
                f"{native_path.stem}.{role}.{label}.evidence"
            )
            if destination.exists() or not source.is_file():
                raise MeshDfuFailure(f"{role} {label} evidence path mismatch")
            shutil.copyfile(source, destination)
            if file_sha256(destination) != file_sha256(source):
                raise MeshDfuFailure(f"{role} {label} evidence copy mismatch")
            copied[label] = {
                "path": destination.name,
                "sha256": file_sha256(destination),
            }
        if copied["build_record"]["sha256"] != build.build_record["record_sha256"]:
            raise MeshDfuFailure(f"{role} exact build record digest mismatch")
        application_text = application_source.read_text(encoding="utf-8")
        records[role] = {
            "status": "NOT_APPLICABLE",
            "condition": "application_watchdog_disabled",
            "symbols": {
                "CONFIG_WATCHDOG": config_symbol(
                    application_text, "CONFIG_WATCHDOG"
                ),
            },
            "boot_feed_configured": classifications[role][
                "boot_feed_configured"
            ],
            **copied,
        }
        if records[role]["symbols"]["CONFIG_WATCHDOG"] != "n":
            raise MeshDfuFailure("disabled application watchdog config mismatch")
    return {
        "schema_version": 1,
        "kind": "m33_mcuboot_watchdog_condition",
        "status": "NOT_APPLICABLE",
        "condition": "application_watchdog_disabled",
        "builds": records,
    }


def cache_value(text: str, key: str) -> str:
    """! @brief CMakeCache의 단일 문자열 값을 반환합니다. """

    match = re.search(rf"(?m)^{re.escape(key)}:[^=]+=(.*)$", text)
    if match is None:
        raise MeshDfuFailure(f"CMake cache 값이 없습니다: {key}")
    return match.group(1).strip()


def validate_domains(root: Path) -> None:
    """! @brief sysbuild domain과 flash 순서를 app→boot 계약에 고정합니다. """

    path = root / "domains.yaml"
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise MeshDfuFailure(f"domains.yaml을 읽지 못했습니다: {error}") from error
    if len(text) > 8192:
        raise MeshDfuFailure("domains.yaml 크기가 허용 범위를 넘습니다")
    entries = re.findall(
        r"(?m)^  - name: ([a-z0-9_]+)\r?\n    build_dir: (.+)$", text
    )
    if [name for name, _directory in entries] != [APPLICATION_DOMAIN, BOOT_DOMAIN]:
        raise MeshDfuFailure(f"sysbuild domain 구성이 다릅니다: {entries!r}")
    for name, directory in entries:
        if Path(directory.strip()).resolve() != (root / name).resolve():
            raise MeshDfuFailure(f"{name} build_dir가 exact sysbuild root와 다릅니다")
    match = re.search(r"(?ms)^flash_order:\r?\n((?:  - [a-z0-9_]+\r?\n?)+)", text)
    if match is None:
        raise MeshDfuFailure("domains.yaml에 flash_order가 없습니다")
    order = re.findall(r"(?m)^  - ([a-z0-9_]+)$", match.group(1))
    if order != [BOOT_DOMAIN, APPLICATION_DOMAIN]:
        raise MeshDfuFailure(f"sysbuild flash_order가 다릅니다: {order!r}")


def collect_build(
    root_argument: Path,
    role: str,
    core_revision: str,
    board_revision: str,
    signing_key: Path,
) -> BuildInput:
    """! @brief 역할·key·version·build record가 일치하는 sysbuild만 수락합니다. """

    root = root_argument.resolve()
    validate_domains(root)
    app = root / APPLICATION_DOMAIN
    boot = root / BOOT_DOMAIN
    cache = require_tokens(root / "CMakeCache.txt", (f"M32_MDFU_ROLE:UNINITIALIZED={role}",))
    expected_version = CANDIDATE_VERSION if role == "candidate" else BASE_VERSION
    expected_counter = 2 if role == "candidate" else 1
    require_tokens(
        app / "zephyr/.config",
        (
            "CONFIG_BOOTLOADER_MCUBOOT=y",
            f'CONFIG_MCUBOOT_IMGTOOL_SIGN_VERSION="{expected_version[0]}.0.0+0"',
            f'CONFIG_MCUBOOT_EXTRA_IMGTOOL_ARGS="--security-counter {expected_counter}"',
        ),
    )
    boot_config = require_tokens(
        boot / "zephyr/.config",
        (
            "CONFIG_BOOT_SIGNATURE_TYPE_ECDSA_P256=y",
            "CONFIG_MCUBOOT_DOWNGRADE_PREVENTION=y",
            "CONFIG_MCUBOOT_DOWNGRADE_PREVENTION_SECURITY_COUNTER=y",
        ),
    )
    key_match = re.search(r'^CONFIG_BOOT_SIGNATURE_KEY_FILE="(.+)"$', boot_config, re.M)
    if key_match is None or Path(key_match.group(1)).resolve() != signing_key:
        raise MeshDfuFailure(f"{role} MCUboot signing key identity가 다릅니다")

    signed_hex = immutable_image(app / "zephyr/zephyr.signed.hex", None)
    raw_bin = immutable_image(app / "zephyr/zephyr.bin", None)
    if core_revision.encode("ascii") not in raw_bin.path.read_bytes():
        raise MeshDfuFailure(f"{role} application image에 exact Core revision이 없습니다")
    build_record = validate_build_record(
        signed_hex.path, core_revision, board_revision, APPLICATION_ROOT
    )
    public_key = boot / "zephyr/autogen-pubkey.c"
    if not public_key.is_file() or public_key.stat().st_size <= 0:
        raise MeshDfuFailure(f"{role} MCUboot public key source가 없습니다")

    candidate_sha256: str | None = None
    candidate_size: int | None = None
    if role != "candidate":
        candidate_sha256 = cache_value(cache, "M32_MDFU_CANDIDATE_SHA256")
        size_text = cache_value(cache, "M32_MDFU_CANDIDATE_SIZE")
        if re.fullmatch(r"[1-9][0-9]*", size_text) is None:
            raise MeshDfuFailure(f"{role} candidate size cache 형식이 잘못됐습니다")
        candidate_size = int(size_text)

    return BuildInput(
        role=role,
        root=root,
        boot_hex=immutable_image(boot / "zephyr/zephyr.hex", None),
        signed_hex=signed_hex,
        signed_bin=immutable_image(app / "zephyr/zephyr.signed.bin", expected_version),
        raw_bin=raw_bin,
        public_key_sha256=file_sha256(public_key),
        build_record=build_record,
        candidate_sha256=candidate_sha256,
        candidate_size=candidate_size,
    )


def validate_build_set(builds: dict[str, BuildInput]) -> None:
    """! @brief 네 역할이 동일 key와 candidate byte identity를 공유하는지 검사합니다. """

    candidate = builds["candidate"].signed_bin
    if len({build.public_key_sha256 for build in builds.values()}) != 1:
        raise MeshDfuFailure("역할별 MCUboot public key가 다릅니다")
    for role in ROLES:
        build = builds[role]
        if build.candidate_sha256 != candidate.sha256:
            raise MeshDfuFailure(f"{role}에 고정된 candidate SHA-256이 다릅니다")
        if build.candidate_size != candidate.size:
            raise MeshDfuFailure(f"{role}에 고정된 candidate size가 다릅니다")


def erase_secondary_slot(probe_sha256: str, timeout_seconds: float) -> None:
    """! @brief secondary slot의 exact sector 범위만 지웁니다. """

    erase_nrf54l_rram_pyocd_sha256(
        "secondary",
        probe_sha256,
        SLOT1_OFFSET,
        SLOT1_END - SLOT1_OFFSET,
        timeout_seconds,
    )


def flash_secondary_candidate(
    probe_sha256: str, image: ImageInput, timeout_seconds: float
) -> str:
    """! @brief Distributor secondary slot에 signed binary를 sector 방식으로 기록합니다. """

    _mode, programmed = flash_binary_pyocd_sha256(
        "distributor_candidate",
        probe_sha256,
        image.path,
        SLOT1_OFFSET,
        timeout_seconds,
        defer_reset=True,
    )
    return programmed


def access_preserving_reset(probe_sha256: str, timeout_seconds: float) -> None:
    """! @brief nRF54L 접근 보호를 보존하는 system reset을 수행합니다. """

    reset_target_pyocd_sha256(
        "mesh_dfu",
        probe_sha256,
        min(timeout_seconds, 30.0),
    )


def fields(line: str) -> dict[str, str]:
    """! @brief protocol의 중복 없는 key=value field를 반환합니다. """

    output: dict[str, str] = {}
    for field in line.split("|")[3:]:
        if "=" not in field:
            continue
        key, value = field.split("=", 1)
        if key in output:
            raise MeshDfuFailure(f"중복 protocol field: {key}")
        output[key] = value
    return output


def integer(values: dict[str, str], key: str) -> int:
    """! @brief 필수 decimal field를 음이 아닌 정수로 변환합니다. """

    value = values.get(key, "")
    if re.fullmatch(r"[0-9]+", value) is None:
        raise MeshDfuFailure(f"정수 protocol field 오류: {key}")
    return int(value)


def send(port: Any, line: str) -> None:
    """! @brief ASCII 명령 한 줄을 완전히 기록합니다. """

    payload = (line + "\n").encode("ascii")
    if port.write(payload) != len(payload):
        raise MeshDfuFailure("UART command가 일부만 기록됐습니다")
    port.flush()


def read_record(
    role: str,
    port: Any,
    record: str,
    transcript: list[str],
    deadline: float,
    *,
    nonce: str | None = None,
    core_revision: str | None = None,
) -> dict[str, str]:
    """! @brief boot noise를 건너뛰고 역할의 exact protocol record를 기다립니다. """

    while time.monotonic() < deadline:
        payload = port.readline()
        if not payload:
            continue
        if len(payload) > 1024:
            raise MeshDfuFailure(f"{role} UART line이 너무 깁니다")
        line = payload.decode("ascii", errors="replace").strip()
        if not line.startswith(PROTOCOL + "|"):
            if line:
                transcript.append(f"{role}-raw: {line}")
                reject_target_fault(role, line)
            continue
        transcript.append(f"{role}: {line}")
        values = fields(line)
        if line.startswith(f"{PROTOCOL}|FAIL|"):
            raise MeshDfuFailure(f"{role} target FAIL: {values.get('stage', 'unknown')}")
        if not line.startswith(f"{PROTOCOL}|{record}|"):
            continue
        if values.get("role") != role:
            raise MeshDfuFailure(f"{record} role 불일치")
        if nonce is not None and values.get("nonce") != nonce:
            raise MeshDfuFailure(f"{record} nonce 불일치")
        if core_revision is not None and values.get("core") != core_revision:
            raise MeshDfuFailure(f"{record} Core revision 불일치")
        return values
    raise MeshDfuFailure(f"{role} {record} timeout")


def cleanup_ports(
    ports: dict[str, Any],
    nonce: str,
    core_revision: str,
    transcript: list[str],
    required: bool,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    """! @brief 정상·예외 경로 모두에서 세 역할 STOP을 독립 시도합니다. """

    report: dict[str, Any] = {
        "required": required,
        "command_sent": {role: False for role in ROLES},
        "stopped": {role: False for role in ROLES},
        "errors": [],
        "status": "NOT_REQUIRED" if not required else "FAIL",
    }
    if not required:
        return report
    if not ports:
        report["errors"].append("cleanup required before serial endpoint was available")
        return report
    for role, port in ports.items():
        try:
            send(port, f"{PROTOCOL}|STOP|nonce={nonce}")
            report["command_sent"][role] = True
        except Exception as error:
            report["errors"].append(f"{role} STOP: {type(error).__name__}: {error}")
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        progressed = False
        for role, port in ports.items():
            if report["stopped"][role]:
                continue
            try:
                payload = port.readline()
            except Exception as error:
                report["errors"].append(
                    f"{role} cleanup read: {type(error).__name__}: {error}"
                )
                continue
            if not payload:
                continue
            progressed = True
            line = payload.decode("ascii", errors="replace").strip()
            if not line.startswith(PROTOCOL + "|"):
                continue
            transcript.append(f"{role}: {line}")
            try:
                values = fields(line)
            except Exception as error:
                report["errors"].append(
                    f"{role} cleanup parse: {type(error).__name__}: {error}"
                )
                continue
            if (
                line.startswith(f"{PROTOCOL}|STOPPED|")
                and values.get("role") == role
                and values.get("nonce") == nonce
                and values.get("core") == core_revision
                and values.get("cleanup") == "pass"
            ):
                report["stopped"][role] = True
        if (
            set(ports) == set(ROLES)
            and all(report["command_sent"].values())
            and all(report["stopped"].values())
        ):
            report["status"] = "PASS"
            return report
        if not progressed:
            time.sleep(0.005)
    report["errors"].append("bounded Mesh DFU cleanup evidence incomplete")
    return report


def close_ports(ports: dict[str, Any]) -> dict[str, str]:
    """! @brief 부분 serial open을 포함해 모든 handle close 결과를 기록합니다. """

    result = {role: "NOT_OPENED" for role in ROLES}
    for role, port in ports.items():
        try:
            port.close()
            result[role] = "PASS"
        except Exception as error:
            result[role] = f"FAIL:{type(error).__name__}:{error}"
    return result


@contextmanager
def pre_serial_cleanup_guard(
    state: dict[str, Any],
    ports: dict[str, Any],
    nonce: str,
    core_revision: str,
    transcript: list[str],
    failure_evidence: dict[str, Any],
):
    """! @brief reset 뒤 serial 소유권 이전 전 예외도 정리 실패로 기록합니다. """

    try:
        yield
    finally:
        if state["radio_started"] and not state["serial_cleanup_owned"]:
            try:
                cleanup = cleanup_ports(
                    ports,
                    nonce,
                    core_revision,
                    transcript,
                    required=True,
                )
            except Exception as error:
                cleanup = {
                    "required": True,
                    "status": "FAIL",
                    "errors": [
                        f"cleanup exception: {type(error).__name__}: {error}"
                    ],
                }
            finally:
                closed = close_ports(ports)
            failure_evidence["cleanup"] = cleanup
            failure_evidence["serial_close"] = closed


def validate_boot(
    role: str,
    values: dict[str, str],
    version: str,
    confirmed: int,
    iteration: int | None = None,
) -> None:
    """! @brief candidate 또는 rollback BOOT 정량 상태를 판정합니다. """

    if values.get("version") != version or integer(values, "confirmed") != confirmed:
        raise MeshDfuFailure(f"{role} BOOT version/confirm 불일치")
    if iteration is not None and not 1 <= iteration <= ITERATION_TARGET:
        raise MeshDfuFailure("iteration 범위 오류")


def collect_iteration(
    ports: dict[str, Any],
    iteration: int,
    nonce: str,
    core_revision: str,
    candidate: ImageInput,
    transcript: list[str],
    deadline: float,
) -> tuple[
    dict[str, dict[str, str]],
    dict[str, str] | None,
    dict[str, str] | None,
    dict[str, Any],
]:
    """! @brief 두 candidate boot·APPLIED와 Distributor iteration을 함께 수집합니다. """

    boots: dict[str, dict[str, str]] = {}
    applied: dict[str, dict[str, str]] = {}
    distributor_iteration: dict[str, str] | None = None
    final_result: dict[str, str] | None = None
    final_end: dict[str, str] | None = None
    while time.monotonic() < deadline:
        progressed = False
        for role, port in ports.items():
            payload = port.readline()
            if not payload:
                continue
            progressed = True
            if len(payload) > 1024:
                raise MeshDfuFailure(f"{role} UART line이 너무 깁니다")
            line = payload.decode("ascii", errors="replace").strip()
            if not line.startswith(PROTOCOL + "|"):
                if line:
                    transcript.append(f"{role}-raw: {line}")
                    reject_target_fault(role, line)
                continue
            transcript.append(f"{role}: {line}")
            values = fields(line)
            if line.startswith(f"{PROTOCOL}|FAIL|"):
                raise MeshDfuFailure(
                    f"{role} target FAIL: {values.get('stage', 'unknown')}"
                )
            if values.get("nonce") not in (None, nonce):
                raise MeshDfuFailure(f"{role} session nonce 불일치")
            if values.get("core") not in (None, core_revision):
                raise MeshDfuFailure(f"{role} Core revision 불일치")
            if role in ("target_a", "target_b") and line.startswith(
                f"{PROTOCOL}|BOOT|"
            ):
                if role in boots:
                    raise MeshDfuFailure(f"{role} candidate BOOT 중복")
                validate_boot(role, values, "2.0.0+0", 0, iteration)
                boots[role] = values
                confirm = int(iteration == ITERATION_TARGET and role == "target_a")
                send(
                    port,
                    f"{PROTOCOL}|APPLY|nonce={nonce}|iteration={iteration}"
                    f"|confirm={confirm}|core={core_revision}",
                )
            elif role in ("target_a", "target_b") and line.startswith(
                f"{PROTOCOL}|APPLIED|"
            ):
                if role not in boots or integer(values, "iteration") != iteration:
                    raise MeshDfuFailure(f"{role} APPLIED 순서 불일치")
                expected_confirm = int(
                    iteration == ITERATION_TARGET and role == "target_a"
                )
                if integer(values, "confirmed") != expected_confirm:
                    raise MeshDfuFailure(f"{role} APPLIED confirm 불일치")
                applied[role] = values
            elif role == "distributor" and line.startswith(
                f"{PROTOCOL}|ITERATION|"
            ):
                if integer(values, "iteration") != iteration:
                    raise MeshDfuFailure("Distributor iteration 불일치")
                if integer(values, "targets") != 2:
                    raise MeshDfuFailure("Distributor target 분모 불일치")
                if (
                    values.get("version") != "2.0.0+0"
                    or values.get("signed_sha256") != candidate.sha256
                    or integer(values, "image_size") != candidate.size
                ):
                    raise MeshDfuFailure("Distributor candidate identity 불일치")
                distributor_iteration = values
            elif role == "distributor" and line.startswith(f"{PROTOCOL}|RESULT|"):
                final_result = values
            elif role == "distributor" and line.startswith(f"{PROTOCOL}|END|"):
                final_end = values
        ready = (
            set(boots) == {"target_a", "target_b"}
            and set(applied) == {"target_a", "target_b"}
            and distributor_iteration is not None
        )
        if ready and (
            iteration < ITERATION_TARGET
            or (final_result is not None and final_end is not None)
        ):
            return boots, final_result, final_end, {
                "boots": boots,
                "applied": applied,
                "distributor": distributor_iteration,
            }
        if not progressed:
            time.sleep(0.005)
    raise MeshDfuFailure(f"DFU iteration {iteration} timeout")


def validate_final_result(
    values: dict[str, str], end: dict[str, str], candidate: ImageInput
) -> None:
    """! @brief 5회·10 target·세 negative와 signed image를 판정합니다. """

    expected = {
        "iterations": ITERATION_TARGET,
        "targets": TARGET_RESULT_DENOMINATOR,
        "image_size": candidate.size,
        "wrong_key_rejected": 1,
        "wrong_image_rejected": 1,
        "partial_image_rejected": 1,
    }
    for key, value in expected.items():
        if integer(values, key) != value:
            raise MeshDfuFailure(f"최종 {key} 분모 불일치")
    if values.get("version") != "2.0.0+0" or values.get(
        "signed_sha256"
    ) != candidate.sha256:
        raise MeshDfuFailure("최종 signed candidate identity 불일치")
    if end.get("status") != "pass":
        raise MeshDfuFailure("Distributor END status 불일치")


def reset_and_wait_rollback(
    roles: Sequence[str],
    boards: dict[str, dict[str, Any]],
    ports: dict[str, Any],
    nonce: str,
    core_revision: str,
    transcript: list[str],
    flash_timeout: float,
    deadline: float,
) -> dict[str, dict[str, str]]:
    """! @brief unconfirmed candidate를 V2 reset하고 base rollback을 확인합니다. """

    records: dict[str, dict[str, str]] = {}
    for role in roles:
        access_preserving_reset(boards[role]["probe_sha256"], flash_timeout)
    for role in roles:
        values = read_record(
            role,
            ports[role],
            "BOOT",
            transcript,
            deadline,
            nonce=nonce,
            core_revision=core_revision,
        )
        validate_boot(role, values, "0.0.0+0", 1)
        records[role] = values
    return records


def build_dispatch_cycle_records(
    iterations: list[dict[str, Any]],
    rollbacks: list[dict[str, Any]],
    transcript: list[str],
    candidate: ImageInput,
) -> list[dict[str, Any]]:
    """! @brief 5회 두 Target의 signed update·rollback raw 분모를 10회로 펼칩니다. """

    if [row.get("iteration") for row in iterations] != list(
        range(1, ITERATION_TARGET + 1)
    ):
        raise MeshDfuFailure("DFU iteration sequence mismatch")
    if [row.get("iteration") for row in rollbacks] != list(
        range(1, ITERATION_TARGET + 1)
    ):
        raise MeshDfuFailure("DFU rollback sequence mismatch")
    rollback_roles = {
        row.get("iteration"): set(row.get("roles", [])) for row in rollbacks
    }
    expected_rollbacks = {
        iteration: ({"target_b"} if iteration == ITERATION_TARGET else
                    {"target_a", "target_b"})
        for iteration in range(1, ITERATION_TARGET + 1)
    }
    if rollback_roles != expected_rollbacks:
        raise MeshDfuFailure("DFU rollback role denominator mismatch")
    records: list[dict[str, Any]] = []
    expected_start: int | None = None
    for row in iterations:
        iteration = row["iteration"]
        start = row.get("transcript_line_start")
        end = row.get("transcript_line_end")
        if not isinstance(start, int) or not isinstance(end, int) or \
                end < start or end > len(transcript):
            raise MeshDfuFailure("DFU raw iteration range mismatch")
        if expected_start is not None and start != expected_start:
            raise MeshDfuFailure("DFU raw iteration continuity mismatch")
        raw = ("\n".join(transcript[start - 1:end]) + "\n").encode(
            "ascii", errors="replace"
        )
        if row.get("transcript_sha256") != hashlib.sha256(raw).hexdigest():
            raise MeshDfuFailure("DFU raw iteration digest mismatch")
        expected_start = end + 1
        details = row.get("details", {})
        if set(details.get("boots", {})) != {"target_a", "target_b"} or \
                set(details.get("applied", {})) != {"target_a", "target_b"}:
            raise MeshDfuFailure("DFU target update denominator mismatch")
        distributor = details.get("distributor", {})
        if distributor.get("signed_sha256") != candidate.sha256 or \
                integer(distributor, "targets") != 2:
            raise MeshDfuFailure("DFU signed candidate raw identity mismatch")
        for role in ("target_a", "target_b"):
            confirmed = iteration == ITERATION_TARGET and role == "target_a"
            if not confirmed and role not in rollback_roles.get(iteration, set()):
                raise MeshDfuFailure("DFU rollback denominator mismatch")
            records.append(
                {
                    "cycle": len(records) + 1,
                    "iteration": iteration,
                    "target": role,
                    "status": "PASS",
                    "signed_sha256": candidate.sha256,
                    "final_state": "confirmed" if confirmed else "rolled_back",
                    "transcript_sha256": row["transcript_sha256"],
                    "semantics": {
                        "signed_mesh_dfu": "PASS",
                        "rollback": "PASS",
                        "active_watchdog_condition": "NOT_APPLICABLE",
                        "cleanup": "PASS",
                    },
                }
            )
    if len(records) != TARGET_RESULT_DENOMINATOR:
        raise MeshDfuFailure("DFU dispatch cycle denominator mismatch")
    return records


def save_attempt(prefix: Path, evidence: dict[str, Any], transcript: list[str]) -> None:
    """! @brief raw UID 없는 신규 JSON·transcript를 덮어쓰기 없이 저장합니다. """

    json_path = prefix.with_suffix(".json")
    transcript_path = prefix.with_suffix(".transcript.log")
    if json_path.exists() or transcript_path.exists():
        raise MeshDfuFailure("기존 M32-MDFU-01 attempt를 덮어쓰지 않습니다")
    raw = ("\n".join(transcript) + "\n").encode("ascii", errors="replace")
    if b"uid=" in raw.lower() or b"probe_id=" in raw.lower():
        raise MeshDfuFailure("transcript에 raw probe identity가 있습니다")
    prefix.parent.mkdir(parents=True, exist_ok=True)
    evidence["transcript_sha256"] = hashlib.sha256(raw).hexdigest()
    evidence["observed_utc"] = datetime.now(timezone.utc).isoformat()
    transcript_path.write_bytes(raw)
    json_path.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def image_evidence(image: ImageInput) -> dict[str, Any]:
    """! @brief 경로와 key를 제외한 image byte identity를 반환합니다. """

    return {
        "name": image.path.name,
        "size": image.size,
        "sha256": image.sha256,
        "version": list(image.version) if image.version is not None else None,
    }


def execute(args: argparse.Namespace) -> dict[str, Any]:
    """! @brief exact clean source에서 V2-only 5회 signed DFU를 실행합니다. """

    global _active_attempt

    if args.flash_timeout <= 0 or not 60.0 <= args.result_timeout <= 10800.0:
        raise MeshDfuFailure("flash timeout 또는 result timeout 범위가 잘못됐습니다")
    validate_source_clean(
        MILESTONE,
        APPLICATION_ROOT,
        RUNNER_PATH,
        additional_paths=(
            HIL / "m32_ble_capability_run.py",
            HIL / "m32_ble_capability.py",
            HIL / "m33_sdk_risk_common.py",
            HIL / "v04_protocol.py",
        ),
    )
    core_revision = git_revision(REPOSITORY)
    board_revision = git_revision(BOARD_ROOT)
    validate_board_revision(board_revision)
    signing_key = validate_private_key(args.signing_key)
    builds = {
        role: collect_build(
            getattr(args, f"build_{role}"),
            role,
            core_revision,
            board_revision,
            signing_key,
        )
        for role in ROLES
    }
    builds["candidate"] = collect_build(
        args.build_candidate,
        "candidate",
        core_revision,
        board_revision,
        signing_key,
    )
    validate_build_set(builds)
    watchdog_conditions = {
        role: build_watchdog_classification(build)
        for role, build in builds.items()
    }
    candidate = builds["candidate"].signed_bin

    serial_module, list_ports = import_pyserial()
    boards: dict[str, dict[str, Any]] = {}
    for role in ROLES:
        digest = getattr(args, f"probe_{role}_sha256")
        uid, volume, port = discover(digest, list_ports)
        boards[role] = {
            "uid": uid,
            "probe_sha256": digest,
            "volume": volume,
            "port": port,
        }
    if len({board["uid"] for board in boards.values()}) != len(ROLES):
        raise MeshDfuFailure("세 역할이 서로 다른 probe에 매핑되지 않았습니다")

    nonce = hashlib.sha256(
        f"{time.time_ns()}:{core_revision}:{candidate.sha256}".encode("ascii")
    ).hexdigest()[:32]
    transcript: list[str] = []
    flash_results: dict[str, Any] = {}
    iteration_records: list[dict[str, Any]] = []
    rollback_records: list[dict[str, Any]] = []
    dispatch_cycle_records: list[dict[str, Any]] = []
    capacities: dict[str, dict[str, int]] = {}
    started = time.monotonic()
    deadline = started + args.result_timeout
    prefix = args.output_prefix.resolve()
    native_path = prefix.with_suffix(".json")
    if native_path.exists() or prefix.with_suffix(".transcript.log").exists():
        raise MeshDfuFailure("기존 M32-MDFU-01 attempt를 덮어쓰지 않습니다")
    watchdog_condition_evidence = copy_watchdog_condition_evidence(
        native_path,
        builds,
        watchdog_conditions,
    )
    base_images = {role: builds[role].signed_hex.path for role in ROLES}
    sidecars = reserve_sidecars(native_path, ROLES)
    copy_program_inputs(base_images, sidecars)
    program_images = {role: sidecars[role]["image"] for role in ROLES}
    build_records = {role: builds[role].build_record for role in ROLES}
    readback_records: dict[str, dict[str, Any]] = {}
    programming_receipt = None
    cleanup: dict[str, Any] = {"required": False, "status": "NOT_REQUIRED"}
    close_result = {role: "NOT_OPENED" for role in ROLES}
    public_boards = {
        role: {
            "probe_sha256": board["probe_sha256"],
            "volume": str(board["volume"]),
            "port": board["port"],
        }
        for role, board in boards.items()
    }
    failure_evidence = {
        "schema_version": 1,
        "test_ids": ["M32-MDFU-01:primary"],
        "status": "FAIL",
        "scope": "signed_mesh_dfu_five_iterations_two_targets_and_mcuboot_rollback",
        "source_clean": True,
        "source_revision": core_revision,
        "identity": {"core": core_revision},
        "board_revision": board_revision,
        "boards": public_boards,
        "iterations_completed": 0,
        "iteration_records": iteration_records,
        "dispatch_cycle_records": dispatch_cycle_records,
        "rollback_records": rollback_records,
        "images": {
            "candidate": image_evidence(candidate),
            **{
                f"{role}_base": image_evidence(builds[role].signed_bin)
                for role in ROLES
            },
        },
        "trust_public_key_source_sha256": builds["candidate"].public_key_sha256,
        "flash_backend": "pyocd-cmsis-dap-v2-exact-sector",
        "flash_results": flash_results,
        "build_records": build_records,
        "watchdog_condition_evidence": watchdog_condition_evidence,
        "cleanup": cleanup,
        "serial_close": close_result,
        "exact_programming": {},
        "secondary_slot": {
            "offset": SLOT1_OFFSET,
            "size": SLOT1_SIZE,
            "erase_end_exclusive": SLOT1_END,
        },
        "mass_erase_or_recover": False,
        "raw_probe_identity_persisted": False,
        "sdk_risk_regression": {
            "mcuboot_active_watchdog": {
                "status": watchdog_condition_evidence["status"],
                "condition": watchdog_condition_evidence["condition"],
                "builds": watchdog_conditions,
                "not_run_is_pass": False,
            },
        },
    }
    _active_attempt = {
        "evidence": failure_evidence,
        "transcript": transcript,
        "started": started,
        "prefix": prefix,
    }
    ports: dict[str, Any] = {}
    cleanup_state = {"radio_started": False, "serial_cleanup_owned": False}

    with ProbeLocks([boards[role]["uid"] for role in ROLES]), pre_serial_cleanup_guard(
        cleanup_state,
        ports,
        nonce,
        core_revision,
        transcript,
        failure_evidence,
    ):
        for role in ROLES:
            board = boards[role]
            board["registers"] = collect_register_identity_sha256(
                board["probe_sha256"], board["volume"]
            )
            public_boards[role]["registers"] = board["registers"]
            erase_secondary_slot(board["probe_sha256"], args.flash_timeout)
            flash_results[f"{role}_boot"] = flash_image_pyocd_sha256(
                f"{role}-bootloader",
                board["probe_sha256"],
                builds[role].boot_hex.path,
                args.flash_timeout,
                defer_reset=True,
            )
            flash_results[f"{role}_base"] = flash_image_pyocd_sha256(
                f"{role}-signed-base",
                board["probe_sha256"],
                program_images[role],
                args.flash_timeout,
                defer_reset=True,
            )
            flash_results[f"{role}_settings_clear"] = clear_nrf54l_rram_pyocd_sha256(
                role,
                board["probe_sha256"],
                SETTINGS_STORAGE_START,
                SETTINGS_STORAGE_SIZE,
                args.flash_timeout,
            )
        flash_results["distributor_candidate_bytes"] = flash_secondary_candidate(
            boards["distributor"]["probe_sha256"], candidate, args.flash_timeout
        )
        readback_records, programming_receipt = readback_programmed_images(
            {role: boards[role]["uid"] for role in ROLES},
            {role: boards[role]["probe_sha256"] for role in ROLES},
            program_images,
            sidecars,
        )
        cleanup_state["radio_started"] = True
        for role in ROLES:
            access_preserving_reset(
                boards[role]["probe_sha256"], args.flash_timeout
            )
        time.sleep(2.0)

        cleanup_state["serial_cleanup_owned"] = True
        try:
            for role in ROLES:
                ports[role] = serial_module.Serial(
                    boards[role]["port"], 115200, timeout=0.05, write_timeout=2.0
                )
            for port in ports.values():
                port.reset_input_buffer()
            for role in ROLES:
                send(ports[role], f"{PROTOCOL}|PROBE")
                ready = read_record(role, ports[role], "READY", transcript, deadline)
                if (
                    ready.get("version") != "0.0.0+0"
                    or integer(ready, "confirmed") != 1
                    or ready.get("core") != core_revision
                ):
                    raise MeshDfuFailure(f"{role} initial READY 불일치")
                capacities[role] = validate_capacity(ready)

            clear = f"{PROTOCOL}|CLEAR|nonce={nonce}|core={core_revision}"
            for role in ("target_a", "target_b", "distributor"):
                send(ports[role], clear)
                read_record(
                    role,
                    ports[role],
                    "CLEARED",
                    transcript,
                    deadline,
                    nonce=nonce,
                    core_revision=core_revision,
                )
            start = f"{PROTOCOL}|START|nonce={nonce}|core={core_revision}"
            for role in ("target_a", "target_b"):
                send(ports[role], start)
                read_record(
                    role,
                    ports[role],
                    "BEGIN",
                    transcript,
                    deadline,
                    nonce=nonce,
                    core_revision=core_revision,
                )
            send(ports["distributor"], start)
            read_record(
                "distributor",
                ports["distributor"],
                "BEGIN",
                transcript,
                deadline,
                nonce=nonce,
                core_revision=core_revision,
            )

            final_result: dict[str, str] | None = None
            final_end: dict[str, str] | None = None
            for iteration in range(1, ITERATION_TARGET + 1):
                iteration_start = len(transcript)
                boots, result, end, details = collect_iteration(
                    ports,
                    iteration,
                    nonce,
                    core_revision,
                    candidate,
                    transcript,
                    deadline,
                )
                iteration_records.append(
                    {
                        "iteration": iteration,
                        "target_a_confirmed": int(iteration == ITERATION_TARGET),
                        "target_b_confirmed": 0,
                        "candidate_boots": len(boots),
                        "details": details,
                        "transcript_line_start": iteration_start + 1,
                    }
                )
                failure_evidence["iterations_completed"] = len(iteration_records)
                if iteration < ITERATION_TARGET:
                    rollback = reset_and_wait_rollback(
                        ("target_a", "target_b"),
                        boards,
                        ports,
                        nonce,
                        core_revision,
                        transcript,
                        args.flash_timeout,
                        deadline,
                    )
                    rollback_records.append(
                        {"iteration": iteration, "roles": sorted(rollback)}
                    )
                    next_iteration = iteration + 1
                    send(
                        ports["distributor"],
                        f"{PROTOCOL}|NEXT|nonce={nonce}|iteration={next_iteration}"
                        f"|core={core_revision}",
                    )
                    nexted = read_record(
                        "distributor",
                        ports["distributor"],
                        "NEXTED",
                        transcript,
                        deadline,
                        nonce=nonce,
                        core_revision=core_revision,
                    )
                    if integer(nexted, "iteration") != next_iteration:
                        raise MeshDfuFailure("NEXTED iteration 불일치")
                    iteration_records[-1]["transcript_line_end"] = len(transcript)
                    iteration_raw = (
                        "\n".join(transcript[iteration_start:]) + "\n"
                    ).encode("ascii", errors="replace")
                    iteration_records[-1]["transcript_sha256"] = hashlib.sha256(
                        iteration_raw
                    ).hexdigest()
                else:
                    final_result = result
                    final_end = end

            if final_result is None or final_end is None:
                raise MeshDfuFailure("최종 RESULT 또는 END가 없습니다")
            validate_final_result(final_result, final_end, candidate)
            send(ports["target_a"], f"{PROTOCOL}|PROBE")
            final_a = read_record(
                "target_a", ports["target_a"], "READY", transcript, deadline
            )
            if (
                final_a.get("version") != "2.0.0+0"
                or integer(final_a, "confirmed") != 1
                or final_a.get("core") != core_revision
            ):
                raise MeshDfuFailure("target_a final confirmed image 불일치")
            final_b = reset_and_wait_rollback(
                ("target_b",),
                boards,
                ports,
                nonce,
                core_revision,
                transcript,
                args.flash_timeout,
                deadline,
            )
            rollback_records.append(
                {"iteration": ITERATION_TARGET, "roles": sorted(final_b)}
            )
            iteration_records[-1]["transcript_line_end"] = len(transcript)
            final_iteration_raw = (
                "\n".join(
                    transcript[iteration_records[-1]["transcript_line_start"] - 1:]
                )
                + "\n"
            ).encode("ascii", errors="replace")
            iteration_records[-1]["transcript_sha256"] = hashlib.sha256(
                final_iteration_raw
            ).hexdigest()

        finally:
            try:
                cleanup = cleanup_ports(
                    ports,
                    nonce,
                    core_revision,
                    transcript,
                    required=True,
                )
            except Exception as error:
                cleanup = {
                    "required": True,
                    "status": "FAIL",
                    "errors": [
                        f"cleanup exception: {type(error).__name__}: {error}"
                    ],
                }
            finally:
                close_result = close_ports(ports)
            failure_evidence["cleanup"] = cleanup
            failure_evidence["serial_close"] = close_result
        if cleanup["status"] != "PASS" or any(
                value.startswith("FAIL:") for value in close_result.values()):
            raise MeshDfuFailure("resource cleanup was not proven")

    dispatch_cycle_records.extend(
        build_dispatch_cycle_records(
            iteration_records,
            rollback_records,
            transcript,
            candidate,
        )
    )

    for build in builds.values():
        for image in (build.boot_hex, build.signed_hex, build.signed_bin, build.raw_bin):
            validate_image_unchanged(image.path, image.size, image.sha256)

    require_exact_clean_source(REPOSITORY, core_revision)
    validate_programming_receipt(programming_receipt, ROLES, readback_records)
    exact_program = exact_program_evidence(
        ROLES,
        {role: boards[role]["probe_sha256"] for role in ROLES},
        sidecars,
        {
            role: {
                "mode": flash_results[f"{role}_base"][0],
                "bytes": str(flash_results[f"{role}_base"][1]),
            }
            for role in ROLES
        },
        build_records,
        readback_records,
    )
    attestation = dispatch_attestation(
        "m32_mesh_dfu",
        core_revision,
        TARGET_RESULT_DENOMINATOR,
        (
            "signed_mesh_dfu",
            "rollback",
            "active_watchdog_condition",
            "cleanup",
        ),
        ROLES,
        exact_program,
        semantic_status={
            "signed_mesh_dfu": "PASS",
            "rollback": "PASS",
            "active_watchdog_condition": "NOT_APPLICABLE",
            "cleanup": "PASS",
        },
    )
    failure_evidence["exact_programming"] = exact_program

    evidence = {
        "schema_version": 1,
        "test_ids": ["M32-MDFU-01:primary"],
        "status": "PASS",
        "scope": "signed_mesh_dfu_five_iterations_two_targets_and_mcuboot_rollback",
        "source_clean": True,
        "source_revision": core_revision,
        "identity": {"core": core_revision},
        "board_revision": board_revision,
        "nonce": nonce,
        "boards": public_boards,
        "iterations": ITERATION_TARGET,
        "cycles": TARGET_RESULT_DENOMINATOR,
        "firmware_distribution_targets": TARGET_RESULT_DENOMINATOR,
        "capacities": capacities,
        "negative": {
            "wrong_image": "rejected",
            "wrong_key": "rejected",
            "rollback": "observed",
            "partial_image": "rejected",
        },
        "rollback_count": sum(len(item["roles"]) for item in rollback_records),
        "iteration_records": iteration_records,
        "dispatch_cycle_records": dispatch_cycle_records,
        "rollback_records": rollback_records,
        "images": {
            "candidate": image_evidence(candidate),
            **{
                f"{role}_base": image_evidence(builds[role].signed_bin)
                for role in ROLES
            },
        },
        "trust_public_key_source_sha256": builds["candidate"].public_key_sha256,
        "flash_backend": "pyocd-cmsis-dap-v2-exact-sector",
        "flash_results": flash_results,
        "build_records": build_records,
        "watchdog_condition_evidence": watchdog_condition_evidence,
        "cleanup": cleanup,
        "serial_close": close_result,
        "exact_programming": exact_program,
        "secondary_slot": {
            "offset": SLOT1_OFFSET,
            "size": SLOT1_SIZE,
            "erase_end_exclusive": SLOT1_END,
        },
        "mass_erase_or_recover": False,
        "sdk_risk_regression": {
            "mcuboot_active_watchdog": {
                "status": watchdog_condition_evidence["status"],
                "condition": watchdog_condition_evidence["condition"],
                "builds": watchdog_conditions,
                "not_run_is_pass": False,
            },
        },
        "duration_seconds": round(time.monotonic() - started, 3),
        "m33_dispatch_attestation": attestation,
    }
    save_attempt(prefix, evidence, transcript)
    _active_attempt = None
    return evidence


def main(arguments: Sequence[str] | None = None) -> int:
    """! @brief M32-MDFU-01을 실행하고 PASS 증적을 저장합니다. """

    args = parse_arguments(arguments)
    try:
        evidence = execute(args)
    except Exception as error:
        message = re.sub(r"(?i)\b[0-9a-f]{16,64}\b", "<redacted-identity>", str(error))
        if _active_attempt is not None:
            failure_evidence = _active_attempt["evidence"]
            failure_evidence["failure"] = f"{type(error).__name__}: {message[:500]}"
            failure_evidence["duration_seconds"] = round(
                time.monotonic() - _active_attempt["started"], 3
            )
            try:
                save_attempt(
                    _active_attempt["prefix"],
                    failure_evidence,
                    _active_attempt["transcript"],
                )
            except Exception as save_error:
                save_message = re.sub(
                    r"(?i)\b[0-9a-f]{16,64}\b",
                    "<redacted-identity>",
                    str(save_error),
                )
                print(
                    f"M32_MDFU_EVIDENCE_FAIL: {type(save_error).__name__}: "
                    f"{save_message[:500]}",
                    file=sys.stderr,
                )
        print(
            f"M32_MDFU_HIL_FAIL: {type(error).__name__}: {message[:500]}",
            file=sys.stderr,
        )
        return 1
    print(
        f"M32_MDFU_HIL_STATUS={evidence['status']};"
        f"ITERATIONS={evidence['iterations']};"
        f"TARGETS={evidence['firmware_distribution_targets']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
