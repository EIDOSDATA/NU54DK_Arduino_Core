#!/usr/bin/env python3
"""! @brief 비공개 native 후보의 격리 설치·갱신·재설치·제거를 source별로 검증합니다. """
from __future__ import annotations

import argparse
import copy
import functools
import http.server
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import threading

ROOT = Path(__file__).resolve().parents[2]


def load(name,path):
    """! @brief 같은 검토 source의 공통 모듈만 명시적으로 읽습니다. """
    spec = importlib.util.spec_from_file_location(name,path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


P = load('host_lifecycle_producer',ROOT/'tools/ci/host_native_package.py')
CONSUMER = load('host_lifecycle_consumer',ROOT/'tools/ci/host_native_package_consumer.py')
BUILDER = load('host_lifecycle_builder',ROOT/'tools/nu54-builder/src/nu54_builder.py')
OWNED = __import__(BUILDER.implementation.__name__+'.owned_process',fromlist=['run_owned'])


def require_upgrade(previous,current):
    """! @brief 명시한 시험 후보에서 RC1으로의 전이만 허용하고 암묵 downgrade는 거부합니다. """
    if (previous,current) != ('0.6.0-host.1','0.6.0-rc.1'):
        raise ValueError('E_HOST_DOWNGRADE_POLICY: 이 절차는 host.1에서 rc.1로의 갱신만 허용합니다.')


def verified_producer(directory,source,version):
    """! @brief package 원형의 source·version·재현성·archive/index hash를 모두 대조합니다. """
    record = json.loads((directory/'producer.json').read_text(encoding='utf-8'))
    if record['source_revision'] != source or record['version'] != version or record['reproducible_bytes'] is not True:
        raise ValueError('producer source·version·재현성 계약이 다릅니다.')
    archive = directory/'package'/record['archive']['filename']
    index = directory/'package'/record['index']['filename']
    if archive.stat().st_size != record['archive']['size'] or P.sha(archive) != record['archive']['sha256'] or P.sha(index) != record['index']['sha256']:
        raise ValueError('producer 원형 hash가 다릅니다.')
    package = P.load_package(ROOT)
    package.configure_release_candidates(package.RELEASE_CANDIDATE_VERSIONS+(version,))
    package.validate_archive(archive,expected_version=version,expected_commit=source)
    package.validate_index(index,artifact_dir=directory/'package')
    return record,archive,json.loads(index.read_text(encoding='utf-8'))


def main(arguments=None):
    """! @brief 새 attempt만 사용하고 SDK·사용자 marker·원형 실패를 보존합니다. """
    parser = argparse.ArgumentParser()
    parser.add_argument('--current-producer',type=Path,required=True)
    parser.add_argument('--source',required=True)
    parser.add_argument('--previous-producer',type=Path,required=True)
    parser.add_argument('--previous-source',required=True)
    parser.add_argument('--work-root',type=Path,required=True)
    parser.add_argument('--sdk-root',type=Path,required=True)
    parser.add_argument('--prerequisite-root',type=Path,required=True)
    parser.add_argument('--cli-archive',type=Path,required=True)
    parser.add_argument('--run-post-install',action='store_true')
    args = parser.parse_args(arguments)
    if any(not path.is_absolute() for path in (args.work_root,args.sdk_root,args.prerequisite_root,args.cli_archive,args.current_producer,args.previous_producer)):
        raise ValueError('모든 root와 입력은 절대 경로여야 합니다.')
    if args.work_root.exists() or args.work_root.resolve().is_relative_to(ROOT):
        raise ValueError('source 밖의 새 attempt directory가 필요합니다.')
    require_upgrade('0.6.0-host.1','0.6.0-rc.1')
    old,old_archive,old_index = verified_producer(args.previous_producer,args.previous_source,'0.6.0-host.1')
    current,archive,index = verified_producer(args.current_producer,args.source,'0.6.0-rc.1')
    descriptor = BUILDER.require_supported_host(BUILDER.describe_host())
    key = descriptor['os']+'-'+descriptor['architecture']
    pins = json.loads((ROOT/'tools/nu54-prerequisites/platform-pins.json').read_text(encoding='utf-8'))
    cli_pin = pins['platforms'][key]['arduino_cli']['archive']
    if args.cli_archive.stat().st_size != cli_pin['size'] or P.sha(args.cli_archive) != cli_pin['sha256']:
        raise ValueError('공식 CLI archive의 size/SHA-256이 다릅니다.')
    args.work_root.mkdir(parents=True)
    base = args.work_root
    (base/'logs').mkdir()
    (base/'reports').mkdir()
    data,user,downloads = base/'한글 data',base/'한글 user',base/'downloads'
    user.mkdir()
    marker = user/'preserved-user-data.txt'
    marker.write_text('HOST lifecycle user data must survive\n',encoding='utf-8')
    marker_sha = P.sha(marker)
    ready = args.prerequisite_root/'ready.json'
    ready_sha = P.sha(ready)
    ready_identity = json.loads(ready.read_text(encoding='utf-8'))
    ready_identity.pop('SDK_archive_extracted',None)
    environment = dict(os.environ,NUCODE_NCS_INSTALL_ROOT=str(args.sdk_root),
        NUCODE_PREREQUISITE_STATE_ROOT=str(args.prerequisite_root),
        NUCODE_TOOLCHAIN_ROOT=str(args.sdk_root/'toolchains'/pins['platforms'][key]['toolchain']['bundle_id']),
        PYTHONUTF8='1',PYTHONIOENCODING='utf-8',PYTHONDONTWRITEBYTECODE='1')
    for name in ('PYTHONHOME','PYTHONPATH','GITHUB_SHA','GITHUB_ACTIONS'):
        environment.pop(name,None)
    cli = CONSUMER.unpack_cli(args.cli_archive,base/'cli',descriptor['os']=='windows')
    config = base/'arduino-cli.yaml'
    CONSUMER.write_json(config,{'directories':{'data':str(data),'downloads':str(downloads),'user':str(user)}})
    mirror = base/'mirror'
    mirror.mkdir()
    merged = copy.deepcopy(index)
    merged['packages'][0]['platforms'] += old_index['packages'][0]['platforms']
    if merged['packages'][0]['tools'] != old_index['packages'][0]['tools']:
        raise ValueError('전이 후보의 bootstrap tools pin이 다릅니다.')
    for source_archive in (old_archive,archive):
        shutil.copyfile(source_archive,mirror/source_archive.name)
    for system in merged['packages'][0]['tools'][0]['systems']:
        filename = system['archiveFileName']
        asset = args.current_producer/'bootstrap-tools'/filename
        if asset.stat().st_size != int(system['size']) or 'SHA-256:'+P.sha(asset) != system['checksum']:
            raise ValueError('초기 runtime 원형이 index pin과 다릅니다.')
        shutil.copyfile(asset,mirror/filename)
    handler = functools.partial(CONSUMER.LocalIndexHandler,directory=str(mirror))
    server = http.server.ThreadingHTTPServer(('127.0.0.1',0),handler)
    address = 'http://127.0.0.1:'+str(server.server_address[1])
    for platform in merged['packages'][0]['platforms']:
        platform['url'] = address+'/'+platform['archiveFileName']
    for system in merged['packages'][0]['tools'][0]['systems']:
        system['url'] = address+'/'+system['archiveFileName']
    index_name = 'package_nucode_nu54dk_host_index.json'
    CONSUMER.write_json(mirror/index_name,merged)
    url = address+'/'+index_name
    thread = threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    receipt = dict(kind='NATIVE_PRIVATE_LIFECYCLE',status='FAIL',source_revision=args.source,
        previous_source_revision=args.previous_source,host=descriptor,
        prior_source_build_credit_transferred=False,hardware_operations=0,
        physical_USB_gate='NOT_RUN',public_stable_migration='NOT_RUN_SEPARATE_WINDOWS_ROW',
        post_install_execution=('CURRENT_RC_UPGRADE_AND_REINSTALL' if args.run_post_install else
            'NOT_RUN_PREVERIFIED_SHARED_SDK_POLICY'),previous_candidate_post_install='SKIPPED',steps=[])

    def run(name,command,timeout=180):
        """! @brief 실제 exit·부분 출력·자식 정리를 단계별 새 파일로 남깁니다. """
        try:
            result = OWNED.run_owned(command,cwd=base,environment=environment,
                capture_directory=base/'logs',timeout=timeout)
            (base/'logs'/(name+'.log')).write_bytes(result.stdout)
            receipt['steps'].append(dict(name=name,exit_code=result.returncode,cleanup=result.cleanup))
            if result.returncode != 0:
                raise ValueError('lifecycle 명령 실패: '+name)
            return result.stdout
        except (OWNED.OwnedTimeout,OWNED.OwnedInterrupted,OWNED.OwnedExecutionError) as error:
            (base/'logs'/(name+'.log')).write_bytes(error.output)
            receipt['steps'].append(dict(name=name,outcome=type(error).__name__,cleanup=error.cleanup))
            raise

    def core(name,operation,version=None):
        """! @brief 격리 CLI data만 변경하고 전역 IDE·SDK를 제거하지 않습니다. """
        command = [cli,'core',operation]
        if version:
            command += ['nucode:zephyr@'+version] if operation=='install' else ['nucode:zephyr']
        if operation=='install':
            command += ['--run-post-install' if args.run_post_install and version=='0.6.0-rc.1' else '--skip-post-install']
        return run(name,[*command,'--config-file',config,'--additional-urls',url],900 if operation=='install' else 180)

    def snapshot(name,version,source,source_archive):
        """! @brief 설치 파일은 해당 version의 source 원형에만 대조합니다. """
        platform = data/'packages/nucode/hardware/zephyr'/version
        result = CONSUMER.check_installed(platform,source_archive,version,source)
        CONSUMER.write_json(base/'reports'/(name+'.json'),result)
        return platform,result

    try:
        identity = json.loads(run('cli-version',[cli,'version','--json'],60))
        if identity['VersionString'] != '1.5.1' or identity['Application'] != 'arduino-cli':
            raise ValueError('CLI actual version이 다릅니다.')
        core('index','update-index')
        core('install-previous','install','0.6.0-host.1')
        old_platform,_ = snapshot('previous','0.6.0-host.1',args.previous_source,old_archive)
        core('upgrade','install','0.6.0-rc.1')
        platform,first = snapshot('upgraded','0.6.0-rc.1',args.source,archive)
        actual_ready = json.loads(ready.read_text(encoding='utf-8'))
        actual_ready.pop('SDK_archive_extracted',None)
        if actual_ready != ready_identity:
            raise ValueError('갱신 post-install 뒤 공유 SDK identity가 달라졌습니다.')
        ready_sha = P.sha(ready)
        if old_platform.exists():
            raise ValueError('갱신 후 이전 package directory가 남았습니다.')
        core('same-version-install','install','0.6.0-rc.1')
        _,same = snapshot('same-version','0.6.0-rc.1',args.source,archive)
        if first != same:
            raise ValueError('동일 version install 뒤 설치 byte가 다릅니다.')
        try:
            require_upgrade('0.6.0-rc.1','0.6.0-host.1')
        except ValueError:
            receipt['downgrade_policy'] = 'EXPECTED_REJECTION_BEFORE_CLI_OR_SDK_MUTATION'
        else:
            raise ValueError('downgrade를 거부하지 않았습니다.')
        core('uninstall','uninstall','0.6.0-rc.1')
        if platform.exists() or not marker.is_file() or P.sha(marker) != marker_sha or P.sha(ready) != ready_sha:
            raise ValueError('제거 후 package 잔여 또는 사용자 데이터·공유 SDK marker 변경입니다.')
        core('reinstall','install','0.6.0-rc.1')
        platform,installed = snapshot('reinstalled','0.6.0-rc.1',args.source,archive)
        bootstrap = json.loads((platform/'tools/nu54-prerequisites/bootstrap-pins.json').read_text(encoding='utf-8'))
        runtime = data/'packages/nucode/tools/nu54-python'/bootstrap['runtime']['tool_version']/bootstrap['platforms'][key]['executable']
        runtime_identity = json.loads(run('managed-python',[runtime,'-I','-B','-c',
            'import json,platform,sys;print(json.dumps({"version":platform.python_version(),"isolated":sys.flags.isolated}))'],60))
        if runtime_identity != {'version':bootstrap['runtime']['python_version'],'isolated':1}:
            raise ValueError('설치한 관리 Python identity가 다릅니다.')
        run('installed-sdk-verify',[runtime,'-I','-B',platform/'tools/nu54-prerequisites/nordic.py',
            'verify','--install-root',args.sdk_root,'--evidence',base/'reports/sdk-verification.json'],180)
        catalog = CONSUMER.EXAMPLES.load_catalog(platform)
        ## @brief 전체 예제 발견 검사는 기존 공통 catalog parser와 설치 경로 대조를 사용합니다.
        discovery = CONSUMER.discover(cli,config,platform,catalog,environment,base)
        actual_ready = json.loads(ready.read_text(encoding='utf-8'))
        actual_ready.pop('SDK_archive_extracted',None)
        if P.sha(marker) != marker_sha or actual_ready != ready_identity:
            raise ValueError('검증 후 사용자 데이터·공유 SDK marker가 달라졌습니다.')
        receipt.update(status='PASS',installed_snapshot=installed,example_discovery=discovery,
            managed_python=runtime_identity,same_version_install='NOOP_BYTES_VERIFIED',
            uninstall_then_reinstall='PASS',user_data_preserved=True,shared_SDK_identity_preserved=True,
            platform=str(platform),cli=str(cli),config=str(config),cli_sha256=P.sha(cli))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)
        CONSUMER.write_json(base/'result.json',receipt)
    print(json.dumps({'status':receipt['status'],'evidence':str(base/'result.json')}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
