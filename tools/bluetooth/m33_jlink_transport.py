"""! @file
@brief 원형 pyOCD 판정을 유지하며 J-Link 연결·종료만 명시적으로 제한합니다.
@note 설치 SDK·pyOCD·pylink 파일을 수정하지 않습니다. import만으로 DLL을 로드하지 않습니다.
"""
from contextlib import contextmanager, ExitStack
import ctypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import uuid

import m33_probe_transport as transport


_BACKEND = None
_BACKEND_LOCK = threading.RLock()
_SESSION_LOCK = threading.RLock()

PREOPEN_COMMANDS = ('DisableAutoUpdateFW', 'SuppressGUI = 1')
POSTOPEN_COMMANDS = ('SetRestartOnClose = 0', 'SetSkipDebugDeInit = 1')


def canonical_serial(raw):
    """! @brief 완전한 USB decimal serial만 허용하고 선행 0을 정규화합니다. """
    if not isinstance(raw, str) or not raw.isascii() or not raw.isdecimal() or not 1 <= len(raw) <= 12:
        raise ValueError('Invalid complete decimal serial')
    value = int(raw)
    if not 1 <= value <= 0xFFFFFFFF:
        raise ValueError('Serial out of range')
    return str(value)


def probe_digest(raw):
    """! @brief 모든 새 DK actor가 같은 decimal serial hash lock을 사용합니다. """
    return hashlib.sha256(canonical_serial(raw).encode('ascii')).hexdigest()


def build_types(pylink, probe_base, events, dll):
    """! @brief 의존성을 주입하여 DLL 없이 연결 순서·실패 정리를 시험할 수 있습니다. """
    class SafeLink(pylink.JLink):
        """! @brief 자동 FW 갱신·재시도 없이 선택한 프로브를 한 번 엽니다. """
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

    class SafeProbe(probe_base):
        """! @brief 원형 J-Link 전송을 재사용하고 실제 열림 상태를 bool로 반환합니다. """
        @classmethod
        def _get_jlink(cls):
            """! @brief byte 검증한 개별 DLL 사본으로 동시 연결의 native 상태를 분리합니다. """
            lib = load_pinned_library(pylink, dll)
            warnings = []
            warning_count = [0]

            def observe_log(message, warning=False):
                """! @brief 제한된 경고 분류를 보존하고 callback에서 예외를 던지지 않습니다. """
                if warning or str(message).lstrip().startswith(('WARN:', 'ERROR:')):
                    warning_count[0] += 1
                    if len(warnings) < 32:
                        warnings.append({'kind': 'JLink_log_warning_or_error'})
                    else:
                        warnings[-1]['overflow'] = True

            link = SafeLink(lib=lib, unsecure_hook=lambda *_: pylink.enums.JLinkFlags.DLG_BUTTON_NO, log=observe_log,
                            detailed_log=observe_log, warn=lambda message: observe_log(message, True),
                            error=lambda message: observe_log(message, True))
            link._observer_warnings = warnings
            link._observer_warning_count = warning_count
            return link

        @property
        def is_open(self):
            """! @brief pylink 1.7의 opened 메서드를 호출하여 닫힌 상태를 정확히 판정합니다. """
            return bool(self._link.opened())

        def open(self):
            """! @brief 기본 non-interactive의 SilentUpdateFW 호출을 허용하지 않습니다. """
            if self.session.options.get('jlink.non_interactive') is not False:
                raise ValueError('Unsafe non-interactive default')
            try:
                returned = super().open()
                if self.Protocol.SWD not in self._supported_protocols or self._default_protocol != self.Protocol.SWD:
                    raise ValueError('SWD support required; no JTAG fallback')
                return returned
            except BaseException as primary_error:
                try:
                    if self.is_open and not getattr(self._link, '_native_close_attempted', False):
                        events.append({'operation': 'partial_probe_open_cleanup', 'status': 'ATTEMPTED'})
                        self.close()
                except BaseException as cleanup_error:
                    events.append({'operation': 'partial_probe_open_cleanup', 'status': 'FAIL',
                                   'error_type': type(cleanup_error).__name__})
                    primary_error.add_note('Partial probe open cleanup failed: ' + type(cleanup_error).__name__)
                raise

        def connect(self, protocol=None):
            """! @brief target 자동 선택·자동 연결·전력 제어 없이 원형 CoreSight 연결만 허용합니다. """
            if self.session.options.get('jlink.device') is not None or self.session.options.get('jlink.power') is not False:
                raise ValueError('Explicit raw CoreSight mode required')
            if protocol is None or protocol == self.Protocol.DEFAULT:
                protocol = self.Protocol.SWD
            if protocol != self.Protocol.SWD:
                raise ValueError('Only SWD protocol is allowed')
            return super().connect(protocol)

    return SafeLink, SafeProbe


def load_reviewed_pyocd(events):
    """! @brief 최초 import의 probe 자동 탐색만 차단하고 선택한 클래스와 옵션을 명시 로드합니다. """
    if 'pyocd' in sys.modules:
        raise RuntimeError('Fresh process without pre-imported pyOCD required')
    import importlib_metadata
    original = importlib_metadata.entry_points

    def scoped_entry_points(*args, **kwargs):
        """! @brief probe plugin의 기본 DLL 자동 로드만 차단합니다. """
        if not args and kwargs == {'group': 'pyocd.probe'}:
            events.append({'operation': 'probe_plugin_discovery', 'status': 'BLOCKED_EXPLICIT_ADAPTER_ONLY'})
            return ()
        return original(*args, **kwargs)

    try:
        importlib_metadata.entry_points = scoped_entry_points
        from pyocd.probe.jlink_probe import JLinkProbe, JLinkProbePlugin
        from pyocd.core.session import Session
        from pyocd.core.target import Target
        from pyocd.core.options import add_option_set
        from pyocd.probe.aggregator import PROBE_CLASSES
        if PROBE_CLASSES:
            raise RuntimeError('Unexpected automatic probe plugin')
        add_option_set(JLinkProbePlugin().options)
    finally:
        importlib_metadata.entry_points = original
        if 'pyocd.core.plugin' in sys.modules:
            sys.modules['pyocd.core.plugin'].entry_points = original
    return JLinkProbe, Session, Target


def checked_directory(value):
    """! @brief 새 출력·DLL 사본·project 경로를 D 작업 영역과 여유 하한으로 제한합니다. """
    path = Path(value).resolve()
    root = Path("D:/w06").resolve()
    if not path.is_relative_to(root) or not path.is_dir():
        raise ValueError("Existing D:/w06 directory required")
    if shutil.disk_usage(path).free < 4 * 1024 ** 3:
        raise ValueError("D:/w06 free-space floor reached")
    return path


def load_pinned_library(pylink, dll):
    """! @brief 고정 DLL byte를 먼저 검증한 뒤 D의 독립 사본만 로드합니다. """
    payload = Path(dll["path"]).read_bytes()
    if hashlib.sha256(payload).hexdigest() != dll["sha256"]:
        raise ValueError("Pinned J-Link DLL changed")
    temporary = checked_directory(tempfile.gettempdir())
    if shutil.disk_usage(temporary).free - len(payload) < 4 * 1024 ** 3:
        raise ValueError("J-Link DLL copy would cross D free-space floor")
    handle = tempfile.NamedTemporaryFile(prefix="w06-jlink-", suffix=".dll", dir=temporary,
                                         delete=False)
    try:
        with handle:
            handle.write(payload)
            handle.flush()
        if hashlib.sha256(Path(handle.name).read_bytes()).hexdigest() != dll["sha256"]:
            raise ValueError("Isolated J-Link DLL copy differs")
        library = pylink.library.Library(dllpath=handle.name, use_tmpcpy=False)
        ## @brief pylink의 원형 unload가 native 해제 후 사본을 제거하도록 소유권을 전달합니다.
        library._temp = handle
        return library
    except BaseException:
        Path(handle.name).unlink(missing_ok=True)
        raise


def checked_close(session, probe, row):
    """! @brief Session.close가 내부에서 삼킨 정리 오류까지 원형 호출 한 번으로 확인합니다. """
    event = {"status": "FAIL", "operations": []}
    row["session_close"] = event

    def observe(name, original):
        """! @brief 실제 정리 호출의 반환·예외를 보존합니다. """
        def invoke(*args, **kwargs):
            """! @brief private 오류 문자열 대신 실패한 동작만 기록합니다. """
            item = {"operation": name, "status": "FAIL"}
            event["operations"].append(item)
            try:
                value = original(*args, **kwargs)
                item["status"] = "RETURNED"
                return value
            except BaseException as error:
                item["error_type"] = type(error).__name__
                raise
        return invoke

    with ExitStack() as stack:
        for owner, name in ((session, "_trace_stop"), (session.board, "uninit"),
                            (probe, "disconnect"), (probe, "close")):
            original = getattr(owner, name)
            setattr(owner, name, observe(name, original))
            stack.callback(setattr, owner, name, original)
        session.close()
    if (any(item["status"] != "RETURNED" for item in event["operations"])
            or probe.is_open or probe.wire_protocol is not None):
        raise RuntimeError("J-Link session close incomplete")
    event["status"] = "PASS"


def _publish_session(directory, row):
    """! @brief 성공·실패 모두 새 sidecar에 기록하고 완전히 쓴 byte hash를 등록합니다. """
    row["ended_utc"] = datetime.now(timezone.utc).isoformat()
    payload = (json.dumps(row, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    path = directory / ("session-" + str(os.getpid()) + "-" + uuid.uuid4().hex + ".json")
    with path.open("xb") as stream:
        stream.write(payload)
    pin = {key: row[key] for key in ("status", "probe_sha256", "session_close", "transport",
                                    "initialized", "cpu_identity_verified")}
    if "target_uid_sha256" in row:
        pin["target_uid_sha256"] = row["target_uid_sha256"]
    pin.update(path=str(path), sha256=hashlib.sha256(payload).hexdigest())
    transport.record_session_receipt(pin)


def get_backend(fixture, base_type):
    """! @brief 프로세스당 명시 adapter 하나를 생성하고 선택·증거 경로 변경을 거부합니다. """
    global _BACKEND
    with _BACKEND_LOCK:
        audit_value = os.environ.get(transport.AUDIT_ENV)
        if not audit_value or not Path(audit_value).is_absolute():
            raise ValueError("Explicit existing J-Link audit directory required")
        audit_directory = checked_directory(audit_value)
        checked_directory(tempfile.gettempdir())
        if _BACKEND is not None:
            if (_BACKEND.fixture_sha256 != fixture["fixture_sha256"]
                    or _BACKEND.audit_directory != audit_directory):
                raise ValueError("J-Link backend binding changed")
            return _BACKEND
        import pylink
        events = []
        probe_base, session_type, target_type = load_reviewed_pyocd(events)
        from pyocd.flash.file_programmer import FileProgrammer
        from serial.tools import list_ports
        _, probe_type = build_types(pylink, probe_base, events, fixture["dll"])
        import m33_diagnostics as diagnostics

        class Backend(base_type):
            """! @brief 원형 sector program·SYSRESETREQ를 상속하는 별도 J-Link backend입니다. """
            def __init__(self):
                """! @brief 기본 probe 탐색 helper를 생성하지 않습니다. """
                self.session_type, self.target_type = session_type, target_type
                self.programmer_type, self.list_ports = FileProgrammer, list_ports
                self.fixture_sha256 = fixture["fixture_sha256"]
                self.audit_directory = audit_directory
                self.probes = None

            def discover(self):
                """! @brief OS mapping을 매번 확인하고 선택한 세 USB probe만 열거합니다. """
                with _SESSION_LOCK:
                    for board in fixture["boards"]:
                        transport.resolve_endpoint(board["probe_sha256"], None, board["port"], self.list_ports)
                    if self.probes is None:
                        self.probes = [probe_type(board["serial"]) for board in fixture["boards"]]
                    return list(self.probes), list(self.list_ports.comports())

            @contextmanager
            def session(self, probe, initialize=True):
                """! @brief caller의 공통 lock 안에서 exact identity와 모든 종료 동작을 확인합니다. """
                with _SESSION_LOCK:
                    if type(probe) is not probe_type or type(initialize) is not bool:
                        raise ValueError("Explicit J-Link probe/session type required")
                    transport.load_fixture()
                    checked_directory(self.audit_directory)
                    mapping = next((board for board in fixture["boards"]
                                    if board["serial"] == probe.unique_id), None)
                    if mapping is None or probe.is_open:
                        raise ValueError("Unmapped or already-open J-Link probe")
                    row = {"kind": "nu54-jlink-session", "status": "FAIL",
                           "started_utc": datetime.now(timezone.utc).isoformat(),
                           "pid": os.getpid(), "transport": transport.descriptor(),
                           "probe_sha256": mapping["probe_sha256"], "initialized": False,
                           "cpu_identity_verified": False,
                           "session_close": {"status": "NOT_ATTEMPTED", "operations": []}}
                    current = Path.cwd()
                    session = None
                    initialized = False
                    events_start = len(events)
                    warnings_start = probe._link._observer_warning_count[0]
                    options = dict(diagnostics.SAFE_SESSION_OPTIONS)
                    options.update({"jlink.device": None, "jlink.power": False,
                                    "jlink.non_interactive": False})
                    try:
                        with tempfile.TemporaryDirectory(prefix="w06-dk-session-") as temporary:
                            try:
                                session = self.session_type(probe, auto_open=False,
                                    options=dict(options, project_dir=temporary))
                                session.open(init_board=False)
                                session.target.dp.connect()
                                row["debug_identity"] = self.identity(session)
                                diagnostics.validate_debug_identity(row["debug_identity"])
                                if initialize:
                                    initialized = True
                                    session.board.init()
                                    row["initialized"] = True
                                    part = session.target.read32(0x00FFC31C)
                                    cpuid = session.target.read32(0xE000ED00)
                                    words = [session.target.read32(address)
                                             for address in (0x00FFC304, 0x00FFC308)]
                                    identity = hashlib.sha256(b"".join(
                                        value.to_bytes(4, "little") for value in words)).hexdigest()
                                    if (part != 0x54B15 or cpuid != 0x411FD210
                                            or identity != mapping["target_uid_sha256"]):
                                        raise ValueError("Exact nRF54L15 target identity mismatch")
                                    row["target_uid_sha256"] = identity
                                    row["cpu_identity_verified"] = True
                                yield session
                            finally:
                                try:
                                    if session is not None:
                                        try:
                                            if initialized:
                                                session.board.uninit()
                                        finally:
                                            checked_close(session, probe, row)
                                finally:
                                    os.chdir(current)
                        if probe._link._observer_warning_count[0] != warnings_start:
                            raise RuntimeError("J-Link session emitted warning or error")
                        row["status"] = "PASS"
                    except BaseException as error:
                        row["error_type"] = type(error).__name__
                        raise
                    finally:
                        final_error = None
                        for key, observe in (
                            ("probe_closed", lambda: not probe.is_open),
                            ("probe_disconnected", lambda: probe.wire_protocol is None),
                            ("library_warning_count", lambda: probe._link._observer_warning_count[0] - warnings_start),
                        ):
                            try:
                                row[key] = observe()
                            except BaseException as error:
                                row[key] = None
                                row.setdefault("final_observation_errors", []).append(
                                    {"operation": key, "error_type": type(error).__name__})
                                final_error = error
                        row["transport_events"] = events[events_start:]
                        if (row["probe_closed"] is not True or row["probe_disconnected"] is not True
                                or row["library_warning_count"] != 0):
                            if row["status"] == "PASS" and final_error is None:
                                final_error = RuntimeError("J-Link final state is not clean")
                            row["status"] = "FAIL"
                        _publish_session(self.audit_directory, row)
                        if final_error is not None:
                            raise RuntimeError("J-Link final close observation failed") from final_error

        _BACKEND = Backend()
        return _BACKEND
