#!/usr/bin/env python3
"""! @brief 고정 SDK에 승인된 upstream patch를 build 동안만 적용합니다. """

from __future__ import annotations

from contextlib import contextmanager
import hashlib
from pathlib import Path
import re
import subprocess
from typing import Any, Iterator, Sequence


REPOSITORY = Path(__file__).resolve().parents[4]
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
REVISION = re.compile(r"[0-9a-f]{40}\Z")

RUNTIME_ZEPHYR_LOCK = {
    "patches": [
        {
            "applies_to_revision": "bf801e4e3d19e1ffa76164346480cb7734dd2800",
            "files": [
                "subsys/bluetooth/mesh/friend.c",
                "subsys/bluetooth/mesh/lpn.h",
                "subsys/bluetooth/mesh/net.h",
                "subsys/bluetooth/mesh/transport.c",
            ],
            "path": (
                "tools/nu54-builder/sdk-patches/zephyr/"
                "3564414a3b27-friend-clear-confirm.patch"
            ),
            "sha256": (
                "5b63939ee86d71e0e43da84ca61dccb2c2dce2691e1370eaa49c8224c16bcd65"
            ),
            "upstream_repository": "https://github.com/zephyrproject-rtos/zephyr",
            "upstream_revision": "3564414a3b27ae52718efe5244261ebd00102f56",
        }
    ],
    "repository": "https://github.com/nrfconnect/sdk-zephyr",
    "revision": "bf801e4e3d19e1ffa76164346480cb7734dd2800",
    "version": "4.4.0",
}


class PatchFailure(RuntimeError):
    """! @brief SDK patch 계약 위반을 나타냅니다. """


def file_sha256(path: Path) -> str:
    """! @brief 파일 byte의 SHA-256을 반환합니다. """

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _git(repository: Path, arguments: Sequence[str], *, check: bool = True) -> str:
    """! @brief Git 명령을 shell 없이 실행하고 UTF-8 출력을 반환합니다. """

    try:
        result = subprocess.run(
            ("git", "-C", str(repository), *arguments),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError as error:
        raise PatchFailure(f"Git 실행에 실패했습니다: {repository}: {error}") from error
    if check and result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise PatchFailure(
            f"Git 명령이 실패했습니다: {subprocess.list2cmdline(result.args)}: {detail}"
        )
    return result.stdout.strip()


def _content_changes(repository: Path) -> tuple[str, ...]:
    """! @brief 줄바꿈 stat 오판을 제외한 staged·tracked·untracked 변경을 반환합니다. """

    paths: set[str] = set()
    commands = (
        ("diff", "--name-only", "--diff-filter=ACMDRTUXB"),
        ("diff", "--cached", "--name-only", "--diff-filter=ACMDRTUXB"),
        ("ls-files", "--others", "--exclude-standard"),
    )
    for command in commands:
        paths.update(item for item in _git(repository, command).splitlines() if item)
    return tuple(sorted(paths))


def _restore_original_bytes(repository: Path, originals: dict[str, bytes]) -> None:
    """! @brief patch 대상 파일을 적용 전 byte와 정확히 같은 상태로 복원합니다. """

    for relative, content in originals.items():
        path = repository / relative
        if not path.is_file():
            raise PatchFailure(f"Zephyr patch 원본 파일이 없습니다: {relative}")
        if path.read_bytes() != content:
            path.write_bytes(content)


def patchset_sha256(records: Sequence[dict[str, Any]]) -> str:
    """! @brief 순서가 고정된 patch byte SHA 집합의 결합 SHA-256을 반환합니다. """

    joined = "".join(str(record["sha256"]) for record in records)
    return hashlib.sha256(joined.encode("ascii")).hexdigest()


def approved_zephyr_patches(lock: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    """! @brief lock에 고정된 Zephyr patch descriptor와 실제 byte를 검증합니다. """

    zephyr = lock.get("zephyr")
    if not isinstance(zephyr, dict):
        raise PatchFailure("Zephyr lock object가 없습니다")
    raw = zephyr.get("patches", [])
    if not isinstance(raw, list):
        raise PatchFailure("Zephyr patch 목록이 배열이 아닙니다")
    records: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    for descriptor in raw:
        if not isinstance(descriptor, dict):
            raise PatchFailure("Zephyr patch descriptor가 object가 아닙니다")
        required = {
            "path",
            "sha256",
            "upstream_repository",
            "upstream_revision",
            "applies_to_revision",
            "files",
        }
        if set(descriptor) != required:
            raise PatchFailure("Zephyr patch descriptor 필드가 고정 계약과 다릅니다")
        relative = descriptor["path"]
        digest = descriptor["sha256"]
        upstream = descriptor["upstream_revision"]
        applies_to = descriptor["applies_to_revision"]
        files = descriptor["files"]
        if (
            not isinstance(relative, str)
            or not relative.startswith("tools/nu54-builder/sdk-patches/zephyr/")
            or Path(relative).is_absolute()
            or ".." in Path(relative).parts
            or relative in seen_paths
        ):
            raise PatchFailure(f"Zephyr patch 경로가 잘못됐습니다: {relative}")
        if not isinstance(digest, str) or SHA256.fullmatch(digest) is None:
            raise PatchFailure(f"Zephyr patch SHA-256이 잘못됐습니다: {relative}")
        if not isinstance(upstream, str) or REVISION.fullmatch(upstream) is None:
            raise PatchFailure(f"Zephyr upstream revision이 잘못됐습니다: {relative}")
        if applies_to != zephyr.get("revision"):
            raise PatchFailure(f"Zephyr patch base revision이 lock과 다릅니다: {relative}")
        if descriptor["upstream_repository"] != "https://github.com/zephyrproject-rtos/zephyr":
            raise PatchFailure(f"Zephyr patch upstream이 공식 저장소가 아닙니다: {relative}")
        if (
            not isinstance(files, list)
            or not files
            or len(set(files)) != len(files)
            or not all(
                isinstance(item, str)
                and item.startswith("subsys/bluetooth/mesh/")
                and ".." not in Path(item).parts
                for item in files
            )
        ):
            raise PatchFailure(f"Zephyr patch 대상 파일이 잘못됐습니다: {relative}")
        path = (REPOSITORY / relative).resolve()
        if not path.is_file() or not path.is_relative_to(REPOSITORY.resolve()):
            raise PatchFailure(f"Zephyr patch 파일이 없습니다: {relative}")
        if file_sha256(path) != digest:
            raise PatchFailure(f"Zephyr patch byte가 lock과 다릅니다: {relative}")
        seen_paths.add(relative)
        records.append(
            {
                "path": relative,
                "sha256": digest,
                "upstream_repository": descriptor["upstream_repository"],
                "upstream_revision": upstream,
                "applies_to_revision": applies_to,
                "files": list(files),
            }
        )
    return tuple(records)


@contextmanager
def applied_zephyr_patches(
    workspace: Path, lock: dict[str, Any]
) -> Iterator[tuple[dict[str, Any], ...]]:
    """! @brief clean Zephyr checkout에 patch를 적용하고 종료 시 원상복구합니다. """

    records = approved_zephyr_patches(lock)
    if not records:
        yield records
        return
    zephyr = workspace.resolve() / "zephyr"
    expected_revision = str(lock["zephyr"]["revision"])
    if _git(zephyr, ("rev-parse", "HEAD")) != expected_revision:
        raise PatchFailure("Zephyr patch 대상 revision이 lock과 다릅니다")
    if _content_changes(zephyr):
        raise PatchFailure("Zephyr patch는 clean exact checkout에만 적용할 수 있습니다")
    originals = {
        relative: (zephyr / relative).read_bytes()
        for relative in sorted(
            {item for record in records for item in record["files"]}
        )
    }
    applied: list[dict[str, Any]] = []
    cleanup_error: Exception | None = None
    try:
        for record in records:
            patch = (REPOSITORY / record["path"]).resolve()
            _git(zephyr, ("apply", "--check", "--whitespace=error-all", str(patch)))
            _git(zephyr, ("apply", "--whitespace=error-all", str(patch)))
            applied.append(record)
        changed = set(
            _git(zephyr, ("diff", "--name-only", "--diff-filter=ACMRT")).splitlines()
        )
        expected = {item for record in records for item in record["files"]}
        if changed != expected:
            raise PatchFailure(
                f"Zephyr patch 대상 파일 집합이 다릅니다: {sorted(changed)} != {sorted(expected)}"
            )
        yield records
    finally:
        for record in reversed(applied):
            patch = (REPOSITORY / record["path"]).resolve()
            try:
                _git(zephyr, ("apply", "--check", "--reverse", str(patch)))
                _git(zephyr, ("apply", "--reverse", str(patch)))
            except Exception as error:
                cleanup_error = error
                break
        try:
            _restore_original_bytes(zephyr, originals)
        except Exception as error:
            if cleanup_error is None:
                cleanup_error = error
            else:
                cleanup_error = PatchFailure(
                    f"{cleanup_error}; 원본 byte 복원 실패: {error}"
                )
        if cleanup_error is None:
            try:
                if _content_changes(zephyr):
                    cleanup_error = PatchFailure(
                        "Zephyr patch 원상복구 뒤 checkout이 clean하지 않습니다"
                    )
            except Exception as error:
                cleanup_error = error
        if cleanup_error is not None:
            raise PatchFailure(
                f"Zephyr patch 원상복구에 실패했습니다: {cleanup_error}"
            ) from cleanup_error
