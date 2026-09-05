"""! @brief 패키저의 license 수집·판정과 외부 prerequisite 책임입니다. """
from __future__ import annotations
from typing import Any, Iterable
import re
from .channels import (
    legal_review_status,
)
from .model import (
    BOARD_REPOSITORY_URL,
    NCS_REVISION,
    NCS_VERSION,
    PackageError,
    REPOSITORY_URL,
    SourceFile,
    TOOLCHAIN_BUNDLE_ID,
    ZEPHYR_REVISION,
    ZEPHYR_VERSION,
)
from .serialization import (
    sha256_bytes,
    strict_json_loads,
)


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
def build_external_prerequisites(
    files: list[SourceFile], version: str
) -> list[dict[str, Any]]:
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
        "legal_review_status": legal_review_status(version),
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
        "legal_review_status": legal_review_status(version),
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
        "external_prerequisites": build_external_prerequisites(files, version),
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
