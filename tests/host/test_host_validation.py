"""! @brief 비식별 선택·유한 Serial oracle·재열거와 실패 시 close를 검증합니다. """
import importlib
import importlib.util
import contextlib
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('host_validation_builder',ROOT/'tools/nu54-builder/src/nu54_builder.py')
BUILDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILDER)
M = importlib.import_module(BUILDER.implementation.__name__+'.host_validation')


class HostValidationTests(unittest.TestCase):
    """! @brief mock Serial은 protocol·자원 반환만 검증하며 물리 PASS가 아닙니다. """
    def setUp(self):
        """! @brief 매 호출에 새로운 port와 수신 buffer를 사용합니다. """
        self.port = SimpleNamespace(device='fixture-port',serial_number='fixture-serial')
        self.digest = M.identity_hash(self.port.serial_number)
        self.instances = []

    def factory(self, *, reply=True, fail_write=False):
        """! @brief 실제 Serial 인터페이스의 open/write/read/close 경계를 모델링합니다. """
        instances = self.instances
        class Connection:
            """! @brief nonce를 정확히 반사하거나 의도한 오류만 생성합니다. """
            def __init__(self,**kwargs):
                """! @brief open 전 timeout·control line을 검증할 수 있게 보존합니다. """
                self.options = kwargs
                self.is_open = False
                self.buffer = b''
                instances.append(self)
            def open(self):
                """! @brief 이중 open은 허용하지 않습니다. """
                assert self.dtr is False and self.rts is False
                assert self.options['timeout'] > 0 and self.options['write_timeout'] > 0
                self.is_open = True
            def write(self,payload):
                """! @brief 정상 nonce를 반사하며 partial write 오류를 구분합니다. """
                if fail_write:
                    raise OSError('fixture write failure')
                self.buffer = b'NUCODE_M6_ECHO:'+payload if reply else b''
                return len(payload)
            def read(self,size):
                """! @brief 최대 요청 byte 수만 반환합니다. """
                result,self.buffer = self.buffer[:size],self.buffer[size:]
                return result
            def close(self):
                """! @brief 실패 경로에서도 close를 관측합니다. """
                self.is_open = False
        return Connection

    def test_ambiguous_and_invalid_identity_never_fall_back(self):
        """! @brief 다중 port·잘못된 hash는 자동 첫 장치 선택을 금지합니다. """
        for ports,digest in (([self.port,self.port],self.digest),([self.port],'raw-uid'),([],self.digest)):
            with self.subTest(digest=digest),self.assertRaises(BUILDER.AdapterError):
                M.select_serial(ports,digest)

    def test_path_disambiguates_only_the_same_serial(self):
        """! @brief path와 serial이 서로 다른 장치를 가리키면 거부합니다. """
        self.assertIs(M.select_serial([self.port],self.digest,M.identity_hash(self.port.device)),self.port)
        with self.assertRaises(BUILDER.AdapterError):
            M.select_serial([self.port],'0'*64,M.identity_hash(self.port.device))

    def test_fresh_nonce_echo_and_reenumeration_reopen_twice(self):
        """! @brief 두 cycle 사이 port 이름이 바뀌어도 exact serial을 재열거합니다. """
        ports = iter([[self.port],[SimpleNamespace(device='changed-port',serial_number='fixture-serial')]])
        result = M.serial_echo(self.digest,None,1,ports=lambda:next(ports),factory=self.factory())
        self.assertEqual(result['status'],'PASS')
        self.assertEqual(len(result['rounds']),6)
        self.assertEqual(len(set(row['nonce_sha256'] for row in result['rounds'])),6)
        self.assertTrue(all(not item.is_open for item in self.instances))
        self.assertEqual(self.instances[1].port,'changed-port')
        self.assertEqual(result['physical_USB_replug'],'NOT_RUN')

    def test_timeout_and_write_error_close_port_without_pass(self):
        """! @brief 잘못된 echo와 쓰기 오류는 close 후 실패로 남습니다. """
        for options,error in ((dict(reply=False),BUILDER.AdapterError),(dict(fail_write=True),OSError)):
            with self.subTest(options=options),self.assertRaises(error):
                M.serial_echo(self.digest,None,0.01,ports=lambda:[self.port],factory=self.factory(**options))
            self.assertTrue(all(not item.is_open for item in self.instances))

    def test_nus_pair_requires_both_directions_and_closes_both_ports(self):
        """! @brief 두 연결을 교차한 peer 모델에서 실제 write/read 경계와 양방향 nonce를 검사합니다. """
        instances = {}
        class Connection:
            """! @brief 보낸 byte는 자기 port가 아닌 상대 port에만 도착합니다. """
            def __init__(self,**kwargs):
                """! @brief 열기 전의 독립 buffer입니다. """
                self.buffer = b''
                self.is_open = False
            def open(self):
                """! @brief 식별된 port만 연결합니다. """
                instances[self.port] = self
                self.is_open = True
            def write(self,payload):
                """! @brief 수신자는 다른 port뿐입니다. """
                peer = instances['pair-b' if self.port=='pair-a' else 'pair-a']
                peer.buffer += payload
                return len(payload)
            def read(self,size):
                """! @brief 상대 write에서 받은 원형만 반환합니다. """
                value,self.buffer = self.buffer[:size],self.buffer[size:]
                return value
            def close(self):
                """! @brief 양쪽 close를 관측합니다. """
                self.is_open = False
        ports = [SimpleNamespace(device='pair-a',serial_number='serial-a'),SimpleNamespace(device='pair-b',serial_number='serial-b')]
        result = M.serial_pair(dict(serial_sha256=M.identity_hash('serial-a')),
            dict(serial_sha256=M.identity_hash('serial-b')),ports=lambda:ports,factory=Connection)
        self.assertEqual([(row['sender'],row['receiver']) for row in result['directions']],[(0,1),(1,0)])
        self.assertTrue(all(not item.is_open for item in instances.values()))
        self.assertNotEqual(result['directions'][0]['nonce_sha256'],result['directions'][1]['nonce_sha256'])


class HostDebugCleanupTests(unittest.TestCase):
    """! @brief 가상 target의 실제 제어 흐름으로 ELF 불일치 때 resume를 확인합니다. """
    def test_resume_and_close_are_required_even_on_image_mismatch(self):
        """! @brief firmware를 쓰거나 reset하지 않고 halt 실패 뒤에도 복귀합니다. """
        states = SimpleNamespace(HALTED='halted',RUNNING='running',SLEEPING='sleeping')
        for mismatch,sleeping in ((False,False),(True,False),(False,True)):
            events = []
            elf = SimpleNamespace(symbol_decoder=SimpleNamespace(
                get_symbol_for_address=lambda pc:SimpleNamespace(name='fixture_function')),
                read=lambda pc,size:b'\x12\x34')
            class Target:
                """! @brief 명령 byte 읽기와 halt/resume 순서만 제공합니다. """
                state = states.RUNNING
                @property
                def elf(self):
                    """! @brief 지정한 ELF의 decoder를 제공합니다. """
                    return elf
                @elf.setter
                def elf(self,value):
                    """! @brief ELF 설정을 실제 제어 순서에 기록합니다. """
                    events.append('elf')
                def halt(self):
                    """! @brief reset 없이 halt합니다. """
                    events.append('halt')
                    self.state = states.HALTED
                def get_state(self):
                    """! @brief 관측 state만 반환합니다. """
                    return self.state
                def read_core_register(self,name):
                    """! @brief ELF에 존재하는 PC를 반환합니다. """
                    return 0x1001
                def read_memory_block8(self,pc,size):
                    """! @brief mismatch case는 다른 실제 byte로 취급합니다. """
                    return b'\x00\x00' if mismatch else b'\x12\x34'
                def resume(self):
                    """! @brief 성공·실패 모두 실행 상태로 복귀합니다. """
                    events.append('resume')
                    self.state = states.SLEEPING if sleeping else states.RUNNING
            class Session:
                """! @brief close 없이 성공하면 시험을 통과할 수 없습니다. """
                target = Target()
                probe = SimpleNamespace()
                def __enter__(self):
                    """! @brief 선택한 probe만 엽니다. """
                    events.append('open')
                    return self
                def __exit__(self,*args):
                    """! @brief 예외에도 probe를 닫습니다. """
                    events.append('close')
            fake = {'pyocd':SimpleNamespace(),'pyocd.core':SimpleNamespace(),
                'pyocd.core.helpers':SimpleNamespace(ConnectHelper=SimpleNamespace(
                    session_with_chosen_probe=lambda **kwargs:Session())),
                'pyocd.core.target':SimpleNamespace(Target=SimpleNamespace(State=states))}
            with self.subTest(mismatch=mismatch),tempfile.TemporaryDirectory() as temporary:
                path = Path(temporary)/'fixture.elf'
                path.write_bytes(b'ELF-FIXTURE')
                with mock.patch.dict(sys.modules,fake),mock.patch.object(M,'discover_pyocd_probe_ids',return_value=['fixture-probe']):
                    if mismatch:
                        with self.assertRaisesRegex(BUILDER.AdapterError,'E_HOST_DEBUG_IMAGE'):
                            M.debug_elf(M.identity_hash('fixture-probe'),path)
                    else:
                        result = M.debug_elf(M.identity_hash('fixture-probe'),path)
                        self.assertTrue(result['resumed'] and result['probe_closed'])
                self.assertEqual(events,['open','elf','halt','resume','close'])


class HostWorkerLaunchTests(unittest.TestCase):
    """! @brief 실제 tool 환경 계약으로 부모 실행 경로를 검사하며 물리 PASS로 세지 않습니다. """
    def fixture(self,root):
        """! @brief 환경 객체에 없는 python key를 추가하지 않는 SDK 실행 fixture입니다. """
        platform = root/'platform'
        build = root/'build'
        build.mkdir()
        manifest = build/'Fixture.nu54-build.json'
        manifest.write_text('{}',encoding='utf-8')
        elf = build/'Fixture.elf'
        elf.write_bytes(b'ELF-FIXTURE')
        args = SimpleNamespace(operation='blink',output_root=root/'result',platform_root=platform,
            build_path=build,sketch_root=platform/'libraries/NUCODE_BLE/examples/NUSPeripheral',
            fqbn='fixture:fqbn',board='fixture-board',project_name='Fixture',manifest=manifest,
            profile='ble',probe_sha256=M.identity_hash('fixture-probe'),serial_sha256='1'*64,
            path_sha256=None,timeout_seconds=1,allow_jlink_backend=True)
        tools = dict(toolchain_root=root/'fixed-sdk/toolchain',ncs_root=root/'fixed-sdk/ncs',
            environment={'SDK_ENV':'FIXED','PATH':'fixed-sdk-bin'})
        context = dict(fixture_name='primary')
        inputs = dict(manifest_path=manifest,elf=elf,zephyr_build=build/'zephyr',elf_sha256='e'*64,hex_sha256='f'*64,
            manifest=dict(context=context,sysbuild=False,cache=dict(input_manifest=dict(
                adapter=dict(embedded_core_revision='fixture-same-source')))))
        return args,tools,context,inputs,root/'fixed-sdk/toolchain/python.exe'

    @contextlib.contextmanager
    def parent_environment(self,args,tools,contexts,inputs,sdk_python,run):
        """! @brief 대상·캐시 검증은 독립 fixture로 두고 SDK worker 실행 계약만 관측합니다. """
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(M,'tool_environment',return_value=tools))
            resolver = stack.enter_context(mock.patch.object(M,'resolve_toolchain_executable',return_value=sdk_python))
            stack.enter_context(mock.patch.object(M,'load_context',side_effect=lambda item,**kwargs:contexts[id(item)]))
            stack.enter_context(mock.patch.object(M,'paths_from_context',side_effect=lambda paths,context:
                dict(workspace=args.output_root.parent/('cache-'+context['fixture_name']))))
            for name in ('build_lock','probe_lock'):
                stack.enter_context(mock.patch.object(M,name,side_effect=lambda *values,**kwargs:contextlib.nullcontext()))
            stack.enter_context(mock.patch.object(M,'validate_flash_tool_identity'))
            stack.enter_context(mock.patch.object(M,'validate_runner_configuration'))
            validator = stack.enter_context(mock.patch.object(M,'validate_flash_manifest',side_effect=lambda item:inputs[id(item)]))
            stack.enter_context(mock.patch.object(M,'discover_pyocd_probe_ids',return_value=['fixture-probe','fixture-peer']))
            runner = stack.enter_context(mock.patch.object(M,'run_owned',side_effect=run))
            yield resolver,validator,runner

    def result_runner(self,calls,fail_operation=None):
        """! @brief 새 worker 원형을 생성하며 실제 child나 probe는 실행하지 않습니다. """
        def run(command,**kwargs):
            """! @brief 성공과 실패·복귀를 구분해 부모의 실제 분기를 실행합니다. """
            calls.append((command,kwargs))
            operation = next(value for value in command if str(value) in ('_blink','_debug','_serial','_pair','_resume'))
            failed = operation == fail_operation
            path = Path(command[command.index('--result')+1])
            path.write_text(json.dumps(dict(status='FAIL' if failed else 'PASS',fixture_only=True)),encoding='utf-8')
            return SimpleNamespace(returncode=1 if failed else 0,stdout=b'FIXTURE_WORKER',
                cleanup=dict(active_processes_after=0))
        return run

    def test_single_worker_uses_fixed_sdk_python_without_invented_environment_key(self):
        """! @brief blink·debug·serial 부모 경로가 시스템 Python으로 대체되지 않습니다. """
        for operation in ('blink','debug','serial'):
            with self.subTest(operation=operation),tempfile.TemporaryDirectory() as temporary:
                args,tools,context,inputs,sdk = self.fixture(Path(temporary))
                args.operation = operation
                calls = []
                self.assertNotIn('python',tools)
                with self.parent_environment(args,tools,{id(args):context},{id(args):inputs},sdk,
                        self.result_runner(calls)) as (resolver,validator,runner):
                    M.physical_check(args)
                    resolver.assert_called_once_with(tools['toolchain_root'],'python')
                self.assertEqual(len(calls),1)
                self.assertEqual(calls[0][0][0],sdk)
                self.assertIn('_'+operation,calls[0][0])
                self.assertEqual(calls[0][1]['environment']['SDK_ENV'],'FIXED')
                self.assertEqual(calls[0][1]['environment']['NUCODE_SELECTED_PROBE_SHA256'],args.probe_sha256)
                result = json.loads((args.output_root/'result.json').read_text(encoding='utf-8'))
                self.assertEqual(result['host_python'],str(sdk))
                self.assertFalse(result['physical_recovery_pending'])

    def test_pre_worker_failure_does_not_report_target_recovery_pending(self):
        """! @brief 장치 worker 시작 전 manifest 오류는 보드를 halt했다고 기록하지 않습니다. """
        with tempfile.TemporaryDirectory() as temporary:
            args,tools,context,inputs,sdk = self.fixture(Path(temporary))
            with self.parent_environment(args,tools,{id(args):context},{id(args):inputs},sdk,
                    self.result_runner([])) as (resolver,validator,runner):
                validator.side_effect = BUILDER.AdapterError('fixture invalid manifest')
                with self.assertRaisesRegex(BUILDER.AdapterError,'invalid manifest'):
                    M.physical_check(args)
                runner.assert_not_called()
            result = json.loads((args.output_root/'result.json').read_text(encoding='utf-8'))
            self.assertEqual(result['status'],'FAIL')
            self.assertFalse(result['physical_recovery_pending'])

    def test_failed_debug_and_recovery_both_use_same_sdk_python(self):
        """! @brief 실제 worker 실패 뒤 복귀도 고정 SDK Python으로 수행하고 FAIL은 유지합니다. """
        with tempfile.TemporaryDirectory() as temporary:
            args,tools,context,inputs,sdk = self.fixture(Path(temporary))
            args.operation = 'debug'
            calls = []
            with self.parent_environment(args,tools,{id(args):context},{id(args):inputs},sdk,
                    self.result_runner(calls,fail_operation='_debug')):
                with self.assertRaisesRegex(BUILDER.AdapterError,'E_HOST_WORKER'):
                    M.physical_check(args)
            self.assertEqual(len(calls),2)
            self.assertTrue(all(command[0]==sdk for command,kwargs in calls))
            self.assertIn('_resume',calls[1][0])
            result = json.loads((args.output_root/'result.json').read_text(encoding='utf-8'))
            self.assertEqual(result['status'],'FAIL')
            self.assertEqual(result['recovery_resume_exit'],0)
            self.assertFalse(result['physical_recovery_pending'])

    def test_pair_worker_uses_fixed_sdk_python_with_real_environment_shape(self):
        """! @brief 두 NUS manifest의 부모 경로도 동일한 SDK locator를 사용합니다. """
        with tempfile.TemporaryDirectory() as temporary:
            args,tools,context,inputs,sdk = self.fixture(Path(temporary))
            peer = SimpleNamespace(**vars(args))
            peer.build_path = Path(temporary)/'peer-build'
            peer.sketch_root = args.platform_root/'libraries/NUCODE_BLE/examples/NUSCentral'
            peer_context = dict(fixture_name='peer')
            peer_inputs = dict(inputs,manifest=dict(inputs['manifest'],context=peer_context))
            args.peer_manifest = Path(temporary)/'peer.nu54-build.json'
            args.peer_probe_sha256 = M.identity_hash('fixture-peer')
            args.peer_serial_sha256 = '2'*64
            args.peer_path_sha256 = None
            calls = []
            with mock.patch.object(M,'manifest_namespace',return_value=peer),self.parent_environment(
                    args,tools,{id(args):context,id(peer):peer_context},
                    {id(args):inputs,id(peer):peer_inputs},sdk,self.result_runner(calls)) as (resolver,validator,runner):
                M.physical_pair(args)
                resolver.assert_called_once_with(tools['toolchain_root'],'python')
            self.assertEqual(len(calls),1)
            self.assertEqual(calls[0][0][0],sdk)
            self.assertIn('_pair',calls[0][0])
            self.assertEqual(calls[0][1]['environment'],tools['environment'])


if __name__ == '__main__':
    unittest.main()
