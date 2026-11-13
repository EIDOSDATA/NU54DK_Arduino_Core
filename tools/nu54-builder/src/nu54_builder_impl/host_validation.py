"""! @brief exact build·SHA identity·공통 lock에 결합한 유한 Serial·ELF debug 검증입니다. """
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sys
import time

from .artifacts import validate_flash_manifest
from .build import load_context
from .common import AdapterError, atomic_write_json, canonical_path, file_sha256
from .environment import tool_environment
from .host_diagnostics import identity_hash, inspect_host
from .locking import build_lock, probe_lock
from .owned_process import finite_timeout, OwnedExecutionError, OwnedInterrupted, OwnedTimeout, run_owned
from .paths import adapter_paths, paths_from_context
from .upload import discover_pyocd_probe_ids, validate_flash_tool_identity, validate_runner_configuration


def select_identity(values, requested, identity, label):
    """! @brief 누락·중복·원문 identity를 장치 접근 전에 거부합니다. """
    if not re.fullmatch(r'[0-9a-f]{64}', requested or ''):
        raise AdapterError(f'[NU54:E_HOST_IDENTITY] {label} SHA-256이 필요합니다.')
    matches = [item for item in values if identity_hash(identity(item)) == requested]
    if len(matches) != 1:
        raise AdapterError(f'[NU54:E_HOST_IDENTITY] {label}의 일치 수가1이 아닙니다: {len(matches)}')
    return matches[0]


def select_serial(ports, serial_sha256, path_sha256=None):
    """! @brief serial identity를 유지하고 다중 VCOM일 때 path identity도 요구합니다. """
    values = list(ports)
    if path_sha256:
        selected = select_identity(values,path_sha256,lambda item:str(item.device),'serial path')
        return select_identity([selected],serial_sha256,lambda item:item.serial_number,'serial')
    return select_identity(values,serial_sha256,lambda item:item.serial_number,'serial')


def serial_echo(serial_sha256, path_sha256, timeout, rounds=3, *, ports=None, factory=None):
    """! @brief 두 번 열기·닫기와 재열거 뒤 유한 nonce echo를 확인합니다.
    @see https://pyserial.readthedocs.io/en/latest/pyserial_api.html
    """
    if ports is None:
        from serial.tools import list_ports
        ports = list_ports.comports
    if factory is None:
        from serial import Serial
        factory = Serial
    timeout = finite_timeout(timeout)
    if type(rounds) is not int or not 1 <= rounds <= 10:
        raise ValueError('Serial round는1~10이어야 합니다.')
    rows = []
    for cycle in range(2):
        selected = select_serial(ports(),serial_sha256,path_sha256)
        connection = factory(port=None,baudrate=115200,timeout=0.05,
            write_timeout=min(timeout,2),exclusive=True if os.name != 'nt' else None)
        connection.dtr = False
        connection.rts = False
        connection.port = selected.device
        try:
            connection.open()
            for number in range(rounds):
                payload = ('nu54-host-'+secrets.token_hex(12)).encode('ascii')
                expected = b'NUCODE_M6_ECHO:'+payload
                if connection.write(payload+b'\n') != len(payload)+1:
                    raise AdapterError('[NU54:E_HOST_SERIAL_WRITE] Serial 부분 쓰기입니다.')
                deadline = time.monotonic()+timeout
                received = bytearray()
                while time.monotonic() < deadline:
                    received.extend(connection.read(256))
                    if b'NUCODE_M6_ERROR:' in received:
                        raise AdapterError('[NU54:E_HOST_SERIAL_RUNTIME] SerialEcho가 오류를 보고했습니다.')
                    if expected+b'\r\n' in received or expected+b'\n' in received:
                        break
                    if len(received) > 65536:
                        raise AdapterError('[NU54:E_HOST_SERIAL_LIMIT] Serial 출력 제한을 초과했습니다.')
                else:
                    raise AdapterError('[NU54:E_HOST_SERIAL_TIMEOUT] exact nonce echo를 받지 못했습니다.')
                rows.append(dict(cycle=cycle,round=number,nonce_sha256=identity_hash(payload.decode()),
                    received_sha256=hashlib.sha256(received).hexdigest(),matched=True))
        finally:
            connection.close()
        if connection.is_open:
            raise AdapterError('[NU54:E_HOST_SERIAL_CLOSE] Serial port가 닫히지 않았습니다.')
    return dict(status='PASS',serial_sha256=serial_sha256,path_sha256=path_sha256,
        open_close_cycles=2,re_enumerated=True,rounds=rows,physical_USB_replug='NOT_RUN',
        dtr_requested=False,rts_requested=False,port_closed=True)


def serial_pair(first,second,timeout=10,*,ports=None,factory=None):
    """! @brief 두 NUS 공개 예제의 UART→BLE→UART를 양방향 fresh nonce로 검사합니다. """
    if ports is None:
        from serial.tools import list_ports
        ports = list_ports.comports
    if factory is None:
        from serial import Serial
        factory = Serial
    timeout = finite_timeout(timeout)
    selected = [select_serial(ports(),row['serial_sha256'],row.get('path_sha256')) for row in (first,second)]
    if str(selected[0].device) == str(selected[1].device):
        raise AdapterError('[NU54:E_HOST_SERIAL_PAIR] 서로 다른 VCOM 두 개가 필요합니다.')
    connections,rows = [],[]
    with contextlib.ExitStack() as stack:
        for port in selected:
            connection = factory(port=None,baudrate=115200,timeout=0.05,
                write_timeout=min(timeout,2),exclusive=True if os.name!='nt' else None)
            connections.append(connection)
            stack.callback(connection.close)
            connection.dtr = connection.rts = False
            connection.port = port.device
            connection.open()
        for sender,receiver in ((0,1),(1,0)):
            payload = ('nu54-nus-'+secrets.token_hex(12)).encode('ascii')
            if connections[sender].write(payload+b'\n') != len(payload)+1:
                raise AdapterError('[NU54:E_HOST_SERIAL_WRITE] NUS 부분 쓰기입니다.')
            deadline,received = time.monotonic()+timeout,bytearray()
            while time.monotonic() < deadline:
                received.extend(connections[receiver].read(256))
                if b'BLE error' in received or b'start failed' in received:
                    raise AdapterError('[NU54:E_HOST_NUS_RUNTIME] NUS 공개 예제가 오류를 보고했습니다.')
                if payload+b'\n' in received:
                    break
                if len(received) > 65536:
                    raise AdapterError('[NU54:E_HOST_SERIAL_LIMIT] NUS 출력 제한을 초과했습니다.')
            else:
                raise AdapterError('[NU54:E_HOST_NUS_TIMEOUT] 반대 보드에서 exact nonce를 받지 못했습니다.')
            rows.append(dict(sender=sender,receiver=receiver,matched=True,
                nonce_sha256=hashlib.sha256(payload).hexdigest(),received_sha256=hashlib.sha256(received).hexdigest()))
    if any(connection.is_open for connection in connections):
        raise AdapterError('[NU54:E_HOST_SERIAL_CLOSE] NUS VCOM이 닫히지 않았습니다.')
    return dict(status='PASS',directions=rows,ports_closed=True,
        security_or_external_interoperability_claimed=False)


def debug_elf(probe_sha256, elf, *, resume_only=False):
    """! @brief ELF로 PC symbol을 찾고 실제 명령 byte를 대조한 뒤 항상 resume합니다.
    @see https://github.com/pyocd/pyOCD/blob/main/docs/api_examples.md
    """
    from pyocd.core.helpers import ConnectHelper
    from pyocd.core.target import Target
    probe = select_identity(discover_pyocd_probe_ids(),probe_sha256,lambda item:item,'probe')
    os.environ['NUCODE_SELECTED_PROBE_SHA256']=probe_sha256
    guard_script=Path(__file__).resolve().parents[1]/'nu54_pyocd_guard.py'
    if not guard_script.is_file():
        raise AdapterError('[NU54:E_PROBE_BACKEND] 설치본의 probe 보호 진입점이 없습니다.')
    session = ConnectHelper.session_with_chosen_probe(unique_id=probe,blocking=False,
        return_first=False,options={'target_override':'nrf54l','connect_mode':'attach',
            'auto_unlock':False,'resume_on_disconnect':True,'frequency':1000000,
            'no_config':True,'user_script':str(guard_script),'jlink.non_interactive':False,
            'jlink.device':None,'jlink.power':False,
            'cache.read_code_from_elf':False,'cache.enable_memory':False,
            'cache.enable_register':False})
    if session is None:
        raise AdapterError('[NU54:E_HOST_DEBUG_PROBE] exact probe session을 만들지 못했습니다.')
    result = dict(status='FAIL',probe_sha256=probe_sha256,program_operations=0,reset_operations=0)
    with session:
        target = session.target
        try:
            if not resume_only:
                target.elf = str(elf)
                target.halt()
                deadline = time.monotonic()+2
                while target.get_state() != Target.State.HALTED:
                    if time.monotonic() >= deadline:
                        raise AdapterError('[NU54:E_HOST_DEBUG_HALT] halt 완료를 확인하지 못했습니다.')
                    time.sleep(0.01)
                pc = int(target.read_core_register('pc')) & ~1
                symbol = target.elf.symbol_decoder.get_symbol_for_address(pc)
                if symbol is None:
                    raise AdapterError('[NU54:E_HOST_DEBUG_SYMBOL] PC의 ELF symbol이 없습니다.')
                expected = bytes(target.elf.read(pc,2))
                actual = bytes(target.read_memory_block8(pc,2))
                if len(expected) != 2 or expected != actual:
                    raise AdapterError('[NU54:E_HOST_DEBUG_IMAGE] 실제 PC 명령과 ELF가 다릅니다.')
                result.update(pc=pc,symbol=symbol.name,instruction_hex=actual.hex(),
                    elf_sha256=file_sha256(elf),actual_instruction_matches_ELF=True)
        finally:
            target.resume()
            deadline = time.monotonic()+2
            while target.get_state() not in (Target.State.RUNNING,Target.State.SLEEPING):
                if time.monotonic() >= deadline:
                    raise AdapterError('[NU54:E_HOST_DEBUG_RESUME] 실행 복귀를 확인하지 못했습니다.')
                time.sleep(0.01)
            result['resumed'] = True
    result.update(status='PASS',probe_closed=True,resume_only=resume_only,
        actual_probe_guard=getattr(session.probe,'_nu54_probe_guard',None))
    return result


def blink_gpio(probe_sha256,elf):
    """! @brief 고정 NU54DK LED0 P2.09의 출력 변화를 읽기 전용으로 관측합니다.
    @details NCS3.4.0 nrfx/bsp/stable/mdk/nrf54l15_global.h의 P2_S=0x50050400,
    nrf54l15_types.h의 GPIO OUT=0x00·DIR=0x10을 사용합니다. 핀·register는 쓰지 않습니다.
    """
    from pyocd.core.helpers import ConnectHelper
    from pyocd.core.target import Target
    identity = debug_elf(probe_sha256,elf)
    probe = select_identity(discover_pyocd_probe_ids(),probe_sha256,lambda item:item,'probe')
    session = ConnectHelper.session_with_chosen_probe(unique_id=probe,blocking=False,return_first=False,
        options={'target_override':'nrf54l','connect_mode':'attach','auto_unlock':False,
            'resume_on_disconnect':True,'frequency':1000000,'cache.enable_memory':False,
            'no_config':True,'user_script':str(Path(__file__).resolve().parents[1]/'nu54_pyocd_guard.py'),
            'jlink.non_interactive':False,'jlink.device':None,'jlink.power':False})
    if session is None:
        raise AdapterError('[NU54:E_HOST_DEBUG_PROBE] exact probe session을 만들지 못했습니다.')
    samples = []
    with session:
        target = session.target
        if target.get_state() not in (Target.State.RUNNING,Target.State.SLEEPING) or not int(target.read32(0x50050410)) & (1<<9):
            raise AdapterError('[NU54:E_HOST_BLINK_DIRECTION] 실행 상태 또는 LED0 출력 방향이 다릅니다.')
        started = time.monotonic()
        while time.monotonic()-started < 2.2:
            samples.append(dict(seconds=round(time.monotonic()-started,4),value=(int(target.read32(0x50050400))>>9)&1))
            time.sleep(0.025)
        if target.get_state() not in (Target.State.RUNNING,Target.State.SLEEPING):
            raise AdapterError('[NU54:E_HOST_BLINK_RUNNING] 관측 뒤 target이 실행 중이 아닙니다.')
    transitions = sum(first['value'] != second['value'] for first,second in zip(samples,samples[1:]))
    if {row['value'] for row in samples} != {0,1} or transitions < 3:
        raise AdapterError('[NU54:E_HOST_BLINK_TRANSITIONS] LED0의 실제 반복 출력을 확인하지 못했습니다.')
    return dict(status='PASS',probe_sha256=probe_sha256,ELF_identity=identity,
        GPIO='P2.09',register_writes=0,transitions=transitions,samples=samples,
        visible_light_sensor='NOT_RUN',probe_closed=True)


def worker(arguments):
    """! @brief SDK Python child에서만 장치를 열고 오류 원문 identity를 출력하지 않습니다. """
    parser = argparse.ArgumentParser()
    parser.add_argument('operation',choices=('_serial','_debug','_resume','_blink','_pair'))
    parser.add_argument('--result',type=Path,required=True)
    parser.add_argument('--probe-sha256',required=True)
    parser.add_argument('--serial-sha256')
    parser.add_argument('--path-sha256')
    parser.add_argument('--peer-probe-sha256')
    parser.add_argument('--peer-serial-sha256')
    parser.add_argument('--peer-path-sha256')
    parser.add_argument('--elf',type=Path)
    parser.add_argument('--timeout-seconds',type=finite_timeout,default=5)
    args = parser.parse_args(arguments)
    try:
        select_identity(discover_pyocd_probe_ids(),args.probe_sha256,lambda value:value,'probe')
        if args.operation == '_serial':
            result = serial_echo(args.serial_sha256,args.path_sha256,args.timeout_seconds)
        elif args.operation == '_pair':
            select_identity(discover_pyocd_probe_ids(),args.peer_probe_sha256,lambda value:value,'peer probe')
            result = serial_pair(dict(serial_sha256=args.serial_sha256,path_sha256=args.path_sha256),
                dict(serial_sha256=args.peer_serial_sha256,path_sha256=args.peer_path_sha256),args.timeout_seconds)
        elif args.operation == '_blink':
            result = blink_gpio(args.probe_sha256,args.elf)
        else:
            result = debug_elf(args.probe_sha256,args.elf,resume_only=args.operation=='_resume')
        with args.result.open('x',encoding='utf-8') as stream:
            json.dump(result,stream,ensure_ascii=False,indent=2)
        print('NU54_HOST_WORKER_PASS')
        return 0
    except Exception as error:
        with args.result.open('x',encoding='utf-8') as stream:
            json.dump(dict(status='FAIL',error_type=type(error).__name__,
                marker=re.search(r'\[NU54:[A-Z_]+\]',str(error)).group(0)
                if re.search(r'\[NU54:[A-Z_]+\]',str(error)) else 'UNCLASSIFIED'),stream)
        print('NU54_HOST_WORKER_FAIL')
        return 1


def physical_check(args):
    """! @brief build 두 lock과 exact probe lock을 유지한 채 SDK child를 유한 실행합니다. """
    output = canonical_path(args.output_root)
    if not Path(args.output_root).is_absolute() or output.exists():
        raise AdapterError('[NU54:E_HOST_ATTEMPT] 새 절대 output directory가 필요합니다.')
    output.mkdir(parents=True)
    receipt = dict(status='FAIL',operation=args.operation,probe_sha256=args.probe_sha256,
        user_physical_OS_gate='PARTIAL_SINGLE_OPERATION',started_at_utc=time.time(),
        firmware_source_relabelled=False,physical_recovery_pending=args.operation in ('debug','blink'))
    try:
        tools = tool_environment(canonical_path(args.platform_root))
        paths = adapter_paths(args)
        with build_lock(paths['state_root'],operation='host-check-session'):
            context = load_context(args,create=False)
            contextual = paths_from_context(paths,context)
            with build_lock(contextual['workspace'],operation='host-check-cache'):
                validate_flash_tool_identity(context,tools)
                inputs = validate_flash_manifest(args)
                if inputs['manifest']['context'] != context:
                    raise AdapterError('[NU54:E_HOST_CONTEXT] 현재 session과 manifest가 다릅니다.')
                if inputs['manifest']['sysbuild']:
                    raise AdapterError('[NU54:E_HOST_CONTEXT] 대표 native 단일 image만 검증합니다.')
                validate_runner_configuration(inputs['zephyr_build'],'pyocd')
                probe = select_identity(discover_pyocd_probe_ids(),args.probe_sha256,lambda value:value,'probe')
                entry = Path(args.platform_root)/'tools/nu54-prerequisites/host-check.py'
                command = [tools['python'],'-I','-X','utf8','-B',entry,'_'+args.operation,
                    '--result',output/'worker.json','--probe-sha256',args.probe_sha256,
                    '--timeout-seconds',str(args.timeout_seconds)]
                if args.operation == 'serial':
                    command += ['--serial-sha256',args.serial_sha256]
                    if args.path_sha256:
                        command += ['--path-sha256',args.path_sha256]
                else:
                    command += ['--elf',inputs['elf']]
                receipt.update(manifest_sha256=file_sha256(inputs['manifest_path']),
                    elf_sha256=inputs['elf_sha256'],hex_sha256=inputs['hex_sha256'],
                    build_context=context,host_python=str(tools['python']))
                child_environment=dict(tools['environment'],NUCODE_SELECTED_PROBE_SHA256=args.probe_sha256,
                    NUCODE_ALLOW_JLINK_BACKEND='1' if args.allow_jlink_backend else '0')
                with probe_lock(probe):
                    interrupted = None
                    try:
                        result = run_owned(command,cwd=tools['ncs_root'],environment=child_environment,
                            capture_directory=output,timeout=min(1800,max(60,(args.timeout_seconds+min(args.timeout_seconds,2))*6+15)))
                        raw = result.stdout
                        receipt.update(child_exit_code=result.returncode,cleanup=result.cleanup)
                    except (OwnedTimeout,OwnedInterrupted,OwnedExecutionError) as error:
                        raw = error.output
                        receipt.update(child_exit_code=None,process_outcome=type(error).__name__,cleanup=error.cleanup)
                        interrupted = error
                    text = raw.decode('utf-8',errors='replace').replace(probe,'sha256:'+args.probe_sha256)
                    (output/'child.log').write_text(text,encoding='utf-8')
                    if args.operation in ('debug','blink') and (interrupted is not None or result.returncode != 0):
                        recovery = [tools['python'],'-I','-X','utf8','-B',entry,'_resume',
                            '--result',output/'resume.json','--probe-sha256',args.probe_sha256]
                        resumed = run_owned(recovery,cwd=tools['ncs_root'],environment=child_environment,
                            capture_directory=output,timeout=30)
                        (output/'resume.log').write_text(resumed.stdout.decode('utf-8',errors='replace').replace(probe,'sha256:'+args.probe_sha256),encoding='utf-8')
                        receipt['recovery_resume_exit'] = resumed.returncode
                        receipt['physical_recovery_pending'] = resumed.returncode != 0
                    if interrupted is not None:
                        raise interrupted
                    if result.returncode != 0:
                        raise AdapterError('[NU54:E_HOST_WORKER] 실패 원형과 worker.json을 확인하십시오.')
                    observed = json.loads((output/'worker.json').read_text(encoding='utf-8'))
                    if observed['status'] != 'PASS':
                        raise AdapterError('[NU54:E_HOST_WORKER] worker가 PASS를 보고하지 않았습니다.')
                    receipt.update(status='PASS',observed=observed,physical_recovery_pending=False)
    finally:
        atomic_write_json(output/'result.json',receipt)
    print(json.dumps(dict(status=receipt['status'],operation=args.operation,evidence=str(output/'result.json'))))


def manifest_namespace(path):
    """! @brief peer manifest의 실제 요청 identity를 기존 flash 검증기에 전달합니다. """
    document = json.loads(path.read_text(encoding='utf-8'))
    inputs = document['cache']['input_manifest']
    if not path.name.endswith('.nu54-build.json'):
        raise AdapterError('[NU54:E_HOST_CONTEXT] 실제 peer build manifest가 필요합니다.')
    return argparse.Namespace(manifest=str(path),platform_root=document['context']['platform_root'],
        build_path=str(path.parent),sketch_root=inputs['sketch']['root'],fqbn=document['fqbn'],
        project_name=path.name[:-len('.nu54-build.json')],board=document['board'],profile=inputs['target']['profile'])


def physical_pair(args):
    """! @brief 같은 source의 두 NUS image와 두 probe를 정렬된 lock 아래 결합합니다. """
    output = canonical_path(args.output_root)
    if not Path(args.output_root).is_absolute() or output.exists():
        raise AdapterError('[NU54:E_HOST_ATTEMPT] 새 절대 output directory가 필요합니다.')
    output.mkdir(parents=True)
    receipt = dict(status='FAIL',operation='ble-pair',physical_USB_replug='NOT_RUN',
        user_physical_OS_gate='PARTIAL_SINGLE_OPERATION',source_credits_combined=False)
    try:
        pair = [args,manifest_namespace(args.peer_manifest)]
        if canonical_path(pair[0].platform_root) != canonical_path(pair[1].platform_root):
            raise AdapterError('[NU54:E_HOST_CONTEXT] 같은 설치본의 두 NUS image가 필요합니다.')
        tools = tool_environment(canonical_path(args.platform_root))
        paths = [adapter_paths(item) for item in pair]
        with contextlib.ExitStack() as stack:
            for root in sorted({row['state_root'] for row in paths},key=str):
                stack.enter_context(build_lock(root,operation='host-nus-session'))
            contexts = [load_context(item,create=False) for item in pair]
            workspaces = [paths_from_context(row,context)['workspace'] for row,context in zip(paths,contexts)]
            for root in sorted(set(workspaces),key=str):
                stack.enter_context(build_lock(root,operation='host-nus-cache'))
            manifests = []
            for item,context in zip(pair,contexts):
                validate_flash_tool_identity(context,tools)
                actual = validate_flash_manifest(item)
                if actual['manifest']['context'] != context:
                    raise AdapterError('[NU54:E_HOST_CONTEXT] 실제 NUS session과 manifest가 다릅니다.')
                manifests.append(actual)
            sources = [row['manifest']['cache']['input_manifest']['adapter']['embedded_core_revision'] for row in manifests]
            if sources[0] != sources[1]:
                raise AdapterError('[NU54:E_HOST_CONTEXT] 서로 다른 source의 NUS image입니다.')
            platform = canonical_path(args.platform_root)
            for item,name in zip(pair,('NUSPeripheral','NUSCentral')):
                if canonical_path(item.sketch_root) != platform/'libraries/NUCODE_BLE/examples'/name:
                    raise AdapterError('[NU54:E_HOST_CONTEXT] 공개 NUS Peripheral/Central 설치 예제가 필요합니다.')
            probes = [select_identity(discover_pyocd_probe_ids(),value,lambda item:item,'probe')
                for value in (args.probe_sha256,args.peer_probe_sha256)]
            if len(set(probes)) != 2:
                raise AdapterError('[NU54:E_HOST_SERIAL_PAIR] 서로 다른 probe 두 개가 필요합니다.')
            for probe in sorted(probes,key=str.casefold):
                stack.enter_context(probe_lock(probe))
            entry = platform/'tools/nu54-prerequisites/host-check.py'
            command = [tools['python'],'-I','-X','utf8','-B',entry,'_pair','--result',output/'worker.json',
                '--probe-sha256',args.probe_sha256,'--peer-probe-sha256',args.peer_probe_sha256,
                '--serial-sha256',args.serial_sha256,'--peer-serial-sha256',args.peer_serial_sha256,
                '--timeout-seconds','10']
            for name in ('path_sha256','peer_path_sha256'):
                if getattr(args,name,None):
                    command += ['--'+name.replace('_','-'),getattr(args,name)]
            try:
                result = run_owned(command,cwd=tools['ncs_root'],environment=tools['environment'],capture_directory=output,timeout=60)
                raw = result.stdout
                receipt.update(child_exit_code=result.returncode,cleanup=result.cleanup)
            except (OwnedTimeout,OwnedInterrupted,OwnedExecutionError) as error:
                raw = error.output
                receipt.update(process_outcome=type(error).__name__,cleanup=error.cleanup)
                raise
            finally:
                if 'raw' in locals():
                    text = raw.decode('utf-8',errors='replace')
                    for probe in probes:
                        text = text.replace(probe,'sha256:'+identity_hash(probe))
                    (output/'child.log').write_text(text,encoding='utf-8')
            if result.returncode != 0:
                raise AdapterError('[NU54:E_HOST_WORKER] NUS 실패 원형을 확인하십시오.')
            observed = json.loads((output/'worker.json').read_text(encoding='utf-8'))
            if observed['status'] != 'PASS':
                raise AdapterError('[NU54:E_HOST_WORKER] NUS 양방향 PASS가 없습니다.')
            receipt.update(status='PASS',observed=observed,source_revision=sources[0],
                build_manifest_sha256=[file_sha256(row['manifest_path']) for row in manifests],
                probes_sha256=[identity_hash(probe) for probe in probes])
    finally:
        atomic_write_json(output/'result.json',receipt)
    print(json.dumps(dict(status='PASS',evidence=str(output/'result.json'))))


def main(arguments=None):
    """! @brief inventory와 장치 작업을 구분하며 미실행 항목을 PASS로 올리지 않습니다. """
    arguments = list(sys.argv[1:] if arguments is None else arguments)
    if arguments and arguments[0].startswith('_'):
        return worker(arguments)
    from .cli import add_common_arguments
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='operation',required=True)
    inventory = sub.add_parser('inventory')
    inventory.add_argument('--evidence',type=Path)
    for name in ('serial','debug','blink','ble-pair'):
        command = sub.add_parser(name)
        add_common_arguments(command)
        command.add_argument('--manifest',required=True)
        command.add_argument('--probe-sha256',required=True)
        command.add_argument('--output-root',required=True)
        command.add_argument('--timeout-seconds',type=finite_timeout,default=5)
        command.add_argument('--allow-jlink-backend',action='store_true')
        if name in ('serial','ble-pair'):
            command.add_argument('--serial-sha256',required=True)
            command.add_argument('--path-sha256')
        if name == 'ble-pair':
            command.add_argument('--peer-manifest',type=Path,required=True)
            command.add_argument('--peer-probe-sha256',required=True)
            command.add_argument('--peer-serial-sha256',required=True)
            command.add_argument('--peer-path-sha256')
    args = parser.parse_args(arguments)
    try:
        if args.operation == 'inventory':
            result = inspect_host(include_probes=True)
            if args.evidence:
                if args.evidence.exists():
                    raise AdapterError('[NU54:E_HOST_ATTEMPT] 기존 inventory 증거를 덮어쓰지 않습니다.')
                atomic_write_json(args.evidence,result)
            print(json.dumps(result,ensure_ascii=False))
            return 0 if result['probes']['status']=='ENUMERATED' and result['serial']['status']=='ENUMERATED' else 1
        if args.operation=='ble-pair':
            physical_pair(args)
        else:
            physical_check(args)
        return 0
    except KeyboardInterrupt:
        print('[NU54:E_HOST_INTERRUPTED] 부분 출력·정리 결과를 새 attempt에서 확인하십시오.',file=sys.stderr)
        return 130
    except (AdapterError,OSError,ValueError,OwnedExecutionError) as error:
        marker = re.search(r'\[NU54:[A-Z_]+\]',str(error))
        print(marker.group(0) if marker else '[NU54:E_HOST_CHECK]',file=sys.stderr)
        return 2
