#!/usr/bin/env python3
"""! @brief NU54DK Arduino Boards Manager 배포물을 재현 가능하게 생성하고 검증합니다. """

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


SUPPORTED_VERSIONS = ("0.0.90", "0.0.91")
VENDOR = "nucode"
ARCHITECTURE = "zephyr"
MAINTAINER = "NUCODE / Quantum"
CONTACT_EMAIL = "EIDOSDATA@users.noreply.github.com"
REPOSITORY_URL = "https://github.com/EIDOSDATA/NU54DK_Arduino_Core"
BOARD_REPOSITORY_URL = "https://github.com/Nucode01/NU54DK_Zephyr_DTS"
INDEX_FILENAME = "package_nucode_nu54dk_preview_index.json"
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


## @brief 외부 명령을 실행하고 실패를 패키징 오류로 변환합니다.
def run_checked(arguments: list[str], *, cwd: Path, binary: bool = False) -> bytes | str:
    try:
        result = subprocess.run(
            arguments,
            cwd=cwd,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=not binary,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        detail = ""
        if isinstance(error, subprocess.CalledProcessError):
            stderr = error.stderr
            detail = stderr.decode("utf-8", "replace") if isinstance(stderr, bytes) else (stderr or "")
        raise PackageError(f"명령 실행 실패: {' '.join(arguments)}\n{detail.strip()}") from error
    return result.stdout


## @brief Git ref를 full commit SHA로 고정합니다.
def resolve_commit(repo_root: Path, revision: str) -> str:
    output = run_checked(
        ["git", "rev-parse", "--verify", f"{revision}^{{commit}}"], cwd=repo_root
    )
    commit = str(output).strip()
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise PackageError(f"full Git commit SHA를 얻지 못했습니다: {commit}")
    return commit


## @brief Git commit 시간을 SPDX UTC timestamp로 정규화합니다.
def commit_timestamp(repo_root: Path, commit: str) -> str:
    output = str(
        run_checked(["git", "show", "-s", "--format=%cI", commit], cwd=repo_root)
    ).strip()
    try:
        parsed = dt.datetime.fromisoformat(output).astimezone(dt.timezone.utc)
    except ValueError as error:
        raise PackageError(f"Git commit 시간을 해석하지 못했습니다: {output}") from error
    return parsed.replace(microsecond=0).isoformat().replace("+00:00", "Z")


## @brief Git tree의 blob 및 gitlink를 byte 안전하게 열거합니다.
def git_tree_entries(repo_root: Path, revision: str) -> list[tuple[str, str, str, str]]:
    raw = run_checked(
        ["git", "ls-tree", "-r", "-z", "--full-tree", revision], cwd=repo_root, binary=True
    )
    assert isinstance(raw, bytes)
    entries: list[tuple[str, str, str, str]] = []
    for record in raw.split(b"\0"):
        if not record:
            continue
        try:
            metadata, encoded_path = record.split(b"\t", 1)
            mode, object_type, object_id = metadata.decode("ascii").split(" ", 2)
            path = encoded_path.decode("utf-8")
        except (ValueError, UnicodeDecodeError) as error:
            raise PackageError("Git tree record를 안전하게 해석하지 못했습니다.") from error
        entries.append((mode, object_type, object_id, path))
    return entries


## @brief Git blob 원문을 읽습니다.
def git_blob(repo_root: Path, object_id: str) -> bytes:
    output = run_checked(["git", "cat-file", "blob", object_id], cwd=repo_root, binary=True)
    assert isinstance(output, bytes)
    return output


## @brief Windows 추출 환경에서 위험하거나 비밀일 수 있는 경로를 거부합니다.
def ensure_safe_relative_path(path: str) -> None:
    if not path or "\\" in path or "\0" in path:
        raise PackageError(f"안전하지 않은 경로입니다: {path!r}")
    pure = PurePosixPath(path)
    if pure.is_absolute() or any(part in ("", ".", "..") for part in pure.parts):
        raise PackageError(f"안전하지 않은 상대 경로입니다: {path}")
    if re.match(r"^[A-Za-z]:", path):
        raise PackageError(f"드라이브 경로는 허용하지 않습니다: {path}")
    for part in pure.parts:
        lowered = part.casefold()
        if lowered in {".git", ".svn", ".hg", "__pycache__", "build", "out", ".cache"}:
            raise PackageError(f"배포 금지 경로가 포함되었습니다: {path}")
        if lowered in {"id_rsa", "id_ed25519", "authorized_keys", ".env", "secrets.json"}:
            raise PackageError(f"비밀정보 후보 파일은 배포할 수 없습니다: {path}")
        if lowered.endswith((".pem", ".pfx", ".p12", ".jks", ".keystore", ".key")):
            raise PackageError(f"개인키 후보 파일은 배포할 수 없습니다: {path}")


## @brief Arduino platform runtime에 필요한 상위 저장소 파일만 선택합니다.
def include_core_path(path: str) -> bool:
    ensure_safe_relative_path(path)
    pure = PurePosixPath(path)
    if path.endswith("/.gitkeep") or pure.name == ".gitkeep" or pure.suffix.casefold() == ".pdf":
        return False
    if len(pure.parts) == 1:
        return pure.name in {
            "LICENSE",
            "boards.txt",
            "platform.txt",
            "programmers.txt",
            "post_install.bat",
            "post_install.sh",
        }
    root = pure.parts[0]
    if root in {"cores", "dts", "examples", "libraries", "third_party", "variants", "zephyr"}:
        return True
    if root == "tools":
        return len(pure.parts) >= 2 and pure.parts[1] in {"nu54-builder", "nu54-prerequisites"}
    return False


## @brief 보드 저장소에서 DTS runtime과 라이선스만 선택합니다.
def include_board_path(path: str) -> bool:
    ensure_safe_relative_path(path)
    pure = PurePosixPath(path)
    if pure.suffix.casefold() == ".pdf" or pure.name == ".gitkeep":
        return False
    if pure.parts[0] == "boards":
        return True
    if len(pure.parts) == 1 and pure.name in {"LICENSE", "NOTICE"}:
        return True
    return pure.parts[0] == "LICENSES"


## @brief platform.txt의 version만 배포 버전으로 교체합니다.
def rewrite_platform_version(data: bytes, version: str) -> bytes:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise PackageError("platform.txt가 UTF-8이 아닙니다.") from error
    lines = text.splitlines(keepends=True)
    matches = [index for index, line in enumerate(lines) if line.startswith("version=")]
    if matches != [1] and len(matches) != 1:
        raise PackageError("platform.txt에는 version= 항목이 정확히 하나 있어야 합니다.")
    index = matches[0]
    ending = "\r\n" if lines[index].endswith("\r\n") else "\n"
    lines[index] = f"version={version}{ending}"
    return "".join(lines).encode("utf-8")


## @brief 상위 commit과 gitlink commit을 깨끗한 패키지 입력으로 materialize합니다.
def collect_source_files(repo_root: Path, commit: str, version: str) -> tuple[list[SourceFile], str]:
    board_path = "board_package/NU54DK_Zephyr_DTS"
    board_entry: tuple[str, str, str, str] | None = None
    files: list[SourceFile] = []
    for mode, object_type, object_id, path in git_tree_entries(repo_root, commit):
        if path == board_path:
            board_entry = (mode, object_type, object_id, path)
            continue
        if path.startswith(f"{board_path}/"):
            raise PackageError("보드 패키지가 gitlink가 아닌 중첩 파일로 저장되어 있습니다.")
        if not include_core_path(path):
            continue
        if object_type != "blob" or mode not in {"100644", "100755"}:
            raise PackageError(f"지원하지 않는 Git object입니다: {mode} {object_type} {path}")
        data = git_blob(repo_root, object_id)
        transformation = None
        if path == "platform.txt":
            data = rewrite_platform_version(data, version)
            transformation = "platform-version"
        files.append(
            SourceFile(
                path=path,
                data=data,
                mode=0o755 if mode == "100755" else 0o644,
                origin="core",
                git_object=object_id,
                transformation=transformation,
            )
        )

    if board_entry is None:
        raise PackageError(f"{commit}에 {board_path} gitlink가 없습니다.")
    mode, object_type, board_revision, _ = board_entry
    if mode != "160000" or object_type != "commit" or not re.fullmatch(r"[0-9a-f]{40}", board_revision):
        raise PackageError("보드 패키지 항목이 유효한 gitlink가 아닙니다.")
    submodule_root = repo_root / board_path
    if not submodule_root.is_dir():
        raise PackageError("보드 서브모듈이 초기화되지 않았습니다. git submodule update --init을 실행하십시오.")
    try:
        run_checked(["git", "cat-file", "-e", f"{board_revision}^{{commit}}"], cwd=submodule_root)
    except PackageError as error:
        raise PackageError(f"보드 서브모듈에 고정 revision이 없습니다: {board_revision}") from error

    for sub_mode, sub_type, object_id, sub_path in git_tree_entries(submodule_root, board_revision):
        if not include_board_path(sub_path):
            continue
        if sub_type != "blob" or sub_mode not in {"100644", "100755"}:
            raise PackageError(f"지원하지 않는 보드 Git object입니다: {sub_path}")
        package_path = f"{board_path}/{sub_path}"
        files.append(
            SourceFile(
                path=package_path,
                data=git_blob(submodule_root, object_id),
                mode=0o755 if sub_mode == "100755" else 0o644,
                origin="board",
                git_object=object_id,
            )
        )

    files.sort(key=lambda item: item.path.encode("utf-8"))
    paths = [item.path for item in files]
    if len(paths) != len(set(paths)) or len({path.casefold() for path in paths}) != len(paths):
        raise PackageError("대소문자 비구분 환경에서 충돌하는 패키지 경로가 있습니다.")
    required = {
        "LICENSE",
        "boards.txt",
        "platform.txt",
        "tools/nu54-prerequisites/pins.json",
        f"{board_path}/LICENSE",
        f"{board_path}/NOTICE",
    }
    missing = sorted(required.difference(paths))
    if missing:
        raise PackageError(f"필수 패키지 파일이 없습니다: {', '.join(missing)}")
    return files, board_revision


## @brief 소스 파일에 선언된 SPDX 식별자를 수집합니다.
def declared_spdx_identifiers(files: Iterable[SourceFile]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    pattern = re.compile(rb"SPDX-License-Identifier:\s*([^\r\n*]+)")
    for item in files:
        identifiers = sorted(
            {
                match.decode("utf-8", "strict").strip()
                for match in pattern.findall(item.data)
                if match.strip()
            }
        )
        if identifiers:
            result[item.path] = identifiers
    return result


## @brief 패키지에 고정된 외부 설치 구성요소를 재배포와 구분해 기록합니다.
def build_external_prerequisites(files: list[SourceFile]) -> list[dict[str, Any]]:
    pins_file = next(
        (item for item in files if item.path == "tools/nu54-prerequisites/pins.json"), None
    )
    if pins_file is None:
        raise PackageError("외부 전제조건 inventory를 만들 pins.json이 없습니다.")
    pins = strict_json_loads(pins_file.data, source="tools/nu54-prerequisites/pins.json")
    if not isinstance(pins, dict):
        raise PackageError("pins.json 최상위 값이 object가 아닙니다.")
    try:
        nrfutil = pins["nrfutil"]
        sdk_manager = pins["sdk_manager"]
        ncs = pins["ncs"]
        zephyr = pins["zephyr"]
        toolchain = pins["toolchain"]
        fixed = {
            "nrfutil_version": nrfutil["version"],
            "nrfutil_url": nrfutil["url"],
            "nrfutil_sha256": nrfutil["sha256"],
            "sdk_manager_version": sdk_manager["version"],
            "ncs_version": ncs["version"],
            "ncs_revision": ncs["revision"],
            "zephyr_revision": zephyr["revision"],
            "toolchain_bundle_id": toolchain["bundle_id"],
        }
    except (KeyError, TypeError) as error:
        raise PackageError(f"pins.json 외부 전제조건 필드가 불완전합니다: {error}") from error
    expected = {
        "nrfutil_version": "8.2.1",
        "nrfutil_sha256": "1d291d8a9d6bb5bec18454f8d95064aed7f62e8997ec1c4511f13bdf1124c037",
        "sdk_manager_version": "1.16.1",
        "ncs_version": NCS_VERSION,
        "ncs_revision": NCS_REVISION,
        "zephyr_revision": ZEPHYR_REVISION,
        "toolchain_bundle_id": TOOLCHAIN_BUNDLE_ID,
    }
    for key, value in expected.items():
        if fixed[key] != value:
            raise PackageError(f"pins.json {key}가 release 계약과 다릅니다: {fixed[key]!r}")
    if not isinstance(fixed["nrfutil_url"], str) or not fixed["nrfutil_url"].startswith("https://"):
        raise PackageError("nRF Util pin URL은 HTTPS여야 합니다.")

    common = {
        "distribution": "external-not-redistributed",
        "license_expression": "NOASSERTION",
        "legal_review_status": "required-before-final-public-release",
    }
    return [
        {
            **common,
            "name": "nRF Util",
            "version": fixed["nrfutil_version"],
            "required": True,
            "source": fixed["nrfutil_url"],
            "sha256": fixed["nrfutil_sha256"],
            "installer": "tools/nu54-prerequisites/install-nordic.ps1",
        },
        {
            **common,
            "name": "nRF Util sdk-manager",
            "version": fixed["sdk_manager_version"],
            "required": True,
            "source": "https://docs.nordicsemi.com/bundle/nrfutil/page/guides/sdk_manager.html",
            "installer": "nrfutil install --set tools/nu54-prerequisites/nrfutil-requirements.json",
        },
        {
            **common,
            "name": "nRF Connect SDK",
            "version": fixed["ncs_version"],
            "revision": fixed["ncs_revision"],
            "required": True,
            "source": "https://github.com/nrfconnect/sdk-nrf",
            "installer": f"nrfutil sdk-manager sdk install {fixed['ncs_version']}",
        },
        {
            **common,
            "name": "Zephyr",
            "version": ZEPHYR_VERSION,
            "revision": fixed["zephyr_revision"],
            "required": True,
            "source": "https://github.com/nrfconnect/sdk-zephyr",
            "installer": f"nRF Connect SDK {fixed['ncs_version']} manifest",
        },
        {
            **common,
            "name": "nRF Connect SDK Toolchain",
            "version": fixed["toolchain_bundle_id"],
            "bundle_id": fixed["toolchain_bundle_id"],
            "required": True,
            "source": "https://docs.nordicsemi.com/bundle/nrf-connect-vscode/page/toolchains.html",
            "installer": f"nrfutil sdk-manager toolchain install --toolchain-bundle-id {fixed['toolchain_bundle_id']}",
        },
        {
            **common,
            "name": "pyOCD",
            "version": "0.45.1",
            "required": True,
            "source": "https://github.com/pyocd/pyOCD",
            "installer": f"nRF Connect SDK toolchain bundle {fixed['toolchain_bundle_id']}",
        },
        {
            **common,
            "name": "SEGGER J-Link Software",
            "version": "user-supplied",
            "required": False,
            "source": "https://www.segger.com/downloads/jlink/",
            "installer": "optional-user-installation",
        },
    ]


## @brief 패키지에 포함된 라이선스 원문과 구성요소 범위를 기록합니다.
def build_license_inventory(
    files: list[SourceFile], version: str, board_revision: str
) -> dict[str, Any]:
    by_path = {item.path: item for item in files}
    license_specs = (
        ("LICENSE", "MIT", "NUCODE NU54DK Arduino Core"),
        ("third_party/ArduinoCore-API/LICENSE", "LGPL-2.1-or-later AND MIT", "ArduinoCore-API 1.5.2"),
        ("board_package/NU54DK_Zephyr_DTS/LICENSE", "MIT", "NU54DK Zephyr DTS repository"),
        (
            "board_package/NU54DK_Zephyr_DTS/LICENSES/Apache-2.0.txt",
            "Apache-2.0",
            "NU54DK Zephyr derived board definition",
        ),
    )
    license_files: list[dict[str, Any]] = []
    for path, expression, component in license_specs:
        item = by_path.get(path)
        if item is None:
            raise PackageError(f"라이선스 원문이 패키지에 없습니다: {path}")
        license_files.append(
            {
                "component": component,
                "license_expression": expression,
                "path": path,
                "sha256": sha256_bytes(item.data),
                "size": len(item.data),
            }
        )
    inventory = {
        "schema_version": 1,
        "legal_review_status": "required-before-final-public-release",
        "notice": "이 기계적 목록은 법률 자문 또는 최종 재배포 승인을 대신하지 않습니다.",
        "components": [
            {
                "name": "NUCODE NU54DK Arduino Core",
                "version": version,
                "license_expression": "MIT",
                "source": REPOSITORY_URL,
            },
            {
                "name": "ArduinoCore-API",
                "version": "1.5.2",
                "revision": "cd91833d90b4fe50e428021ba5051e2b7ceafc84",
                "license_expression": "LGPL-2.1-or-later AND MIT",
                "source": "https://github.com/arduino/ArduinoCore-API",
            },
            {
                "name": "NU54DK Zephyr DTS repository",
                "revision": board_revision,
                "license_expression": "MIT",
                "scope": ["board_package/NU54DK_Zephyr_DTS/LICENSE"],
                "source": BOARD_REPOSITORY_URL,
            },
            {
                "name": "NU54DK Zephyr derived board definition",
                "revision": board_revision,
                "license_expression": "Apache-2.0",
                "scope": ["board_package/NU54DK_Zephyr_DTS/boards/nucode/nu54dk/**"],
                "notice": "board_package/NU54DK_Zephyr_DTS/NOTICE",
                "source": BOARD_REPOSITORY_URL,
            },
        ],
        "license_files": license_files,
        "notice_files": [],
        "external_prerequisites": build_external_prerequisites(files),
        "declared_spdx_identifiers": declared_spdx_identifiers(files),
    }
    notice_specs = (
        ("third_party/THIRD_PARTY_NOTICES.md", "ArduinoCore-API"),
        ("board_package/NU54DK_Zephyr_DTS/NOTICE", "NU54DK Zephyr derived board definition"),
    )
    for path, component in notice_specs:
        item = by_path.get(path)
        if item is None:
            raise PackageError(f"필수 notice 원문이 패키지에 없습니다: {path}")
        inventory["notice_files"].append(
            {
                "component": component,
                "path": path,
                "sha256": sha256_bytes(item.data),
                "size": len(item.data),
            }
        )
    return inventory


## @brief 배포물에 동봉할 third-party 고지를 만듭니다.
def build_third_party_notices(board_revision: str) -> bytes:
    text = f"""# Third-party notices

이 파일은 Boards Manager 패키지에 포함된 외부 구성요소를 식별합니다. 저장소 최상위
`LICENSE`의 MIT 조건은 NUCODE가 자체 작성한 코드에만 적용되며 아래 구성요소의 원
라이선스를 대체하지 않습니다.

## ArduinoCore-API 1.5.2

- 원본: <https://github.com/arduino/ArduinoCore-API>
- 고정 commit: `cd91833d90b4fe50e428021ba5051e2b7ceafc84`
- 라이선스: `LGPL-2.1-or-later AND MIT`
- 원문: `third_party/ArduinoCore-API/LICENSE`

## NU54DK Zephyr DTS

- 원본: <{BOARD_REPOSITORY_URL}>
- 고정 commit: `{board_revision}`
- 패키지 포함 범위의 종합 식별: `MIT AND Apache-2.0`
- 저장소 최상위 원문 `LICENSE`: `MIT`
- 파생 범위 `boards/nucode/nu54dk/**`: `Apache-2.0`
- Apache 원문: `board_package/NU54DK_Zephyr_DTS/LICENSES/Apache-2.0.txt`
- 범위 고지: `board_package/NU54DK_Zephyr_DTS/NOTICE`

## 외부 설치 전제조건

다음 항목은 이 Boards Manager ZIP에 포함하거나 재배포하지 않고 공식 설치기 또는 사용자가
별도로 공급합니다. 종합 라이선스는 추정하지 않고 `NOASSERTION`으로 기록하며 최종 공개 전
법률 검토가 필요합니다.

- nRF Util `8.2.1` 및 nRF Util sdk-manager `1.16.1`
- nRF Connect SDK `{NCS_VERSION}` (`{NCS_REVISION}`)
- Zephyr `{ZEPHYR_VERSION}` (`{ZEPHYR_REVISION}`)
- nRF Connect SDK toolchain bundle `{TOOLCHAIN_BUNDLE_ID}`
- toolchain에 포함된 pyOCD `0.45.1`
- 사용자가 선택적으로 설치하는 SEGGER J-Link Software

상세 checksum과 파일별 SPDX 선언은 `license-inventory.json` 및 `sbom.spdx.json`에
기록합니다. 이 목록은 법률 자문 또는 최종 공개 배포 승인을 대신하지 않습니다.
"""
    return text.encode("utf-8")


## @brief 패키지 경로와 원문 고지로 file별 license conclusion을 결정합니다.
def concluded_file_license(item: SourceFile, identifiers: list[str]) -> str:
    path = item.path
    board_root = "board_package/NU54DK_Zephyr_DTS/"
    if path.startswith(f"{board_root}boards/nucode/nu54dk/"):
        return "Apache-2.0"
    if path == f"{board_root}LICENSE":
        return "MIT"
    if path == f"{board_root}LICENSES/Apache-2.0.txt":
        return "Apache-2.0"
    if path == f"{board_root}NOTICE":
        return "NOASSERTION"
    arduino_root = "third_party/ArduinoCore-API/"
    if path == f"{arduino_root}LICENSE":
        return "LGPL-2.1-or-later AND MIT"
    if path in {
        f"{arduino_root}api/Udp.h",
        f"{arduino_root}api/deprecated-avr-comp/avr/pgmspace.h",
    }:
        return "MIT"
    if path.startswith(f"{arduino_root}api/"):
        return identifiers[0] if len(identifiers) == 1 else "LGPL-2.1-or-later"
    if path.startswith(arduino_root) or path.startswith("third_party/"):
        return "NOASSERTION"
    if len(identifiers) == 1:
        return identifiers[0]
    if identifiers:
        return "NOASSERTION"
    return "MIT"


## @brief SPDX 2.3 JSON SBOM을 소스 파일 단위로 생성합니다.
def build_spdx(
    files: list[SourceFile],
    version: str,
    commit: str,
    created: str,
    external_prerequisites: list[dict[str, Any]],
) -> dict[str, Any]:
    declared = declared_spdx_identifiers(files)
    release_url = release_asset_url(version, archive_filename(version))
    spdx_files: list[dict[str, Any]] = []
    relationships: list[dict[str, str]] = []
    verification_hashes: list[str] = []
    for item in files:
        sha1 = sha1_bytes(item.data)
        verification_hashes.append(sha1)
        identifier = f"SPDXRef-File-{hashlib.sha256(item.path.encode('utf-8')).hexdigest()[:24]}"
        identifiers = declared.get(item.path, [])
        conclusion = concluded_file_license(item, identifiers)
        spdx_files.append(
            {
                "SPDXID": identifier,
                "checksums": [
                    {"algorithm": "SHA1", "checksumValue": sha1},
                    {"algorithm": "SHA256", "checksumValue": sha256_bytes(item.data)},
                ],
                "copyrightText": "NOASSERTION",
                "fileName": f"./{item.path}",
                "licenseConcluded": conclusion,
                "licenseInfoInFiles": identifiers or [conclusion],
            }
        )
        relationships.append(
            {
                "spdxElementId": "SPDXRef-Package-NU54DK-Arduino-Core",
                "relationshipType": "CONTAINS",
                "relatedSpdxElement": identifier,
            }
        )
    verification_code = hashlib.sha1("".join(sorted(verification_hashes)).encode("ascii")).hexdigest()
    packages: list[dict[str, Any]] = [
        {
            "SPDXID": "SPDXRef-Package-NU54DK-Arduino-Core",
            "name": "NUCODE NU54DK Zephyr Boards",
            "versionInfo": version,
            "downloadLocation": release_url,
            "filesAnalyzed": True,
            "licenseConcluded": "NOASSERTION",
            "licenseDeclared": "NOASSERTION",
            "copyrightText": "NOASSERTION",
            "packageVerificationCode": {"packageVerificationCodeValue": verification_code},
        }
    ]
    for prerequisite in external_prerequisites:
        package_id = f"SPDXRef-External-{hashlib.sha256(prerequisite['name'].encode('utf-8')).hexdigest()[:20]}"
        packages.append(
            {
                "SPDXID": package_id,
                "name": prerequisite["name"],
                "versionInfo": prerequisite["version"],
                "downloadLocation": prerequisite["source"],
                "filesAnalyzed": False,
                "licenseConcluded": "NOASSERTION",
                "licenseDeclared": "NOASSERTION",
                "copyrightText": "NOASSERTION",
                "comment": (
                    "distribution: external-not-redistributed; "
                    f"installer: {prerequisite['installer']}; "
                    "legal review required before final public release"
                ),
            }
        )
        if prerequisite["required"]:
            relationships.append(
                {
                    "spdxElementId": "SPDXRef-Package-NU54DK-Arduino-Core",
                    "relationshipType": "DEPENDS_ON",
                    "relatedSpdxElement": package_id,
                }
            )
        else:
            relationships.append(
                {
                    "spdxElementId": package_id,
                    "relationshipType": "OPTIONAL_DEPENDENCY_OF",
                    "relatedSpdxElement": "SPDXRef-Package-NU54DK-Arduino-Core",
                }
            )
    return {
        "SPDXID": "SPDXRef-DOCUMENT",
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "name": f"NU54DK Arduino Core {version}",
        "documentNamespace": f"{REPOSITORY_URL}/spdx/{version}/{commit}",
        "creationInfo": {
            "created": created,
            "creators": ["Tool: nu54_package.py", f"Organization: {MAINTAINER}"],
            "licenseListVersion": "3.25",
        },
        "documentDescribes": ["SPDXRef-Package-NU54DK-Arduino-Core"],
        "packages": packages,
        "files": spdx_files,
        "relationships": relationships,
    }


## @brief release asset 이름을 고정합니다.
def archive_filename(version: str) -> str:
    return f"nucode-nu54dk-zephyr-{version}.zip"


## @brief prerelease tag 이름을 고정합니다.
def release_tag(version: str) -> str:
    return f"m10-preview-{version}"


## @brief 공개 GitHub prerelease asset URL을 만듭니다.
def release_asset_url(version: str, filename: str) -> str:
    return f"{REPOSITORY_URL}/releases/download/{release_tag(version)}/{filename}"


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
    return {
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
        "source_policy": "exact-commit-plus-declared-platform-version-rewrite",
        "generated_metadata": list(METADATA_FILES),
        "file_count": len(entries),
        "total_size": sum(entry["size"] for entry in entries),
        "files": entries,
        "file_hashes": file_hashes,
    }


## @brief ZIP 내부 checksum 목록을 생성합니다.
def build_internal_checksums(files: dict[str, tuple[bytes, int]]) -> bytes:
    lines = [
        f"{sha256_bytes(data)}  {path}"
        for path, (data, _mode) in sorted(files.items(), key=lambda pair: pair[0].encode("utf-8"))
        if path != "CHECKSUMS.sha256"
    ]
    return ("\n".join(lines) + "\n").encode("utf-8")


## @brief 고정 timestamp, mode, 순서로 ZIP 한 개를 기록합니다.
def write_deterministic_zip(
    destination: Path, root: str, files: dict[str, tuple[bytes, int]]
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    if temporary.exists():
        temporary.unlink()
    try:
        ## @note 압축기 구현 차이까지 제거하기 위해 작은 core package는 STORE 방식으로 고정합니다.
        with zipfile.ZipFile(
            temporary,
            mode="w",
            compression=zipfile.ZIP_STORED,
            allowZip64=False,
            strict_timestamps=True,
        ) as archive:
            for path, (data, mode) in sorted(files.items(), key=lambda pair: pair[0].encode("utf-8")):
                ensure_safe_relative_path(path)
                info = zipfile.ZipInfo(f"{root}/{path}", date_time=ZIP_TIMESTAMP)
                info.compress_type = zipfile.ZIP_STORED
                info.create_system = 3
                info.external_attr = ((stat.S_IFREG | mode) & 0xFFFF) << 16
                archive.writestr(info, data, compress_type=zipfile.ZIP_STORED)
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()


## @brief archive와 sidecar의 외부 checksum 목록을 생성합니다.
def write_external_checksums(paths: list[Path], destination: Path) -> None:
    lines = [f"{sha256_bytes(path.read_bytes())}  {path.name}" for path in sorted(paths, key=lambda p: p.name)]
    destination.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))


## @brief 지정 commit에서 Boards Manager archive와 provenance sidecar를 만듭니다.
def build_package(repo_root: Path, output_dir: Path, version: str, revision: str) -> dict[str, Path]:
    if version not in SUPPORTED_VERSIONS:
        raise PackageError(f"지원하는 preview version이 아닙니다: {version}")
    repo_root = repo_root.resolve()
    output_dir = output_dir.resolve()
    commit = resolve_commit(repo_root, revision)
    created = commit_timestamp(repo_root, commit)
    source_files, board_revision = collect_source_files(repo_root, commit, version)
    release_manifest = build_release_manifest(source_files, version, commit, board_revision)
    license_inventory = build_license_inventory(source_files, version, board_revision)
    external_prerequisites = build_external_prerequisites(source_files)
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


## @brief ZIP 구조, metadata 계약, 모든 payload checksum을 fail-closed 검증합니다.
def validate_archive(
    archive_path: Path,
    *,
    expected_version: str | None = None,
    expected_commit: str | None = None,
) -> dict[str, Any]:
    archive_path = archive_path.resolve()
    if not archive_path.is_file():
        raise PackageError(f"archive가 없습니다: {archive_path}")
    if archive_path.stat().st_size > MAX_ARCHIVE_SIZE:
        raise PackageError("archive가 허용 크기를 초과합니다.")
    try:
        archive = zipfile.ZipFile(archive_path, "r")
    except (OSError, zipfile.BadZipFile) as error:
        raise PackageError(f"ZIP을 열 수 없습니다: {error}") from error
    with archive:
        infos = archive.infolist()
        if not infos:
            raise PackageError("빈 ZIP은 허용하지 않습니다.")
        names = [info.filename for info in infos]
        if names != sorted(names, key=lambda name: name.encode("utf-8")):
            raise PackageError("ZIP entry가 UTF-8 byte 순서로 정렬되지 않았습니다.")
        if len(names) != len(set(names)) or len({name.casefold() for name in names}) != len(names):
            raise PackageError("ZIP entry가 중복되거나 대소문자 충돌합니다.")
        roots: set[str] = set()
        total_size = 0
        relative_infos: dict[str, zipfile.ZipInfo] = {}
        relative_data: dict[str, bytes] = {}
        for info in infos:
            if info.is_dir() or info.filename.endswith("/"):
                raise PackageError("명시적 directory entry는 허용하지 않습니다.")
            if info.date_time != ZIP_TIMESTAMP:
                raise PackageError(f"ZIP timestamp가 고정값이 아닙니다: {info.filename}")
            if info.create_system != 3 or info.compress_type != zipfile.ZIP_STORED:
                raise PackageError(f"ZIP system/compression 계약이 다릅니다: {info.filename}")
            mode = (info.external_attr >> 16) & 0xFFFF
            if not stat.S_ISREG(mode) or stat.S_IMODE(mode) not in {0o644, 0o755}:
                raise PackageError(f"ZIP file mode가 안전하지 않습니다: {info.filename} {mode:o}")
            if info.flag_bits & 0x1:
                raise PackageError("암호화된 ZIP entry는 허용하지 않습니다.")
            if info.file_size > MAX_FILE_SIZE:
                raise PackageError(f"ZIP entry가 허용 크기를 초과합니다: {info.filename}")
            total_size += info.file_size
            if total_size > MAX_ARCHIVE_SIZE:
                raise PackageError("ZIP 해제 크기가 허용치를 초과합니다.")
            pure = PurePosixPath(info.filename)
            if len(pure.parts) < 2:
                raise PackageError("모든 ZIP entry는 하나의 top-level directory 안에 있어야 합니다.")
            roots.add(pure.parts[0])
            relative = PurePosixPath(*pure.parts[1:]).as_posix()
            ensure_safe_relative_path(relative)
            relative_infos[relative] = info
            try:
                relative_data[relative] = archive.read(info)
            except (RuntimeError, zipfile.BadZipFile) as error:
                raise PackageError(f"ZIP entry를 읽지 못했습니다: {info.filename}") from error
        if len(roots) != 1:
            raise PackageError("ZIP에는 정확히 하나의 top-level directory가 있어야 합니다.")
        missing_metadata = sorted(set(METADATA_FILES).difference(relative_data))
        if missing_metadata:
            raise PackageError(f"필수 metadata가 없습니다: {', '.join(missing_metadata)}")

        manifest = strict_json_loads(relative_data["release-manifest.json"], source="release-manifest.json")
        if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
            raise PackageError("release-manifest schema_version이 1이 아닙니다.")
        version = manifest.get("version")
        if version not in SUPPORTED_VERSIONS or (expected_version and version != expected_version):
            raise PackageError(f"release-manifest version이 예상과 다릅니다: {version}")
        expected_root = f"nucode-nu54dk-zephyr-{version}"
        if roots != {expected_root} or manifest.get("archive_root") != expected_root:
            raise PackageError("archive top-level directory가 manifest와 다릅니다.")
        if manifest.get("archive_file_name") != archive_filename(version):
            raise PackageError("archive filename 계약이 manifest와 다릅니다.")
        if archive_path.name != archive_filename(version):
            raise PackageError("실제 archive filename이 계약과 다릅니다.")
        required_manifest_fields = {
            "core_revision": r"[0-9a-f]{40}",
            "board_revision": r"[0-9a-f]{40}",
            "ncs_revision": re.escape(NCS_REVISION),
            "zephyr_revision": re.escape(ZEPHYR_REVISION),
            "toolchain_bundle_id": re.escape(TOOLCHAIN_BUNDLE_ID),
            "prerequisites_pins_sha256": r"[0-9a-f]{64}",
        }
        for field, pattern in required_manifest_fields.items():
            value = manifest.get(field)
            if not isinstance(value, str) or not re.fullmatch(pattern, value):
                raise PackageError(f"release-manifest {field}가 유효하지 않습니다: {value!r}")
        if expected_commit and manifest["core_revision"] != expected_commit:
            raise PackageError("release-manifest core_revision이 예상 commit과 다릅니다.")
        fixed_values = {
            "vendor": VENDOR,
            "architecture": ARCHITECTURE,
            "source_repository": REPOSITORY_URL,
            "board_repository": BOARD_REPOSITORY_URL,
            "ncs_version": NCS_VERSION,
            "zephyr_version": ZEPHYR_VERSION,
            "release_tag": release_tag(version),
            "release_url": release_asset_url(version, archive_filename(version)),
        }
        for field, expected in fixed_values.items():
            if manifest.get(field) != expected:
                raise PackageError(f"release-manifest {field}가 고정값과 다릅니다.")

        payload_paths = sorted(
            set(relative_data).difference(METADATA_FILES), key=lambda path: path.encode("utf-8")
        )
        records = manifest.get("files")
        if not isinstance(records, list):
            raise PackageError("release-manifest files가 배열이 아닙니다.")
        record_paths = [record.get("path") for record in records if isinstance(record, dict)]
        if len(record_paths) != len(records) or record_paths != payload_paths:
            raise PackageError("release-manifest file 목록이 ZIP payload와 다릅니다.")
        file_hashes = manifest.get("file_hashes")
        if not isinstance(file_hashes, dict) or list(file_hashes) != payload_paths:
            raise PackageError("release-manifest file_hashes가 ZIP payload와 다릅니다.")
        for record in records:
            path = record["path"]
            data = relative_data[path]
            digest = sha256_bytes(data)
            mode = stat.S_IMODE((relative_infos[path].external_attr >> 16) & 0xFFFF)
            if record.get("sha256") != digest or file_hashes.get(path) != digest:
                raise PackageError(f"release-manifest checksum 불일치: {path}")
            if record.get("size") != len(data) or record.get("mode") != f"{mode:04o}":
                raise PackageError(f"release-manifest size/mode 불일치: {path}")
            if record.get("origin") not in {"core", "board"}:
                raise PackageError(f"release-manifest origin이 유효하지 않습니다: {path}")
            if not re.fullmatch(r"[0-9a-f]{40}", str(record.get("git_object", ""))):
                raise PackageError(f"release-manifest git_object가 유효하지 않습니다: {path}")
        pins_path = "tools/nu54-prerequisites/pins.json"
        if manifest["prerequisites_pins_sha256"] != sha256_bytes(relative_data[pins_path]):
            raise PackageError("release-manifest와 prerequisite pins checksum이 다릅니다.")

        platform = relative_data.get("platform.txt", b"")
        try:
            version_lines = [line for line in platform.decode("utf-8").splitlines() if line.startswith("version=")]
        except UnicodeDecodeError as error:
            raise PackageError("platform.txt가 UTF-8이 아닙니다.") from error
        if version_lines != [f"version={version}"]:
            raise PackageError("platform.txt version이 archive version과 다릅니다.")
        for path in payload_paths:
            if not include_core_path(path) and not (
                path.startswith("board_package/NU54DK_Zephyr_DTS/")
                and include_board_path(path.removeprefix("board_package/NU54DK_Zephyr_DTS/"))
            ):
                raise PackageError(f"허용목록 밖의 payload가 있습니다: {path}")

        checksums = parse_checksums(relative_data["CHECKSUMS.sha256"], source="CHECKSUMS.sha256")
        checksum_paths = sorted(set(relative_data).difference({"CHECKSUMS.sha256"}), key=lambda p: p.encode("utf-8"))
        if list(checksums) != checksum_paths:
            raise PackageError("CHECKSUMS.sha256 경로 목록이 ZIP과 다릅니다.")
        for path in checksum_paths:
            if checksums[path] != sha256_bytes(relative_data[path]):
                raise PackageError(f"CHECKSUMS.sha256 불일치: {path}")

        sbom = strict_json_loads(relative_data["sbom.spdx.json"], source="sbom.spdx.json")
        if not isinstance(sbom, dict) or sbom.get("spdxVersion") != "SPDX-2.3":
            raise PackageError("SPDX SBOM version이 유효하지 않습니다.")
        sbom_files = sbom.get("files")
        if not isinstance(sbom_files, list):
            raise PackageError("SPDX files가 배열이 아닙니다.")
        sbom_paths = sorted(
            [str(item.get("fileName", "")).removeprefix("./") for item in sbom_files if isinstance(item, dict)],
            key=lambda path: path.encode("utf-8"),
        )
        if sbom_paths != payload_paths:
            raise PackageError("SPDX file 목록이 payload와 다릅니다.")
        for item in sbom_files:
            path = str(item["fileName"]).removeprefix("./")
            hashes = {
                checksum.get("algorithm"): checksum.get("checksumValue")
                for checksum in item.get("checksums", [])
                if isinstance(checksum, dict)
            }
            if hashes.get("SHA256") != sha256_bytes(relative_data[path]):
                raise PackageError(f"SPDX SHA256 불일치: {path}")
            conclusion = item.get("licenseConcluded")
            if path == "board_package/NU54DK_Zephyr_DTS/LICENSE" and conclusion != "MIT":
                raise PackageError("SPDX가 보드 저장소 최상위 LICENSE를 MIT로 기록하지 않았습니다.")
            if (
                path.startswith("board_package/NU54DK_Zephyr_DTS/boards/nucode/nu54dk/")
                and conclusion != "Apache-2.0"
            ):
                raise PackageError(f"SPDX가 파생 보드 파일을 Apache-2.0으로 기록하지 않았습니다: {path}")

        spdx_packages = sbom.get("packages")
        if not isinstance(spdx_packages, list) or not spdx_packages:
            raise PackageError("SPDX packages가 비어 있습니다.")
        package_by_name = {
            item.get("name"): item for item in spdx_packages if isinstance(item, dict)
        }
        external_names = {
            "nRF Util",
            "nRF Util sdk-manager",
            "nRF Connect SDK",
            "Zephyr",
            "nRF Connect SDK Toolchain",
            "pyOCD",
            "SEGGER J-Link Software",
        }
        if (
            len(spdx_packages) != 1 + len(external_names)
            or set(package_by_name) != {"NUCODE NU54DK Zephyr Boards", *external_names}
        ):
            raise PackageError("SPDX 외부 전제조건 package 목록이 계약과 다릅니다.")
        for name in external_names:
            item = package_by_name[name]
            if (
                item.get("filesAnalyzed") is not False
                or item.get("licenseConcluded") != "NOASSERTION"
                or item.get("licenseDeclared") != "NOASSERTION"
                or "external-not-redistributed" not in str(item.get("comment", ""))
            ):
                raise PackageError(f"SPDX 외부 전제조건 분류가 안전하지 않습니다: {name}")

        inventory = strict_json_loads(
            relative_data["license-inventory.json"], source="license-inventory.json"
        )
        if not isinstance(inventory, dict) or inventory.get("schema_version") != 1:
            raise PackageError("license inventory schema가 유효하지 않습니다.")
        if inventory.get("legal_review_status") != "required-before-final-public-release":
            raise PackageError("license inventory가 법률 검토 필요 상태를 보존하지 않습니다.")
        license_files = inventory.get("license_files")
        if not isinstance(license_files, list) or not license_files:
            raise PackageError("license inventory에 라이선스 원문이 없습니다.")
        for item in license_files:
            if not isinstance(item, dict) or item.get("path") not in relative_data:
                raise PackageError("license inventory path가 ZIP에 없습니다.")
            path = item["path"]
            if item.get("sha256") != sha256_bytes(relative_data[path]) or item.get("size") != len(relative_data[path]):
                raise PackageError(f"license inventory checksum 불일치: {path}")
        license_by_path = {item["path"]: item for item in license_files}
        board_mit = "board_package/NU54DK_Zephyr_DTS/LICENSE"
        board_apache = "board_package/NU54DK_Zephyr_DTS/LICENSES/Apache-2.0.txt"
        if license_by_path.get(board_mit, {}).get("license_expression") != "MIT":
            raise PackageError("보드 저장소 최상위 LICENSE를 MIT로 분류하지 않았습니다.")
        if license_by_path.get(board_apache, {}).get("license_expression") != "Apache-2.0":
            raise PackageError("보드 파생 파일용 Apache 원문을 올바르게 분류하지 않았습니다.")
        components = inventory.get("components")
        if not isinstance(components, list):
            raise PackageError("license inventory components가 배열이 아닙니다.")
        component_by_name = {
            item.get("name"): item for item in components if isinstance(item, dict)
        }
        if component_by_name.get("NU54DK Zephyr DTS repository", {}).get("license_expression") != "MIT":
            raise PackageError("보드 저장소 MIT component 범위가 없습니다.")
        derived = component_by_name.get("NU54DK Zephyr derived board definition", {})
        if (
            derived.get("license_expression") != "Apache-2.0"
            or derived.get("scope") != ["board_package/NU54DK_Zephyr_DTS/boards/nucode/nu54dk/**"]
            or derived.get("notice") != "board_package/NU54DK_Zephyr_DTS/NOTICE"
        ):
            raise PackageError("보드 파생 파일 Apache component 범위가 정확하지 않습니다.")
        notice_files = inventory.get("notice_files")
        if not isinstance(notice_files, list) or not notice_files:
            raise PackageError("license inventory notice_files가 비어 있습니다.")
        for item in notice_files:
            if not isinstance(item, dict) or item.get("path") not in relative_data:
                raise PackageError("license inventory notice path가 ZIP에 없습니다.")
            path = item["path"]
            if item.get("sha256") != sha256_bytes(relative_data[path]) or item.get("size") != len(relative_data[path]):
                raise PackageError(f"license inventory notice checksum 불일치: {path}")
        board_notice = "board_package/NU54DK_Zephyr_DTS/NOTICE"
        if board_notice not in {item["path"] for item in notice_files}:
            raise PackageError("보드 Apache 범위 NOTICE 원문이 inventory에 없습니다.")

        pins_path = "tools/nu54-prerequisites/pins.json"
        expected_external = build_external_prerequisites(
            [
                SourceFile(
                    path=pins_path,
                    data=relative_data[pins_path],
                    mode=0o644,
                    origin="core",
                    git_object="0" * 40,
                )
            ]
        )
        if inventory.get("external_prerequisites") != expected_external:
            raise PackageError("외부 전제조건 inventory가 pins 및 고정 계약과 다릅니다.")
        relationships = sbom.get("relationships")
        if not isinstance(relationships, list):
            raise PackageError("SPDX relationships가 배열이 아닙니다.")
        relationship_set = {
            (
                item.get("spdxElementId"),
                item.get("relationshipType"),
                item.get("relatedSpdxElement"),
            )
            for item in relationships
            if isinstance(item, dict)
        }
        core_id = "SPDXRef-Package-NU54DK-Arduino-Core"
        for prerequisite in expected_external:
            package = package_by_name[prerequisite["name"]]
            if (
                package.get("versionInfo") != prerequisite["version"]
                or package.get("downloadLocation") != prerequisite["source"]
            ):
                raise PackageError(f"SPDX 외부 package pin이 inventory와 다릅니다: {prerequisite['name']}")
            package_id = package.get("SPDXID")
            expected_relationship = (
                (core_id, "DEPENDS_ON", package_id)
                if prerequisite["required"]
                else (package_id, "OPTIONAL_DEPENDENCY_OF", core_id)
            )
            if expected_relationship not in relationship_set:
                raise PackageError(f"SPDX 외부 dependency 관계가 없습니다: {prerequisite['name']}")
        return manifest


## @brief 로컬 archive들을 읽어 공식 Arduino package index를 생성합니다.
def generate_index(output_dir: Path, versions: list[str], destination: Path | None = None) -> Path:
    output_dir = output_dir.resolve()
    normalized_versions = sorted(set(versions), key=lambda value: tuple(map(int, value.split("."))), reverse=True)
    if not normalized_versions or any(version not in SUPPORTED_VERSIONS for version in normalized_versions):
        raise PackageError("index에는 지원하는 preview version을 하나 이상 지정해야 합니다.")
    platforms: list[dict[str, Any]] = []
    for version in normalized_versions:
        archive_path = output_dir / archive_filename(version)
        validate_archive(archive_path, expected_version=version)
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
    path = destination.resolve() if destination else output_dir / INDEX_FILENAME
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
        raise PackageError("preview package index는 NCS/toolchain을 재배포하는 tools 항목을 포함하지 않습니다.")
    platforms = package.get("platforms")
    if not isinstance(platforms, list) or not platforms:
        raise PackageError("package index platforms가 비어 있습니다.")
    versions: list[str] = []
    for platform in platforms:
        if not isinstance(platform, dict):
            raise PackageError("package index platform record가 object가 아닙니다.")
        version = platform.get("version")
        if version not in SUPPORTED_VERSIONS or version in versions:
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
            validate_archive(archive_path, expected_version=version)
            if checksum != f"SHA-256:{sha256_bytes(archive_path.read_bytes())}":
                raise PackageError(f"package index와 archive checksum이 다릅니다: {version}")
            if size != str(archive_path.stat().st_size):
                raise PackageError(f"package index와 archive size가 다릅니다: {version}")
    expected_order = sorted(versions, key=lambda value: tuple(map(int, value.split("."))), reverse=True)
    if versions != expected_order:
        raise PackageError("package index version은 최신 순서여야 합니다.")
    return document


## @brief CLI 인자를 정의합니다.
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="NU54DK Boards Manager package builder/validator")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build", help="exact Git commit에서 재현 가능한 package를 생성합니다.")
    build.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    build.add_argument("--output-dir", type=Path, required=True)
    build.add_argument("--version", choices=SUPPORTED_VERSIONS, required=True)
    build.add_argument("--commit", default="HEAD")
    build.add_argument("--update-index", action="store_true")

    validate = subparsers.add_parser("validate", help="package archive를 엄격하게 검증합니다.")
    validate.add_argument("--archive", type=Path, required=True)
    validate.add_argument("--expected-version", choices=SUPPORTED_VERSIONS)
    validate.add_argument("--expected-commit")

    index = subparsers.add_parser("index", help="로컬 archive로 package index를 생성합니다.")
    index.add_argument("--output-dir", type=Path, required=True)
    index.add_argument("--versions", nargs="+", choices=SUPPORTED_VERSIONS, required=True)
    index.add_argument("--output", type=Path)

    validate_index_parser = subparsers.add_parser("validate-index", help="package index를 검증합니다.")
    validate_index_parser.add_argument("--index", type=Path, required=True)
    validate_index_parser.add_argument("--artifact-dir", type=Path)
    return parser


## @brief CLI 진입점입니다.
def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        if arguments.command == "build":
            paths = build_package(
                arguments.repo_root, arguments.output_dir, arguments.version, arguments.commit
            )
            if arguments.update_index:
                available = [
                    version
                    for version in SUPPORTED_VERSIONS
                    if (arguments.output_dir / archive_filename(version)).is_file()
                ]
                paths["index"] = generate_index(arguments.output_dir, available)
            for name, path in paths.items():
                print(f"NU54_PACKAGE_{name.upper()}={path}")
        elif arguments.command == "validate":
            manifest = validate_archive(
                arguments.archive,
                expected_version=arguments.expected_version,
                expected_commit=arguments.expected_commit,
            )
            print(f"NU54_PACKAGE_VALID={manifest['version']}:{manifest['core_revision']}")
        elif arguments.command == "index":
            path = generate_index(arguments.output_dir, arguments.versions, arguments.output)
            print(f"NU54_PACKAGE_INDEX={path}")
        elif arguments.command == "validate-index":
            document = validate_index(arguments.index, artifact_dir=arguments.artifact_dir)
            print(f"NU54_PACKAGE_INDEX_VALID={len(document['packages'][0]['platforms'])}")
        return 0
    except PackageError as error:
        print(f"NU54_PACKAGE_ERROR={error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
