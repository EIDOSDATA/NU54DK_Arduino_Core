#!/usr/bin/env python3
"""! @brief fcbbfac5 공개 PBP exact build를 고정한 5-mode campaign launcher입니다.

기존 runner와 campaign을 수정하지 않고 검토된 build log, manifest, image, 공개 sketch를
fail-closed 검사합니다. self-test는 probe, COM, target hardware를 사용하지 않습니다.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Sequence


EXPECTED_CORE_REVISION = "fcbbfac5fe348c51be0fb4e30f2b8415099b8758"
EXPECTED_BOARD_REVISION = "fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3"
EXPECTED_NRF_REVISION = "99553055607b2e9885fbc80ccd11fa9da81c2df0"
EXPECTED_ZEPHYR_REVISION = "bf801e4e3d19e1ffa76164346480cb7734dd2800"
EXPECTED_TOOLCHAIN_BUNDLE = "dcbdc366a1"
EXPECTED_FQBN = "nucode:zephyr:nu54dk:feature_set=ble,upload_probe=pyocd"
EXPECTED_BOARD = "nrf54l15dk/nrf54l15/cpuapp/nu54dk"
EXPECTED_CAMPAIGN_SHA256 = (
    "954deb5cf46520d74159ed8751e4ee1db0f640dffc2bfbc4ae61c1053569ae1f"
)
HASH_PATTERN = re.compile(r"[0-9a-f]{64}")

CORE_ROOT = Path(r"C:\Users\eidos\GitHub\NU54DK_Arduino_Core")
SOURCE_EXAMPLE = CORE_ROOT / (
    "libraries/NUCODE_BLE_Audio/examples/PublicAudioBroadcastSource/"
    "PublicAudioBroadcastSource.ino"
)
SINK_EXAMPLE = CORE_ROOT / (
    "libraries/NUCODE_BLE_Audio/examples/PublicAudioBroadcastSink/"
    "PublicAudioBroadcastSink.ino"
)
SOURCE_IMAGE = Path(
    r"C:\w\m31w07-source-fcbbfac5\PublicAudioBroadcastSource.ino.hex"
)
SINK_IMAGE = Path(r"C:\w\m31w07-sink-fcbbfac5\PublicAudioBroadcastSink.ino.hex")
SOURCE_MANIFEST = Path(
    r"C:\w\m31w07-source-fcbbfac5\PublicAudioBroadcastSource.ino.nu54-build.json"
)
SINK_MANIFEST = Path(
    r"C:\w\m31w07-sink-fcbbfac5\PublicAudioBroadcastSink.ino.nu54-build.json"
)
SOURCE_LOG = Path(r"C:\w\m31w07-source-fcbbfac5.build.log")
SINK_LOG = Path(r"C:\w\m31w07-sink-fcbbfac5.build.log")

EXPECTED_FILES = {
    SOURCE_EXAMPLE: "9476ef6d0575c54664189f74df79d8f473802815ebb4e15a9b60cee45cb06212",
    SINK_EXAMPLE: "c7b16301bfaa8f9949cd19b0158c4452d3fabfb51b19f93235acc11a486f1bf5",
    SOURCE_IMAGE: "1b5d5adcdf62a5974a9edddcbd8f88f7f658252d5224e22b6b0ca8d5cbbefa1e",
    SINK_IMAGE: "ca5f1db5ded8792cb833d3ac7f0dab351d685607170fc6e966397800a2a560cb",
    SOURCE_MANIFEST: "f9f555227329fe48df0bab25f7c44d61e004c71a60cdaf746cae2e0e2eb8d079",
    SINK_MANIFEST: "8ad171e13818e72ac231a0fa1dc7e594d8cfc910d634f05f7a1cd0676d495ad7",
    SOURCE_LOG: "dbfe2c1c30022711df209395a54cf37b646cb5aa3f62dd8cf163687b3b52b25e",
    SINK_LOG: "68d823b3c87e3ae5fd942d1a5639666163fe62ef22480cf61b4adde809294bf8",
}

EXPECTED_BUILDS = {
    "source": {
        "manifest": SOURCE_MANIFEST,
        "image": SOURCE_IMAGE,
        "image_sha256": EXPECTED_FILES[SOURCE_IMAGE],
        "sketch_root": SOURCE_EXAMPLE.parent,
        "log": SOURCE_LOG,
        "program_bytes": 499812,
        "dynamic_bytes": 223274,
    },
    "sink": {
        "manifest": SINK_MANIFEST,
        "image": SINK_IMAGE,
        "image_sha256": EXPECTED_FILES[SINK_IMAGE],
        "sketch_root": SINK_EXAMPLE.parent,
        "log": SINK_LOG,
        "program_bytes": 488776,
        "dynamic_bytes": 225708,
    },
}


class ExactCampaignFailure(RuntimeError):
    """! @brief exact campaign 준비 실패를 나타냅니다. """


def sha256_file(path: Path) -> str:
    """! @brief 파일 SHA-256을 계산합니다. """
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def campaign_path() -> Path:
    """! @brief 보존된 revision-neutral campaign 경로를 반환합니다. """
    return Path(__file__).resolve().with_name("pbp_full_campaign.py")


def verify_file(path: Path, expected_hash: str) -> None:
    """! @brief 파일 존재와 exact SHA-256을 확인합니다. """
    if not path.is_file():
        raise ExactCampaignFailure(f"필수 파일이 없습니다: {path}")
    actual_hash = sha256_file(path)
    if actual_hash != expected_hash:
        raise ExactCampaignFailure(
            f"파일 SHA-256 불일치 expected={expected_hash} actual={actual_hash}"
        )


def verify_repository() -> None:
    """! @brief core checkout의 exact HEAD와 clean 상태를 확인합니다. """
    try:
        head = subprocess.check_output(
            ("git", "rev-parse", "HEAD"), cwd=CORE_ROOT, text=True
        ).strip()
        dirty = subprocess.check_output(
            ("git", "status", "--porcelain=v1", "--untracked-files=all"),
            cwd=CORE_ROOT,
            text=True,
        ).strip()
    except (OSError, subprocess.CalledProcessError) as error:
        raise ExactCampaignFailure("Core source 확인 실패") from error
    if head != EXPECTED_CORE_REVISION:
        raise ExactCampaignFailure(f"Core revision 불일치: {head}")
    if dirty:
        raise ExactCampaignFailure("Core source가 clean 상태가 아닙니다.")


def nested(document: dict[str, Any], *keys: str) -> Any:
    """! @brief JSON 중첩 값을 fail-closed 방식으로 읽습니다. """
    value: Any = document
    for key in keys:
        if not isinstance(value, dict) or key not in value:
            raise ExactCampaignFailure(f"manifest 필드가 없습니다: {'.'.join(keys)}")
        value = value[key]
    return value


def verify_build(role: str, expected: dict[str, Any]) -> None:
    """! @brief 한 역할의 manifest와 Arduino size 출력을 확인합니다. """
    manifest_path: Path = expected["manifest"]
    try:
        document = json.loads(manifest_path.read_text(encoding="utf-8"))
        log_text = expected["log"].read_text(encoding="utf-8", errors="strict")
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ExactCampaignFailure(f"{role} build 증거 읽기 실패") from error
    required = {
        ("source_inputs", "m31_audio_revisions", "NUCODE_CORE_REVISION"):
            EXPECTED_CORE_REVISION,
        ("source_inputs", "m31_audio_revisions", "NUCODE_BOARD_REVISION"):
            EXPECTED_BOARD_REVISION,
        ("source_inputs", "m31_audio_revisions", "NUCODE_NCS_REVISION"):
            EXPECTED_NRF_REVISION,
        ("source_inputs", "m31_audio_revisions", "NUCODE_ZEPHYR_REVISION"):
            EXPECTED_ZEPHYR_REVISION,
        ("cache", "input_manifest", "toolchain", "bundle_id"):
            EXPECTED_TOOLCHAIN_BUNDLE,
        ("board",): EXPECTED_BOARD,
        ("context", "fqbn"): EXPECTED_FQBN,
        ("context", "profile"): "ble",
        ("context", "sketch_root"): expected["sketch_root"].as_posix(),
        ("artifacts", "hex", "path"): expected["image"].as_posix(),
        ("artifacts", "hex", "sha256"): expected["image_sha256"],
    }
    for keys, expected_value in required.items():
        actual_value = nested(document, *keys)
        if actual_value != expected_value:
            raise ExactCampaignFailure(
                f"{role} manifest 불일치 {'.'.join(keys)}={actual_value!r}"
            )
    program_line = f"Sketch uses {expected['program_bytes']} bytes"
    dynamic_line = f"Global variables use {expected['dynamic_bytes']} bytes"
    if program_line not in log_text or dynamic_line not in log_text:
        raise ExactCampaignFailure(f"{role} Arduino size 증거가 다릅니다.")


def static_preflight() -> None:
    """! @brief hardware를 건드리지 않고 모든 exact 입력을 검증합니다. """
    verify_repository()
    verify_file(campaign_path(), EXPECTED_CAMPAIGN_SHA256)
    for path, expected_hash in EXPECTED_FILES.items():
        verify_file(path, expected_hash)
    for role, expected in EXPECTED_BUILDS.items():
        verify_build(role, expected)


def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    """! @brief self-test와 실제 run 인자를 정의합니다. """
    parser = argparse.ArgumentParser(description="fcbbfac5 PBP exact campaign")
    parser.add_argument("command", choices=("run", "self-test"))
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--source-port", default="COM10")
    parser.add_argument("--sink-port", default="COM14")
    parser.add_argument("--source-probe-sha256")
    parser.add_argument("--sink-probe-sha256")
    return parser.parse_args(arguments)


def base_command(args: argparse.Namespace) -> tuple[str, ...]:
    """! @brief 고정 build만 전달하는 revision-neutral campaign 명령을 만듭니다. """
    return (
        sys.executable,
        str(campaign_path()),
        args.command,
        "--core-root",
        str(CORE_ROOT),
        "--core-revision",
        EXPECTED_CORE_REVISION,
        "--source-image",
        str(SOURCE_IMAGE),
        "--source-image-sha256",
        EXPECTED_FILES[SOURCE_IMAGE],
        "--source-example-sha256",
        EXPECTED_FILES[SOURCE_EXAMPLE],
        "--sink-image",
        str(SINK_IMAGE),
        "--sink-image-sha256",
        EXPECTED_FILES[SINK_IMAGE],
        "--sink-example-sha256",
        EXPECTED_FILES[SINK_EXAMPLE],
    )


def main(arguments: Sequence[str] | None = None) -> int:
    """! @brief 정적 preflight 뒤 self-test 또는 full campaign을 실행합니다. """
    args = parse_arguments(arguments)
    static_preflight()
    command = list(base_command(args))
    if args.command == "self-test":
        completed = subprocess.run(command, check=False)
        if completed.returncode == 0:
            print(
                "M31_PBP_FCBBFAC5_PREFLIGHT=PASS;"
                "BUILDS=2;HARDWARE=UNTOUCHED"
            )
        return completed.returncode
    required = {
        "output-dir": args.output_dir,
        "source-probe-sha256": args.source_probe_sha256,
        "sink-probe-sha256": args.sink_probe_sha256,
    }
    missing = [name for name, value in required.items() if value is None]
    if missing:
        raise ExactCampaignFailure(f"필수 run 인자가 없습니다: {','.join(missing)}")
    for value in (args.source_probe_sha256, args.sink_probe_sha256):
        if HASH_PATTERN.fullmatch(value) is None:
            raise ExactCampaignFailure("Probe SHA-256 형식이 잘못되었습니다.")
    command.extend(
        (
            "--output-dir",
            str(args.output_dir),
            "--source-port",
            args.source_port,
            "--sink-port",
            args.sink_port,
            "--source-probe-sha256",
            args.source_probe_sha256,
            "--sink-probe-sha256",
            args.sink_probe_sha256,
        )
    )
    return subprocess.run(command, check=False).returncode


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ExactCampaignFailure as error:
        print(f"M31_PBP_FCBBFAC5_PREFLIGHT=FAIL;ERROR={error}", file=sys.stderr)
        raise SystemExit(2) from error
