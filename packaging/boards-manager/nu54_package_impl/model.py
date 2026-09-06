"""! @brief 패키저의 고정 계약과 입력 자료형 책임입니다. """
from __future__ import annotations
from dataclasses import dataclass


LEGACY_PREVIEW_VERSIONS = ("0.0.90", "0.0.91", "0.0.92", "0.0.93")


## @brief 공개 byte를 유지하지만 M10 PASS 근거로 사용하지 않는 preview입니다.
FAILED_M10_PREVIEW_VERSIONS = ("0.0.94", "0.0.95")


## @brief 현재 immutable M10 lifecycle 검증에 사용할 preview 쌍입니다.
SAFE_PREVIEW_VERSIONS = ("0.0.96", "0.0.97")


SUPPORTED_VERSIONS = (
    LEGACY_PREVIEW_VERSIONS
    + FAILED_M10_PREVIEW_VERSIONS
    + SAFE_PREVIEW_VERSIONS
)


RELEASE_CANDIDATE_VERSIONS = (
    "0.1.0-rc.2",
    "0.2.0-rc.1",
    "0.2.0-rc.2",
    "0.3.0-rc.1",
    "0.3.0-rc.2",
    "0.3.0-rc.3",
)


STABLE_VERSIONS = ("0.1.0", "0.2.0", "0.3.0")


## @brief 이미 공개한 stable archive가 다른 source로 재생성되는 것을 막는 commit 계약입니다.
STABLE_RELEASE_COMMITS = {
    "0.1.0": "5dbc5e37270e477d21f578dd877f4b5226b44a0d",
    "0.2.0": "41fc44e452d2b6eef4b46307af6c277499f8d2d5",
    "0.3.0": "94ee3fec29ba9f86835b6cb3d96ab13ce2cf8c11",
}


## @brief 과거 패키지를 최신 허용목록으로 재해석하지 않고 공개 byte 그대로 검증합니다.
PUBLISHED_STABLE_ARCHIVE_IDENTITIES = {
    "0.1.0": {
        "size": 760412,
        "sha256": "722a46685b97aff42a75fb84db8ea74de75f3c32f59ea58225cd86d5acd141a6",
    },
    "0.2.0": {
        "size": 932376,
        "sha256": "1c2b4dddd6da0c1530f9d32630ec7d5b5285cff28c826a9a95c864226aeaea6e",
    },
    "0.3.0": {
        "size": 1660169,
        "sha256": "138740bcf6c458992fdb5c8eb81d6110d28b0baee18c68f5d8cb050e2e0e1ecc",
    },
}


PACKAGE_VERSIONS = SUPPORTED_VERSIONS + RELEASE_CANDIDATE_VERSIONS + STABLE_VERSIONS


WINDOWS_SAFE_VERSIONS = (
    FAILED_M10_PREVIEW_VERSIONS
    + SAFE_PREVIEW_VERSIONS
    + RELEASE_CANDIDATE_VERSIONS
    + STABLE_VERSIONS
)


VENDOR = "nucode"


ARCHITECTURE = "zephyr"


MAINTAINER = "NUCODE / Quantum"


CONTACT_EMAIL = "EIDOSDATA@users.noreply.github.com"


REPOSITORY_URL = "https://github.com/EIDOSDATA/NU54DK_Arduino_Core"


BOARD_REPOSITORY_URL = "https://github.com/Nucode01/NU54DK_Zephyr_DTS"


INDEX_FILENAME = "package_nucode_nu54dk_preview_index.json"


RC_INDEX_FILENAME = "package_nucode_nu54dk_rc_index.json"


STABLE_INDEX_FILENAME = "package_nucode_nu54dk_index.json"


LEGAL_REVIEW_REQUIRED = "required-before-final-public-release"


STABLE_LEGAL_REVIEW_STATUSES = {
    "0.1.0": "project-owner-approved-for-final-public-release",
    "0.2.0": "project-owner-approved-for-final-public-release",
    "0.3.0": "project-owner-approved-for-final-public-release",
}


NCS_VERSION = "v3.4.0"


NCS_REVISION = "99553055607b2e9885fbc80ccd11fa9da81c2df0"


ZEPHYR_VERSION = "4.4.0"


ZEPHYR_REVISION = "bf801e4e3d19e1ffa76164346480cb7734dd2800"


TOOLCHAIN_BUNDLE_ID = "dcbdc366a1"


ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


MAX_ARCHIVE_SIZE = 128 * 1024 * 1024


MAX_FILE_SIZE = 32 * 1024 * 1024


METADATA_FILES = (
    "release-manifest.json",
    "sbom.spdx.json",
    "license-inventory.json",
    "THIRD_PARTY_NOTICES.md",
    "CHECKSUMS.sha256",
)


class PackageError(RuntimeError):
    """! @brief 안전하게 계속할 수 없는 패키징 오류입니다. """


@dataclass(frozen=True)
class SourceFile:
    """! @brief Git 입력과 패키지 byte 사이의 출처를 보존합니다. """

    path: str
    data: bytes
    mode: int
    origin: str
    git_object: str
    transformation: str | None = None
