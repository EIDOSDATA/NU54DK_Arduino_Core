"""! @brief 고정 pyOCD의 선택한 probe만 firmware 갱신·GUI 없이 열도록 제한합니다. """
import ctypes
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re

PREOPEN_COMMANDS = ("DisableAutoUpdateFW", "SuppressGUI = 1")
POSTOPEN_COMMANDS = ("SetRestartOnClose = 0", "SetSkipDebugDeInit = 1")


def canonical_serial(raw):
    """! @brief 원시 decimal serial의 완전한 값만 허용합니다. """
    if not isinstance(raw,str) or not raw.isascii() or not raw.isdecimal() or not 1 <= len(raw) <= 12 or not 1 <= int(raw) <= 0xFFFFFFFF:
        raise ValueError("[NU54:E_PROBE_BACKEND] 완전한 decimal serial이 필요합니다.")
    return str(int(raw))


def probe_digest(raw):
    """! @brief 선택한 probe의 비식별 identity를 계산합니다. """
    return hashlib.sha256(canonical_serial(raw).encode("ascii")).hexdigest()


def build_safe_link(pylink,events):
    """! @brief 기존 검토된 pre-open 순서와 실패 정리의 공통 부분을 재사용합니다. """
    class SafeLink(pylink.JLink):
        """! @brief 자동 FW 갱신·재시도 없이 선택한 프로브를 한 번 엽니다. """
        def disable_dialog_boxes(self):
            """! @brief SilentUpdateFW를 포함하는 기본 편의 함수를 호출하지 않습니다. """
            raise RuntimeError('[NU54:E_PROBE_FIRMWARE_POLICY] SilentUpdateFW 경로는 허용하지 않습니다.')
        def command_checked(self, command):
            """! @brief 허용된 설정 명령의 반환값과 원형 오류를 보존합니다. """
            if command not in PREOPEN_COMMANDS + POSTOPEN_COMMANDS:
                raise ValueError('Unreviewed command refused')
            event = {'operation': 'command', 'command': command, 'status': 'PENDING'}
            events.append(event)
            warning_count = getattr(self, '_observer_warning_count', [0])[0]
            try:
                value = self.exec_command(command)
                event['return_code'] = value
                event['native_error_checked'] = self._open_refcount == 1
                event['native_error'] = self.error if event['native_error_checked'] else None
                if type(value) is not int or value < 0 or event['native_error'] is not None or getattr(self, '_observer_warning_count', [0])[0] != warning_count:
                    raise RuntimeError('J-Link configuration command rejected')
                event['status'] = 'RETURNED'
            except BaseException as error:
                event.update(status='FAIL', error_type=type(error).__name__)
                raise

        def open(self, serial_no=None, ip_addr=None):
            """! @brief serial 선택·잠금·FW 금지 설정 뒤 OpenEx를 정확히 한 번 호출합니다. """
            if ip_addr is not None or serial_no is None or self._open_refcount != 0 or self._lock is not None:
                raise ValueError('Only one explicit unopened USB serial is allowed')
            if self.opened():
                raise ValueError('Native DLL already open')
            serial_no = int(canonical_serial(str(serial_no)))
            native_open_attempted = False
            self._native_close_attempted = False
            try:
                value = self._dll.JLINKARM_EMU_SelectByUSBSN(serial_no)
                events.append({'operation': 'select_usb', 'probe_sha256': probe_digest(str(serial_no)), 'return_code': value})
                if value < 0:
                    raise RuntimeError('Exact J-Link serial unavailable')
                self._lock = pylink.jlock.JLock(serial_no)
                if not self._lock.acquire():
                    raise RuntimeError('J-Link library lock occupied')
                for command in PREOPEN_COMMANDS:
                    self.command_checked(command)
                events.append({'operation': 'OpenEx', 'status': 'ATTEMPTED'})
                open_warning_count = getattr(self, '_observer_warning_count', [0])[0]
                native_open_attempted = True
                pointer = self._dll.JLINKARM_OpenEx(self.log_handler, self.error_handler)
                failure = ctypes.cast(pointer, ctypes.c_char_p).value
                if failure is not None:
                    raise RuntimeError('J-Link OpenEx failed: ' + failure.decode(errors='replace'))
                self._open_refcount = 1
                events[-1]['status'] = 'RETURNED'
                if getattr(self, '_observer_warning_count', [0])[0] != open_warning_count:
                    raise RuntimeError('J-Link open emitted warning or error')
                if hasattr(self._dll, 'JLINK_SetHookUnsecureDialog'):
                    self.unsecure_hook = pylink.enums.JLinkFunctions.UNSECURE_HOOK_PROTOTYPE(self._unsecure_hook)
                    self._dll.JLINK_SetHookUnsecureDialog(self.unsecure_hook)
                for command in POSTOPEN_COMMANDS:
                    self.command_checked(command)
            except BaseException as primary_error:
                try:
                    if native_open_attempted:
                        event = {'operation': 'failed_open_close', 'status': 'ATTEMPTED'}
                        events.append(event)
                        try:
                            event['native_open_observed'] = bool(self.opened())
                            if event['native_open_observed']:
                                self._native_close_attempted = True
                                self._dll.JLINKARM_Close()
                                if self.opened():
                                    raise RuntimeError('Native DLL remains open after close')
                                event['status'] = 'RETURNED'
                            else:
                                event['status'] = 'NOT_OPEN_NO_NATIVE_CLOSE'
                        except BaseException as cleanup_error:
                            event.update(status='FAIL', error_type=type(cleanup_error).__name__)
                            primary_error.add_note('Failed-open close also failed: ' + type(cleanup_error).__name__)
                        finally:
                            self._open_refcount = 0
                finally:
                    if self._lock is not None:
                        try:
                            self._lock.release()
                            self._lock = None
                        except BaseException as cleanup_error:
                            events.append({'operation': 'lock_release', 'status': 'FAIL',
                                           'error_type': type(cleanup_error).__name__})
                            primary_error.add_note('Owned JLock release failed: ' + type(cleanup_error).__name__)
                raise

        def close(self):
            """! @brief native close 한 번과 소유 lock 해제를 직접 확인하고 실패를 삼키지 않습니다. """
            if self._open_refcount == 0:
                return None
            if self._open_refcount != 1 or getattr(self, '_native_close_attempted', False):
                raise RuntimeError('Repeated native close refused')
            event = {'operation': 'native_close', 'status': 'ATTEMPTED'}
            events.append(event)
            self._native_close_attempted = True
            self._coresight_configured = False
            try:
                self._dll.JLINKARM_Close()
                if self.opened():
                    raise RuntimeError('Native DLL remains open after close')
                event['status'] = 'RETURNED'
            except BaseException as error:
                event.update(status='FAIL', error_type=type(error).__name__)
                raise
            finally:
                self._open_refcount = 0
                if self._lock is not None:
                    self._lock.release()
                    self._lock = None
    return SafeLink


def guard_probe(probe, *, expected_sha256, allow_jlink_backend=False):
    """! @brief 명시한 identity와 실제 backend를 열기 전에 확인하고 J-Link만 제한합니다. """
    identity=str(probe.unique_id)
    if not re.fullmatch(r'[0-9a-f]{64}',expected_sha256 or '') or hashlib.sha256(identity.encode()).hexdigest()!=expected_sha256:
        raise ValueError('[NU54:E_PROBE_BACKEND] 실제 probe가 명시한 SHA-256과 다릅니다.')
    previous=getattr(probe,'_nu54_probe_guard',None)
    if previous is not None:
        if previous['probe_sha256']!=expected_sha256 or (previous['backend']=='J-Link-via-pyOCD' and not allow_jlink_backend):
            raise ValueError('[NU54:E_PROBE_BACKEND] 기존 보호 상태도 현재의 명시적 선택을 충족해야 합니다.')
        return previous
    backend=type(probe).__module__+'.'+type(probe).__name__
    if backend=='pyocd.probe.cmsis_dap_probe.CMSISDAPProbe':
        proof=dict(backend='CMSIS-DAP',probe_sha256=expected_sha256,firmware_update_commands_requested=0)
        probe._nu54_probe_guard=proof
        return proof
    if backend!='pyocd.probe.jlink_probe.JLinkProbe' or not allow_jlink_backend:
        raise ValueError('[NU54:E_PROBE_BACKEND] 기본 경로는 CMSIS-DAP입니다. J-Link backend는 exact identity와 명시적 선택이 필요합니다.')
    import pylink
    from pyocd.probe.jlink_probe import JLinkProbe
    if importlib.metadata.version('pyocd')!='0.42.0' or importlib.metadata.version('pylink-square')!='1.7.0':
        raise ValueError('[NU54:E_PROBE_BACKEND] 검토한 고정 SDK pyOCD/pylink version이 아닙니다.')
    if probe._link.opened() or probe._link._open_refcount!=0 or probe._link._lock is not None:
        raise ValueError('[NU54:E_PROBE_BACKEND] 이미 열린 J-Link에는 보호 정책을 뒤늦게 적용하지 않습니다.')
    dll_path=Path(str(probe._link._dll._name))
    if not dll_path.is_absolute() or not dll_path.is_file():
        raise ValueError('[NU54:E_PROBE_BACKEND] 실제 로드한 J-Link library 경로를 확인하지 못했습니다.')
    with dll_path.open('rb') as stream:
        dll_sha256=hashlib.file_digest(stream,'sha256').hexdigest()
    events=[]
    warning_count=[0]
    def observe(message):
        """! @brief native 경고를 원시 UID 없이 검출하며 자동 수락하지 않습니다. """
        warning_count[0]+=1
    SafeLink=build_safe_link(pylink,events)
    link=SafeLink(lib=probe._link._library,unsecure_hook=lambda *_:pylink.enums.JLinkFlags.DLG_BUTTON_NO,
        warn=observe,error=observe)
    link._observer_warning_count=warning_count
    class SafeProbe(JLinkProbe):
        """! @brief SDK 전송을 유지하고 열림 상태·기본 GUI/FW 경로만 명시적으로 제한합니다. """
        @property
        def is_open(self):
            """! @brief pylink 메서드 객체 대신 실제 열린 bool을 반환합니다. """
            return bool(self._link.opened())
        def open(self):
            """! @brief 선택한 USB serial을1회 열고 부분 실패도 정리합니다. """
            if self.session.options.get('jlink.non_interactive') is not False:
                raise ValueError('[NU54:E_PROBE_FIRMWARE_POLICY] 기본 SilentUpdateFW 옵션은 거부합니다.')
            try:
                result=super().open()
                if self.Protocol.SWD not in self._supported_protocols or self._default_protocol!=self.Protocol.SWD:
                    raise ValueError('[NU54:E_PROBE_BACKEND] SWD가 필요하며 JTAG fallback을 하지 않습니다.')
                self._nu54_probe_guard['automatic_firmware_update']='DISABLED_BEFORE_OPEN'
                print('NU54_PROBE_OPEN_GUARDED='+json.dumps({key:value for key,value in self._nu54_probe_guard.items() if key!='events'},sort_keys=True),flush=True)
                return result
            except BaseException:
                if self.is_open and not getattr(self._link,'_native_close_attempted',False):
                    self.close()
                raise
        def connect(self,protocol=None):
            """! @brief 전력 제어·vendor 자동 target 선택 없이 SDK CoreSight SWD를 사용합니다. """
            if self.session.options.get('jlink.device') is not None or self.session.options.get('jlink.power') is not False:
                raise ValueError('[NU54:E_PROBE_BACKEND] 자동 target 선택·전력 제어를 허용하지 않습니다.')
            if protocol is None or protocol==self.Protocol.DEFAULT:
                protocol=self.Protocol.SWD
            if protocol!=self.Protocol.SWD:
                raise ValueError('[NU54:E_PROBE_BACKEND] SWD만 허용합니다.')
            return super().connect(protocol)
    probe.__class__=SafeProbe
    probe._link=link
    proof=dict(backend='J-Link-via-pyOCD',probe_sha256=expected_sha256,dll_sha256=dll_sha256,
        automatic_firmware_update='REQUIRED_BEFORE_OPEN_NOT_OPENED_YET',GUI='SUPPRESSED_WITHOUT_SILENT_UPDATE',
        unlock_recover='DENIED',SDK_files_modified=False,events=events)
    probe._nu54_probe_guard=proof
    return proof


def guard_session(session):
    """! @brief SDK의 공식 user-script 초기화 시점에 probe open보다 먼저 보호 정책을 적용합니다. """
    proof=guard_probe(session.probe,expected_sha256=os.environ.get('NUCODE_SELECTED_PROBE_SHA256'),
        allow_jlink_backend=os.environ.get('NUCODE_ALLOW_JLINK_BACKEND')=='1')
    if proof['backend']=='J-Link-via-pyOCD':
        session.options['jlink.non_interactive']=False
        session.options['jlink.device']=None
        session.options['jlink.power']=False
    return proof
