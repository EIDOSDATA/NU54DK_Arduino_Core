"""! @brief Arduino BAP 양방향 stream의 종료·재연결을 실기 측정합니다. """

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
ADDRESS = re.compile(r"\b[0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5}\b")
CLIENT_SENT = re.compile(r"LE Audio duplex sent frames=(\d+)")
SERVER_SENT = re.compile(r"LE Audio duplex sent=(\d+)")
RECEIVED = re.compile(r"LE Audio duplex received=(\d+) energy=(\d+) dropped=(\d+)")


def sha256(path: Path) -> str:
    """! @brief firmware와 flash 기록의 byte hash를 계산합니다. """
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_flash(path: Path, role: str, image: Path, probe_hash: str) -> None:
    """! @brief 실제 flash한 역할과 측정에 지정한 이미지를 대조합니다. """
    record = json.loads(path.read_text(encoding="utf-8-sig"))
    if (record.get("status") != "FLASH_PREPARED" or
            not record.get(f"{role}_flash") or
            record.get(f"{role}_probe_sha256") != probe_hash or
            record.get(f"{role}_image_sha256") != sha256(image)):
        raise RuntimeError(f"{role} image and flash record disagree")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--client-probe-sha256", required=True)
    parser.add_argument("--server-probe-sha256", required=True)
    parser.add_argument("--client-image", required=True, type=Path)
    parser.add_argument("--server-image", required=True, type=Path)
    parser.add_argument("--client-config", required=True, type=Path)
    parser.add_argument("--server-config", required=True, type=Path)
    parser.add_argument("--client-flash-record", required=True, type=Path)
    parser.add_argument("--server-flash-record", required=True, type=Path)
    parser.add_argument("--core-revision", required=True)
    parser.add_argument("--source-clean", action="store_true")
    parser.add_argument("--cycles", type=int, default=20)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.cycles < 1 or args.cycles > 20:
        parser.error("cycles must be between 1 and 20")
    if args.client_probe_sha256 == args.server_probe_sha256:
        parser.error("client and server probe identities overlap")
    for config in (args.client_config, args.server_config):
        lines = config.read_text(encoding="utf-8").splitlines()
        if "CONFIG_LIBLC3=y" not in lines or "CONFIG_FPU=y" not in lines:
            parser.error("both images require LC3 and FPU")
    verify_flash(args.client_flash_record, "client", args.client_image,
                 args.client_probe_sha256)
    verify_flash(args.server_flash_record, "server", args.server_image,
                 args.server_probe_sha256)
    if args.source_clean:
        revision = subprocess.check_output(("git", "rev-parse", "HEAD"),
                                           cwd=ROOT, text=True).strip()
        dirty = subprocess.check_output(("git", "status", "--porcelain"),
                                        cwd=ROOT, text=True).strip()
        if dirty or revision != args.core_revision:
            parser.error("exact HIL requires clean source and full HEAD revision")

    serial, ports = import_pyserial()
    client_uid, _, client_port = discover(args.client_probe_sha256, ports)
    server_uid, _, server_port = discover(args.server_probe_sha256, ports)
    if client_uid == server_uid or client_port == server_port:
        raise RuntimeError("role mapping overlap")
    record = {
        "status": "FAIL", "test": "arduino_bap_duplex_stop_release_cycles",
        "core_revision": args.core_revision, "source_clean": args.source_clean,
        "client_probe_sha256": args.client_probe_sha256,
        "server_probe_sha256": args.server_probe_sha256,
        "client_port": client_port, "server_port": server_port,
        "client_image_sha256": sha256(args.client_image),
        "server_image_sha256": sha256(args.server_image),
        "client_config_sha256": sha256(args.client_config),
        "server_config_sha256": sha256(args.server_config),
        "client_flash_record_sha256": sha256(args.client_flash_record),
        "server_flash_record_sha256": sha256(args.server_flash_record),
        "requested_cycles": args.cycles, "completed_cycles": 0,
        "cycle_seconds": [], "client_lines": [], "server_lines": [],
    }
    try:
        with ProbeLocks([client_uid, server_uid]):
            with serial.Serial(client_port, 115200, timeout=0.03) as client, \
                    serial.Serial(server_port, 115200, timeout=0.03) as server:
                client.reset_input_buffer()
                server.reset_input_buffer()
                hardware_reset(server_uid)
                hardware_reset(client_uid)
                client.reset_input_buffer()
                server.reset_input_buffer()
                cycle_started = time.monotonic()
                server_rx_baseline = 0
                server_tx_baseline = 0
                server_rx = 0
                server_tx = 0
                client_sent = 0
                client_rx = 0
                streaming = False
                stop_requested = False
                stopped = False
                disconnected = False
                while record["completed_cycles"] < args.cycles:
                    cycle = record["completed_cycles"] + 1
                    if time.monotonic() - cycle_started > 30.0:
                        raise RuntimeError(f"cycle {cycle} exceeded 30 seconds")
                    for port, role in ((client, "client"), (server, "server")):
                        line = port.readline().decode("utf-8", errors="replace").strip()
                        if not line:
                            continue
                        line = ADDRESS.sub("<bt-address>", line[:400])
                        record[f"{role}_lines"].append(line)
                        if ("failed" in line.lower() or "FATAL" in line or
                                "Stack overflow" in line or "*****" in line):
                            raise RuntimeError(f"{role} error in cycle {cycle}: {line[:100]}")
                        if role == "client":
                            if "LE Audio duplex client streaming" in line:
                                streaming = True
                                disconnected = False
                            if stop_requested and "LE Audio stream stopped" in line:
                                stopped = True
                            if stopped and "LE Audio peer disconnected" in line:
                                disconnected = True
                            match = CLIENT_SENT.search(line)
                            if match:
                                client_sent = max(client_sent, int(match.group(1)))
                            match = RECEIVED.search(line)
                            if match:
                                count, energy, drops = (int(value) for value in match.groups())
                                if energy == 0 or drops != 0:
                                    raise RuntimeError("client LC3 energy/drop invalid")
                                client_rx = max(client_rx, count)
                        else:
                            match = SERVER_SENT.search(line)
                            if match:
                                server_tx = max(server_tx, int(match.group(1)))
                            match = RECEIVED.search(line)
                            if match:
                                count, energy, drops = (int(value) for value in match.groups())
                                if energy == 0 or drops != 0:
                                    raise RuntimeError("server LC3 energy/drop invalid")
                                server_rx = max(server_rx, count)
                    if (streaming and not stop_requested and client_sent >= 100 and
                            client_rx >= 100 and server_rx >= server_rx_baseline + 100 and
                            server_tx >= server_tx_baseline + 100):
                        client.write(b"s")
                        stop_requested = True
                    if stop_requested and stopped and disconnected:
                        record["completed_cycles"] = cycle
                        record["cycle_seconds"].append(
                            round(time.monotonic() - cycle_started, 3)
                        )
                        print(f"M31_BAP_DUPLEX_CYCLE={cycle}/{args.cycles}", flush=True)
                        cycle_started = time.monotonic()
                        server_rx_baseline = server_rx
                        server_tx_baseline = server_tx
                        client_sent = 0
                        client_rx = 0
                        streaming = False
                        stop_requested = False
                        stopped = False
                        disconnected = False
        record["status"] = "ARDUINO_BAP_DUPLEX_STOP_RELEASE_PASS"
    except Exception as error:
        record["failure_class"] = type(error).__name__
        record["failure_detail"] = ADDRESS.sub("<bt-address>", str(error)[:180])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print("M31_BAP_DUPLEX_STOP=" + record["status"])
    return 0 if record["status"] == "ARDUINO_BAP_DUPLEX_STOP_RELEASE_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
