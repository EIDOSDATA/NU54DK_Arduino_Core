"""! @brief 패키저의 불변 release channel·identity 판정 책임입니다. """
from __future__ import annotations
from . import model
import re
from .model import (
    LEGAL_REVIEW_REQUIRED,
    PackageError,
    REPOSITORY_URL,
    STABLE_LEGAL_REVIEW_STATUSES,
    STABLE_VERSIONS,
    SUPPORTED_VERSIONS,
)


## @brief 패키지 버전에 대응하는 프로젝트 법률 검토 상태를 반환합니다.
def legal_review_status(version: str) -> str:
    if version in SUPPORTED_VERSIONS or version in model.RELEASE_CANDIDATE_VERSIONS:
        return LEGAL_REVIEW_REQUIRED
    if version in STABLE_VERSIONS:
        status = STABLE_LEGAL_REVIEW_STATUSES.get(version)
        if status:
            return status
    raise PackageError(f"법률 검토 상태가 승인되지 않은 패키지 버전입니다: {version}")


## @brief release asset 이름을 고정합니다.
def archive_filename(version: str) -> str:
    return f"nucode-nu54dk-zephyr-{version}.zip"


## @brief 패키지 버전의 배포 채널을 fail-closed 방식으로 판별합니다.
def release_channel(version: str) -> str:
    if version in SUPPORTED_VERSIONS:
        return "preview"
    if version in model.RELEASE_CANDIDATE_VERSIONS:
        return "release-candidate"
    if version in STABLE_VERSIONS:
        return "stable"
    raise PackageError(f"지원하지 않는 패키지 버전입니다: {version}")


## @brief Arduino package version을 최신 순으로 정렬할 key를 만듭니다.
def version_sort_key(version: str) -> tuple[int, int, int, int, int]:
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(?:-rc\.(\d+))?", version)
    if not match or version not in model.PACKAGE_VERSIONS:
        raise PackageError(f"지원하지 않는 패키지 버전입니다: {version}")
    major, minor, patch, rc = match.groups()
    ## @note 같은 기본 버전에서는 stable을 RC보다 최신으로 정렬합니다.
    return (int(major), int(minor), int(patch), 1 if rc is None else 0, int(rc or 0))


## @brief preview와 공개 버전의 tag 이름을 서로 분리해 고정합니다.
def release_tag(version: str) -> str:
    channel = release_channel(version)
    if channel == "preview":
        return f"m10-preview-{version}"
    return f"v{version}"


## @brief 공개 GitHub Release asset URL을 만듭니다.
def release_asset_url(version: str, filename: str) -> str:
    return f"{REPOSITORY_URL}/releases/download/{release_tag(version)}/{filename}"
