"""! @brief 공개 Arduino BAP stream의 disable·release·재연결 반복을 확인합니다. """

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
DECODED_PATTERN = re.compile(r"LE Audio decoded frames=(\d+) energy=(\d+) dropped=(\d+)")
CYCLE_PATTERN = re.compile(r"LE Audio completed cycles=(\d+)")


def file_hash(path: Path) -> str:
    """! @brief 이미지 또는 구성 파일의 byte 해시를 계산합니다. """
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_clean(revision: str) -> None:
    """! @brief HIL 입력을 현재 clean HEAD와 결합합니다. """
    head = subprocess.check_output(("git", "rev-parse", "HEAD"), cwd=ROOT, text=True).strip()
    changed = subprocess.check_output(("git", "status", "--porcelain"), cwd=ROOT, text=True)
    if changed.strip() or head != revision:
        raise RuntimeError("exact HIL requires clean source and full HEAD revision")


def collect_cycles(client, server, record: dict, requested: int) -> None:
    """! @brief 각 stream의 LC3 100 frame과 ASE release 후 새 연결을 확인합니다. """
    expected = 1
    started = time.monotonic()
    cycle_started = started
    streaming = False
    sent = False
    stopped = False
    disconnected = False
    decoded = 0
    while expected <= requested:
        if time.monotonic() - cycle_started > 30.0:
            raise RuntimeError(f"cycle {expected} exceeded 30-second recovery limit")
        for port, role in ((client, "client"), (server, "server")):
            line = port.readline().decode("utf-8", errors="replace").strip()
            if not line:
                continue
            line = ADDRESS_PATTERN.sub("<bt-address>", line[:400])
            if "Stack overflow" in line or "*****" in line or "FATAL" in line:
                record[f"{role}_lines"].append(line)
                raise RuntimeError(f"{role} fatal fault in cycle {expected}")
            if "LE Audio" not in line:
                continue
            record[f"{role}_lines"].append(line)
            if role == "client":
                if "LE Audio source streaming" in line:
                    streaming = True
                if streaming and "LE Audio sent frames=100" in line:
                    sent = True
                if "LE Audio stream stopped" in line:
                    stopped = True
                if stopped and "LE Audio peer disconnected" in line:
                    disconnected = True
                match = CYCLE_PATTERN.search(line)
                if match is not None:
                    if int(match.group(1)) != expected or not (streaming and sent and stopped):
                        raise RuntimeError(f"cycle {expected} skipped stream/stop/release")
                    record["completed_cycles"] = expected
            else:
                match = DECODED_PATTERN.search(line)
                if match is not None:
                    count, energy, drops = (int(value) for value in match.groups())
                    if energy == 0 or drops != 0 or count < decoded:
                        raise RuntimeError(f"sink LC3 error in cycle {expected}")
                    decoded = count
        if record["completed_cycles"] == expected and disconnected and decoded >= expected * 100:
            record["cycle_seconds"].append(round(time.monotonic() - cycle_started, 3))
            print(f"M31_BAP_STOP_CYCLE={expected}/{requested}", flush=True)
            expected += 1
            cycle_started = time.monotonic()
            streaming = False
            sent = False
            stopped = False
            disconnected = False
    record["elapsed_s"] = round(time.monotonic() - started, 3)
    record["server_decoded_frames"] = decoded


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
    parser.add_argument("--cycles", type=int, default=20)
    parser.add_argument("--source-clean", action="store_true")
    args = parser.parse_args()
    if args.cycles < 1 or args.cycles > 20:
        parser.error("cycles must be between 1 and 20")
    if args.client_probe_sha256 == args.server_probe_sha256:
        parser.error("source and sink probe hashes must differ")
    for config_path in (args.client_config, args.server_config):
        lines = config_path.read_text(encoding="utf-8").splitlines()
        for required in ("CONFIG_LIBLC3=y", "CONFIG_BT_TX_PROCESSOR_STACK_SIZE=3200"):
            if required not in lines:
                parser.error(f"{config_path.name} requires {required}")
    if args.source_clean:
        verify_clean(args.core_revision)

    serial, ports = import_pyserial()
    client_uid, _, client_port = discover(args.client_probe_sha256, ports)
    server_uid, _, server_port = discover(args.server_probe_sha256, ports)
    if client_uid == server_uid or client_port == server_port:
        raise RuntimeError("source and sink probe mapping overlap")
    record = {
        "status": "FAIL", "test": "arduino_bap_lc3_stop_release_cycles",
        "source_clean": args.source_clean, "core_revision": args.core_revision,
        "client_probe_sha256": args.client_probe_sha256,
        "server_probe_sha256": args.server_probe_sha256,
        "client_port": client_port, "server_port": server_port,
        "client_image_sha256": file_hash(args.client_image),
        "server_image_sha256": file_hash(args.server_image),
        "client_config_sha256": file_hash(args.client_config),
        "server_config_sha256": file_hash(args.server_config),
        "requested_cycles": args.cycles, "completed_cycles": 0,
        "cycle_seconds": [], "client_lines": [], "server_lines": [],
    }
    try:
        with ProbeLocks([client_uid, server_uid]):
            with serial.Serial(client_port, 115200, timeout=0.03) as client, \
                    serial.Serial(server_port, 115200, timeout=0.03) as server:
                client.reset_input_buffer()
                server.reset_input_buffer()
                hardware_reset(client_uid)
                time.sleep(2)
                client.reset_input_buffer()
                server.reset_input_buffer()
                hardware_reset(server_uid)
                collect_cycles(client, server, record, args.cycles)
        record["status"] = "ARDUINO_BAP_LC3_20_STOP_RELEASE_PASS" if \
            args.cycles == 20 else "ARDUINO_BAP_LC3_STOP_RELEASE_PASS"
    except Exception as error:
        record["error"] = str(error)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"M31_BAP_STOP={record['status']}")
    if record["status"] == "FAIL":
        print(record["error"], file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
