"""Measure connected CTE command, controller-event, and raw-IQ boundaries."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ble_pair_hil_common import flash_image_pyocd
from m6_serial_echo import import_pyserial
from m31_ble_capability_run import collect_register_identity, discover
from m31_cs_ras_pair_run import hardware_reset
from v04_protocol import ProbeLocks


IQ_PATTERN = re.compile(
    r"error=(\d+)\|count=(\d+)\|type=(\d+)\|status=(\d+)\|"
    r"sample_type=(\d+)\|slot=(\d+)\|event=(\d+)\|channel=(\d+)\|"
    r"i0=(-?\d+)\|q0=(-?\d+)\|rssi=(-?\d+)"
)
HOST_STATE_ARMED = "DF_CONN|HOST_RX_STATE|enabled=1|params=1|cte_types=1"
HOST_STATE_DISARMED = "DF_CONN|HOST_RX_STATE|enabled=0|params=1|cte_types=0"
VALID_PACKET_STATUSES = {0, 1, 2, 255}


def append_line(port, key, record):
    """Read and retain one bounded UART line."""
    line = port.readline().decode("utf-8", errors="replace").strip()
    if line:
        record[key].append(line[:400])
    return line


def stop_pair(receiver, responder, record, timeout=10.0):
    """Disable receiver procedures first, then release the responder."""
    receiver.write(b"s")
    receiver.flush()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        append_line(receiver, "receiver_lines", record)
        append_line(responder, "responder_lines", record)
        if (any("DF_CONN|STOPPED" in line
                for line in record["receiver_lines"]) and
                any("CTE peer disconnected" in line
                    for line in record["responder_lines"])):
            break
    responder.write(b"s")
    responder.flush()
    responder_deadline = time.monotonic() + 1.0
    while time.monotonic() < responder_deadline:
        append_line(receiver, "receiver_lines", record)
        append_line(responder, "responder_lines", record)
    connected = any("DF_CONN|CONNECTED|error=0" in line
                    for line in record["receiver_lines"])
    stop_codes = {
        "request_disabled": any("DF_CONN|RAW_REQUEST_STOP|code=0" in line
                                for line in record["receiver_lines"]),
        "sampling_disabled": any("DF_CONN|RAW_RX_STOP|code=0" in line
                                 for line in record["receiver_lines"]),
        "disconnect_requested": any(
            "DF_CONN|DISCONNECT_REQUEST|code=0" in line
            for line in record["receiver_lines"]
        ),
        "receiver_stopped": any("DF_CONN|STOPPED" in line
                                for line in record["receiver_lines"]),
        "host_state_disarmed": any(HOST_STATE_DISARMED in line
                                   for line in record["receiver_lines"]),
        "responder_stopped": any(
            "CTE responses stopped" in line
            for line in record["responder_lines"]
        ),
        "responder_disconnected": any(
            "CTE peer disconnected" in line
            for line in record["responder_lines"]
        ),
    }
    required = ("receiver_stopped",)
    if connected:
        required = (
            "request_disabled",
            "sampling_disabled",
            "host_state_disarmed",
            "disconnect_requested",
            "receiver_stopped",
            "responder_disconnected",
        )
    record["cleanup"] = stop_codes
    record["cleanup_confirmed"] = all(stop_codes[key] for key in required)


def validate_source(parser, args):
    """Bind a requested exact run to the current clean commit."""
    if not args.source_clean:
        return
    root = Path(__file__).resolve().parents[3]
    revision = subprocess.check_output(
        ("git", "rev-parse", "HEAD"), cwd=root, text=True
    ).strip()
    changed = subprocess.check_output(
        ("git", "status", "--porcelain"), cwd=root, text=True
    ).strip()
    if changed or args.core_revision != revision:
        parser.error("exact HIL requires clean source and full HEAD revision")


def classify(record):
    """Keep command acceptance, controller event, and raw IQ scopes separate."""
    antenna = next((line for line in record["receiver_lines"]
                    if "DF_CONN|ANT_INFO|" in line), "")
    reception = next((line for line in record["receiver_lines"]
                      if "DF_CONN|AOA_RX_ENABLE|" in line), "")
    raw_receiver = next((line for line in record["receiver_lines"]
                         if "DF_CONN|RAW_RX_PARAM|" in line), "")
    raw_request = next((line for line in record["receiver_lines"]
                        if "DF_CONN|RAW_REQUEST|" in line), "")
    host_state_armed = any(HOST_STATE_ARMED in line
                           for line in record["receiver_lines"])
    command_accepted = (
        ("code=0" in raw_receiver) and
        ("code=0" in raw_request) and
        host_state_armed
    )
    controller_events = (
        record["host_iq_callbacks"] + record["host_gate_drops"]
    )
    record["controller_iq_events"] = controller_events
    record["path_results"] = {
        "connected_controller_commands": (
            "PASS" if command_accepted else "HOLD"
        ),
        "connected_controller_iq_event": (
            "PASS" if controller_events > 0 else "HOLD"
        ),
        "connected_host_callback": (
            "PASS" if record["host_iq_callbacks"] > 0 else "HOLD"
        ),
        "connected_raw_iq_samples": (
            "PASS" if record["iq_reports"] >= 20 else "HOLD"
        ),
        "connectionless_controller_commands": "NOT RUN",
        "connectionless_controller_iq_event": "NOT RUN",
        "connectionless_host_callback": "NOT RUN",
        "connectionless_raw_iq_samples": "NOT RUN",
        "antenna_switching": "NOT RUN",
        "angle_measurement": "NOT RUN",
        "external_rf_path": "NOT RUN",
    }
    if not any("DF_CONN|CONNECTED|error=0" in line
               for line in record["receiver_lines"]):
        raise RuntimeError("receiver did not connect")
    if not any("CTE responses enabled on connected peer" in line
               for line in record["responder_lines"]):
        raise RuntimeError("responder did not enable CTE")
    if record["iq_reports"] >= 20:
        record["status"] = "PASS"
        record["outcome"] = "CONNECTED_RAW_IQ_OBSERVED"
        record["raw_iq_rx"] = "PASS"
    elif record["host_iq_callbacks"] > 0:
        record["status"] = "HOLD"
        record["outcome"] = "HOST_CALLBACK_WITHOUT_20_VALID_IQ_REPORTS"
        record["raw_iq_rx"] = "HOLD"
    elif record["host_gate_drops"] > 0:
        record["status"] = "HOLD"
        record["outcome"] = "CONTROLLER_IQ_EVENT_HOST_DROPPED"
        record["raw_iq_rx"] = "HOLD"
    elif command_accepted:
        record["status"] = "HOLD"
        record["outcome"] = "COMMANDS_ACCEPTED_IQ_NOT_OBSERVED"
        record["raw_iq_rx"] = "HOLD"
    elif ("count=1" in antenna) and ("code=-22" in reception):
        record["status"] = "HOLD"
        record["outcome"] = "HOST_SINGLE_ANTENNA_REJECTED"
        record["raw_iq_rx"] = "NOT RUN"
    elif "code=0" in reception:
        record["status"] = "HOLD"
        record["outcome"] = "HOST_RX_ENABLED_IQ_NOT_OBSERVED"
        record["raw_iq_rx"] = "HOLD"
    else:
        raise RuntimeError("unclassified connected CTE result")


def record_iq_line(record, line):
    """Validate one Host callback without upgrading unusable samples to PASS."""
    match = IQ_PATTERN.search(line)
    if match is None:
        raise RuntimeError("malformed IQ report")
    values = tuple(map(int, match.groups()))
    (error, count, cte_type, status, sample_type, slot, event, channel,
     first_i, first_q, rssi) = values
    if error not in (0, 1, 2):
        raise RuntimeError("invalid IQ callback error")
    if error == 0 and (
        cte_type != 1 or status not in VALID_PACKET_STATUSES or
        sample_type != 0 or slot != 2 or not 0 <= channel <= 36 or
        not -128 <= first_i <= 127 or not -128 <= first_q <= 127 or
        not -1270 <= rssi <= 200
    ):
        raise RuntimeError("invalid IQ report")
    if error == 0 and event in record["iq_event_counters"]:
        raise RuntimeError("duplicate IQ event counter")

    record["host_iq_callbacks"] += 1
    status_key = str(status)
    record["iq_packet_status_counts"][status_key] = (
        record["iq_packet_status_counts"].get(status_key, 0) + 1
    )
    if error == 0:
        record["iq_event_counters"].append(event)
    if error == 0 and status == 0 and count > 0:
        record["iq_reports"] += 1
        record["iq_samples"] += count


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--receiver-probe-sha256", required=True)
    parser.add_argument("--responder-probe-sha256", required=True)
    parser.add_argument("--receiver-image", type=Path, required=True)
    parser.add_argument("--responder-image", type=Path, required=True)
    parser.add_argument("--core-revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-clean", action="store_true")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("refusing to overwrite existing evidence")
    validate_source(parser, args)

    serial, ports = import_pyserial()
    rx_uid, rx_volume, rx_port = discover(args.receiver_probe_sha256, ports)
    tx_uid, tx_volume, tx_port = discover(args.responder_probe_sha256, ports)
    if rx_uid == tx_uid or rx_port == tx_port:
        raise RuntimeError("role mapping overlap")
    record = {
        "status": "FAIL",
        "outcome": "UNEXPECTED",
        "scope": "connected_raw_iq_rx",
        "raw_iq_rx": "NOT RUN",
        "angle_measurement": "NOT RUN",
        "core_revision": args.core_revision,
        "receiver_probe_sha256": args.receiver_probe_sha256,
        "responder_probe_sha256": args.responder_probe_sha256,
        "receiver_port": rx_port,
        "responder_port": tx_port,
        "receiver_image_sha256": hashlib.sha256(
            args.receiver_image.read_bytes()
        ).hexdigest(),
        "responder_image_sha256": hashlib.sha256(
            args.responder_image.read_bytes()
        ).hexdigest(),
        "source_clean": args.source_clean,
        "iq_reports": 0,
        "iq_samples": 0,
        "iq_event_counters": [],
        "host_iq_callbacks": 0,
        "controller_iq_events": 0,
        "host_gate_drops": 0,
        "iq_packet_status_counts": {},
        "cleanup_confirmed": False,
        "receiver_lines": [],
        "responder_lines": [],
    }
    try:
        with ProbeLocks([rx_uid, tx_uid]):
            record["receiver_registers"] = collect_register_identity(
                rx_uid, rx_volume
            )
            record["responder_registers"] = collect_register_identity(
                tx_uid, tx_volume
            )
            with serial.Serial(rx_port, 115200, timeout=0.05) as receiver, \
                    serial.Serial(tx_port, 115200, timeout=0.05) as responder:
                receiver.reset_input_buffer()
                responder.reset_input_buffer()
                record["responder_flash"] = flash_image_pyocd(
                    "df_connected_responder", tx_uid, args.responder_image,
                    120.0, hardware_reset=True
                )
                record["receiver_flash"] = flash_image_pyocd(
                    "df_connected_receiver", rx_uid, args.receiver_image,
                    120.0, hardware_reset=True
                )
                hardware_reset(tx_uid)
                hardware_reset(rx_uid)
                started = time.monotonic()
                run_error = None
                try:
                    deadline = started + 60.0
                    while time.monotonic() < deadline:
                        for port, key in ((receiver, "receiver_lines"),
                                          (responder, "responder_lines")):
                            line = append_line(port, key, record)
                            if key != "receiver_lines" or not line:
                                continue
                            if "DF_CONN|IQ|" in line:
                                record_iq_line(record, line)
                            if (
                                "Received conn CTE report when CTE receive disabled"
                                in line
                            ):
                                record["host_gate_drops"] += 1
                        if record["iq_reports"] >= 20:
                            break
                        if any("DF_CONN|RAW_RX_PARAM|code=" in item and
                               "code=0" not in item
                               for item in record["receiver_lines"]):
                            break
                    record["elapsed_s"] = round(
                        time.monotonic() - started, 3
                    )
                    classify(record)
                except Exception as error:
                    run_error = error
                finally:
                    stop_pair(receiver, responder, record)
                if run_error is not None:
                    raise run_error
                if not record["cleanup_confirmed"]:
                    raise RuntimeError("DF cleanup contract incomplete")
    except Exception as error:
        record["status"] = "FAIL"
        record["failure_class"] = type(error).__name__
        detail = str(error).replace(rx_uid, "<probe>").replace(
            tx_uid, "<probe>"
        )
        record["failure_detail"] = re.sub(
            r"\b[0-9A-Fa-f]{16,}\b", "<probe>", detail[:120]
        )
    for key in ("receiver_lines", "responder_lines"):
        record[key] = [
            re.sub(r"\b[0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5}\b",
                   "<bt-address>", line)
            for line in record[key]
        ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8"
    )
    print(
        "M31_DF_CONNECTED_RX=" + record["status"] +
        ";OUTCOME=" + record["outcome"]
    )
    return 0 if record["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
