"""! @brief 패키저의 순수 JSON·checksum·payload codec 책임입니다. """
from __future__ import annotations
from typing import Any, Iterable
import hashlib
import json
import re
from .inputs import (
    ensure_safe_relative_path,
)
from .model import (
    PackageError,
)


## @brief JSON을 중복 key 없이 읽습니다.
def strict_json_loads(data: bytes | str, *, source: str) -> Any:
    text = data.decode("utf-8") if isinstance(data, bytes) else data

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise PackageError(f"{source}: 중복 JSON key가 있습니다: {key}")
            result[key] = value
        return result

    try:
        return json.loads(text, object_pairs_hook=reject_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PackageError(f"{source}: 유효한 UTF-8 JSON이 아닙니다: {error}") from error


## @brief JSON을 byte 단위로 재현 가능한 형식으로 직렬화합니다.
def canonical_json(document: Any) -> bytes:
    return (json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


## @brief byte 배열의 SHA-256을 계산합니다.
def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


## @brief byte 배열의 SHA-1을 SPDX file checksum 용도로 계산합니다.
def sha1_bytes(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


## @brief package version만 다른 archive의 실행 payload를 같은 byte identity로 정규화합니다.
def normalize_runtime_payload_bytes(path: str, data: bytes) -> bytes:
    if path != "platform.txt":
        return data
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise PackageError("platform.txt가 UTF-8이 아닙니다.") from error
    lines = text.splitlines(keepends=True)
    matches = [index for index, line in enumerate(lines) if line.startswith("version=")]
    if len(matches) != 1:
        raise PackageError("platform.txt에는 version= 항목이 정확히 하나 있어야 합니다.")
    index = matches[0]
    ending = "\r\n" if lines[index].endswith("\r\n") else "\n" if lines[index].endswith("\n") else ""
    lines[index] = f"version=@NU54_PACKAGE_VERSION@{ending}"
    return "".join(lines).encode("utf-8")


## @brief 실제 설치 payload의 version 독립 SHA-256 fingerprint를 계산합니다.
def runtime_payload_sha256(files: Iterable[tuple[str, bytes, int]]) -> str:
    records: list[dict[str, Any]] = []
    for path, data, mode in sorted(files, key=lambda item: item[0].encode("utf-8")):
        normalized = normalize_runtime_payload_bytes(path, data)
        records.append(
            {
                "mode": f"{mode:04o}",
                "path": path,
                "sha256": sha256_bytes(normalized),
                "size": len(normalized),
            }
        )
    return sha256_bytes(
        canonical_json(
            {
                "normalization": "platform-version-sentinel-v1",
                "records": records,
                "schema_version": 1,
            }
        )
    )


## @brief ZIP 내부 checksum 목록을 생성합니다.
def build_internal_checksums(files: dict[str, tuple[bytes, int]]) -> bytes:
    lines = [
        f"{sha256_bytes(data)}  {path}"
        for path, (data, _mode) in sorted(files.items(), key=lambda pair: pair[0].encode("utf-8"))
        if path != "CHECKSUMS.sha256"
    ]
    return ("\n".join(lines) + "\n").encode("utf-8")


## @brief strict checksum 목록을 읽습니다.
def parse_checksums(data: bytes, *, source: str) -> dict[str, str]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise PackageError(f"{source}: checksum 목록이 UTF-8이 아닙니다.") from error
    result: dict[str, str] = {}
    for line in text.splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  ([^\r\n]+)", line)
        if not match:
            raise PackageError(f"{source}: checksum record 형식이 잘못되었습니다: {line!r}")
        digest, path = match.groups()
        ensure_safe_relative_path(path)
        if path in result:
            raise PackageError(f"{source}: checksum path가 중복됩니다: {path}")
        result[path] = digest
    return result
