#!/usr/bin/env python3
"""! @brief native runner에서 실제 Boards Manager 설치·공개 예제 compile·artifact를 검증합니다. """
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import functools
import hashlib
import http.server
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import threading
import time
import urllib.request
import urllib.parse
import zipfile

ROOT = Path(__file__).resolve().parents[2]
SHARDS = 8


def load_module(name: str, path: Path):
    """! @brief 현재 checkout의 명시한 helper만 import합니다. """
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


P = load_module('native_package_consumer_producer', Path(__file__).with_name('host_native_package.py'))
S = load_module('native_package_consumer_semantics', Path(__file__).with_name('host_artifact_semantics.py'))
EXAMPLES = load_module('native_package_consumer_examples', Path(__file__).with_name('m33_w05_installed_examples.py'))


def write_json(path: Path, value):
    """! @brief 새 증거 파일만 작성하며 기존 attempt를 덮어쓰지 않습니다. """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def download(asset: dict, directory: Path) -> Path:
    """! @brief CI controller가 고정 CLI asset의 실제 SHA-256·크기를 먼저 검사합니다. """
    directory.mkdir(parents=True)
    target = directory / Path(urllib.parse.urlparse(asset['url']).path).name
    digest = hashlib.sha256()
    size = 0
    request = urllib.request.Request(asset['url'], headers={'User-Agent': 'NU54-native-package-CI'})
    with urllib.request.urlopen(request, timeout=60) as response, target.open('xb') as stream:
        while block := response.read(1024 * 1024):
            size += len(block)
            if size > asset['size']:
                raise ValueError('CLI archive 크기가 pin보다 큽니다.')
            digest.update(block)
            stream.write(block)
    if size != asset['size'] or digest.hexdigest() != asset['sha256']:
        raise ValueError('CLI archive의 고정 SHA-256·크기가 다릅니다.')
    return target


def unpack_cli(archive: Path, directory: Path, windows: bool) -> Path:
    """! @brief 검증한 CLI만 새 경로로 풀고 link·절대·탈출 경로를 거부합니다. """
    directory.mkdir()
    if windows:
        with zipfile.ZipFile(archive) as stream:
            for item in stream.infolist():
                relative = PurePosixPath(item.filename)
                if (relative.is_absolute() or '..' in relative.parts or '\\' in item.filename or ':' in item.filename
                        or stat.S_ISLNK(item.external_attr >> 16)):
                    raise ValueError('CLI ZIP에 안전하지 않은 경로가 있습니다.')
            stream.extractall(directory)
    else:
        with tarfile.open(archive, 'r:gz') as stream:
            if any(item.issym() or item.islnk() for item in stream.getmembers()):
                raise ValueError('CLI archive에 link가 있습니다.')
            stream.extractall(directory, filter='data')
    candidates = list(directory.rglob('arduino-cli.exe' if windows else 'arduino-cli'))
    if len(candidates) != 1 or not candidates[0].is_file():
        raise ValueError('공식 CLI executable이 정확히 하나 있어야 합니다.')
    return candidates[0].resolve()


def eligible_os_executable(path: Path) -> bool:
    """! @brief 접근할 수 없는 OS 관리 파일은 조회 대상에서 제외하고 금지 runtime은 허용하지 않습니다. """
    try:
        return not path.name.startswith(('python', 'pip', 'git')) and os.access(path, os.X_OK) and path.is_file()
    except OSError:
        return False


def consumer_environment(base: Path, host_os: str, install: Path) -> dict[str, str]:
    """! @brief system Python·Git fallback을 차단한 자식 환경만 만들고 사용자 전역은 바꾸지 않습니다. """
    environment = {name: value for name, value in os.environ.items()
        if not name.startswith('ACTIONS_') and name not in ('GH_TOKEN', 'GITHUB_TOKEN', 'SYSTEM_ACCESSTOKEN')
        and not re.search(r'(?:^|_)(?:TOKEN|SECRET|PASSWORD|CREDENTIAL)(?:_|$)', name, re.I)}
    for name in ('PYTHONHOME', 'PYTHONPATH', 'NUCODE_PYTHON', 'NUCODE_NCS_ROOT', 'NUCODE_TOOLCHAIN_ROOT', 'ZEPHYR_BASE'):
        environment.pop(name, None)
    if host_os == 'windows':
        system = Path(os.environ['SystemRoot'])
        environment['PATH'] = str(system / 'System32') + os.pathsep + str(system)
    else:
        binary = base / 'os-bin'
        binary.mkdir()
        for root in ('/usr/bin', '/bin', '/usr/sbin', '/sbin'):
            for original in Path(root).iterdir():
                if eligible_os_executable(original) and not (binary / original.name).exists():
                    (binary / original.name).symlink_to(original)
        for name in ('python', 'python3', 'python3.12', 'git', 'pip', 'pip3'):
            trap = binary / name
            trap.write_text('#!/bin/sh\necho HOST_FORBIDDEN_SYSTEM_TOOL:' + name + ' >&2\nexit 97\n', encoding='ascii')
            trap.chmod(0o755)
        environment['PATH'] = str(binary)
    (base / 't').mkdir()
    environment.update(TMP=str(base / 't'), TEMP=str(base / 't'), TMPDIR=str(base / 't'),
        PYTHONUTF8='1', PYTHONIOENCODING='utf-8', PYTHONDONTWRITEBYTECODE='1',
        NUCODE_PREREQUISITE_STATE_ROOT=str(base / 'state'), NUCODE_NCS_INSTALL_ROOT=str(install),
        NUCODE_BUILD_CACHE_ROOT=str(base / 'c'), NUCODE_BUILD_JOBS='2')
    return environment


def run(command: list[str], environment: dict[str, str], log: Path, timeout: int = 3600,
        required_rejection: str | None = None) -> subprocess.CompletedProcess:
    """! @brief 실제 argv·exit·부분 timeout 출력을 같은 attempt의 원문 로그로 보존합니다. """
    try:
        completed = subprocess.run(command, env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            timeout=timeout, check=False)
        output = completed.stdout
    except subprocess.TimeoutExpired as error:
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_bytes(error.stdout or b'')
        raise RuntimeError('native package 자식 명령 timeout: ' + log.name) from error
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open('xb') as stream:
        stream.write(output)
    expected = (completed.returncode != 0 and required_rejection.encode('utf-8') in output
        if required_rejection is not None else completed.returncode == 0)
    if not expected or b'HOST_FORBIDDEN_SYSTEM_TOOL:' in output:
        raise RuntimeError('native package 명령 실패: ' + log.name + ', exit=' + str(completed.returncode))
    return completed


class LocalIndexHandler(http.server.SimpleHTTPRequestHandler):
    """! @brief private Core ZIP·시험 index만 loopback에서 제공하며 외부 bind는 하지 않습니다. """

    def log_message(self, *_arguments):
        """! @brief HTTP 요청·경로를 공개 stdout에 누적하지 않습니다. """

    def list_directory(self, _path):
        """! @brief 디렉터리 목록은 노출하지 않습니다. """
        self.send_error(403)


def check_installed(platform: Path, archive: Path, version: str, source: str) -> dict:
    """! @brief archive의 모든 파일을 실제 설치 byte와 대조하고 개발 Git checkout으로 대체하지 않습니다. """
    manifest = json.loads((platform / 'release-manifest.json').read_text(encoding='utf-8'))
    if manifest['core_revision'] != source or manifest['version'] != version or (platform / '.git').exists():
        raise ValueError('Boards Manager 설치본의 source·version·형태가 다릅니다.')
    count = 0
    with zipfile.ZipFile(archive) as stream:
        prefix = f'nucode-nu54dk-zephyr-{version}/'
        for item in stream.infolist():
            if item.is_dir():
                continue
            if not item.filename.startswith(prefix):
                raise ValueError('private archive root가 다릅니다.')
            relative = item.filename[len(prefix):]
            expected = stream.read(item)
            actual = platform / relative
            if not actual.is_file() or hashlib.sha256(actual.read_bytes()).digest() != hashlib.sha256(expected).digest():
                raise ValueError('설치 package byte가 archive와 다릅니다: ' + relative)
            count += 1
    return {'source_revision': source, 'version': version, 'verified_archive_files': count, 'git_checkout_used_as_installation': False}


def setup(args, base: Path) -> tuple:
    """! @brief 고정 CLI로 package를 실제 설치하고 initial Python·ready marker를 대조합니다. """
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise ValueError('이 consumer는 GitHub native runner 전용입니다.')
    source = P.git(ROOT, 'rev-parse', 'HEAD')
    if source != args.source or source != os.environ['GITHUB_SHA'] or P.git(ROOT, 'status', '--porcelain=v1'):
        raise ValueError('native consumer는 exact clean CI source를 요구합니다.')
    package = P.load_package()
    package.configure_release_candidates(package.RELEASE_CANDIDATE_VERSIONS + (args.version,))
    producer = json.loads((args.producer / 'producer.json').read_text(encoding='utf-8'))
    if producer['source_revision'] != source or producer['version'] != args.version or not producer['reproducible_bytes']:
        raise ValueError('consumer와 producer source·version이 다릅니다.')
    package_dir = args.producer / 'package'
    archive = package_dir / producer['archive']['filename']
    index = package_dir / producer['index']['filename']
    if P.sha(archive) != producer['archive']['sha256'] or P.sha(index) != producer['index']['sha256']:
        raise ValueError('전달한 private archive·index SHA-256이 다릅니다.')
    manifest = package.validate_archive(archive, expected_version=args.version, expected_commit=source)
    package.validate_index(index, artifact_dir=package_dir)
    builder = load_module('native_consumer_host_descriptor', ROOT / 'tools/nu54-builder/src/nu54_builder.py')
    descriptor = builder.describe_host()
    builder.require_supported_host(descriptor)
    key = descriptor['os'] + '-' + descriptor['architecture']
    pins = json.loads((ROOT / 'tools/nu54-prerequisites/platform-pins.json').read_text(encoding='utf-8'))
    if set(base.iterdir()) - {base / 'state'}:
        raise ValueError('기존 consumer attempt를 덮어쓰지 않습니다.')
    state = base / 'state'
    if state.exists() and set(state.iterdir()) - {state / 'downloads'}:
        raise ValueError('download cache 외에 이전 설치 상태가 있습니다.')
    (base / 'reports').mkdir()
    (base / 'logs').mkdir()
    install = Path('/opt/nordic/ncs') if key == 'macos-arm64' else base / 'ncs'
    environment = consumer_environment(base, descriptor['os'], install)
    environment['SOURCE_DATE_EPOCH'] = str(producer['source_date_epoch'])
    cli_archive = download(pins['platforms'][key]['arduino_cli']['archive'], base / 'cli-download')
    cli = unpack_cli(cli_archive, base / 'cli', descriptor['os'] == 'windows')
    cli_identity = run([str(cli), 'version', '--json'], environment, base / 'logs/cli-version.log', 60)
    cli_version = json.loads(cli_identity.stdout)
    if (cli_version.get('Application') != 'arduino-cli'
            or cli_version.get('VersionString') != pins['platforms'][key]['arduino_cli']['version']):
        raise ValueError('실제 Arduino CLI version이 pin과 다릅니다.')
    config = base / 'arduino-cli.yaml'
    data = base / '한글 data'
    user = base / '한글 user'
    write_json(config, {'directories': {'data': data.as_posix(), 'downloads': (base / 'arduino-downloads').as_posix(), 'user': user.as_posix()}})
    mirror = base / 'mirror'
    mirror.mkdir()
    shutil.copyfile(archive, mirror / archive.name)
    handler = functools.partial(LocalIndexHandler, directory=str(mirror))
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
    address = 'http://127.0.0.1:' + str(server.server_address[1])
    local = json.loads(index.read_text(encoding='utf-8'))
    local['packages'][0]['platforms'][0]['url'] = address + '/' + archive.name
    for system in local['packages'][0]['tools'][0]['systems']:
        filename = system['archiveFileName']
        tool_archive = args.producer / 'bootstrap-tools' / filename
        if (tool_archive.stat().st_size != int(system['size'])
                or 'SHA-256:' + P.sha(tool_archive) != system['checksum']):
            raise ValueError('실제 파생 초기 runtime archive가 index pin과 다릅니다.')
        shutil.copyfile(tool_archive, mirror / filename)
        system['url'] = address + '/' + filename
    local_name = 'package_nucode_nu54dk_host_index.json'
    write_json(mirror / local_name, local)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = address + '/' + local_name
        run([str(cli), 'core', 'update-index', '--config-file', str(config), '--additional-urls', url], environment, base / 'logs/update-index.log')
        run([str(cli), 'core', 'install', 'nucode:zephyr@' + args.version, '--run-post-install',
            '--config-file', str(config), '--additional-urls', url], environment, base / 'logs/core-install.log')
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)
    platform = data / 'packages/nucode/hardware/zephyr' / args.version
    installed = check_installed(platform, archive, args.version, source)
    bootstrap_pins = json.loads((platform / package.implementation.inputs.native.BOOTSTRAP_PATH).read_text(encoding='utf-8'))
    runtime = data / 'packages/nucode/tools/nu54-python' / bootstrap_pins['runtime']['tool_version'] / bootstrap_pins['platforms'][key]['executable']
    result = run([str(runtime), '-I', '-B', '-c', 'import json,platform,sys;print(json.dumps({"version":platform.python_version(),"isolated":sys.flags.isolated}))'],
        environment, base / 'logs/initial-python.log', 60)
    identity = json.loads(result.stdout)
    if identity != {'version': bootstrap_pins['runtime']['python_version'], 'isolated': 1}:
        raise ValueError('실제 설치된 initial Python의 version·isolation이 다릅니다.')
    ready = json.loads((state / 'ready.json').read_text(encoding='utf-8'))
    if ready['status'] != 'ready' or ready['platform_key'] != key or ready['platform_pins_sha256'] != manifest['platform_prerequisites_sha256']:
        raise ValueError('실제 post-install ready marker와 exact package pin이 다릅니다.')
    environment.update(NUCODE_NCS_ROOT=str(install / pins['ncs']['version']), NUCODE_TOOLCHAIN_ROOT=str(install / 'toolchains' / pins['platforms'][key]['toolchain']['bundle_id']))
    run([str(runtime), '-I', '-B', str(platform / 'tools/nu54-prerequisites/nordic.py'), 'verify',
        '--install-root', str(install),
        '--evidence', str(base / 'reports/stored-verification.json')], environment, base / 'logs/stored-verification.log')
    private = base / 'private/CI-signing-key.pem'
    signed = run([str(runtime), '-I', '-B', str(Path(__file__).with_name('host_native_runtime.py')), '--platform', str(platform),
        '--signing-key', str(private)], environment, base / 'logs/signing-fixture.log', 120)
    signing = json.loads(signed.stdout)
    environment['NUCODE_DFU_SIGNING_KEY'] = str(private)
    context = {'schema_version': 1, 'source_revision': source, 'version': args.version, 'host': descriptor,
        'platform_key': key, 'archive_sha256': producer['archive']['sha256'], 'official_index_sha256': producer['index']['sha256'],
        'arduino_cli': {'version': cli_version['VersionString'], 'commit': cli_version.get('Commit'), 'executable_sha256': P.sha(cli)},
        'workflow_run_id': os.environ['GITHUB_RUN_ID'], 'workflow_run_attempt': int(os.environ.get('GITHUB_RUN_ATTEMPT', '1')),
        'loopback_index_sha256': P.sha(mirror / local_name), 'initial_python': identity, 'installed_snapshot': installed,
        'platform_prerequisites_sha256': manifest['platform_prerequisites_sha256'],
        'bootstrap_pins_sha256': manifest['bootstrap_pins_sha256'], 'bundle_id': pins['platforms'][key]['toolchain']['bundle_id'],
        'signing_fixture': signing, 'system_Python_or_Git_fallback_allowed': False,
        'hardware_operations': 0, 'user_physical_OS_gate': 'NOT_RUN'}
    write_json(base / 'reports/context.json', context)
    return cli, config, platform, environment, context, archive, builder, runtime


def discover(cli: Path, config: Path, platform: Path, catalog: dict, environment: dict, base: Path) -> list[dict]:
    """! @brief 같은 실제 파일 객체를 기준으로 CLI의 전체 설치 예제 발견을 검사합니다. """
    groups = {}
    for identity in catalog:
        groups.setdefault(identity.split('/', 1)[0], set()).add(identity)
    result = []
    for number, (directory, expected) in enumerate(sorted(groups.items())):
        library = platform / 'libraries' / directory
        name = EXAMPLES.library_name(library / 'library.properties')
        completed = run([str(cli), 'lib', 'examples', name, '--json', '--config-file', str(config)],
            environment, base / f'logs/discover-{number:02d}.log', 120)
        listing = json.loads(completed.stdout)
        entries = listing.get('examples') if isinstance(listing, dict) else None
        if not isinstance(entries, list) or len(entries) != 1 or not isinstance(entries[0], dict):
            raise ValueError('설치 library 발견 결과가 정확히 하나가 아닙니다: ' + directory)
        entry = entries[0]
        detail = entry.get('library', {})
        location = Path(str(detail.get('install_dir', '')))
        if detail.get('name') != name or not location.is_absolute() or not location.samefile(library):
            raise ValueError('다른 설치 library가 선택됐습니다: ' + directory)
        paths = entry.get('examples')
        if not isinstance(paths, list):
            raise ValueError('CLI 예제 목록이 배열이 아닙니다.')
        found = set()
        for raw in paths:
            path = Path(str(raw))
            if not path.is_absolute() or not path.parent.samefile(library / 'examples') or not (path / (path.name + '.ino')).is_file():
                raise ValueError('설치 예제 경로·실제 sketch가 다릅니다: ' + directory)
            found.add(directory + '/' + path.name)
        if found != expected or len(paths) != len(found):
            raise ValueError('CLI가 발견한 예제 분모가 metadata와 다릅니다: ' + directory)
        count, digest = EXAMPLES.tree_fingerprint(library)
        result.append({'directory': directory, 'example_count': len(found), 'file_count': count, 'tree_sha256': digest})
    if sum(row['example_count'] for row in result) != 204:
        raise ValueError('native 발견 예제 분모는204개여야 합니다.')
    return result


def validate_compiled(manifest: dict, build: Path, sketch: Path, fqbn: str, context: dict, builder) -> dict:
    """! @brief source·Host·SDK·bundle·실제 설치 sketch와 공개 artifact byte를 결합합니다. """
    common = builder.implementation.common
    inputs = manifest.get('cache', {}).get('input_manifest', {})
    pins = json.loads((ROOT / 'tools/nu54-prerequisites/platform-pins.json').read_text(encoding='utf-8'))
    if (manifest.get('fqbn') != fqbn or manifest.get('board') != EXAMPLES.TARGET_BOARD
            or inputs.get('adapter', {}).get('embedded_core_revision') != context['source_revision']
            or inputs.get('board_package', {}).get('revision') != pins['board_revision']
            or inputs.get('ncs', {}).get('nrf_revision') != pins['ncs']['revision']
            or inputs.get('ncs', {}).get('zephyr_revision') != pins['zephyr']['revision']
            or inputs.get('toolchain', {}).get('bundle_id') != context['bundle_id']):
        raise ValueError('build manifest의 source·FQBN·고정 SDK·board·bundle이 다릅니다.')
    target = inputs.get('target', {})
    if (target.get('fqbn') != fqbn or target.get('board') != EXAMPLES.TARGET_BOARD
            or target.get('profile') != fqbn.rsplit('=', 1)[-1]
            or not isinstance(manifest.get('sysbuild'), bool) or target.get('sysbuild') is not manifest['sysbuild']):
        raise ValueError('build manifest의 profile·sysbuild 선택이 실제 요청과 다릅니다.')
    host = inputs.get('host', {})
    if any(host.get(key) != context['host'][key] for key in ('os', 'architecture', 'native')):
        raise ValueError('build manifest의 실제 Host가 다릅니다.')
    resources = manifest.get('resource_audit')
    if not isinstance(resources, dict) or any(not isinstance(resources.get(name), dict)
            or type(resources[name].get('used_bytes')) is not int or resources[name]['used_bytes'] < 0
            for name in ('flash', 'ram')):
        raise ValueError('build manifest에 실제 FLASH/RAM 계측이 없습니다.')
    sketch_root = Path(str(inputs.get('sketch', {}).get('root', '')))
    if not sketch_root.is_absolute() or not sketch_root.samefile(sketch):
        raise ValueError('build manifest가 실제 설치 sketch를 가리키지 않습니다.')
    files = {}
    names = ('elf', 'hex', 'bin', 'boot.hex') if manifest.get('sysbuild') is True else ('elf', 'hex')
    for name in names:
        record = manifest.get('artifacts', {}).get(name, {})
        path = Path(str(record.get('path', '')))
        if (not path.is_absolute() or not common.is_within(path, build) or not path.is_file()
                or path.stat().st_size == 0 or record.get('size') != path.stat().st_size
                or record.get('sha256') != P.sha(path)):
            raise ValueError('실제 build의 ELF·HEX 경계·size·hash가 다릅니다: ' + name)
        files[name] = path
    return files


def compile_one(number: int, identity: str, record: dict, cli: Path, config: Path, platform: Path,
        environment: dict, context: dict, builder, runtime: Path, base: Path, timeout: int) -> dict:
    """! @brief 한 설치 예제를 fresh build하고 ELF·HEX·원형 manifest를 보존합니다. """
    started = time.monotonic()
    profile = record['profile']
    sketch = Path(record['directory'])
    build = base / f'b/{number:03d}'
    build.mkdir(parents=True)
    parser_cache = base / f'p/{number:03d}'
    parser_cache.mkdir(parents=True)
    child_environment = dict(environment, PARSETAB_DIR=str(parser_cache))
    log = base / f'logs/compile-{number:03d}.log'
    row = {'identity': identity, 'profile': profile, 'status': 'FAIL', 'log': log.relative_to(base).as_posix()}
    fqbn = 'nucode:zephyr:nu54dk:feature_set=' + profile
    try:
        completed = run([str(cli), 'compile', '--config-file', str(config), '--fqbn', fqbn, '--build-path', str(build), str(sketch)],
            child_environment, log, timeout)
        row['actual_exit_code'] = completed.returncode
        manifests = list(build.glob('*.nu54-build.json'))
        if len(manifests) != 1:
            raise ValueError('실제 compile manifest가 정확히 하나가 아닙니다.')
        manifest = json.loads(manifests[0].read_text(encoding='utf-8'))
        files = validate_compiled(manifest, build, sketch, fqbn, context, builder)
        target = base / f'targets/{number:03d}'
        target.mkdir(parents=True)
        outputs = {}
        for name, path in {**files, 'manifest': manifests[0]}.items():
            destination = target / {'elf': 'app.elf', 'hex': 'app.hex', 'bin': 'app.signed.bin',
                'boot.hex': 'boot.hex', 'manifest': 'build-manifest.json'}[name]
            shutil.copyfile(path, destination)
            outputs[name] = {'path': destination.relative_to(base).as_posix(), 'sha256': P.sha(destination), 'size': destination.stat().st_size}
        row.update(status='PASS', outputs=outputs, ELF=S.elf_semantics(files['elf']), HEX=S.hex_semantics(files['hex']),
            sysbuild=manifest.get('sysbuild') is True, resource_audit=manifest.get('resource_audit'),
            compiler=manifest['cache']['input_manifest']['toolchain']['compiler'])
        if row['sysbuild']:
            verification_log = base / f'logs/verify-signed-{number:03d}.log'
            verified = run([str(runtime), '-I', '-B', str(Path(__file__).with_name('host_native_runtime.py')),
                '--platform', str(platform), '--signing-key', environment['NUCODE_DFU_SIGNING_KEY'],
                '--verify-image', str(files['bin'])], environment, verification_log, 120)
            verification = json.loads(verified.stdout)
            if verification.get('status') != 'PASS' or verification['public_key_sha256'] != context['signing_fixture']['public_key_sha256']:
                raise ValueError('signed application이 현재 CI signing fixture와 일치하지 않습니다.')
            public = bytes.fromhex(context['signing_fixture']['public_key_der_hex'])
            row.update(signature_verification=verification, signature_verification_log_sha256=P.sha(verification_log),
                boot_HEX=S.hex_semantics(files['boot.hex'], public))
    except Exception as error:
        row.update(status='FAIL', error_type=type(error).__name__, error=str(error).replace(str(base), '<WORK>'))
    row.update(elapsed_s=round(time.monotonic() - started, 3), log_sha256=P.sha(log) if log.is_file() else None)
    print('HOST_NATIVE_COMPILE=' + row['status'] + ';EXAMPLE=' + identity, flush=True)
    return row


def compile_negative(number: int, case: dict, catalog: dict, cli: Path, config: Path,
        environment: dict, base: Path) -> dict:
    """! @brief 원형9개 profile 거부 조건을 native 진입점에서도 실제 비성공 exit·marker로 확인합니다. """
    log = base / f'logs/negative-{number:02d}.log'
    row = {'id': case['id'], 'identity': case['identity'], 'profile': case['profile'],
        'required_marker': case['marker'], 'status': 'FAIL', 'log': log.relative_to(base).as_posix()}
    try:
        build = base / f'negative/{number:02d}'
        build.mkdir(parents=True)
        fqbn = 'nucode:zephyr:nu54dk:feature_set=' + case['profile']
        completed = run([str(cli), 'compile', '--config-file', str(config), '--fqbn', fqbn,
            '--build-path', str(build), str(catalog[case['identity']]['directory'])], environment, log,
            120, required_rejection=case['marker'])
        if list(build.glob('*.nu54-build.json')) or list(build.glob('*.elf')):
            raise ValueError('거부한 profile에 성공 artifact가 공개됐습니다.')
        row.update(status='PASS', actual_exit_code=completed.returncode, expected_rejection=True)
    except Exception as error:
        row.update(error_type=type(error).__name__, error=str(error).replace(str(base), '<WORK>'))
    row['log_sha256'] = P.sha(log) if log.is_file() else None
    return row


def main() -> int:
    """! @brief 실제 설치·발견 뒤 smoke 또는 정확한8분할 예제 compile 증거를 기록합니다. """
    parser = argparse.ArgumentParser()
    parser.add_argument('--producer', type=Path, required=True)
    parser.add_argument('--source', required=True)
    parser.add_argument('--version', choices=P.PRIVATE_VERSIONS, default=P.PRIVATE_VERSIONS[0])
    parser.add_argument('--work-root', type=Path, required=True)
    parser.add_argument('--mode', choices=('smoke', 'examples'), required=True)
    parser.add_argument('--shard-index', type=int, default=0)
    parser.add_argument('--jobs', type=int, choices=(1,), default=1)
    parser.add_argument('--compile-timeout', type=int, default=1200)
    args = parser.parse_args()
    base = args.work_root
    if (not base.is_absolute() or base == Path(base.anchor) or base.resolve().is_relative_to(ROOT.resolve())
            or not 0 <= args.shard_index < SHARDS or args.compile_timeout <= 0):
        raise ValueError('격리한 절대 work root와 유한 shard·timeout을 지정해야 합니다.')
    base.mkdir(parents=True, exist_ok=True)
    result = {'schema_version': 1, 'kind': 'HOST_NATIVE_BOARDS_MANAGER_CONSUMER', 'status': 'FAIL',
        'source_revision': args.source, 'version': args.version, 'mode': args.mode,
        'shard_index': args.shard_index, 'shard_count': SHARDS, 'hardware_operations': 0,
        'user_physical_OS_gate': 'NOT_RUN', 'started_utc': datetime.now(timezone.utc).isoformat()}
    try:
        cli, config, platform, environment, context, archive, builder, runtime = setup(args, base)
        result['context'] = context
        catalog = EXAMPLES.load_catalog(platform)
        result['discovery'] = discover(cli, config, platform, catalog, environment, base)
        ordered = sorted(catalog, key=str.casefold)
        selected = ['NUCODE_NU54DK/Blink'] if args.mode == 'smoke' else [identity for number, identity in enumerate(ordered) if number % SHARDS == args.shard_index]
        if not selected or any(identity not in catalog for identity in selected):
            raise ValueError('smoke 또는 shard의 예제 배정이 유효하지 않습니다.')
        result['assigned_identities'] = selected
        rows = []
        with ThreadPoolExecutor(max_workers=args.jobs) as pool:
            futures = [pool.submit(compile_one, number, identity, catalog[identity], cli, config, platform,
                environment, context, builder, runtime, base, args.compile_timeout) for number, identity in enumerate(selected)]
            for future in as_completed(futures):
                rows.append(future.result())
        rows.sort(key=lambda row: row['identity'].casefold())
        result['builds'] = rows
        negative_cases = [] if args.mode == 'smoke' else [(number, case) for number, case in enumerate(EXAMPLES.NEGATIVE_PROFILE_MATRIX)
            if number % SHARDS == args.shard_index]
        negatives = [compile_negative(number, case, catalog, cli, config, environment, base) for number, case in negative_cases]
        result['negative_profiles'] = negatives
        result['installed_snapshot_after'] = check_installed(platform, archive, args.version, args.source)
        result['summary'] = {'discovered': 204, 'assigned': len(selected),
            'passed': sum(row['status'] == 'PASS' for row in rows), 'failed': sum(row['status'] != 'PASS' for row in rows),
            'negative_assigned': len(negative_cases), 'negative_passed': sum(row['status'] == 'PASS' for row in negatives)}
        if (len(rows) == len(selected) and all(row['status'] == 'PASS' for row in rows)
                and all(row['status'] == 'PASS' for row in negatives)):
            result['status'] = 'PASS'
    except Exception as error:
        result.update(error_type=type(error).__name__, error=str(error).replace(str(base), '<WORK>'))
    result['finished_utc'] = datetime.now(timezone.utc).isoformat()
    write_json(base / 'reports/result.json', result)
    print(json.dumps({'status': result['status'], 'source_revision': args.source, 'mode': args.mode,
        'summary': result.get('summary'), 'error': result.get('error')}, ensure_ascii=False))
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
