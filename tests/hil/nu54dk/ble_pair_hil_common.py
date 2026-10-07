#!/usr/bin/env python3
"""! @brief M19/M20 두 보드 BLE HIL의 장치·image·UART 공통 경계를 제공합니다. """

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
import hashlib
import json
import math
import re
import secrets
import shutil
import string
import subprocess
import sys
import threading
import time
from typing import Any, Callable, Sequence


HIL_DIRECTORY = Path(__file__).resolve().parent
REPOSITORY = HIL_DIRECTORY.parents[2]
BOARD_ROOT = REPOSITORY / "board_package" / "NU54DK_Zephyr_DTS"

from m6_serial_echo import (  # noqa: E402
    DAPLINK_TARGET,
    DEFAULT_BAUD_RATE,
    DaplinkVolume,
    detail_value,
    find_daplink_volume,
    find_serial_port,
    normalize_board_id,
    read_details,
    validate_hex_image,
    wait_for_flash_result,
)
from m14_pin_hil import (  # noqa: E402
    CORE_SOURCE_SCOPES,
    build_record_value,
    file_sha256,
    git_revision,
    source_files_digest,
    validate_board_revision,
)


NONCE_PATTERN = re.compile(r"^[0-9a-f]{32}$")
MAX_TRANSCRIPT_BYTES = 262144
DEFAULT_RESULT_TIMEOUT_SECONDS = 180.0
ARDUINO_REVISION_FAMILIES = {
    "NUCODE_BLE_ISO": "m31_iso_revisions",
    "NUCODE_BLE_Audio": "m31_audio_revisions",
    "NUCODE_BLE_DirectionFinding": "m31_df_revisions",
    "NUCODE_BLE_ChannelSounding": "m31_cs_revisions",
}
ARDUINO_REVISION_FEATURES = {
    "NUCODE_BLE_ISO": "nucode.ble.iso",
    "NUCODE_BLE_Audio": "nucode.ble.audio",
    "NUCODE_BLE_DirectionFinding": "nucode.ble.direction_finding",
    "NUCODE_BLE_ChannelSounding": "nucode.ble.channel_sounding",
}


class BlePairHilFailure(RuntimeError):
    """! @brief M19/M20 pair HIL의 fail-closed 오류를 나타냅니다. """


class PairExecutionFailure(BlePairHilFailure):
    """! @brief 실행 오류와 실패 시점까지의 두 raw transcript를 보존합니다. """

    def __init__(
        self, message: str, peripheral_transcript: bytes, central_transcript: bytes
    ) -> None:
        super().__init__(message)
        self.peripheral_transcript = peripheral_transcript
        self.central_transcript = central_transcript


@dataclass(frozen=True)
class RoleEndpoint:
    """! @brief 한 role에 결합한 DAPLink UID·MSD·UART endpoint입니다. """

    board_id: str
    volume: DaplinkVolume
    port_name: str


@dataclass(frozen=True)
class RoleExecution:
    """! @brief 한 role의 flash 결과와 raw transcript입니다. """

    flash_sequence: str
    flash_bytes: str
    transcript: bytes


@dataclass(frozen=True)
class PairExecution:
    """! @brief 두 role의 동시 실행 결과입니다. """

    peripheral: RoleExecution
    central: RoleExecution


## @brief 동일 실행에 쓸 32자리 소문자 nonce를 검증하거나 생성합니다.
def build_nonce(explicit_nonce: str | None = None) -> str:
    nonce = explicit_nonce if explicit_nonce is not None else secrets.token_hex(16)
    if NONCE_PATTERN.fullmatch(nonce) is None:
        raise BlePairHilFailure("BLE pair nonce는 32자리 소문자 hex여야 합니다.")
    return nonce


## @brief 한 UID로 DAPLink MSD와 target UART를 함께 찾습니다.
def discover_endpoint(
    board_id: str,
    explicit_volume: str | None,
    explicit_port: str,
    list_ports: Any,
) -> RoleEndpoint:
    normalized = normalize_board_id(board_id)
    return RoleEndpoint(
        normalized,
        find_daplink_volume(normalized, explicit_volume),
        find_serial_port(normalized, explicit_port, list_ports),
    )


## @brief DAPLink UID 원문을 외부 증적에 쓸 SHA-256 identity로 변환합니다.
def probe_sha256(board_id: str) -> str:
    normalized = normalize_board_id(board_id)
    return hashlib.sha256(normalized.encode("ascii")).hexdigest()


## @brief pyOCD 진단 문자열에서 raw probe UID를 외부 출력 전에 제거합니다.
def redact_probe_output(payload: bytes, board_id: str) -> str:
    text = payload.decode("utf-8", errors="backslashreplace")
    return re.sub(
        re.escape(normalize_board_id(board_id)),
        "<probe-redacted>",
        text,
        flags=re.IGNORECASE,
    )


## @brief SHA-256 identity 하나에 정확히 하나의 DAPLink MSD와 UART를 결합합니다.
def discover_endpoint_sha256(
    digest: str,
    explicit_volume: str | None,
    explicit_port: str,
    list_ports: Any,
) -> RoleEndpoint:
    if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        raise BlePairHilFailure("probe identity는 64자리 소문자 SHA-256이어야 합니다.")
    roots = (
        (Path(explicit_volume).resolve(),)
        if explicit_volume is not None
        else tuple(Path(f"{letter}:/") for letter in string.ascii_uppercase)
    )
    matches: list[tuple[str, DaplinkVolume]] = []
    for root in roots:
        details = read_details(root)
        if details is None or detail_value(details, "Target Detect") != DAPLINK_TARGET:
            continue
        raw_uid = detail_value(details, "Unique ID")
        if raw_uid is None:
            continue
        normalized = normalize_board_id(raw_uid)
        if probe_sha256(normalized) == digest:
            matches.append((normalized, DaplinkVolume(root, details)))
    if len(matches) != 1:
        raise BlePairHilFailure(
            f"probe SHA-256 mapping은 정확히 하나여야 합니다: count={len(matches)}"
        )
    board_id, volume = matches[0]
    try:
        port_name = find_serial_port(board_id, explicit_port, list_ports)
    except Exception:
        raise BlePairHilFailure(
            "probe SHA-256에 대응하는 target UART를 결정하지 못했습니다."
        ) from None
    return RoleEndpoint(
        board_id,
        volume,
        port_name,
    )


## @brief raw UID 없이 외부 직렬화가 가능한 board identity를 만듭니다.
def public_endpoint(endpoint: RoleEndpoint) -> dict[str, str]:
    return {
        "probe_sha256": probe_sha256(endpoint.board_id),
        "msd_root": str(endpoint.volume.root),
        "uart_port": endpoint.port_name,
    }


def _load_private_pyocd_backend(digest: str):
    """! @brief raw UID를 argv에 넣지 않고 SHA-256으로 live pyOCD probe를 선택합니다. """

    if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        raise BlePairHilFailure("probe identity는 64자리 소문자 SHA-256이어야 합니다.")
    try:
        __import__("pyocd")
    except ModuleNotFoundError:
        from pyocd_launcher import _resolve_site_packages

        site_packages = _resolve_site_packages()
        if site_packages is not None and str(site_packages) not in sys.path:
            sys.path.insert(0, str(site_packages))
    tools = REPOSITORY / "tools" / "bluetooth"
    if str(tools) not in sys.path:
        sys.path.insert(0, str(tools))
    from m33_diagnostics import PyocdPreparationBackend, private_debug_output

    backend = PyocdPreparationBackend()
    with private_debug_output():
        probes, _ports = backend.discover()
    matches = [probe for probe in probes
               if probe_sha256(probe.unique_id) == digest]
    if len(matches) != 1:
        raise BlePairHilFailure(
            f"probe SHA-256 mapping은 정확히 하나여야 합니다: count={len(matches)}"
        )
    return backend, matches[0], private_debug_output


def collect_register_identity_sha256(
    digest: str,
    _volume: str | Path | None = None,
) -> dict[str, str]:
    """! @brief raw UID argv 없이 SHA-256 probe의 DP/AP identity를 읽습니다. """

    backend, probe, private_debug_output = _load_private_pyocd_backend(digest)
    try:
        from m33_diagnostics import validate_debug_identity

        with private_debug_output():
            with backend.session(probe, initialize=False) as session:
                values = backend.identity(session)
                validate_debug_identity(values)
    except Exception as error:
        raise BlePairHilFailure("CMSIS-DAP V2 DP/AP register query failure") from error
    return {
        "dp_idcode": f"0x{values['dp_idcode']:08x}",
        "dp_targetid_observed": f"0x{values['target_id']:08x}",
        "ahb_ap_idr": f"0x{values['ahb_ap_idr']:08x}",
        "ahb_ap_csw": f"0x{values['ahb_ap_csw']:08x}",
        "ctrl_ap_idr": f"0x{values['ctrl_ap_idr']:08x}",
        "approtect_status": f"0x{values['approtect_status']:08x}",
    }


def _intel_hex_programmed_bytes(image: Path) -> int:
    """! @brief Intel HEX의 실제 load byte 수를 중복 주소 없이 계산합니다. """

    tools = REPOSITORY / "tools" / "bluetooth"
    if str(tools) not in sys.path:
        sys.path.insert(0, str(tools))
    from m33_regression import intel_hex_ranges

    return sum(len(data) for _address, data in intel_hex_ranges(image))


def _flash_init_timed_out(error: BaseException) -> bool:
    """! @brief pyOCD flash algorithm 초기화 timeout만 정확히 식별합니다. """

    current: BaseException | None = error
    visited = set()
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        if (type(current).__name__ == "FlashFailure" and
                str(current).strip().casefold() == "flash init timed out"):
            return True
        current = current.__cause__ or current.__context__
    return False


def _run_flash_session_with_retry(
    digest: str,
    deadline: float,
    operation: Callable[[Any, Any], None],
) -> None:
    """! @brief init timeout에만 새 pyOCD session으로 유한 1회 재시도합니다. """

    for attempt in range(2):
        backend, probe, private_debug_output = _load_private_pyocd_backend(digest)
        try:
            with private_debug_output():
                with backend.session(probe) as session:
                    operation(backend, session)
            return
        except Exception as error:
            if (attempt == 0 and time.monotonic() < deadline and
                    _flash_init_timed_out(error)):
                continue
            raise


def flash_image_pyocd_sha256(
    role: str,
    digest: str,
    image: Path,
    timeout_seconds: float,
    *,
    defer_reset: bool = False,
    expected_sha256: str | None = None,
) -> tuple[str, str]:
    """! @brief raw UID argv 없이 SHA-256 live probe에 sector program을 수행합니다. """

    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise BlePairHilFailure("--flash-timeout은 0보다 커야 합니다.")
    image = validate_hex_image(str(image))
    raw = image.read_bytes()
    if expected_sha256 is not None and (
            not re.fullmatch(r"[0-9a-f]{64}", expected_sha256) or
            hashlib.sha256(raw).hexdigest() != expected_sha256):
        raise BlePairHilFailure(f"{role} exact HEX snapshot 불일치")
    programmed_bytes = _intel_hex_programmed_bytes(image)
    if image.read_bytes() != raw:
        raise BlePairHilFailure(f"{role} Intel HEX가 program 직전에 변경됐습니다.")
    if programmed_bytes <= 0:
        raise BlePairHilFailure(f"{role} Intel HEX load byte가 없습니다.")
    deadline = time.monotonic() + timeout_seconds
    try:
        def program(backend: Any, session: Any) -> None:
            """! @brief 한 session에서 sector program과 승인된 reset을 완료합니다. """

            if time.monotonic() >= deadline:
                raise BlePairHilFailure(f"{role} pyOCD sector flash timeout")
            backend.program(session, {"raw": raw})
            if not defer_reset:
                backend.start(session)
            if time.monotonic() >= deadline:
                raise BlePairHilFailure(f"{role} pyOCD sector flash timeout")

        _run_flash_session_with_retry(digest, deadline, program)
    except BlePairHilFailure:
        raise
    except Exception as error:
        raise BlePairHilFailure(f"{role} pyOCD sector flash 실패") from error
    mode = "pyocd-sector-no-reset" if defer_reset else "pyocd-sector-sw-reset"
    return mode, str(programmed_bytes)


def flash_binary_pyocd_sha256(
    role: str,
    digest: str,
    image: Path,
    base_address: int,
    timeout_seconds: float,
    *,
    defer_reset: bool = False,
) -> tuple[str, str]:
    """! @brief raw UID argv 없이 binary를 지정 주소에 sector program합니다. """

    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0 or \
            base_address < 0:
        raise BlePairHilFailure("binary flash 주소와 timeout이 잘못됐습니다.")
    image = image.resolve()
    if not image.is_file() or image.stat().st_size <= 0:
        raise BlePairHilFailure(f"{role} binary image가 없습니다.")
    deadline = time.monotonic() + timeout_seconds
    try:
        def program(backend: Any, session: Any) -> None:
            """! @brief 한 session에서 binary sector program과 reset을 완료합니다. """

            if time.monotonic() >= deadline:
                raise BlePairHilFailure(f"{role} pyOCD binary flash timeout")
            backend.programmer_type(
                session,
                chip_erase="sector",
                smart_flash=False,
                trust_crc=False,
                keep_unwritten=True,
                no_reset=True,
            ).program(
                str(image),
                base_address=base_address,
                file_format="bin",
            )
            if not defer_reset:
                backend.start(session)
            if time.monotonic() >= deadline:
                raise BlePairHilFailure(f"{role} pyOCD binary flash timeout")

        _run_flash_session_with_retry(digest, deadline, program)
    except BlePairHilFailure:
        raise
    except Exception as error:
        raise BlePairHilFailure(f"{role} pyOCD binary sector flash 실패") from error
    mode = "pyocd-sector-no-reset" if defer_reset else "pyocd-sector-sw-reset"
    return mode, str(image.stat().st_size)


def reset_target_pyocd_sha256(
    role: str,
    digest: str,
    timeout_seconds: float,
) -> str:
    """! @brief raw UID argv 없이 SHA-256 probe에 software reset을 수행합니다. """

    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise BlePairHilFailure("reset timeout은 0보다 커야 합니다.")
    deadline = time.monotonic() + timeout_seconds
    backend, probe, private_debug_output = _load_private_pyocd_backend(digest)
    try:
        with private_debug_output():
            with backend.session(probe) as session:
                if time.monotonic() >= deadline:
                    raise BlePairHilFailure(f"{role} pyOCD software reset timeout")
                backend.start(session)
                if time.monotonic() >= deadline:
                    raise BlePairHilFailure(f"{role} pyOCD software reset timeout")
    except BlePairHilFailure:
        raise
    except Exception as error:
        raise BlePairHilFailure(f"{role} pyOCD software reset 실패") from error
    return "pyocd-v2-sw-reset"


def erase_nrf54l_rram_pyocd_sha256(
    role: str,
    digest: str,
    start: int,
    size: int,
    timeout_seconds: float,
) -> dict[str, int | str]:
    """! @brief SHA-256 live probe로 지정 RRAM sector만 erase하고 전 byte를 검증합니다. """

    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0 or \
            start < 0 or size <= 0:
        raise BlePairHilFailure("RRAM sector erase 범위와 timeout이 잘못됐습니다.")
    deadline = time.monotonic() + timeout_seconds
    observed_digest: str | None = None
    try:
        from pyocd.flash.eraser import FlashEraser

        def erase(backend: Any, session: Any) -> None:
            """! @brief 한 session에서 sector erase와 전 byte readback을 완료합니다. """

            nonlocal observed_digest
            observed_hash = hashlib.sha256()
            halted = False
            try:
                if time.monotonic() >= deadline:
                    raise BlePairHilFailure(f"{role} RRAM sector erase timeout")
                FlashEraser(session, FlashEraser.Mode.SECTOR).erase(
                    [(start, start + size)]
                )
                session.target.halt()
                halted = True
                for address in range(start, start + size, 0x1000):
                    if time.monotonic() >= deadline:
                        raise BlePairHilFailure(f"{role} RRAM sector erase timeout")
                    length = min(0x1000, start + size - address)
                    observed = bytes(
                        session.target.read_memory_block8(address, length)
                    )
                    if len(observed) != length or observed != b"\xff" * length:
                        raise BlePairHilFailure(
                            f"{role} RRAM sector erase readback이 다릅니다."
                        )
                    observed_hash.update(observed)
                observed_digest = observed_hash.hexdigest()
            finally:
                if halted:
                    session.target.resume()

        _run_flash_session_with_retry(digest, deadline, erase)
    except BlePairHilFailure:
        raise
    except Exception as error:
        raise BlePairHilFailure(f"{role} RRAM sector erase 실패") from error
    expected_hash = hashlib.sha256(b"\xff" * size).hexdigest()
    if observed_digest != expected_hash:
        raise BlePairHilFailure(f"{role} RRAM sector erase digest가 다릅니다.")
    return {
        "mode": "pyocd-sector-erase-verified",
        "start": start,
        "end_exclusive": start + size,
        "bytes": size,
        "erase_value": "0xff",
        "expected_sha256": expected_hash,
        "observed_sha256": observed_digest,
        "readback_backend": "pyocd-live-target",
    }


def clear_nrf54l_rram_pyocd_sha256(
    role: str,
    digest: str,
    start: int,
    size: int,
    timeout_seconds: float,
) -> dict[str, int | str]:
    """! @brief SHA-256 live probe로 RRAM을 0xff로 채우고 전체 범위를 검증합니다. """

    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0 or \
            start < 0 or size <= 0 or \
            start % 4 != 0 or size % 0x100 != 0:
        raise BlePairHilFailure("RRAM clear 범위와 timeout이 잘못됐습니다.")
    deadline = time.monotonic() + timeout_seconds
    backend, probe, private_debug_output = _load_private_pyocd_backend(digest)
    try:
        with private_debug_output():
            with backend.session(probe) as session:
                session.target.halt()
                try:
                    session.target.write32(0x5004B500, 1)
                    if session.target.read32(0x5004B500) & 1 == 0:
                        raise BlePairHilFailure(
                            f"{role} RRAM write-enable 확인이 실패했습니다."
                        )
                    words = [0xFFFFFFFF] * (0x100 // 4)
                    for address in range(start, start + size, 0x100):
                        if time.monotonic() >= deadline:
                            raise BlePairHilFailure(f"{role} RRAM clear timeout")
                        session.target.write_memory_block32(address, words)
                    observed_hash = hashlib.sha256()
                    for address in range(start, start + size, 0x1000):
                        if time.monotonic() >= deadline:
                            raise BlePairHilFailure(f"{role} RRAM readback timeout")
                        length = min(0x1000, start + size - address)
                        observed = bytes(
                            session.target.read_memory_block8(address, length)
                        )
                        if len(observed) != length or observed != b"\xff" * length:
                            raise BlePairHilFailure(
                                f"{role} RRAM clear readback이 다릅니다."
                            )
                        observed_hash.update(observed)
                finally:
                    session.target.resume()
    except BlePairHilFailure:
        raise
    except Exception as error:
        raise BlePairHilFailure(f"{role} RRAM clear 실패") from error
    expected_hash = hashlib.sha256(b"\xff" * size).hexdigest()
    if observed_hash.hexdigest() != expected_hash:
        raise BlePairHilFailure(f"{role} RRAM 전체 range digest가 다릅니다.")
    return {
        "mode": "nrf54l-rram-fill-verified",
        "start": start,
        "end_exclusive": start + size,
        "bytes": size,
        "erase_value": "0xff",
        "verified_words": size // 4,
        "expected_sha256": expected_hash,
        "observed_sha256": observed_hash.hexdigest(),
        "readback_backend": "pyocd-live-target",
    }


## @brief 두 role이 서로 다른 UID·MSD·UART인지 검사합니다.
def validate_pair_identity(peripheral: RoleEndpoint, central: RoleEndpoint) -> None:
    if peripheral.board_id == central.board_id:
        raise BlePairHilFailure("peripheral과 central DAPLink UID가 같습니다.")
    if peripheral.volume.root.resolve() == central.volume.root.resolve():
        raise BlePairHilFailure("peripheral과 central DAPLink MSD가 같습니다.")
    if peripheral.port_name.casefold() == central.port_name.casefold():
        raise BlePairHilFailure("peripheral과 central UART가 같습니다.")


## @brief exact-commit HIL 입력 source와 board checkout이 clean인지 검사합니다.
def validate_source_clean(
    milestone: str,
    application_root: Path,
    runner_path: Path,
    additional_paths: Sequence[Path] = (),
) -> None:
    """! @brief runner가 직접 import하는 추가 source까지 exact clean 상태로 묶습니다. """

    core_paths = (
        "platform.txt",
        "cores/arduino",
        "dts",
        "libraries",
        "third_party/ArduinoCore-API",
        "third_party/ArduinoCore-API.provenance.yml",
        "variants/nu54dk",
        "zephyr",
        str(application_root.relative_to(REPOSITORY)),
        str(runner_path.relative_to(REPOSITORY)),
        "tests/hil/nu54dk/ble_pair_hil_common.py",
        "tests/hil/nu54dk/m14_pin_hil.py",
        "tests/hil/nu54dk/m6_serial_echo.py",
        "tests/hil/nu54dk/pyocd_launcher.py",
        *(str(path.resolve().relative_to(REPOSITORY)) for path in additional_paths),
    )
    core = subprocess.run(
        (
            "git",
            "-C",
            str(REPOSITORY),
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            "--",
            *core_paths,
        ),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    board = subprocess.run(
        (
            "git",
            "-C",
            str(BOARD_ROOT),
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        ),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if core.returncode != 0 or core.stdout.strip():
        raise BlePairHilFailure(
            f"{milestone} HIL source에 commit되지 않은 변경이 있습니다: "
            f"{core.stdout.strip() or core.stderr.strip()}"
        )
    if board.returncode != 0 or board.stdout.strip():
        raise BlePairHilFailure(
            "board_package submodule이 clean하지 않습니다: "
            f"{board.stdout.strip() or board.stderr.strip()}"
        )


## @brief build record와 비교할 현재 source byte digest를 계산합니다.
def current_source_digests(application_root: Path) -> dict[str, str]:
    board_scope = BOARD_ROOT / "boards" / "nucode" / "nu54dk"
    return {
        "core_source_sha256": source_files_digest(REPOSITORY, CORE_SOURCE_SCOPES),
        "application_source_sha256": source_files_digest(
            application_root, (application_root,)
        ),
        "board_source_sha256": source_files_digest(BOARD_ROOT, (board_scope,)),
    }


## @brief Arduino build artifact 옆의 JSON manifest를 fail-closed 방식으로 읽습니다.
def validate_arduino_build_manifest(
    image: Path,
    record_path: Path,
    core_revision: str,
    board_revision: str,
) -> dict[str, str]:
    try:
        if record_path.stat().st_size > 1024 * 1024:
            raise BlePairHilFailure("NUCODE Arduino build manifest 크기가 허용 범위를 넘었습니다.")
        document = json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BlePairHilFailure(
            f"Arduino build manifest를 읽지 못했습니다: {record_path}: {error}"
        ) from error
    if not isinstance(document, dict):
        raise BlePairHilFailure("Arduino build manifest 최상위 값이 object가 아닙니다.")

    def nested(*keys: str) -> Any:
        value: Any = document
        for key in keys:
            if not isinstance(value, dict) or key not in value:
                raise BlePairHilFailure(
                    f"Arduino build manifest 필드가 없습니다: {'.'.join(keys)}"
                )
            value = value[key]
        return value

    source_inputs = nested("source_inputs")
    if not isinstance(source_inputs, dict):
        raise BlePairHilFailure("Arduino build manifest의 source input 형식이 잘못됐습니다.")
    selected_libraries = nested("context", "selected_libraries")
    if (
        not isinstance(selected_libraries, list)
        or any(not isinstance(value, str) or not value
               for value in selected_libraries)
        or len(selected_libraries) != len(set(selected_libraries))
    ):
        raise BlePairHilFailure(
            "Arduino build manifest의 selected library 형식이 잘못됐습니다."
        )
    selected_revision_libraries = {
        value for value in selected_libraries
        if value in ARDUINO_REVISION_FAMILIES
    }
    expected_families = {
        ARDUINO_REVISION_FAMILIES[value]
        for value in selected_revision_libraries
    }
    input_manifest = nested("cache", "input_manifest")
    if not isinstance(input_manifest, dict):
        raise BlePairHilFailure("Arduino build manifest의 cache input 형식이 잘못됐습니다.")
    selected_features = nested(
        "cache", "input_manifest", "configuration", "selected_features"
    )
    if not isinstance(selected_features, list):
        raise BlePairHilFailure(
            "Arduino build manifest의 selected feature 형식이 잘못됐습니다."
        )
    selected_feature_ids = []
    for feature in selected_features:
        feature_id = feature.get("id") if isinstance(feature, dict) else None
        if not isinstance(feature_id, str) or not feature_id:
            raise BlePairHilFailure(
                "Arduino build manifest의 selected feature identity가 잘못됐습니다."
            )
        selected_feature_ids.append(feature_id)
    if len(selected_feature_ids) != len(set(selected_feature_ids)):
        raise BlePairHilFailure(
            "Arduino build manifest의 selected feature가 중복됐습니다."
        )
    revision_feature_ids = {
        feature_id for feature_id in selected_feature_ids
        if feature_id in ARDUINO_REVISION_FEATURES.values()
    }
    expected_feature_ids = {
        ARDUINO_REVISION_FEATURES[library]
        for library in selected_revision_libraries
    }
    if revision_feature_ids != expected_feature_ids:
        raise BlePairHilFailure(
            "Arduino build manifest의 selected library/cache feature가 다릅니다: "
            f"expected={sorted(expected_feature_ids)}, "
            f"actual={sorted(revision_feature_ids)}"
        )

    platform_root_value = nested("context", "platform_root")
    if not isinstance(platform_root_value, str) or not platform_root_value:
        raise BlePairHilFailure(
            "Arduino build manifest의 platform root 형식이 잘못됐습니다."
        )
    platform_root = Path(platform_root_value)
    if not platform_root.is_absolute():
        raise BlePairHilFailure(
            "Arduino build manifest의 platform root가 절대 경로가 아닙니다."
        )
    platform_root = platform_root.resolve()

    source_rows = source_inputs.get("sources")
    if not isinstance(source_rows, list):
        raise BlePairHilFailure(
            "Arduino build manifest의 source graph 형식이 잘못됐습니다."
        )
    source_libraries = set()
    for row in source_rows:
        logical_identity = (
            row.get("logical_identity") if isinstance(row, dict) else None
        )
        if not isinstance(logical_identity, str):
            raise BlePairHilFailure(
                "Arduino build manifest의 source identity 형식이 잘못됐습니다."
        )
        match = re.fullmatch(r"platform:libraries/([^/]+)/.+", logical_identity)
        if match is not None and match.group(1) in ARDUINO_REVISION_FAMILIES:
            library = match.group(1)
            source_path_value = row.get("source_path")
            if not isinstance(source_path_value, str) or not source_path_value:
                raise BlePairHilFailure(
                    "Arduino build manifest의 source path 형식이 잘못됐습니다."
                )
            source_path = Path(source_path_value)
            if not source_path.is_absolute():
                raise BlePairHilFailure(
                    "Arduino build manifest의 source path가 절대 경로가 아닙니다."
                )
            library_root = (platform_root / "libraries" / library).resolve()
            try:
                relative_source = source_path.resolve().relative_to(library_root)
            except ValueError as error:
                raise BlePairHilFailure(
                    "Arduino build manifest의 source identity/path가 다릅니다: "
                    f"identity={logical_identity}, source_path={source_path_value}"
                ) from error
            if not relative_source.parts:
                raise BlePairHilFailure(
                    "Arduino build manifest의 source path가 library 파일이 아닙니다: "
                    f"{source_path_value}"
                )
            expected_identity = (
                f"platform:libraries/{library}/{relative_source.as_posix()}"
            )
            if logical_identity != expected_identity:
                raise BlePairHilFailure(
                    "Arduino build manifest의 source identity/path가 다릅니다: "
                    f"identity={logical_identity}, expected={expected_identity}"
                )
            source_libraries.add(library)
    if source_libraries != selected_revision_libraries:
        raise BlePairHilFailure(
            "Arduino build manifest의 selected library/source graph가 다릅니다: "
            f"selected={sorted(selected_revision_libraries)}, "
            f"sources={sorted(source_libraries)}"
        )

    expected_revisions = {
        "NUCODE_CORE_REVISION": core_revision,
        "NUCODE_BOARD_REVISION": board_revision,
        "NUCODE_NCS_REVISION": "99553055607b2e9885fbc80ccd11fa9da81c2df0",
        "NUCODE_ZEPHYR_REVISION": "bf801e4e3d19e1ffa76164346480cb7734dd2800",
    }
    unknown_families = {
        key for key in source_inputs
        if key.startswith("m31_") and key.endswith("_revisions")
        and key not in ARDUINO_REVISION_FAMILIES.values()
    }
    if unknown_families:
        raise BlePairHilFailure(
            "Arduino build manifest에 알 수 없는 revision family가 있습니다: "
            f"{sorted(unknown_families)}"
        )
    revision_families = {
        key: source_inputs[key]
        for key in ARDUINO_REVISION_FAMILIES.values()
        if key in source_inputs
    }
    if set(revision_families) != expected_families:
        raise BlePairHilFailure(
            "Arduino build manifest의 selected library/revision family가 다릅니다: "
            f"expected={sorted(expected_families)}, "
            f"actual={sorted(revision_families)}"
        )
    for family, revisions in revision_families.items():
        if not isinstance(revisions, dict) or revisions != expected_revisions:
            raise BlePairHilFailure(
                "Arduino build manifest revision 불일치: "
                f"{family}={revisions}, expected={expected_revisions}"
            )

    cache_revisions = {
        "NUCODE_CORE_REVISION": nested(
            "cache", "input_manifest", "adapter", "embedded_core_revision"
        ),
        "NUCODE_BOARD_REVISION": nested(
            "cache", "input_manifest", "board_package", "revision"
        ),
        "NUCODE_NCS_REVISION": nested(
            "cache", "input_manifest", "ncs", "nrf_revision"
        ),
        "NUCODE_ZEPHYR_REVISION": nested(
            "cache", "input_manifest", "ncs", "zephyr_revision"
        ),
    }
    if cache_revisions != expected_revisions:
        raise BlePairHilFailure(
            "Arduino build manifest cache revision 불일치: "
            f"actual={cache_revisions}, expected={expected_revisions}"
        )

    image_artifact = nested("artifacts", "hex")
    if not isinstance(image_artifact, dict):
        raise BlePairHilFailure("Arduino build manifest의 HEX artifact 형식이 잘못됐습니다.")
    image_digest = file_sha256(image)
    expected_artifact = {
        "path": image.resolve().as_posix(),
        "sha256": image_digest,
        "size": image.stat().st_size,
    }
    for key, expected in expected_artifact.items():
        actual = image_artifact.get(key)
        if key == "path" and isinstance(actual, str):
            actual = Path(actual).resolve().as_posix()
        if actual != expected:
            raise BlePairHilFailure(
                f"Arduino build manifest HEX 불일치: {key}={actual}, expected={expected}"
            )

    board = nested("board")
    if board != "nrf54l15dk/nrf54l15/cpuapp/nu54dk":
        raise BlePairHilFailure(f"Arduino build manifest board 불일치: {board}")
    bundle = nested("cache", "input_manifest", "toolchain", "bundle_id")
    if bundle != "dcbdc366a1":
        raise BlePairHilFailure(f"Arduino build manifest toolchain bundle 불일치: {bundle}")
    compiler = nested("cache", "input_manifest", "toolchain", "compiler")
    if not isinstance(compiler, str) or "14.3.0" not in compiler:
        raise BlePairHilFailure(f"Arduino build manifest C++ compiler 불일치: {compiler}")

    return {
        "core_revision": core_revision,
        "board_revision": board_revision,
        "ncs_revision": expected_revisions["NUCODE_NCS_REVISION"],
        "zephyr_revision": expected_revisions["NUCODE_ZEPHYR_REVISION"],
        "board": "nrf54l15dk",
        "board_qualifiers": "nrf54l15/cpuapp/nu54dk",
        "toolchain_bundle_id": bundle,
        "cxx_compiler": compiler,
        "hex_sha256": image_digest,
        "record_format": "nu54-build-json",
        "record_name": record_path.name,
        "record_sha256": file_sha256(record_path),
    }


## @brief HEX build record를 exact revision·target·source byte와 결합합니다.
def validate_build_record(
    image: Path,
    core_revision: str,
    board_revision: str,
    application_root: Path,
) -> dict[str, str]:
    arduino_record_path = image.with_suffix(".nu54-build.json")
    if arduino_record_path.is_file():
        return validate_arduino_build_manifest(
            image, arduino_record_path, core_revision, board_revision
        )
    record_path = image.parent.parent / "nucode_arduino_core_build.yml"
    try:
        if record_path.stat().st_size > 16384:
            raise BlePairHilFailure("NUCODE build record 크기가 허용 범위를 넘었습니다.")
        record_text = record_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise BlePairHilFailure(
            f"HEX build record를 읽지 못했습니다: {record_path}: {error}"
        ) from error

    keys = (
        "core_revision",
        "core_source_sha256",
        "application_source_sha256",
        "board_revision",
        "board_source_sha256",
        "ncs_revision",
        "zephyr_revision",
        "board",
        "board_qualifiers",
        "toolchain_variant",
        "toolchain_path",
        "cxx_compiler",
    )
    values = {key: build_record_value(record_text, key) for key in keys}
    expected = {
        "core_revision": core_revision[:12],
        "board_revision": board_revision[:12],
        "ncs_revision": "99553055607b",
        "zephyr_revision": "bf801e4e3d19",
        "board": "nrf54l15dk",
        "board_qualifiers": "nrf54l15/cpuapp/nu54dk",
        "toolchain_variant": "zephyr",
    }
    for key, expected_value in expected.items():
        if values[key] != expected_value:
            raise BlePairHilFailure(
                f"build record 불일치: {key}={values[key]}, expected={expected_value}"
            )
    toolchain_path = values["toolchain_path"].replace("\\", "/").casefold()
    expected_toolchain_suffix = "/toolchains/dcbdc366a1/opt/zephyr-sdk"
    if not toolchain_path.endswith(expected_toolchain_suffix):
        raise BlePairHilFailure(
            f"build record toolchain bundle 불일치: {values['toolchain_path']}"
        )
    if values["cxx_compiler"] != "GNU 14.3.0":
        raise BlePairHilFailure(
            f"build record C++ compiler 불일치: {values['cxx_compiler']}"
        )
    for key, expected_digest in current_source_digests(application_root).items():
        if not re.fullmatch(r"[0-9a-f]{64}", values[key]):
            raise BlePairHilFailure(f"build record digest 형식 오류: {key}")
        if values[key] != expected_digest:
            raise BlePairHilFailure(
                f"build record source 불일치: {key}={values[key]}, "
                f"expected={expected_digest}"
            )
    values["record_name"] = record_path.name
    values["record_sha256"] = file_sha256(record_path)
    return values


## @brief evidence와 두 raw transcript의 신규 출력 경로를 준비합니다.
def prepare_output_paths(
    evidence_argument: str | None, overwrite: bool
) -> tuple[Path, Path, Path]:
    if not evidence_argument:
        raise BlePairHilFailure("실제 실행에는 --evidence가 필요합니다.")
    evidence = Path(evidence_argument).resolve()
    if evidence.suffix.lower() != ".json":
        raise BlePairHilFailure("--evidence는 .json 파일이어야 합니다.")
    peripheral = evidence.with_name(f"{evidence.stem}.peripheral.transcript.log")
    central = evidence.with_name(f"{evidence.stem}.central.transcript.log")
    paths = (evidence, peripheral, central)
    existing = [path for path in paths if path.exists()]
    if existing and not overwrite:
        raise BlePairHilFailure(
            "기존 증적을 덮어쓰지 않습니다: "
            + ", ".join(str(path) for path in existing)
        )
    for path in existing:
        if not path.is_file():
            raise BlePairHilFailure(f"증적 경로가 일반 파일이 아닙니다: {path}")
    evidence.parent.mkdir(parents=True, exist_ok=True)
    if overwrite:
        for path in existing:
            path.unlink()
    return paths


## @brief 한 role image를 지정 DAPLink MSD에 기록합니다.
def flash_image(
    milestone: str,
    role: str,
    volume: DaplinkVolume,
    image: Path,
    timeout_seconds: float,
) -> tuple[str, str]:
    if timeout_seconds <= 0:
        raise BlePairHilFailure("--flash-timeout은 0보다 커야 합니다.")
    previous_sequence = detail_value(volume.details, "Flash Sequence")
    destination = volume.root / f"NUCODE_{milestone}_{role.upper()}.HEX"
    shutil.copyfile(image, destination)
    details = wait_for_flash_result(volume.root, previous_sequence, timeout_seconds)
    return (
        detail_value(details, "Flash Sequence") or "unknown",
        detail_value(details, "Last Flash Bytes") or "unknown",
    )


## @brief legacy UID를 SHA-256으로 변환해 선택한 target sector만 기록합니다.
def flash_image_pyocd(
    role: str,
    board_id: str,
    image: Path,
    timeout_seconds: float,
    *,
    hardware_reset: bool = False,
    cmsis_dap_v1: bool = False,
    preserve_nrf54l_access: bool = False,
    defer_reset: bool = False,
) -> tuple[str, str]:
    if hardware_reset and defer_reset:
        raise BlePairHilFailure("hardware_reset과 defer_reset은 함께 사용할 수 없습니다.")
    if cmsis_dap_v1:
        raise BlePairHilFailure("hash-only pyOCD backend은 CMSIS-DAP V2만 허용합니다.")
    del preserve_nrf54l_access
    mode, programmed = flash_image_pyocd_sha256(
        role,
        probe_sha256(board_id),
        image,
        timeout_seconds,
        defer_reset=defer_reset,
    )
    if not hardware_reset and not defer_reset:
        mode = "pyocd-sector"
    return mode, programmed


## @brief 정지한 nRF54L의 RRAM 구간을 erase value로 채우고 전 byte를 검증합니다.
def clear_nrf54l_rram_pyocd(
    role: str,
    board_id: str,
    start: int,
    size: int,
    timeout_seconds: float,
) -> dict[str, int | str]:
    return clear_nrf54l_rram_pyocd_sha256(
        role,
        probe_sha256(board_id),
        start,
        size,
        timeout_seconds,
    )


## @brief CMSIS-DAP V2에서 flash 뒤 application software reset barrier를 실행합니다.
def reset_target_pyocd(
    role: str,
    board_id: str,
    timeout_seconds: float,
    *,
    preserve_nrf54l_access: bool = False,
) -> str:
    del preserve_nrf54l_access
    return reset_target_pyocd_sha256(
        role,
        probe_sha256(board_id),
        timeout_seconds,
    )


## @brief bounded UART capture에서 newline 하나를 읽습니다.
def read_line(
    serial_port: Any,
    pending: bytearray,
    raw_capture: bytearray,
    deadline: float,
    *,
    stop_event: threading.Event | None = None,
) -> bytes:
    while time.monotonic() < deadline:
        if stop_event is not None and stop_event.is_set():
            raise BlePairHilFailure("다른 role 실패로 UART 수집을 중단했습니다.")
        newline = pending.find(b"\n")
        if newline >= 0:
            line = bytes(pending[:newline]).rstrip(b"\r")
            del pending[: newline + 1]
            return line
        waiting = getattr(serial_port, "in_waiting", 0)
        chunk = serial_port.read(waiting if waiting > 0 else 1)
        if chunk:
            pending.extend(chunk)
            raw_capture.extend(chunk)
            if len(raw_capture) > MAX_TRANSCRIPT_BYTES:
                raise BlePairHilFailure("UART transcript가 허용 크기를 넘었습니다.")
    raise TimeoutError("UART line을 제한 시간 안에 읽지 못했습니다.")


## @brief role의 exact READY token까지 수집합니다.
def wait_ready(
    serial_port: Any,
    milestone: str,
    role: str,
    pending: bytearray,
    capture: bytearray,
    deadline: float,
) -> None:
    prefix = f"NUCODE_{milestone}_".encode("ascii")
    fail_prefix = f"NUCODE_{milestone}_FAIL:".encode("ascii")
    expected = f"NUCODE_{milestone}_READY:role={role}".encode("ascii")
    while True:
        line = read_line(serial_port, pending, capture, deadline)
        if line.startswith(fail_prefix):
            raise BlePairHilFailure(f"{role} target 실패: {line!r}")
        if line.startswith(prefix) and line != expected:
            raise BlePairHilFailure(
                f"{role} READY 앞 stale protocol token입니다: {line!r}"
            )
        if line == expected:
            return


## @brief 양쪽 role에 동일 nonce의 start command를 기록합니다.
def write_start_command(serial_port: Any, milestone: str, nonce: str) -> None:
    request = f"NUCODE_{milestone}_START:{nonce}\r\n".encode("ascii")
    written = serial_port.write(request)
    serial_port.flush()
    if written != len(request):
        raise BlePairHilFailure("BLE pair 시작 command가 일부만 기록됐습니다.")


## @brief peripheral 광고 확인 뒤 central scan 시작을 허용합니다.
def wait_peripheral_advertising(
    serial_port: Any,
    milestone: str,
    nonce: str,
    pending: bytearray,
    capture: bytearray,
    deadline: float,
) -> None:
    prefix = f"NUCODE_{milestone}_".encode("ascii")
    fail_prefix = f"NUCODE_{milestone}_FAIL:".encode("ascii")
    expected = (
        f"NUCODE_{milestone}_PERIPHERAL:ADVERTISE:PASS:nonce={nonce}"
    ).encode("ascii")
    while True:
        line = read_line(serial_port, pending, capture, deadline)
        if line.startswith(fail_prefix):
            raise BlePairHilFailure(f"peripheral target 실패: {line!r}")
        if line.startswith(prefix) and line != expected:
            raise BlePairHilFailure(
                f"광고 전 stale protocol token입니다: {line!r}"
            )
        if line == expected:
            return


## @brief 한 role의 현재 nonce FINAL까지 UART를 독립 수집합니다.
def collect_until_final(
    serial_port: Any,
    milestone: str,
    role: str,
    nonce: str,
    pending: bytearray,
    capture: bytearray,
    deadline: float,
    stop_event: threading.Event,
) -> None:
    final_prefix = f"NUCODE_{milestone}_{role.upper()}:FINAL:PASS:".encode(
        "ascii"
    )
    fail_prefix = f"NUCODE_{milestone}_FAIL:".encode("ascii")
    nonce_suffix = f":nonce={nonce}".encode("ascii")
    try:
        while True:
            line = read_line(
                serial_port, pending, capture, deadline, stop_event=stop_event
            )
            if line:
                print(f"[{role}] {line.decode('utf-8', errors='backslashreplace')}")
            if line.startswith(fail_prefix):
                raise BlePairHilFailure(f"{role} target 실패: {line!r}")
            if line.startswith(final_prefix):
                if not line.endswith(nonce_suffix):
                    raise BlePairHilFailure(f"{role} FINAL nonce 불일치: {line!r}")
                return
    except Exception:
        stop_event.set()
        raise


## @brief flash 전 UART를 열어 두 role의 전체 boot transcript를 보존합니다.
def execute_pair(
    *,
    serial_module: Any,
    milestone: str,
    peripheral_endpoint: RoleEndpoint,
    central_endpoint: RoleEndpoint,
    peripheral_image: Path,
    central_image: Path,
    nonce: str,
    baud_rate: int,
    flash_timeout: float,
    result_timeout: float,
    flash_backend: str = "daplink-msd",
) -> PairExecution:
    if baud_rate != DEFAULT_BAUD_RATE:
        raise BlePairHilFailure(f"기준선은 {DEFAULT_BAUD_RATE} baud만 허용합니다.")
    if not 30.0 <= result_timeout <= 600.0:
        raise BlePairHilFailure("--result-timeout은 30..600초여야 합니다.")
    if flash_backend not in ("daplink-msd", "pyocd-sector"):
        raise BlePairHilFailure(f"알 수 없는 flash backend입니다: {flash_backend}")

    captures = {"peripheral": bytearray(), "central": bytearray()}
    pending = {"peripheral": bytearray(), "central": bytearray()}
    flashes = {
        "peripheral": ("not-started", "unknown"),
        "central": ("not-started", "unknown"),
    }
    try:
        with ExitStack() as stack:
            ports = {}
            for role, endpoint in (
                ("peripheral", peripheral_endpoint),
                ("central", central_endpoint),
            ):
                ports[role] = stack.enter_context(
                    serial_module.Serial(
                        port=endpoint.port_name,
                        baudrate=baud_rate,
                        bytesize=serial_module.EIGHTBITS,
                        parity=serial_module.PARITY_NONE,
                        stopbits=serial_module.STOPBITS_ONE,
                        timeout=0.1,
                        write_timeout=2.0,
                    )
                )
                ports[role].reset_input_buffer()

            if flash_backend == "pyocd-sector":
                ports["peripheral"].reset_input_buffer()
                flashes["peripheral"] = flash_image_pyocd_sha256(
                    "peripheral",
                    probe_sha256(peripheral_endpoint.board_id),
                    peripheral_image,
                    flash_timeout,
                )
                ports["central"].reset_input_buffer()
                flashes["central"] = flash_image_pyocd_sha256(
                    "central",
                    probe_sha256(central_endpoint.board_id),
                    central_image,
                    flash_timeout,
                )
            else:
                ports["peripheral"].reset_input_buffer()
                flashes["peripheral"] = flash_image(
                    milestone,
                    "peripheral",
                    peripheral_endpoint.volume,
                    peripheral_image,
                    flash_timeout,
                )
                ports["central"].reset_input_buffer()
                flashes["central"] = flash_image(
                    milestone,
                    "central",
                    central_endpoint.volume,
                    central_image,
                    flash_timeout,
                )
            deadline = time.monotonic() + result_timeout
            for role in ("peripheral", "central"):
                wait_ready(
                    ports[role], milestone, role, pending[role], captures[role], deadline
                )
            write_start_command(ports["peripheral"], milestone, nonce)
            wait_peripheral_advertising(
                ports["peripheral"],
                milestone,
                nonce,
                pending["peripheral"],
                captures["peripheral"],
                deadline,
            )
            write_start_command(ports["central"], milestone, nonce)

            stop_event = threading.Event()
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [
                    executor.submit(
                        collect_until_final,
                        ports[role],
                        milestone,
                        role,
                        nonce,
                        pending[role],
                        captures[role],
                        deadline,
                        stop_event,
                    )
                    for role in ("peripheral", "central")
                ]
                try:
                    for future in futures:
                        future.result()
                except Exception:
                    stop_event.set()
                    raise
    except Exception as error:
        raise PairExecutionFailure(
            str(error), bytes(captures["peripheral"]), bytes(captures["central"])
        ) from error

    return PairExecution(
        RoleExecution(*flashes["peripheral"], bytes(captures["peripheral"])),
        RoleExecution(*flashes["central"], bytes(captures["central"])),
    )


## @brief milestone protocol line만 추출하고 stale nonce·FAIL을 거부합니다.
def protocol_lines(transcript: bytes, milestone: str, nonce: str) -> list[bytes]:
    nonce = build_nonce(nonce)
    prefix = f"NUCODE_{milestone}_".encode("ascii")
    ready_prefix = f"NUCODE_{milestone}_READY:".encode("ascii")
    fail_prefix = f"NUCODE_{milestone}_FAIL:".encode("ascii")
    expected_suffix = f":nonce={nonce}".encode("ascii")
    lines = [
        line.strip()
        for line in transcript.replace(b"\r", b"").split(b"\n")
        if line.strip().startswith(prefix)
    ]
    for line in lines:
        if line.startswith(fail_prefix):
            raise BlePairHilFailure(f"target 실패 token입니다: {line!r}")
        if line.startswith(ready_prefix):
            continue
        if not line.endswith(expected_suffix):
            raise BlePairHilFailure(f"stale 또는 다른 nonce token입니다: {line!r}")
    return lines


## @brief strict parser의 다음 exact line을 소비합니다.
def take_exact(lines: list[bytes], cursor: int, expected: bytes) -> int:
    if cursor >= len(lines):
        raise BlePairHilFailure(f"protocol line 누락: {expected!r}")
    if lines[cursor] != expected:
        raise BlePairHilFailure(
            f"protocol 순서/값 불일치: 기대={expected!r}, 실제={lines[cursor]!r}"
        )
    return cursor + 1


## @brief 시험 중 image byte 불변성을 재검사합니다.
def validate_image_unchanged(image: Path, size: int, sha256: str) -> None:
    if image.stat().st_size != size or file_sha256(image) != sha256:
        raise BlePairHilFailure("시험 중 HEX byte가 변경됐습니다.")


## @brief 실패 시점의 두 transcript를 출력 경로에 보존합니다.
def save_failure_transcripts(
    peripheral_path: Path, central_path: Path, error: Exception
) -> bool:
    if not isinstance(error, PairExecutionFailure):
        return False
    peripheral_path.write_bytes(error.peripheral_transcript)
    central_path.write_bytes(error.central_transcript)
    return True


## @brief raw transcript를 evidence용 identity record로 바꿉니다.
def transcript_record(path: Path, raw: bytes) -> dict[str, Any]:
    return {
        "name": path.name,
        "size": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


## @brief image를 build/flash identity record로 바꿉니다.
def image_record(
    image: Path,
    size: int,
    sha256: str,
    execution: RoleExecution,
    build_record: dict[str, str],
) -> dict[str, Any]:
    return {
        "name": image.name,
        "size": size,
        "sha256": sha256,
        "flash_sequence": execution.flash_sequence,
        "flash_bytes": execution.flash_bytes,
        "build_record": build_record,
    }


__all__ = [
    "BOARD_ROOT",
    "DEFAULT_BAUD_RATE",
    "DEFAULT_RESULT_TIMEOUT_SECONDS",
    "REPOSITORY",
    "BlePairHilFailure",
    "PairExecutionFailure",
    "RoleEndpoint",
    "build_nonce",
    "discover_endpoint",
    "execute_pair",
    "file_sha256",
    "git_revision",
    "image_record",
    "prepare_output_paths",
    "protocol_lines",
    "save_failure_transcripts",
    "take_exact",
    "transcript_record",
    "validate_board_revision",
    "validate_build_record",
    "validate_hex_image",
    "validate_image_unchanged",
    "validate_pair_identity",
    "validate_source_clean",
]
