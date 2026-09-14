"""! @brief 지원 Host 판별과 실행 파일·사용자 경로 해석 계약입니다. """

from __future__ import annotations

from pathlib import Path
from typing import Mapping
from typing import TypedDict
import os
import platform
import re

from .common import AdapterError, canonical_path


class HostDescriptor(TypedDict):
    """! @brief Build Adapter가 사용하는 정규화된 Host 설명자입니다. """

    os: str
    architecture: str
    distribution: str
    version: str
    native: bool
    supported: bool
    reason: str


EXECUTABLE_CANDIDATES: dict[str, dict[str, tuple[str, ...]]] = {
    "windows": {
        "python": ("opt/bin/python.exe",),
        "west": ("opt/bin/Scripts/west.exe",),
        "git": ("bin/git.exe",),
        "cxx": (
            "opt/zephyr-sdk/gnu/arm-zephyr-eabi/bin/arm-zephyr-eabi-g++.exe",
        ),
        "size": (
            "opt/zephyr-sdk/gnu/arm-zephyr-eabi/bin/arm-zephyr-eabi-size.exe",
        ),
        "ccache": ("opt/bin/ccache.exe",),
        "pyocd": ("opt/bin/Scripts/pyocd.exe",),
    },
    "linux": {
        "python": ("opt/bin/python3", "opt/bin/python"),
        "west": ("opt/bin/west", "opt/bin/bin/west", "opt/bin/Scripts/west"),
        "git": ("bin/git", "opt/bin/git", "opt/bin/bin/git"),
        "cxx": (
            "opt/zephyr-sdk/arm-zephyr-eabi/bin/arm-zephyr-eabi-g++",
            "opt/zephyr-sdk/gnu/arm-zephyr-eabi/bin/arm-zephyr-eabi-g++",
        ),
        "size": (
            "opt/zephyr-sdk/arm-zephyr-eabi/bin/arm-zephyr-eabi-size",
            "opt/zephyr-sdk/gnu/arm-zephyr-eabi/bin/arm-zephyr-eabi-size",
        ),
        "ccache": ("opt/bin/ccache", "opt/bin/bin/ccache"),
        "pyocd": ("opt/bin/pyocd", "opt/bin/bin/pyocd", "opt/bin/Scripts/pyocd"),
    },
    "macos": {
        "python": ("opt/bin/python3", "opt/bin/python"),
        "west": ("opt/bin/west", "opt/bin/bin/west", "opt/bin/Scripts/west"),
        "git": ("bin/git", "opt/bin/git", "opt/bin/bin/git"),
        "cxx": (
            "opt/zephyr-sdk/arm-zephyr-eabi/bin/arm-zephyr-eabi-g++",
            "opt/zephyr-sdk/gnu/arm-zephyr-eabi/bin/arm-zephyr-eabi-g++",
        ),
        "size": (
            "opt/zephyr-sdk/arm-zephyr-eabi/bin/arm-zephyr-eabi-size",
            "opt/zephyr-sdk/gnu/arm-zephyr-eabi/bin/arm-zephyr-eabi-size",
        ),
        "ccache": ("opt/bin/ccache", "opt/bin/bin/ccache"),
        "pyocd": ("opt/bin/pyocd", "opt/bin/bin/pyocd", "opt/bin/Scripts/pyocd"),
    },
}


## @brief 운영체제 이름을 제품 계약의 세 값으로 정규화합니다.
def canonical_host_os(system_name: str) -> str:
    normalized = system_name.strip().casefold()
    aliases = {
        "windows": "windows",
        "win32": "windows",
        "linux": "linux",
        "darwin": "macos",
        "macos": "macos",
    }
    if normalized not in aliases:
        raise AdapterError(f"[NU54:E_HOST_OS] 지원하지 않는 Host OS입니다: {system_name}")
    return aliases[normalized]


## @brief CPU architecture 별칭을 x86_64 또는 arm64로 정규화합니다.
def canonical_architecture(machine: str) -> str:
    normalized = machine.strip().casefold()
    aliases = {
        "amd64": "x86_64",
        "x64": "x86_64",
        "x86_64": "x86_64",
        "aarch64": "arm64",
        "arm64": "arm64",
    }
    if normalized not in aliases:
        raise AdapterError(
            f"[NU54:E_HOST_ARCH] 지원하지 않는 Host architecture입니다: {machine}"
        )
    return aliases[normalized]


## @brief 점으로 구분한 version의 숫자 prefix를 비교 tuple로 변환합니다.
def version_tuple(value: str) -> tuple[int, ...]:
    match = re.match(r"^\s*(\d+(?:\.\d+)*)", value)
    if match is None:
        return ()
    return tuple(int(part) for part in match.group(1).split("."))


## @brief Linux os-release의 단순 key/value를 shell 실행 없이 읽습니다.
def linux_release(path: Path = Path("/etc/os-release")) -> tuple[str, str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return "unknown", "unknown"
    values: dict[str, str] = {}
    for line in lines:
        if "=" not in line or line.lstrip().startswith("#"):
            continue
        key, value = line.split("=", 1)
        values[key] = value.strip().strip('"')
    return values.get("ID", "unknown").casefold(), values.get("VERSION_ID", "unknown")


## @brief 현재 또는 주입한 Host 값을 지원 matrix에 따라 fail-closed로 기술합니다.
def describe_host(
    *,
    system_name: str | None = None,
    machine: str | None = None,
    distribution: str | None = None,
    version: str | None = None,
    native: bool = True,
) -> HostDescriptor:
    host_os = canonical_host_os(system_name or platform.system())
    architecture = canonical_architecture(machine or platform.machine())

    if host_os == "windows":
        host_distribution = (distribution or "windows").casefold()
        host_version = version or platform.win32_ver()[0] or platform.release()
        supported = architecture == "x86_64" and version_tuple(host_version) >= (10,)
        requirement = "Windows 10/11 x86-64 native"
    elif host_os == "linux":
        detected_distribution, detected_version = linux_release()
        host_distribution = (distribution or detected_distribution).casefold()
        host_version = version or detected_version
        supported = (
            architecture == "x86_64"
            and host_distribution == "ubuntu"
            and version_tuple(host_version) >= (24, 4)
        )
        requirement = "Ubuntu 24.04+ AMD64 native"
    else:
        host_distribution = (distribution or "macos").casefold()
        host_version = version or platform.mac_ver()[0] or "unknown"
        supported = architecture == "arm64" and version_tuple(host_version) >= (26,)
        requirement = "macOS 26+ Apple Silicon native"

    if not native:
        supported = False
    reason = "supported" if supported else f"필요 조건: {requirement}"
    return {
        "os": host_os,
        "architecture": architecture,
        "distribution": host_distribution,
        "version": host_version,
        "native": native,
        "supported": supported,
        "reason": reason,
    }


## @brief 지원 matrix 밖의 Host를 build 시작 전에 거부합니다.
def require_supported_host(descriptor: HostDescriptor | None = None) -> HostDescriptor:
    current = descriptor or describe_host()
    if not current["supported"]:
        raise AdapterError(
            "[NU54:E_HOST_UNSUPPORTED] 지원하지 않는 Host입니다: "
            f"os={current['os']} distribution={current['distribution']} "
            f"version={current['version']} architecture={current['architecture']} "
            f"native={str(current['native']).lower()}; {current['reason']}"
        )
    return current


## @brief Host별 toolchain 내부 실행 파일 후보를 반환합니다.
def executable_candidates(tool: str, host_os: str | None = None) -> tuple[str, ...]:
    selected_os = canonical_host_os(host_os or platform.system())
    candidates = EXECUTABLE_CANDIDATES[selected_os].get(tool)
    if candidates is None:
        raise AdapterError(f"[NU54:E_TOOL_NAME] 알 수 없는 tool 이름입니다: {tool}")
    return candidates


## @brief Toolchain root 아래의 실제 실행 가능한 파일 하나를 결정합니다.
def resolve_toolchain_executable(
    toolchain_root: Path,
    tool: str,
    *,
    host_os: str | None = None,
    required: bool = True,
) -> Path | None:
    selected_os = canonical_host_os(host_os or platform.system())
    checked: list[Path] = []
    for relative in executable_candidates(tool, selected_os):
        candidate = canonical_path(toolchain_root / relative)
        checked.append(candidate)
        if not candidate.is_file():
            continue
        if selected_os != "windows" and not os.access(candidate, os.X_OK):
            continue
        return candidate
    if not required:
        return None
    paths = ", ".join(path.as_posix() for path in checked)
    raise AdapterError(
        f"[NU54:E_TOOL_EXECUTABLE] {tool} 실행 파일을 찾지 못했습니다: {paths}"
    )


## @brief Host별 사용자 application data root를 계산합니다.
def application_data_root(
    descriptor: HostDescriptor | None = None,
    environment: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    current = descriptor or describe_host()
    variables = environment if environment is not None else os.environ
    user_home = canonical_path(home or Path.home())
    if current["os"] == "windows":
        value = variables.get("LOCALAPPDATA")
        if not value:
            raise AdapterError("[NU54:E_HOST_DATA_ROOT] LOCALAPPDATA 환경 변수가 없습니다.")
        return canonical_path(value)
    if current["os"] == "linux":
        value = variables.get("XDG_DATA_HOME")
        return canonical_path(value) if value else user_home / ".local" / "share"
    return user_home / "Library" / "Application Support"


## @brief Host별 사용자 cache root를 계산합니다.
def user_cache_root(
    descriptor: HostDescriptor | None = None,
    environment: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    current = descriptor or describe_host()
    variables = environment if environment is not None else os.environ
    user_home = canonical_path(home or Path.home())
    if current["os"] == "windows":
        value = variables.get("LOCALAPPDATA")
        if not value:
            raise AdapterError("[NU54:E_HOST_CACHE_ROOT] LOCALAPPDATA 환경 변수가 없습니다.")
        return canonical_path(value)
    if current["os"] == "linux":
        value = variables.get("XDG_CACHE_HOME")
        return canonical_path(value) if value else user_home / ".cache"
    return user_home / "Library" / "Caches"
