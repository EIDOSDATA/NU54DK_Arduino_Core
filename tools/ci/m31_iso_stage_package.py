#!/usr/bin/env python3
"""! @brief clean Git source를 독립 Arduino Sketchbook package로 복사합니다. """

from __future__ import annotations

from argparse import ArgumentParser
from pathlib import Path
import hashlib
import json
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packaging" / "boards-manager"))
from nu54_package_impl.inputs import collect_source_files  # noqa: E402
from nu54_package_impl import model as package_model  # noqa: E402


## @brief 배포 대상 파일의 현재 clean checkout byte를 독립 디렉터리에 복사합니다.
def main() -> int:
    parser = ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--downloads-dir", required=True, type=Path)
    args = parser.parse_args()
    destination = args.root.resolve()
    if destination.exists() or destination.is_relative_to(ROOT):
        parser.error("새 저장소 외부 staging root가 필요합니다")
    dirty = subprocess.check_output(("git", "status", "--porcelain"),
                                    cwd=ROOT, text=True).strip()
    if dirty:
        parser.error("clean Git source가 필요합니다")
    revision = subprocess.check_output(("git", "rev-parse", "HEAD"),
                                       cwd=ROOT, text=True).strip()
    selected, board_revision = collect_source_files(ROOT, revision, "0.4.1-dev")
    board_root = ROOT / "board_package" / "NU54DK_Zephyr_DTS"
    actual_board = subprocess.check_output(("git", "rev-parse", "HEAD"),
                                           cwd=board_root, text=True).strip()
    if actual_board != board_revision:
        raise RuntimeError("board submodule checkout이 고정 gitlink와 다릅니다")
    platform = destination / "user" / "hardware" / "nucode" / "zephyr"
    digest = hashlib.sha256()
    total_bytes = 0
    file_hashes: dict[str, str] = {}
    for item in selected:
        source = ROOT / item.path
        if not source.is_file() or source.is_symlink():
            raise RuntimeError(f"source file이 없습니다: {item.path}")
        data = source.read_bytes()
        target = platform / item.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        digest.update(item.path.encode("utf-8") + b"\0")
        file_digest = hashlib.sha256(data).digest()
        digest.update(file_digest)
        file_hashes[item.path] = file_digest.hex()
        total_bytes += len(data)
    runtime_manifest = {
        "schema_version": 1,
        "package_name": "NUCODE NU54DK Zephyr Boards",
        "version": "0.4.1-dev",
        "staging_type": "unpublished_clean_development_checkout",
        "core_revision": revision,
        "board_revision": board_revision,
        "ncs_version": package_model.NCS_VERSION,
        "ncs_revision": package_model.NCS_REVISION,
        "zephyr_version": package_model.ZEPHYR_VERSION,
        "zephyr_revision": package_model.ZEPHYR_REVISION,
        "toolchain_bundle_id": package_model.TOOLCHAIN_BUNDLE_ID,
        "prerequisites_pins_sha256": file_hashes[
            "tools/nu54-prerequisites/pins.json"],
        "file_count": len(selected),
        "total_size": total_bytes,
        "file_hashes": file_hashes,
    }
    (platform / "release-manifest.json").write_text(
        json.dumps(runtime_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    config = destination / "arduino-cli.yaml"
    config.write_text(
        "directories:\n"
        f"  data: {args.data_dir.resolve().as_posix()}\n"
        f"  downloads: {args.downloads_dir.resolve().as_posix()}\n"
        f"  user: {(destination / 'user').as_posix()}\n",
        encoding="utf-8",
    )
    manifest = {
        "core_revision": revision,
        "board_revision": board_revision,
        "source_clean": True,
        "staging_type": "independent_clean_checkout_platform_files",
        "file_count": len(selected),
        "file_bytes": total_bytes,
        "file_tree_sha256": digest.hexdigest(),
        "arduino_config_sha256": hashlib.sha256(config.read_bytes()).hexdigest(),
        "platform_is_symlink": platform.is_symlink(),
    }
    (destination / "staging.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if platform.resolve().is_relative_to(ROOT) or manifest["platform_is_symlink"]:
        raise RuntimeError("staged platform이 저장소를 가리킵니다")
    print(f"M31_ISO_STAGE=PASS;FILES={len(selected)};CORE={revision}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
