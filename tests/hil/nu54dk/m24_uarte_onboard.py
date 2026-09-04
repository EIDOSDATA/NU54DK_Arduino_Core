#!/usr/bin/env python3
"""Run the no-extra-wiring M24 UARTE EasyDMA test through DAP VCOM."""

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


INSTANCES = (20, 21, 22, 30)
BOARD = "nrf54l15dk"
QUALIFIERS = "nrf54l15/cpuapp/nu54dk"
BAUD_RATE = 115200
PACKET_SIZE = 32
MAX_COMMAND_OUTPUT = 64 * 1024


class UarteHilFailure(RuntimeError):
    """The exact-input or physical UARTE HIL contract failed."""


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
        raise UarteHilFailure(f"Git identity query failed: {result.stderr.strip()}")
    return result.stdout.strip()


def parse_build_record(path: Path) -> dict[str, str]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 64 * 1024:
        raise UarteHilFailure(f"invalid build record: {path}")
    fields: dict[str, str] = {}
    pattern = re.compile(r"^  ([a-z0-9_]+): '([^']*)'$", re.ASCII)
    for line in path.read_text(encoding="utf-8").splitlines():
        match = pattern.fullmatch(line)
        if match:
            fields[match.group(1)] = match.group(2)
    return fields


def locate_images(
    repository: Path, build_root: Path, instances: Iterable[int]
) -> tuple[str, str, dict[int, dict[str, Any]]]:
    repository = repository.resolve()
    build_root = build_root.resolve()
    if git_output(repository, "status", "--porcelain"):
        raise UarteHilFailure("HIL requires a clean exact source checkout.")
    commit = git_output(repository, "rev-parse", "HEAD")
    board_revision = git_output(
        repository, "rev-parse", "HEAD:board_package/NU54DK_Zephyr_DTS"
    )
    images: dict[int, dict[str, Any]] = {}
    for instance in instances:
        scenario = f"nucode.m24.uarte{instance}_hil"
        candidates = list(
            build_root.glob(
                f"**/{scenario}/m24_uarte_onboard_hil/zephyr/zephyr.hex"
            )
        )
        if len(candidates) != 1:
            raise UarteHilFailure(
                f"{scenario} must have exactly one zephyr.hex: {len(candidates)}"
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
                raise UarteHilFailure(
                    f"{scenario} build record {key} mismatch: "
                    f"expected={expected}, actual={record.get(key)!r}"
                )
        images[instance] = {
            "path": image.resolve(),
            "sha256": sha256_file(image),
            "size": image.stat().st_size,
            "build_record": record_path.resolve(),
            "build_record_sha256": sha256_file(record_path),
            "application_source_sha256": record.get("application_source_sha256", ""),
            "core_source_sha256": record.get("core_source_sha256", ""),
        }
    return commit, board_revision, images


def matching_port_names(port_records: Iterable[Any], probe_id: str) -> list[str]:
    normalized = probe_id.strip().casefold()
    if not normalized:
        raise UarteHilFailure("--probe-id is required.")
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
        raise UarteHilFailure(
            "The selected DAP probe must expose exactly two VCOM ports: "
            f"found={len(devices)}"
        )
    return devices


def pyocd_command(pyocd: Path, probe_id: str, image: Path) -> list[str]:
    return [
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


def flash_image(
    pyocd: Path, probe_id: str, image: Path, timeout_seconds: float
) -> dict[str, Any]:
    if timeout_seconds <= 0:
        raise UarteHilFailure("--flash-timeout must be positive.")
    command = pyocd_command(pyocd, probe_id, image)
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
        raise UarteHilFailure(f"pyOCD flash failed: {error}") from error
    output = result.stdout[-MAX_COMMAND_OUTPUT:].decode("utf-8", "replace")
    if result.returncode != 0:
        raise UarteHilFailure(
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


def choose_unique_response(
    transcripts: dict[str, bytes], expected: bytes
) -> str:
    matches = [device for device, data in transcripts.items() if data == expected]
    if len(matches) != 1:
        sizes = {device: len(data) for device, data in transcripts.items()}
        raise UarteHilFailure(
            "exactly one VCOM must return the reversed packet: "
            f"matches={len(matches)}, received_sizes={sizes}"
        )
    for device, data in transcripts.items():
        if device != matches[0] and data:
            raise UarteHilFailure(
                f"non-selected VCOM returned unexpected bytes: port={device}, size={len(data)}"
            )
    return matches[0]


def ready_frame(instance: int) -> bytes:
    return bytes(0xA0 ^ instance ^ index for index in range(PACKET_SIZE))


def collect_exact_frame(
    streams: dict[str, Any], expected: bytes, timeout_seconds: float
) -> tuple[str, dict[str, bytes]]:
    transcripts = {device: bytearray() for device in streams}
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        for device, stream in streams.items():
            waiting = int(getattr(stream, "in_waiting", 0))
            if waiting:
                transcripts[device].extend(stream.read(waiting))
        if any(len(data) >= len(expected) for data in transcripts.values()):
            time.sleep(0.1)
            for device, stream in streams.items():
                waiting = int(getattr(stream, "in_waiting", 0))
                if waiting:
                    transcripts[device].extend(stream.read(waiting))
            break
        time.sleep(0.01)
    frozen = {device: bytes(data) for device, data in transcripts.items()}
    return choose_unique_response(frozen, expected), frozen


def exercise_instance(
    streams: dict[str, Any], payload: bytes, timeout_seconds: float
) -> tuple[str, dict[str, bytes]]:
    if len(payload) != PACKET_SIZE or timeout_seconds <= 0:
        raise UarteHilFailure("invalid UARTE packet size or timeout.")
    for stream in streams.values():
        if stream.write(payload) != len(payload):
            raise UarteHilFailure("VCOM accepted only part of the test packet.")
        stream.flush()

    expected = payload[::-1]
    transcripts = {device: bytearray() for device in streams}
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        for device, stream in streams.items():
            waiting = int(getattr(stream, "in_waiting", 0))
            if waiting:
                transcripts[device].extend(stream.read(waiting))
                if len(transcripts[device]) > PACKET_SIZE:
                    break
        if any(len(data) > PACKET_SIZE for data in transcripts.values()):
            break
        if any(bytes(data) == expected for data in transcripts.values()):
            time.sleep(0.1)
            for device, stream in streams.items():
                waiting = int(getattr(stream, "in_waiting", 0))
                if waiting:
                    transcripts[device].extend(stream.read(waiting))
            break
        time.sleep(0.01)
    frozen = {device: bytes(data) for device, data in transcripts.items()}
    return choose_unique_response(frozen, expected), frozen


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
        raise UarteHilFailure("pyOCD executable was not found.")
    if args.settle_seconds < 0 or args.response_timeout <= 0:
        raise UarteHilFailure("settle and response timeouts are invalid.")
    commit, board_revision, images = locate_images(
        args.repository, args.build_root, INSTANCES
    )
    try:
        import serial
        from serial.tools import list_ports
    except ImportError as error:
        raise UarteHilFailure("pyserial is required for VCOM HIL.") from error

    port_names = matching_port_names(list_ports.comports(), args.probe_id)
    streams: dict[str, Any] = {}
    results: list[dict[str, Any]] = []
    try:
        for device in port_names:
            streams[device] = serial.Serial(
                port=device,
                baudrate=BAUD_RATE,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=0,
                write_timeout=2.0,
                xonxoff=False,
                rtscts=False,
                dsrdtr=False,
            )
        for sequence, instance in enumerate(INSTANCES, start=1):
            image = images[instance]
            for stream in streams.values():
                stream.reset_input_buffer()
                stream.reset_output_buffer()
            flash = flash_image(args.pyocd, args.probe_id, image["path"], args.flash_timeout)
            from onboard_start import reset_halted_start
            flash["controlled_start"] = reset_halted_start(streams, args.probe_id)
            ready_port, ready_transcripts = collect_exact_frame(
                streams, ready_frame(instance), args.settle_seconds + args.response_timeout
            )
            for stream in streams.values():
                stream.reset_input_buffer()
                stream.reset_output_buffer()
            payload = hashlib.sha256(
                f"M24-UARTE-{instance}-{commit}".encode("ascii")
            ).digest()
            selected, transcripts = exercise_instance(
                streams, payload, args.response_timeout
            )
            if selected != ready_port:
                raise UarteHilFailure(
                    "UARTE READY and data response used different VCOM ports."
                )
            results.append(
                {
                    "sequence": sequence,
                    "instance": instance,
                    "image": {
                        "sha256": image["sha256"],
                        "size": image["size"],
                        "build_record_sha256": image["build_record_sha256"],
                        "application_source_sha256": image[
                            "application_source_sha256"
                        ],
                        "core_source_sha256": image["core_source_sha256"],
                    },
                    "flash": flash,
                    "payload_sha256": hashlib.sha256(payload).hexdigest(),
                    "response_sha256": hashlib.sha256(payload[::-1]).hexdigest(),
                    "selected_vcom_index": port_names.index(selected),
                    "ready_sha256": hashlib.sha256(ready_frame(instance)).hexdigest(),
                    "ready_received_sizes": {
                        str(port_names.index(device)): len(data)
                        for device, data in ready_transcripts.items()
                    },
                    "received_sizes": {
                        str(port_names.index(device)): len(data)
                        for device, data in transcripts.items()
                    },
                    "status": "passed",
                }
            )
            print(f"M24_UARTE_INSTANCE_PASS={instance};VCOM={port_names.index(selected)}")
    finally:
        for stream in streams.values():
            try:
                stream.close()
            except Exception:
                pass

    evidence = {
        "schema_version": 1,
        "milestone": "M24",
        "evidence_type": "onboard-uarte-easydma",
        "status": "passed",
        "core_revision": commit,
        "board_revision": board_revision,
        "probe_id_sha256": hashlib.sha256(args.probe_id.encode("ascii")).hexdigest(),
        "vcom_candidate_count": len(port_names),
        "baud_rate": BAUD_RATE,
        "packet_size": PACKET_SIZE,
        "instances": results,
        "mass_erase_requested": False,
        "recover_requested": False,
        "completed_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    write_evidence(args.evidence, evidence)
    print(f"M24_UARTE_ONBOARD_HIL_PASS=4;EVIDENCE={args.evidence.resolve()}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except UarteHilFailure as error:
        print(f"M24_UARTE_ONBOARD_HIL_FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
