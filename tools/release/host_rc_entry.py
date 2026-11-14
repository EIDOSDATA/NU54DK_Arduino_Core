#!/usr/bin/env python3
"""! @brief 비공개 RC kit의 설치·회귀·장치 검증을 단계별 새 attempt로 실행합니다. """
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]


def load(name,path):
    """! @brief 확인한 kit source의 절대 파일만 읽습니다. """
    spec = importlib.util.spec_from_file_location(name,path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def file_sha256(path):
    """! @brief 외부 tooling을 import하기 전에 표준 라이브러리만으로 원형을 검사합니다. """
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def verify_kit(kit):
    """! @brief kit manifest의 모든 원형 byte를 실행 전에 대조합니다. """
    manifest = json.loads((kit/'kit-manifest.json').read_text(encoding='utf-8'))
    if manifest['kind'] != 'UNPUBLISHED_PRIVATE_HOST_RC1_KIT' or manifest['version'] != '0.6.0-rc.1':
        raise ValueError('지원하는 private RC1 kit가 아닙니다.')
    if not re.fullmatch(r'[0-9a-f]{40}',manifest.get('source_revision','')) or manifest.get('expected_technical_source') != manifest['source_revision']:
        raise ValueError('kit의 exact source identity가 다릅니다.')
    seen = set()
    for row in manifest['files']:
        relative = PurePosixPath(row['path'])
        if relative.is_absolute() or '..' in relative.parts or relative.as_posix() in seen:
            raise ValueError('kit 원장 경로가 안전하지 않거나 중복됐습니다.')
        path = kit/relative
        if path.is_symlink() or not path.is_file() or path.stat().st_size != row['size'] or file_sha256(path) != row['sha256']:
            raise ValueError('kit 원형 byte 불일치: '+relative.as_posix())
        seen.add(relative.as_posix())
    required = {'source/tools/release/host_rc_entry.py','source/tools/release/host_native_lifecycle.py',
        'payload/current/producer.json','payload/previous/producer.json','source.tar','START.cmd','START.sh'}
    if not required.issubset(seen):
        raise ValueError('kit 원장에 필수 도구·전이 입력·진입점이 빠졌습니다.')
    if ROOT.resolve() != (kit/'source').resolve():
        raise ValueError('실행 중인 source가 이 kit에 포함된 source가 아닙니다.')
    return manifest


def build_arguments(path):
    """! @brief 실제 build manifest에서 공통 CLI identity를 읽고 파일명·source를 대조합니다. """
    manifest = json.loads(path.read_text(encoding='utf-8'))
    context = manifest['context']
    inputs = manifest['cache']['input_manifest']
    suffix = '.nu54-build.json'
    if not path.name.endswith(suffix):
        raise ValueError('실제 build manifest 경로가 아닙니다.')
    values = dict(platform_root=context['platform_root'],build_path=str(path.parent),
        sketch_root=inputs['sketch']['root'],fqbn=manifest['fqbn'],board=manifest['board'],
        profile=inputs['target']['profile'],project_name=path.name[:-len(suffix)],manifest=str(path))
    return [item for key,value in values.items() for item in ('--'+key.replace('_','-'),value)]


def main(arguments=None):
    """! @brief 공개·자동 예약·정식 지원 승격 없이 요청한 한 단계만 실행합니다. """
    global L
    parser = argparse.ArgumentParser()
    parser.add_argument('--kit',type=Path,required=True)
    parser.add_argument('--work-root',type=Path,required=True)
    parser.add_argument('--sdk-root',type=Path)
    sub = parser.add_subparsers(dest='operation',required=True)
    for name in ('plan','install-sdk','lifecycle','inventory'):
        sub.add_parser(name)
    build_parser = sub.add_parser('build')
    build_parser.add_argument('--all-examples',action='store_true')
    for name in ('upload','serial','debug','blink'):
        command = sub.add_parser(name)
        command.add_argument('--example',choices=('blink','serial','nus-peripheral','nus-central'),required=True)
        command.add_argument('--probe-sha256',required=True)
        command.add_argument('--allow-jlink-backend',action='store_true')
        if name == 'serial':
            command.add_argument('--serial-sha256',required=True)
            command.add_argument('--path-sha256')
    pair = sub.add_parser('ble-pair')
    for name in ('probe-sha256','serial-sha256','peer-probe-sha256','peer-serial-sha256'):
        pair.add_argument('--'+name,required=True)
    pair.add_argument('--path-sha256')
    pair.add_argument('--peer-path-sha256')
    pair.add_argument('--allow-jlink-backend',action='store_true')
    args = parser.parse_args(arguments)
    if not args.kit.is_absolute() or not args.work_root.is_absolute() or args.work_root.resolve().is_relative_to(args.kit.resolve()):
        raise ValueError('kit 밖의 새 절대 work root가 필요합니다.')
    kit = args.kit.resolve()
    manifest = verify_kit(kit)
    L = load('host_rc_entry_lifecycle',ROOT/'tools/release/host_native_lifecycle.py')
    descriptor = L.BUILDER.require_supported_host(L.BUILDER.describe_host())
    key = descriptor['os']+'-'+descriptor['architecture']
    sdk = args.sdk_root or (Path('/opt/nordic/ncs') if descriptor['os']=='macos' else args.work_root/'sdk')
    if not sdk.is_absolute():
        raise ValueError('SDK root는 절대 경로여야 합니다.')
    state_root = args.work_root/'prerequisites'
    pins = json.loads((ROOT/'tools/nu54-prerequisites/platform-pins.json').read_text(encoding='utf-8'))
    plan = dict(source_revision=manifest['source_revision'],version=manifest['version'],host=descriptor,
        kit_manifest_sha256=L.P.sha(kit/'kit-manifest.json'),SDK_root=str(sdk),work_root=str(args.work_root),
        required_order=['install-sdk','lifecycle','build','inventory','upload','blink','serial','debug','ble-pair'],
        physical_USB_gate='NOT_RUN',publication='NOT_PUBLISHED')
    if args.operation=='plan':
        print(json.dumps(plan,ensure_ascii=False,indent=2))
        return 0
    attempts = args.work_root/'attempts'
    attempts.mkdir(parents=True,exist_ok=True)
    attempt = attempts/(args.operation+'-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    attempt.mkdir()
    environment = dict(os.environ,NUCODE_NCS_INSTALL_ROOT=str(sdk),NUCODE_NCS_ROOT=str(sdk/'v3.4.0'),
        NUCODE_PREREQUISITE_STATE_ROOT=str(state_root),
        NUCODE_TOOLCHAIN_ROOT=str(sdk/'toolchains'/pins['platforms'][key]['toolchain']['bundle_id']),
        NUCODE_BUILD_CACHE_ROOT=str(args.work_root/'c'),NUCODE_BUILD_JOBS='2',
        PYTHONUTF8='1',PYTHONIOENCODING='utf-8',PYTHONDONTWRITEBYTECODE='1')
    for name in ('PYTHONHOME','PYTHONPATH','GITHUB_SHA','GITHUB_ACTIONS','NUCODE_PROBE_UID'):
        environment.pop(name,None)
    state_path = args.work_root/'state.json'
    state = json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else dict(source_revision=manifest['source_revision'])
    if state['source_revision'] != manifest['source_revision']:
        raise ValueError('기존 work root는 다른 RC source입니다. 새 work root를 지정하십시오.')
    receipt = dict(plan,operation=args.operation,status='FAIL',steps=[])

    def run(name,command,timeout=180,expected_rejection=None):
        """! @brief 무한 대기·자동 재시도 없이 실제 출력과 cleanup을 보존합니다. """
        try:
            result = L.OWNED.run_owned(command,cwd=args.work_root,environment=environment,
                capture_directory=attempt,timeout=timeout)
            (attempt/(name+'.log')).write_bytes(result.stdout)
            expected = (result.returncode != 0 and expected_rejection.encode() in result.stdout
                if expected_rejection is not None else result.returncode == 0)
            receipt['steps'].append(dict(name=name,exit_code=result.returncode,cleanup=result.cleanup,
                expected_rejection=expected_rejection,expected_result_matched=expected))
            if not expected:
                raise ValueError('RC 단계 명령 실패: '+name)
            return result.stdout
        except (L.OWNED.OwnedTimeout,L.OWNED.OwnedInterrupted,L.OWNED.OwnedExecutionError) as error:
            (attempt/(name+'.log')).write_bytes(error.output)
            receipt['steps'].append(dict(name=name,outcome=type(error).__name__,cleanup=error.cleanup))
            raise

    try:
        if args.operation=='install-sdk':
            operation = 'verify' if (state_root/'ready.json').exists() else 'install'
            run('sdk',[sys.executable,'-I','-X','utf8','-B',ROOT/'tools/nu54-prerequisites/nordic.py',operation,
                '--state-root',state_root,'--install-root',sdk,'--cache-root',state_root/'downloads',
                '--evidence',attempt/'sdk.json'],1800)
            state['SDK_ready'] = str(state_root/'ready.json')
        elif args.operation=='lifecycle':
            work = attempt/'lifecycle'
            run('lifecycle',[sys.executable,'-I','-X','utf8','-B',ROOT/'tools/release/host_native_lifecycle.py',
                '--source',manifest['source_revision'],'--current-producer',kit/'payload/current',
                '--previous-source',manifest['previous_source_revision'],'--previous-producer',kit/'payload/previous',
                '--work-root',work,'--sdk-root',sdk,'--prerequisite-root',state_root,
                '--cli-archive',kit/manifest['cli_files'][key],'--run-post-install'],1800)
            observed = json.loads((work/'result.json').read_text(encoding='utf-8'))
            if observed['status'] != 'PASS':
                raise ValueError('lifecycle PASS가 없습니다.')
            state['installation'] = observed
        else:
            installed = state['installation']
            platform = Path(installed['platform'])
            current = json.loads((kit/'payload/current/producer.json').read_text(encoding='utf-8'))
            archive = kit/'payload/current/package'/current['archive']['filename']
            L.CONSUMER.check_installed(platform,archive,manifest['version'],manifest['source_revision'])
            sdk_python = L.BUILDER.resolve_toolchain_executable(Path(environment['NUCODE_TOOLCHAIN_ROOT']),'python')
            bootstrap = json.loads((platform/'tools/nu54-prerequisites/bootstrap-pins.json').read_text(encoding='utf-8'))
            runtime = Path(installed['config']).parent/'한글 data/packages/nucode/tools/nu54-python'/bootstrap['runtime']['tool_version']/bootstrap['platforms'][key]['executable']
            run('sdk-verify',[runtime,'-I','-X','utf8','-B',platform/'tools/nu54-prerequisites/nordic.py','verify',
                '--install-root',sdk,'--state-root',state_root,'--evidence',attempt/'sdk.json'],180)
            if args.operation=='build':
                catalog = L.CONSUMER.EXAMPLES.load_catalog(platform)
                state['builds'] = {}
                environment['NUCODE_BUILD_CACHE_ROOT'] = str(args.work_root/('c-'+L.P.sha(kit/'kit-manifest.json')[:6]+'-'+attempt.name[-13:-1]))
                if Path(environment['NUCODE_BUILD_CACHE_ROOT']).exists():
                    raise ValueError('cold build용 cache가 이미 존재합니다.')
                context = dict(source_revision=manifest['source_revision'],host=descriptor,
                    bundle_id=pins['platforms'][key]['toolchain']['bundle_id'])
                representatives = [('blink','NUCODE_NU54DK/Blink'),('serial','NUCODE_NU54DK/SerialEcho'),
                    ('nus-peripheral','NUCODE_BLE/NUSPeripheral'),('nus-central','NUCODE_BLE/NUSCentral')]
                aliases = {identity:alias for alias,identity in representatives}
                identities = sorted(catalog) if args.all_examples else [identity for alias,identity in representatives]
                if args.all_examples:
                    key_path = attempt/'private/host-test-key.pem'
                    run('signing-fixture',[runtime,'-I','-X','utf8','-B',ROOT/'tools/ci/host_native_runtime.py',
                        '--platform',platform,'--signing-key',key_path],120)
                    environment['NUCODE_DFU_SIGNING_KEY'] = str(key_path)
                    receipt['signing_fixture'] = 'LOCAL_TEST_ONLY_NOT_A_GITHUB_WORKFLOW_RECEIPT'
                for number,identity in enumerate(identities):
                    alias = aliases.get(identity,f'example-{number:03d}')
                    record = catalog[identity]
                    build = attempt/f'b/{number:03d}'
                    build.mkdir(parents=True)
                    environment['PARSETAB_DIR'] = str(attempt/f'p/{number:03d}')
                    Path(environment['PARSETAB_DIR']).mkdir(parents=True)
                    fqbn = 'nucode:zephyr:nu54dk:feature_set='+record['profile']
                    cold_key = None
                    for temperature in (('cold','warm') if identity in aliases else ('cold',)):
                        run(alias+'-'+temperature,[installed['cli'],'compile','--config-file',installed['config'],
                            '--fqbn',fqbn,'--build-path',build,record['directory']],1200)
                        actual = list(build.glob('*.nu54-build.json'))
                        if len(actual) != 1:
                            raise ValueError('build manifest가 정확히 하나가 아닙니다.')
                        document = json.loads(actual[0].read_text(encoding='utf-8'))
                        files = L.CONSUMER.validate_compiled(document,build,Path(record['directory']),fqbn,context,L.BUILDER)
                        if temperature=='cold':
                            cold_key = document['cache']['key']
                        elif cold_key != document['cache']['key']:
                            raise ValueError('warm build의 cache identity가 cold와 다릅니다.')
                        if document['sysbuild']:
                            verified = json.loads(run(alias+'-signature',[runtime,'-I','-X','utf8','-B',
                                ROOT/'tools/ci/host_native_runtime.py','--platform',platform,
                                '--signing-key',key_path,'--verify-image',files['bin']],120))
                            if verified['status'] != 'PASS':
                                raise ValueError('실제 signed image 서명이 맞지 않습니다.')
                        shutil.copyfile(actual[0],attempt/(alias+'-'+temperature+'.json'))
                    if identity in aliases:
                        state['builds'][alias] = str(actual[0])
                receipt['cold_warm_examples'] = 4
                receipt['cold_positive_examples'] = len(identities)
                receipt['negative_profile_rejections'] = 0
                if args.all_examples:
                    for number,case in enumerate(L.CONSUMER.EXAMPLES.NEGATIVE_PROFILE_MATRIX):
                        directory = attempt/f'negative/{number:02d}'
                        directory.mkdir(parents=True)
                        run('negative-'+case['id'],[installed['cli'],'compile','--config-file',installed['config'],
                            '--fqbn','nucode:zephyr:nu54dk:feature_set='+case['profile'],'--build-path',directory,
                            catalog[case['identity']]['directory']],L.CONSUMER.NEGATIVE_PROFILE_TIMEOUT_SECONDS,expected_rejection=case['marker'])
                        if list(directory.glob('*.elf')) or list(directory.glob('*.nu54-build.json')):
                            raise ValueError('거부한 profile이 성공 artifact를 남겼습니다.')
                        receipt['negative_profile_rejections'] += 1
                receipt['all_204_examples'] = 'PASS' if args.all_examples else 'NOT_RUN_REPRESENTATIVES_ONLY'
            elif args.operation=='inventory':
                run('inventory',[sdk_python,'-I','-X','utf8','-B',platform/'tools/nu54-prerequisites/host-check.py',
                    'inventory','--evidence',attempt/'inventory.json'],60)
            else:
                example = 'nus-peripheral' if args.operation=='ble-pair' else args.example
                build_manifest = Path(state['builds'][example])
                common = build_arguments(build_manifest)
                if args.operation=='ble-pair':
                    command = [sdk_python,'-I','-X','utf8','-B',platform/'tools/nu54-prerequisites/host-check.py',
                        'ble-pair',*common,'--output-root',attempt/'physical',
                        '--peer-manifest',state['builds']['nus-central']]
                    for name in ('probe_sha256','serial_sha256','peer_probe_sha256','peer_serial_sha256',
                        'path_sha256','peer_path_sha256'):
                        if getattr(args,name,None):
                            command += ['--'+name.replace('_','-'),getattr(args,name)]
                    if args.allow_jlink_backend:
                        command += ['--allow-jlink-backend']
                    run('ble-pair',command,90)
                elif args.operation=='upload':
                    command=[sdk_python,'-I','-X','utf8','-B',platform/'tools/nu54-builder/src/nu54_builder.py',
                        'flash',*common,'--runner','pyocd','--probe-sha256',args.probe_sha256,
                        '--timeout-seconds','180']
                    if args.allow_jlink_backend:
                        command += ['--allow-jlink-backend']
                    run('upload',command,200)
                else:
                    if args.operation=='blink' and args.example != 'blink':
                        raise ValueError('LED GPIO 관측은 Blink image에만 사용하십시오.')
                    if args.operation=='serial' and args.example != 'serial':
                        raise ValueError('nonce echo 검사는 SerialEcho image에만 사용하십시오.')
                    command = [sdk_python,'-I','-X','utf8','-B',platform/'tools/nu54-prerequisites/host-check.py',
                        args.operation,*common,'--probe-sha256',args.probe_sha256,'--output-root',attempt/'physical']
                    if args.operation=='serial':
                        command += ['--serial-sha256',args.serial_sha256]
                        if args.path_sha256:
                            command += ['--path-sha256',args.path_sha256]
                    if args.allow_jlink_backend:
                        command += ['--allow-jlink-backend']
                    run('physical',command,90)
            state['last_operation'] = args.operation
        receipt['status'] = 'PASS'
        L.BUILDER.atomic_write_json(state_path,state)
    finally:
        L.CONSUMER.write_json(attempt/'result.json',receipt)
    print(json.dumps(dict(status='PASS',operation=args.operation,evidence=str(attempt/'result.json'))))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
