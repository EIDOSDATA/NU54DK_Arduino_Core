#!/usr/bin/env python3
"""! @brief AC-01 P2 loopback과 SW0 자기구동 IRQ를 DAPLink/UART로 검증합니다. """

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from typing import Any, Sequence


HIL_DIRECTORY = Path(__file__).resolve().parent
REPOSITORY = HIL_DIRECTORY.parents[2]
BOARD_ROOT = REPOSITORY / "board_package" / "NU54DK_Zephyr_DTS"
APPLICATION_SOURCE_ROOT = REPOSITORY / "tests" / "zephyr" / "ac01_hil"
CORE_SOURCE_SCOPES = (
    REPOSITORY / "cores" / "arduino",
    REPOSITORY / "dts",
    REPOSITORY / "libraries",
    REPOSITORY / "third_party" / "ArduinoCore-API",
    REPOSITORY / "third_party" / "ArduinoCore-API.provenance.yml",
    REPOSITORY / "variants" / "nu54dk",
    REPOSITORY / "zephyr",
)
BOARD_SOURCE_SCOPE = BOARD_ROOT / "boards" / "nucode" / "nu54dk"
BOARD_SUBMODULE_PATH = "board_package/NU54DK_Zephyr_DTS"
if str(HIL_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(HIL_DIRECTORY))

from m6_serial_echo import (  # noqa: E402
    DEFAULT_BAUD_RATE,
    DaplinkVolume,
    detail_value,
    find_daplink_volume,
    find_serial_port,
    import_pyserial,
    normalize_board_id,
    validate_hex_image,
    wait_for_flash_result,
)


READY_TOKEN = (
    b"NUCODE_AC01_GPIO_HIL_READY:schema=1:gpio0=P2.5:gpio1=P2.6:"
    b"wiring=P2.5_TO_P2.6:irq=SW0_P1.13_SELF_OPEN_DRAIN"
)
OPEN_DRAIN_TOKEN = (
    b"NUCODE_AC01_OPEN_DRAIN:PASS:low=LOW:released=HIGH:"
    b"pullup=PIN_GPIO1_INTERNAL"
)
LOW_LEVEL_TOKEN = b"NUCODE_AC01_LEVEL_LOW:PASS:first=1:held=1:rearmed=2"
HIGH_LEVEL_TOKEN = b"NUCODE_AC01_LEVEL_HIGH:PASS:first=1:held=1:rearmed=2"
SHIFT_TOKEN = (
    b"NUCODE_AC01_SHIFT:PASS:out_msb_last=HIGH:out_lsb_last=LOW:"
    b"in_low=0x00:in_high=0xFF"
)
FINAL_PASS_TOKEN = b"NUCODE_AC01_GPIO_HIL_PASS"
FINAL_FAIL_TOKEN = b"NUCODE_AC01_GPIO_HIL_FAIL:"
PROTOCOL_PREFIX = b"NUCODE_AC01_"
PULSE_PATTERN = re.compile(
    rb"^NUCODE_AC01_PULSE:PASS:short_us=([0-9]+):long_us=([0-9]+):"
    rb"timeout_us=0$"
)
MASK_PATTERN = re.compile(
    rb"^NUCODE_AC01_INTERRUPT_MASK:PASS:masked=0:nested=0:restored=1:"
    rb"heartbeat_delta=([0-9]+)$"
)
REVISION_PATTERN = re.compile(r"^[0-9a-f]{40}$")
MAX_TRANSCRIPT_BYTES = 65536


class Ac01HilFailure(RuntimeError):
    """! @brief AC-01 HIL의 source·장치·protocol 계약 실패를 나타냅니다. """


@dataclass(frozen=True)
class Ac01HilResult:
    """! @brief AC-01 HIL에서 승인한 계측값을 구조화합니다. """

    short_pulse_us: int
    long_pulse_us: int
    heartbeat_delta: int


## @brief 실제 실행과 parser 단위 시험에 사용할 CLI 인자를 생성합니다.
def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "NU54DK AC-01 image를 기록해 P2.5↔P2.6 GPIO loopback과 "
            "SW0 자기구동 level IRQ/callback mask를 검증합니다."
        )
    )
    parser.add_argument("--hex", dest="hex_path")
    parser.add_argument(
        "--board-id",
        required=True,
        help="시험할 CMSIS-DAP V2 UID; 두 보드 오선택을 막기 위해 필수",
    )
    parser.add_argument("--volume")
    parser.add_argument("--port", default="auto")
    parser.add_argument("--baud", type=int, default=DEFAULT_BAUD_RATE)
    parser.add_argument("--flash-timeout", type=float, default=45.0)
    parser.add_argument("--result-timeout", type=float, default=45.0)
    parser.add_argument("--evidence", help="PASS JSON evidence 경로")
    parser.add_argument("--expected-core-revision")
    parser.add_argument(
        "--acknowledge-loopback",
        action="store_true",
        help="같은 보드의 P2.5와 P2.6이 점퍼 한 가닥으로 연결되었음을 명시",
    )
    parser.add_argument("--overwrite-evidence", action="store_true")
    parser.add_argument("--discover-only", action="store_true")
    return parser.parse_args(arguments)


## @brief 파일의 SHA-256을 streaming 방식으로 계산합니다.
def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


## @brief CMake build record와 같은 상대 경로·파일 SHA 목록 digest를 계산합니다.
def files_digest(base_directory: Path, scopes: Sequence[Path]) -> str:
    files: list[Path] = []
    for scope in scopes:
        if scope.is_file():
            files.append(scope)
        elif scope.is_dir():
            files.extend(path for path in scope.rglob("*") if path.is_file())
    files.sort(key=lambda path: path.as_posix())
    if not files:
        raise Ac01HilFailure(f"source digest 입력 파일이 없습니다: {base_directory}")
    payload = "".join(
        f"{path.relative_to(base_directory).as_posix()}:{file_sha256(path)}\n"
        for path in files
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


## @brief 현재 Core·AC-01 application·board tree의 source digest를 계산합니다.
def current_source_digests() -> dict[str, str]:
    return {
        "core_source_sha256": files_digest(REPOSITORY, CORE_SOURCE_SCOPES),
        "application_source_sha256": files_digest(
            APPLICATION_SOURCE_ROOT, (APPLICATION_SOURCE_ROOT,)
        ),
        "board_source_sha256": files_digest(BOARD_ROOT, (BOARD_SOURCE_SCOPE,)),
    }


## @brief 저장소가 기대한 exact commit인지 확인하고 revision을 반환합니다.
def git_revision(repository: Path, expected: str | None = None) -> str:
    completed = subprocess.run(
        ("git", "-C", str(repository), "rev-parse", "HEAD"),
        capture_output=True,
        check=False,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    revision = completed.stdout.strip().lower()
    if completed.returncode != 0 or REVISION_PATTERN.fullmatch(revision) is None:
        raise Ac01HilFailure(f"Git revision을 확인하지 못했습니다: {repository}")
    if expected is not None:
        normalized = expected.strip().lower()
        if REVISION_PATTERN.fullmatch(normalized) is None:
            raise Ac01HilFailure("--expected-core-revision은 40자리 SHA여야 합니다.")
        if revision != normalized:
            raise Ac01HilFailure(
                f"Core revision 불일치: 기대={normalized}, 실제={revision}"
            )
    return revision


## @brief 부모 commit이 고정한 board submodule revision을 반환합니다.
def parent_board_revision() -> str:
    completed = subprocess.run(
        (
            "git",
            "-C",
            str(REPOSITORY),
            "rev-parse",
            f"HEAD:{BOARD_SUBMODULE_PATH}",
        ),
        capture_output=True,
        check=False,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    revision = completed.stdout.strip().lower()
    if completed.returncode != 0 or REVISION_PATTERN.fullmatch(revision) is None:
        raise Ac01HilFailure("부모 commit의 board submodule gitlink를 확인하지 못했습니다.")
    return revision


## @brief HIL 관련 Core source와 board submodule이 clean인지 검사합니다.
def validate_source_clean() -> None:
    core_paths = (
        "cores/arduino",
        "dts",
        "libraries",
        "third_party/ArduinoCore-API",
        "third_party/ArduinoCore-API.provenance.yml",
        "variants/nu54dk",
        "zephyr",
        "tests/zephyr/ac01_hil",
        "tests/hil/nu54dk/ac01_gpio_hil.py",
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
        check=False,
        text=True,
        encoding="utf-8",
        errors="replace",
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
        check=False,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if core.returncode != 0 or core.stdout.strip():
        raise Ac01HilFailure(
            "AC-01 HIL source에 commit되지 않은 변경이 있습니다: "
            f"{core.stdout.strip() or core.stderr.strip()}"
        )
    if board.returncode != 0 or board.stdout.strip():
        raise Ac01HilFailure(
            "board_package submodule이 clean하지 않습니다: "
            f"{board.stdout.strip() or board.stderr.strip()}"
        )


## @brief build record의 quoted scalar 하나를 읽습니다.
def build_record_value(text: str, key: str) -> str:
    match = re.search(rf"^\s*{re.escape(key)}:\s*'([^']+)'\s*$", text, re.MULTILINE)
    if match is None:
        raise Ac01HilFailure(f"NUCODE build record key가 없습니다: {key}")
    return match.group(1)


## @brief HEX build record를 exact revision·source·NCS target에 결합합니다.
def validate_build_record(
    image: Path, core_revision: str, board_revision: str
) -> dict[str, str]:
    record_path = image.parent.parent / "nucode_arduino_core_build.yml"
    try:
        if record_path.stat().st_size > 16384:
            raise Ac01HilFailure("NUCODE build record가 허용 크기를 초과했습니다.")
        text = record_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise Ac01HilFailure(f"build record를 읽지 못했습니다: {record_path}") from error
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
    )
    values = {key: build_record_value(text, key) for key in keys}
    expected = {
        "core_revision": core_revision[:12],
        "board_revision": board_revision[:12],
        "ncs_revision": "99553055607b",
        "zephyr_revision": "bf801e4e3d19",
        "board": "nrf54l15dk",
        "board_qualifiers": "nrf54l15/cpuapp/nu54dk",
    }
    for key, expected_value in expected.items():
        if values[key] != expected_value:
            raise Ac01HilFailure(
                f"build record identity 불일치: {key}={values[key]}, "
                f"expected={expected_value}"
            )
    for key, digest in current_source_digests().items():
        if values[key] != digest:
            raise Ac01HilFailure(
                f"build record exact source 불일치: {key}={values[key]}, expected={digest}"
            )
    values["record_name"] = record_path.name
    values["record_sha256"] = file_sha256(record_path)
    return values


## @brief UART transcript가 exact AC-01 token 순서와 값 범위를 만족하는지 검증합니다.
def parse_transcript(transcript: bytes) -> Ac01HilResult:
    normalized = transcript.replace(b"\r", b"")
    if FINAL_FAIL_TOKEN in normalized:
        raise Ac01HilFailure("target이 AC-01 GPIO HIL 실패를 보고했습니다.")
    protocol_lines = [
        line.strip()
        for line in normalized.splitlines()
        if line.strip().startswith(PROTOCOL_PREFIX)
    ]
    if len(protocol_lines) != 8:
        raise Ac01HilFailure(
            f"AC-01 protocol line 수가 다릅니다: expected=8, actual={len(protocol_lines)}"
        )
    fixed = {
        0: READY_TOKEN,
        1: OPEN_DRAIN_TOKEN,
        2: LOW_LEVEL_TOKEN,
        3: HIGH_LEVEL_TOKEN,
        5: SHIFT_TOKEN,
        7: FINAL_PASS_TOKEN,
    }
    for index, expected in fixed.items():
        if protocol_lines[index] != expected:
            raise Ac01HilFailure(
                f"AC-01 protocol 순서 또는 값이 다릅니다: index={index}, "
                f"actual={protocol_lines[index]!r}"
            )
    pulse = PULSE_PATTERN.fullmatch(protocol_lines[4])
    mask = MASK_PATTERN.fullmatch(protocol_lines[6])
    if pulse is None or mask is None:
        raise Ac01HilFailure("AC-01 pulse 또는 interrupt mask token 형식이 다릅니다.")
    short_us = int(pulse.group(1), 10)
    long_us = int(pulse.group(2), 10)
    heartbeat_delta = int(mask.group(1), 10)
    if not 500 <= short_us <= 8000:
        raise Ac01HilFailure(f"short pulse 범위를 벗어났습니다: {short_us}")
    if not 12000 <= long_us <= 40000:
        raise Ac01HilFailure(f"long pulse 범위를 벗어났습니다: {long_us}")
    if heartbeat_delta <= 0:
        raise Ac01HilFailure("callback mask 중 scheduler heartbeat가 진행되지 않았습니다.")
    return Ac01HilResult(short_us, long_us, heartbeat_delta)


## @brief 최종 PASS 또는 완결된 FAIL line까지 UART transcript를 수집합니다.
def read_transcript(serial_port: Any, timeout_seconds: float) -> bytes:
    if not 1.0 <= timeout_seconds <= 120.0:
        raise Ac01HilFailure("--result-timeout은 1..120초 범위여야 합니다.")
    deadline = time.monotonic() + timeout_seconds
    observed = bytearray()
    while time.monotonic() < deadline:
        waiting = serial_port.in_waiting
        chunk = serial_port.read(waiting if waiting > 0 else 1)
        if chunk:
            observed.extend(chunk)
            normalized = bytes(observed).replace(b"\r", b"")
            lines = normalized.splitlines()
            if FINAL_PASS_TOKEN in lines or any(
                line.startswith(FINAL_FAIL_TOKEN) for line in lines
            ):
                return bytes(observed)
            if len(observed) > MAX_TRANSCRIPT_BYTES:
                raise Ac01HilFailure("AC-01 UART transcript가 허용 크기를 초과했습니다.")
    raise TimeoutError(
        "AC-01 최종 UART token을 찾지 못했습니다: "
        f"observed_tail={bytes(observed[-1024:])!r}"
    )


## @brief AC-01 HEX를 DAPLink MSD에 기록하고 flash 결과를 반환합니다.
def flash_image(
    volume: DaplinkVolume, image: Path, timeout_seconds: float
) -> tuple[str, str]:
    if timeout_seconds <= 0:
        raise Ac01HilFailure("--flash-timeout은 0보다 커야 합니다.")
    previous_sequence = detail_value(volume.details, "Flash Sequence")
    shutil.copyfile(image, volume.root / "NUCODE_AC01_GPIO_HIL.HEX")
    details = wait_for_flash_result(volume.root, previous_sequence, timeout_seconds)
    return (
        detail_value(details, "Flash Sequence") or "unknown",
        detail_value(details, "Last Flash Bytes") or "unknown",
    )


## @brief flash 후 UART protocol을 수집하고 AC-01 결과를 판정합니다.
def verify_hil(
    serial_module: Any,
    port_name: str,
    baud_rate: int,
    flash_callback: Any,
    result_timeout: float,
) -> tuple[str, str, bytes, Ac01HilResult]:
    if baud_rate != DEFAULT_BAUD_RATE:
        raise Ac01HilFailure(f"AC-01은 {DEFAULT_BAUD_RATE} baud만 허용합니다.")
    with serial_module.Serial(
        port=port_name,
        baudrate=baud_rate,
        bytesize=serial_module.EIGHTBITS,
        parity=serial_module.PARITY_NONE,
        stopbits=serial_module.STOPBITS_ONE,
        timeout=0.1,
        write_timeout=2.0,
    ) as serial_port:
        serial_port.reset_input_buffer()
        sequence, byte_count = flash_callback()
        transcript = read_transcript(serial_port, result_timeout)
    return sequence, byte_count, transcript, parse_transcript(transcript)


## @brief evidence와 companion transcript의 안전한 신규 경로를 준비합니다.
def prepare_output_paths(argument: str | None, overwrite: bool) -> tuple[Path, Path]:
    if not argument:
        raise Ac01HilFailure("실제 시험에는 --evidence JSON 경로가 필요합니다.")
    evidence = Path(argument).resolve()
    if evidence.suffix.lower() != ".json":
        raise Ac01HilFailure("--evidence는 .json 확장자여야 합니다.")
    transcript = evidence.with_suffix(".transcript.log")
    for path in (evidence, transcript):
        if path.exists() and not overwrite:
            raise Ac01HilFailure(f"기존 증적을 자동 덮어쓰지 않습니다: {path}")
        if path.exists() and overwrite:
            if not path.is_file():
                raise Ac01HilFailure(f"증적 경로가 일반 파일이 아닙니다: {path}")
            path.unlink()
    evidence.parent.mkdir(parents=True, exist_ok=True)
    return evidence, transcript


## @brief 결과를 exact image·revision·fixture·transcript identity와 결합합니다.
def build_evidence(
    *,
    core_revision: str,
    board_revision: str,
    board_id: str,
    image: Path,
    flash_sequence: str,
    flash_byte_count: str,
    port_name: str,
    transcript_path: Path,
    transcript: bytes,
    result: Ac01HilResult,
    build_record: dict[str, str],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "gate": "ac01-nu54dk-gpio-loopback-hil",
        "status": "passed",
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "core_revision": core_revision,
        "board_revision": board_revision,
        "board_target": "nrf54l15dk/nrf54l15/cpuapp/nu54dk",
        "fixture": {
            "acknowledged": True,
            "board_count_used": 1,
            "wire": "PIN_GPIO0/P2.5 to PIN_GPIO1/P2.6",
            "external_pullup": False,
            "pullup_source": "PIN_GPIO1 internal pull-up",
            "interrupt_pin": "PIN_BUTTON0/P1.13",
            "interrupt_drive": "input-connected open-drain self-drive",
            "interrupt_manual_press_required": False,
        },
        "probe": {"type": "CMSIS-DAP-v2", "uid": board_id},
        "serial": {"port": port_name, "baud": DEFAULT_BAUD_RATE},
        "flash": {
            "transport": "DAPLink-MSD",
            "mass_erase_requested": False,
            "recover_requested": False,
            "sequence": flash_sequence,
            "byte_count": flash_byte_count,
        },
        "image": {
            "name": image.name,
            "size": image.stat().st_size,
            "sha256": file_sha256(image),
        },
        "build_record": build_record,
        "result": asdict(result),
        "transcript": {
            "name": transcript_path.name,
            "size": len(transcript),
            "sha256": hashlib.sha256(transcript).hexdigest(),
        },
    }


## @brief 장치 탐색 또는 전체 AC-01 loopback HIL과 evidence 생성을 수행합니다.
def main(arguments: Sequence[str] | None = None) -> int:
    args = parse_arguments(arguments)
    board_id = normalize_board_id(args.board_id)
    volume = find_daplink_volume(board_id, args.volume)
    serial_module, list_ports = import_pyserial()
    port_name = find_serial_port(board_id, args.port, list_ports)
    print(
        "NU54DK discovery SUCCESS: "
        f"uid={board_id}, volume={volume.root}, port={port_name}, baud={args.baud}"
    )
    if args.discover_only:
        return 0
    if not args.acknowledge_loopback:
        raise Ac01HilFailure(
            "실제 시험은 같은 보드 P2.5↔P2.6 연결과 --acknowledge-loopback이 필요합니다."
        )

    evidence_path, transcript_path = prepare_output_paths(
        args.evidence, args.overwrite_evidence
    )
    image = validate_hex_image(args.hex_path)
    core_revision = git_revision(REPOSITORY, args.expected_core_revision)
    board_revision = git_revision(BOARD_ROOT)
    expected_board_revision = parent_board_revision()
    if board_revision != expected_board_revision:
        raise Ac01HilFailure(
            "board checkout과 부모 gitlink가 다릅니다: "
            f"expected={expected_board_revision}, actual={board_revision}"
        )
    validate_source_clean()
    build_record = validate_build_record(image, core_revision, board_revision)

    sequence, byte_count, transcript, result = verify_hil(
        serial_module,
        port_name,
        args.baud,
        lambda: flash_image(volume, image, args.flash_timeout),
        args.result_timeout,
    )
    transcript_path.write_bytes(transcript)
    evidence = build_evidence(
        core_revision=core_revision,
        board_revision=board_revision,
        board_id=board_id,
        image=image,
        flash_sequence=sequence,
        flash_byte_count=byte_count,
        port_name=port_name,
        transcript_path=transcript_path,
        transcript=transcript,
        result=result,
        build_record=build_record,
    )
    evidence_path.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        "AC-01 GPIO HIL PASS: "
        f"short_us={result.short_pulse_us}, long_us={result.long_pulse_us}, "
        f"heartbeat_delta={result.heartbeat_delta}, evidence={evidence_path}"
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print(f"AC-01 GPIO HIL FAIL: {error}", file=sys.stderr)
        sys.exit(1)
