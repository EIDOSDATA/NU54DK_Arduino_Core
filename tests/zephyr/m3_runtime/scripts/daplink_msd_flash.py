"""NU54DK DAPLink MSD에 Twister 산출물을 기록하는 사용자 지정 flash 명령입니다."""

from __future__ import annotations

import argparse
import re
import shutil
import string
import sys
import time
from pathlib import Path


def parse_arguments() -> argparse.Namespace:
    """Twister가 전달하는 build 경로와 probe 식별자를 해석합니다."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--build-dir", required=True)
    parser.add_argument("--board-id")
    return parser.parse_args()


def read_details(root: Path) -> str | None:
    """DAPLink DETAILS.TXT를 읽고 일시적인 remount 오류는 후보 제외로 처리합니다."""

    try:
        return (root / "DETAILS.TXT").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def detail_value(details: str, key: str) -> str | None:
    """DETAILS.TXT의 단일 key 값을 반환합니다."""

    match = re.search(rf"^{re.escape(key)}:\s*(.+?)\s*$", details, re.MULTILINE)
    return match.group(1) if match else None


def find_daplink_volume(board_id: str | None) -> tuple[Path, str]:
    """드라이브 문자를 고정하지 않고 대상 NU54DK DAPLink 볼륨을 찾습니다."""

    expected_id = board_id.lower() if board_id and board_id.lower() != "none" else None
    candidates: list[tuple[Path, str]] = []

    for letter in string.ascii_uppercase:
        root = Path(f"{letter}:/")
        details = read_details(root)
        if details is None or detail_value(details, "Target Detect") != "nRF54L15":
            continue

        unique_id = detail_value(details, "Unique ID")
        if expected_id is not None and (unique_id is None or unique_id.lower() != expected_id):
            continue

        candidates.append((root, details))

    if len(candidates) != 1:
        raise RuntimeError(
            f"일치하는 NU54DK DAPLink 볼륨이 정확히 하나여야 합니다. 발견={len(candidates)}"
        )

    return candidates[0]


def wait_for_flash_result(root: Path, previous_sequence: str | None) -> str:
    """DAPLink remount와 flash 완료를 기다리고 SUCCESS 결과를 검증합니다."""

    deadline = time.monotonic() + 45.0
    latest_details: str | None = None

    while time.monotonic() < deadline:
        latest_details = read_details(root)
        if latest_details is not None:
            result = detail_value(latest_details, "Last Flash Result")
            sequence = detail_value(latest_details, "Flash Sequence")
            sequence_changed = previous_sequence is None or sequence != previous_sequence
            if sequence_changed and result == "SUCCESS":
                return latest_details
            if sequence_changed and result not in (None, "NONE", "SUCCESS"):
                error = detail_value(latest_details, "Last Flash Error") or "알 수 없음"
                raise RuntimeError(f"DAPLink flash 실패: {result}, {error}")

        time.sleep(0.2)

    raise RuntimeError("DAPLink flash 완료를 45초 안에 확인하지 못했습니다.")


def main() -> int:
    """Twister image를 flash하고 DAPLink가 보고한 결과를 반환합니다."""

    arguments = parse_arguments()
    build_directory = Path(arguments.build_dir).resolve()
    image = build_directory / "zephyr" / "zephyr.hex"
    if not image.is_file():
        sysbuild_images = sorted(build_directory.glob("*/zephyr/zephyr.hex"))
        if len(sysbuild_images) != 1:
            raise FileNotFoundError(
                f"Twister HEX가 정확히 하나여야 합니다: 직접={image}, sysbuild={sysbuild_images}"
            )
        image = sysbuild_images[0]

    root, details = find_daplink_volume(arguments.board_id)
    previous_sequence = detail_value(details, "Flash Sequence")
    destination = root / "NUCODE.HEX"

    shutil.copyfile(image, destination)
    result_details = wait_for_flash_result(root, previous_sequence)

    unique_id = detail_value(result_details, "Unique ID") or "unknown"
    byte_count = detail_value(result_details, "Last Flash Bytes") or "unknown"
    sequence = detail_value(result_details, "Flash Sequence") or "unknown"
    print(f"DAPLink flash SUCCESS: uid={unique_id}, bytes={byte_count}, sequence={sequence}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print(f"DAPLink flash ERROR: {error}", file=sys.stderr)
        sys.exit(1)
