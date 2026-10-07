#!/usr/bin/env python3
"""! @brief M33-W05 Windows clean 설치본의 공개 예제를 전수 검증합니다. """

from __future__ import annotations

from argparse import ArgumentParser, Namespace
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from typing import Any, Callable, Sequence


ROOT = Path(__file__).resolve().parents[2]
EXPECTED_EXAMPLES = 204
MAX_DIAGNOSTIC_RETESTS_PER_BUILD = 1
CI_SHARD_COUNT = 8
CI_SHARD_ASSIGNMENT = "sorted_identity_modulo_v1"
TARGET_BOARD = "nrf54l15dk/nrf54l15/cpuapp/nu54dk"
ALLOWED_PROFILES = frozenset({
    "standard",
    "ble",
    "adaptive",
    "fabric",
    "secure_ble_dfu",
    "ble_audio_io",
    "radio_ieee802154",
    "radio_esb",
    "coexistence_ble_mesh",
    "coexistence_ble_154",
    "coexistence_ble_esb",
    "external_coexistence",
})
NEGATIVE_PROFILE_MATRIX = (
    {
        "id": "fabric_under_standard",
        "identity": "NUCODE_Peripheral_Fabric/AdcContinuousDma",
        "profile": "standard",
        "marker": "[NU54:E_FEATURE_PROFILE]",
    },
    {
        "id": "radio_154_under_ble",
        "identity": "NUCODE_Radio_IEEE802154/Radio154Transmitter",
        "profile": "ble",
        "marker": "[NU54:E_FEATURE_PROFILE]",
    },
    {
        "id": "radio_esb_under_ble",
        "identity": "NUCODE_Radio_ESB/EsbPtx",
        "profile": "ble",
        "marker": "[NU54:E_FEATURE_PROFILE]",
    },
    {
        "id": "ble_154_coexistence_under_radio_only",
        "identity": "NUCODE_Radio_Coexistence/Ble154Coexistence",
        "profile": "radio_ieee802154",
        "marker": "[NU54:E_FEATURE_PROFILE]",
    },
    {
        "id": "ble_esb_coexistence_under_radio_only",
        "identity": "NUCODE_Radio_Coexistence/BleEsbCoexistence",
        "profile": "radio_esb",
        "marker": "[NU54:E_FEATURE_PROFILE]",
    },
    {
        "id": "mesh_coexistence_under_ble",
        "identity": "NUCODE_Radio_Coexistence/BleMeshCoexistence",
        "profile": "ble",
        "marker": "[NU54:E_FEATURE_PROFILE]",
    },
    {
        "id": "external_coexistence_under_ble",
        "identity": "NUCODE_Radio_Coexistence/RadioCoexistenceOneWire",
        "profile": "ble",
        "marker": "[NU54:E_FEATURE_PROFILE]",
    },
    {
        "id": "secure_dfu_under_ble",
        "identity": "NUCODE_BLE_DFU/SecureDfuPeripheral",
        "profile": "ble",
        "marker": "[NU54:E_FEATURE_PROFILE]",
    },
    {
        "id": "external_audio_under_standard",
        "identity": "NUCODE_BLE_Audio/ExternalPdmMicrophoneSource",
        "profile": "standard",
        "marker": "[NU54:E_FEATURE_PROFILE]",
    },
)


class M33W05Failure(RuntimeError):
    """! @brief W05 설치 예제 계약 위반입니다. """


def utc_now() -> str:
    """! @brief 현재 UTC 시각을 증거용 문자열로 반환합니다. """

    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    """! @brief 파일의 SHA-256을 계산합니다. """

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def path_identity(path: Path) -> str:
    """! @brief 공개 증거에 원문 경로 대신 기록할 경로 지문을 계산합니다. """

    normalized = str(path.resolve()).replace("\\", "/").casefold()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    """! @brief 중복 key를 거부하며 JSON object를 읽습니다. """

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        document: dict[str, Any] = {}
        for key, value in pairs:
            if key in document:
                raise M33W05Failure(f"중복 JSON key입니다: {path}: {key}")
            document[key] = value
        return document

    try:
        document = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicates
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise M33W05Failure(f"JSON을 읽지 못했습니다: {path}: {error}") from error
    if not isinstance(document, dict):
        raise M33W05Failure(f"JSON root가 object가 아닙니다: {path}")
    return document


def tree_fingerprint(directory: Path) -> tuple[int, str]:
    """! @brief 이름과 내용을 포함한 directory tree 지문을 계산합니다. """

    files = sorted(
        (path for path in directory.rglob("*") if path.is_file()),
        key=lambda path: path.relative_to(directory).as_posix().casefold(),
    )
    digest = hashlib.sha256()
    for path in files:
        relative = path.relative_to(directory).as_posix()
        digest.update(relative.encode("utf-8") + b"\0")
        digest.update(bytes.fromhex(sha256_file(path)))
    return len(files), digest.hexdigest()


def public_examples(platform: Path) -> dict[str, Path]:
    """! @brief platform의 공개 Arduino 예제를 identity별로 열거합니다. """

    result: dict[str, Path] = {}
    libraries = platform / "libraries"
    if not libraries.is_dir():
        raise M33W05Failure(f"libraries directory가 없습니다: {libraries}")
    for library in sorted(libraries.iterdir(), key=lambda path: path.name.casefold()):
        if not library.is_dir() or not (library / "library.properties").is_file():
            continue
        examples = library / "examples"
        if not examples.is_dir():
            continue
        for example in sorted(examples.iterdir(), key=lambda path: path.name.casefold()):
            sketch = example / f"{example.name}.ino"
            if not example.is_dir() or not sketch.is_file():
                continue
            identity = f"{library.name}/{example.name}"
            if identity in result:
                raise M33W05Failure(f"중복 공개 예제 identity입니다: {identity}")
            result[identity] = example.resolve()
    return result


def load_catalog(platform: Path, expected_count: int = EXPECTED_EXAMPLES) -> dict[str, dict]:
    """! @brief metadata와 실제 공개 예제의 identity·profile·역할을 대조합니다. """

    metadata_path = platform / "libraries" / "example-metadata.json"
    document = read_json(metadata_path)
    records = document.get("examples")
    if (
        document.get("schema_version") != 1
        or document.get("example_count") != expected_count
        or not isinstance(records, dict)
        or len(records) != expected_count
    ):
        raise M33W05Failure("예제 metadata schema 또는 분모가 잘못되었습니다")
    discovered = public_examples(platform)
    if len(discovered) != expected_count or set(discovered) != set(records):
        raise M33W05Failure("metadata와 공개 예제 identity 집합이 다릅니다")
    result: dict[str, dict] = {}
    for identity, directory in discovered.items():
        record = records[identity]
        if not isinstance(record, dict):
            raise M33W05Failure(f"예제 metadata record가 object가 아닙니다: {identity}")
        expected_path = (
            Path("libraries") / identity.split("/", 1)[0] / "examples"
            / identity.split("/", 1)[1] / f"{identity.split('/', 1)[1]}.ino"
        ).as_posix()
        profile = record.get("recommended_profile")
        alternatives = record.get("alternative_profiles")
        board_count = record.get("board_count")
        roles = record.get("roles")
        if record.get("path") != expected_path:
            raise M33W05Failure(f"예제 상대 경로가 잘못되었습니다: {identity}")
        if profile not in ALLOWED_PROFILES:
            raise M33W05Failure(f"예제 권장 profile이 잘못되었습니다: {identity}")
        if not isinstance(alternatives, list) or any(
            not isinstance(alternative, dict)
            or alternative.get("profile") not in ALLOWED_PROFILES
            for alternative in alternatives
        ):
            raise M33W05Failure(f"예제 대안 profile이 잘못되었습니다: {identity}")
        if (
            not isinstance(board_count, int)
            or board_count < 1
            or not isinstance(roles, list)
            or len(roles) != board_count
            or any(not isinstance(role, str) or not role.strip() for role in roles)
        ):
            raise M33W05Failure(f"예제 역할 분모가 잘못되었습니다: {identity}")
        result[identity] = {
            "directory": directory,
            "profile": profile,
            "alternative_profiles": [
                alternative["profile"] for alternative in alternatives
            ],
            "board_count": board_count,
            "roles": list(roles),
            "sketch_sha256": sha256_file(directory / f"{directory.name}.ino"),
        }
    return result


def library_name(properties: Path) -> str:
    """! @brief library.properties의 단일 name 값을 반환합니다. """

    names = []
    for line in properties.read_text(encoding="utf-8").splitlines():
        if line.startswith("name="):
            names.append(line.split("=", 1)[1].strip())
    if len(names) != 1 or not names[0]:
        raise M33W05Failure(f"library name이 정확히 하나가 아닙니다: {properties}")
    return names[0]


def discover_library(
    cli: Path,
    config: Path,
    source: Path,
    installed: Path,
    library_directory: str,
    expected_identities: set[str],
) -> dict[str, Any]:
    """! @brief Arduino CLI 발견 결과와 source/install library tree를 대조합니다. """

    source_library = source / "libraries" / library_directory
    installed_library = installed / "libraries" / library_directory
    if installed_library.resolve().is_relative_to(source.resolve()):
        raise M33W05Failure("설치 library가 source tree 안에 있습니다")
    source_count, source_hash = tree_fingerprint(source_library)
    installed_count, installed_hash = tree_fingerprint(installed_library)
    if (source_count, source_hash) != (installed_count, installed_hash):
        raise M33W05Failure(f"source/install library tree가 다릅니다: {library_directory}")
    name = library_name(source_library / "library.properties")
    try:
        completed = subprocess.run(
            (
                str(cli), "lib", "examples", name, "--json",
                "--config-file", str(config),
            ),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise M33W05Failure(f"Arduino CLI example discovery timeout: {name}") from error
    if completed.returncode != 0:
        raise M33W05Failure(f"Arduino CLI example discovery 실패: {name}")
    listing = json.loads(completed.stdout)
    entries = listing.get("examples") if isinstance(listing, dict) else None
    if not isinstance(entries, list) or len(entries) != 1:
        raise M33W05Failure(f"설치 library가 정확히 하나가 아닙니다: {name}")
    entry = entries[0]
    library = entry.get("library") if isinstance(entry, dict) else None
    if not isinstance(library, dict) or library.get("name") != name:
        raise M33W05Failure(f"Arduino CLI library identity가 다릅니다: {name}")
    install_dir = Path(str(library.get("install_dir", ""))).resolve()
    if install_dir != installed_library.resolve():
        raise M33W05Failure(f"Arduino CLI가 다른 설치 library를 선택했습니다: {name}")
    paths = entry.get("examples")
    if not isinstance(paths, list):
        raise M33W05Failure(f"Arduino CLI example 목록이 배열이 아닙니다: {name}")
    identities: set[str] = set()
    for value in paths:
        example = Path(str(value)).resolve()
        if example.parent != installed_library.resolve() / "examples":
            raise M33W05Failure(f"설치 예제 경로가 library 밖입니다: {name}")
        sketch = example / f"{example.name}.ino"
        if not sketch.is_file():
            raise M33W05Failure(f"설치 sketch가 없습니다: {name}/{example.name}")
        identities.add(f"{library_directory}/{example.name}")
    if identities != expected_identities or len(paths) != len(identities):
        raise M33W05Failure(f"설치 예제 discovery 분모가 다릅니다: {name}")
    return {
        "directory": library_directory,
        "name": name,
        "example_count": len(identities),
        "file_count": source_count,
        "tree_sha256": source_hash,
        "container_platform": entry.get("library", {}).get("container_platform"),
    }


def discover_installation(
    cli: Path,
    config: Path,
    source: Path,
    installed: Path,
    catalog: dict[str, dict],
) -> list[dict[str, Any]]:
    """! @brief 설치된 모든 공개 library의 예제 발견과 tree hash를 검사합니다. """

    groups: dict[str, set[str]] = {}
    for identity in catalog:
        library = identity.split("/", 1)[0]
        groups.setdefault(library, set()).add(identity)
    rows = [
        discover_library(
            cli, config, source, installed, library, groups[library]
        )
        for library in sorted(groups, key=str.casefold)
    ]
    if sum(row["example_count"] for row in rows) != EXPECTED_EXAMPLES:
        raise M33W05Failure("설치 예제 discovery 전체 분모가 204가 아닙니다")
    return rows


def git_output(repository: Path, *arguments: str) -> str:
    """! @brief 지정 repository의 Git 출력을 반환합니다. """

    try:
        return subprocess.check_output(
            ("git", "-C", str(repository), *arguments),
            text=True,
            encoding="utf-8",
            errors="strict",
            timeout=30,
        ).strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        raise M33W05Failure(f"Git 검사에 실패했습니다: {repository}") from error


def verify_fixed_inputs(source: Path, sdk_root: Path) -> dict[str, str]:
    """! @brief clean source와 고정 NCS/Zephyr/board revision을 검사합니다. """

    lock = read_json(source / "tools" / "ci" / "ncs-3.4.0.lock.json")
    if git_output(source, "status", "--porcelain"):
        raise M33W05Failure("exact 설치본 검사에는 clean source가 필요합니다")
    revision = git_output(source, "rev-parse", "HEAD")
    nrf_revision = git_output(sdk_root / "nrf", "rev-parse", "HEAD")
    zephyr_revision = git_output(sdk_root / "zephyr", "rev-parse", "HEAD")
    board_path = source / "board_package" / "NU54DK_Zephyr_DTS"
    board_revision = git_output(board_path, "rev-parse", "HEAD")
    expected = {
        "nrf_revision": lock["ncs"]["revision"],
        "zephyr_revision": lock["zephyr"]["revision"],
        "board_revision": lock["board"]["revision"],
    }
    actual = {
        "nrf_revision": nrf_revision,
        "zephyr_revision": zephyr_revision,
        "board_revision": board_revision,
    }
    if actual != expected:
        raise M33W05Failure("NCS 3.4.0 또는 board revision이 고정 lock과 다릅니다")
    return {"source_revision": revision, **actual}


def verify_installed_snapshot(installed: Path, source_revision: str) -> str:
    """! @brief 설치 platform이 같은 exact commit의 clean 독립 checkout인지 검사합니다. """

    if git_output(installed, "status", "--porcelain"):
        raise M33W05Failure("설치 platform checkout이 clean 상태가 아닙니다")
    revision = git_output(installed, "rev-parse", "HEAD")
    if revision != source_revision:
        raise M33W05Failure("설치 platform revision이 exact source와 다릅니다")
    return revision


def fqbn(prefix: str, profile: str) -> str:
    """! @brief profile을 포함한 NU54DK FQBN을 반환합니다. """

    if profile not in ALLOWED_PROFILES:
        raise M33W05Failure(f"허용하지 않는 profile입니다: {profile}")
    return f"{prefix}:feature_set={profile}"


def redact_text(text: str, replacements: Sequence[Path]) -> str:
    """! @brief 로그 tail에서 환경별 절대 경로를 제거합니다. """

    result = text
    for index, path in enumerate(replacements):
        raw = str(path.resolve())
        token = f"<PATH_{index}>"
        for value in {raw, raw.replace("\\", "/")}:
            result = result.replace(value, token)
    result = re.sub(
        r"(?i)(?<![A-Za-z0-9_])[A-Z]:[\\/][^\s\"'`]+",
        "<ABSOLUTE_PATH>",
        result,
    )
    result = re.sub(
        r"(?<![A-Za-z0-9_])/(?:home|Users)/[^\s\"'`]+",
        "<ABSOLUTE_PATH>",
        result,
    )
    return result


def validate_public_values(value: object, location: str = "$") -> None:
    """! @brief 공개 evidence의 절대 경로·UID·secret 노출을 거부합니다. """

    sensitive_keys = {
        "uid", "raw_uid", "device_uid", "hardware_uid", "serial_number",
        "secret", "password", "passwd", "token", "access_token",
        "refresh_token", "api_key", "private_key", "credential", "credentials",
    }
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).casefold().replace("-", "_")
            secret_key = re.search(
                r"(?:^|_)(?:secret|password|passwd|token|api_key|private_key|"
                r"credential)(?:_|$)",
                normalized,
            )
            raw_uid_key = re.search(
                r"(?:^|_)(?:raw_uid|raw_device_uid|device_uid|hardware_uid|uid|"
                r"serial_number)(?:_|$)",
                normalized,
            )
            if (
                normalized in sensitive_keys
                or secret_key is not None
                or raw_uid_key is not None and not normalized.endswith("_sha256")
            ):
                raise M33W05Failure(f"민감 evidence field입니다: {location}.{key}")
            validate_public_values(child, f"{location}.{key}")
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            validate_public_values(child, f"{location}[{index}]")
        return
    if not isinstance(value, str):
        return
    path_patterns = (
        r"(?i)(?<![A-Za-z0-9_])[A-Z]:[\\/]",
        r"(?:^|[\s\"'`])\\\\[^\\/\s]+[\\/]",
        r"(?i)(?:^|[\s\"'`])/(?:Users|home|tmp|var/tmp|private|Volumes|mnt|opt)/",
    )
    secret_patterns = (
        r"(?i)-----BEGIN [^-]*PRIVATE KEY-----",
        r"(?i)\b(?:password|passwd|secret|token|api[_ -]?key)\s*[:=]\s*\S+",
        r"(?i)\bauthorization\s*[:=]\s*(?:bearer\s+)?\S+",
        r"(?i)\b(?:raw[_ -]?uid|device[_ -]?uid|hardware[_ -]?uid|uid)"
        r"\s*[:=]\s*[0-9a-f-]{8,}",
    )
    if any(re.search(pattern, value) is not None for pattern in path_patterns):
        raise M33W05Failure(f"evidence 절대 경로 노출입니다: {location}")
    if any(re.search(pattern, value) is not None for pattern in secret_patterns):
        raise M33W05Failure(f"evidence secret 또는 raw UID 노출입니다: {location}")


def validate_build_manifest(
    manifest_path: Path,
    build_path: Path,
    sketch: Path,
    expected_fqbn: str,
    fixed: dict[str, str],
) -> tuple[str, str]:
    """! @brief build manifest의 고정 입력과 primary HEX hash를 검증합니다. """

    manifest = read_json(manifest_path)
    input_manifest = manifest.get("cache", {}).get("input_manifest", {})
    ncs = input_manifest.get("ncs", {})
    board = input_manifest.get("board_package", {})
    sketch_record = input_manifest.get("sketch", {})
    if manifest.get("fqbn") != expected_fqbn or manifest.get("board") != TARGET_BOARD:
        raise M33W05Failure("build manifest의 FQBN 또는 board가 다릅니다")
    if (
        ncs.get("nrf_revision") != fixed["nrf_revision"]
        or ncs.get("zephyr_revision") != fixed["zephyr_revision"]
        or board.get("revision") != fixed["board_revision"]
    ):
        raise M33W05Failure("build manifest의 고정 revision이 다릅니다")
    if Path(str(sketch_record.get("root", ""))).resolve() != sketch.resolve():
        raise M33W05Failure("build manifest가 설치 sketch를 가리키지 않습니다")
    hex_record = manifest.get("artifacts", {}).get("hex", {})
    image = Path(str(hex_record.get("path", ""))).resolve()
    if (
        not image.is_relative_to(build_path.resolve())
        or not image.is_file()
        or image.stat().st_size == 0
        or hex_record.get("sha256") != sha256_file(image)
    ):
        raise M33W05Failure("build manifest의 primary HEX가 잘못되었습니다")
    return sha256_file(manifest_path), sha256_file(image)


def compile_example(
    cli: Path,
    config: Path,
    fqbn_prefix: str,
    identity: str,
    sketch: Path,
    profile: str,
    build_path: Path,
    log_path: Path,
    timeout: int,
    fixed: dict[str, str],
    redactions: Sequence[Path],
) -> dict[str, Any]:
    """! @brief 설치 예제 하나를 fresh build directory에서 컴파일합니다. """

    build_path.mkdir(parents=True)
    started = time.monotonic()
    command = (
        str(cli), "compile", "--config-file", str(config),
        "--fqbn", fqbn(fqbn_prefix, profile),
        "--build-path", str(build_path), str(sketch),
    )
    timed_out = False
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        combined = completed.stdout + completed.stderr
        exit_code = completed.returncode
    except subprocess.TimeoutExpired as error:
        timed_out = True
        stdout = error.stdout.decode(errors="replace") if isinstance(error.stdout, bytes) else error.stdout
        stderr = error.stderr.decode(errors="replace") if isinstance(error.stderr, bytes) else error.stderr
        combined = (stdout or "") + (stderr or "")
        exit_code = None
    log_path.write_text(combined, encoding="utf-8", newline="\n")
    manifests = list(build_path.glob("*.nu54-build.json"))
    manifest_sha256 = None
    hex_sha256 = None
    failure = None
    if not timed_out and exit_code == 0 and len(manifests) == 1:
        try:
            manifest_sha256, hex_sha256 = validate_build_manifest(
                manifests[0], build_path, sketch, fqbn(fqbn_prefix, profile), fixed
            )
        except M33W05Failure as error:
            failure = str(error)
    elif timed_out:
        failure = "compile_timeout"
    else:
        failure = "compile_or_manifest_failure"
    passed = exit_code == 0 and not timed_out and failure is None
    tail = redact_text("\n".join(combined.splitlines()[-20:]), redactions)
    return {
        "identity": identity,
        "profile": profile,
        "status": "PASS" if passed else "FAIL",
        "exit_code": exit_code,
        "timed_out": timed_out,
        "elapsed_s": round(time.monotonic() - started, 3),
        "sketch_sha256": sha256_file(sketch / f"{sketch.name}.ino"),
        "log_sha256": sha256_file(log_path),
        "manifest_sha256": manifest_sha256,
        "hex_sha256": hex_sha256,
        "failure": failure,
        "failure_tail": [] if passed else tail.splitlines(),
    }


def compile_negative(
    cli: Path,
    config: Path,
    fqbn_prefix: str,
    case: dict[str, str],
    sketch: Path,
    build_path: Path,
    log_path: Path,
    timeout: int,
    redactions: Sequence[Path],
) -> dict[str, Any]:
    """! @brief 잘못된 profile 조합이 명시적 오류로 유한하게 거부되는지 검사합니다. """

    build_path.mkdir(parents=True)
    started = time.monotonic()
    timed_out = False
    try:
        completed = subprocess.run(
            (
                str(cli), "compile", "--config-file", str(config),
                "--fqbn", fqbn(fqbn_prefix, case["profile"]),
                "--build-path", str(build_path), str(sketch),
            ),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        combined = completed.stdout + completed.stderr
        exit_code = completed.returncode
    except subprocess.TimeoutExpired as error:
        timed_out = True
        stdout = error.stdout.decode(errors="replace") if isinstance(error.stdout, bytes) else error.stdout
        stderr = error.stderr.decode(errors="replace") if isinstance(error.stderr, bytes) else error.stderr
        combined = (stdout or "") + (stderr or "")
        exit_code = None
    log_path.write_text(combined, encoding="utf-8", newline="\n")
    artifacts = list(build_path.glob("*.ino.hex")) + list(
        build_path.glob("*.nu54-build.json")
    )
    passed = (
        not timed_out
        and exit_code is not None
        and exit_code != 0
        and case["marker"] in combined
        and not artifacts
    )
    tail = redact_text("\n".join(combined.splitlines()[-20:]), redactions)
    return {
        "id": case["id"],
        "identity": case["identity"],
        "rejected_profile": case["profile"],
        "expected_marker": case["marker"],
        "status": "PASS" if passed else "FAIL",
        "exit_code": exit_code,
        "timed_out": timed_out,
        "unexpected_artifact_count": len(artifacts),
        "elapsed_s": round(time.monotonic() - started, 3),
        "log_sha256": sha256_file(log_path),
        "failure_tail": [] if passed else tail.splitlines(),
    }


def write_evidence(path: Path, document: dict[str, Any]) -> None:
    """! @brief JSON evidence를 같은 directory 안에서 원자적으로 교체합니다. """

    validate_public_values(document)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    temporary.replace(path)


def validate_paths(arguments: Namespace) -> dict[str, Path]:
    """! @brief 입력 file과 source/install/build/evidence 분리를 검사합니다. """

    paths = {
        "source": arguments.repository.resolve(),
        "installed": arguments.installed_platform.resolve(),
        "sdk": arguments.sdk_root.resolve(),
        "cli": arguments.arduino_cli.resolve(),
        "config": arguments.config_file.resolve(),
        "build": arguments.build_root.resolve(),
        "output": arguments.output.resolve(),
    }
    for key in ("source", "installed", "sdk"):
        if not paths[key].is_dir():
            raise M33W05Failure(f"{key} directory가 없습니다")
    for key in ("cli", "config"):
        if not paths[key].is_file():
            raise M33W05Failure(f"{key} file이 없습니다")
    if arguments.jobs < 1 or arguments.jobs > 2:
        raise M33W05Failure("--jobs는 1 또는 2여야 합니다")
    if arguments.compile_timeout < 60 or arguments.compile_timeout > 3600:
        raise M33W05Failure("--compile-timeout은 60~3600초여야 합니다")
    if arguments.negative_timeout < 10 or arguments.negative_timeout > 600:
        raise M33W05Failure("--negative-timeout은 10~600초여야 합니다")
    shard_index = getattr(arguments, "shard_index", None)
    shard_count = getattr(arguments, "shard_count", CI_SHARD_COUNT)
    if shard_index is not None and (
        shard_count != CI_SHARD_COUNT
        or not 0 <= shard_index < shard_count
    ):
        raise M33W05Failure("CI shard index/count는 0~7과 8이어야 합니다")
    if paths["build"].exists() or paths["output"].exists():
        raise M33W05Failure("기존 build root나 evidence를 덮어쓰지 않습니다")
    if paths["installed"].is_relative_to(paths["source"]):
        raise M33W05Failure("설치 platform은 source tree 밖이어야 합니다")
    for key in ("build", "output"):
        if paths[key].is_relative_to(paths["source"]) or paths[key].is_relative_to(
            paths["installed"]
        ):
            raise M33W05Failure("build root와 evidence는 source/install tree 밖이어야 합니다")
    if paths["output"].is_relative_to(paths["build"]):
        raise M33W05Failure("evidence는 fresh build root 밖이어야 합니다")
    return paths


def select_shard_identities(
    identities: Sequence[str], shard_index: int, shard_count: int = CI_SHARD_COUNT
) -> list[str]:
    """! @brief 정렬 identity를 modulo 규칙으로 정확히 한 shard에 배정합니다. """

    if shard_count != CI_SHARD_COUNT or not 0 <= shard_index < shard_count:
        raise M33W05Failure("CI shard index/count는 0~7과 8이어야 합니다")
    ordered = sorted(identities, key=str.casefold)
    if len(ordered) != len(set(ordered)):
        raise M33W05Failure("shard 입력 identity가 중복됐습니다")
    return [
        identity for offset, identity in enumerate(ordered)
        if offset % shard_count == shard_index
    ]


def selected_work(
    catalog: dict[str, dict], shard_index: int | None,
    shard_count: int = CI_SHARD_COUNT,
) -> tuple[list[str], list[dict[str, str]]]:
    """! @brief 기본 전수 또는 지정 CI shard의 positive·negative 집합을 반환합니다. """

    if shard_index is None:
        return (
            sorted(catalog, key=str.casefold),
            sorted(NEGATIVE_PROFILE_MATRIX, key=lambda item: item["id"].casefold()),
        )
    positives = select_shard_identities(list(catalog), shard_index, shard_count)
    negative_ids = select_shard_identities(
        [case["id"] for case in NEGATIVE_PROFILE_MATRIX], shard_index, shard_count
    )
    by_id = {case["id"]: case for case in NEGATIVE_PROFILE_MATRIX}
    return positives, [by_id[identifier] for identifier in negative_ids]


def run_parallel(
    jobs: int,
    tasks: Sequence[tuple],
    worker: Callable[..., dict[str, Any]],
    on_result: Callable[[dict[str, Any]], None],
) -> None:
    """! @brief 최대 두 worker로 모든 task를 실행하고 결과를 즉시 전달합니다. """

    with ThreadPoolExecutor(max_workers=jobs) as executor:
        futures = {executor.submit(worker, *task): task for task in tasks}
        for future in as_completed(futures):
            on_result(future.result())


def apply_diagnostic_retest(
    document: dict[str, Any],
    initial: dict[str, Any],
    retry: dict[str, Any],
) -> None:
    """! @brief 최초 실패와 단 한 번의 진단 재시험을 보존해 최종 결과에 반영합니다. """

    identity = initial.get("identity")
    if (
        not isinstance(identity, str)
        or initial.get("status") != "FAIL"
        or retry.get("identity") != identity
    ):
        raise M33W05Failure("진단 재시험 identity 또는 최초 실패 상태가 잘못되었습니다")
    retests = document.setdefault("diagnostic_retests", [])
    if not isinstance(retests, list):
        raise M33W05Failure("진단 재시험 evidence가 배열이 아닙니다")
    count = sum(row.get("identity") == identity for row in retests)
    if count >= MAX_DIAGNOSTIC_RETESTS_PER_BUILD:
        raise M33W05Failure(f"진단 재시험 횟수를 초과했습니다: {identity}")
    builds = document.get("builds")
    if not isinstance(builds, list):
        raise M33W05Failure("build evidence가 배열이 아닙니다")
    indexes = [
        index for index, row in enumerate(builds)
        if row.get("identity") == identity
    ]
    if len(indexes) != 1 or builds[indexes[0]] != initial:
        raise M33W05Failure(f"최초 실패 build evidence가 유일하지 않습니다: {identity}")
    retests.append({
        "identity": identity,
        "reason": "initial_compile_failure",
        "attempt": 2,
        "initial": initial,
        "retry": retry,
    })
    retests.sort(key=lambda item: item["identity"].casefold())
    builds[indexes[0]] = retry
    builds.sort(key=lambda item: item["identity"].casefold())


def execute(arguments: Namespace) -> dict[str, Any]:
    """! @brief W05 clean 설치본의 discovery·compile·negative 검사를 실행합니다. """

    if os.name != "nt":
        raise M33W05Failure("M33-W05 clean 설치본 검사는 Windows에서 실행해야 합니다")
    paths = validate_paths(arguments)
    fixed = verify_fixed_inputs(paths["source"], paths["sdk"])
    installed_revision = verify_installed_snapshot(
        paths["installed"], fixed["source_revision"]
    )
    source_catalog = load_catalog(paths["source"])
    installed_catalog = load_catalog(paths["installed"])
    source_metadata = paths["source"] / "libraries" / "example-metadata.json"
    installed_metadata = paths["installed"] / "libraries" / "example-metadata.json"
    if sha256_file(source_metadata) != sha256_file(installed_metadata):
        raise M33W05Failure("source/install example metadata hash가 다릅니다")
    for identity in source_catalog:
        source = source_catalog[identity]
        installed = installed_catalog[identity]
        if (
            source["profile"] != installed["profile"]
            or source["alternative_profiles"] != installed["alternative_profiles"]
            or source["board_count"] != installed["board_count"]
            or source["roles"] != installed["roles"]
            or source["sketch_sha256"] != installed["sketch_sha256"]
        ):
            raise M33W05Failure(f"source/install 예제 record가 다릅니다: {identity}")
    for case in NEGATIVE_PROFILE_MATRIX:
        if case["identity"] not in installed_catalog:
            raise M33W05Failure(f"negative 예제가 없습니다: {case['identity']}")
        entry = installed_catalog[case["identity"]]
        if case["profile"] in {entry["profile"], *entry["alternative_profiles"]}:
            raise M33W05Failure(f"negative profile이 허용 profile과 같습니다: {case['id']}")
    libraries = discover_installation(
        paths["cli"], paths["config"], paths["source"],
        paths["installed"], installed_catalog,
    )
    initial_library_fingerprint = {
        row["directory"]: row["tree_sha256"] for row in libraries
    }
    paths["build"].mkdir(parents=True)
    log_root = paths["build"] / "logs"
    positive_root = paths["build"] / "positive"
    positive_retest_root = paths["build"] / "positive-retest"
    negative_root = paths["build"] / "negative"
    log_root.mkdir()
    positive_root.mkdir()
    positive_retest_root.mkdir()
    negative_root.mkdir()
    redactions = (
        paths["source"], paths["installed"], paths["sdk"], paths["build"],
        paths["config"].parent, paths["cli"].parent,
    )
    profile_counts = {
        profile: sum(entry["profile"] == profile for entry in installed_catalog.values())
        for profile in sorted(
            {entry["profile"] for entry in installed_catalog.values()}, key=str.casefold
        )
    }
    shard_index = getattr(arguments, "shard_index", None)
    shard_count = getattr(arguments, "shard_count", CI_SHARD_COUNT)
    selected_identities, selected_negatives = selected_work(
        installed_catalog, shard_index, shard_count
    )
    expected_builds = len(selected_identities)
    expected_negatives = len(selected_negatives)
    document: dict[str, Any] = {
        "schema_version": 1,
        "work_id": "M33-W05",
        "test_id": "M33-EXAMPLE-01",
        "status": "IN_PROGRESS",
        "observed_utc": utc_now(),
        "source_revision": fixed["source_revision"],
        "installed_source_revision": installed_revision,
        "source_clean_before": True,
        "installed_clean_before": True,
        "host_scope": "Windows clean installed tree",
        "fixed_inputs": {
            "ncs_version": "3.4.0",
            "nrf_revision": fixed["nrf_revision"],
            "zephyr_revision": fixed["zephyr_revision"],
            "board_revision": fixed["board_revision"],
            "target": TARGET_BOARD,
        },
        "tools": {
            "arduino_cli_sha256": sha256_file(paths["cli"]),
            "arduino_config_sha256": sha256_file(paths["config"]),
        },
        "isolation": {
            "source_path_sha256": path_identity(paths["source"]),
            "installed_path_sha256": path_identity(paths["installed"]),
            "build_path_sha256": path_identity(paths["build"]),
            "source_install_separate": True,
            "fresh_build_root": True,
            "jobs": arguments.jobs,
        },
        "diagnostic_retest_policy": {
            "maximum_per_failed_build": MAX_DIAGNOSTIC_RETESTS_PER_BUILD,
            "fresh_build_directory": True,
            "serial": True,
            "initial_failure_is_preserved": True,
        },
        "denominators": {
            "catalog": EXPECTED_EXAMPLES,
            "discovered": EXPECTED_EXAMPLES,
            "compiled": EXPECTED_EXAMPLES,
            "negative_profiles": len(NEGATIVE_PROFILE_MATRIX),
        },
        "profile_counts": profile_counts,
        "claim_boundary": {
            "compile_is_runtime": False,
            "negative_rejection_is_feature_runtime": False,
            "external_io_not_run_is_pass": False,
            "physical_runtime_recorded_elsewhere": True,
        },
        "metadata_sha256": sha256_file(source_metadata),
        "libraries": libraries,
        "builds": [],
        "diagnostic_retests": [],
        "negative_profiles": [],
    }
    if shard_index is not None:
        document["shard"] = {
            "index": shard_index,
            "count": shard_count,
            "assignment": CI_SHARD_ASSIGNMENT,
            "global_compiled": EXPECTED_EXAMPLES,
            "global_negative_profiles": len(NEGATIVE_PROFILE_MATRIX),
            "assigned_compiled": expected_builds,
            "assigned_negative_profiles": expected_negatives,
        }
    write_evidence(paths["output"], document)

    def record_build(row: dict[str, Any]) -> None:
        document["builds"].append(row)
        document["builds"].sort(key=lambda item: item["identity"].casefold())
        write_evidence(paths["output"], document)
        print(f"{row['identity']}: {row['status']}", flush=True)

    positive_tasks = []
    for identity in selected_identities:
        entry = installed_catalog[identity]
        key = identity.replace("/", "__")
        positive_tasks.append((
            paths["cli"], paths["config"], arguments.fqbn_prefix,
            identity, entry["directory"], entry["profile"],
            positive_root / key, log_root / f"positive-{key}.log",
            arguments.compile_timeout, fixed, redactions,
        ))
    run_parallel(arguments.jobs, positive_tasks, compile_example, record_build)

    initial_failures = [
        row for row in document["builds"] if row["status"] == "FAIL"
    ]
    for initial in sorted(
        initial_failures, key=lambda item: item["identity"].casefold()
    ):
        identity = initial["identity"]
        entry = installed_catalog[identity]
        key = identity.replace("/", "__")
        retry = compile_example(
            paths["cli"], paths["config"], arguments.fqbn_prefix,
            identity, entry["directory"], entry["profile"],
            positive_retest_root / key,
            log_root / f"positive-retest-{key}.log",
            arguments.compile_timeout, fixed, redactions,
        )
        apply_diagnostic_retest(document, initial, retry)
        write_evidence(paths["output"], document)
        print(f"retest:{identity}: {retry['status']}", flush=True)

    def record_negative(row: dict[str, Any]) -> None:
        document["negative_profiles"].append(row)
        document["negative_profiles"].sort(key=lambda item: item["id"])
        write_evidence(paths["output"], document)
        print(f"negative:{row['id']}: {row['status']}", flush=True)

    negative_tasks = []
    for case in selected_negatives:
        key = case["id"]
        negative_tasks.append((
            paths["cli"], paths["config"], arguments.fqbn_prefix,
            case, installed_catalog[case["identity"]]["directory"],
            negative_root / key, log_root / f"negative-{key}.log",
            arguments.negative_timeout, redactions,
        ))
    run_parallel(arguments.jobs, negative_tasks, compile_negative, record_negative)

    source_clean_after = not bool(git_output(paths["source"], "status", "--porcelain"))
    revision_after = git_output(paths["source"], "rev-parse", "HEAD")
    installed_clean_after = not bool(
        git_output(paths["installed"], "status", "--porcelain")
    )
    installed_revision_after = git_output(paths["installed"], "rev-parse", "HEAD")
    installed_unchanged = sha256_file(installed_metadata) == document["metadata_sha256"]
    for library, expected_hash in initial_library_fingerprint.items():
        current_hash = tree_fingerprint(paths["installed"] / "libraries" / library)[1]
        installed_unchanged = installed_unchanged and current_hash == expected_hash
    build_passes = sum(row["status"] == "PASS" for row in document["builds"])
    negative_passes = sum(
        row["status"] == "PASS" for row in document["negative_profiles"]
    )
    document["summary"] = {
        "catalog": len(installed_catalog),
        "discovered": sum(row["example_count"] for row in libraries),
        "compiled_pass": build_passes,
        "compiled_fail": expected_builds - build_passes,
        "initial_compile_fail": len(initial_failures),
        "diagnostic_retest_pass": sum(
            row["retry"]["status"] == "PASS"
            for row in document["diagnostic_retests"]
        ),
        "diagnostic_retest_fail": sum(
            row["retry"]["status"] != "PASS"
            for row in document["diagnostic_retests"]
        ),
        "negative_pass": negative_passes,
        "negative_fail": expected_negatives - negative_passes,
    }
    document["source_clean_after"] = source_clean_after
    document["source_revision_after"] = revision_after
    document["installed_clean_after"] = installed_clean_after
    document["installed_revision_after"] = installed_revision_after
    document["installed_tree_unchanged"] = installed_unchanged
    document["finished_utc"] = utc_now()
    document["status"] = "PASS" if (
        build_passes == expected_builds
        and negative_passes == expected_negatives
        and source_clean_after
        and revision_after == fixed["source_revision"]
        and installed_clean_after
        and installed_revision_after == fixed["source_revision"]
        and installed_unchanged
    ) else "FAIL"
    write_evidence(paths["output"], document)
    return document


def argument_parser() -> ArgumentParser:
    """! @brief 유한 실행 제한을 포함한 CLI parser를 만듭니다. """

    parser = ArgumentParser()
    parser.add_argument("--repository", type=Path, default=ROOT)
    parser.add_argument("--installed-platform", type=Path, required=True)
    parser.add_argument("--sdk-root", type=Path, required=True)
    parser.add_argument("--arduino-cli", type=Path, required=True)
    parser.add_argument("--config-file", type=Path, required=True)
    parser.add_argument("--build-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--compile-timeout", type=int, default=1200)
    parser.add_argument("--negative-timeout", type=int, default=120)
    parser.add_argument("--fqbn-prefix", default="nucode:zephyr:nu54dk")
    parser.add_argument("--shard-index", type=int)
    parser.add_argument("--shard-count", type=int, default=CI_SHARD_COUNT)
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    """! @brief CLI를 실행하고 최종 분모를 한 줄로 출력합니다. """

    parsed = argument_parser().parse_args(arguments)
    try:
        result = execute(parsed)
    except (M33W05Failure, OSError, json.JSONDecodeError) as error:
        print(f"M33_W05_INSTALLED_EXAMPLES_FAIL: {error}", file=sys.stderr)
        return 1
    summary = result["summary"]
    compiled_denominator = result.get("shard", {}).get(
        "assigned_compiled", EXPECTED_EXAMPLES
    )
    negative_denominator = result.get("shard", {}).get(
        "assigned_negative_profiles", len(NEGATIVE_PROFILE_MATRIX)
    )
    print(
        f"M33_W05_INSTALLED_EXAMPLES={result['status']};"
        f"DISCOVERED={summary['discovered']}/{EXPECTED_EXAMPLES};"
        f"COMPILED={summary['compiled_pass']}/{compiled_denominator};"
        f"NEGATIVE={summary['negative_pass']}/{negative_denominator}"
    )
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
