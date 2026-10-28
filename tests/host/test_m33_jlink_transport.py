"""! @brief 실제 DLL·프로브 없이 연결 순서와 실패 정리를 검증합니다. """
import ctypes
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import importlib
import os
import tempfile
import builtins
from contextlib import ExitStack

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools/bluetooth"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
import m33_jlink_transport as adapter


class FakeDLL:
    """! @brief native 함수 호출과 실제 opened 상태를 분리해 모사합니다. """
    def __init__(self):
        self.calls = []
        self.is_open = False
        self.open_fail = False
        self.close_fail = False
        self.open_callback = None

    def JLINKARM_EMU_SelectByUSBSN(self, serial):
        self.calls.append(('select', serial))
        return 0

    def JLINKARM_OpenEx(self, *_):
        self.calls.append(('open',))
        if self.open_callback is not None:
            self.open_callback()
        if self.open_fail:
            return ctypes.c_char_p(b'fake open failure')
        self.is_open = True
        return None

    def JLINKARM_Close(self):
        self.calls.append(('close',))
        if self.close_fail:
            raise RuntimeError('fake native close failure')
        self.is_open = False


class FakeLock:
    """! @brief 획득·반환과 충돌을 독립 검증합니다. """
    all = []
    available = True

    def __init__(self, serial):
        self.acquired = False
        self.released = False
        self.all.append(self)

    def acquire(self):
        self.acquired = self.available
        return self.acquired

    def release(self):
        self.released = self.acquired
        self.acquired = False


class FakeLink:
    """! @brief 설정 거부와 경고를 native open 이전에 주입합니다. """
    def __init__(self, **kwargs):
        self._dll = getattr(kwargs.get('lib'), '_dll', None) or FakeDLL()
        self._open_refcount = 0
        self._lock = None
        self.log_handler = self.error_handler = None
        self._observer_warning_count = [0]
        self.bad_command = None
        self.warn_command = None
        self._unsecure_hook = kwargs.get('unsecure_hook')
        self.error = None
        self.return_values = {}
        self.error_reads = []
        self.preopen_only_error = False

    @property
    def error(self):
        self.error_reads.append(self._open_refcount)
        if self.preopen_only_error and self._open_refcount == 0:
            return -256
        return self._error_value

    @error.setter
    def error(self, value):
        self._error_value = value

    def exec_command(self, command):
        self._dll.calls.append(('command', command))
        if command == self.warn_command:
            self._observer_warning_count[0] += 1
        return -1 if command == self.bad_command else self.return_values.get(command, 0)

    def opened(self):
        return self._dll.is_open


class FakeProbe:
    """! @brief open 후 supported_tifs 단계 실패를 재현합니다. """
    Protocol = SimpleNamespace(DEFAULT=0, SWD=1, JTAG=2)

    def open(self):
        self._link.open(1057707567)
        if getattr(self, 'late_failure', False):
            raise RuntimeError('supported_tifs failed')
        self._supported_protocols = [self.Protocol.JTAG] if getattr(self, 'jtag_only', False) else [self.Protocol.SWD]
        self._default_protocol = self._supported_protocols[0]

    def close(self):
        self._link.close()

    def connect(self, protocol=None):
        return 'connected'


class AdapterTests(unittest.TestCase):
    """! @brief 실행 안전 조건이 실제 호출 순서와 예외에서 유지되는지 검사합니다. """
    def setUp(self):
        FakeLock.all = []
        FakeLock.available = True
        self.events = []
        fake = SimpleNamespace(JLink=FakeLink, jlock=SimpleNamespace(JLock=FakeLock),
                               library=SimpleNamespace(Library=lambda **_: None),
                               enums=SimpleNamespace(JLinkFlags=SimpleNamespace(DLG_BUTTON_NO=2)))
        self.Link, self.Probe = adapter.build_types(fake, FakeProbe, self.events, {
            'path': 'D:/w06/synthetic-test-only.dll',
            'sha256': hashlib.sha256(b'fake DLL').hexdigest()})

    def test_exact_open_order_and_no_fw_update(self):
        link = self.Link()
        link.open(1057707567)
        self.assertEqual(link._dll.calls, [('select', 1057707567),
            ('command', 'DisableAutoUpdateFW'), ('command', 'SuppressGUI = 1'), ('open',),
            ('command', 'SetRestartOnClose = 0'), ('command', 'SetSkipDebugDeInit = 1')])
        link.close()
        self.assertFalse(link.opened())
        self.assertTrue(FakeLock.all[0].released)
        link.close()
        self.assertEqual(link._dll.calls.count(('close',)), 1)

    def test_inhibit_rejection_never_opens(self):
        link = self.Link()
        link.bad_command = 'DisableAutoUpdateFW'
        with self.assertRaises(RuntimeError):
            link.open(1057707567)
        self.assertNotIn(('open',), link._dll.calls)
        self.assertTrue(FakeLock.all[0].released)

    def test_positive_command_data_is_not_generic_failure(self):
        link = self.Link()
        link.return_values['SetRestartOnClose = 0'] = 1
        link.open(1057707567)
        self.assertTrue(link.opened())
        self.assertTrue(any(row.get('command') == 'SetRestartOnClose = 0' and row['return_code'] == 1
                            and row['native_error'] is None and row['status'] == 'RETURNED' for row in self.events))
        link.close()

    def test_native_error_stops_after_open_before_target(self):
        link = self.Link()
        link.error = 1
        with self.assertRaises(RuntimeError):
            link.open(1057707567)
        self.assertIn(('open',), link._dll.calls)
        self.assertFalse(link.opened())
        self.assertEqual(link.error_reads, [1])

    def test_preopen_haserror_not_queried(self):
        link = self.Link()
        link.preopen_only_error = True
        link.open(1057707567)
        self.assertEqual(link.error_reads, [1, 1])
        link.close()

    def test_command_allowlist_cannot_enable_firmware_update(self):
        link = self.Link()
        with self.assertRaises(ValueError):
            link.command_checked('SilentUpdateFW')
        self.assertEqual(link._dll.calls, [])

    def test_unsecure_hook_explicit_no(self):
        with patch.object(adapter, 'load_pinned_library',
                          return_value=SimpleNamespace(_dll=FakeDLL())):
            link = self.Probe._get_jlink()
        self.assertEqual(link._unsecure_hook(), 2)

    def test_bad_dll_pin_rejected_before_load(self):
        fake_path = SimpleNamespace(read_bytes=lambda: b'changed DLL')
        with patch.object(adapter, 'Path', return_value=fake_path):
            with self.assertRaisesRegex(ValueError, 'DLL changed'):
                self.Probe._get_jlink()
    def test_no_effect_warning_never_opens(self):
        link = self.Link()
        link.warn_command = 'DisableAutoUpdateFW'
        with self.assertRaises(RuntimeError):
            link.open(1057707567)
        self.assertNotIn(('open',), link._dll.calls)

    def test_postopen_rejection_closes_once(self):
        link = self.Link()
        link.bad_command = 'SetRestartOnClose = 0'
        with self.assertRaises(RuntimeError):
            link.open(1057707567)
        self.assertEqual(link._dll.calls.count(('close',)), 1)
        self.assertFalse(link.opened())
        self.assertTrue(FakeLock.all[0].released)

    def test_failed_open_without_native_open_not_closed(self):
        link = self.Link()
        link._dll.open_fail = True
        with self.assertRaises(RuntimeError):
            link.open(1057707567)
        self.assertNotIn(('close',), link._dll.calls)
        self.assertTrue(FakeLock.all[0].released)

    def test_close_failure_preserved_and_lock_released(self):
        link = self.Link()
        link.open(1057707567)
        link._dll.close_fail = True
        with self.assertRaises(RuntimeError):
            link.close()
        self.assertTrue(link.opened())
        self.assertTrue(FakeLock.all[0].released)
        link.close()
        self.assertEqual(link._dll.calls.count(('close',)), 1)

    def test_partial_probe_open_cleanup(self):
        probe = self.Probe()
        probe._link = self.Link()
        probe.session = SimpleNamespace(options={'jlink.non_interactive': False})
        probe.late_failure = True
        with self.assertRaisesRegex(RuntimeError, 'supported_tifs'):
            probe.open()
        self.assertFalse(probe.is_open)
        self.assertEqual(probe._link._dll.calls.count(('close',)), 1)

    def test_real_bool_state(self):
        probe = self.Probe()
        probe._link = self.Link()
        self.assertIs(probe.is_open, False)
        probe._link.open(1057707567)
        self.assertIs(probe.is_open, True)
        probe.close()
        self.assertIs(probe.is_open, False)

    def test_unsafe_options_rejected(self):
        probe = self.Probe()
        probe.session = SimpleNamespace(options={'jlink.non_interactive': True})
        with self.assertRaises(ValueError):
            probe.open()
        for options in ({'jlink.device': 'NRF54L15', 'jlink.power': False},
                        {'jlink.device': None, 'jlink.power': True}):
            probe.session = SimpleNamespace(options=options)
            with self.assertRaises(ValueError):
                probe.connect()

    def test_serial_normalization_and_invalid_inputs(self):
        self.assertEqual(adapter.canonical_serial('001057707567'), '1057707567')
        self.assertEqual(adapter.probe_digest('001057707567'), adapter.probe_digest('1057707567'))
        for value in ('', '0', ' 1057707567', '1057707567x', '4294967296', '１２３'):
            with self.assertRaises(ValueError):
                adapter.canonical_serial(value)

    def test_lock_conflict_no_open(self):
        link = self.Link()
        FakeLock.available = False
        with self.assertRaises(RuntimeError):
            link.open(1057707567)
        self.assertNotIn(('open',), link._dll.calls)

    def test_reused_link_rejected(self):
        link = self.Link()
        link.open(1057707567)
        with self.assertRaises(ValueError):
            link.open(1057707567)
        self.assertEqual(link._dll.calls.count(('open',)), 1)
        link.close()

    def test_native_open_with_zero_refcount_rejected(self):
        link = self.Link()
        link._dll.is_open = True
        with self.assertRaises(ValueError):
            link.open(1057707567)
        self.assertEqual(link._dll.calls, [])

    def test_open_warning_fails_before_target_and_closes(self):
        link = self.Link()
        link._dll.open_callback = lambda: link._observer_warning_count.__setitem__(0, 1)
        with self.assertRaisesRegex(RuntimeError, 'open emitted'):
            link.open(1057707567)
        self.assertFalse(link.opened())
        self.assertTrue(FakeLock.all[0].released)
        self.assertNotIn(('command', 'SetRestartOnClose = 0'), link._dll.calls)

    def test_jtag_only_probe_rejected_and_closed(self):
        probe = self.Probe()
        probe._link = self.Link()
        probe.session = SimpleNamespace(options={'jlink.non_interactive': False})
        probe.jtag_only = True
        with self.assertRaisesRegex(ValueError, 'SWD support'):
            probe.open()
        self.assertFalse(probe.is_open)

    def test_explicit_jtag_connect_rejected(self):
        probe = self.Probe()
        probe.session = SimpleNamespace(options={'jlink.device': None, 'jlink.power': False})
        with self.assertRaises(ValueError):
            probe.connect(probe.Protocol.JTAG)
        self.assertEqual(probe.connect(), 'connected')


class LibraryAndCloseTests(unittest.TestCase):
    """! @brief 실제 DLL 대신 독립 가짜 library와 원형 checked_close를 검증합니다. """

    def setUp(self):
        """! @brief D에 합성 payload만 만들며 native loader를 대역으로 주입합니다. """
        self.temporary = tempfile.TemporaryDirectory(prefix='m33-jlink-pure-', dir='D:/w06/tmp')
        self.folder = Path(self.temporary.name).resolve()
        self.assertTrue(self.folder.is_relative_to(Path('D:/w06').resolve()))
        self.payload = b'fake DLL bytes; not executable'
        self.original = self.folder / 'original-synthetic.dll'
        self.original.write_bytes(self.payload)
        self.dll = {'path': str(self.original), 'sha256': hashlib.sha256(self.payload).hexdigest()}
        self.libraries = []

        def library(**kwargs):
            value = SimpleNamespace(_dll=FakeDLL(), path=Path(kwargs['dllpath']))
            self.assertFalse(kwargs['use_tmpcpy'])
            self.libraries.append(value)
            return value

        self.fake = SimpleNamespace(JLink=FakeLink, jlock=SimpleNamespace(JLock=FakeLock),
                                    library=SimpleNamespace(Library=library),
                                    enums=SimpleNamespace(JLinkFlags=SimpleNamespace(DLG_BUTTON_NO=2)))
        self.temp_patch = patch.object(adapter.tempfile, 'gettempdir', return_value=str(self.folder))
        self.space_patch = patch.object(adapter.shutil, 'disk_usage', return_value=SimpleNamespace(free=8 * 1024 ** 3))
        self.temp_patch.start()
        self.space_patch.start()
        FakeLock.all = []
        FakeLock.available = True

    def tearDown(self):
        """! @brief native가 없는 검증된 시험 폴더만 정리합니다. """
        self.temp_patch.stop()
        self.space_patch.stop()
        self.temporary.cleanup()

    def test_two_independent_DLL_copies_and_sessions(self):
        events = []
        _link, probe = adapter.build_types(self.fake, FakeProbe, events, self.dll)
        first, second = probe._get_jlink(), probe._get_jlink()
        self.assertEqual(len(self.libraries), 2)
        first_path, second_path = [library.path for library in self.libraries]
        self.assertNotEqual(first_path, second_path)
        for path in (first_path, second_path):
            self.assertNotEqual(path, self.original)
            self.assertTrue(path.resolve().is_relative_to(self.folder))
            self.assertEqual(path.read_bytes(), self.payload)
        self.assertIsNot(first._dll, second._dll)
        first.open(1057707567)
        second.open(1057715090)
        first.close()
        self.assertFalse(first.opened())
        self.assertTrue(second.opened())
        self.assertNotIn(('close',), second._dll.calls)
        second.close()
        self.assertEqual(first._dll.calls.count(('close',)), 1)
        self.assertEqual(second._dll.calls.count(('close',)), 1)

    def test_original_pin_checked_before_any_Library_call(self):
        invalid = dict(self.dll, sha256='0' * 64)
        with patch.object(self.fake.library, 'Library') as native:
            with self.assertRaisesRegex(ValueError, 'DLL changed'):
                adapter.load_pinned_library(self.fake, invalid)
            native.assert_not_called()
        self.assertEqual(list(self.folder.glob('w06-jlink-*.dll')), [])

    def test_library_failure_removes_only_new_copy(self):
        attempted = []

        def failure(**kwargs):
            attempted.append(Path(kwargs['dllpath']))
            raise RuntimeError('synthetic library load failure')

        with patch.object(self.fake.library, 'Library', side_effect=failure):
            with self.assertRaisesRegex(RuntimeError, 'synthetic library'):
                adapter.load_pinned_library(self.fake, self.dll)
        self.assertEqual(len(attempted), 1)
        self.assertFalse(attempted[0].exists())
        self.assertEqual(self.original.read_bytes(), self.payload)

    def test_wrong_temp_root_rejected_before_Library(self):
        with patch.object(adapter.tempfile, 'gettempdir', return_value='C:/Windows/Temp'), \
                patch.object(self.fake.library, 'Library') as native:
            with self.assertRaises(ValueError):
                adapter.load_pinned_library(self.fake, self.dll)
            native.assert_not_called()

    def test_DLL_copy_cannot_cross_free_space_floor(self):
        free = 4 * 1024 ** 3 + len(self.payload) - 1
        with patch.object(adapter.shutil, 'disk_usage', return_value=SimpleNamespace(free=free)), \
                patch.object(self.fake.library, 'Library') as native:
            with self.assertRaisesRegex(ValueError, 'copy would cross'):
                adapter.load_pinned_library(self.fake, self.dll)
            native.assert_not_called()
        self.assertEqual(list(self.folder.glob('w06-jlink-*.dll')), [])

    def close_fixture(self, failing_operation=None):
        """! @brief 닫힌 상태까지 복귀해도 내부 예외를 삼키는 가짜 Session을 만듭니다. """
        probe = SimpleNamespace(is_open=True, wire_protocol='SWD')

        def operation(name):
            if name == 'disconnect':
                probe.wire_protocol = None
            if name == 'close':
                probe.is_open = False
            if name == failing_operation:
                raise RuntimeError('synthetic swallowed ' + name)

        probe.disconnect = lambda: operation('disconnect')
        probe.close = lambda: operation('close')
        session = SimpleNamespace(_trace_stop=lambda: operation('_trace_stop'),
                                  board=SimpleNamespace(uninit=lambda: operation('uninit')))

        def close():
            for function in (session._trace_stop, session.board.uninit, probe.disconnect, probe.close):
                try:
                    function()
                except RuntimeError:
                    pass

        session.close = close
        return session, probe

    def test_checked_close_detects_swallowed_errors_even_if_closed(self):
        for failed in ('_trace_stop', 'uninit', 'disconnect', 'close'):
            with self.subTest(operation=failed):
                session, probe = self.close_fixture(failed)
                originals = (session._trace_stop, session.board.uninit, probe.disconnect, probe.close)
                row = {}
                with self.assertRaisesRegex(RuntimeError, 'close incomplete'):
                    adapter.checked_close(session, probe, row)
                self.assertFalse(probe.is_open)
                self.assertIsNone(probe.wire_protocol)
                self.assertEqual(row['session_close']['status'], 'FAIL')
                self.assertTrue(any(value['operation'] == failed and value['status'] == 'FAIL'
                                    for value in row['session_close']['operations']))
                self.assertEqual(originals, (session._trace_stop, session.board.uninit,
                                             probe.disconnect, probe.close))

    def test_checked_close_success_records_original_operations(self):
        session, probe = self.close_fixture()
        row = {}
        adapter.checked_close(session, probe, row)
        self.assertEqual(row['session_close']['status'], 'PASS')
        self.assertEqual(row['session_close']['operations'], [
            {'operation': name, 'status': 'RETURNED'}
            for name in ('_trace_stop', 'uninit', 'disconnect', 'close')])


class PluginImportTests(unittest.TestCase):
    """! @brief 실제 pyOCD import 없이 scoped plugin 차단과 복원을 검증합니다. """

    def test_preimported_pyocd_refused(self):
        with patch.dict(sys.modules, {'pyocd': SimpleNamespace()}):
            with self.assertRaisesRegex(RuntimeError, 'Fresh process'):
                adapter.load_reviewed_pyocd([])

    def test_scoped_plugin_discovery_is_restored(self):
        original_import = builtins.__import__
        original_entries = unittest.mock.Mock(return_value=('other-plugin',))
        metadata = SimpleNamespace(entry_points=original_entries)
        plugin = SimpleNamespace(entry_points=original_entries)
        add_options = unittest.mock.Mock()
        expected = (type('JLinkProbe', (), {}), type('Session', (), {}), type('Target', (), {}))
        modules = {
            'importlib_metadata': metadata,
            'pyocd.probe.jlink_probe': SimpleNamespace(JLinkProbe=expected[0],
                JLinkProbePlugin=lambda: SimpleNamespace(options={'synthetic': True})),
            'pyocd.core.session': SimpleNamespace(Session=expected[1]),
            'pyocd.core.target': SimpleNamespace(Target=expected[2]),
            'pyocd.core.options': SimpleNamespace(add_option_set=add_options),
            'pyocd.probe.aggregator': SimpleNamespace(PROBE_CLASSES={}),
        }

        def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == 'pyocd.probe.jlink_probe':
                self.assertEqual(metadata.entry_points(group='pyocd.probe'), ())
                self.assertEqual(metadata.entry_points(group='unrelated'), ('other-plugin',))
            if name in modules:
                return modules[name]
            return original_import(name, globals, locals, fromlist, level)

        events = []
        with patch.dict(sys.modules, {'pyocd.core.plugin': plugin}):
            sys.modules.pop('pyocd', None)
            with patch.object(builtins, '__import__', side_effect=fake_import):
                self.assertEqual(adapter.load_reviewed_pyocd(events), expected)
        self.assertIs(metadata.entry_points, original_entries)
        self.assertIs(plugin.entry_points, original_entries)
        original_entries.assert_called_once_with(group='unrelated')
        add_options.assert_called_once_with({'synthetic': True})
        self.assertEqual(events, [{'operation': 'probe_plugin_discovery',
                                  'status': 'BLOCKED_EXPLICIT_ADAPTER_ONLY'}])


class BackendIntegrationTests(unittest.TestCase):
    """! @brief 원형 backend 흐름의 UID 결합·실패 종료·실제 sidecar를 native 없이 검증합니다. """

    def setUp(self):
        """! @brief DLL·pyOCD import와 target I/O를 모두 대역으로 제한합니다. """
        self.temporary = tempfile.TemporaryDirectory(prefix='m33-backend-pure-', dir='D:/w06/tmp')
        self.folder = Path(self.temporary.name).resolve()
        self.assertTrue(self.folder.is_relative_to(Path('D:/w06').resolve()))
        self.stack = ExitStack()
        self.addCleanup(self.temporary.cleanup)
        self.addCleanup(self.stack.close)
        self.descriptor = {'kind': 'jlink-swd', 'board': 'nrf54l15dk',
                           'fixture_sha256': 'a' * 64, 'dll_sha256': 'b' * 64}
        uid = hashlib.sha256((1).to_bytes(4, 'little') + (2).to_bytes(4, 'little')).hexdigest()
        self.fixture = {'fixture_sha256': 'a' * 64, 'dll': {'path': 'synthetic', 'sha256': 'b' * 64},
                        'boards': [{'serial': str(serial), 'port': 'COM' + str(index + 20),
                                    'probe_sha256': hashlib.sha256(str(serial).encode()).hexdigest(),
                                    'target_uid_sha256': uid}
                                   for index, serial in enumerate((1057707567, 1057715090, 1057783094))]}
        owner = self
        self.calls = []
        self.sessions = []

        class Probe:
            """! @brief 열린 상태와 최종 관측 오류를 독립적으로 제어합니다. """
            def __init__(self, serial):
                self.unique_id = serial
                self._is_open = False
                self.wire_protocol = None
                self._link = SimpleNamespace(_observer_warning_count=[0])
                self.closed_reads = 0
                self.close_called = False
                self.fail_final_observation = False

            @property
            def is_open(self):
                if self.close_called:
                    self.closed_reads += 1
                    if self.fail_final_observation and self.closed_reads > 1:
                        raise RuntimeError('synthetic final observation failure')
                return self._is_open

            def disconnect(self):
                owner.calls.append('disconnect')
                self.wire_protocol = None

            def close(self):
                owner.calls.append('close')
                self._is_open = False
                self.close_called = True

        class Session:
            """! @brief 설치 Session과 같은 삼킨 정리 예외 경로를 모사합니다. """
            def __init__(self, probe, auto_open, options):
                owner.assertFalse(auto_open)
                owner.assertFalse(options['jlink.non_interactive'])
                owner.assertFalse(options['jlink.power'])
                owner.assertIsNone(options['jlink.device'])
                self.probe = probe
                self.board = SimpleNamespace(init=lambda: owner.calls.append('init'),
                                             uninit=lambda: owner.calls.append('uninit'))
                values = {0x00FFC31C: 0x54B15, 0xE000ED00: 0x411FD210,
                          0x00FFC304: 1, 0x00FFC308: 2}
                self.target = SimpleNamespace(
                    dp=SimpleNamespace(connect=lambda: owner.calls.append('dp.connect')),
                    read32=lambda address: values[address])
                owner.sessions.append(self)

            def open(self, init_board):
                owner.assertFalse(init_board)
                self.probe._is_open = True
                self.probe.wire_protocol = 'SWD'
                self.probe.close_called = False
                self.probe.closed_reads = 0
                owner.calls.append('open')

            def _trace_stop(self):
                owner.calls.append('trace_stop')

            def close(self):
                for operation in (self._trace_stop, self.board.uninit,
                                  self.probe.disconnect, self.probe.close):
                    try:
                        operation()
                    except RuntimeError:
                        pass

        class Base:
            """! @brief 기본 backend 생성자는 호출되면 실패하도록 둡니다. """
            def __init__(self):
                raise AssertionError('Default discovery constructor must not run')

            def identity(self, session):
                return {'synthetic_debug_identity': True}

        self.Probe = Probe
        self.Session = Session
        self.Base = Base
        self.diagnostics = SimpleNamespace(SAFE_SESSION_OPTIONS={'auto_unlock': False},
                                            validate_debug_identity=unittest.mock.Mock())
        self.modules = {
            'pylink': SimpleNamespace(),
            'pyocd.flash.file_programmer': SimpleNamespace(FileProgrammer=object),
            'serial.tools': SimpleNamespace(list_ports=SimpleNamespace(comports=lambda: [])),
            'm33_diagnostics': self.diagnostics,
        }
        original_import = builtins.__import__

        def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name in self.modules:
                return self.modules[name]
            return original_import(name, globals, locals, fromlist, level)

        self.stack.enter_context(patch.object(builtins, '__import__', side_effect=fake_import))
        self.stack.enter_context(patch.dict(os.environ, {adapter.transport.AUDIT_ENV: str(self.folder)}))
        self.stack.enter_context(patch.object(adapter, '_BACKEND', None))
        self.stack.enter_context(patch.object(adapter.tempfile, 'gettempdir', return_value=str(self.folder)))
        self.stack.enter_context(patch.object(adapter.shutil, 'disk_usage',
                                             return_value=SimpleNamespace(free=8 * 1024 ** 3)))
        self.stack.enter_context(patch.object(adapter, 'load_reviewed_pyocd',
                                             return_value=(Probe, Session, object)))
        self.stack.enter_context(patch.object(adapter, 'build_types', return_value=(object, Probe)))
        self.stack.enter_context(patch.object(adapter.transport, 'load_fixture', return_value=self.fixture))
        self.stack.enter_context(patch.object(adapter.transport, 'descriptor', return_value=self.descriptor))
        self.stack.enter_context(patch.object(adapter.transport, 'resolve_endpoint', return_value={}))
        self.stack.enter_context(patch.object(adapter.transport, '_RECEIPTS', []))
        self.backend = adapter.get_backend(self.fixture, Base)

    def receipt(self):
        """! @brief 게시 pin을 실제 파일 byte와 대조하여 실패 증거 유실도 검사합니다. """
        pins = adapter.transport.session_receipts()
        self.assertEqual(len(pins), 1)
        pin = pins[0]
        payload = Path(pin['path']).read_bytes()
        self.assertEqual(hashlib.sha256(payload).hexdigest(), pin['sha256'])
        return pin, json.loads(payload)

    def test_initialized_session_publishes_verified_UID_and_transport(self):
        probes, _ports = self.backend.discover()
        self.assertEqual(len(probes), 3)
        with self.backend.session(probes[0]) as session:
            self.assertIs(session, self.sessions[0])
        pin, row = self.receipt()
        self.assertEqual(pin['status'], 'PASS')
        self.assertEqual(pin['target_uid_sha256'], self.fixture['boards'][0]['target_uid_sha256'])
        self.assertEqual(pin['transport'], self.descriptor)
        self.assertTrue(pin['initialized'])
        self.assertTrue(pin['cpu_identity_verified'])
        self.assertEqual(pin['session_close']['status'], 'PASS')
        self.assertTrue(row['probe_closed'])
        self.assertTrue(row['probe_disconnected'])
        self.assertEqual(self.calls.count('close'), 1)

    def test_body_failure_still_closes_and_publishes_FAIL(self):
        probe = self.Probe(self.fixture['boards'][0]['serial'])
        with self.assertRaisesRegex(ValueError, 'synthetic caller failure'):
            with self.backend.session(probe):
                raise ValueError('synthetic caller failure')
        pin, row = self.receipt()
        self.assertEqual(pin['status'], 'FAIL')
        self.assertEqual(row['error_type'], 'ValueError')
        self.assertEqual(pin['session_close']['status'], 'PASS')
        self.assertEqual(self.calls.count('close'), 1)

    def test_UID_mismatch_closes_without_verified_UID_pin(self):
        probe = self.Probe(self.fixture['boards'][0]['serial'])
        self.fixture['boards'][0]['target_uid_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'target identity mismatch'):
            with self.backend.session(probe):
                self.fail('Identity mismatch must not enter caller body')
        pin, _row = self.receipt()
        self.assertEqual(pin['status'], 'FAIL')
        self.assertFalse(pin['cpu_identity_verified'])
        self.assertNotIn('target_uid_sha256', pin)
        self.assertEqual(pin['session_close']['status'], 'PASS')

    def test_final_observation_failure_publishes_then_raises(self):
        probe = self.Probe(self.fixture['boards'][0]['serial'])
        probe.fail_final_observation = True
        with self.assertRaisesRegex(RuntimeError, 'final close observation failed'):
            with self.backend.session(probe):
                pass
        pin, row = self.receipt()
        self.assertEqual(pin['status'], 'FAIL')
        self.assertIsNone(row['probe_closed'])
        self.assertEqual(row['final_observation_errors'], [
            {'operation': 'probe_closed', 'error_type': 'RuntimeError'}])
        self.assertEqual(pin['session_close']['status'], 'PASS')


if __name__ == '__main__':
    unittest.main()
