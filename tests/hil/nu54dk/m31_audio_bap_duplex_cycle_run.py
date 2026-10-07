"""! @brief Arduino BAP 양방향 stream의 종료·재연결을 실기 측정합니다. """

import argparse
from contextlib import ExitStack
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
from ble_pair_hil_common import validate_build_record
from v04_protocol import ProbeLocks


ROOT = Path(__file__).resolve().parents[3]
LOCK = json.loads((ROOT / "tools/ci/ncs-3.4.0.lock.json").read_text(encoding="utf-8"))
APPLICATIONS = {
    "client": ROOT / "libraries/NUCODE_BLE_Audio/examples/BapUnicastDuplexClient",
    "server": ROOT / "libraries/NUCODE_BLE_Audio/examples/BapUnicastDuplexServer",
}
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


def validate_cycle_records(record: dict, cycles: int) -> None:
    """! @brief 양방향 LC3 frame·QoS 종료·ACL 정리의 회차별 실제 분모를 검사합니다. """

    rows = record.get("cycle_records")
    if (not isinstance(rows, list) or len(rows) != cycles or
            [row.get("cycle") for row in rows] != list(range(1, cycles + 1))):
        raise ValueError("BAP cycle denominator mismatch")
    expected_events = {
        "client": ["streaming", "stopped", "disconnected"],
        "server": ["disconnected"],
    }
    previous_ends = {"client": 0, "server": 0}
    server_totals = {"sent_frames": 0, "received_frames": 0}
    for row in rows:
        if (set(row) != {"cycle", "status", "duration_seconds", "client", "server",
                         "events", "cleanup", "client_range", "server_range"} or
                row["status"] != "PASS" or row["cleanup"] != "PASS" or
                not isinstance(row["duration_seconds"], (int, float)) or
                not 0 < row["duration_seconds"] <= 30.0 or
                row["events"] != expected_events):
            raise ValueError("BAP cycle lifecycle mismatch")
        parsed = {}
        for role in ("client", "server"):
            counters = row[role]
            if (set(counters) != {"sent_frames", "received_frames", "energy",
                                  "dropped_frames"} or
                    not isinstance(counters["sent_frames"], int) or
                    counters["sent_frames"] < 100 or
                    not isinstance(counters["received_frames"], int) or
                    counters["received_frames"] < 100 or
                    not isinstance(counters["energy"], int) or counters["energy"] <= 0 or
                    counters["dropped_frames"] != 0):
                raise ValueError(f"BAP {role} frame/QoS denominator mismatch")
            value_range = row[f"{role}_range"]
            lines = record.get(f"{role}_lines")
            if (not isinstance(value_range, list) or len(value_range) != 2 or
                    value_range[0] != previous_ends[role] or
                    not isinstance(lines, list) or
                    not value_range[0] < value_range[1] <= len(lines)):
                raise ValueError(f"BAP {role} transcript range mismatch")
            previous_ends[role] = value_range[1]
            parsed[role] = lines[value_range[0]:value_range[1]]
            if any(any(marker in line.lower() for marker in
                       ("failed", "fatal", "stack overflow", "*****"))
                   for line in parsed[role]):
                raise ValueError(f"BAP {role} transcript failure marker")
        client_markers = (
            ("LE Audio duplex client streaming", "streaming"),
            ("LE Audio stream stopped", "stopped"),
            ("LE Audio peer disconnected", "disconnected"),
        )
        client_positions = [
            [index for index, line in enumerate(parsed["client"]) if marker in line]
            for marker, _event in client_markers
        ]
        server_positions = [
            index for index, line in enumerate(parsed["server"])
            if "LE Audio duplex peer disconnected" in line
        ]
        observed_events = {
            "client": ([event for _marker, event in client_markers]
                       if all(len(values) == 1 for values in client_positions) and
                       [values[0] for values in client_positions] == sorted(
                           values[0] for values in client_positions
                       ) else []),
            "server": ["disconnected"] if len(server_positions) == 1 else [],
        }
        if observed_events != expected_events:
            raise ValueError("BAP raw lifecycle event mismatch")
        client_sent = [int(match.group(1)) for line in parsed["client"]
                       if (match := CLIENT_SENT.search(line))]
        client_received = [tuple(int(value) for value in match.groups())
                           for line in parsed["client"]
                           if (match := RECEIVED.search(line))]
        server_sent = [int(match.group(1)) for line in parsed["server"]
                       if (match := SERVER_SENT.search(line))]
        server_received = [tuple(int(value) for value in match.groups())
                           for line in parsed["server"]
                           if (match := RECEIVED.search(line))]
        if not all((client_sent, client_received, server_sent, server_received)):
            raise ValueError("BAP raw frame counter missing")
        raw_counters = {
            "client": {
                "sent_frames": max(client_sent),
                "received_frames": max(value[0] for value in client_received),
                "energy": client_received[-1][1],
                "dropped_frames": client_received[-1][2],
            },
            "server": {
                "sent_frames": max(server_sent) - server_totals["sent_frames"],
                "received_frames": max(value[0] for value in server_received) -
                server_totals["received_frames"],
                "energy": server_received[-1][1],
                "dropped_frames": server_received[-1][2],
            },
        }
        server_totals["sent_frames"] = max(server_sent)
        server_totals["received_frames"] = max(value[0] for value in server_received)
        if raw_counters != {role: row[role] for role in ("client", "server")}:
            raise ValueError("BAP raw counter differs from typed cycle")
    if any(previous_ends[role] != len(record[f"{role}_lines"])
           for role in previous_ends):
        raise ValueError("BAP transcript has unassigned trailing lines")


def _append_line(record: dict, role: str, line: str) -> str:
    """! @brief 주소를 제거한 bounded UART 행을 raw evidence에 추가합니다. """

    sanitized = ADDRESS.sub("<bt-address>", line[:400])
    record[f"{role}_lines"].append(sanitized)
    return sanitized


def _best_effort_cleanup(client, server, record: dict, state: dict,
                         timeout: float = 8.0) -> None:
    """! @brief 실패 경로에서도 stream STOP과 양쪽 ACL 해제를 유한하게 시도합니다. """

    attempted = not state["client_disconnected"] or not state["server_disconnected"]
    if attempted:
        try:
            client.write(b"s")
            client.flush()
        except Exception:
            pass
    deadline = time.monotonic() + timeout
    while attempted and time.monotonic() < deadline and not (
            state["client_disconnected"] and state["server_disconnected"]):
        for port, role in ((client, "client"), (server, "server")):
            try:
                line = port.readline().decode("utf-8", errors="replace").strip()
            except Exception:
                continue
            if not line:
                continue
            line = _append_line(record, role, line)
            if role == "client" and "LE Audio stream stopped" in line:
                state["client_stopped"] = True
            if role == "client" and "LE Audio peer disconnected" in line:
                state["client_disconnected"] = True
            if role == "server" and "LE Audio duplex peer disconnected" in line:
                state["server_disconnected"] = True
    record["cleanup"]["client"].update({
        "stop": "PASS" if state["client_stopped"] or state["client_disconnected"] else "FAIL",
        "acl": "PASS" if state["client_disconnected"] else "FAIL",
    })
    record["cleanup"]["server"].update({
        "stop": "PASS" if state["server_disconnected"] else "FAIL",
        "acl": "PASS" if state["server_disconnected"] else "FAIL",
    })


def _emergency_client_stop(client, record: dict) -> None:
    """! @brief 정상 cleanup 전에 빠져나온 client에도 STOP을 최선으로 전송합니다. """

    if record["cleanup"]["client"].get("stop") == "PASS":
        return
    try:
        client.write(b"s")
        client.flush()
    except Exception:
        pass


def _close_serial(port, record: dict, role: str) -> None:
    """! @brief 부분 open을 포함한 serial close 성공 여부를 역할별로 남깁니다. """

    try:
        port.close()
    except Exception:
        record["cleanup"][role]["serial_close"] = "FAIL"
    else:
        record["cleanup"][role]["serial_close"] = "PASS"


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
    if args.output.exists():
        parser.error("refusing to overwrite existing evidence")
    if not args.source_clean:
        parser.error("exact HIL requires --source-clean")
    for config in (args.client_config, args.server_config):
        lines = config.read_text(encoding="utf-8").splitlines()
        if "CONFIG_LIBLC3=y" not in lines or "CONFIG_FPU=y" not in lines:
            parser.error("both images require LC3 and FPU")
    verify_flash(args.client_flash_record, "client", args.client_image,
                 args.client_probe_sha256)
    verify_flash(args.server_flash_record, "server", args.server_image,
                 args.server_probe_sha256)
    build_records = {
        "client": validate_build_record(
            args.client_image, args.core_revision, LOCK["board"]["revision"],
            APPLICATIONS["client"],
        ),
        "server": validate_build_record(
            args.server_image, args.core_revision, LOCK["board"]["revision"],
            APPLICATIONS["server"],
        ),
    }
    revision = subprocess.check_output(
        ("git", "rev-parse", "HEAD"), cwd=ROOT, text=True, timeout=30
    ).strip()
    dirty = subprocess.check_output(
        ("git", "status", "--porcelain", "--untracked-files=all"),
        cwd=ROOT, text=True, timeout=30,
    ).strip()
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
        "cycle_seconds": [], "cycle_records": [],
        "client_lines": [], "server_lines": [],
        "build_records": build_records,
        "cleanup": {
            "client": {"stop": "NOT_RUN", "acl": "NOT_RUN", "serial_close": "NOT_RUN"},
            "server": {"stop": "NOT_RUN", "acl": "NOT_RUN", "serial_close": "NOT_RUN"},
        },
    }
    state = {
        "client_stopped": False,
        "client_disconnected": False,
        "server_disconnected": False,
    }
    client = None
    server = None
    try:
        with ProbeLocks([client_uid, server_uid]):
            with ExitStack() as serial_stack:
                client = serial.Serial(client_port, 115200, timeout=0.03)
                serial_stack.callback(_close_serial, client, record, "client")
                serial_stack.callback(_emergency_client_stop, client, record)
                server = serial.Serial(server_port, 115200, timeout=0.03)
                serial_stack.callback(_close_serial, server, record, "server")
                try:
                    client.reset_input_buffer()
                    server.reset_input_buffer()
                    hardware_reset(args.server_probe_sha256)
                    hardware_reset(args.client_probe_sha256)
                    client.reset_input_buffer()
                    server.reset_input_buffer()
                    cycle_started = time.monotonic()
                    server_rx_baseline = 0
                    server_tx_baseline = 0
                    server_rx = 0
                    server_tx = 0
                    client_sent = 0
                    client_rx = 0
                    client_energy = 0
                    client_drops = -1
                    server_energy = 0
                    server_drops = -1
                    streaming = False
                    stop_requested = False
                    events = {"client": [], "server": []}
                    cycle_line_start = {"client": 0, "server": 0}
                    while record["completed_cycles"] < args.cycles:
                        cycle = record["completed_cycles"] + 1
                        if time.monotonic() - cycle_started > 30.0:
                            raise RuntimeError(f"cycle {cycle} exceeded 30 seconds")
                        for port, role in ((client, "client"), (server, "server")):
                            line = port.readline().decode("utf-8", errors="replace").strip()
                            if not line:
                                continue
                            line = _append_line(record, role, line)
                            if ("failed" in line.lower() or "FATAL" in line or
                                    "Stack overflow" in line or "*****" in line):
                                raise RuntimeError(f"{role} error in cycle {cycle}: {line[:100]}")
                            if role == "client":
                                if "LE Audio duplex client streaming" in line:
                                    streaming = True
                                    state["client_disconnected"] = False
                                    state["server_disconnected"] = False
                                    events["client"].append("streaming")
                                if stop_requested and "LE Audio stream stopped" in line:
                                    state["client_stopped"] = True
                                    events["client"].append("stopped")
                                if state["client_stopped"] and "LE Audio peer disconnected" in line:
                                    state["client_disconnected"] = True
                                    events["client"].append("disconnected")
                                match = CLIENT_SENT.search(line)
                                if match:
                                    client_sent = max(client_sent, int(match.group(1)))
                                match = RECEIVED.search(line)
                                if match:
                                    count, client_energy, client_drops = (
                                        int(value) for value in match.groups()
                                    )
                                    if client_energy == 0 or client_drops != 0:
                                        raise RuntimeError("client LC3 energy/drop invalid")
                                    client_rx = max(client_rx, count)
                            else:
                                if "LE Audio duplex peer disconnected" in line:
                                    state["server_disconnected"] = True
                                    events["server"].append("disconnected")
                                match = SERVER_SENT.search(line)
                                if match:
                                    server_tx = max(server_tx, int(match.group(1)))
                                match = RECEIVED.search(line)
                                if match:
                                    count, server_energy, server_drops = (
                                        int(value) for value in match.groups()
                                    )
                                    if server_energy == 0 or server_drops != 0:
                                        raise RuntimeError("server LC3 energy/drop invalid")
                                    server_rx = max(server_rx, count)
                        if (streaming and not stop_requested and client_sent >= 100 and
                                client_rx >= 100 and server_rx >= server_rx_baseline + 100 and
                                server_tx >= server_tx_baseline + 100):
                            client.write(b"s")
                            client.flush()
                            stop_requested = True
                        if (stop_requested and state["client_stopped"] and
                                state["client_disconnected"] and state["server_disconnected"]):
                            elapsed = round(time.monotonic() - cycle_started, 3)
                            cycle_record = {
                                "cycle": cycle,
                                "status": "PASS",
                                "duration_seconds": elapsed,
                                "client": {
                                    "sent_frames": client_sent,
                                    "received_frames": client_rx,
                                    "energy": client_energy,
                                    "dropped_frames": client_drops,
                                },
                                "server": {
                                    "sent_frames": server_tx - server_tx_baseline,
                                    "received_frames": server_rx - server_rx_baseline,
                                    "energy": server_energy,
                                    "dropped_frames": server_drops,
                                },
                                "events": events,
                                "cleanup": "PASS",
                                "client_range": [cycle_line_start["client"],
                                                 len(record["client_lines"])],
                                "server_range": [cycle_line_start["server"],
                                                 len(record["server_lines"])],
                            }
                            record["cycle_records"].append(cycle_record)
                            record["completed_cycles"] = cycle
                            record["cycle_seconds"].append(elapsed)
                            print(f"M31_BAP_DUPLEX_CYCLE={cycle}/{args.cycles}", flush=True)
                            cycle_started = time.monotonic()
                            server_rx_baseline = server_rx
                            server_tx_baseline = server_tx
                            client_sent = 0
                            client_rx = 0
                            client_energy = 0
                            client_drops = -1
                            server_energy = 0
                            server_drops = -1
                            streaming = False
                            stop_requested = False
                            state["client_stopped"] = False
                            events = {"client": [], "server": []}
                            cycle_line_start = {
                                "client": len(record["client_lines"]),
                                "server": len(record["server_lines"]),
                            }
                finally:
                    _best_effort_cleanup(client, server, record, state)
        validate_cycle_records(record, args.cycles)
        if any(value != "PASS" for role in record["cleanup"].values()
               for value in role.values()):
            raise RuntimeError("BAP final cleanup incomplete")
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
