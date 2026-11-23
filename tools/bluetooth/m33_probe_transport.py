"""! @brief 명시적으로 고정한 DK transport와 기존 CMSIS-DAP 경계를 선택합니다.
@note 이 모듈의 import·manifest 검사는 DLL 로드나 하드웨어 접근을 하지 않습니다.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading


FIXTURE_ENV = "NU54_HIL_JLINK_FIXTURE"
HASH_ENV = "NU54_HIL_JLINK_FIXTURE_SHA256"
AUDIT_ENV = "NU54_HIL_JLINK_AUDIT_DIR"
_FIXTURE_BINDING = None
_RECEIPTS = []
_RECEIPT_LOCK = threading.RLock()


def _sha(value):
    """! @brief 소문자 SHA-256 문자열만 허용합니다. """
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def canonical_serial(raw):
    """! @brief 완전한 decimal USB serial을 공통 lock identity로 정규화합니다. """
    if (not isinstance(raw, str) or not raw.isascii() or not raw.isdecimal()
            or not 1 <= len(raw) <= 12 or not 1 <= int(raw) <= 0xFFFFFFFF):
        raise ValueError("Invalid complete J-Link USB serial")
    return str(int(raw))


def validate_descriptor(value):
    """! @brief 과거 CMSIS와 실제 J-Link 증거를 서로 대체하지 않고 검증합니다. """
    if value == {"kind": "cmsis-dap-v2"}:
        return value
    if (not isinstance(value, dict)
            or set(value) != {"kind", "fixture_sha256", "dll_sha256", "board"}
            or value.get("kind") != "jlink-swd" or value.get("board") != "nrf54l15dk"
            or not _sha(value.get("fixture_sha256")) or not _sha(value.get("dll_sha256"))):
        raise ValueError("Invalid explicit probe transport descriptor")
    return value


def load_fixture():
    """! @brief path와 byte SHA를 함께 요구하고 한 프로세스 내 선택 변경을 거부합니다. """
    global _FIXTURE_BINDING
    path_text, expected = os.environ.get(FIXTURE_ENV), os.environ.get(HASH_ENV)
    if path_text is None and expected is None:
        if _FIXTURE_BINDING not in (None, ("cmsis-dap-v2", None)):
            raise ValueError("Probe transport selection removed during process")
        _FIXTURE_BINDING = ("cmsis-dap-v2", None)
        return None
    if not path_text or not _sha(expected):
        raise ValueError("J-Link fixture requires explicit path and SHA-256")
    path = Path(path_text)
    if not path.is_absolute() or not path.is_file():
        raise ValueError("J-Link fixture must be an existing absolute file")
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != expected:
        raise ValueError("J-Link fixture bytes changed")
    binding = (str(path.resolve()), expected)
    if _FIXTURE_BINDING is not None and binding != _FIXTURE_BINDING:
        raise ValueError("Probe transport fixture changed during process")
    fixture = json.loads(payload)
    if (not isinstance(fixture, dict)
            or set(fixture) != {"kind", "version", "board", "dll", "boards"}
            or fixture["kind"] != "nu54-hil-jlink-fixture" or type(fixture["version"]) is not int
            or fixture["version"] != 1 or fixture["board"] != "nrf54l15dk"):
        raise ValueError("Unknown J-Link fixture schema")
    dll = fixture["dll"]
    if (not isinstance(dll, dict) or set(dll) != {"path", "sha256"}
            or not isinstance(dll["path"], str) or not Path(dll["path"]).is_absolute()
            or not _sha(dll["sha256"])):
        raise ValueError("Explicit DLL path/hash required")
    boards = fixture["boards"]
    if not isinstance(boards, list) or len(boards) != 3:
        raise ValueError("Three exact physical DK identities required")
    for row in boards:
        if (not isinstance(row, dict)
                or set(row) != {"serial", "usb_serial", "probe_sha256", "target_uid_sha256",
                               "port", "vid", "pid", "interface"}
                or canonical_serial(row["serial"]) != row["serial"]
                or canonical_serial(row["usb_serial"]) != row["serial"]
                or row["probe_sha256"] != hashlib.sha256(row["serial"].encode("ascii")).hexdigest()
                or not _sha(row["target_uid_sha256"])
                or not isinstance(row["port"], str) or re.fullmatch(r"COM[1-9][0-9]*", row["port"]) is None
                or type(row["vid"]) is not int or row["vid"] != 0x1366
                or type(row["pid"]) is not int or row["pid"] != 0x1069
                or row["interface"] != "MI_02"):
            raise ValueError("Invalid exact DK USB/UART/target identity")
    for key in ("serial", "usb_serial", "probe_sha256", "target_uid_sha256", "port"):
        if len({row[key] for row in boards}) != 3:
            raise ValueError("Duplicate DK identity or UART")
    _FIXTURE_BINDING = binding
    return dict(fixture, fixture_sha256=expected)


def descriptor():
    """! @brief raw USB serial 없이 실제 선택한 transport를 증거에 결합합니다. """
    fixture = load_fixture()
    if fixture is None:
        return {"kind": "cmsis-dap-v2"}
    return {"kind": "jlink-swd", "fixture_sha256": fixture["fixture_sha256"],
            "dll_sha256": fixture["dll"]["sha256"], "board": fixture["board"]}


def reset_mode():
    """! @brief 동일 SYSRESETREQ 동작의 실제 probe transport를 구분합니다. """
    return "pyocd-v2-sw-reset" if load_fixture() is None else "pyocd-jlink-sw-reset"


def lock_identities(values, hashed=False):
    """! @brief 명시 DK의 부분 역할 실행도 같은 세 보드 lock 집합으로 보호합니다. """
    requested = list(values)
    fixture = load_fixture()
    if fixture is None:
        return requested
    key = "probe_sha256" if hashed else "serial"
    expected = [board[key] for board in fixture["boards"]]
    if not requested or any(value not in expected for value in requested):
        raise ValueError("Lock identity outside the pinned three-board DK fixture")
    return expected


def resolve_endpoint(digest, explicit_volume, explicit_port, list_ports):
    """! @brief 현재 OS의 exact USB serial·VID/PID·MI02·COM을 함께 대조합니다. """
    fixture = load_fixture()
    if fixture is None:
        return None
    if explicit_volume is not None:
        raise ValueError("J-Link DK has no DAPLink MSD endpoint")
    matches = [row for row in fixture["boards"] if row["probe_sha256"] == digest]
    if len(matches) != 1:
        raise ValueError("Probe is outside pinned DK fixture")
    row = matches[0]
    if explicit_port is not None and str(explicit_port).casefold() not in ("auto", row["port"].casefold()):
        raise ValueError("Requested UART differs from pinned DK fixture")
    ports = [port for port in list_ports.comports()
             if str(getattr(port, "device", "")).casefold() == row["port"].casefold()]
    if len(ports) != 1:
        raise ValueError("Pinned DK UART is unavailable or ambiguous")
    port = ports[0]
    pnp = [entry for entry in serial_pnp_snapshot()
           if entry.get("DeviceID", "").casefold() == row["port"].casefold()]
    if (getattr(port, "vid", None) != row["vid"] or getattr(port, "pid", None) != row["pid"]
            or getattr(port, "serial_number", None) != row["usb_serial"]
            or len(pnp) != 1 or pnp[0].get("Status") != "OK"
            or not pnp[0].get("PNPDeviceID", "").upper().startswith(
                "USB\\VID_1366&PID_1069&MI_02\\")):
        raise ValueError("Live DK composite USB mapping differs from fixture")
    return {"board_id": row["serial"], "port_name": str(port.device),
            "volume": None, "transport": descriptor()}


def serial_pnp_snapshot():
    """! @brief pySerial이 생략하는 composite interface를 Windows 읽기 전용 목록으로 대조합니다. """
    if os.name != "nt":
        raise ValueError("This pinned DK fixture requires Windows composite USB mapping")
    command = ("@(Get-CimInstance Win32_SerialPort | "
               "Select-Object DeviceID,PNPDeviceID,Status) | ConvertTo-Json -Compress")
    result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
                            capture_output=True, text=True, check=True, timeout=30,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    value = json.loads(result.stdout)
    return value if isinstance(value, list) else [value]


def ensure_pyocd_available():
    """! @brief SDK 검색을 보존하되 J-Link 선택에서 기본 probe DLL 자동 로드를 피합니다. """
    if importlib.util.find_spec("pyocd") is None:
        from pyocd_launcher import _resolve_site_packages
        site_packages = _resolve_site_packages()
        if site_packages is not None and str(site_packages) not in sys.path:
            sys.path.insert(0, str(site_packages))
    if load_fixture() is None:
        __import__("pyocd")


def session_receipts():
    """! @brief 이미 종료한 debug session의 불변 sidecar 결합값만 반환합니다. """
    with _RECEIPT_LOCK:
        return copy.deepcopy(_RECEIPTS)


def record_session_receipt(pin):
    """! @brief backend가 완전히 쓴 session 증거를 직렬화 순서대로 등록합니다. """
    with _RECEIPT_LOCK:
        _RECEIPTS.append(copy.deepcopy(pin))


def create_backend(default_factory):
    """! @brief 기본 CMSIS 구현을 보존하고 명시 선택한 DK backend만 생성합니다. """
    fixture = load_fixture()
    if fixture is None:
        return default_factory()
    ensure_pyocd_available()
    from m33_jlink_transport import get_backend
    return get_backend(fixture, default_factory)
