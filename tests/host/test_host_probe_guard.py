"""! @brief 실제 native open 없이 firmware 금지 명령 순서와 실패 정리를 검증합니다. """
import ctypes
import hashlib
import importlib.util
from pathlib import Path
import sys
import tempfile
import runpy
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[2]
SPEC=importlib.util.spec_from_file_location("host_probe_guard_test",ROOT/"tools/nu54-builder/src/nu54_builder_impl/probe_guard.py")
M=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


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


class JLinkProbe:
    """! @brief SDK backend의 open·connect 경계를 장치 없이 모사합니다. """
    __module__ = 'pyocd.probe.jlink_probe'
    Protocol = SimpleNamespace(DEFAULT=0, SWD=1, JTAG=2)

    def open(self):
        self._link.open(int(self.unique_id))
        if getattr(self, 'late_failure', False):
            raise RuntimeError('supported_tifs failed')
        self._supported_protocols = [self.Protocol.SWD]
        self._default_protocol = self.Protocol.SWD

    def close(self):
        self._link.close()

    def connect(self, protocol=None):
        return protocol


class GuardTests(unittest.TestCase):
    """! @brief 자동 FW 갱신 차단과 부분 실패의 소유 자원 정리를 검증합니다. """
    def setUp(self):
        FakeLock.all = []
        FakeLock.available = True
        self.events = []
        self.pylink = SimpleNamespace(JLink=FakeLink, jlock=SimpleNamespace(JLock=FakeLock),
            enums=SimpleNamespace(JLinkFlags=SimpleNamespace(DLG_BUTTON_NO=2)))
        self.Link = M.build_safe_link(self.pylink, self.events)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dll_path = Path(self.temp.name)/'synthetic-only.dll'
        self.dll_path.write_bytes(b'not a native library')
        self.modules = mock.patch.dict(sys.modules, {'pylink':self.pylink,
            'pyocd.probe.jlink_probe':SimpleNamespace(JLinkProbe=JLinkProbe)})
        self.modules.start()
        self.addCleanup(self.modules.stop)
        versions = mock.patch.object(M.importlib.metadata, 'version',
            side_effect=lambda name:{'pyocd':'0.42.0','pylink-square':'1.7.0'}[name])
        versions.start()
        self.addCleanup(versions.stop)

    def probe(self):
        """! @brief native open이 불가능한 synthetic identity와 library를 만듭니다. """
        probe = JLinkProbe()
        probe.unique_id = '123456789'
        probe.session = SimpleNamespace(options={'jlink.non_interactive':False,
            'jlink.device':None,'jlink.power':False})
        probe._link = FakeLink()
        probe._link._dll._name = str(self.dll_path)
        probe._link._library = SimpleNamespace(_dll=probe._link._dll)
        return probe

    def guard(self, probe):
        """! @brief 선택한 synthetic probe에만 보호를 적용합니다. """
        return M.guard_probe(probe, expected_sha256=hashlib.sha256(probe.unique_id.encode()).hexdigest(),
            allow_jlink_backend=True)

    def test_preopen_order_and_single_close(self):
        link = self.Link()
        link.open(123456789)
        self.assertEqual(link._dll.calls, [('select',123456789),
            ('command','DisableAutoUpdateFW'),('command','SuppressGUI = 1'),('open',),
            ('command','SetRestartOnClose = 0'),('command','SetSkipDebugDeInit = 1')])
        link.close()
        link.close()
        self.assertEqual(link._dll.calls.count(('close',)),1)
        self.assertTrue(FakeLock.all[0].released)

    def test_disable_fw_rejection_never_opens(self):
        link = self.Link()
        link.bad_command = 'DisableAutoUpdateFW'
        with self.assertRaises(RuntimeError):
            link.open(123456789)
        self.assertNotIn(('open',),link._dll.calls)
        self.assertTrue(FakeLock.all[0].released)

    def test_disable_fw_warning_never_opens(self):
        link = self.Link()
        link.warn_command = 'DisableAutoUpdateFW'
        with self.assertRaises(RuntimeError):
            link.open(123456789)
        self.assertNotIn(('open',),link._dll.calls)

    def test_gui_rejection_never_opens(self):
        link = self.Link()
        link.bad_command = 'SuppressGUI = 1'
        with self.assertRaises(RuntimeError):
            link.open(123456789)
        self.assertNotIn(('open',),link._dll.calls)

    def test_native_error_only_read_after_open(self):
        link = self.Link()
        link.preopen_only_error = True
        link.open(123456789)
        self.assertEqual(link.error_reads,[1,1])
        link.close()

    def test_postopen_rejection_closes_and_releases(self):
        link = self.Link()
        link.bad_command = 'SetRestartOnClose = 0'
        with self.assertRaises(RuntimeError):
            link.open(123456789)
        self.assertFalse(link.opened())
        self.assertEqual(link._dll.calls.count(('close',)),1)
        self.assertTrue(FakeLock.all[0].released)

    def test_failed_native_open_releases_without_double_close(self):
        link = self.Link()
        link._dll.open_fail = True
        with self.assertRaises(RuntimeError):
            link.open(123456789)
        self.assertFalse(link.opened())
        self.assertNotIn(('close',),link._dll.calls)
        self.assertTrue(FakeLock.all[0].released)

    def test_close_failure_is_preserved_with_lock_released(self):
        link = self.Link()
        link.open(123456789)
        link._dll.close_fail = True
        with self.assertRaises(RuntimeError):
            link.close()
        self.assertTrue(FakeLock.all[0].released)
        link.close()
        self.assertEqual(link._dll.calls.count(('close',)),1)

    def test_silent_fw_helper_and_unreviewed_commands_refused(self):
        link = self.Link()
        with self.assertRaises(RuntimeError):
            link.disable_dialog_boxes()
        with self.assertRaises(ValueError):
            link.command_checked('SilentUpdateFW')
        self.assertEqual(link._dll.calls,[])

    def test_occupied_lock_never_opens(self):
        FakeLock.available = False
        link = self.Link()
        with self.assertRaises(RuntimeError):
            link.open(123456789)
        self.assertNotIn(('open',),link._dll.calls)

    def test_invalid_identity_never_selects_probe(self):
        for serial in ('','0','123x','１２３','4294967296'):
            with self.subTest(serial=serial),self.assertRaises(ValueError):
                self.Link().open(serial)
        self.assertEqual(self.events,[])

    def test_jlink_requires_explicit_opt_in(self):
        probe = self.probe()
        with self.assertRaises(ValueError):
            M.guard_probe(probe,expected_sha256=hashlib.sha256(probe.unique_id.encode()).hexdigest())
        self.assertEqual(probe._link._dll.calls,[])

    def test_wrong_hash_never_opens(self):
        probe = self.probe()
        with self.assertRaises(ValueError):
            M.guard_probe(probe,expected_sha256='0'*64,allow_jlink_backend=True)
        self.assertEqual(probe._link._dll.calls,[])

    def test_wrong_sdk_version_never_opens(self):
        probe = self.probe()
        with mock.patch.object(M.importlib.metadata,'version',return_value='other'),self.assertRaises(ValueError):
            self.guard(probe)
        self.assertEqual(probe._link._dll.calls,[])

    def test_default_cmsis_dap_keeps_backend_and_proof(self):
        cls = type('CMSISDAPProbe',(),{'__module__':'pyocd.probe.cmsis_dap_probe'})
        probe = cls()
        probe.unique_id = 'cmsis-dap-synthetic'
        proof = M.guard_probe(probe,expected_sha256=hashlib.sha256(probe.unique_id.encode()).hexdigest())
        self.assertEqual(proof['backend'],'CMSIS-DAP')
        self.assertIs(probe._nu54_probe_guard,proof)
        self.assertIs(type(probe),cls)

    def test_guarded_open_uses_safe_link_and_real_bool(self):
        probe = self.probe()
        proof = self.guard(probe)
        self.assertEqual(proof['automatic_firmware_update'],'REQUIRED_BEFORE_OPEN_NOT_OPENED_YET')
        self.assertEqual(probe._link._unsecure_hook(),2)
        self.assertIs(probe.is_open,False)
        probe.open()
        self.assertIs(probe.is_open,True)
        self.assertEqual(proof['automatic_firmware_update'],'DISABLED_BEFORE_OPEN')
        self.assertEqual(proof['dll_sha256'],hashlib.sha256(self.dll_path.read_bytes()).hexdigest())
        probe.close()
        self.assertIs(probe.is_open,False)

    def test_partial_sdk_open_failure_cleans_native(self):
        probe = self.probe()
        self.guard(probe)
        probe.late_failure = True
        with self.assertRaisesRegex(RuntimeError,'supported_tifs'):
            probe.open()
        self.assertFalse(probe.is_open)
        self.assertEqual(probe._link._dll.calls.count(('close',)),1)

    def test_default_silent_fw_option_refused_before_open(self):
        probe = self.probe()
        self.guard(probe)
        probe.session.options['jlink.non_interactive'] = True
        with self.assertRaises(ValueError):
            probe.open()
        self.assertEqual(probe._link._dll.calls,[])

    def test_target_power_and_jtag_options_refused(self):
        probe = self.probe()
        self.guard(probe)
        for changes in ({'jlink.power':True},{'jlink.device':'NRF54L15'}):
            with mock.patch.dict(probe.session.options,changes),self.assertRaises(ValueError):
                probe.connect()
        with self.assertRaises(ValueError):
            probe.connect(probe.Protocol.JTAG)
        self.assertEqual(probe._link._dll.calls,[])

    def test_existing_guard_still_requires_explicit_opt_in(self):
        probe = self.probe()
        self.guard(probe)
        with self.assertRaises(ValueError):
            M.guard_probe(probe,expected_sha256=hashlib.sha256(probe.unique_id.encode()).hexdigest())

    def test_installed_user_script_guards_before_any_open(self):
        probe = self.probe()
        probe.session.options['jlink.non_interactive'] = True
        with mock.patch.dict('os.environ',{'NUCODE_SELECTED_PROBE_SHA256':hashlib.sha256(probe.unique_id.encode()).hexdigest(),
                'NUCODE_ALLOW_JLINK_BACKEND':'1'}):
            runpy.run_path(str(ROOT/'tools/nu54-builder/src/nu54_pyocd_guard.py'),init_globals={'session':SimpleNamespace(
                probe=probe,options=probe.session.options)})
        self.assertFalse(probe.session.options['jlink.non_interactive'])
        self.assertFalse(probe.session.options['jlink.power'])
        self.assertEqual(probe._link._dll.calls,[])
        self.assertEqual(probe._nu54_probe_guard['automatic_firmware_update'],'REQUIRED_BEFORE_OPEN_NOT_OPENED_YET')


if __name__ == '__main__':
    unittest.main()
