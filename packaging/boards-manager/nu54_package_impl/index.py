"""! @brief 패키저의 Boards Manager index 생성·검증 책임입니다. """
from __future__ import annotations
from . import model
from pathlib import Path, PurePosixPath
from typing import Any, Iterable
import re
from .channels import (
    archive_filename,
    release_asset_url,
    release_channel,
    release_tag,
    version_sort_key,
)
from .model import (
    ARCHITECTURE,
    CONTACT_EMAIL,
    INDEX_FILENAME,
    MAINTAINER,
    PackageError,
    RC_INDEX_FILENAME,
    REPOSITORY_URL,
    STABLE_INDEX_FILENAME,
    VENDOR,
)
from .serialization import (
    canonical_json,
    sha256_bytes,
    strict_json_loads,
)
from .validation import (
    validate_index_archive,
)


## @brief 로컬 archive들을 읽어 공식 Arduino package index를 생성합니다.
def generate_index(output_dir: Path, versions: list[str], destination: Path | None = None) -> Path:
    output_dir = output_dir.resolve()
    if not versions or any(version not in model.PACKAGE_VERSIONS for version in versions):
        raise PackageError("index에는 지원하는 package version을 하나 이상 지정해야 합니다.")
    channels = {release_channel(version) for version in versions}
    if len(channels) != 1:
        raise PackageError("서로 다른 배포 채널은 하나의 index에 혼합할 수 없습니다.")
    normalized_versions = sorted(set(versions), key=version_sort_key, reverse=True)
    platforms: list[dict[str, Any]] = []
    for version in normalized_versions:
        archive_path = output_dir / archive_filename(version)
        validate_index_archive(archive_path, version)
        platforms.append(
            {
                "name": "NUCODE NU54DK Zephyr Boards",
                "architecture": ARCHITECTURE,
                "version": version,
                "category": "Contributed",
                "url": release_asset_url(version, archive_path.name),
                "archiveFileName": archive_path.name,
                "checksum": f"SHA-256:{sha256_bytes(archive_path.read_bytes())}",
                "size": str(archive_path.stat().st_size),
                "boards": [{"name": "NU54DK (nRF54L15, Zephyr)"}],
                "help": {"online": f"{REPOSITORY_URL}/tree/{release_tag(version)}"},
                "toolsDependencies": [],
            }
        )
    document = {
        "packages": [
            {
                "name": VENDOR,
                "maintainer": MAINTAINER,
                "websiteURL": REPOSITORY_URL,
                "email": CONTACT_EMAIL,
                "help": {"online": f"{REPOSITORY_URL}/issues"},
                "platforms": platforms,
                "tools": [],
            }
        ]
    }
    channel = next(iter(channels))
    default_name = {
        "preview": INDEX_FILENAME,
        "release-candidate": RC_INDEX_FILENAME,
        "stable": STABLE_INDEX_FILENAME,
    }[channel]
    path = destination.resolve() if destination else output_dir / default_name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json(document))
    validate_index(path, artifact_dir=output_dir)
    return path


## @brief Arduino package index identity, URL, checksum, local artifact 일치를 검증합니다.
def validate_index(index_path: Path, *, artifact_dir: Path | None = None) -> dict[str, Any]:
    document = strict_json_loads(index_path.read_bytes(), source=index_path.name)
    if not isinstance(document, dict) or set(document) != {"packages"}:
        raise PackageError("package index 최상위 schema가 유효하지 않습니다.")
    packages = document.get("packages")
    if not isinstance(packages, list) or len(packages) != 1 or not isinstance(packages[0], dict):
        raise PackageError("package index에는 package가 정확히 하나 있어야 합니다.")
    package = packages[0]
    expected_identity = {
        "name": VENDOR,
        "maintainer": MAINTAINER,
        "websiteURL": REPOSITORY_URL,
        "email": CONTACT_EMAIL,
    }
    for field, expected in expected_identity.items():
        if package.get(field) != expected:
            raise PackageError(f"package index identity {field}가 고정값과 다릅니다.")
    if package.get("tools") != []:
        raise PackageError("package index는 NCS/toolchain을 재배포하는 tools 항목을 포함하지 않습니다.")
    platforms = package.get("platforms")
    if not isinstance(platforms, list) or not platforms:
        raise PackageError("package index platforms가 비어 있습니다.")
    versions: list[str] = []
    for platform in platforms:
        if not isinstance(platform, dict):
            raise PackageError("package index platform record가 object가 아닙니다.")
        version = platform.get("version")
        if version not in model.PACKAGE_VERSIONS or version in versions:
            raise PackageError(f"package index version이 유효하지 않습니다: {version}")
        versions.append(version)
        filename = archive_filename(version)
        fixed = {
            "name": "NUCODE NU54DK Zephyr Boards",
            "architecture": ARCHITECTURE,
            "category": "Contributed",
            "archiveFileName": filename,
            "url": release_asset_url(version, filename),
        }
        for field, expected in fixed.items():
            if platform.get(field) != expected:
                raise PackageError(f"package index platform {field}가 고정값과 다릅니다.")
        if platform.get("toolsDependencies") != []:
            raise PackageError("toolsDependencies에는 공개 재배포하지 않는 NCS/toolchain을 넣을 수 없습니다.")
        checksum = platform.get("checksum")
        size = platform.get("size")
        if not isinstance(checksum, str) or not re.fullmatch(r"SHA-256:[0-9a-f]{64}", checksum):
            raise PackageError("package index checksum이 SHA-256 형식이 아닙니다.")
        if not isinstance(size, str) or not re.fullmatch(r"[1-9][0-9]*", size):
            raise PackageError("package index size가 10진 문자열이 아닙니다.")
        if artifact_dir:
            archive_path = artifact_dir.resolve() / filename
            validate_index_archive(archive_path, version)
            if checksum != f"SHA-256:{sha256_bytes(archive_path.read_bytes())}":
                raise PackageError(f"package index와 archive checksum이 다릅니다: {version}")
            if size != str(archive_path.stat().st_size):
                raise PackageError(f"package index와 archive size가 다릅니다: {version}")
    channels = {release_channel(version) for version in versions}
    if len(channels) != 1:
        raise PackageError("서로 다른 배포 채널이 하나의 index에 혼합되었습니다.")
    expected_order = sorted(versions, key=version_sort_key, reverse=True)
    if versions != expected_order:
        raise PackageError("package index version은 최신 순서여야 합니다.")
    return document
