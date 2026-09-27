"""! @brief Arduino BAP LC3 두 역할의 sink 재시작 후 연결 복구를 실기로 검증합니다. """

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
FRAME_PATTERN = re.compile(r"LE Audio (?:sent|decoded) frames=(\d+)")


def image_hash(path: Path) -> str:
    """! @brief 입력 image와 구성 파일의 byte 해시를 반환합니다. """
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_clean(revision: str) -> None:
    """! @brief 결과가 현재 깨끗한 commit의 코드와 결합되도록 강제합니다. """
    head = subprocess.check_output(("git", "rev-parse", "HEAD"), cwd=ROOT, text=True).strip()
    changed = subprocess.check_output(("git", "status", "--porcelain"), cwd=ROOT, text=True)
    if changed.strip() or head != revision:
        raise RuntimeError("exact HIL requires clean source and full HEAD revision")


def collect_until(client, server, record: dict, phase: str, timeout: float) -> dict:
    """! @brief 두 UART의 광고·재접속·LC3 복호화 100 frame을 순서대로 관찰합니다. """
    state = {"advertising": False, "disconnected": phase == "initial",
             "streaming": False, "sent": 0, "decoded": 0}
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for port, role in ((client, "client"), (server, "server")):
            line = port.readline().decode("utf-8", errors="replace").strip()
            if not line:
                continue
            line = ADDRESS_PATTERN.sub("<bt-address>", line[:400])
            if "Stack overflow" in line or "*****" in line or "FATAL" in line:
                record[f"{role}_lines"].append(line)
                raise RuntimeError(f"{role} fatal fault during {phase}")
            if "LE Audio" not in line:
                continue
            record[f"{role}_lines"].append(line)
            if role == "server" and "LE Audio sink advertising" in line:
                state["advertising"] = True
            if role == "client" and "LE Audio peer disconnected" in line:
                state["disconnected"] = True
            if not state["advertising"]:
                continue
            if role == "client" and state["disconnected"] and \
                    "LE Audio source streaming" in line:
                state["streaming"] = True
            match = FRAME_PATTERN.search(line)
            if match is not None:
                if role == "client" and state["streaming"] and "sent frames=" in line:
                    state["sent"] = max(state["sent"], int(match.group(1)))
                if role == "server" and "decoded frames=" in line:
                    state["decoded"] = max(state["decoded"], int(match.group(1)))
        if state["streaming"] and state["sent"] >= 100 and state["decoded"] >= 100:
            return state
    raise RuntimeError(f"{phase} recovery timeout: {state}")


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
        configuration = config_path.read_text(encoding="utf-8")
        for required in ("CONFIG_LIBLC3=y", "CONFIG_BT_TX_PROCESSOR_STACK_SIZE=3200"):
            if required not in configuration.splitlines():
                parser.error(f"{config_path.name} requires {required}")
    if args.source_clean:
        verify_clean(args.core_revision)

    serial, ports = import_pyserial()
    client_uid, _, client_port = discover(args.client_probe_sha256, ports)
    server_uid, _, server_port = discover(args.server_probe_sha256, ports)
    if client_uid == server_uid or client_port == server_port:
        raise RuntimeError("source and sink probe mapping overlap")
    record = {
        "status": "FAIL", "test": "arduino_bap_lc3_sink_restart_recovery",
        "source_clean": args.source_clean, "core_revision": args.core_revision,
        "client_probe_sha256": args.client_probe_sha256,
        "server_probe_sha256": args.server_probe_sha256,
        "client_port": client_port, "server_port": server_port,
        "client_image_sha256": image_hash(args.client_image),
        "server_image_sha256": image_hash(args.server_image),
        "client_config_sha256": image_hash(args.client_config),
        "server_config_sha256": image_hash(args.server_config),
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
                collect_until(client, server, record, "initial", 45.0)
                for cycle in range(1, args.cycles + 1):
                    started = time.monotonic()
                    hardware_reset(server_uid)
                    collect_until(client, server, record, f"cycle_{cycle}", 45.0)
                    record["completed_cycles"] = cycle
                    record["cycle_seconds"].append(round(time.monotonic() - started, 3))
                    print(f"M31_BAP_RECOVERY_CYCLE={cycle}/{args.cycles}", flush=True)
        record["status"] = "ARDUINO_BAP_LC3_20_RESTART_RECOVERY_PASS" if \
            args.cycles == 20 else "ARDUINO_BAP_LC3_RESTART_RECOVERY_PASS"
    except Exception as error:
        record["error"] = str(error)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"M31_BAP_RECOVERY={record['status']}")
    if record["status"] == "FAIL":
        print(record["error"], file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
