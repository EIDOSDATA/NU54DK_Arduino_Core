"""! @brief 패키저의 입력·생성·검증 orchestration 책임입니다. """
from __future__ import annotations
from . import model
from pathlib import Path, PurePosixPath
from .archive import (
    write_deterministic_zip,
    write_external_checksums,
)
from .inputs import (
    collect_source_files,
    commit_timestamp,
    resolve_commit,
)
from .licenses import (
    build_external_prerequisites,
    build_license_inventory,
    build_third_party_notices,
)
from .manifest import (
    build_release_manifest,
)
from .model import (
    PackageError,
    STABLE_RELEASE_COMMITS,
)
from .sbom import (
    build_spdx,
)
from .serialization import (
    build_internal_checksums,
    canonical_json,
)
from .validation import (
    validate_archive,
)


## @brief 지정 commit에서 Boards Manager archive와 provenance sidecar를 만듭니다.
def build_package(repo_root: Path, output_dir: Path, version: str, revision: str) -> dict[str, Path]:
    if version not in model.PACKAGE_VERSIONS:
        raise PackageError(f"지원하는 package version이 아닙니다: {version}")
    repo_root = repo_root.resolve()
    output_dir = output_dir.resolve()
    commit = resolve_commit(repo_root, revision)
    stable_commit = STABLE_RELEASE_COMMITS.get(version)
    if stable_commit is not None:
        tooling_commit = resolve_commit(repo_root, "HEAD")
        if commit != stable_commit or tooling_commit != stable_commit:
            raise PackageError(
                f"공개 stable {version}은 source와 패키징 도구를 모두 고정 commit "
                f"{stable_commit}에서 실행해야 합니다: source={commit}, tooling={tooling_commit}"
            )
    created = commit_timestamp(repo_root, commit)
    source_files, board_revision = collect_source_files(repo_root, commit, version)
    release_manifest = build_release_manifest(source_files, version, commit, board_revision)
    license_inventory = build_license_inventory(source_files, version, board_revision)
    external_prerequisites = build_external_prerequisites(source_files, version)
    spdx = build_spdx(source_files, version, commit, created, external_prerequisites)

    archive_files: dict[str, tuple[bytes, int]] = {
        item.path: (item.data, item.mode) for item in source_files
    }
    metadata_bytes = {
        "release-manifest.json": canonical_json(release_manifest),
        "sbom.spdx.json": canonical_json(spdx),
        "license-inventory.json": canonical_json(license_inventory),
        "THIRD_PARTY_NOTICES.md": build_third_party_notices(board_revision),
    }
    archive_files.update({path: (data, 0o644) for path, data in metadata_bytes.items()})
    archive_files["CHECKSUMS.sha256"] = (build_internal_checksums(archive_files), 0o644)

    output_dir.mkdir(parents=True, exist_ok=True)
    base = f"nucode-nu54dk-zephyr-{version}"
    archive_path = output_dir / f"{base}.zip"
    write_deterministic_zip(archive_path, base, archive_files)
    sidecars = {
        "manifest": output_dir / f"{base}.release-manifest.json",
        "sbom": output_dir / f"{base}.spdx.json",
        "licenses": output_dir / f"{base}.license-inventory.json",
        "notices": output_dir / f"{base}.THIRD_PARTY_NOTICES.md",
    }
    sidecars["manifest"].write_bytes(metadata_bytes["release-manifest.json"])
    sidecars["sbom"].write_bytes(metadata_bytes["sbom.spdx.json"])
    sidecars["licenses"].write_bytes(metadata_bytes["license-inventory.json"])
    sidecars["notices"].write_bytes(metadata_bytes["THIRD_PARTY_NOTICES.md"])
    checksums = output_dir / f"{base}.CHECKSUMS.sha256"
    write_external_checksums([archive_path, *sidecars.values()], checksums)
    paths = {"archive": archive_path, "checksums": checksums, **sidecars}
    validate_archive(archive_path, expected_version=version, expected_commit=commit)
    return paths
