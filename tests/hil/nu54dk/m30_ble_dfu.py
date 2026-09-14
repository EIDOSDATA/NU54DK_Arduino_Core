#!/usr/bin/env python3
"""! @brief 두 NU54DK로 인증 BLE DFU·부정 image·rollback HIL을 실행합니다. """

from __future__ import annotations

import argparse
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile
import time
from typing import Any, Sequence


HIL_DIRECTORY = Path(__file__).resolve().parent
if str(HIL_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(HIL_DIRECTORY))

from ble_pair_hil_common import (  # noqa: E402
    BOARD_ROOT,
    BlePairHilFailure,
    DEFAULT_BAUD_RATE,
    REPOSITORY,
    RoleEndpoint,
    discover_endpoint,
    file_sha256,
    flash_image_pyocd,
    git_revision,
    transcript_record,
    validate_board_revision,
    validate_build_record,
    validate_image_unchanged,
    validate_pair_identity,
    validate_source_clean,
)
from m30_mcuboot import (  # noqa: E402
    M30BootFailure,
    erase_secondary_slot,
    imgtool_environment,
    validate_private_key,
)
from m6_serial_echo import import_pyserial  # noqa: E402


MILESTONE = "M30"
APPLICATION_ROOT = REPOSITORY / "tests/zephyr/m30_ble_dfu_hil"
DFU_LIBRARY = REPOSITORY / "libraries/NUCODE_BLE_DFU"
RUNNER_PATH = Path(__file__).resolve()
BOOT_RUNNER_PATH = HIL_DIRECTORY / "m30_mcuboot.py"
BOARD_DIRECTORY = "nrf54l15dk_nrf54l15_cpuapp_nu54dk"
TOOLCHAIN_DIRECTORY = "zephyr_gnu"
SCENARIO = "nucode.m30.dfu.peripheral"
APPLICATION_DOMAIN = "m30_ble_dfu_hil"
BOOT_DOMAIN = "mcuboot"
MCUBOOT_MAGIC = 0x96F3B83D
MCUBOOT_HASH_TLV = 0x10
MCUBOOT_TLV_INFO_MAGIC = 0x6907
MCUBOOT_PROTECTED_TLV_INFO_MAGIC = 0x6908
SLOT_SIZE = 729088
PRIMARY_FLASH_AREA_ID = 1
PROTOCOL = b"M30DFU|1|"
MAX_SMP_PACKET = 244
MAX_TRANSCRIPT_BYTES = 8 * 1024 * 1024
POSITIVE_UPDATES = 10
NEGATIVE_ATTEMPTS = 20
BASE_VERSION = (0, 0, 0, 0)
FINAL_VERSION = (10, 0, 0, 0)
UNCONFIRMED_VERSION = (11, 0, 0, 0)


class M30DfuFailure(RuntimeError):
    """! @brief M30-DFU build·transport·target 검증 실패입니다. """


@dataclass(frozen=True)
class ImageArtifact:
    """! @brief 변경 감시 가능한 MCUboot image identity입니다. """

    path: Path
    size: int
    sha256: str
    version: tuple[int, int, int, int]
    image_hash: bytes


@dataclass(frozen=True)
class PeripheralBuild:
    """! @brief 한 peripheral sysbuild의 bootloader와 application 입력입니다. """

    root: Path
    boot_hex: Path
    signed_hex: Path
    raw_bin: Path
    auto_confirm: int
    record: dict[str, str]
    public_key_sha256: str


@dataclass(frozen=True)
class CentralBuild:
    """! @brief Central relay image와 exact build record입니다. """

    root: Path
    image: Path
    record: dict[str, str]


@dataclass(frozen=True)
class BootRecord:
    """! @brief peripheral BOOT protocol에서 읽은 실행 image 상태입니다. """

    active_area_id: int
    confirmed: int
    auto_confirm: int
    version: tuple[int, int, int, int]


@dataclass(frozen=True)
class SmpResult:
    """! @brief 검증을 마친 SMP response payload와 오류입니다. """

    payload: dict[Any, Any]
    error_group: int | None
    error_code: int


def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    """! @brief exact 두 build·두 endpoint·두 phase 상한을 선언합니다. """

    parser = argparse.ArgumentParser(
        description="M30 인증 BLE DFU 정상·negative·rollback을 두 NU54DK에서 검증합니다."
    )
    parser.add_argument("--peripheral-build-outdir", required=True)
    parser.add_argument("--unconfirmed-build-outdir", required=True)
    parser.add_argument("--central-build-outdir", required=True)
    parser.add_argument("--peripheral-board-id", required=True)
    parser.add_argument("--central-board-id", required=True)
    parser.add_argument("--peripheral-volume")
    parser.add_argument("--central-volume")
    parser.add_argument("--peripheral-port", default="auto")
    parser.add_argument("--central-port", default="auto")
    parser.add_argument("--baud", type=int, default=DEFAULT_BAUD_RATE)
    parser.add_argument("--flash-timeout", type=float, default=120.0)
    parser.add_argument("--phase-timeout", type=float, default=1200.0)
    parser.add_argument("--trust-signing-key", required=True)
    parser.add_argument("--wrong-signing-key", required=True)
    parser.add_argument("--imgtool-python", required=True)
    parser.add_argument("--imgtool", required=True)
    parser.add_argument("--expected-core-revision")
    parser.add_argument("--nonce")
    parser.add_argument("--evidence")
    parser.add_argument("--overwrite-evidence", action="store_true")
    parser.add_argument("--discover-only", action="store_true")
    return parser.parse_args(arguments)


def cbor_length(major: int, value: int) -> bytes:
    """! @brief canonical CBOR major type과 non-negative 길이를 encode합니다. """

    if not 0 <= major <= 7 or value < 0:
        raise M30DfuFailure("CBOR major type 또는 길이가 잘못됐습니다.")
    prefix = major << 5
    if value < 24:
        return bytes((prefix | value,))
    if value <= 0xFF:
        return bytes((prefix | 24, value))
    if value <= 0xFFFF:
        return bytes((prefix | 25,)) + struct.pack(">H", value)
    if value <= 0xFFFFFFFF:
        return bytes((prefix | 26,)) + struct.pack(">I", value)
    if value <= 0xFFFFFFFFFFFFFFFF:
        return bytes((prefix | 27,)) + struct.pack(">Q", value)
    raise M30DfuFailure("CBOR 정수가 64-bit 범위를 넘습니다.")


def cbor_encode(value: Any) -> bytes:
    """! @brief SMP에 필요한 bounded canonical CBOR subset을 encode합니다. """

    if value is False:
        return b"\xf4"
    if value is True:
        return b"\xf5"
    if value is None:
        return b"\xf6"
    if isinstance(value, int):
        if value >= 0:
            return cbor_length(0, value)
        return cbor_length(1, -1 - value)
    if isinstance(value, bytes):
        return cbor_length(2, len(value)) + value
    if isinstance(value, str):
        encoded = value.encode("utf-8")
        return cbor_length(3, len(encoded)) + encoded
    if isinstance(value, (list, tuple)):
        return cbor_length(4, len(value)) + b"".join(cbor_encode(item) for item in value)
    if isinstance(value, dict):
        result = bytearray(cbor_length(5, len(value)))
        for key, item in value.items():
            result.extend(cbor_encode(key))
            result.extend(cbor_encode(item))
        return bytes(result)
    raise M30DfuFailure(f"지원하지 않는 CBOR type입니다: {type(value).__name__}")


class CborDecoder:
    """! @brief depth·길이·중복 key를 제한하는 CBOR decoder입니다. """

    def __init__(self, data: bytes) -> None:
        self.data = data
        self.offset = 0

    def take(self, length: int) -> bytes:
        """! @brief 입력 범위를 넘지 않는 exact byte를 소비합니다. """

        if length < 0 or self.offset + length > len(self.data):
            raise M30DfuFailure("CBOR payload가 중간에서 끝났습니다.")
        result = self.data[self.offset : self.offset + length]
        self.offset += length
        return result

    def argument(self, additional: int) -> int | None:
        """! @brief additional information을 definite 길이 또는 indefinite로 변환합니다. """

        if additional < 24:
            return additional
        sizes = {24: 1, 25: 2, 26: 4, 27: 8}
        if additional in sizes:
            return int.from_bytes(self.take(sizes[additional]), "big")
        if additional == 31:
            return None
        raise M30DfuFailure("CBOR reserved additional information입니다.")

    def decode(self, depth: int = 0) -> Any:
        """! @brief 최대 12단계의 definite·indefinite CBOR 값을 decode합니다. """

        if depth > 12:
            raise M30DfuFailure("CBOR nesting이 허용 깊이를 넘습니다.")
        initial = self.take(1)[0]
        if initial == 0xFF:
            raise M30DfuFailure("예상 밖 CBOR break입니다.")
        major = initial >> 5
        additional = initial & 0x1F
        argument = self.argument(additional)
        if major == 0:
            if argument is None:
                raise M30DfuFailure("indefinite 정수는 허용하지 않습니다.")
            return argument
        if major == 1:
            if argument is None:
                raise M30DfuFailure("indefinite 음수는 허용하지 않습니다.")
            return -1 - argument
        if major in (2, 3):
            if argument is None:
                pieces: list[bytes] = []
                while self.offset < len(self.data) and self.data[self.offset] != 0xFF:
                    item = self.decode(depth + 1)
                    expected = bytes if major == 2 else str
                    if not isinstance(item, expected):
                        raise M30DfuFailure("indefinite CBOR 문자열 chunk type이 다릅니다.")
                    pieces.append(item if isinstance(item, bytes) else item.encode("utf-8"))
                self.take(1)
                raw = b"".join(pieces)
            else:
                raw = self.take(argument)
            if major == 2:
                return raw
            try:
                return raw.decode("utf-8")
            except UnicodeDecodeError as error:
                raise M30DfuFailure("CBOR text가 UTF-8이 아닙니다.") from error
        if major == 4:
            items = []
            if argument is None:
                while self.offset < len(self.data) and self.data[self.offset] != 0xFF:
                    items.append(self.decode(depth + 1))
                self.take(1)
            else:
                for _index in range(argument):
                    items.append(self.decode(depth + 1))
            return items
        if major == 5:
            result: dict[Any, Any] = {}
            remaining = argument
            while remaining is None or remaining > 0:
                if remaining is None and self.offset < len(self.data) and self.data[self.offset] == 0xFF:
                    self.take(1)
                    break
                key = self.decode(depth + 1)
                if not isinstance(key, (str, int)) or key in result:
                    raise M30DfuFailure("CBOR map key가 잘못됐거나 중복됐습니다.")
                result[key] = self.decode(depth + 1)
                if remaining is not None:
                    remaining -= 1
            return result
        if major == 7 and argument in (20, 21, 22):
            return {20: False, 21: True, 22: None}[argument]
        raise M30DfuFailure(f"지원하지 않는 CBOR major type입니다: {major}")


def cbor_decode(data: bytes) -> Any:
    """! @brief CBOR 한 값과 trailing byte 부재를 검증합니다. """

    decoder = CborDecoder(data)
    result = decoder.decode()
    if decoder.offset != len(data):
        raise M30DfuFailure("CBOR payload 뒤에 trailing byte가 있습니다.")
    return result


def parse_mcuboot_image(path: Path) -> ImageArtifact:
    """! @brief MCUboot v1 header·SHA-256 TLV와 byte identity를 읽습니다. """

    path = path.resolve()
    try:
        data = path.read_bytes()
    except OSError as error:
        raise M30DfuFailure(f"image를 읽지 못했습니다: {path}: {error}") from error
    if len(data) < 32 or len(data) > SLOT_SIZE:
        raise M30DfuFailure(f"image 크기가 잘못됐습니다: {path.name}: {len(data)}")
    magic, _load, header_size, protected_size, image_size, _flags = struct.unpack_from(
        "<IIHHII", data, 0
    )
    if magic != MCUBOOT_MAGIC or header_size != 0x800:
        raise M30DfuFailure(f"MCUboot v1 header가 아닙니다: {path.name}")
    version = struct.unpack_from("<BBHI", data, 20)
    cursor = header_size + image_size
    if cursor + protected_size > len(data):
        raise M30DfuFailure(f"protected TLV 범위가 image 밖입니다: {path.name}")
    if protected_size:
        protected_magic, protected_total = struct.unpack_from("<HH", data, cursor)
        if protected_magic != MCUBOOT_PROTECTED_TLV_INFO_MAGIC or protected_total != protected_size:
            raise M30DfuFailure(f"protected TLV header가 잘못됐습니다: {path.name}")
        cursor += protected_size
    if cursor + 4 > len(data):
        raise M30DfuFailure(f"일반 TLV header가 없습니다: {path.name}")
    tlv_magic, tlv_total = struct.unpack_from("<HH", data, cursor)
    if tlv_magic != MCUBOOT_TLV_INFO_MAGIC or tlv_total < 4 or cursor + tlv_total > len(data):
        raise M30DfuFailure(f"일반 TLV 범위가 잘못됐습니다: {path.name}")
    end = cursor + tlv_total
    cursor += 4
    hashes: list[bytes] = []
    while cursor < end:
        if cursor + 4 > end:
            raise M30DfuFailure(f"TLV entry header가 잘렸습니다: {path.name}")
        tlv_type, _pad, length = struct.unpack_from("<BBH", data, cursor)
        cursor += 4
        if cursor + length > end:
            raise M30DfuFailure(f"TLV entry가 범위를 넘습니다: {path.name}")
        if tlv_type == MCUBOOT_HASH_TLV:
            hashes.append(data[cursor : cursor + length])
        cursor += length
    if len(hashes) != 1 or len(hashes[0]) != 32:
        raise M30DfuFailure(f"SHA-256 TLV가 정확히 하나가 아닙니다: {path.name}")
    return ImageArtifact(path, len(data), hashlib.sha256(data).hexdigest(), version, hashes[0])


def resolve_sysbuild_root(argument: str) -> Path:
    """! @brief direct 또는 Twister peripheral sysbuild root를 반환합니다. """

    outdir = Path(argument).resolve()
    candidates = (
        outdir,
        outdir / BOARD_DIRECTORY / TOOLCHAIN_DIRECTORY / SCENARIO,
    )
    matches = [candidate for candidate in candidates if (candidate / "domains.yaml").is_file()]
    if len(matches) != 1:
        raise M30DfuFailure("peripheral build에서 exact domains.yaml 하나를 찾지 못했습니다.")
    return matches[0]


def require_text_tokens(path: Path, tokens: Sequence[str]) -> str:
    """! @brief 생성 파일에 필수 보안·역할 token이 있는지 확인합니다. """

    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise M30DfuFailure(f"생성 파일을 읽지 못했습니다: {path}: {error}") from error
    for token in tokens:
        if token not in text:
            raise M30DfuFailure(f"생성 token이 없습니다: {path.name}: {token}")
    return text


def validate_domains(root: Path) -> None:
    """! @brief sysbuild domain과 flash 순서를 MCUboot+application으로 고정합니다. """

    text = require_text_tokens(root / "domains.yaml", ("default: m30_ble_dfu_hil", "flash_order:"))
    entries = re.findall(r"(?m)^  - name: ([a-z0-9_]+)\r?\n    build_dir: (.+)$", text)
    if [name for name, _directory in entries] != [APPLICATION_DOMAIN, BOOT_DOMAIN]:
        raise M30DfuFailure(f"sysbuild domain 구성이 다릅니다: {entries!r}")
    flash_match = re.search(r"(?ms)^flash_order:\r?\n((?:  - [a-z0-9_]+\r?\n?)+)", text)
    if flash_match is None or re.findall(r"(?m)^  - ([a-z0-9_]+)$", flash_match.group(1)) != [
        BOOT_DOMAIN,
        APPLICATION_DOMAIN,
    ]:
        raise M30DfuFailure("sysbuild flash_order가 bootloader→application이 아닙니다.")


def collect_peripheral_build(
    argument: str, core_revision: str, trust_key: Path, auto_confirm: int
) -> PeripheralBuild:
    """! @brief exact sysbuild·P-256 key·authenticated SMP·역할 define을 검증합니다. """

    root = resolve_sysbuild_root(argument)
    validate_domains(root)
    app = root / APPLICATION_DOMAIN
    boot = root / BOOT_DOMAIN
    require_text_tokens(
        app / "zephyr/.config",
        (
            "CONFIG_BOOTLOADER_MCUBOOT=y",
            "CONFIG_IMG_ENABLE_IMAGE_CHECK=y",
            "CONFIG_MCUMGR_TRANSPORT_BT=y",
            "CONFIG_MCUMGR_TRANSPORT_BT_PERM_RW_AUTHEN=y",
            "CONFIG_MCUMGR_TRANSPORT_BT_REASSEMBLY=y",
            "CONFIG_BT_SMP_SC_PAIR_ONLY=y",
            "CONFIG_BT_SMP_MIN_ENC_KEY_SIZE=16",
        ),
    )
    boot_config = require_text_tokens(
        boot / "zephyr/.config",
        (
            "CONFIG_BOOT_SIGNATURE_TYPE_ECDSA_P256=y",
            "CONFIG_MCUBOOT_DOWNGRADE_PREVENTION=y",
            "CONFIG_MCUBOOT_DOWNGRADE_PREVENTION_SECURITY_COUNTER=y",
        ),
    )
    key_match = re.search(r'^CONFIG_BOOT_SIGNATURE_KEY_FILE="(.+)"$', boot_config, re.M)
    if key_match is None or Path(key_match.group(1)).resolve() != trust_key:
        raise M30DfuFailure("MCUboot public-key build identity가 trust key와 다릅니다.")
    require_text_tokens(
        app / "build.ninja",
        (
            f'M30_DFU_CORE_REVISION=\\"{core_revision}\\"',
            "NUCODE_M30_DFU_PERIPHERAL=1",
            f"NUCODE_M30_DFU_AUTO_CONFIRM={auto_confirm}",
        ),
    )
    raw = app / "zephyr/zephyr.bin"
    if not raw.is_file() or core_revision.encode("ascii") not in raw.read_bytes():
        raise M30DfuFailure("peripheral raw image에 exact Core revision이 없습니다.")
    signed_hex = app / "zephyr/zephyr.signed.hex"
    record = validate_build_record(signed_hex, core_revision, git_revision(BOARD_ROOT), APPLICATION_ROOT)
    public_key = boot / "zephyr/autogen-pubkey.c"
    if not public_key.is_file():
        raise M30DfuFailure("MCUboot 생성 public key source가 없습니다.")
    return PeripheralBuild(
        root,
        boot / "zephyr/zephyr.hex",
        signed_hex,
        raw,
        auto_confirm,
        record,
        file_sha256(public_key),
    )


def collect_central_build(argument: str, core_revision: str) -> CentralBuild:
    """! @brief loaderless Central relay와 L4·MTU role define을 검증합니다. """

    root = Path(argument).resolve()
    if (root / "domains.yaml").exists():
        raise M30DfuFailure("Central build는 --no-sysbuild loaderless image여야 합니다.")
    require_text_tokens(
        root / "zephyr/.config",
        (
            "# CONFIG_BOOTLOADER_MCUBOOT is not set",
            "CONFIG_BT_SMP_SC_PAIR_ONLY=y",
            "CONFIG_BT_SMP_MIN_ENC_KEY_SIZE=16",
            "CONFIG_BT_L2CAP_TX_MTU=247",
        ),
    )
    ninja = require_text_tokens(
        root / "build.ninja",
        (f'M30_DFU_CORE_REVISION=\\"{core_revision}\\"',),
    )
    if "NUCODE_M30_DFU_PERIPHERAL=1" in ninja:
        raise M30DfuFailure("Central build에 peripheral 역할 define이 있습니다.")
    image = root / "zephyr/zephyr.hex"
    record = validate_build_record(image, core_revision, git_revision(BOARD_ROOT), APPLICATION_ROOT)
    return CentralBuild(root, image, record)


def run_imgtool(
    raw: Path,
    output: Path,
    version: tuple[int, int, int, int],
    security_counter: int,
    imgtool_python: Path,
    imgtool: Path,
    key: Path | None,
) -> ImageArtifact:
    """! @brief 저장소 밖 key로 고정 layout MCUboot candidate를 생성합니다. """

    for label, path in (("imgtool Python", imgtool_python), ("imgtool", imgtool), ("raw image", raw)):
        if not path.is_file():
            raise M30DfuFailure(f"{label}가 없습니다: {path}")
    version_text = f"{version[0]}.{version[1]}.{version[2]}+{version[3]}"
    command = [
        str(imgtool_python),
        str(imgtool),
        "sign",
        "--version",
        version_text,
        "--slot-size",
        hex(SLOT_SIZE),
        "--header-size",
        "0x800",
        "--align",
        "16",
        "--rom-fixed",
        "0x10000",
        "--security-counter",
        str(security_counter),
    ]
    if key is not None:
        command.extend(("--key", str(key)))
    command.extend((str(raw), str(output)))
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            timeout=90.0,
            check=False,
            env=imgtool_environment(imgtool_python),
        )
    except (OSError, subprocess.TimeoutExpired, M30BootFailure) as error:
        raise M30DfuFailure(f"imgtool candidate 생성 실패: {error}") from error
    if result.returncode != 0:
        message = (result.stdout + result.stderr).decode("utf-8", errors="backslashreplace")
        raise M30DfuFailure(f"imgtool candidate 생성 실패: {message}")
    artifact = parse_mcuboot_image(output)
    if artifact.version != version:
        raise M30DfuFailure(f"candidate version이 다릅니다: {artifact.version}, expected={version}")
    return artifact


def mutate_corrupt(source: ImageArtifact, output: Path) -> ImageArtifact:
    """! @brief header/TLV는 보존하고 payload 한 byte만 손상합니다. """

    data = bytearray(source.path.read_bytes())
    header_size = struct.unpack_from("<H", data, 8)[0]
    image_size = struct.unpack_from("<I", data, 12)[0]
    if image_size < 128:
        raise M30DfuFailure("손상시킬 image payload가 너무 작습니다.")
    data[header_size + 64] ^= 0x01
    output.write_bytes(data)
    artifact = parse_mcuboot_image(output)
    if artifact.image_hash != source.image_hash or artifact.sha256 == source.sha256:
        raise M30DfuFailure("corrupt candidate가 embedded hash만 보존하지 못했습니다.")
    return artifact


def mutate_truncated(source: ImageArtifact, output: Path) -> ImageArtifact:
    """! @brief signed TLV tail 16 byte를 제거한 candidate를 생성합니다. """

    data = source.path.read_bytes()
    if len(data) <= 16:
        raise M30DfuFailure("truncated candidate 원본이 너무 작습니다.")
    output.write_bytes(data[:-16])
    path = output.resolve()
    return ImageArtifact(path, path.stat().st_size, file_sha256(path), source.version, source.image_hash)


def endpoint_evidence(endpoint: RoleEndpoint) -> dict[str, str]:
    """! @brief raw probe UID 없이 물리 endpoint identity를 기록합니다. """

    match = re.match(r"^([A-Za-z]):(?:[\\/]|$)", str(endpoint.volume.root))
    if match is None:
        raise M30DfuFailure("DAPLink volume이 Windows drive root가 아닙니다.")
    return {
        "board_id_sha256": hashlib.sha256(endpoint.board_id.encode("ascii")).hexdigest(),
        "volume": f"{match.group(1).upper()}:",
        "port": endpoint.port_name,
    }


def artifact_evidence(artifact: ImageArtifact) -> dict[str, Any]:
    """! @brief private key 경로 없이 candidate byte identity를 기록합니다. """

    return {
        "name": artifact.path.name,
        "size": artifact.size,
        "sha256": artifact.sha256,
        "image_hash": artifact.image_hash.hex(),
        "version": list(artifact.version),
    }


def output_paths(argument: str | None, overwrite: bool) -> tuple[Path, Path, Path]:
    """! @brief 신규 JSON과 role별 raw transcript 경로를 준비합니다. """

    if not argument:
        raise M30DfuFailure("실제 실행에는 --evidence가 필요합니다.")
    evidence = Path(argument).resolve()
    if evidence.suffix.casefold() != ".json":
        raise M30DfuFailure("--evidence는 .json 파일이어야 합니다.")
    peripheral = evidence.with_name(f"{evidence.stem}.peripheral.transcript.log")
    central = evidence.with_name(f"{evidence.stem}.central.transcript.log")
    paths = (evidence, peripheral, central)
    if any(path.exists() for path in paths) and not overwrite:
        raise M30DfuFailure("기존 M30 DFU 증적을 덮어쓰지 않습니다.")
    for path in paths:
        if path.exists():
            if not path.is_file():
                raise M30DfuFailure(f"증적 경로가 일반 파일이 아닙니다: {path}")
            path.unlink()
    evidence.parent.mkdir(parents=True, exist_ok=True)
    return paths


READY_PATTERN = re.compile(rb"^M30DFU\|1\|READY\|role=(peripheral|central)\|core=([0-9a-f]{40})$")
BEGIN_PATTERN = re.compile(
    rb"^M30DFU\|1\|BEGIN\|role=(peripheral|central)\|nonce=([0-9a-f]{32})\|core=([0-9a-f]{40})$"
)
BOOT_PATTERN = re.compile(
    rb"^M30DFU\|1\|BOOT\|role=peripheral\|active_area_id=(\d+)\|confirmed=(\d+)"
    rb"\|auto_confirm=(\d+)\|version=(\d+)\.(\d+)\.(\d+)\+(\d+)"
    rb"\|nonce=([0-9a-f]{32})\|core=([0-9a-f]{40})$"
)
LINK_PATTERNS = {
    "peripheral": re.compile(
        rb"^M30DFU\|1\|LINK\|role=peripheral\|level=4\|key_size=16\|smp=1"
        rb"\|nonce=([0-9a-f]{32})\|core=([0-9a-f]{40})$"
    ),
    "central": re.compile(
        rb"^M30DFU\|1\|LINK\|role=central\|level=4\|key_size=16\|mtu=247\|smp=1"
        rb"\|nonce=([0-9a-f]{32})\|core=([0-9a-f]{40})$"
    ),
}
RX_PATTERN = re.compile(
    rb"^M30DFU\|1\|RX\|role=central\|data=([0-9a-f]+)"
    rb"\|nonce=([0-9a-f]{32})\|core=([0-9a-f]{40})$"
)
UNLINK_PATTERN = re.compile(
    rb"^M30DFU\|1\|UNLINK\|role=central"
    rb"\|nonce=([0-9a-f]{32})\|core=([0-9a-f]{40})$"
)


class DfuSession:
    """! @brief 두 VCOM과 authenticated SMP request/response 상태를 소유합니다. """

    def __init__(
        self,
        serial_module: Any,
        peripheral: RoleEndpoint,
        central: RoleEndpoint,
        baud: int,
        nonce: str,
        core_revision: str,
    ) -> None:
        if baud != DEFAULT_BAUD_RATE:
            raise M30DfuFailure(f"M30 DFU는 {DEFAULT_BAUD_RATE} baud만 허용합니다.")
        self.serial_module = serial_module
        self.endpoints = {"peripheral": peripheral, "central": central}
        self.baud = baud
        self.nonce = nonce
        self.core_revision = core_revision
        self.stack = ExitStack()
        self.ports: dict[str, Any] = {}
        self.pending = {"peripheral": bytearray(), "central": bytearray()}
        self.capture = {"peripheral": bytearray(), "central": bytearray()}
        self.sequence = 0
        self.central_started = False

    def __enter__(self) -> DfuSession:
        """! @brief role별 exact VCOM을 열고 기존 입력을 비웁니다. """

        for role in ("peripheral", "central"):
            endpoint = self.endpoints[role]
            port = self.stack.enter_context(
                self.serial_module.Serial(
                    endpoint.port_name,
                    baudrate=self.baud,
                    bytesize=self.serial_module.EIGHTBITS,
                    parity=self.serial_module.PARITY_NONE,
                    stopbits=self.serial_module.STOPBITS_ONE,
                    timeout=0.05,
                    write_timeout=2.0,
                )
            )
            port.reset_input_buffer()
            self.ports[role] = port
        return self

    def __exit__(self, exception_type: Any, exception: Any, traceback: Any) -> None:
        """! @brief 열린 VCOM을 역순으로 닫습니다. """

        self.stack.close()

    def send_line(self, role: str, line: str) -> None:
        """! @brief 민감 payload를 출력하지 않고 완전한 ASCII command를 기록합니다. """

        data = (line + "\r\n").encode("ascii")
        if self.ports[role].write(data) != len(data):
            raise M30DfuFailure(f"{role} VCOM command가 일부만 기록됐습니다.")
        self.ports[role].flush()

    def read_line(self, role: str, deadline: float) -> bytes:
        """! @brief role별 bounded raw capture에서 newline 한 줄을 반환합니다. """

        pending = self.pending[role]
        capture = self.capture[role]
        port = self.ports[role]
        while time.monotonic() < deadline:
            newline = pending.find(b"\n")
            if newline >= 0:
                line = bytes(pending[:newline]).rstrip(b"\r")
                del pending[: newline + 1]
                return line
            waiting = int(getattr(port, "in_waiting", 0))
            chunk = port.read(waiting if waiting > 0 else 1)
            if chunk:
                pending.extend(chunk)
                capture.extend(chunk)
                if len(capture) > MAX_TRANSCRIPT_BYTES:
                    raise M30DfuFailure(f"{role} transcript가 허용 크기를 넘었습니다.")
        raise TimeoutError(f"{role} UART line timeout")

    def checked_line(self, role: str, deadline: float) -> bytes:
        """! @brief target FAIL을 즉시 승격하고 protocol line을 반환합니다. """

        line = self.read_line(role, deadline)
        if line.startswith(b"M30DFU|1|FAIL|"):
            raise M30DfuFailure(f"{role} target 실패: {line!r}")
        return line

    def synchronize(self, role: str, deadline: float) -> None:
        """! @brief 재부팅 뒤 READY query를 재시도해 application 생존을 확인합니다. """

        while time.monotonic() < deadline:
            self.send_line(role, "M30DFU|1|READY?")
            attempt = min(deadline, time.monotonic() + 1.0)
            try:
                while True:
                    line = self.checked_line(role, attempt)
                    match = READY_PATTERN.fullmatch(line)
                    if match is None:
                        continue
                    if match.group(1).decode("ascii") != role or match.group(2).decode("ascii") != self.core_revision:
                        raise M30DfuFailure(f"{role} READY identity가 다릅니다.")
                    return
            except TimeoutError:
                continue
        raise M30DfuFailure(f"{role} READY 동기화 timeout")

    def wait_begin(self, role: str, deadline: float) -> None:
        """! @brief START 뒤 exact role·nonce·revision BEGIN을 기다립니다. """

        while True:
            line = self.checked_line(role, deadline)
            match = BEGIN_PATTERN.fullmatch(line)
            if match is None:
                continue
            if (
                match.group(1).decode("ascii") != role
                or match.group(2).decode("ascii") != self.nonce
                or match.group(3).decode("ascii") != self.core_revision
            ):
                raise M30DfuFailure(f"{role} BEGIN identity가 다릅니다.")
            return

    def wait_boot(self, deadline: float) -> BootRecord:
        """! @brief START 직후 peripheral image 상태를 검증해 반환합니다. """

        while True:
            line = self.checked_line("peripheral", deadline)
            match = BOOT_PATTERN.fullmatch(line)
            if match is None:
                continue
            if match.group(8).decode("ascii") != self.nonce or match.group(9).decode("ascii") != self.core_revision:
                raise M30DfuFailure("peripheral BOOT identity가 다릅니다.")
            values = [int(value) for value in match.groups()[:7]]
            return BootRecord(values[0], values[1], values[2], tuple(values[3:7]))

    def start_peripheral(self, deadline: float) -> BootRecord:
        """! @brief 새 peripheral boot에 nonce를 넣고 BOOT 상태를 읽습니다. """

        self.synchronize("peripheral", deadline)
        self.send_line(
            "peripheral",
            f"M30DFU|1|START|nonce={self.nonce}|core={self.core_revision}",
        )
        self.wait_begin("peripheral", deadline)
        return self.wait_boot(deadline)

    def start_central(self, deadline: float) -> None:
        """! @brief Central scan을 동일 nonce로 한 번만 시작합니다. """

        if self.central_started:
            return
        self.synchronize("central", deadline)
        self.send_line(
            "central",
            f"M30DFU|1|START|nonce={self.nonce}|core={self.core_revision}",
        )
        self.wait_begin("central", deadline)
        self.central_started = True

    def wait_link(self, role: str, deadline: float) -> None:
        """! @brief exact L4·16-byte key·MTU·SMP link token을 검증합니다. """

        pattern = LINK_PATTERNS[role]
        while True:
            line = self.checked_line(role, deadline)
            match = pattern.fullmatch(line)
            if match is None:
                continue
            if match.group(1).decode("ascii") != self.nonce or match.group(2).decode("ascii") != self.core_revision:
                raise M30DfuFailure(f"{role} LINK identity가 다릅니다.")
            return

    def connect_initial(self, deadline: float) -> BootRecord:
        """! @brief Peripheral 광고 뒤 Central scan을 시작하고 양쪽 L4를 확인합니다. """

        boot = self.start_peripheral(deadline)
        self.start_central(deadline)
        self.wait_link("peripheral", deadline)
        self.wait_link("central", deadline)
        return boot

    def reconnect(self, deadline: float) -> BootRecord:
        """! @brief peripheral reboot 뒤 같은 Central과 다시 L4 연결합니다. """

        boot = self.start_peripheral(deadline)
        self.wait_link("peripheral", deadline)
        self.wait_link("central", deadline)
        return boot

    def wait_rx(self, deadline: float) -> bytes:
        """! @brief exact nonce·revision의 SMP response bytes를 반환합니다. """

        while True:
            line = self.checked_line("central", deadline)
            match = RX_PATTERN.fullmatch(line)
            if match is None:
                continue
            if match.group(2).decode("ascii") != self.nonce or match.group(3).decode("ascii") != self.core_revision:
                raise M30DfuFailure("SMP RX identity가 다릅니다.")
            try:
                return bytes.fromhex(match.group(1).decode("ascii"))
            except ValueError as error:
                raise M30DfuFailure("SMP RX hex가 잘못됐습니다.") from error

    def wait_unlink(self, deadline: float) -> None:
        """! @brief reset response 뒤 기존 Peripheral 연결 종료를 확인합니다. """

        while True:
            line = self.checked_line("central", deadline)
            match = UNLINK_PATTERN.fullmatch(line)
            if match is None:
                continue
            if (
                match.group(1).decode("ascii") != self.nonce
                or match.group(2).decode("ascii") != self.core_revision
            ):
                raise M30DfuFailure("central UNLINK identity가 다릅니다.")
            return

    def transaction(
        self,
        operation: int,
        group: int,
        command_id: int,
        payload: dict[Any, Any],
        deadline: float,
    ) -> SmpResult:
        """! @brief 한 version-2 SMP request와 exact response를 교환합니다. """

        encoded = cbor_encode(payload)
        sequence = self.sequence
        self.sequence = (self.sequence + 1) & 0xFF
        first = (1 << 3) | operation
        packet = struct.pack(">BBHHBB", first, 0, len(encoded), group, sequence, command_id) + encoded
        if len(packet) > MAX_SMP_PACKET:
            raise M30DfuFailure(f"SMP request가 ATT payload를 넘습니다: {len(packet)}")
        self.send_line("central", f"M30DFU|1|TX|{packet.hex()}")
        response = self.wait_rx(deadline)
        if len(response) < 8:
            raise M30DfuFailure("SMP response가 header보다 짧습니다.")
        response_first, flags, length, response_group, response_sequence, response_id = struct.unpack(
            ">BBHHBB", response[:8]
        )
        if (
            flags != 0
            or response_first & 0xE0 != 0
            or (response_first >> 3) & 0x03 != 1
            or response_first & 0x07 != operation + 1
            or length != len(response) - 8
            or response_group != group
            or response_sequence != sequence
            or response_id != command_id
        ):
            raise M30DfuFailure("SMP response header가 request identity와 다릅니다.")
        document = cbor_decode(response[8:])
        if not isinstance(document, dict):
            raise M30DfuFailure("SMP response payload가 map이 아닙니다.")
        error_group: int | None = None
        error_code = 0
        if "err" in document:
            error = document["err"]
            if not isinstance(error, dict) or not isinstance(error.get("group"), int) or not isinstance(error.get("rc"), int):
                raise M30DfuFailure("SMP group error 형식이 잘못됐습니다.")
            error_group = error["group"]
            error_code = error["rc"]
        elif "rc" in document:
            if not isinstance(document["rc"], int):
                raise M30DfuFailure("SMP generic rc 형식이 잘못됐습니다.")
            error_code = document["rc"]
        return SmpResult(document, error_group, error_code)

    def require_success(self, result: SmpResult, label: str) -> dict[Any, Any]:
        """! @brief SMP 오류가 없는 payload만 반환합니다. """

        if result.error_code != 0:
            raise M30DfuFailure(
                f"{label} SMP 오류: group={result.error_group}, rc={result.error_code}"
            )
        return result.payload

    def upload(self, artifact: ImageArtifact, deadline: float) -> int:
        """! @brief SHA-256 resume 계약으로 slot 1에 image 전체를 전송합니다. """

        data = artifact.path.read_bytes()
        offset = 0
        requests = 0
        while offset < len(data):
            chunk_length = min(216, len(data) - offset)
            while True:
                request: dict[str, Any] = {
                    "image": 0,
                    "data": data[offset : offset + chunk_length],
                    "off": offset,
                }
                if offset == 0:
                    request["len"] = len(data)
                    request["sha"] = bytes.fromhex(artifact.sha256)
                if len(cbor_encode(request)) + 8 <= MAX_SMP_PACKET:
                    break
                chunk_length -= 16
                if chunk_length <= 0:
                    raise M30DfuFailure("SMP upload chunk를 ATT MTU에 맞출 수 없습니다.")
            response = self.require_success(
                self.transaction(2, 1, 1, request, deadline), "image upload"
            )
            next_offset = response.get("off")
            if not isinstance(next_offset, int) or not offset < next_offset <= len(data):
                raise M30DfuFailure(
                    f"image upload offset가 진행하지 않습니다: {offset}->{next_offset}"
                )
            offset = next_offset
            requests += 1
            if requests % 250 == 0 or offset == len(data):
                print(
                    f"M30_DFU_UPLOAD_PROGRESS={artifact.path.name}:{offset}/{len(data)}",
                    flush=True,
                )
        if response.get("match") is not True:
            raise M30DfuFailure("최종 upload SHA-256 match가 true가 아닙니다.")
        return requests

    def image_state(self, deadline: float) -> list[dict[str, Any]]:
        """! @brief image state list를 strict type으로 반환합니다. """

        payload = self.require_success(
            self.transaction(0, 1, 0, {}, deadline), "image state read"
        )
        images = payload.get("images")
        if not isinstance(images, list) or not all(isinstance(item, dict) for item in images):
            raise M30DfuFailure("image state의 images가 map 배열이 아닙니다.")
        return images

    def state_for_hash(self, image_hash: bytes, deadline: float) -> dict[str, Any] | None:
        """! @brief exact embedded image hash의 state entry를 찾습니다. """

        matches = [item for item in self.image_state(deadline) if item.get("hash") == image_hash]
        if len(matches) > 1:
            raise M30DfuFailure("동일 image hash가 여러 slot에 있습니다.")
        return matches[0] if matches else None

    def request_test(self, image_hash: bytes, deadline: float) -> SmpResult:
        """! @brief 지정 hash를 permanent가 아닌 test boot로 표시합니다. """

        return self.transaction(2, 1, 0, {"confirm": False, "hash": image_hash}, deadline)

    def erase_secondary(self, deadline: float) -> None:
        """! @brief MCUmgr가 허용한 inactive slot 1만 지웁니다. """

        self.require_success(
            self.transaction(2, 1, 5, {"slot": 1}, deadline), "secondary erase"
        )

    def reset_and_reconnect(self, deadline: float) -> BootRecord:
        """! @brief OS management reset response 뒤 새 peripheral boot를 L4로 재연결합니다. """

        self.require_success(self.transaction(2, 0, 5, {}, deadline), "OS reset")
        self.wait_unlink(deadline)
        return self.reconnect(deadline)


def validate_boot(
    record: BootRecord,
    version: tuple[int, int, int, int],
    *,
    confirmed: int,
    auto_confirm: int,
) -> None:
    """! @brief 실행 image version·confirm mode·active slot을 검증합니다. """

    if (
        record.active_area_id != PRIMARY_FLASH_AREA_ID
        or record.version != version
        or record.confirmed != confirmed
        or record.auto_confirm != auto_confirm
    ):
        raise M30DfuFailure(
            f"BOOT 상태가 다릅니다: {record}, expected={version}/{confirmed}/{auto_confirm}"
        )


def create_candidates(
    confirmed: PeripheralBuild,
    unconfirmed: PeripheralBuild,
    trust_key: Path,
    wrong_key: Path,
    imgtool_python: Path,
    imgtool: Path,
    directory: Path,
) -> tuple[list[ImageArtifact], dict[str, ImageArtifact], ImageArtifact]:
    """! @brief 정상 10개·negative 5종·unconfirmed rollback image를 생성합니다. """

    positives = [
        run_imgtool(
            confirmed.raw_bin,
            directory / f"positive-v{version}.bin",
            (version, 0, 0, 0),
            version + 1,
            imgtool_python,
            imgtool,
            trust_key,
        )
        for version in range(1, POSITIVE_UPDATES + 1)
    ]
    unsigned = run_imgtool(
        confirmed.raw_bin,
        directory / "negative-unsigned.bin",
        (20, 0, 0, 0),
        12,
        imgtool_python,
        imgtool,
        None,
    )
    wrong = run_imgtool(
        confirmed.raw_bin,
        directory / "negative-wrong-key.bin",
        (20, 0, 0, 1),
        12,
        imgtool_python,
        imgtool,
        wrong_key,
    )
    valid_corrupt_source = run_imgtool(
        confirmed.raw_bin,
        directory / "negative-corrupt-source.bin",
        (20, 0, 0, 2),
        12,
        imgtool_python,
        imgtool,
        trust_key,
    )
    corrupt = mutate_corrupt(valid_corrupt_source, directory / "negative-corrupt.bin")
    valid_truncated_source = run_imgtool(
        confirmed.raw_bin,
        directory / "negative-truncated-source.bin",
        (20, 0, 0, 3),
        12,
        imgtool_python,
        imgtool,
        trust_key,
    )
    truncated = mutate_truncated(valid_truncated_source, directory / "negative-truncated.bin")
    downgrade = run_imgtool(
        confirmed.raw_bin,
        directory / "negative-downgrade.bin",
        (9, 0, 0, 0),
        10,
        imgtool_python,
        imgtool,
        trust_key,
    )
    rollback = run_imgtool(
        unconfirmed.raw_bin,
        directory / "unconfirmed-v11.bin",
        UNCONFIRMED_VERSION,
        12,
        imgtool_python,
        imgtool,
        trust_key,
    )
    return positives, {
        "unsigned": unsigned,
        "wrong_key": wrong,
        "corrupt": corrupt,
        "truncated": truncated,
        "downgrade": downgrade,
    }, rollback


def run_positive(
    session: DfuSession,
    positives: Sequence[ImageArtifact],
    deadline: float,
) -> dict[str, Any]:
    """! @brief signed BLE update 10회와 hash·confirm 상태를 검증합니다. """

    upload_requests = 0
    hash_mismatches = 0
    unconfirmed_boots = 0
    for index, artifact in enumerate(positives, start=1):
        upload_requests += session.upload(artifact, deadline)
        state = session.state_for_hash(artifact.image_hash, deadline)
        if state is None or state.get("bootable") is not True:
            raise M30DfuFailure(f"positive v{index}가 bootable state에 없습니다.")
        result = session.request_test(artifact.image_hash, deadline)
        session.require_success(result, f"positive v{index} test request")
        boot = session.reset_and_reconnect(deadline)
        if boot.confirmed != 1:
            unconfirmed_boots += 1
        validate_boot(boot, artifact.version, confirmed=1, auto_confirm=1)
        active = session.state_for_hash(artifact.image_hash, deadline)
        if active is None or active.get("active") is not True or active.get("confirmed") is not True:
            hash_mismatches += 1
            raise M30DfuFailure(f"positive v{index} active hash·confirm state가 다릅니다.")
        print(f"M30_DFU_POSITIVE_PASS={index}/{POSITIVE_UPDATES}", flush=True)
    return {
        "updates": len(positives),
        "upload_requests": upload_requests,
        "hash_mismatches": hash_mismatches,
        "unconfirmed_boots": unconfirmed_boots,
    }


def run_negative_class(
    session: DfuSession,
    name: str,
    artifact: ImageArtifact,
    deadline: float,
) -> dict[str, Any]:
    """! @brief 한 invalid image upload 뒤 test 승인·boot 거부를 20회 반복합니다. """

    upload_requests = session.upload(artifact, deadline)
    state_rejects = 0
    boot_rejects = 0
    invalid_accepts = 0
    for attempt in range(1, NEGATIVE_ATTEMPTS + 1):
        result = session.request_test(artifact.image_hash, deadline)
        if result.error_code != 0:
            state_rejects += 1
        else:
            boot = session.reset_and_reconnect(deadline)
            if boot.version == FINAL_VERSION and boot.confirmed == 1 and boot.auto_confirm == 1:
                boot_rejects += 1
            else:
                invalid_accepts += 1
                raise M30DfuFailure(f"{name} candidate가 boot됐습니다: {boot}")
        if attempt % 5 == 0:
            print(f"M30_DFU_NEGATIVE_PROGRESS={name}:{attempt}/{NEGATIVE_ATTEMPTS}", flush=True)
    if state_rejects + boot_rejects != NEGATIVE_ATTEMPTS:
        raise M30DfuFailure(f"{name} negative attempt 계수가 다릅니다.")
    session.erase_secondary(deadline)
    return {
        "attempts": NEGATIVE_ATTEMPTS,
        "upload_requests": upload_requests,
        "state_rejects": state_rejects,
        "boot_rejects": boot_rejects,
        "invalid_accepts": invalid_accepts,
    }


def run_rollback(
    session: DfuSession,
    rollback: ImageArtifact,
    deadline: float,
) -> dict[str, Any]:
    """! @brief 미확정 image 첫 boot와 다음 boot의 confirmed 복귀를 검증합니다. """

    upload_requests = session.upload(rollback, deadline)
    session.require_success(
        session.request_test(rollback.image_hash, deadline), "unconfirmed test request"
    )
    first = session.reset_and_reconnect(deadline)
    validate_boot(first, UNCONFIRMED_VERSION, confirmed=0, auto_confirm=0)
    active = session.state_for_hash(rollback.image_hash, deadline)
    if active is None or active.get("active") is not True or active.get("confirmed") is True:
        raise M30DfuFailure("unconfirmed image의 active state가 다릅니다.")
    reverted = session.reset_and_reconnect(deadline)
    validate_boot(reverted, FINAL_VERSION, confirmed=1, auto_confirm=1)
    return {
        "upload_requests": upload_requests,
        "unconfirmed_first_boots": 1,
        "rollback_accepts": 0,
        "recovered_version": list(reverted.version),
    }


def main(arguments: Sequence[str] | None = None) -> int:
    """! @brief preflight 또는 실제 M30-DFU-01/NEG-01을 실행합니다. """

    args = parse_arguments(arguments)
    if not 120.0 <= args.phase_timeout <= 1200.0:
        raise M30DfuFailure("--phase-timeout은 120..1200초여야 합니다.")
    if args.flash_timeout <= 0:
        raise M30DfuFailure("--flash-timeout은 0보다 커야 합니다.")
    if args.nonce is None:
        nonce = os.urandom(16).hex()
    elif re.fullmatch(r"[0-9a-f]{32}", args.nonce):
        nonce = args.nonce
    else:
        raise M30DfuFailure("--nonce는 32자리 소문자 hex여야 합니다.")

    serial_module, list_ports = import_pyserial()
    peripheral_endpoint = discover_endpoint(
        args.peripheral_board_id,
        args.peripheral_volume,
        args.peripheral_port,
        list_ports,
    )
    central_endpoint = discover_endpoint(
        args.central_board_id,
        args.central_volume,
        args.central_port,
        list_ports,
    )
    validate_pair_identity(peripheral_endpoint, central_endpoint)
    if args.discover_only:
        print("M30_DFU_DISCOVERY_PASS=2")
        return 0

    validate_source_clean(
        MILESTONE,
        APPLICATION_ROOT,
        RUNNER_PATH,
        (DFU_LIBRARY, BOOT_RUNNER_PATH),
    )
    core_revision = git_revision(REPOSITORY)
    if args.expected_core_revision and args.expected_core_revision != core_revision:
        raise M30DfuFailure("현재 Core revision이 --expected-core-revision과 다릅니다.")
    board_revision = git_revision(BOARD_ROOT)
    validate_board_revision(board_revision)
    trust_key = validate_private_key(args.trust_signing_key, "trust signing key")
    wrong_key = validate_private_key(args.wrong_signing_key, "wrong signing key")
    if trust_key.read_bytes() == wrong_key.read_bytes():
        raise M30DfuFailure("trust key와 wrong key가 같습니다.")
    confirmed = collect_peripheral_build(
        args.peripheral_build_outdir, core_revision, trust_key, 1
    )
    unconfirmed = collect_peripheral_build(
        args.unconfirmed_build_outdir, core_revision, trust_key, 0
    )
    central = collect_central_build(args.central_build_outdir, core_revision)
    if confirmed.public_key_sha256 != unconfirmed.public_key_sha256:
        raise M30DfuFailure("confirmed와 unconfirmed MCUboot public key가 다릅니다.")
    if file_sha256(confirmed.boot_hex) != file_sha256(unconfirmed.boot_hex):
        raise M30DfuFailure("confirmed와 unconfirmed MCUboot image가 다릅니다.")
    immutable_inputs = {
        path.resolve(): (path.stat().st_size, file_sha256(path))
        for path in (
            confirmed.boot_hex,
            confirmed.signed_hex,
            confirmed.raw_bin,
            unconfirmed.boot_hex,
            unconfirmed.signed_hex,
            unconfirmed.raw_bin,
            central.image,
        )
    }
    evidence_path, peripheral_transcript, central_transcript = output_paths(
        args.evidence, args.overwrite_evidence
    )

    imgtool_python = Path(args.imgtool_python).resolve()
    imgtool = Path(args.imgtool).resolve()
    flash_results: dict[str, Any] = {}
    session: DfuSession | None = None
    started = time.monotonic()
    try:
        with tempfile.TemporaryDirectory(prefix="n54-m30-dfu-") as temporary:
            positives, negatives, rollback = create_candidates(
                confirmed,
                unconfirmed,
                trust_key,
                wrong_key,
                imgtool_python,
                imgtool,
                Path(temporary),
            )
            erase_secondary_slot(peripheral_endpoint.board_id, args.flash_timeout)
            flash_results["peripheral_bootloader"] = flash_image_pyocd(
                "peripheral-bootloader",
                peripheral_endpoint.board_id,
                confirmed.boot_hex,
                args.flash_timeout,
            )
            flash_results["peripheral_primary"] = flash_image_pyocd(
                "peripheral-primary",
                peripheral_endpoint.board_id,
                confirmed.signed_hex,
                args.flash_timeout,
            )
            flash_results["central"] = flash_image_pyocd(
                "central-relay",
                central_endpoint.board_id,
                central.image,
                args.flash_timeout,
            )

            with DfuSession(
                serial_module,
                peripheral_endpoint,
                central_endpoint,
                args.baud,
                nonce,
                core_revision,
            ) as session:
                initial_deadline = time.monotonic() + 60.0
                initial = session.connect_initial(initial_deadline)
                validate_boot(initial, BASE_VERSION, confirmed=1, auto_confirm=1)

                positive_started = time.monotonic()
                positive = run_positive(
                    session, positives, positive_started + args.phase_timeout
                )
                positive_duration = time.monotonic() - positive_started

                negative_started = time.monotonic()
                negative_results = {
                    name: run_negative_class(
                        session,
                        name,
                        artifact,
                        negative_started + args.phase_timeout,
                    )
                    for name, artifact in negatives.items()
                }
                rollback_result = run_rollback(
                    session, rollback, negative_started + args.phase_timeout
                )
                negative_duration = time.monotonic() - negative_started

                invalid_accepts = sum(
                    result["invalid_accepts"] for result in negative_results.values()
                )
                if invalid_accepts != 0 or rollback_result["rollback_accepts"] != 0:
                    raise M30DfuFailure("negative 또는 rollback acceptance가 0이 아닙니다.")

                peripheral_capture = bytes(session.capture["peripheral"])
                central_capture = bytes(session.capture["central"])
                candidates_evidence = {
                    "positive": [artifact_evidence(item) for item in positives],
                    "negative": {
                        name: artifact_evidence(item) for name, item in negatives.items()
                    },
                    "unconfirmed": artifact_evidence(rollback),
                }
    except Exception as error:
        if session is not None:
            peripheral_transcript.write_bytes(bytes(session.capture["peripheral"]))
            central_transcript.write_bytes(bytes(session.capture["central"]))
        if isinstance(error, (M30DfuFailure, M30BootFailure, BlePairHilFailure)):
            raise M30DfuFailure(
                f"{error}; 실패 transcript: {peripheral_transcript.name}, {central_transcript.name}"
            ) from error
        raise

    for path, (size, digest) in immutable_inputs.items():
        validate_image_unchanged(path, size, digest)
    peripheral_transcript.write_bytes(peripheral_capture)
    central_transcript.write_bytes(central_capture)
    duration = time.monotonic() - started
    evidence = {
        "schema_version": 1,
        "status": "passed",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": round(duration, 3),
        "core_revision": core_revision,
        "board_revision": board_revision,
        "boards": 2,
        "endpoints": {
            "peripheral": endpoint_evidence(peripheral_endpoint),
            "central": endpoint_evidence(central_endpoint),
        },
        "results": {
            "M30-DFU-01": {
                "status": "passed",
                "duration_seconds": round(positive_duration, 3),
                **positive,
            },
            "M30-DFU-NEG-01": {
                "status": "passed",
                "duration_seconds": round(negative_duration, 3),
                "classes": negative_results,
                "invalid_accepts": 0,
                **rollback_result,
            },
        },
        "candidates": candidates_evidence,
        "trust_public_key_source_sha256": confirmed.public_key_sha256,
        "build_records": {
            "confirmed": confirmed.record,
            "unconfirmed": unconfirmed.record,
            "central": central.record,
        },
        "flash_backend": "pyocd-exact-sector",
        "flash_results": flash_results,
        "transport": {
            "carrier": "BLE",
            "security_level": 4,
            "encryption_key_size": 16,
            "att_mtu": 247,
            "host_to_ble_bridge": "NU54DK-central-vcom",
        },
        "power_cut_injected": False,
        "physical_power_loss_claim": False,
        "mass_erase_or_recover": False,
        "transcripts": {
            "peripheral": transcript_record(peripheral_transcript, peripheral_capture),
            "central": transcript_record(central_transcript, central_capture),
        },
    }
    evidence_path.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print("M30_DFU_HIL_PASS=10;HASH_MISMATCHES=0;UNCONFIRMED_BOOTS=0")
    print("M30_DFU_NEG_HIL_PASS=5x20;INVALID_ACCEPTS=0;ROLLBACK_ACCEPTS=0;POWER_CUT=0")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (M30DfuFailure, M30BootFailure, BlePairHilFailure) as error:
        print(f"M30_DFU_HIL_FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
