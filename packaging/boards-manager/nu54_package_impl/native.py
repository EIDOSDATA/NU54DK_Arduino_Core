"""! @brief 후속 native package의 고정 초기 Python·recipe·원문 고지 계약을 소유합니다. """
from __future__ import annotations

from pathlib import PurePosixPath
import re
import zipfile
from typing import Any, Iterable

from .model import NCS_REVISION, NCS_VERSION, PackageError, TOOLCHAIN_BUNDLE_ID, ZEPHYR_REVISION
from . import bootstrap_archive


BOOTSTRAP_PATH = 'tools/nu54-prerequisites/bootstrap-pins.json'
PLATFORM_PINS_PATH = 'tools/nu54-prerequisites/platform-pins.json'
NATIVE_SOURCE_POLICY = 'exact-commit-plus-declared-native-bootstrap-recipes-and-windows-crlf-rewrites'
PLATFORMS = {
    'windows-x86_64': ('x86_64-mingw32', 'x86_64-pc-windows-msvc', 'python.exe'),
    'linux-x86_64': ('x86_64-linux-gnu', 'x86_64-unknown-linux-gnu', 'bin/python3.12'),
    'macos-arm64': ('arm64-apple-darwin', 'aarch64-apple-darwin', 'bin/python3.12'),
}


def is_native_version(version: str) -> bool:
    """! @brief 승인된 version 목록과 별개로 v0.6.0 이후의 package 형식을 선택합니다. """
    match = re.fullmatch(r'(\d+)\.(\d+)\.(\d+)(?:-[0-9A-Za-z.-]+)?', version)
    return match is not None and tuple(map(int, match.groups())) >= (0, 6, 0)


def load_bootstrap(data: bytes, payload: dict[str, bytes] | None = None) -> dict[str, Any]:
    """! @brief 공식 세 ABI의 고정 asset과 원문 license byte를 strict JSON으로 검증합니다. """
    from .serialization import sha256_bytes, strict_json_loads
    pins = strict_json_loads(data, source=BOOTSTRAP_PATH)
    if not isinstance(pins, dict) or pins.get('schema_version') != 1:
        raise PackageError('초기 Python pin schema가 유효하지 않습니다.')
    runtime = pins.get('runtime')
    platforms = pins.get('platforms')
    if not isinstance(runtime, dict) or not isinstance(platforms, dict) or set(platforms) != set(PLATFORMS):
        raise PackageError('초기 Python은 고정한 native 세 Host 자산을 모두 선언해야 합니다.')
    version = runtime.get('python_version', '')
    release = runtime.get('upstream_release', '')
    if (not isinstance(version, str) or not re.fullmatch(r'3\.12\.\d+', version)
            or not isinstance(release, str) or not re.fullmatch(r'\d{8}', release)
            or runtime.get('name') != 'nu54-python' or runtime.get('tool_version') != version + '-' + release + '.nu54.1'
            or runtime.get('arduino_archive_layout') != bootstrap_archive.LAYOUT
            or runtime.get('distribution_status') != 'UNPUBLISHED_PRIVATE_CI_ONLY'
            or runtime.get('source_repository') != 'https://github.com/astral-sh/python-build-standalone'):
        raise PackageError('초기 Python runtime identity가 고정 계약과 다릅니다.')
    for key, (host, triple, executable) in PLATFORMS.items():
        item = platforms[key]
        if not isinstance(item, dict) or (item.get('arduino_host'), item.get('upstream_target'), item.get('executable')) != (host, triple, executable):
            raise PackageError('초기 Python의 Host·ABI·실행 경로가 다릅니다: ' + key)
        archive = item.get('archive')
        filename = f'cpython-{version}+{release}-{triple}-install_only_stripped.tar.gz'
        url = runtime['source_repository'] + '/releases/download/' + release + '/' + filename.replace('+', '%2B')
        if (not isinstance(archive, dict) or archive.get('filename') != filename or archive.get('url') != url
                or not isinstance(archive.get('size'), int) or isinstance(archive['size'], bool) or archive['size'] <= 0
                or not isinstance(archive.get('sha256'), str) or not re.fullmatch(r'[0-9a-f]{64}', archive['sha256'])):
            raise PackageError('초기 Python 공식 archive URL·size·SHA-256이 유효하지 않습니다: ' + key)
        compatible = item.get('arduino_archive')
        filename = f"nu54-python-{runtime['tool_version']}-{key}.tar.bz2"
        url = ('https://github.com/EIDOSDATA/NU54DK_Arduino_Core/releases/download/tools-nu54-python-'
            + runtime['tool_version'] + '/' + filename)
        if (not isinstance(compatible, dict) or compatible.get('filename') != filename or compatible.get('url') != url
                or type(compatible.get('size')) is not int or compatible['size'] <= 0
                or not isinstance(compatible.get('sha256'), str) or not re.fullmatch(r'[0-9a-f]{64}', compatible['sha256'])):
            raise PackageError('실제 생성한 Arduino용 runtime archive의 pin이 유효하지 않습니다: ' + key)
    notices = pins.get('notice_files')
    if not isinstance(notices, list) or not notices:
        raise PackageError('초기 Python의 원문 license 고지가 필요합니다.')
    seen = set()
    notice_platforms = set()
    for item in notices:
        if not isinstance(item, dict) or not isinstance(item.get('path'), str):
            raise PackageError('초기 Python license 경로가 유효하지 않습니다.')
        relative = PurePosixPath(item['path'])
        if (len(relative.parts) != 3 or relative.parts[0] != 'bootstrap-licenses'
                or relative.parts[1] not in PLATFORMS or relative.parts[2] in ('.', '..')
                or '\\' in item['path'] or relative.as_posix() != item['path'] or item['path'] in seen
                or not isinstance(item.get('sha256'), str) or not re.fullmatch(r'[0-9a-f]{64}', item['sha256'])
                or not isinstance(item.get('size'), int) or isinstance(item['size'], bool) or item['size'] <= 0):
            raise PackageError('초기 Python license 경로·중복·hash·size가 유효하지 않습니다.')
        seen.add(item['path'])
        notice_platforms.add(relative.parts[1])
        if payload is not None:
            body = payload.get('tools/nu54-prerequisites/' + item['path'])
            if body is None or len(body) != item['size'] or sha256_bytes(body) != item['sha256']:
                raise PackageError('초기 Python 원문 license가 누락되거나 변경됐습니다: ' + item['path'])
    if notice_platforms != set(PLATFORMS):
        raise PackageError('초기 Python license는 세 Host 모두의 upstream 고지를 포함해야 합니다.')
    return pins


def bootstrap_from_files(files: Iterable[Any]) -> dict[str, Any]:
    """! @brief CWD가 아닌 선택된 exact commit의 package 입력에서 bootstrap을 읽습니다. """
    payload = {item.path: item.data for item in files}
    if BOOTSTRAP_PATH not in payload:
        raise PackageError('native package에 초기 Python pin이 없습니다.')
    return load_bootstrap(payload[BOOTSTRAP_PATH], payload)


def load_platform_pins(data: bytes) -> dict[str, Any]:
    """! @brief native package의 SDK·board와 세 bundle 선언을 기존 고정 계약에 결합합니다. """
    from .serialization import strict_json_loads
    pins = strict_json_loads(data, source=PLATFORM_PINS_PATH)
    try:
        valid = (isinstance(pins, dict) and pins.get('schema_version') == 1
            and pins['ncs']['version'] == NCS_VERSION and pins['ncs']['revision'] == NCS_REVISION
            and pins['zephyr']['revision'] == ZEPHYR_REVISION and set(pins['platforms']) == set(PLATFORMS)
            and pins['platforms']['windows-x86_64']['toolchain']['bundle_id'] == TOOLCHAIN_BUNDLE_ID)
        for key in PLATFORMS:
            item = pins['platforms'][key]
            valid = valid and item['nrfutil']['version'] == '8.2.1' and item['sdk_manager']['version'] == '1.16.1'
            valid = valid and re.fullmatch(r'[0-9a-f]{10}', item['toolchain']['bundle_id']) is not None
    except (KeyError, TypeError, AttributeError) as error:
        raise PackageError('native Nordic pin 필드가 불완전합니다.') from error
    if not valid:
        raise PackageError('native Nordic pin이 SDK·세 Host 고정 계약과 다릅니다.')
    return pins


def tool_dependency(pins: dict[str, Any]) -> list[dict[str, str]]:
    """! @brief Nordic SDK 재배포 없이 고정 초기 Python 하나만 의존성으로 선언합니다. """
    return [{'packager': 'nucode', 'name': pins['runtime']['name'], 'version': pins['runtime']['tool_version']}]


def tool_definition(pins: dict[str, Any]) -> dict[str, Any]:
    """! @brief upstream byte를 보존한 실제 파생 archive 세 개의 private download record를 생성합니다. """
    return {'name': pins['runtime']['name'], 'version': pins['runtime']['tool_version'], 'systems': [
        {'host': item['arduino_host'], 'url': item['arduino_archive']['url'], 'archiveFileName': item['arduino_archive']['filename'],
         'size': str(item['arduino_archive']['size']), 'checksum': 'SHA-256:' + item['arduino_archive']['sha256']}
        for _, item in sorted(pins['platforms'].items())]}


def bootstrap_from_archive(archive: Any, version: str) -> dict[str, Any]:
    """! @brief 이미 전체 검증한 archive에서 실행 없이 bootstrap·license 원문을 읽습니다. """
    root = f'nucode-nu54dk-zephyr-{version}/'
    try:
        with zipfile.ZipFile(archive) as stream:
            data = stream.read(root + BOOTSTRAP_PATH)
            pins = load_bootstrap(data)
            payload = {'tools/nu54-prerequisites/' + item['path']:
                stream.read(root + 'tools/nu54-prerequisites/' + item['path']) for item in pins['notice_files']}
            return load_bootstrap(data, payload)
    except (KeyError, OSError, zipfile.BadZipFile) as error:
        raise PackageError('native archive의 bootstrap·license 원문을 읽을 수 없습니다.') from error


def rewrite_platform(data: bytes, pins: dict[str, Any]) -> bytes:
    """! @brief native package recipe를 system Python 탐색 없이 exact tool 경로에 결합합니다. """
    text = data.decode('utf-8')
    root = '{runtime.tools.' + pins['runtime']['name'] + '-' + pins['runtime']['tool_version'] + '.path}'
    entry = ' -I -B "{runtime.platform.path}/tools/nu54-builder/src/nu54_builder.py"'
    values = {'nu54.builder': f'"{root}/python.exe"' + entry,
        'nu54.builder.windows': f'"{root}/python.exe"' + entry,
        'nu54.builder.linux': f'"{root}/bin/python3.12"' + entry,
        'nu54.builder.macosx': f'"{root}/bin/python3.12"' + entry}
    counts = dict.fromkeys(values, 0)
    lines = []
    for line in text.splitlines():
        key = line.split('=', 1)[0]
        if key in values:
            counts[key] += 1
            line = key + '=' + values[key]
        elif line.startswith('# Windows command interpreter'):
            line = '# @brief Windows도 고정 초기 Python으로 같은 backend를 직접 실행합니다.'
        elif line.startswith('# POSIX Host는'):
            line = '# @brief POSIX도 고정 초기 Python으로 같은 backend를 직접 실행합니다.'
        lines.append(line)
    if any(count != 1 for count in counts.values()):
        raise PackageError('native package의 네 Host recipe가 정확히 하나씩 있어야 합니다.')
    return ('\n'.join(lines) + '\n').encode('utf-8')


def render_post_install(path: str, pins: dict[str, Any]) -> bytes:
    """! @brief 두 OS 진입점 모두 같은 Python 설치 backend에 argv만 전달합니다. """
    version = pins['runtime']['tool_version']
    if path == 'post_install.bat':
        text = f'''@echo off
setlocal EnableExtensions
set "NU54_PYTHON=%~dp0..\\..\\..\\tools\\nu54-python\\{version}\\python.exe"
if not exist "%NU54_PYTHON%" (
  echo [NU54:E_BOOTSTRAP] Pinned initial Python was not found. 1>&2
  exit /b 2
)
if defined NUCODE_NCS_INSTALL_ROOT (
  "%NU54_PYTHON%" -I -B "%~dp0tools\\nu54-prerequisites\\nordic.py" install --install-root "%NUCODE_NCS_INSTALL_ROOT%"
) else (
  "%NU54_PYTHON%" -I -B "%~dp0tools\\nu54-prerequisites\\nordic.py" install
)
exit /b %ERRORLEVEL%
'''
        return text.replace('\n', '\r\n').encode('ascii')
    if path != 'post_install.sh':
        raise PackageError('native 설치 진입점 경로가 잘못되었습니다.')
    text = f'''#!/bin/sh
# @brief 고정 초기 Python으로 공통 Nordic 설치 backend를 실행합니다.
set -eu
platform_directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
bootstrap_runtime="${{platform_directory}}/../../../tools/nu54-python/{version}/bin/python3.12"
if [ ! -x "${{bootstrap_runtime}}" ]; then
    echo '[NU54:E_BOOTSTRAP] Pinned initial Python was not found.' >&2
    exit 2
fi
if [ "${{NUCODE_NCS_INSTALL_ROOT+x}}" = x ]; then
    exec "${{bootstrap_runtime}}" -I -B "${{platform_directory}}/tools/nu54-prerequisites/nordic.py" install --install-root "${{NUCODE_NCS_INSTALL_ROOT}}" "$@"
fi
exec "${{bootstrap_runtime}}" -I -B "${{platform_directory}}/tools/nu54-prerequisites/nordic.py" install "$@"
'''
    return text.encode('utf-8')
