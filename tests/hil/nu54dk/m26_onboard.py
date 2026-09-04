#!/usr/bin/env python3
"""Run the no-extra-wiring M26 TEMP and WDT30 reset HIL through DAP VCOM."""

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
SCENARIO = "nucode.m26.onboard_hil"
BAUD_RATE = 115200
PACKET_SIZE = 32
# Zephyr include/zephyr/drivers/hwinfo.h: RESET_WATCHDOG = BIT(4).
RESET_WATCHDOG = 1 << 4
MAX_RESET_PREFIX = 64
FRAME_QUIET_SECONDS = 0.05
MAX_COMMAND_OUTPUT = 64 * 1024


class M26HilFailure(RuntimeError):
    """The exact-input or physical M26 onboard HIL contract failed."""


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
        raise M26HilFailure(f"Git identity query failed: {result.stderr.strip()}")
    return result.stdout.strip()


def parse_build_record(path: Path) -> dict[str, str]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 64 * 1024:
        raise M26HilFailure(f"invalid build record: {path}")
    fields: dict[str, str] = {}
    pattern = re.compile(r"^  ([a-z0-9_]+): '([^']*)'$", re.ASCII)
    for line in path.read_text(encoding="utf-8").splitlines():
        match = pattern.fullmatch(line)
        if match:
            fields[match.group(1)] = match.group(2)
    return fields


def locate_image(
    repository: Path, build_root: Path
) -> tuple[str, str, dict[str, Any]]:
    repository = repository.resolve()
    build_root = build_root.resolve()
    if git_output(repository, "status", "--porcelain"):
        raise M26HilFailure("HIL requires a clean exact source checkout.")
    commit = git_output(repository, "rev-parse", "HEAD")
    board_revision = git_output(
        repository, "rev-parse", "HEAD:board_package/NU54DK_Zephyr_DTS"
    )
    candidates = list(
        build_root.glob(f"**/{SCENARIO}/m26_onboard_hil/zephyr/zephyr.hex")
    )
    if len(candidates) != 1:
        raise M26HilFailure(
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
            raise M26HilFailure(
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
        raise M26HilFailure(
            "The selected DAP probe must expose exactly two VCOM ports: "
            f"found={len(devices)}"
        )
    return devices


def ready_frame() -> bytes:
    return bytes(0xE6 ^ index for index in range(PACKET_SIZE))


def command_frame() -> bytes:
    return bytes(0x26 ^ index for index in range(PACKET_SIZE))


def reset_ready_frame() -> bytes:
    return bytes(0x96 ^ index for index in range(PACKET_SIZE))


def result_request_frame() -> bytes:
    return bytes(0x76 ^ index for index in range(PACKET_SIZE))


def validate_reset_ready(transcripts: dict[str, bytes], selected_port: str) -> bytes:
    """Resynchronize only the expected reset boundary, retaining all prefix bytes."""
    if selected_port not in transcripts:
        raise M26HilFailure("M26 reset READY port is absent.")
    if any(data for port, data in transcripts.items() if port != selected_port):
        raise M26HilFailure("non-selected VCOM returned reset-boundary bytes.")
    data = transcripts[selected_port]
    marker = reset_ready_frame()
    offset = data.find(marker)
    if offset < 0 or offset > MAX_RESET_PREFIX or data[offset:] != marker:
        raise M26HilFailure("invalid M26 reset READY boundary or trailing bytes.")
    return data[:offset]


def collect_reset_ready(
    streams: dict[str, Any], selected_port: str, timeout_seconds: float
) -> tuple[bytes, dict[str, bytes]]:
    transcripts = {port: bytearray() for port in streams}
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        for port, stream in streams.items():
            waiting = int(getattr(stream, "in_waiting", 0))
            if waiting:
                transcripts[port].extend(stream.read(min(waiting, MAX_RESET_PREFIX + PACKET_SIZE + 1)))
        if any(data for port, data in transcripts.items() if port != selected_port):
            break
        if len(transcripts[selected_port]) > MAX_RESET_PREFIX + PACKET_SIZE:
            break
        if reset_ready_frame() in transcripts[selected_port]:
            time.sleep(FRAME_QUIET_SECONDS)
            for port, stream in streams.items():
                waiting = int(getattr(stream, "in_waiting", 0))
                if waiting:
                    transcripts[port].extend(stream.read(min(waiting, MAX_RESET_PREFIX + PACKET_SIZE + 1)))
            break
        time.sleep(0.005)
    frozen = {port: bytes(data) for port, data in transcripts.items()}
    return validate_reset_ready(frozen, selected_port), frozen


def _validate_checksum(frame: bytes, phase: str) -> None:
    if len(frame) != PACKET_SIZE:
        raise M26HilFailure(f"M26 {phase} size mismatch: {len(frame)}")
    checksum = 0
    for value in frame[:-1]:
        checksum ^= value
    if frame[-1] != checksum:
        raise M26HilFailure(f"M26 {phase} checksum mismatch.")


def validate_armed_frame(frame: bytes) -> dict[str, int]:
    _validate_checksum(frame, "armed")
    if frame[:4] != b"AR26":
        raise M26HilFailure("M26 armed magic mismatch.")
    version, temperature_pass, configured, started, fed = frame[4:9]
    temperature = int.from_bytes(frame[9:13], "little", signed=True)
    driver_error = int.from_bytes(frame[13:17], "little", signed=True)
    instance = frame[17]
    if (
        version != 1
        or temperature_pass != 1
        or configured != 1
        or started != 1
        or fed != 1
        or not -4000 <= temperature <= 12500
        or driver_error != 0
        or instance != 30
    ):
        raise M26HilFailure(
            "M26 arm result mismatch: "
            f"version={version}, temp_pass={temperature_pass}, "
            f"configured={configured}, started={started}, fed={fed}, "
            f"temperature={temperature}, driver_error={driver_error}, "
            f"instance={instance}"
        )
    return {"temperature_centi_celsius": temperature, "watchdog_instance": instance}


def validate_result_frame(frame: bytes) -> dict[str, int]:
    _validate_checksum(frame, "result")
    if frame[:4] != b"NU26":
        raise M26HilFailure("M26 result magic mismatch.")
    version, temperature_pass, reset_pass, all_pass = frame[4:8]
    temperature = int.from_bytes(frame[8:12], "little", signed=True)
    reset_cause = int.from_bytes(frame[12:16], "little")
    supported_cause = int.from_bytes(frame[16:20], "little")
    instance, retained_pass = frame[20:22]
    if (
        version != 1
        or temperature_pass != 1
        or reset_pass != 1
        or all_pass != 1
        or not -4000 <= temperature <= 12500
        or (reset_cause & RESET_WATCHDOG) == 0
        or (reset_cause & ~supported_cause) != 0
        or instance != 30
        or retained_pass != 1
    ):
        raise M26HilFailure(
            "M26 reset result mismatch: "
            f"version={version}, temp_pass={temperature_pass}, reset={reset_pass}, "
            f"all={all_pass}, temperature={temperature}, cause={reset_cause}, "
            f"supported={supported_cause}, instance={instance}, "
            f"retained={retained_pass}"
        )
    return {
        "temperature_centi_celsius": temperature,
        "watchdog_instance": instance,
        "reset_cause": reset_cause,
        "supported_reset_cause": supported_cause,
    }


def choose_exact_frame(transcripts: dict[str, bytes], expected: bytes) -> str:
    matches = [device for device, data in transcripts.items() if data == expected]
    if len(matches) != 1:
        raise M26HilFailure(
            "exactly one VCOM must return the expected frame: "
            f"matches={len(matches)}, sizes="
            f"{ {device: len(data) for device, data in transcripts.items()} }"
        )
    if any(data for device, data in transcripts.items() if device != matches[0]):
        raise M26HilFailure("non-selected VCOM returned unexpected bytes.")
    return matches[0]


def collect_packet(
    streams: dict[str, Any], timeout_seconds: float
) -> tuple[str, dict[str, bytes]]:
    transcripts = {device: bytearray() for device in streams}
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        for device, stream in streams.items():
            waiting = int(getattr(stream, "in_waiting", 0))
            if waiting:
                transcripts[device].extend(stream.read(waiting))
        if any(len(data) >= PACKET_SIZE for data in transcripts.values()):
            # Serial reads can split or coalesce USB packets. Reject late extras.
            time.sleep(FRAME_QUIET_SECONDS)
            for device, stream in streams.items():
                waiting = int(getattr(stream, "in_waiting", 0))
                if waiting:
                    transcripts[device].extend(stream.read(waiting))
            break
        time.sleep(0.01)
    frozen = {device: bytes(data) for device, data in transcripts.items()}
    candidates = [device for device, data in frozen.items() if len(data) == PACKET_SIZE]
    if len(candidates) != 1:
        raise M26HilFailure(
            "exactly one VCOM must return one packet: "
            f"candidates={candidates}, sizes="
            f"{ {device: len(data) for device, data in frozen.items()} }"
        )
    if any(data for device, data in frozen.items() if device != candidates[0]):
        raise M26HilFailure("non-selected VCOM returned unexpected packet bytes.")
    return candidates[0], frozen


def flash_image(
    pyocd: Path, probe_id: str, image: Path, timeout_seconds: float
) -> dict[str, Any]:
    command = [
        str(pyocd),
        "load",
        "--no-config",
        "--no-reset",
        "-O",
        "resume_on_disconnect=false",
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
        raise M26HilFailure(f"pyOCD flash failed: {error}") from error
    if result.returncode != 0:
        output = result.stdout[-MAX_COMMAND_OUTPUT:].decode("utf-8", "replace")
        raise M26HilFailure(
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
    parser.add_argument("--reset-timeout", type=float, default=8.0)
    return parser.parse_args(arguments)


def main(arguments: Sequence[str] | None = None) -> int:
    args = parse_arguments(arguments)
    if not args.pyocd.is_file():
        raise M26HilFailure("pyOCD executable was not found.")
    if (args.flash_timeout <= 0 or args.settle_seconds < 0 or
            args.response_timeout <= 0 or args.reset_timeout <= 1.0):
        raise M26HilFailure("M26 settle/response/reset timeouts are invalid.")
    commit, board_revision, image = locate_image(args.repository, args.build_root)
    try:
        import serial
        from serial.tools import list_ports
    except ImportError as error:
        raise M26HilFailure("pyserial is required for VCOM HIL.") from error

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
        from onboard_start import reset_halted_start
        flash["controlled_start"] = reset_halted_start(streams, args.probe_id)
        time.sleep(args.settle_seconds)
        ready_port, ready_transcripts = collect_packet(streams, args.response_timeout)
        choose_exact_frame(ready_transcripts, ready_frame())
        for stream in streams.values():
            stream.reset_input_buffer()
            stream.reset_output_buffer()
            if stream.write(command_frame()) != PACKET_SIZE:
                raise M26HilFailure("VCOM accepted only part of the command frame.")
            stream.flush()
        armed_port, armed_transcripts = collect_packet(streams, args.response_timeout)
        if armed_port != ready_port:
            raise M26HilFailure("M26 READY and armed frames used different VCOM ports.")
        armed = validate_armed_frame(armed_transcripts[armed_port])
        reset_wait_started = time.monotonic()
        reset_prefix, reset_transcripts = collect_reset_ready(
            streams, ready_port, args.reset_timeout
        )
        reset_ready_seconds = time.monotonic() - reset_wait_started
        if not 1.0 <= reset_ready_seconds <= args.reset_timeout:
            raise M26HilFailure("M26 watchdog reset READY arrived outside the expected interval.")
        if streams[ready_port].write(result_request_frame()) != PACKET_SIZE:
            raise M26HilFailure("VCOM accepted only part of the result request.")
        streams[ready_port].flush()
        result_port, result_transcripts = collect_packet(streams, args.response_timeout)
        if result_port != ready_port:
            raise M26HilFailure("M26 reset result used a different VCOM port.")
        result = validate_result_frame(result_transcripts[result_port])
        if result["temperature_centi_celsius"] != armed["temperature_centi_celsius"]:
            raise M26HilFailure("retained TEMP value changed across watchdog reset.")
    finally:
        for stream in streams.values():
            try:
                stream.close()
            except Exception:
                pass

    evidence = {
        "schema_version": 2,
        "protocol_version": 2,
        "milestone": "M26",
        "evidence_type": "onboard-temp-and-wdt30-reset",
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
        "armed_received_sizes": {
            str(port_names.index(device)): len(data)
            for device, data in armed_transcripts.items()
        },
        "result_received_sizes": {
            str(port_names.index(device)): len(data)
            for device, data in result_transcripts.items()
        },
        "reset_ready_seconds": round(reset_ready_seconds, 3),
        "reset_prefix_hex": reset_prefix.hex(),
        "reset_prefix_size": len(reset_prefix),
        "reset_ready_received_sizes": {
            str(port_names.index(device)): len(data)
            for device, data in reset_transcripts.items()
        },
        **result,
        "mass_erase_requested": False,
        "recover_requested": False,
        "completed_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    write_evidence(args.evidence, evidence)
    print(
        "M26_ONBOARD_HIL_PASS=1;"
        f"TEMP_CENTI_C={result['temperature_centi_celsius']};"
        f"WDT={result['watchdog_instance']};EVIDENCE={args.evidence.resolve()}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except M26HilFailure as error:
        print(f"M26_ONBOARD_HIL_FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
