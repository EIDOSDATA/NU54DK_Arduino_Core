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
import sys
import time
from typing import Any, Sequence


HIL_DIRECTORY = Path(__file__).resolve().parent
if str(HIL_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(HIL_DIRECTORY))

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
    parser.add_argument("--evidence")
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


def _protocol_lines(transcript: bytes) -> list[bytes]:
    """! @brief raw UART에서 AC-03 protocol line만 순서대로 반환합니다. """

    return [
        line.strip()
        for line in transcript.replace(b"\r", b"").split(b"\n")
        if line.strip().startswith(PREFIX)
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
            if FAIL_PREFIX in transcript:
                raise AC03HilFailure("target FAIL token이 있습니다.")
            if not clear_sent and BOOT_PATTERN.search(transcript.replace(b"\r", b"")):
                _write_command(serial_port, CLEAR_COMMAND)
                clear_sent = True
                continue
            if clear_sent and not cleared and b"NUCODE_AC03_CLEARED:PASS" in transcript:
                cleared = True
            if cleared and not start_sent:
                idle = b"NUCODE_AC03_BOOT:schema=1:stage=idle:nonce=none"
                cleared_index = transcript.rfind(b"NUCODE_AC03_CLEARED:PASS")
                if transcript.find(idle, cleared_index) >= 0:
                    _write_command(serial_port, START_COMMAND + nonce_bytes + b"\r\n")
                    start_sent = True
                    continue
            for stage, prerequisite in (
                (b"verify_persistence", SEED_TOKEN),
                (b"verify_corruption", CORRUPTION_TOKEN),
                (b"verify_recovery", RECOVERY_TOKEN),
            ):
                if stage in continued or prerequisite not in transcript:
                    continue
                boot = (
                    b"NUCODE_AC03_BOOT:schema=1:stage="
                    + stage
                    + b":nonce="
                    + nonce_bytes
                )
                if boot in transcript:
                    _write_command(
                        serial_port, CONTINUE_COMMAND + nonce_bytes + b"\r\n"
                    )
                    continued.add(stage)
                    break
            final = b"NUCODE_AC03_FINAL:PASS:nonce=" + nonce_bytes
            if final in transcript:
                parse_transcript(transcript, nonce)
                return transcript
    raise AC03HilFailure(
        f"AC-03 최종 PASS를 {timeout_seconds:.1f}초 안에 받지 못했습니다."
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


def main(arguments: Sequence[str] | None = None) -> int:
    """! @brief 두 보드 실행 결과가 모두 PASS일 때만 evidence를 기록합니다. """

    args = parse_arguments(arguments)
    board_ids = [normalize_board_id(value) for value in args.board_id]
    if len(board_ids) != 2 or len(set(board_ids)) != 2:
        raise AC03HilFailure("서로 다른 --board-id를 정확히 두 번 지정해야 합니다.")
    if len(args.port) > 2 or len(args.volume) > 2:
        raise AC03HilFailure("--port와 --volume은 보드 순서대로 최대 두 번 지정합니다.")
    serial_module, list_ports = import_pyserial()
    ports = list(args.port) + ["auto"] * (2 - len(args.port))
    volumes = list(args.volume) + [None] * (2 - len(args.volume))
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
    image = validate_hex_image(args.hex_path)
    results: list[BoardResult] = []
    transcripts: dict[str, str] = {}
    for board_id, port, volume in zip(board_ids, ports, volumes):
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
        results.append(result)
        transcripts[board_id] = transcript.decode("ascii", errors="replace")
        print(f"AC03_BOARD_PASS={board_id};PORT={result.port};RESETS=3")
    evidence = {
        "schema_version": 1,
        "gate": "ac03-two-board-storage-hil",
        "status": "passed",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "image": {"path": image.as_posix(), "sha256": file_sha256(image)},
        "boards": [asdict(result) for result in results],
        "transcripts": transcripts,
    }
    if args.evidence:
        evidence_path = Path(args.evidence).resolve()
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        if evidence_path.exists():
            raise AC03HilFailure(f"기존 evidence를 덮어쓰지 않습니다: {evidence_path}")
        evidence_path.write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    print("AC03_TWO_BOARD_HIL_PASS=2")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AC03HilFailure, FileNotFoundError, RuntimeError, ValueError) as error:
        print(f"AC03_TWO_BOARD_HIL_FAIL: {error}", file=sys.stderr)
        raise SystemExit(1) from error
