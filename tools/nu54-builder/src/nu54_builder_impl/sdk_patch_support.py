"""! @brief 설치 Core의 고정 SDK patch 계약을 build adapter에 연결합니다. """

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .common import AdapterError
from . import sdk_patches


def _lock() -> dict[str, Any]:
    """! @brief 배포 builder에 내장된 Zephyr patch 계약을 반환합니다. """

    return {"zephyr": sdk_patches.RUNTIME_ZEPHYR_LOCK}


def _validate_platform_root(platform_root: Path) -> None:
    """! @brief 실행 중인 manager와 요청한 설치 Core가 같은 root인지 검증합니다. """

    actual = platform_root.resolve()
    expected = sdk_patches.REPOSITORY.resolve()
    if actual != expected:
        raise AdapterError(
            "[NU54:E_SDK_PATCH] SDK patch manager가 다른 설치 Core에서 로드됐습니다: "
            f"{expected} != {actual}"
        )


def patchset_sha256(platform_root: Path) -> str:
    """! @brief 설치 Core의 검증된 Zephyr patch 집합 SHA-256을 반환합니다. """

    _validate_platform_root(platform_root)
    records = sdk_patches.approved_zephyr_patches(_lock())
    return str(sdk_patches.patchset_sha256(records))


def patch_environment(platform_root: Path) -> dict[str, str]:
    """! @brief CMake provenance에 전달할 SDK patch 환경을 반환합니다. """

    return {"NUCODE_ZEPHYR_PATCHSET_SHA256": patchset_sha256(platform_root)}


@contextmanager
def applied_sdk_patches(
    platform_root: Path,
    zephyr_base: Path,
    environment: dict[str, str],
) -> Iterator[tuple[dict[str, Any], ...]]:
    """! @brief 한 adapter build 명령 범위에서 SDK patch를 적용하고 복구합니다. """

    _validate_platform_root(platform_root)
    lock = _lock()
    records = sdk_patches.approved_zephyr_patches(lock)
    expected = str(sdk_patches.patchset_sha256(records))
    if environment.get("NUCODE_ZEPHYR_PATCHSET_SHA256") != expected:
        raise AdapterError("[NU54:E_SDK_PATCH] build 환경의 patch 집합이 lock과 다릅니다")
    if environment.get("NUCODE_ZEPHYR_PATCHES_APPLIED") == "1":
        actual = set(sdk_patches._content_changes(zephyr_base.resolve()))
        expected_files = {
            path for record in records for path in record["files"]
        }
        if actual != expected_files:
            raise AdapterError(
                "[NU54:E_SDK_PATCH] 상위 builder의 patch 파일 집합이 lock과 다릅니다"
            )
        yield records
        return
    try:
        with sdk_patches.applied_zephyr_patches(
            zephyr_base.resolve().parent, lock
        ) as applied:
            yield applied
    except sdk_patches.PatchFailure as error:
        raise AdapterError(f"[NU54:E_SDK_PATCH] {error}") from error
