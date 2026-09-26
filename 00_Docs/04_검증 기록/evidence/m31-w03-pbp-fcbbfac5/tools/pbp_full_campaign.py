#!/usr/bin/env python3
"""! @brief 공개 PBP 5개 HIL 시나리오를 한 exact provenance로 실행합니다.

이 도구는 image를 만들지 않습니다. 호출자가 제공한 동일 revision의 source/sink image와
공개 sketch hash를 사용해 positive, stop/restart, wrong code, unsupported quality,
sync loss를 순서대로 실행합니다. PBP는 bond 저장소를 사용하지 않으므로 storage erase는
수행하지 않습니다.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Sequence


EXPECTED_RUNNER_SHA256 = (
    "66e0e27f84f4535e5212035e198e4c9b4be37b698026edc7cc718771ba89036e"
)
EXPECTED_DEBUG_HELPER_SHA256 = (
    "a2d9c1a83198a3e28c6d2562320697edbbc3adba03ce10c8e6295ffde310a7a2"
)
EXPECTED_FLASH_HELPER_SHA256 = (
    "3cdbd5d87aa8a39240bf06124ee0f5bfeafbfdf9c9c96c2705ab07d066497d16"
)
MODES = ("positive", "stop-restart", "wrong-code", "quality", "sync-loss")
HASH_PATTERN = re.compile(r"[0-9a-f]{64}")
REVISION_PATTERN = re.compile(r"[0-9a-f]{40}")
SCENARIO_TIMEOUT_SECONDS = 600.0
OUTPUT_LIMIT = 1200


class CampaignFailure(RuntimeError):
    """! @brief campaign 준비 또는 실행 실패를 나타냅니다. """


def utc_now() -> str:
    """! @brief 현재 UTC 시각을 ISO 8601로 반환합니다. """
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    """! @brief 파일 SHA-256을 계산합니다. """
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def bounded_text(value: str) -> str:
    """! @brief subprocess 출력을 bounded 한 줄 문자열로 만듭니다. """
    sanitized = value.strip().replace("\r", "\\r").replace("\n", "\\n")
    if len(sanitized) <= OUTPUT_LIMIT:
        return sanitized
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    marker = f"...<truncated sha256={digest}>..."
    side = max(0, (OUTPUT_LIMIT - len(marker)) // 2)
    return (sanitized[:side] + marker + sanitized[-side:])[:OUTPUT_LIMIT]


def verify_exact_file(path: Path, expected_hash: str, label: str) -> Path:
    """! @brief 파일 존재와 고정 hash를 fail-closed 검사합니다. """
    resolved = path.resolve()
    if not resolved.is_file():
        raise CampaignFailure(f"{label} 파일이 없습니다: {resolved}")
    actual_hash = sha256_file(resolved)
    if actual_hash != expected_hash:
        raise CampaignFailure(
            f"{label} SHA-256 불일치 expected={expected_hash} actual={actual_hash}"
        )
    return resolved


def default_path(name: str) -> Path:
    """! @brief campaign sibling 도구 경로를 반환합니다. """
    return Path(__file__).resolve().with_name(name)


def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    """! @brief exact build와 출력 경로 인자를 정의합니다. """
    parser = argparse.ArgumentParser(description="공개 PBP exact 5-mode campaign")
    parser.add_argument("command", choices=("run", "self-test"))
    parser.add_argument("--core-root", type=Path)
    parser.add_argument("--core-revision")
    parser.add_argument("--source-image", type=Path)
    parser.add_argument("--source-image-sha256")
    parser.add_argument("--source-example-sha256")
    parser.add_argument("--sink-image", type=Path)
    parser.add_argument("--sink-image-sha256")
    parser.add_argument("--sink-example-sha256")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--source-port", default="COM10")
    parser.add_argument("--sink-port", default="COM14")
    parser.add_argument("--source-probe-sha256")
    parser.add_argument("--sink-probe-sha256")
    parser.add_argument("--runner", type=Path, default=default_path("pbp_hil_final.py"))
    parser.add_argument(
        "--reset-helper",
        type=Path,
        default=default_path("pyocd_commands_by_hash.py"),
    )
    parser.add_argument(
        "--flash-helper",
        type=Path,
        default=default_path("flash_by_probe_hash.py"),
    )
    return parser.parse_args(arguments)


def verify_tooling(args: argparse.Namespace) -> dict[str, Any]:
    """! @brief runner와 두 helper의 현재 reviewed hash를 확인합니다. """
    runner = verify_exact_file(args.runner, EXPECTED_RUNNER_SHA256, "runner")
    debugger = verify_exact_file(
        args.reset_helper, EXPECTED_DEBUG_HELPER_SHA256, "debug helper"
    )
    flasher = verify_exact_file(
        args.flash_helper, EXPECTED_FLASH_HELPER_SHA256, "flash helper"
    )
    return {
        "runner": runner,
        "runner_sha256": EXPECTED_RUNNER_SHA256,
        "debug_helper": debugger,
        "debug_helper_sha256": EXPECTED_DEBUG_HELPER_SHA256,
        "flash_helper": flasher,
        "flash_helper_sha256": EXPECTED_FLASH_HELPER_SHA256,
    }


def run_self_test(args: argparse.Namespace) -> int:
    """! @brief hash preflight와 runner fixture를 hardware 없이 실행합니다. """
    tooling = verify_tooling(args)
    completed = subprocess.run(
        (sys.executable, str(tooling["runner"]), "self-test"),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="backslashreplace",
        timeout=30.0,
        check=False,
    )
    output = completed.stdout + completed.stderr
    if (
        completed.returncode != 0
        or "M31_PBP_HIL_SELF_TEST=PASS" not in output
        or "HARDWARE=UNTOUCHED" not in output
    ):
        raise CampaignFailure(
            f"runner self-test 실패 rc={completed.returncode} output={bounded_text(output)}"
        )
    print(
        "M31_PBP_CAMPAIGN_SELF_TEST=PASS;"
        f"MODES={len(MODES)};RUNNER={tooling['runner_sha256']};"
        f"DEBUGGER={tooling['debug_helper_sha256']};"
        f"FLASHER={tooling['flash_helper_sha256']};"
        "STORAGE_ERASE=NOT_REQUIRED;HARDWARE=UNTOUCHED"
    )
    return 0


def require_run_arguments(args: argparse.Namespace) -> dict[str, Any]:
    """! @brief run 전 exact source/image/output 계약을 확인합니다. """
    required_names = (
        "core_root",
        "core_revision",
        "source_image",
        "source_image_sha256",
        "source_example_sha256",
        "sink_image",
        "sink_image_sha256",
        "sink_example_sha256",
        "output_dir",
        "source_probe_sha256",
        "sink_probe_sha256",
    )
    missing = [name for name in required_names if getattr(args, name) is None]
    if missing:
        raise CampaignFailure(f"필수 run 인자가 없습니다: {','.join(missing)}")
    if REVISION_PATTERN.fullmatch(args.core_revision) is None:
        raise CampaignFailure("core revision은 40자리 소문자 commit hex여야 합니다.")
    hash_names = (
        "source_image_sha256",
        "source_example_sha256",
        "sink_image_sha256",
        "sink_example_sha256",
        "source_probe_sha256",
        "sink_probe_sha256",
    )
    if any(HASH_PATTERN.fullmatch(getattr(args, name)) is None for name in hash_names):
        raise CampaignFailure("SHA-256 인자 형식이 잘못되었습니다.")
    core_root = args.core_root.resolve()
    if not core_root.is_dir():
        raise CampaignFailure(f"Core root가 없습니다: {core_root}")
    source_image = verify_exact_file(
        args.source_image, args.source_image_sha256, "source image"
    )
    sink_image = verify_exact_file(args.sink_image, args.sink_image_sha256, "sink image")
    output_dir = args.output_dir.resolve()
    if output_dir.exists():
        raise CampaignFailure(f"기존 output directory를 덮어쓰지 않습니다: {output_dir}")
    return {
        "core_root": core_root,
        "source_image": source_image,
        "sink_image": sink_image,
        "output_dir": output_dir,
    }


def scenario_command(
    args: argparse.Namespace,
    tooling: dict[str, Any],
    paths: dict[str, Any],
    mode: str,
) -> tuple[str, ...]:
    """! @brief 한 mode의 완전한 exact runner 명령을 생성합니다. """
    output_dir: Path = paths["output_dir"]
    return (
        sys.executable,
        str(tooling["runner"]),
        mode,
        "--source-port",
        args.source_port,
        "--source-probe-sha256",
        args.source_probe_sha256,
        "--source-image",
        str(paths["source_image"]),
        "--source-image-sha256",
        args.source_image_sha256,
        "--source-example-sha256",
        args.source_example_sha256,
        "--source-flash-receipt",
        str(output_dir / f"{mode}-source-flash.json"),
        "--sink-port",
        args.sink_port,
        "--sink-probe-sha256",
        args.sink_probe_sha256,
        "--sink-image",
        str(paths["sink_image"]),
        "--sink-image-sha256",
        args.sink_image_sha256,
        "--sink-example-sha256",
        args.sink_example_sha256,
        "--sink-flash-receipt",
        str(output_dir / f"{mode}-sink-flash.json"),
        "--core-root",
        str(paths["core_root"]),
        "--core-revision",
        args.core_revision,
        "--cycles",
        "20",
        "--duration",
        "180",
        "--total-timeout",
        "180",
        "--recovery-timeout",
        "30",
        "--reset-timeout",
        "30",
        "--transcript",
        str(output_dir / f"{mode}.transcript.log"),
        "--summary",
        str(output_dir / f"{mode}.summary.json"),
        "--reset-helper",
        str(tooling["debug_helper"]),
        "--flash-helper",
        str(tooling["flash_helper"]),
    )


def write_summary(path: Path, document: dict[str, Any]) -> None:
    """! @brief campaign summary를 x-mode로 기록합니다. """
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(document, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def run_campaign(args: argparse.Namespace) -> int:
    """! @brief 다섯 mode를 순서대로 실행하고 top summary를 남깁니다. """
    tooling = verify_tooling(args)
    paths = require_run_arguments(args)
    campaign_path = Path(__file__).resolve()
    campaign_hash = sha256_file(campaign_path)
    output_dir: Path = paths["output_dir"]
    output_dir.mkdir(parents=True, exist_ok=False)
    started_at = utc_now()
    results: list[dict[str, Any]] = []
    status = "PASS"
    error_text: str | None = None
    for mode in MODES:
        command = scenario_command(args, tooling, paths, mode)
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="backslashreplace",
                timeout=SCENARIO_TIMEOUT_SECONDS,
                check=False,
            )
            output = completed.stdout + completed.stderr
            mode_status = "PASS" if completed.returncode == 0 else "FAIL"
            results.append(
                {
                    "mode": mode,
                    "status": mode_status,
                    "returncode": completed.returncode,
                    "summary": str(output_dir / f"{mode}.summary.json"),
                    "bounded_output": bounded_text(output),
                }
            )
            if completed.returncode != 0:
                status = "FAIL"
                error_text = f"{mode} runner 실패 rc={completed.returncode}"
                break
        except subprocess.TimeoutExpired:
            status = "FAIL"
            error_text = f"{mode} emergency outer timeout"
            results.append({"mode": mode, "status": "FAIL", "reason": error_text})
            break
    if sha256_file(campaign_path) != campaign_hash:
        status = "FAIL"
        error_text = "campaign 실행 중 script가 변경되었습니다."
    try:
        verify_tooling(args)
    except CampaignFailure as error:
        status = "FAIL"
        error_text = str(error)
    document = {
        "schema": "nucode.m31.pbp-campaign.v1",
        "status": status,
        "started_at": started_at,
        "finished_at": utc_now(),
        "core_revision": args.core_revision,
        "campaign": {"path": str(campaign_path), "sha256": campaign_hash},
        "runner": {
            "path": str(tooling["runner"]),
            "sha256": tooling["runner_sha256"],
        },
        "debug_helper": {
            "path": str(tooling["debug_helper"]),
            "sha256": tooling["debug_helper_sha256"],
        },
        "flash_helper": {
            "path": str(tooling["flash_helper"]),
            "sha256": tooling["flash_helper_sha256"],
        },
        "storage_erase": {"required": False, "reason": "PBP는 bond 저장소를 사용하지 않음"},
        "images": {
            "source": {
                "path": str(paths["source_image"]),
                "sha256": args.source_image_sha256,
            },
            "sink": {
                "path": str(paths["sink_image"]),
                "sha256": args.sink_image_sha256,
            },
        },
        "modes": list(MODES),
        "results": results,
        "error": error_text,
        "raw_probe_identifiers_recorded": False,
        "existing_files_overwritten": False,
    }
    write_summary(output_dir / "campaign.summary.json", document)
    print(
        f"M31_PBP_CAMPAIGN={status};MODES_COMPLETED={len(results)};"
        f"SUMMARY={output_dir / 'campaign.summary.json'}"
    )
    return 0 if status == "PASS" else 1


def main(arguments: Sequence[str] | None = None) -> int:
    """! @brief self-test 또는 full campaign을 실행합니다. """
    args = parse_arguments(arguments)
    if args.command == "self-test":
        return run_self_test(args)
    return run_campaign(args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CampaignFailure as error:
        print(f"M31_PBP_CAMPAIGN=FAIL;ERROR={bounded_text(str(error))}", file=sys.stderr)
        raise SystemExit(2) from error
