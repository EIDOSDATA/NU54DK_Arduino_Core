#!/usr/bin/env python3
"""! @brief 한쪽만 bond를 삭제한 CS stale-key negative HIL을 실행합니다. """

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any


sys.path.insert(0, str(Path(__file__).resolve().parent))

from ble_pair_hil_common import flash_image_pyocd  # noqa: E402
from m6_serial_echo import import_pyserial  # noqa: E402
from m31_ble_capability_run import collect_register_identity, discover  # noqa: E402
from m31_cs_ras_pair_run import hardware_reset  # noqa: E402
from v04_protocol import ProbeLocks  # noqa: E402


FAILURE_MARKERS = (
    "UNEXPECTED",
    "setup failed",
    "command rejected",
    "clean failed",
    "stale erase failed",
    "scan failed",
    "advertising failed",
    "pairing response failed",
)


class StaleKeyFailure(RuntimeError):
    """! @brief fixture·UART·stale-key 계약 위반입니다. """


def parse_status_line(role: str, line: str) -> dict[str, int] | None:
    """! @brief role별 정량 status 한 줄을 strict field 집합으로 해석합니다. """

    if role == "initiator":
        pattern = re.compile(
            r"CSKEY initiator status bonds=(\d+) pairing_rejected=(\d+) "
            r"l2=(\d+) ready=(\d+) raw=(\d+) connected=([01])"
        )
        names = ("bonds", "pairing_rejected", "l2", "ready", "raw", "connected")
    elif role == "reflector":
        pattern = re.compile(
            r"CSKEY reflector status bonds=(\d+) pairing_rejected=(\d+) "
            r"l2=(\d+) ready=(\d+) active=(\d+) connected=([01])"
        )
        names = ("bonds", "pairing_rejected", "l2", "ready", "active", "connected")
    else:
        raise ValueError("role must be initiator or reflector")
    match = pattern.fullmatch(line)
    if match is None:
        return None
    return dict(zip(names, map(int, match.groups()), strict=True))


def validate_negative_snapshot(
    initiator: dict[str, int], reflector: dict[str, int]
) -> None:
    """! @brief stale 한쪽 삭제와 repair 거부 뒤 CS 무진행을 판정합니다. """

    if initiator["bonds"] != 1 or reflector["bonds"] != 0:
        raise StaleKeyFailure("one-sided bond count mismatch")
    if initiator["pairing_rejected"] < 1 or reflector["pairing_rejected"] < 1:
        raise StaleKeyFailure("repair pairing was not explicitly rejected by both roles")
    if any(initiator[name] != 0 for name in ("l2", "ready", "raw")):
        raise StaleKeyFailure("initiator advanced after stale-key rejection")
    if any(reflector[name] != 0 for name in ("l2", "ready", "active")):
        raise StaleKeyFailure("reflector advanced after stale-key rejection")


def _read_lines(port: Any, lines: list[str]) -> list[str]:
    """! @brief 현재 UART에 완성된 줄을 bounded transcript에 추가합니다. """

    captured: list[str] = []
    while int(getattr(port, "in_waiting", 0)) > 0:
        line = port.readline().decode("utf-8", errors="replace").strip()
        if not line:
            continue
        line = line[:400]
        lines.append(line)
        captured.append(line)
    return captured


def _pump(
    ports: dict[str, Any], record: dict[str, Any], duration: float = 0.05
) -> list[tuple[str, str]]:
    """! @brief 두 UART를 짧게 번갈아 읽고 명시적 fixture 실패를 즉시 거부합니다. """

    deadline = time.monotonic() + duration
    captured: list[tuple[str, str]] = []
    while time.monotonic() < deadline:
        progressed = False
        for role, port in ports.items():
            for line in _read_lines(port, record[f"{role}_lines"]):
                progressed = True
                captured.append((role, line))
                if any(marker in line for marker in FAILURE_MARKERS):
                    raise StaleKeyFailure(f"{role} fixture failure: {line}")
        if not progressed:
            time.sleep(0.005)
    return captured


def _wait_markers(
    ports: dict[str, Any],
    record: dict[str, Any],
    markers: dict[str, tuple[str, ...]],
    timeout: float,
) -> None:
    """! @brief role별 marker가 모두 관측될 때까지 bounded UART를 읽습니다. """

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        _pump(ports, record)
        complete = True
        for role, wanted in markers.items():
            transcript = record[f"{role}_lines"]
            if not all(any(marker in line for line in transcript) for marker in wanted):
                complete = False
                break
        if complete:
            return
    raise StaleKeyFailure("UART marker timeout")


def _send(port: Any, command: bytes) -> None:
    """! @brief single-byte fixture 명령을 완전하게 기록합니다. """

    if len(command) != 1 or port.write(command) != 1:
        raise StaleKeyFailure("UART command write failed")
    port.flush()


def _latest_status(role: str, lines: list[str]) -> dict[str, int]:
    """! @brief transcript 뒤에서 가장 최근 strict status를 찾습니다. """

    for line in reversed(lines):
        status = parse_status_line(role, line)
        if status is not None:
            return status
    raise StaleKeyFailure(f"{role} status missing")


def _stop(
    ports: dict[str, Any], record: dict[str, Any], timeout: float = 8.0
) -> None:
    """! @brief 양쪽 STOP을 요청하고 scan·광고·ACL 반환 marker를 기다립니다. """

    for port in ports.values():
        try:
            _send(port, b"s")
        except Exception:
            pass
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            _pump(ports, record)
        except StaleKeyFailure:
            pass
        initiator_stopped = any(
            line == "CSKEY initiator STOPPED" for line in record["initiator_lines"]
        )
        reflector_stopped = any(
            line == "CSKEY reflector STOPPED" for line in record["reflector_lines"]
        )
        if initiator_stopped and reflector_stopped:
            record["stop_confirmed"] = True
            return
    record["stop_confirmed"] = False


def _scrub(lines: list[str]) -> list[str]:
    """! @brief Bluetooth 주소와 긴 원시 식별자를 공개 증적에서 제거합니다. """

    return [
        re.sub(
            r"\b[0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5}\b",
            "<bt-address>",
            re.sub(r"\b[0-9A-Fa-f]{16,}\b", "<identity>", line),
        )
        for line in lines
    ]


def main() -> int:
    """! @brief prime raw RAS 뒤 one-sided stale-key negative를 실행합니다. """

    parser = argparse.ArgumentParser()
    parser.add_argument("--initiator-probe-sha256", required=True)
    parser.add_argument("--reflector-probe-sha256", required=True)
    parser.add_argument("--initiator-image", type=Path, required=True)
    parser.add_argument("--reflector-image", type=Path, required=True)
    parser.add_argument("--core-revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--negative-window", type=float, default=30.0)
    parser.add_argument("--source-clean", action="store_true")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("refusing to overwrite existing evidence")
    if not 10.0 <= args.negative_window <= 45.0:
        parser.error("negative-window must be between 10 and 45 seconds")
    if args.source_clean:
        root = Path(__file__).resolve().parents[3]
        revision = subprocess.check_output(
            ("git", "rev-parse", "HEAD"), cwd=root, text=True
        ).strip()
        changed = subprocess.check_output(
            ("git", "status", "--porcelain"), cwd=root, text=True
        ).strip()
        if changed or revision != args.core_revision:
            parser.error("exact HIL requires clean source and full HEAD revision")

    serial, port_inventory = import_pyserial()
    initiator_uid, initiator_volume, initiator_port = discover(
        args.initiator_probe_sha256, port_inventory
    )
    reflector_uid, reflector_volume, reflector_port = discover(
        args.reflector_probe_sha256, port_inventory
    )
    if initiator_uid == reflector_uid or initiator_port == reflector_port:
        raise StaleKeyFailure("role mapping overlap")

    record: dict[str, Any] = {
        "status": "FAIL",
        "test": "one_sided_stale_key_rejection",
        "arbitrary_unequal_ltk_injection": False,
        "source_clean": args.source_clean,
        "core_revision": args.core_revision,
        "negative_window_s": args.negative_window,
        "initiator_probe_sha256": args.initiator_probe_sha256,
        "reflector_probe_sha256": args.reflector_probe_sha256,
        "initiator_port": initiator_port,
        "reflector_port": reflector_port,
        "initiator_image_sha256": hashlib.sha256(
            args.initiator_image.read_bytes()
        ).hexdigest(),
        "reflector_image_sha256": hashlib.sha256(
            args.reflector_image.read_bytes()
        ).hexdigest(),
        "prime_raw_reports": 0,
        "negative_raw_reports": 0,
        "stop_confirmed": False,
        "initiator_lines": [],
        "reflector_lines": [],
    }
    ports: dict[str, Any] = {}
    started = time.monotonic()
    try:
        with ProbeLocks([initiator_uid, reflector_uid]):
            record["initiator_registers"] = collect_register_identity(
                initiator_uid, initiator_volume
            )
            record["reflector_registers"] = collect_register_identity(
                reflector_uid, reflector_volume
            )
            initiator = serial.Serial(
                initiator_port, 115200, timeout=0.02, write_timeout=2.0
            )
            reflector = serial.Serial(
                reflector_port, 115200, timeout=0.02, write_timeout=2.0
            )
            try:
                ports = {"initiator": initiator, "reflector": reflector}
                for port in ports.values():
                    port.reset_input_buffer()
                record["reflector_flash"] = flash_image_pyocd(
                    "cs_stale_reflector",
                    reflector_uid,
                    args.reflector_image,
                    120.0,
                    hardware_reset=True,
                )
                record["initiator_flash"] = flash_image_pyocd(
                    "cs_stale_initiator",
                    initiator_uid,
                    args.initiator_image,
                    120.0,
                    hardware_reset=True,
                )
                for port in ports.values():
                    port.reset_input_buffer()
                hardware_reset(reflector_uid)
                hardware_reset(initiator_uid)
                time.sleep(0.5)

                for port in ports.values():
                    _send(port, b"c")
                _wait_markers(
                    ports,
                    record,
                    {
                        "initiator": ("CSKEY initiator clean bonds=0",),
                        "reflector": ("CSKEY reflector clean bonds=0",),
                    },
                    10.0,
                )

                _send(reflector, b"p")
                _wait_markers(
                    ports,
                    record,
                    {"reflector": ("CSKEY reflector prime advertising",)},
                    5.0,
                )
                _send(initiator, b"p")
                _wait_markers(
                    ports,
                    record,
                    {
                        "initiator": ("CSKEY initiator prime ready raw=",),
                        "reflector": ("CSKEY reflector prime ready bonds=1",),
                    },
                    90.0,
                )
                record["prime_raw_reports"] = sum(
                    "CSKEY initiator prime ready raw=" in line
                    for line in record["initiator_lines"]
                )
                if record["prime_raw_reports"] < 1:
                    raise StaleKeyFailure("prime raw RAS report missing")

                _send(initiator, b"d")
                _wait_markers(
                    ports,
                    record,
                    {
                        "initiator": ("CSKEY initiator disconnected",),
                        "reflector": ("CSKEY reflector disconnected",),
                    },
                    10.0,
                )
                _send(reflector, b"e")
                _wait_markers(
                    ports,
                    record,
                    {"reflector": ("CSKEY reflector stale erased bonds=0",)},
                    5.0,
                )

                _send(reflector, b"n")
                _wait_markers(
                    ports,
                    record,
                    {"reflector": ("CSKEY reflector negative advertising",)},
                    5.0,
                )
                negative_started = time.monotonic()
                _send(initiator, b"n")
                _wait_markers(
                    ports,
                    record,
                    {
                        "initiator": ("CSKEY initiator repair pairing rejected",),
                        "reflector": ("CSKEY reflector repair pairing rejected",),
                    },
                    20.0,
                )
                while time.monotonic() - negative_started < args.negative_window:
                    _pump(ports, record, 0.05)

                record["negative_raw_reports"] = sum(
                    "CSKEY initiator negative raw UNEXPECTED" in line
                    for line in record["initiator_lines"]
                )
                _send(initiator, b"q")
                _send(reflector, b"q")
                _wait_markers(
                    ports,
                    record,
                    {
                        "initiator": ("CSKEY initiator status bonds=",),
                        "reflector": ("CSKEY reflector status bonds=",),
                    },
                    5.0,
                )
                initiator_status = _latest_status(
                    "initiator", record["initiator_lines"]
                )
                reflector_status = _latest_status(
                    "reflector", record["reflector_lines"]
                )
                validate_negative_snapshot(initiator_status, reflector_status)
                record["initiator_negative"] = initiator_status
                record["reflector_negative"] = reflector_status
                _stop(ports, record)
                if not record["stop_confirmed"]:
                    raise StaleKeyFailure("final STOP was not confirmed")
                record["elapsed_s"] = round(time.monotonic() - started, 3)
                record["status"] = "PASS"
            finally:
                _stop(ports, record)
                initiator.close()
                reflector.close()
    except Exception as error:
        record["failure_class"] = type(error).__name__
        detail = str(error).replace(initiator_uid, "<probe>")
        detail = detail.replace(reflector_uid, "<probe>")
        record["failure_detail"] = re.sub(
            r"\b[0-9A-Fa-f]{16,}\b", "<identity>", detail[:200]
        )

    for role in ("initiator", "reflector"):
        record[f"{role}_lines"] = _scrub(record[f"{role}_lines"])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        "M31_CS_STALE_KEY="
        + record["status"]
        + ";PRIME_RAW="
        + str(record["prime_raw_reports"])
        + ";NEGATIVE_RAW="
        + str(record["negative_raw_reports"])
    )
    return 0 if record["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
