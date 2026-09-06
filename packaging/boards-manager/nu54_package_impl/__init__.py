"""! @brief 기존 Python entrypoint가 제공하던 이름을 명시적으로 보존합니다. """
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable
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
from . import model
from .model import (
    LEGACY_PREVIEW_VERSIONS,
    FAILED_M10_PREVIEW_VERSIONS,
    SAFE_PREVIEW_VERSIONS,
    SUPPORTED_VERSIONS,
    RELEASE_CANDIDATE_VERSIONS,
    STABLE_VERSIONS,
    STABLE_RELEASE_COMMITS,
    PUBLISHED_STABLE_ARCHIVE_IDENTITIES,
    PACKAGE_VERSIONS,
    WINDOWS_SAFE_VERSIONS,
    VENDOR,
    ARCHITECTURE,
    MAINTAINER,
    CONTACT_EMAIL,
    REPOSITORY_URL,
    BOARD_REPOSITORY_URL,
    INDEX_FILENAME,
    RC_INDEX_FILENAME,
    STABLE_INDEX_FILENAME,
    LEGAL_REVIEW_REQUIRED,
    STABLE_LEGAL_REVIEW_STATUSES,
    NCS_VERSION,
    NCS_REVISION,
    ZEPHYR_VERSION,
    ZEPHYR_REVISION,
    TOOLCHAIN_BUNDLE_ID,
    ZIP_TIMESTAMP,
    MAX_ARCHIVE_SIZE,
    MAX_FILE_SIZE,
    METADATA_FILES,
    PackageError,
    SourceFile,
)
from . import serialization
from .serialization import (
    strict_json_loads,
    canonical_json,
    sha256_bytes,
    sha1_bytes,
    normalize_runtime_payload_bytes,
    runtime_payload_sha256,
    build_internal_checksums,
    parse_checksums,
)
from . import inputs
from .inputs import (
    run_checked,
    resolve_commit,
    commit_timestamp,
    git_tree_entries,
    git_blob,
    ensure_safe_relative_path,
    include_core_path,
    include_board_path,
    rewrite_platform_version,
    rewrite_windows_command_line_endings,
    collect_source_files,
)
from . import licenses
from .licenses import (
    declared_spdx_identifiers,
    build_external_prerequisites,
    build_license_inventory,
    build_third_party_notices,
    concluded_file_license,
)
from . import sbom
from .sbom import (
    build_spdx,
)
from . import channels
from .channels import (
    legal_review_status,
    archive_filename,
    release_channel,
    version_sort_key,
    release_tag,
    release_asset_url,
)
from . import manifest
from .manifest import (
    build_release_manifest,
)
from . import archive
from .archive import (
    write_deterministic_zip,
    write_external_checksums,
)
from . import validation
from .validation import (
    validate_archive,
    validate_index_archive,
)
from . import index
from .index import (
    generate_index,
    validate_index,
)
from . import build
from .build import (
    build_package,
)
from . import cli
from .cli import (
    build_parser,
    main,
)
__all__ = ['argparse', 'dt', 'hashlib', 'json', 'os', 're', 'stat', 'subprocess', 'sys', 'zipfile', 'dataclass', 'Path', 'PurePosixPath', 'Any', 'Iterable', 'LEGACY_PREVIEW_VERSIONS', 'FAILED_M10_PREVIEW_VERSIONS', 'SAFE_PREVIEW_VERSIONS', 'SUPPORTED_VERSIONS', 'RELEASE_CANDIDATE_VERSIONS', 'STABLE_VERSIONS', 'STABLE_RELEASE_COMMITS', 'PUBLISHED_STABLE_ARCHIVE_IDENTITIES', 'PACKAGE_VERSIONS', 'WINDOWS_SAFE_VERSIONS', 'VENDOR', 'ARCHITECTURE', 'MAINTAINER', 'CONTACT_EMAIL', 'REPOSITORY_URL', 'BOARD_REPOSITORY_URL', 'INDEX_FILENAME', 'RC_INDEX_FILENAME', 'STABLE_INDEX_FILENAME', 'LEGAL_REVIEW_REQUIRED', 'STABLE_LEGAL_REVIEW_STATUSES', 'NCS_VERSION', 'NCS_REVISION', 'ZEPHYR_VERSION', 'ZEPHYR_REVISION', 'TOOLCHAIN_BUNDLE_ID', 'ZIP_TIMESTAMP', 'MAX_ARCHIVE_SIZE', 'MAX_FILE_SIZE', 'METADATA_FILES', 'PackageError', 'SourceFile', 'strict_json_loads', 'canonical_json', 'sha256_bytes', 'sha1_bytes', 'normalize_runtime_payload_bytes', 'runtime_payload_sha256', 'build_internal_checksums', 'parse_checksums', 'run_checked', 'resolve_commit', 'commit_timestamp', 'git_tree_entries', 'git_blob', 'ensure_safe_relative_path', 'include_core_path', 'include_board_path', 'rewrite_platform_version', 'rewrite_windows_command_line_endings', 'collect_source_files', 'declared_spdx_identifiers', 'build_external_prerequisites', 'build_license_inventory', 'build_third_party_notices', 'concluded_file_license', 'build_spdx', 'legal_review_status', 'archive_filename', 'release_channel', 'version_sort_key', 'release_tag', 'release_asset_url', 'build_release_manifest', 'write_deterministic_zip', 'write_external_checksums', 'validate_archive', 'validate_index_archive', 'generate_index', 'validate_index', 'build_package', 'build_parser', 'main']
