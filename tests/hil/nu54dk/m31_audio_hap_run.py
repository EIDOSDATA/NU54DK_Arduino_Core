"""! @brief 공개 Hearing Access 두 역할의 preset·negative·재연결을 실기로 검증합니다. """

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time


HIL = Path(__file__).resolve().parent
ROOT = HIL.parents[2]
sys.path.insert(0, str(HIL))

from ble_pair_hil_common import flash_image_pyocd  # noqa: E402
from m6_serial_echo import import_pyserial  # noqa: E402
from m31_ble_capability_run import collect_register_identity, discover  # noqa: E402
from m31_cs_ras_pair_run import hardware_reset  # noqa: E402
from v04_protocol import ProbeLocks  # noqa: E402


ADDRESS_PATTERN = re.compile(r"\b[0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5}\b")
STATE_PATTERN = re.compile(r"active=(\d+) presets=(\d+)")


def file_hash(path: Path) -> str:
    """! @brief image와 설정 파일의 SHA-256을 계산합니다. """
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_clean(revision: str) -> None:
    """! @brief 현재 clean HEAD와 요청 revision을 결합합니다. """
    head = subprocess.check_output(("git", "rev-parse", "HEAD"), cwd=ROOT, text=True).strip()
    status = subprocess.check_output(("git", "status", "--porcelain"), cwd=ROOT, text=True)
    if status.strip() or head != revision:
        raise RuntimeError("exact HIL requires clean source and full HEAD revision")


def read_available(client, server, record: dict[str, object]) -> list[tuple[str, str]]:
    """! @brief 두 UART에서 bounded line을 읽고 주소를 익명화합니다. """
    lines: list[tuple[str, str]] = []
    for port, role in ((client, "client"), (server, "server")):
        raw = port.readline().decode("utf-8", errors="replace").strip()
        if not raw:
            continue
        line = ADDRESS_PATTERN.sub("<bt-address>", raw[:400])
        if any(token in line for token in ("Stack overflow", "*****", "FATAL")):
            raise RuntimeError(f"{role} fatal fault: {line}")
        cast_lines = record[f"{role}_lines"]
        if isinstance(cast_lines, list) and len(cast_lines) < 4000:
            cast_lines.append(line)
        lines.append((role, line))
    return lines


def wait_for(client, server, record: dict[str, object], predicate, timeout: float, name: str) -> str:
    """! @brief predicate와 일치하는 실제 UART line을 제한 시간 안에 기다립니다. """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for role, line in read_available(client, server, record):
            if predicate(role, line):
                return line
    raise RuntimeError(f"{name} timeout")


def wait_state(
    client, server, record: dict[str, object], expected: int, timeout: float = 10.0
) -> str:
    """! @brief client가 세 preset과 기대 active index를 보고할 때까지 기다립니다. """
    return wait_for(
        client,
        server,
        record,
        lambda role, line: role == "client"
        and (match := STATE_PATTERN.search(line)) is not None
        and int(match.group(1)) == expected
        and int(match.group(2)) == 3,
        timeout,
        f"active preset {expected}",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--client-probe-sha256", required=True)
    parser.add_argument("--server-probe-sha256", required=True)
    parser.add_argument("--client-image", required=True, type=Path)
    parser.add_argument("--server-image", required=True, type=Path)
    parser.add_argument("--client-config", required=True, type=Path)
    parser.add_argument("--server-config", required=True, type=Path)
    parser.add_argument("--core-revision", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--operations", type=int, default=100)
    parser.add_argument("--negative-iterations", type=int, default=20)
    parser.add_argument("--recovery-cycles", type=int, default=20)
    parser.add_argument("--source-clean", action="store_true")
    args = parser.parse_args()
    if args.operations != 100 or args.negative_iterations != 20 or args.recovery_cycles != 20:
        parser.error("release evidence requires 100 operations, 20 negatives, and 20 recoveries")
    if args.client_probe_sha256 == args.server_probe_sha256:
        parser.error("client and server probe hashes must differ")
    if args.source_clean:
        verify_clean(args.core_revision)

    serial, ports = import_pyserial()
    client_uid, client_volume, client_port = discover(args.client_probe_sha256, ports)
    server_uid, server_volume, server_port = discover(args.server_probe_sha256, ports)
    if client_uid == server_uid or client_port == server_port:
        raise RuntimeError("client and server mapping overlap")

    record: dict[str, object] = {
        "status": "FAIL",
        "test": "arduino_hearing_access_profiles",
        "source_clean": args.source_clean,
        "core_revision": args.core_revision,
        "client_probe_sha256": args.client_probe_sha256,
        "server_probe_sha256": args.server_probe_sha256,
        "client_port": client_port,
        "server_port": server_port,
        "client_image_sha256": file_hash(args.client_image),
        "server_image_sha256": file_hash(args.server_image),
        "client_config_sha256": file_hash(args.client_config),
        "server_config_sha256": file_hash(args.server_config),
        "requested_operations": args.operations,
        "completed_operations": 0,
        "invalid_index_rejected": 0,
        "synchronized_request_rejected": 0,
        "requested_recovery_cycles": args.recovery_cycles,
        "completed_recovery_cycles": 0,
        "recovery_seconds": [],
        "client_lines": [],
        "server_lines": [],
    }
    try:
        with ProbeLocks([client_uid, server_uid]):
            record["client_registers"] = collect_register_identity(client_uid, client_volume)
            record["server_registers"] = collect_register_identity(server_uid, server_volume)
            record["server_flash"] = flash_image_pyocd(
                "hearing_server", server_uid, args.server_image, 120.0, hardware_reset=True
            )
            record["client_flash"] = flash_image_pyocd(
                "hearing_client", client_uid, args.client_image, 120.0, hardware_reset=True
            )
            with (
                serial.Serial(client_port, 115200, timeout=0.03) as client,
                serial.Serial(server_port, 115200, timeout=0.03) as server,
            ):
                client.reset_input_buffer()
                server.reset_input_buffer()
                hardware_reset(server_uid)
                time.sleep(1.0)
                hardware_reset(client_uid)
                wait_state(client, server, record, 1, 45.0)

                commands = ((b"5", 5), (b"8", 8), (b"1", 1), (b"n", 5), (b"p", 1))
                for iteration in range(args.operations):
                    command, expected = commands[iteration % len(commands)]
                    client.write(command)
                    client.flush()
                    wait_state(client, server, record, expected)
                    record["completed_operations"] = iteration + 1

                for iteration in range(args.negative_iterations):
                    client.write(b"x")
                    client.flush()
                    wait_for(
                        client,
                        server,
                        record,
                        lambda role, line: role == "client" and
                        "Invalid preset result=1" in line,
                        5.0,
                        "invalid preset rejection",
                    )
                    record["invalid_index_rejected"] = iteration + 1

                for iteration in range(args.negative_iterations):
                    client.write(b"y")
                    client.flush()
                    wait_for(
                        client,
                        server,
                        record,
                        lambda role, line: role == "client" and
                        "Hearing Access operation rejected" in line,
                        10.0,
                        "synchronized preset rejection",
                    )
                    record["synchronized_request_rejected"] = iteration + 1

                server.write(b"n")
                server.flush()
                wait_for(
                    client,
                    server,
                    record,
                    lambda role, line: role == "client" and "name=Conversation" in line,
                    10.0,
                    "preset rename notification",
                )
                server.write(b"a")
                server.flush()
                wait_for(
                    client,
                    server,
                    record,
                        lambda role, line: role == "client"
                        and "preset index=5 available=0" in line,
                    10.0,
                    "preset availability notification",
                )

                for cycle in range(1, args.recovery_cycles + 1):
                    started = time.monotonic()
                    hardware_reset(server_uid)
                    wait_for(
                        client,
                        server,
                        record,
                        lambda role, line: role == "client"
                        and "Hearing Access server disconnected" in line,
                        15.0,
                        "server disconnect",
                    )
                    wait_state(client, server, record, 1, 30.0)
                    elapsed = round(time.monotonic() - started, 3)
                    cast_times = record["recovery_seconds"]
                    if isinstance(cast_times, list):
                        cast_times.append(elapsed)
                    record["completed_recovery_cycles"] = cycle
                    print(f"M31_HAP_RECOVERY={cycle}/{args.recovery_cycles}", flush=True)
        record["status"] = "ARDUINO_HAP_100_OP_20_NEGATIVE_20_RECOVERY_PASS"
    except Exception as error:
        record["error"] = str(error)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"M31_HAP={record['status']}")
    if record["status"] == "FAIL":
        print(record.get("error", "unknown failure"), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
