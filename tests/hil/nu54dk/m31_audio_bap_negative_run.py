"""! @brief Arduino ASCS server의 원격 codec·QoS 거부를 실제 두 보드에서 확인합니다. """

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))

from m6_serial_echo import import_pyserial
from m31_ble_capability_run import discover
from m31_cs_ras_pair_run import hardware_reset
from v04_protocol import ProbeLocks


ROOT = Path(__file__).resolve().parents[3]
ADDRESS_PATTERN = re.compile(r"\b[0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5}\b")
RESPONSE_PATTERN = re.compile(r"M31_NEG_(CODEC|QOS)_RSP code=(\d+) reason=(\d+)")
EXPECTED_REASON = {"codec": 2, "qos": 6}


def file_hash(path: Path) -> str:
    """! @brief 입력 바이너리·구성의 SHA-256을 계산합니다. """
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_clean(revision: str) -> None:
    """! @brief 실기 입력을 clean HEAD와 결합합니다. """
    head = subprocess.check_output(("git", "rev-parse", "HEAD"), cwd=ROOT, text=True).strip()
    changed = subprocess.check_output(("git", "status", "--porcelain"), cwd=ROOT, text=True)
    if changed.strip() or head != revision:
        raise RuntimeError("exact HIL requires clean source and full HEAD revision")


def collect_response(client, server, record: dict, case: str, attempt: int) -> None:
    """! @brief 연결·검색 이후 기대 ASCS 거부 응답 하나를 수집합니다. """
    connected = False
    discovered = False
    started = time.monotonic()
    while time.monotonic() - started < 30.0:
        for port, role in ((client, "client"), (server, "server")):
            line = port.readline().decode("utf-8", errors="replace").strip()
            if not line:
                continue
            line = ADDRESS_PATTERN.sub("<bt-address>", line[:400])
            if "Stack overflow" in line or "*****" in line or "FATAL" in line:
                record[f"{role}_lines"].append(line)
                raise RuntimeError(f"{role} fatal fault in attempt {attempt}")
            if role == "server":
                if "LE Audio" in line:
                    record["server_lines"].append(line)
                continue
            if any(key in line for key in ("Connected", "Sinks discovered", "M31_NEG", "Failed")):
                record["client_lines"].append(line)
            if line == "Connected" or line.startswith("Connected:"):
                connected = True
            if "Sinks discovered" in line:
                discovered = True
            match = RESPONSE_PATTERN.search(line)
            if match is not None:
                response_case, code, reason = match.groups()
                if response_case.lower() != case or int(code) != 7 or \
                        int(reason) != EXPECTED_REASON[case] or not (connected and discovered):
                    raise RuntimeError(f"unexpected ASCS response in attempt {attempt}: {line}")
                record["attempt_seconds"].append(round(time.monotonic() - started, 3))
                record["rejected_operations"] += 1
                print(f"M31_BAP_NEGATIVE={case}:{attempt}/{record['requested_operations']}", flush=True)
                return
    raise RuntimeError(f"{case} attempt {attempt} exceeded 30-second ASCS response limit")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", choices=("codec", "qos"), required=True)
    parser.add_argument("--client-probe-sha256", required=True)
    parser.add_argument("--server-probe-sha256", required=True)
    parser.add_argument("--client-image", required=True, type=Path)
    parser.add_argument("--server-image", required=True, type=Path)
    parser.add_argument("--client-config", required=True, type=Path)
    parser.add_argument("--server-config", required=True, type=Path)
    parser.add_argument("--fixture-record", required=True, type=Path)
    parser.add_argument("--core-revision", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--iterations", type=int, default=20)
    parser.add_argument("--source-clean", action="store_true")
    args = parser.parse_args()
    if args.iterations < 1 or args.iterations > 20:
        parser.error("iterations must be between 1 and 20")
    if args.client_probe_sha256 == args.server_probe_sha256:
        parser.error("client and server probe hashes must differ")
    if args.source_clean:
        verify_clean(args.core_revision)
    fixture = json.loads(args.fixture_record.read_text(encoding="utf-8"))
    if len(fixture.get("generated_main_sha256", "")) != 64:
        parser.error("fixture record requires generated source hash")

    serial, ports = import_pyserial()
    client_uid, _, client_port = discover(args.client_probe_sha256, ports)
    server_uid, _, server_port = discover(args.server_probe_sha256, ports)
    if client_uid == server_uid or client_port == server_port:
        raise RuntimeError("client and server probe mapping overlap")
    record = {
        "status": "FAIL", "test": "arduino_bap_remote_ascs_negative",
        "case": args.case, "source_clean": args.source_clean,
        "core_revision": args.core_revision,
        "client_probe_sha256": args.client_probe_sha256,
        "server_probe_sha256": args.server_probe_sha256,
        "client_port": client_port, "server_port": server_port,
        "client_image_sha256": file_hash(args.client_image),
        "server_image_sha256": file_hash(args.server_image),
        "client_config_sha256": file_hash(args.client_config),
        "server_config_sha256": file_hash(args.server_config),
        "fixture_record_sha256": file_hash(args.fixture_record),
        "requested_operations": args.iterations, "rejected_operations": 0,
        "attempt_seconds": [], "client_lines": [], "server_lines": [],
    }
    try:
        with ProbeLocks([client_uid, server_uid]):
            with serial.Serial(client_port, 115200, timeout=0.03) as client, \
                    serial.Serial(server_port, 115200, timeout=0.03) as server:
                client.reset_input_buffer()
                server.reset_input_buffer()
                for attempt in range(1, args.iterations + 1):
                    client.reset_input_buffer()
                    server.reset_input_buffer()
                    hardware_reset(server_uid)
                    time.sleep(2)
                    hardware_reset(client_uid)
                    collect_response(client, server, record, args.case, attempt)
        record["status"] = "ARDUINO_BAP_REMOTE_ASCS_NEGATIVE_PASS"
    except Exception as error:
        record["error"] = str(error)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"M31_BAP_NEGATIVE_STATUS={record['status']}")
    if record["status"] == "FAIL":
        print(record["error"], file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
