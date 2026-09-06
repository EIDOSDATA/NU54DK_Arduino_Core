"""! @brief 패키저의 runtime manifest 생성 책임입니다. """
from __future__ import annotations
from . import model
from typing import Any, Iterable
from .channels import (
    archive_filename,
    release_asset_url,
    release_tag,
)
from .model import (
    ARCHITECTURE,
    BOARD_REPOSITORY_URL,
    METADATA_FILES,
    NCS_REVISION,
    NCS_VERSION,
    PackageError,
    REPOSITORY_URL,
    SourceFile,
    TOOLCHAIN_BUNDLE_ID,
    VENDOR,
    ZEPHYR_REVISION,
    ZEPHYR_VERSION,
)
from .serialization import (
    runtime_payload_sha256,
    sha256_bytes,
)


## @brief release-manifest 계약과 전체 source hash 목록을 생성합니다.
def build_release_manifest(
    files: list[SourceFile], version: str, commit: str, board_revision: str
) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    file_hashes: dict[str, str] = {}
    for item in files:
        digest = sha256_bytes(item.data)
        entry: dict[str, Any] = {
            "git_object": item.git_object,
            "mode": f"{item.mode:04o}",
            "origin": item.origin,
            "path": item.path,
            "sha256": digest,
            "size": len(item.data),
        }
        if item.transformation:
            entry["transformation"] = item.transformation
        entries.append(entry)
        file_hashes[item.path] = digest
    root = f"nucode-nu54dk-zephyr-{version}"
    pins = next(
        (item for item in files if item.path == "tools/nu54-prerequisites/pins.json"), None
    )
    if pins is None:
        raise PackageError("prerequisite pin 파일이 패키지 입력에 없습니다.")
    manifest = {
        "schema_version": 1,
        "package_name": "NUCODE NU54DK Zephyr Boards",
        "vendor": VENDOR,
        "architecture": ARCHITECTURE,
        "version": version,
        "archive_root": root,
        "archive_file_name": archive_filename(version),
        "release_tag": release_tag(version),
        "release_url": release_asset_url(version, archive_filename(version)),
        "source_repository": REPOSITORY_URL,
        "core_revision": commit,
        "board_repository": BOARD_REPOSITORY_URL,
        "board_revision": board_revision,
        "ncs_version": NCS_VERSION,
        "ncs_revision": NCS_REVISION,
        "zephyr_version": ZEPHYR_VERSION,
        "zephyr_revision": ZEPHYR_REVISION,
        "toolchain_bundle_id": TOOLCHAIN_BUNDLE_ID,
        "prerequisites_pins_sha256": sha256_bytes(pins.data),
        "source_policy": (
            "exact-commit-plus-declared-platform-version-and-windows-crlf-rewrites"
            if version in model.WINDOWS_SAFE_VERSIONS
            else "exact-commit-plus-declared-platform-version-rewrite"
        ),
        "generated_metadata": list(METADATA_FILES),
        "file_count": len(entries),
        "total_size": sum(entry["size"] for entry in entries),
        "files": entries,
        "file_hashes": file_hashes,
    }
    if version in model.WINDOWS_SAFE_VERSIONS:
        manifest["runtime_payload_sha256"] = runtime_payload_sha256(
            (item.path, item.data, item.mode) for item in files
        )
    return manifest
