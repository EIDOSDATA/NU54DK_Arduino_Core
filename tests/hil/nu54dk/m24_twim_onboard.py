#!/usr/bin/env python3
"""Run M24 TWIM20/21/22 read-only BQ25186 tests through DAP VCOM."""

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


INSTANCES = (20, 21, 22)
BOARD = "nrf54l15dk"
QUALIFIERS = "nrf54l15/cpuapp/nu54dk"
BAUD_RATE = 115200
PACKET_SIZE = 32
PMIC_ADDRESS = 0x6A
MASK_ID_REGISTER = 0x0C
EXPECTED_MASK_ID = 0x41
MAX_COMMAND_OUTPUT = 64 * 1024


class TwimHilFailure(RuntimeError):
    """The exact-input or physical TWIM HIL contract failed."""


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
        raise TwimHilFailure(f"Git identity query failed: {result.stderr.strip()}")
    return result.stdout.strip()


def parse_build_record(path: Path) -> dict[str, str]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 64 * 1024:
        raise TwimHilFailure(f"invalid build record: {path}")
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
        raise TwimHilFailure("HIL requires a clean exact source checkout.")
    commit = git_output(repository, "rev-parse", "HEAD")
    board_revision = git_output(
        repository, "rev-parse", "HEAD:board_package/NU54DK_Zephyr_DTS"
    )
    images: dict[int, dict[str, Any]] = {}
    for instance in instances:
        scenario = f"nucode.m24.twim{instance}_hil"
        candidates = list(
            build_root.glob(f"**/{scenario}/m24_twim_onboard_hil/zephyr/zephyr.hex")
        )
        if len(candidates) != 1:
            raise TwimHilFailure(
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
                raise TwimHilFailure(
                    f"{scenario} build record {key} mismatch: "
                    f"expected={expected}, actual={record.get(key)!r}"
                )
        images[instance] = {
            "path": image.resolve(),
            "sha256": sha256_file(image),
            "size": image.stat().st_size,
            "build_record_sha256": sha256_file(record_path),
            "application_source_sha256": record.get("application_source_sha256", ""),
            "core_source_sha256": record.get("core_source_sha256", ""),
        }
    return commit, board_revision, images


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
        raise TwimHilFailure(
            "The selected DAP probe must expose exactly two VCOM ports: "
            f"found={len(devices)}"
        )
    return devices


def ready_frame(instance: int) -> bytes:
    return bytes(0xD0 ^ instance ^ index for index in range(PACKET_SIZE))


def command_frame(instance: int) -> bytes:
    return bytes(0x5A ^ instance ^ index for index in range(PACKET_SIZE))


def validate_result_frame(frame: bytes, instance: int) -> dict[str, int]:
    if len(frame) != PACKET_SIZE:
        raise TwimHilFailure(f"TWIM result size mismatch: {len(frame)}")
    checksum = 0
    for value in frame[:-1]:
        checksum ^= value
    if frame[:4] != b"NUTW" or frame[-1] != checksum:
        raise TwimHilFailure("TWIM result magic or checksum mismatch.")
    expected = (instance, 0, PMIC_ADDRESS, MASK_ID_REGISTER, EXPECTED_MASK_ID, 1)
    observed = (frame[4], frame[5], frame[6], frame[7], frame[8], frame[10])
    if observed != expected or frame[9] != EXPECTED_MASK_ID:
        raise TwimHilFailure(
            "BQ25186 read-only result mismatch: "
            f"instance={frame[4]}, result={frame[5]}, address=0x{frame[6]:02X}, "
            f"register=0x{frame[7]:02X}, value=0x{frame[8]:02X}, pass={frame[10]}"
        )
    return {"address": frame[6], "register": frame[7], "value": frame[8]}


def choose_exact_port(transcripts: dict[str, bytes], expected: bytes) -> str:
    matches = [device for device, data in transcripts.items() if data == expected]
    if len(matches) != 1:
        raise TwimHilFailure(
            "exactly one VCOM must return the expected frame: "
            f"matches={len(matches)}, sizes="
            f"{ {device: len(data) for device, data in transcripts.items()} }"
        )
    if any(data for device, data in transcripts.items() if device != matches[0]):
        raise TwimHilFailure("non-selected VCOM returned unexpected bytes.")
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
    frozen = {device: bytes(data) for device, data in transcripts.items()}
    if expected is not None:
        return choose_exact_port(frozen, expected), frozen
    candidates = [device for device, data in frozen.items() if len(data) == PACKET_SIZE]
    if len(candidates) != 1:
        raise TwimHilFailure(
            f"exactly one VCOM must return a 32-byte result: candidates={candidates}"
        )
    if any(data for device, data in frozen.items() if device != candidates[0]):
        raise TwimHilFailure("non-selected VCOM returned unexpected result bytes.")
    return candidates[0], frozen


def flash_image(
    pyocd: Path, probe_id: str, image: Path, timeout_seconds: float
) -> dict[str, Any]:
    command = [
        str(pyocd),
        "load",
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
        raise TwimHilFailure(f"pyOCD flash failed: {error}") from error
    if result.returncode != 0:
        output = result.stdout[-MAX_COMMAND_OUTPUT:].decode("utf-8", "replace")
        raise TwimHilFailure(
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
        raise TwimHilFailure("pyOCD executable was not found.")
    commit, board_revision, images = locate_images(
        args.repository, args.build_root, INSTANCES
    )
    try:
        import serial
        from serial.tools import list_ports
    except ImportError as error:
        raise TwimHilFailure("pyserial is required for VCOM HIL.") from error

    port_names = matching_port_names(list_ports.comports(), args.probe_id)
    streams: dict[str, Any] = {}
    results: list[dict[str, Any]] = []
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
        for sequence, instance in enumerate(INSTANCES, start=1):
            for stream in streams.values():
                stream.reset_input_buffer()
                stream.reset_output_buffer()
            image = images[instance]
            flash = flash_image(args.pyocd, args.probe_id, image["path"], args.flash_timeout)
            ready_port, ready_transcripts = collect_frame(
                streams,
                ready_frame(instance),
                args.settle_seconds + args.response_timeout,
            )
            for stream in streams.values():
                stream.reset_input_buffer()
                stream.reset_output_buffer()
                if stream.write(command_frame(instance)) != PACKET_SIZE:
                    raise TwimHilFailure("VCOM accepted only part of the command frame.")
                stream.flush()
            result_port, transcripts = collect_frame(
                streams, None, args.response_timeout
            )
            if result_port != ready_port:
                raise TwimHilFailure("TWIM READY and result used different VCOM ports.")
            frame = transcripts[result_port]
            result = validate_result_frame(frame, instance)
            results.append(
                {
                    "sequence": sequence,
                    "instance": instance,
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
                    "status": "passed",
                }
            )
            print(f"M24_TWIM_INSTANCE_PASS={instance};VALUE=0x{result['value']:02X}")
    finally:
        for stream in streams.values():
            try:
                stream.close()
            except Exception:
                pass

    evidence = {
        "schema_version": 1,
        "milestone": "M24",
        "evidence_type": "onboard-twim-bq25186-read-only",
        "status": "passed",
        "core_revision": commit,
        "board_revision": board_revision,
        "probe_id_sha256": hashlib.sha256(args.probe_id.encode("ascii")).hexdigest(),
        "vcom_candidate_count": len(port_names),
        "baud_rate": BAUD_RATE,
        "pmic_address": PMIC_ADDRESS,
        "register": MASK_ID_REGISTER,
        "expected_value": EXPECTED_MASK_ID,
        "write_operations": 0,
        "instances": results,
        "mass_erase_requested": False,
        "recover_requested": False,
        "completed_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    write_evidence(args.evidence, evidence)
    print(f"M24_TWIM_ONBOARD_HIL_PASS=3;EVIDENCE={args.evidence.resolve()}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except TwimHilFailure as error:
        print(f"M24_TWIM_ONBOARD_HIL_FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
