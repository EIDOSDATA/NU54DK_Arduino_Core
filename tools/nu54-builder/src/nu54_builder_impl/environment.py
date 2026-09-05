"""! @brief 고정 SDK·toolchain·설치 prerequisites 경계를 소유합니다. """

from __future__ import annotations
from .models import ToolEnvironment

from pathlib import Path
from typing import Any
import json
import os
import subprocess
from .common import (
    AdapterError,
    BUILD_ENVIRONMENT_OVERRIDE_KEYS,
    DEFAULT_CCACHE_MAX_SIZE,
    NCS_REVISION,
    NCS_VERSION,
    NRFUTIL_SHA256,
    NRFUTIL_VERSION,
    SDK_MANAGER_VERSION,
    TOOLCHAIN_BUNDLE_ID,
    ZEPHYR_REVISION,
    canonical_path,
    exact_git_revision,
    file_sha256,
    load_json_object,
    path_key,
    release_manifest,
)
from .paths import build_cache_root


## @brief 요청 platform root가 exact Git checkout인지 확인합니다.
def is_development_checkout(platform_root: Path) -> bool:
    if not (platform_root / ".git").exists():
        return False
    try:
        top = subprocess.run(
            ["git", "-C", str(platform_root), "rev-parse", "--show-toplevel"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            text=True,
        )
    except OSError:
        return True
    return top.returncode == 0 and path_key(top.stdout.strip()) == path_key(platform_root)


## @brief 고정 버전의 NCS root를 환경 또는 기본 설치 위치에서 찾습니다.
def discover_ncs_root(*, prefer_user_profile: bool = False) -> Path:
    configured = os.environ.get("NUCODE_NCS_ROOT")
    if configured is not None:
        if not configured.strip():
            raise AdapterError("명시한 NUCODE_NCS_ROOT 값이 비어 있습니다.")
        candidate = canonical_path(configured)
        if (candidate / "zephyr" / "CMakeLists.txt").is_file() and (
            candidate / "nrf" / "west.yml"
        ).is_file():
            return candidate.resolve()
        raise AdapterError(
            "명시한 NUCODE_NCS_ROOT에 nRF Connect SDK v3.4.0이 없습니다: "
            f"{candidate}"
        )
    default_candidates = (Path("C:/ncs/v3.4.0"), Path.home() / "ncs" / "v3.4.0")
    if prefer_user_profile:
        default_candidates = tuple(reversed(default_candidates))
    for candidate in default_candidates:
        if (candidate / "zephyr" / "CMakeLists.txt").is_file() and (candidate / "nrf" / "west.yml").is_file():
            return candidate.resolve()
    raise AdapterError(
        "nRF Connect SDK v3.4.0을 찾을 수 없습니다. NUCODE_NCS_ROOT를 설정하십시오."
    )


## @brief NCS version과 연결된 Toolchain Manager bundle identifier를 읽습니다.
def configured_bundle_id(ncs_root: Path) -> str | None:
    registry = ncs_root.parent / "toolchains" / "toolchains.json"
    if not registry.is_file():
        return None
    try:
        documents = json.loads(registry.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    for document in documents if isinstance(documents, list) else []:
        for entry in document.get("toolchains", []):
            if NCS_VERSION in entry.get("ncs_versions", []):
                identifier = entry.get("identifier", {})
                bundle = identifier.get("bundle_id")
                if isinstance(bundle, str):
                    return bundle
    return None


## @brief 개발 환경 discovery 또는 배포 package의 exact Toolchain bundle을 찾습니다.
def discover_toolchain_root(ncs_root: Path, *, exact_required: bool = False) -> Path:
    toolchains_root = ncs_root.parent / "toolchains"
    if exact_required:
        pinned = toolchains_root / TOOLCHAIN_BUNDLE_ID
        if (
            (pinned / "environment.json").is_file()
            and (pinned / "opt" / "bin" / "python.exe").is_file()
        ):
            return pinned.resolve()
        raise AdapterError(
            "Boards Manager package에 필요한 고정 NCS Toolchain bundle을 찾을 수 없습니다: "
            f"{pinned}"
        )

    configured = os.environ.get("NUCODE_TOOLCHAIN_ROOT")
    candidates: list[Path] = []
    if configured:
        candidates.append(canonical_path(configured))
    bundle = configured_bundle_id(ncs_root)
    if bundle:
        candidates.append(ncs_root.parent / "toolchains" / bundle)
    candidates.append(toolchains_root / TOOLCHAIN_BUNDLE_ID)
    if toolchains_root.is_dir():
        candidates.extend(sorted(path for path in toolchains_root.iterdir() if path.is_dir()))
    visited: set[str] = set()
    for candidate in candidates:
        key = path_key(candidate)
        if key in visited:
            continue
        visited.add(key)
        if (candidate / "environment.json").is_file() and (candidate / "opt" / "bin" / "python.exe").is_file():
            return candidate.resolve()
    raise AdapterError(
        "NCS toolchain environment.json을 찾을 수 없습니다. NUCODE_TOOLCHAIN_ROOT를 설정하십시오."
    )


## @brief Toolchain Manager environment.json을 현재 child process 환경에 적용합니다.
def apply_toolchain_environment(toolchain_root: Path) -> dict[str, str]:
    environment = os.environ.copy()
    # 사용자의 shell flag가 canonical cache key 밖에서 build를 바꾸지 못하게 합니다.
    for key in BUILD_ENVIRONMENT_OVERRIDE_KEYS:
        environment.pop(key, None)
    document_path = toolchain_root / "environment.json"
    try:
        document = json.loads(document_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as error:
        raise AdapterError(f"toolchain environment.json을 읽지 못했습니다: {error}") from error

    for entry in document.get("env_vars", []):
        key = entry.get("key")
        if not isinstance(key, str):
            continue
        entry_type = entry.get("type")
        if entry_type == "relative_paths":
            values = [str((toolchain_root / value).resolve()) for value in entry.get("values", [])]
            treatment = entry.get("existing_value_treatment", "overwrite")
            if treatment == "prepend_to" and environment.get(key):
                values.append(environment[key])
            environment[key] = os.pathsep.join(values)
        elif entry_type == "string":
            environment[key] = str(entry.get("value", ""))
    return environment


## @brief M10 사용자별 prerequisite state directory를 계산합니다.
def prerequisite_state_root() -> Path:
    configured = os.environ.get("NUCODE_PREREQUISITE_STATE_ROOT")
    if configured:
        return canonical_path(configured)
    local_data = os.environ.get("LOCALAPPDATA")
    if not local_data:
        raise AdapterError("[NU54:E_PREREQUISITE_STATE] LOCALAPPDATA 환경 변수가 없습니다.")
    return canonical_path(
        Path(local_data) / "NUCODE" / "NU54DK_Arduino_Core" / "prerequisites"
    )


## @brief 배포 package의 pin과 완료 marker를 현재 Nordic 설치와 대조합니다.
def validate_packaged_prerequisites(
    platform_root: Path, ncs_root: Path, toolchain_root: Path
) -> None:
    package_manifest = release_manifest(platform_root)
    pins_path = platform_root / "tools" / "nu54-prerequisites" / "pins.json"
    pins = load_json_object(pins_path, "E_PREREQUISITE_PINS")
    ready_path = prerequisite_state_root() / "ready.json"
    ready = load_json_object(ready_path, "E_PREREQUISITE_READY")
    pins_hash = file_sha256(pins_path)

    if pins.get("schema_version") != 1:
        raise AdapterError("[NU54:E_PREREQUISITE_PINS] 지원하지 않는 pin schema입니다.")
    ## @brief 중첩 pin 값이 object/string 계약을 만족할 때만 반환합니다.
    def pin_value(section: str, field: str) -> Any:
        section_value = pins.get(section)
        return section_value.get(field) if isinstance(section_value, dict) else None

    expected_values = {
        "ncs_version": pin_value("ncs", "version"),
        "ncs_revision": pin_value("ncs", "revision"),
        "zephyr_revision": pin_value("zephyr", "revision"),
        "toolchain_bundle_id": pin_value("toolchain", "bundle_id"),
        "nrfutil_version": pin_value("nrfutil", "version"),
        "nrfutil_sha256": pin_value("nrfutil", "sha256"),
        "sdk_manager_version": pin_value("sdk_manager", "version"),
    }
    if expected_values != {
        "ncs_version": NCS_VERSION,
        "ncs_revision": NCS_REVISION,
        "zephyr_revision": ZEPHYR_REVISION,
        "toolchain_bundle_id": TOOLCHAIN_BUNDLE_ID,
        "nrfutil_version": NRFUTIL_VERSION,
        "nrfutil_sha256": NRFUTIL_SHA256,
        "sdk_manager_version": SDK_MANAGER_VERSION,
    }:
        raise AdapterError("[NU54:E_PREREQUISITE_PINS] Build Adapter와 pin 계약이 다릅니다.")
    for field in ("ncs_revision", "zephyr_revision", "toolchain_bundle_id"):
        if package_manifest.get(field) != expected_values[field]:
            raise AdapterError(
                f"[NU54:E_PACKAGE_MANIFEST] release manifest의 {field} 값이 pin과 다릅니다."
            )
    if package_manifest.get("prerequisites_pins_sha256") != pins_hash:
        raise AdapterError(
            "[NU54:E_PACKAGE_MANIFEST] release manifest의 prerequisite pin hash가 다릅니다."
        )

    if ready.get("schema_version") != 1 or ready.get("status") != "ready":
        raise AdapterError(
            "[NU54:E_PREREQUISITE_READY] 설치 완료 marker가 없거나 상태가 잘못되었습니다. "
            "post_install.bat을 다시 실행하십시오."
        )
    ready_expected = {
        "pins_sha256": pins_hash,
        "ncs_version": NCS_VERSION,
        "ncs_revision": NCS_REVISION,
        "zephyr_revision": ZEPHYR_REVISION,
        "toolchain_bundle_id": TOOLCHAIN_BUNDLE_ID,
        "nrfutil_version": NRFUTIL_VERSION,
        "nrfutil_sha256": NRFUTIL_SHA256,
        "sdk_manager_version": SDK_MANAGER_VERSION,
    }
    for field, expected in ready_expected.items():
        if ready.get(field) != expected:
            raise AdapterError(
                f"[NU54:E_PREREQUISITE_READY] 완료 marker의 {field} 값이 다릅니다."
            )
    marker_ncs_root = ready.get("ncs_root")
    marker_toolchain_root = ready.get("toolchain_root")
    marker_nrfutil = ready.get("nrfutil_path")
    local_data = os.environ.get("LOCALAPPDATA")
    if not local_data:
        raise AdapterError("[NU54:E_PREREQUISITE_STATE] LOCALAPPDATA 환경 변수가 없습니다.")
    expected_nrfutil = canonical_path(
        Path(local_data) / "NUCODE" / "NU54DK_Arduino_Core" / "tools" / "nrfutil.exe"
    )
    if (
        not isinstance(marker_ncs_root, str)
        or path_key(marker_ncs_root) != path_key(ncs_root.parent)
        or not isinstance(marker_toolchain_root, str)
        or path_key(marker_toolchain_root) != path_key(toolchain_root)
        or not isinstance(marker_nrfutil, str)
        or path_key(marker_nrfutil) != path_key(expected_nrfutil)
    ):
        raise AdapterError(
            "[NU54:E_PREREQUISITE_READY] 완료 marker와 발견한 Nordic 설치 경로가 다릅니다."
        )
    if toolchain_root.name != TOOLCHAIN_BUNDLE_ID:
        raise AdapterError("[NU54:E_PREREQUISITE_TOOLCHAIN] 고정 Toolchain bundle이 아닙니다.")
    bundled_git = toolchain_root / "bin" / "git.exe"
    if not bundled_git.is_file():
        raise AdapterError(
            "[NU54:E_PREREQUISITE_TOOLCHAIN] Toolchain bundle의 Git 실행 파일이 없습니다."
        )
    toolchain_manifest = load_json_object(
        toolchain_root / "manifest.json", "E_PREREQUISITE_TOOLCHAIN"
    )
    if toolchain_manifest.get("bundle_id") != TOOLCHAIN_BUNDLE_ID:
        raise AdapterError(
            "[NU54:E_PREREQUISITE_TOOLCHAIN] Toolchain manifest bundle_id가 pin과 다릅니다."
        )
    if not expected_nrfutil.is_file() or file_sha256(expected_nrfutil) != NRFUTIL_SHA256:
        raise AdapterError("[NU54:E_PREREQUISITE_NRFUTIL] nRF Util byte hash가 pin과 다릅니다.")
    if exact_git_revision(ncs_root / "nrf", git_executable=bundled_git) != NCS_REVISION:
        raise AdapterError("[NU54:E_PREREQUISITE_NCS] NCS revision이 고정 pin과 다릅니다.")
    if exact_git_revision(
        ncs_root / "zephyr", git_executable=bundled_git
    ) != ZEPHYR_REVISION:
        raise AdapterError("[NU54:E_PREREQUISITE_ZEPHYR] Zephyr revision이 고정 pin과 다릅니다.")


## @brief west와 compiler에 필요한 실행 환경 및 절대 경로를 구성합니다.
def tool_environment(platform_root: Path | None = None) -> ToolEnvironment:
    packaged = platform_root is not None and not is_development_checkout(platform_root)
    if packaged:
        release_manifest(platform_root)
    ncs_root = discover_ncs_root(prefer_user_profile=packaged)
    toolchain_root = discover_toolchain_root(ncs_root, exact_required=packaged)
    if packaged and platform_root is not None:
        validate_packaged_prerequisites(platform_root, ncs_root, toolchain_root)
    environment = apply_toolchain_environment(toolchain_root)
    zephyr_base = ncs_root / "zephyr"
    environment["ZEPHYR_BASE"] = str(zephyr_base)
    west = toolchain_root / "opt" / "bin" / "Scripts" / "west.exe"
    git = toolchain_root / "bin" / "git.exe"
    compiler = (
        toolchain_root
        / "opt"
        / "zephyr-sdk"
        / "gnu"
        / "arm-zephyr-eabi"
        / "bin"
        / "arm-zephyr-eabi-g++.exe"
    )
    size_tool = compiler.with_name("arm-zephyr-eabi-size.exe")
    ccache = toolchain_root / "opt" / "bin" / ("ccache.exe" if os.name == "nt" else "ccache")
    for executable in (west, git, compiler, size_tool):
        if not executable.is_file():
            raise AdapterError(f"NCS toolchain 실행 파일이 없습니다: {executable}")
    ccache_root = build_cache_root() / "compiler-cache"
    if ccache.is_file():
        ccache_root.mkdir(parents=True, exist_ok=True)
        environment["CCACHE_DIR"] = str(ccache_root)
        environment["CCACHE_MAXSIZE"] = os.environ.get(
            "NUCODE_CCACHE_MAX_SIZE", DEFAULT_CCACHE_MAX_SIZE
        )
        environment["CCACHE_COMPILERCHECK"] = "content"
    return {
        "ncs_root": ncs_root,
        "toolchain_root": toolchain_root,
        "zephyr_base": zephyr_base,
        "environment": environment,
        "west": west,
        "git": git,
        "compiler": compiler,
        "size": size_tool,
        "ccache": ccache if ccache.is_file() else None,
        "ccache_root": ccache_root,
    }


## @brief compiler의 version 첫 줄을 build identity로 읽습니다.
def compiler_version(compiler: Path, environment: dict[str, str]) -> str:
    try:
        result = subprocess.run(
            [str(compiler), "--version"],
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            text=True,
        )
    except OSError:
        return "unknown"
    if result.returncode != 0 or not result.stdout:
        return "unknown"
    return result.stdout.splitlines()[0].strip()
