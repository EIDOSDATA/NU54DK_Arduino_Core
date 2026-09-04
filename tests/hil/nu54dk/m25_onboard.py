#!/usr/bin/env python3
"""Run the no-extra-wiring M25 event/SAADC test through DAP VCOM."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from typing import Any, Iterable, Sequence


BOARD = "nrf54l15dk"
QUALIFIERS = "nrf54l15/cpuapp/nu54dk"
SCENARIO = "nucode.m25.onboard_hil"
BAUD_RATE = 115200
PACKET_SIZE = 32
MAX_COMMAND_OUTPUT = 64 * 1024


class M25HilFailure(RuntimeError):
    """The exact-input or physical M25 onboard HIL contract failed."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def git_output(repository: Path, *arguments: str) -> str:
    result = subprocess.run(
        ("git", "-C", str(repository), *arguments),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        raise M25HilFailure(f"Git identity query failed: {result.stderr.strip()}")
    return result.stdout.strip()


def parse_build_record(path: Path) -> dict[str, str]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 64 * 1024:
        raise M25HilFailure(f"invalid build record: {path}")
    fields: dict[str, str] = {}
    pattern = re.compile(r"^  ([a-z0-9_]+): '([^']*)'$", re.ASCII)
    for line in path.read_text(encoding="utf-8").splitlines():
        match = pattern.fullmatch(line)
        if match:
            fields[match.group(1)] = match.group(2)
    return fields


def locate_image(repository: Path, build_root: Path) -> tuple[str, str, dict[str, Any]]:
    repository = repository.resolve()
    build_root = build_root.resolve()
    if git_output(repository, "status", "--porcelain"):
        raise M25HilFailure("HIL requires a clean exact source checkout.")
    commit = git_output(repository, "rev-parse", "HEAD")
    board_revision = git_output(
        repository, "rev-parse", "HEAD:board_package/NU54DK_Zephyr_DTS"
    )
    candidates = list(
        build_root.glob(f"**/{SCENARIO}/m25_onboard_hil/zephyr/zephyr.hex")
    )
    if len(candidates) != 1:
        raise M25HilFailure(
            f"{SCENARIO} must have exactly one zephyr.hex: {len(candidates)}"
        )
    image = candidates[0]
    record_path = image.parents[1] / "nucode_arduino_core_build.yml"
    record = parse_build_record(record_path)
    required = {
        "core_revision": commit[:12],
        "board_revision": board_revision[:12],
        "board": BOARD,
        "board_qualifiers": QUALIFIERS,
    }
    for key, expected in required.items():
        if record.get(key) != expected:
            raise M25HilFailure(
                f"build record {key} mismatch: expected={expected}, "
                f"actual={record.get(key)!r}"
            )
    return commit, board_revision, {
        "path": image.resolve(),
        "sha256": sha256_file(image),
        "size": image.stat().st_size,
        "build_record_sha256": sha256_file(record_path),
        "application_source_sha256": record.get("application_source_sha256", ""),
        "core_source_sha256": record.get("core_source_sha256", ""),
    }


def matching_port_names(port_records: Iterable[Any], probe_id: str) -> list[str]:
    normalized = probe_id.strip().casefold()
    devices = sorted(
        {
            str(port.device)
            for port in port_records
            if str(getattr(port, "serial_number", "") or "").strip().casefold()
            == normalized
        },
        key=str.casefold,
    )
    if len(devices) != 2:
        raise M25HilFailure(
            "The selected DAP probe must expose exactly two VCOM ports: "
            f"found={len(devices)}"
        )
    return devices


def ready_frame() -> bytes:
    return bytes(0xE5 ^ index for index in range(PACKET_SIZE))


def command_frame() -> bytes:
    return bytes(0x25 ^ index for index in range(PACKET_SIZE))


def validate_result_frame(frame: bytes) -> dict[str, int]:
    if len(frame) != PACKET_SIZE:
        raise M25HilFailure(f"M25 result size mismatch: {len(frame)}")
    checksum = 0
    for value in frame[:-1]:
        checksum ^= value
    if frame[:4] != b"NU25" or frame[-1] != checksum:
        raise M25HilFailure("M25 result magic or checksum mismatch.")
    version, event_pass, analog_pass, all_pass = frame[4:8]
    ticks = int.from_bytes(frame[8:12], "little")
    sample = int.from_bytes(frame[12:14], "little", signed=True)
    stream_linked = frame[14]
    if (
        version != 1
        or event_pass != 1
        or analog_pass != 1
        or all_pass != 1
        or not 1000 <= ticks <= 100000
        or sample <= 0
        or stream_linked != 1
    ):
        raise M25HilFailure(
            "M25 onboard result mismatch: "
            f"version={version}, event={event_pass}, analog={analog_pass}, "
            f"stream={stream_linked}, all={all_pass}, ticks={ticks}, sample={sample}"
        )
    return {
        "timer_ticks": ticks,
        "vdd_raw": sample,
        "stream_linked": stream_linked,
    }


def choose_exact_port(transcripts: dict[str, bytes], expected: bytes) -> str:
    matches = [device for device, data in transcripts.items() if data == expected]
    if len(matches) != 1:
        raise M25HilFailure(
            "exactly one VCOM must return the expected frame: "
            f"matches={len(matches)}, sizes="
            f"{ {device: len(data) for device, data in transcripts.items()} }"
        )
    if any(data for device, data in transcripts.items() if device != matches[0]):
        raise M25HilFailure("non-selected VCOM returned unexpected bytes.")
    return matches[0]


def collect_frame(
    streams: dict[str, Any], expected: bytes | None, timeout_seconds: float
) -> tuple[str, dict[str, bytes]]:
    transcripts = {device: bytearray() for device in streams}
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        for device, stream in streams.items():
            waiting = int(getattr(stream, "in_waiting", 0))
            if waiting:
                transcripts[device].extend(stream.read(waiting))
        if expected is not None and any(
            bytes(data) == expected for data in transcripts.values()
        ):
            break
        if expected is None and any(len(data) >= PACKET_SIZE for data in transcripts.values()):
            break
        if any(len(data) > PACKET_SIZE for data in transcripts.values()):
            break
        time.sleep(0.01)
    if any(len(data) >= PACKET_SIZE for data in transcripts.values()):
        time.sleep(0.05)
        for device, stream in streams.items():
            waiting = int(getattr(stream, "in_waiting", 0))
            if waiting:
                transcripts[device].extend(stream.read(waiting))
    frozen = {device: bytes(data) for device, data in transcripts.items()}
    if expected is not None:
        return choose_exact_port(frozen, expected), frozen
    candidates = [device for device, data in frozen.items() if len(data) == PACKET_SIZE]
    if len(candidates) != 1:
        raise M25HilFailure(
            f"exactly one VCOM must return a 32-byte result: candidates={candidates}; "
            f"sizes={ {device: len(data) for device, data in frozen.items()} }"
        )
    if any(data for device, data in frozen.items() if device != candidates[0]):
        raise M25HilFailure("non-selected VCOM returned unexpected result bytes.")
    return candidates[0], frozen


def flash_image(
    pyocd: Path, probe_id: str, image: Path, timeout_seconds: float
) -> dict[str, Any]:
    command = [
        str(pyocd),
        "load",
        "--no-config",
        "-O",
        "auto_unlock=false",
        "--erase",
        "sector",
        "--target",
        "nrf54l",
        "--uid",
        probe_id,
        "--frequency",
        "1m",
        str(image),
    ]
    started = time.monotonic()
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout_seconds,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise M25HilFailure(f"pyOCD flash failed: {error}") from error
    if result.returncode != 0:
        output = result.stdout[-MAX_COMMAND_OUTPUT:].decode("utf-8", "replace")
        raise M25HilFailure(
            f"pyOCD exited with {result.returncode}: {output[-2048:]}"
        )
    return {
        "runner": "pyocd",
        "target": "nrf54l",
        "seconds": round(time.monotonic() - started, 3),
        "mass_erase_requested": False,
        "recover_requested": False,
        "output_sha256": hashlib.sha256(result.stdout).hexdigest(),
    }


def write_evidence(path: Path, payload: dict[str, Any]) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    repository = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, default=repository)
    parser.add_argument("--build-root", type=Path, required=True)
    parser.add_argument("--probe-id", required=True)
    parser.add_argument("--pyocd", type=Path, default=Path(shutil.which("pyocd") or ""))
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--flash-timeout", type=float, default=120.0)
    parser.add_argument("--settle-seconds", type=float, default=1.5)
    parser.add_argument("--response-timeout", type=float, default=3.0)
    return parser.parse_args(arguments)


def main(arguments: Sequence[str] | None = None) -> int:
    args = parse_arguments(arguments)
    if not args.pyocd.is_file():
        raise M25HilFailure("pyOCD executable was not found.")
    commit, board_revision, image = locate_image(args.repository, args.build_root)
    try:
        import serial
        from serial.tools import list_ports
    except ImportError as error:
        raise M25HilFailure("pyserial is required for VCOM HIL.") from error

    port_names = matching_port_names(list_ports.comports(), args.probe_id)
    streams: dict[str, Any] = {}
    try:
        for device in port_names:
            streams[device] = serial.Serial(
                port=device,
                baudrate=BAUD_RATE,
                timeout=0,
                write_timeout=2.0,
                xonxoff=False,
                rtscts=False,
                dsrdtr=False,
            )
        for stream in streams.values():
            stream.reset_input_buffer()
            stream.reset_output_buffer()
        flash = flash_image(args.pyocd, args.probe_id, image["path"], args.flash_timeout)
        ready_port, ready_transcripts = collect_frame(
            streams, ready_frame(), args.settle_seconds + args.response_timeout
        )
        for stream in streams.values():
            stream.reset_input_buffer()
            stream.reset_output_buffer()
            if stream.write(command_frame()) != PACKET_SIZE:
                raise M25HilFailure("VCOM accepted only part of the command frame.")
            stream.flush()
        result_port, transcripts = collect_frame(streams, None, args.response_timeout)
        if result_port != ready_port:
            raise M25HilFailure("M25 READY and result used different VCOM ports.")
        result = validate_result_frame(transcripts[result_port])
    finally:
        for stream in streams.values():
            try:
                stream.close()
            except Exception:
                pass

    evidence = {
        "schema_version": 1,
        "milestone": "M25",
        "evidence_type": "onboard-egu-dppi-timer-and-internal-vdd-saadc",
        "status": "passed",
        "core_revision": commit,
        "board_revision": board_revision,
        "probe_id_sha256": hashlib.sha256(args.probe_id.encode("ascii")).hexdigest(),
        "vcom_candidate_count": len(port_names),
        "baud_rate": BAUD_RATE,
        "image_sha256": image["sha256"],
        "image_size": image["size"],
        "build_record_sha256": image["build_record_sha256"],
        "application_source_sha256": image["application_source_sha256"],
        "core_source_sha256": image["core_source_sha256"],
        "flash": flash,
        "selected_vcom_index": port_names.index(result_port),
        "ready_received_sizes": {
            str(port_names.index(device)): len(data)
            for device, data in ready_transcripts.items()
        },
        "result_received_sizes": {
            str(port_names.index(device)): len(data)
            for device, data in transcripts.items()
        },
        **result,
        "mass_erase_requested": False,
        "recover_requested": False,
        "completed_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    write_evidence(args.evidence, evidence)
    print(
        f"M25_ONBOARD_HIL_PASS=1;TICKS={result['timer_ticks']};"
        f"VDD_RAW={result['vdd_raw']};EVIDENCE={args.evidence.resolve()}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except M25HilFailure as error:
        print(f"M25_ONBOARD_HIL_FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
