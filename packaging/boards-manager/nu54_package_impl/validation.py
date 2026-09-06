"""! @brief 패키저의 실제 archive 내용과 공개 identity 검증 책임입니다. """
from __future__ import annotations
from . import model
from pathlib import Path, PurePosixPath
from typing import Any, Iterable
import re
import stat
import zipfile
from .channels import (
    archive_filename,
    legal_review_status,
    release_asset_url,
    release_tag,
)
from .inputs import (
    ensure_safe_relative_path,
    include_board_path,
    include_core_path,
    rewrite_windows_command_line_endings,
)
from .licenses import (
    build_external_prerequisites,
)
from .model import (
    ARCHITECTURE,
    BOARD_REPOSITORY_URL,
    MAX_ARCHIVE_SIZE,
    MAX_FILE_SIZE,
    METADATA_FILES,
    NCS_REVISION,
    NCS_VERSION,
    PUBLISHED_STABLE_ARCHIVE_IDENTITIES,
    PackageError,
    REPOSITORY_URL,
    SourceFile,
    TOOLCHAIN_BUNDLE_ID,
    VENDOR,
    ZEPHYR_REVISION,
    ZEPHYR_VERSION,
    ZIP_TIMESTAMP,
)
from .serialization import (
    parse_checksums,
    runtime_payload_sha256,
    sha256_bytes,
    strict_json_loads,
)


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
        if version not in model.PACKAGE_VERSIONS or (
            expected_version is not None and version != expected_version
        ):
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
        if version in model.WINDOWS_SAFE_VERSIONS:
            required_manifest_fields["runtime_payload_sha256"] = r"[0-9a-f]{64}"
        for field, pattern in required_manifest_fields.items():
            value = manifest.get(field)
            if not isinstance(value, str) or not re.fullmatch(pattern, value):
                raise PackageError(f"release-manifest {field}가 유효하지 않습니다: {value!r}")
        if expected_commit is not None and manifest["core_revision"] != expected_commit:
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
            "source_policy": (
                "exact-commit-plus-declared-platform-version-and-windows-crlf-rewrites"
                if version in model.WINDOWS_SAFE_VERSIONS
                else "exact-commit-plus-declared-platform-version-rewrite"
            ),
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
        records_by_path: dict[str, dict[str, Any]] = {}
        for record in records:
            path = record["path"]
            records_by_path[path] = record
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
        if version in model.WINDOWS_SAFE_VERSIONS:
            payload_fingerprint = runtime_payload_sha256(
                (
                    path,
                    relative_data[path],
                    stat.S_IMODE((relative_infos[path].external_attr >> 16) & 0xFFFF),
                )
                for path in payload_paths
            )
            if manifest.get("runtime_payload_sha256") != payload_fingerprint:
                raise PackageError("release-manifest runtime payload fingerprint가 ZIP byte와 다릅니다.")
            windows_scripts = sorted(
                path
                for path in payload_paths
                if PurePosixPath(path).suffix.casefold() in {".bat", ".cmd"}
            )
            required_windows_scripts = {
                "post_install.bat",
                "tools/nu54-builder/nu54-builder.cmd",
            }
            if not required_windows_scripts.issubset(windows_scripts):
                raise PackageError("Windows-safe package에 필수 launcher가 없습니다.")
            for path in windows_scripts:
                data = relative_data[path]
                if data != rewrite_windows_command_line_endings(data, path):
                    raise PackageError(f"Windows-safe command script가 strict CRLF가 아닙니다: {path}")
                if records_by_path[path].get("transformation") != "windows-crlf":
                    raise PackageError(f"Windows-safe command script 변환 provenance가 없습니다: {path}")
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
        if inventory.get("legal_review_status") != legal_review_status(version):
            raise PackageError("license inventory의 프로젝트 법률 검토 상태가 버전 계약과 다릅니다.")
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
            ],
            version,
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


## @brief index에 넣을 archive를 현재 계약 또는 공개된 불변 byte 계약으로 검증합니다.
def validate_index_archive(archive_path: Path, version: str) -> None:
    identity = PUBLISHED_STABLE_ARCHIVE_IDENTITIES.get(version)
    if identity is None:
        validate_archive(archive_path, expected_version=version)
        return
    if not archive_path.is_file():
        raise PackageError(f"공개 stable archive가 없습니다: {archive_path}")
    data = archive_path.read_bytes()
    if len(data) != identity["size"] or sha256_bytes(data) != identity["sha256"]:
        raise PackageError(f"공개 stable archive의 불변 byte identity가 다릅니다: {version}")
