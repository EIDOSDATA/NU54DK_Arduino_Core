"""! @brief 고정 OS별 Nordic 자산을 설치·검증하는 공통 Python backend입니다. """

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse
import urllib.request

from .common import (
    AdapterError, NCS_REVISION, NCS_VERSION, ZEPHYR_REVISION,
    atomic_write_json, canonical_path, exact_git_revision, file_sha256, strict_json_object,
)
from .host import HostDescriptor, application_data_root, describe_host, require_supported_host, resolve_toolchain_executable
from .locking import build_lock

ROOT = Path(__file__).resolve().parents[4]
MANIFEST_PATH = ROOT / 'tools/nu54-prerequisites/platform-pins.json'
BUNDLES = {'windows-x86_64': 'dcbdc366a1', 'linux-x86_64': 'fbf7391cab', 'macos-arm64': 'ccc010f809'}


def require(condition: bool, code: str, message: str) -> None:
    """! @brief 설치 입력의 모호함이나 불일치를 명시적 오류로 거부합니다. """
    if not condition:
        raise AdapterError(f'[NU54:{code}] {message}')


def read_object(path: Path) -> dict[str, Any]:
    """! @brief 중복 key와 비-object root를 거부하며 JSON 파일을 읽습니다. """
    try:
        value = json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=strict_json_object)
    except (OSError, ValueError) as error:
        raise AdapterError(f'[NU54:E_HOST_JSON] JSON을 읽지 못했습니다: {path}: {error}') from error
    require(isinstance(value, dict), 'E_HOST_JSON', 'JSON root는 object여야 합니다.')
    return value


def validate_asset(asset: dict[str, Any]) -> None:
    """! @brief 공식 HTTPS 주소·정량 크기·SHA-256이 모두 있는 자산만 허용합니다. """
    require(isinstance(asset, dict), 'E_HOST_ASSET', '자산 설명은 object여야 합니다.')
    address = urlparse(str(asset.get('url', '')))
    require(address.scheme == 'https' and address.hostname in ('files.nordicsemi.com', 'github.com')
            and address.username is None and address.password is None
            and not address.query and not address.fragment
            and '..' not in address.path.split('/'), 'E_HOST_ASSET_URL', '공식 고정 HTTPS 자산 주소가 아닙니다.')
    require(bool(re.fullmatch(r'[0-9a-f]{64}', str(asset.get('sha256', ''))))
            and type(asset.get('size')) is int and asset['size'] > 0,
            'E_HOST_ASSET_HASH', '정확한 SHA-256과 양의 byte 크기가 필요합니다.')


def load_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    """! @brief 기존 Windows pin을 바꾸지 않고 세 Host의 동일 SDK 계약을 확인합니다. """
    document = read_object(path)
    require(document.get('schema_version') == 1 and document.get('work_package') == 'HOST-W04',
            'E_HOST_PINS', '지원하지 않는 platform pin schema입니다.')
    require(document.get('ncs', {}).get('version') == NCS_VERSION
            and document['ncs'].get('revision') == NCS_REVISION
            and document.get('zephyr', {}).get('revision') == ZEPHYR_REVISION,
            'E_HOST_SDK_PIN', 'NCS/Zephyr exact revision이 기존 SDK 계약과 다릅니다.')
    require(set(document.get('platforms', {})) == set(BUNDLES), 'E_HOST_PINS', '세 Host의 pin이 모두 필요합니다.')
    validate_asset(document['ncs']['archive'])
    for key, pin in document['platforms'].items():
        require(key == pin['os'] + '-' + pin['architecture']
                and pin['toolchain']['bundle_id'] == BUNDLES[key]
                and pin['nrfutil']['version'] == '8.2.1'
                and pin['sdk_manager']['version'] == '1.16.1'
                and pin['arduino_cli']['version'] == '1.5.1', 'E_HOST_TOOL_PIN', 'Host 도구의 고정 version/bundle이 다릅니다.')
        for asset in (pin['nrfutil']['executable'], pin['nrfutil']['core'],
                      pin['sdk_manager']['archive'], pin['toolchain']['archive'], pin['arduino_cli']['archive']):
            validate_asset(asset)
    return document


def select_platform(document: dict[str, Any], descriptor: HostDescriptor | None = None) -> tuple[str, dict[str, Any]]:
    """! @brief 실행 중인 native Host와 일치하는 pin 하나만 선택합니다. """
    current = require_supported_host(descriptor or describe_host())
    key = current['os'] + '-' + current['architecture']
    require(key in document['platforms'], 'E_HOST_PLATFORM_PIN', '현재 OS/architecture pin이 없습니다.')
    return key, document['platforms'][key]


def absolute_root(value: str | Path) -> Path:
    """! @brief 빈 경로·상대 경로와 POSIX에서의 Windows 경로 오해석을 거부합니다. """
    text = str(value)
    require(bool(text.strip()) and Path(text).is_absolute(), 'E_HOST_PATH', '절대 경로를 지정해야 합니다.')
    require(os.name == 'nt' or not PureWindowsPath(text).drive, 'E_HOST_PATH', 'POSIX에서 Windows 경로를 사용할 수 없습니다.')
    return canonical_path(text)


def roots(pin: dict[str, Any], state_root: Path | None = None, install_root: Path | None = None) -> tuple[Path, Path]:
    """! @brief OS별 사용자 상태와 SDK 설치 경로를 계산하고 macOS 고정 경로를 지킵니다. """
    state = absolute_root(state_root or application_data_root() / 'NUCODE/NU54DK_Arduino_Core/prerequisites')
    default = Path('/opt/nordic/ncs') if pin['os'] == 'macos' else Path.home() / 'ncs'
    install = absolute_root(install_root or default)
    if pin['os'] == 'macos':
        require(install == canonical_path(pin['required_install_root']), 'E_HOST_INSTALL_ROOT', 'macOS sdk-manager는 /opt/nordic/ncs를 요구합니다.')
    return state, install


def checked_download(asset: dict[str, Any], cache_root: Path) -> Path:
    """! @brief 부분 다운로드·변조 cache가 완료 파일로 승격되지 않게 합니다. """
    validate_asset(asset)
    cache_root = absolute_root(cache_root)
    cache_root.mkdir(parents=True, exist_ok=True)
    destination = cache_root / (asset['sha256'] + '-' + Path(urlparse(asset['url']).path).name)
    if destination.exists():
        require(destination.is_file() and destination.stat().st_size == asset['size']
                and file_sha256(destination) == asset['sha256'], 'E_HOST_DOWNLOAD_HASH', '기존 cache byte가 고정 자산과 다릅니다.')
        return destination
    descriptor, temporary_name = tempfile.mkstemp(prefix='.download-', dir=cache_root)
    temporary = Path(temporary_name)
    try:
        digest, count = hashlib.sha256(), 0
        with os.fdopen(descriptor, 'wb') as stream:
            with urllib.request.urlopen(asset['url'], timeout=60) as response:
                require(urlparse(response.geturl()).scheme == 'https', 'E_HOST_DOWNLOAD_URL', 'HTTPS 밖으로 이동한 다운로드를 거부합니다.')
                while chunk := response.read(1024 * 1024):
                    count += len(chunk)
                    require(count <= asset['size'], 'E_HOST_DOWNLOAD_SIZE', '공식 자산 크기를 초과했습니다.')
                    digest.update(chunk)
                    stream.write(chunk)
        require(count == asset['size'] and digest.hexdigest() == asset['sha256'],
                'E_HOST_DOWNLOAD_HASH', '다운로드 size/SHA-256이 공식 pin과 다릅니다.')
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()
    return destination


def run(command: Sequence[str | Path], environment: Mapping[str, str], timeout: int = 1800) -> str:
    """! @brief shell 재해석 없이 실행하고 timeout·실패 출력을 보존합니다. """
    try:
        result = subprocess.run([str(value) for value in command], env=dict(environment),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            encoding='utf-8', errors='replace', timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise AdapterError(f'[NU54:E_HOST_COMMAND] 명령 실행 실패: {error}') from error
    require(result.returncode == 0, 'E_HOST_COMMAND', f'종료 code={result.returncode}: {result.stdout}')
    return result.stdout.strip()


def verify_version_output(output: str, name: str, version: str, target: str) -> None:
    """! @brief 공식 다중 행 version metadata를 해석하되 버전·Host 불일치와 잡음을 거부합니다. """
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    executable = r'(?:nrfutil-)?sdk-manager' if name == 'sdk-manager' else 'nrfutil'
    require(bool(lines) and bool(re.fullmatch(executable + ' ' + re.escape(version)
            + r'(?:\s+\([^\r\n]+\))?', lines[0])), 'E_HOST_TOOL_VERSION', f'{name}의 고정 version {version}이 아닙니다.')
    fields = {}
    allowed = {'commit-hash', 'commit-date', 'host', 'build-timestamp', 'classification'}
    for line in lines[1:]:
        key, separator, value = line.partition(':')
        require(bool(separator) and key in allowed and key not in fields and bool(value.strip()),
                'E_HOST_TOOL_VERSION', '알 수 없거나 중복된 version metadata입니다.')
        fields[key] = value.strip()
    if 'host' in fields:
        require(fields['host'] == target, 'E_HOST_TOOL_ARCH', '실행한 nRF Util의 target architecture가 다릅니다.')


def bootstrap(document: dict[str, Any], key: str, state: Path, cache: Path) -> tuple[Path, dict[str, str], dict[str, Any]]:
    """! @brief 사용자 전역 nrfutil 대신 전용 상태에 고정 launcher·core·command를 설치합니다. """
    pin = document['platforms'][key]
    launcher = checked_download(pin['nrfutil']['executable'], cache)
    core = checked_download(pin['nrfutil']['core'], cache)
    manager = checked_download(pin['sdk_manager']['archive'], cache)
    directory = state / 'bootstrap' / key
    directory.mkdir(parents=True, exist_ok=True)
    executable = directory / ('nrfutil.exe' if pin['os'] == 'windows' else 'nrfutil')
    if executable.exists():
        require(file_sha256(executable) == pin['nrfutil']['executable']['sha256'], 'E_HOST_NRFUTIL_HASH', '설치한 launcher byte가 다릅니다.')
    else:
        shutil.copyfile(launcher, executable)
    if pin['os'] != 'windows':
        executable.chmod(0o755)
    environment = {name: value for name, value in os.environ.items() if not name.startswith('NRFUTIL_')}
    environment.update(NRFUTIL_HOME=str(directory / 'home'), NRFUTIL_BOOTSTRAP_TARBALL_PATH=str(core))
    core_version = run([executable, '--version'], environment, 120)
    verify_version_output(core_version, 'nrfutil', pin['nrfutil']['version'], pin['target'])
    run([executable, 'install', '--tarball', manager], environment, 180)
    manager_version = run([executable, 'sdk-manager', '--version'], environment, 60)
    verify_version_output(manager_version, 'sdk-manager', pin['sdk_manager']['version'], pin['target'])
    record = {'schema_version': 1, 'status': 'bootstrap_verified', 'platform_key': key,
        'nrfutil_path': str(executable), 'nrfutil_version_output': core_version,
        'sdk_manager_version_output': manager_version, 'SDK_installed_or_verified': False}
    atomic_write_json(state / 'bootstrap.json', record)
    return executable, environment, record


def verify_install(document: dict[str, Any], key: str, install: Path) -> dict[str, Any]:
    """! @brief 실제 bundled Git로 SDK·Zephyr revision과 OS별 Toolchain manifest를 확인합니다. """
    pin = document['platforms'][key]
    ncs = install / document['ncs']['version']
    toolchain = install / 'toolchains' / pin['toolchain']['bundle_id']
    tc_manifest = read_object(toolchain / 'manifest.json')
    require(tc_manifest.get('bundle_id') == pin['toolchain']['bundle_id'], 'E_HOST_TOOLCHAIN', '설치한 bundle manifest가 다릅니다.')
    require((toolchain / 'environment.json').is_file(), 'E_HOST_TOOLCHAIN', 'Toolchain environment.json이 없습니다.')
    git = resolve_toolchain_executable(toolchain, 'git', host_os=pin['os'])
    require(exact_git_revision(ncs / 'nrf', git_executable=git) == document['ncs']['revision'], 'E_HOST_NCS_REVISION', 'NCS revision이 다릅니다.')
    require(exact_git_revision(ncs / 'zephyr', git_executable=git) == document['zephyr']['revision'], 'E_HOST_ZEPHYR_REVISION', 'Zephyr revision이 다릅니다.')
    from .environment import apply_toolchain_environment
    environment = apply_toolchain_environment(toolchain)
    resolved, versions = {}, {}
    for name in ('python', 'west', 'cxx', 'size'):
        executable = resolve_toolchain_executable(toolchain, name, host_os=pin['os'])
        resolved[name] = str(executable)
        versions[name] = run([executable, '--version'], environment, 60)
    return {'ncs_root': str(install), 'toolchain_root': str(toolchain),
        'ncs_revision': document['ncs']['revision'], 'zephyr_revision': document['zephyr']['revision'],
        'toolchain_bundle_id': pin['toolchain']['bundle_id'], 'resolved_tools': resolved,
        'tool_version_outputs': versions}


def verify_ready(document: dict[str, Any], key: str, state: Path, install: Path, manifest_path: Path) -> dict[str, Any]:
    """! @brief 완료 marker의 hash·경로·도구 실제 version과 SDK revision을 함께 재검사합니다. """
    ready = read_object(state / 'ready.json')
    pin = document['platforms'][key]
    directory = state / 'bootstrap' / key
    executable = directory / ('nrfutil.exe' if pin['os'] == 'windows' else 'nrfutil')
    expected = {'schema_version': 2, 'status': 'ready', 'platform_key': key,
        'platform_pins_sha256': file_sha256(manifest_path), 'ncs_version': document['ncs']['version'],
        'nrfutil_path': str(executable), 'nrfutil_sha256': pin['nrfutil']['executable']['sha256'],
        'nrfutil_version': pin['nrfutil']['version'], 'sdk_manager_version': pin['sdk_manager']['version']}
    require(all(ready.get(name) == value for name, value in expected.items()),
            'E_HOST_READY', '완료 marker와 현재 platform pin·도구 경로가 다릅니다.')
    require(executable.is_file() and file_sha256(executable) == pin['nrfutil']['executable']['sha256'],
            'E_HOST_NRFUTIL_HASH', '설치한 launcher byte가 고정 hash와 다릅니다.')
    environment = {name: value for name, value in os.environ.items() if not name.startswith('NRFUTIL_')}
    environment['NRFUTIL_HOME'] = str(directory / 'home')
    verify_version_output(run([executable, '--version'], environment, 60), 'nrfutil', pin['nrfutil']['version'], pin['target'])
    verify_version_output(run([executable, 'sdk-manager', '--version'], environment, 60), 'sdk-manager', pin['sdk_manager']['version'], pin['target'])
    actual = verify_install(document, key, install)
    require(all(ready.get(name) == value for name, value in actual.items()), 'E_HOST_READY', '완료 marker와 실제 SDK 설치가 다릅니다.')
    return dict(ready, stored_audit_only=True)


def extract_sdk(archive: Path, install: Path, version: str) -> tuple[Path, bool]:
    """! @brief 검증한 SDK byte를 변경 없이 안전하게 추출하고 기존 SDK는 덮어쓰지 않습니다. """
    require(bool(re.fullmatch(r'v\d+\.\d+\.\d+', version)), 'E_HOST_SDK_VERSION', '정확한 SDK version이 필요합니다.')
    destination = install / version
    if destination.exists():
        require(destination.is_dir(), 'E_HOST_SDK_PATH', 'SDK 설치 경로가 directory가 아닙니다.')
        return destination, False
    install.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.nu54-sdk-' + version + '-', dir=install))
    try:
        with tarfile.open(archive, mode='r:gz') as bundle:
            bundle.extractall(staging, filter='data')
        require((staging / 'nrf' / 'west.yml').is_file() and (staging / 'zephyr' / 'VERSION').is_file(),
                'E_HOST_SDK_ARCHIVE', 'SDK archive의 등록 root 구조가 다릅니다.')
        os.replace(staging, destination)
    except (OSError, tarfile.TarError) as error:
        raise AdapterError(f'[NU54:E_HOST_SDK_EXTRACT] 원본을 보존한 추출 실패: {staging}: {error}') from error
    return destination, True


def install_all(document: dict[str, Any], key: str, state: Path, install: Path, cache: Path, manifest_path: Path) -> dict[str, Any]:
    """! @brief 고정 archive를 설치하고 실제 검증이 끝난 경우에만 ready marker를 기록합니다. """
    incomplete = state / 'incomplete.json'
    atomic_write_json(incomplete, {'schema_version': 2, 'status': 'incomplete', 'platform_key': key})
    ready_path = state / 'ready.json'
    if ready_path.exists():
        ready_path.unlink()
    executable, environment, record = bootstrap(document, key, state, cache)
    pin = document['platforms'][key]
    toolchain = checked_download(pin['toolchain']['archive'], cache)
    sdk = checked_download(document['ncs']['archive'], cache)
    directory = [] if pin['os'] == 'macos' else ['--install-dir', str(install)]
    with build_lock(install, operation='host-sdk-install', timeout_seconds=30):
        run([executable, 'sdk-manager', 'toolchain', 'install', '--toolchain-bundle', toolchain,
             '--for-ncs-version', document['ncs']['version'], *directory], environment)
        sdk_root, extracted = extract_sdk(sdk, install, document['ncs']['version'])
        run([executable, 'sdk-manager', 'sdk', 'register', document['ncs']['version'],
             '--type', 'nrf', '--sdk-path', sdk_root,
             '--toolchain-bundle-id', pin['toolchain']['bundle_id'], *directory], environment)
    verified = verify_install(document, key, install)
    ready = dict(verified, schema_version=2, status='ready', platform_key=key,
        platform_pins_sha256=file_sha256(manifest_path), ncs_version=document['ncs']['version'],
        nrfutil_path=str(executable), nrfutil_sha256=pin['nrfutil']['executable']['sha256'],
        nrfutil_version=pin['nrfutil']['version'], sdk_manager_version=pin['sdk_manager']['version'],
        SDK_install_route='PINNED_ARCHIVE_EXTRACT_EXPLICIT_VERSION_BUNDLE_ROOT_REGISTER',
        SDK_archive_extracted=extracted, SDK_archive_sha256=document['ncs']['archive']['sha256'])
    atomic_write_json(ready_path, ready)
    incomplete.unlink()
    return ready


def main(arguments: Sequence[str] | None = None) -> int:
    """! @brief 계획·bootstrap·설치·저장 marker 검사를 서로 다른 실행 범위로 제공합니다. """
    parser = argparse.ArgumentParser()
    parser.add_argument('operation', choices=('plan', 'bootstrap', 'install', 'verify'))
    parser.add_argument('--manifest', type=Path, default=MANIFEST_PATH)
    parser.add_argument('--state-root', type=Path)
    parser.add_argument('--install-root', type=Path)
    parser.add_argument('--cache-root', type=Path)
    parser.add_argument('--evidence', type=Path)
    args = parser.parse_args(arguments)
    require(sys.version_info >= (3, 12), 'E_HOST_PYTHON', '초기 설치 backend에는 Python 3.12 이상이 필요합니다.')
    document = load_manifest(args.manifest)
    key, pin = select_platform(document)
    state, install = roots(pin, args.state_root, args.install_root)
    cache = absolute_root(args.cache_root or state / 'downloads')
    result = {'schema_version': 1, 'status': 'planned', 'platform_key': key,
        'platform_pins_sha256': file_sha256(args.manifest), 'state_root': str(state),
        'install_root': str(install), 'cache_root': str(cache), 'hardware_operations': 0}
    if args.operation != 'plan':
        with build_lock(state, operation='host-prerequisites', timeout_seconds=30):
            if args.operation == 'bootstrap':
                result = bootstrap(document, key, state, cache)[2]
            elif args.operation == 'install':
                result = install_all(document, key, state, install, cache, args.manifest)
            else:
                result = verify_ready(document, key, state, install, args.manifest)
    result.update(operation=args.operation, host_descriptor=describe_host(), hardware_operations=0,
        platform_pins_sha256=file_sha256(args.manifest), backend_sha256=file_sha256(Path(__file__)),
        source_revision=os.environ.get('GITHUB_SHA'),
        implementation_scope='exact_CI_checkout' if os.environ.get('GITHUB_SHA') else 'local_development_worktree')
    if args.evidence is not None:
        atomic_write_json(args.evidence, result)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0
