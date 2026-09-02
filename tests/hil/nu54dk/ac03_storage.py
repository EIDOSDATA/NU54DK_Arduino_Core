#!/usr/bin/env python3
"""! @brief 두 NU54DK의 AC-03 reset 영속성과 손상 복구를 자동 검증합니다. """

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import secrets
import subprocess
import sys
import time
from typing import Any, Sequence


HIL_DIRECTORY = Path(__file__).resolve().parent
REPOSITORY = HIL_DIRECTORY.parents[2]
BOARD_ROOT = REPOSITORY / "board_package" / "NU54DK_Zephyr_DTS"
APPLICATION_SOURCE_ROOT = REPOSITORY / "tests" / "zephyr" / "ac03_hil"
if str(HIL_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(HIL_DIRECTORY))

from ble_pair_hil_common import (  # noqa: E402
    BlePairHilFailure,
    current_source_digests as common_current_source_digests,
    git_revision as common_git_revision,
    validate_board_revision as common_validate_board_revision,
    validate_build_record as common_validate_build_record,
    validate_image_unchanged as common_validate_image_unchanged,
)
from m6_serial_echo import (  # noqa: E402
    DEFAULT_BAUD_RATE,
    find_daplink_volume,
    find_serial_port,
    flash_image,
    import_pyserial,
    normalize_board_id,
    validate_hex_image,
)


PREFIX = b"NUCODE_AC03_"
FAIL_PREFIX = b"NUCODE_AC03_FAIL:"
BOOT_PATTERN = re.compile(
    rb"^NUCODE_AC03_BOOT:schema=1:stage="
    rb"(idle|verify_persistence|verify_corruption|verify_recovery):"
    rb"nonce=(none|[0-9a-f]{32})$",
    re.MULTILINE,
)
FINAL_PATTERN = re.compile(
    rb"^NUCODE_AC03_FINAL:PASS:nonce=([0-9a-f]{32}):"
    rb"reset_persistence=1:corruption_recovery=1:cleanup=1$"
)
CLEAR_COMMAND = b"NUCODE_AC03_COMMAND:CLEAR\r\n"
START_COMMAND = b"NUCODE_AC03_COMMAND:START:"
CONTINUE_COMMAND = b"NUCODE_AC03_COMMAND:CONTINUE:"
SEED_TOKEN = (
    b"NUCODE_AC03_SEED:PASS:eeprom_commit=1:littlefs_no_format=1:"
    b"littlefs_format=1"
)
PERSISTENCE_TOKEN = b"NUCODE_AC03_RESET_PERSISTENCE:PASS:eeprom=1:littlefs=1"
CORRUPTION_TOKEN = b"NUCODE_AC03_CORRUPTION_INJECTED:PASS:length=5"
RECOVERY_TOKEN = (
    b"NUCODE_AC03_CORRUPTION_RECOVERY:PASS:rejected=1:explicit_reset=1:"
    b"fs_isolated=1:path_bounds=1"
)
DEFAULT_TIMEOUT_SECONDS = 120.0
MAX_TRANSCRIPT_BYTES = 262144
EVIDENCE_SCHEMA = 2
CORE_REVISION_PATTERN = re.compile(r"^[0-9a-f]{40}$")
SOURCE_CLEAN_PATHS = (
    "cores/arduino",
    "dts",
    "libraries",
    "third_party/ArduinoCore-API",
    "third_party/ArduinoCore-API.provenance.yml",
    "variants/nu54dk",
    "zephyr",
    "tests/zephyr/ac03_hil",
    "tests/hil/nu54dk/ac03_storage.py",
    "tests/hil/nu54dk/ble_pair_hil_common.py",
    "tests/hil/nu54dk/m14_pin_hil.py",
    "tests/hil/nu54dk/m6_serial_echo.py",
)


class AC03HilFailure(RuntimeError):
    """! @brief AC-03 두 보드 HIL의 선택·protocol·evidence 실패입니다. """


@dataclass(frozen=True)
class BoardResult:
    """! @brief 한 보드에서 검증한 AC-03 결과입니다. """

    board_id: str
    port: str
    nonce: str
    flash_sequence: str
    flash_bytes: str
    reset_boundaries: int
    eeprom_persistence: bool
    littlefs_persistence: bool
    corruption_recovery: bool
    cleanup: bool


def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    """! @brief 서로 다른 보드 두 대와 파괴 승인을 요구하는 CLI를 구성합니다. """

    parser = argparse.ArgumentParser(
        description=(
            "같은 AC-03 HIL HEX를 NU54DK 두 대에 순차 기록하고 EEPROM/LittleFS "
            "reset 영속성, 손상 거부, 명시 복구와 시험 data 정리를 검증합니다."
        )
    )
    parser.add_argument("--hex", dest="hex_path")
    parser.add_argument("--board-id", action="append", required=True)
    parser.add_argument("--port", action="append", default=[])
    parser.add_argument("--volume", action="append", default=[])
    parser.add_argument("--baud", type=int, default=DEFAULT_BAUD_RATE)
    parser.add_argument("--flash-timeout", type=float, default=45.0)
    parser.add_argument("--result-timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument(
        "--evidence",
        help="PASS JSON evidence 경로(--discover-only가 아니면 필수)",
    )
    parser.add_argument(
        "--expected-core-revision",
        help="시험할 checkout의 기대 40자리 Core commit",
    )
    parser.add_argument("--discover-only", action="store_true")
    parser.add_argument(
        "--allow-destructive-storage",
        action="store_true",
        help="두 보드의 EEPROM mirror와 전용 LittleFS 시험 영역 변경을 승인합니다.",
    )
    return parser.parse_args(arguments)


def file_sha256(path: Path) -> str:
    """! @brief 파일의 SHA-256을 streaming 방식으로 계산합니다. """

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def prepare_evidence_path(argument: str | None) -> tuple[Path, Path]:
    """! @brief 실제 실행 전에 신규 JSON과 원자 기록용 임시 경로를 예약합니다. """

    if not argument:
        raise AC03HilFailure("실제 실행에는 --evidence가 필요합니다.")
    evidence = Path(argument).resolve()
    if evidence.suffix.lower() != ".json":
        raise AC03HilFailure("--evidence는 .json 파일이어야 합니다.")
    temporary = evidence.with_name(f".{evidence.name}.tmp")
    existing = [path for path in (evidence, temporary) if path.exists()]
    if existing:
        raise AC03HilFailure(
            "기존 evidence를 덮어쓰지 않습니다: "
            + ", ".join(str(path) for path in existing)
        )
    evidence.parent.mkdir(parents=True, exist_ok=True)
    return evidence, temporary


def write_evidence(evidence: Path, temporary: Path, value: dict[str, Any]) -> None:
    """! @brief PASS evidence를 신규 임시 파일에 쓴 뒤 원자적으로 공개합니다. """

    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(
                json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
                + "\n"
            )
        temporary.replace(evidence)
    except Exception:
        if temporary.is_file():
            temporary.unlink()
        raise


def validate_source_clean() -> None:
    """! @brief AC-03 image·runner 입력과 board submodule의 clean 상태를 검사합니다. """

    core = subprocess.run(
        (
            "git",
            "-C",
            str(REPOSITORY),
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            "--",
            *SOURCE_CLEAN_PATHS,
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
        raise AC03HilFailure(
            "AC-03 HIL source에 commit되지 않은 변경이 있습니다: "
            f"{core.stdout.strip() or core.stderr.strip()}"
        )
    if board.returncode != 0 or board.stdout.strip():
        raise AC03HilFailure(
            "board_package submodule이 clean하지 않습니다: "
            f"{board.stdout.strip() or board.stderr.strip()}"
        )


def validate_exact_inputs(
    image_argument: str | None, expected_core_revision: str | None
) -> tuple[Path, str, str, dict[str, str], dict[str, str], int, str]:
    """! @brief HEX를 exact commit·gitlink·source digest·build record에 결합합니다. """

    if expected_core_revision is None:
        raise AC03HilFailure("실제 실행에는 --expected-core-revision이 필요합니다.")
    normalized = expected_core_revision.strip().lower()
    if CORE_REVISION_PATTERN.fullmatch(normalized) is None:
        raise AC03HilFailure(
            "--expected-core-revision은 40자리 소문자 SHA여야 합니다."
        )
    image = validate_hex_image(image_argument)
    try:
        core_revision = common_git_revision(REPOSITORY, normalized)
        board_revision = common_git_revision(BOARD_ROOT)
        common_validate_board_revision(board_revision)
        validate_source_clean()
        build_record = common_validate_build_record(
            image, core_revision, board_revision, APPLICATION_SOURCE_ROOT
        )
        source_digests = common_current_source_digests(APPLICATION_SOURCE_ROOT)
    except (BlePairHilFailure, RuntimeError, OSError, ValueError) as error:
        raise AC03HilFailure(f"AC-03 exact input 검증 실패: {error}") from error
    image_size = image.stat().st_size
    image_sha256 = file_sha256(image)
    return (
        image,
        core_revision,
        board_revision,
        build_record,
        source_digests,
        image_size,
        image_sha256,
    )


def validate_image_unchanged(image: Path, size: int, sha256: str) -> None:
    """! @brief 시험 전후 HEX byte가 같은지 AC-03 오류로 검사합니다. """

    try:
        common_validate_image_unchanged(image, size, sha256)
    except (BlePairHilFailure, OSError) as error:
        raise AC03HilFailure(f"AC-03 HEX 불변성 검증 실패: {error}") from error


def _complete_lines(transcript: bytes) -> list[bytes]:
    """! @brief 개행까지 수신된 UART line만 순서대로 반환합니다. """

    return [
        line.strip()
        for line in transcript.replace(b"\r", b"").split(b"\n")[:-1]
        if line.strip()
    ]


def _protocol_lines(transcript: bytes) -> list[bytes]:
    """! @brief 완전히 수신된 AC-03 protocol line만 순서대로 반환합니다. """

    return [
        line for line in _complete_lines(transcript) if line.startswith(PREFIX)
    ]


def _find_after(lines: list[bytes], expected: bytes, cursor: int) -> int:
    """! @brief cursor 뒤의 exact token을 찾고 다음 위치를 반환합니다. """

    for index in range(cursor, len(lines)):
        if lines[index] == expected:
            return index + 1
    raise AC03HilFailure(f"필수 protocol token이 없습니다: {expected!r}")


def _find_boot_after(
    lines: list[bytes], stage: bytes, nonce: bytes, cursor: int
) -> int:
    """! @brief 지정 stage·nonce의 reset 뒤 boot token을 찾습니다. """

    for index in range(cursor, len(lines)):
        match = BOOT_PATTERN.fullmatch(lines[index])
        if match is not None and match.groups() == (stage, nonce):
            return index + 1
    raise AC03HilFailure(
        f"reset boot 경계가 없습니다: stage={stage!r}, nonce={nonce!r}"
    )


def parse_transcript(transcript: bytes, expected_nonce: str) -> None:
    """! @brief 한 보드의 전체 reset·복구 protocol을 fail-closed로 검증합니다. """

    if FAIL_PREFIX in transcript:
        raise AC03HilFailure("target FAIL token이 있습니다.")
    nonce = expected_nonce.encode("ascii")
    lines = _protocol_lines(transcript)
    cursor = _find_after(lines, b"NUCODE_AC03_CLEARED:PASS", 0)
    cursor = _find_boot_after(lines, b"idle", b"none", cursor)
    cursor = _find_after(lines, SEED_TOKEN, cursor)
    cursor = _find_boot_after(lines, b"verify_persistence", nonce, cursor)
    cursor = _find_after(lines, PERSISTENCE_TOKEN, cursor)
    cursor = _find_after(lines, CORRUPTION_TOKEN, cursor)
    cursor = _find_boot_after(lines, b"verify_corruption", nonce, cursor)
    cursor = _find_after(lines, RECOVERY_TOKEN, cursor)
    cursor = _find_boot_after(lines, b"verify_recovery", nonce, cursor)
    final_index = None
    for index in range(cursor, len(lines)):
        match = FINAL_PATTERN.fullmatch(lines[index])
        if match is not None:
            if match.group(1) != nonce:
                raise AC03HilFailure("최종 nonce가 START nonce와 다릅니다.")
            final_index = index
            break
    if final_index is None:
        raise AC03HilFailure("최종 PASS token이 없습니다.")
    trailing = [line for line in lines[final_index + 1 :] if line.startswith(PREFIX)]
    if trailing:
        raise AC03HilFailure(f"최종 PASS 뒤 예상하지 않은 token이 있습니다: {trailing!r}")


def _write_command(serial_port: Any, command: bytes) -> None:
    """! @brief 명령 전체를 UART에 기록하고 즉시 flush합니다. """

    written = serial_port.write(command)
    if written != len(command):
        raise AC03HilFailure(f"UART command 일부만 기록됐습니다: {written}/{len(command)}")
    serial_port.flush()


def execute_protocol(
    serial_module: Any,
    port: str,
    baud: int,
    nonce: str,
    timeout_seconds: float,
) -> bytes:
    """! @brief boot stage를 따라 CLEAR·START·CONTINUE를 한 번씩 보냅니다. """

    if timeout_seconds <= 0:
        raise ValueError("--result-timeout은 0보다 커야 합니다.")
    observed = bytearray()
    clear_sent = False
    cleared = False
    start_sent = False
    continued: set[bytes] = set()
    deadline = time.monotonic() + timeout_seconds
    nonce_bytes = nonce.encode("ascii")
    with serial_module.Serial(
        port=port,
        baudrate=baud,
        bytesize=serial_module.EIGHTBITS,
        parity=serial_module.PARITY_NONE,
        stopbits=serial_module.STOPBITS_ONE,
        timeout=0.1,
        write_timeout=2.0,
    ) as serial_port:
        while time.monotonic() < deadline:
            waiting = serial_port.in_waiting
            chunk = serial_port.read(waiting if waiting > 0 else 1)
            if chunk:
                observed.extend(chunk)
                if len(observed) > MAX_TRANSCRIPT_BYTES:
                    raise AC03HilFailure("UART transcript가 허용 크기를 초과했습니다.")
            transcript = bytes(observed)
            lines = _protocol_lines(transcript)
            if any(line.startswith(FAIL_PREFIX) for line in lines):
                raise AC03HilFailure("target FAIL token이 있습니다.")
            if not clear_sent and any(
                BOOT_PATTERN.fullmatch(line) is not None for line in lines
            ):
                _write_command(serial_port, CLEAR_COMMAND)
                clear_sent = True
                continue
            if (
                clear_sent
                and not cleared
                and b"NUCODE_AC03_CLEARED:PASS" in lines
            ):
                cleared = True
            if cleared and not start_sent:
                idle = b"NUCODE_AC03_BOOT:schema=1:stage=idle:nonce=none"
                cleared_index = max(
                    index
                    for index, line in enumerate(lines)
                    if line == b"NUCODE_AC03_CLEARED:PASS"
                )
                if idle in lines[cleared_index + 1 :]:
                    _write_command(serial_port, START_COMMAND + nonce_bytes + b"\r\n")
                    start_sent = True
                    continue
            for stage, prerequisite in (
                (b"verify_persistence", SEED_TOKEN),
                (b"verify_corruption", CORRUPTION_TOKEN),
                (b"verify_recovery", RECOVERY_TOKEN),
            ):
                if stage in continued or prerequisite not in lines:
                    continue
                boot = (
                    b"NUCODE_AC03_BOOT:schema=1:stage="
                    + stage
                    + b":nonce="
                    + nonce_bytes
                )
                if boot in lines:
                    _write_command(
                        serial_port, CONTINUE_COMMAND + nonce_bytes + b"\r\n"
                    )
                    continued.add(stage)
                    break
            final = (
                b"NUCODE_AC03_FINAL:PASS:nonce="
                + nonce_bytes
                + b":reset_persistence=1:corruption_recovery=1:cleanup=1"
            )
            if final in lines:
                parse_transcript(transcript, nonce)
                return transcript
    raise AC03HilFailure(
        f"AC-03 최종 PASS를 {timeout_seconds:.1f}초 안에 받지 못했습니다."
    )


def execute_clear_protocol(
    serial_module: Any,
    port: str,
    baud: int,
    timeout_seconds: float,
) -> bytes:
    """! @brief 재기록된 target에 CLEAR를 보내 idle 재부팅까지 확인합니다. """

    if timeout_seconds <= 0:
        raise ValueError("복구 timeout은 0보다 커야 합니다.")
    observed = bytearray()
    clear_sent = False
    deadline = time.monotonic() + timeout_seconds
    with serial_module.Serial(
        port=port,
        baudrate=baud,
        bytesize=serial_module.EIGHTBITS,
        parity=serial_module.PARITY_NONE,
        stopbits=serial_module.STOPBITS_ONE,
        timeout=0.1,
        write_timeout=2.0,
    ) as serial_port:
        while time.monotonic() < deadline:
            waiting = serial_port.in_waiting
            chunk = serial_port.read(waiting if waiting > 0 else 1)
            if chunk:
                observed.extend(chunk)
                if len(observed) > MAX_TRANSCRIPT_BYTES:
                    raise AC03HilFailure("복구 UART transcript가 허용 크기를 초과했습니다.")
            lines = _protocol_lines(bytes(observed))
            if any(line.startswith(FAIL_PREFIX) for line in lines):
                raise AC03HilFailure("복구 target FAIL token이 있습니다.")
            if not clear_sent and any(
                BOOT_PATTERN.fullmatch(line) is not None for line in lines
            ):
                _write_command(serial_port, CLEAR_COMMAND)
                clear_sent = True
                continue
            if not clear_sent or b"NUCODE_AC03_CLEARED:PASS" not in lines:
                continue
            cleared_index = max(
                index
                for index, line in enumerate(lines)
                if line == b"NUCODE_AC03_CLEARED:PASS"
            )
            idle = b"NUCODE_AC03_BOOT:schema=1:stage=idle:nonce=none"
            if idle in lines[cleared_index + 1 :]:
                return bytes(observed)
    raise AC03HilFailure(
        f"실패 후 CLEAR·idle 복구를 {timeout_seconds:.1f}초 안에 확인하지 못했습니다."
    )


def run_board(
    *,
    board_id: str,
    port: str,
    volume: str | None,
    image: Path,
    serial_module: Any,
    list_ports: Any,
    baud: int,
    flash_timeout: float,
    result_timeout: float,
) -> tuple[BoardResult, bytes]:
    """! @brief 한 보드를 UID로 고정해 flash하고 전체 scenario를 실행합니다. """

    selected_volume = find_daplink_volume(board_id, volume)
    selected_port = find_serial_port(board_id, port, list_ports)
    sequence, byte_count = flash_image(selected_volume, image, flash_timeout)
    nonce = secrets.token_hex(16)
    transcript = execute_protocol(
        serial_module, selected_port, baud, nonce, result_timeout
    )
    return (
        BoardResult(
            board_id=board_id,
            port=selected_port,
            nonce=nonce,
            flash_sequence=sequence,
            flash_bytes=byte_count,
            reset_boundaries=3,
            eeprom_persistence=True,
            littlefs_persistence=True,
            corruption_recovery=True,
            cleanup=True,
        ),
        transcript,
    )


def best_effort_recover_board(
    *,
    board_id: str,
    port: str,
    volume: str | None,
    image: Path,
    serial_module: Any,
    list_ports: Any,
    baud: int,
    flash_timeout: float,
    result_timeout: float,
    image_size: int,
    image_sha256: str,
) -> str:
    """! @brief 실패한 보드를 같은 HEX로 reset한 뒤 시험 저장소를 CLEAR합니다. """

    validate_image_unchanged(image, image_size, image_sha256)
    selected_volume = find_daplink_volume(board_id, volume)
    selected_port = find_serial_port(board_id, port, list_ports)
    sequence, _ = flash_image(selected_volume, image, flash_timeout)
    execute_clear_protocol(
        serial_module,
        selected_port,
        baud,
        min(max(result_timeout, 15.0), 180.0),
    )
    return sequence


def recover_touched_boards(
    *,
    touched: Sequence[tuple[str, str, str]],
    image: Path,
    serial_module: Any,
    list_ports: Any,
    baud: int,
    flash_timeout: float,
    result_timeout: float,
    image_size: int,
    image_sha256: str,
) -> list[str]:
    """! @brief 원래 오류를 방해하지 않고 모든 접촉 보드의 복구 결과를 수집합니다. """

    reports: list[str] = []
    for board_id, port, volume in reversed(tuple(touched)):
        try:
            sequence = best_effort_recover_board(
                board_id=board_id,
                port=port,
                volume=volume,
                image=image,
                serial_module=serial_module,
                list_ports=list_ports,
                baud=baud,
                flash_timeout=flash_timeout,
                result_timeout=result_timeout,
                image_size=image_size,
                image_sha256=image_sha256,
            )
            reports.append(f"{board_id}=cleared(sequence={sequence})")
        ## @brief 한 보드 복구 실패를 기록하고 나머지 보드의 복구를 계속합니다.
        except Exception as recovery_error:
            reports.append(
                f"{board_id}=recovery-failed({type(recovery_error).__name__}: "
                f"{recovery_error})"
            )
    return reports


def resolve_endpoints(
    board_ids: Sequence[str],
    ports: Sequence[str],
    volumes: Sequence[str | None],
    list_ports: Any,
) -> list[tuple[str, str, str]]:
    """! @brief destructive 실행 전에 두 UID의 서로 다른 MSD·UART를 확정합니다. """

    endpoints: list[tuple[str, str, str]] = []
    for board_id, port, volume in zip(board_ids, ports, volumes):
        found_volume = find_daplink_volume(board_id, volume)
        found_port = find_serial_port(board_id, port, list_ports)
        endpoints.append((board_id, found_port, str(found_volume.root)))
    roots = {Path(item[2]).resolve() for item in endpoints}
    port_names = {item[1].casefold() for item in endpoints}
    if len(roots) != 2 or len(port_names) != 2:
        raise AC03HilFailure("두 UID가 서로 다른 DAPLink MSD와 UART에 결합되지 않았습니다.")
    return endpoints


def main(arguments: Sequence[str] | None = None) -> int:
    """! @brief 두 보드 실행 결과가 모두 PASS일 때만 evidence를 기록합니다. """

    args = parse_arguments(arguments)
    board_ids = [normalize_board_id(value) for value in args.board_id]
    if len(board_ids) != 2 or len(set(board_ids)) != 2:
        raise AC03HilFailure("서로 다른 --board-id를 정확히 두 번 지정해야 합니다.")
    if len(args.port) > 2 or len(args.volume) > 2:
        raise AC03HilFailure("--port와 --volume은 보드 순서대로 최대 두 번 지정합니다.")
    ports = list(args.port) + ["auto"] * (2 - len(args.port))
    volumes = list(args.volume) + [None] * (2 - len(args.volume))
    serial_module, list_ports = import_pyserial()
    if args.discover_only:
        for board_id, port, volume in zip(board_ids, ports, volumes):
            found_volume = find_daplink_volume(board_id, volume)
            found_port = find_serial_port(board_id, port, list_ports)
            print(f"AC03_DISCOVER_PASS={board_id};VOLUME={found_volume.root};PORT={found_port}")
        return 0
    if not args.allow_destructive_storage:
        raise AC03HilFailure(
            "실행 전 --allow-destructive-storage로 EEPROM과 전용 FS 시험 변경을 승인해야 합니다."
        )
    evidence_path, evidence_temporary = prepare_evidence_path(args.evidence)
    (
        image,
        core_revision,
        board_revision,
        build_record,
        source_digests,
        image_size,
        image_sha256,
    ) = validate_exact_inputs(args.hex_path, args.expected_core_revision)
    endpoints = resolve_endpoints(board_ids, ports, volumes, list_ports)
    results: list[BoardResult] = []
    transcripts: dict[str, str] = {}
    touched: list[tuple[str, str, str]] = []
    try:
        for board_id, port, volume in endpoints:
            touched.append((board_id, port, volume))
            result, transcript = run_board(
                board_id=board_id,
                port=port,
                volume=volume,
                image=image,
                serial_module=serial_module,
                list_ports=list_ports,
                baud=args.baud,
                flash_timeout=args.flash_timeout,
                result_timeout=args.result_timeout,
            )
            validate_image_unchanged(image, image_size, image_sha256)
            results.append(result)
            transcripts[board_id] = transcript.decode("ascii", errors="replace")
            print(f"AC03_BOARD_PASS={board_id};PORT={result.port};RESETS=3")
        evidence = {
            "schema_version": EVIDENCE_SCHEMA,
            "gate": "ac03-two-board-storage-hil",
            "status": "passed",
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "core_revision": core_revision,
            "board_revision": board_revision,
            "board_target": "nrf54l15dk/nrf54l15/cpuapp/nu54dk",
            "source_digests": source_digests,
            "image": {
                "name": image.name,
                "size": image_size,
                "sha256": image_sha256,
                "build_record": build_record,
            },
            "boards": [asdict(result) for result in results],
            "transcripts": transcripts,
        }
        validate_image_unchanged(image, image_size, image_sha256)
        write_evidence(evidence_path, evidence_temporary, evidence)
    except Exception as error:
        recovery = recover_touched_boards(
            touched=touched,
            image=image,
            serial_module=serial_module,
            list_ports=list_ports,
            baud=args.baud,
            flash_timeout=args.flash_timeout,
            result_timeout=args.result_timeout,
            image_size=image_size,
            image_sha256=image_sha256,
        )
        recovery_text = "; ".join(recovery) if recovery else "접촉 보드 없음"
        raise AC03HilFailure(
            "원래 AC-03 실패를 보존합니다: "
            f"{type(error).__name__}: {error}; 실패 후 복구={recovery_text}"
        ) from error
    print("AC03_TWO_BOARD_HIL_PASS=2")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AC03HilFailure, FileNotFoundError, RuntimeError, ValueError) as error:
        print(f"AC03_TWO_BOARD_HIL_FAIL: {error}", file=sys.stderr)
        raise SystemExit(1) from error
