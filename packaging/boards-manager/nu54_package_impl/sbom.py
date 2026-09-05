"""! @brief 패키저의 SPDX 관계와 provenance 생성 책임입니다. """
from __future__ import annotations
from typing import Any, Iterable
import hashlib
from .channels import (
    archive_filename,
    release_asset_url,
)
from .licenses import (
    concluded_file_license,
    declared_spdx_identifiers,
)
from .model import (
    MAINTAINER,
    REPOSITORY_URL,
    SourceFile,
)
from .serialization import (
    sha1_bytes,
    sha256_bytes,
)


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
