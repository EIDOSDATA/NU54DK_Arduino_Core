"""Measure connected CTE receive acceptance and actual IQ reports."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ble_pair_hil_common import flash_image_pyocd
from m6_serial_echo import import_pyserial
from m31_ble_capability_run import collect_register_identity, discover
from m31_cs_ras_pair_run import hardware_reset
from v04_protocol import ProbeLocks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--receiver-probe-sha256", required=True)
    parser.add_argument("--responder-probe-sha256", required=True)
    parser.add_argument("--receiver-image", type=Path, required=True)
    parser.add_argument("--responder-image", type=Path, required=True)
    parser.add_argument("--core-revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    serial, ports = import_pyserial()
    rx_uid, rx_volume, rx_port = discover(args.receiver_probe_sha256, ports)
    tx_uid, tx_volume, tx_port = discover(args.responder_probe_sha256, ports)
    if rx_uid == tx_uid or rx_port == tx_port:
        raise RuntimeError("role mapping overlap")
    record = {
        "status": "UNEXPECTED",
        "core_revision": args.core_revision,
        "receiver_probe_sha256": args.receiver_probe_sha256,
        "responder_probe_sha256": args.responder_probe_sha256,
        "receiver_port": rx_port,
        "responder_port": tx_port,
        "receiver_image_sha256": hashlib.sha256(args.receiver_image.read_bytes()).hexdigest(),
        "responder_image_sha256": hashlib.sha256(args.responder_image.read_bytes()).hexdigest(),
        "receiver_lines": [],
        "responder_lines": [],
    }
    try:
        with ProbeLocks([rx_uid, tx_uid]):
            record["receiver_registers"] = collect_register_identity(rx_uid, rx_volume)
            record["responder_registers"] = collect_register_identity(tx_uid, tx_volume)
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
                deadline = started + 60.0
                while time.monotonic() < deadline:
                    for port, key in ((receiver, "receiver_lines"),
                                      (responder, "responder_lines")):
                        line = port.readline().decode("utf-8", errors="replace").strip()
                        if line:
                            record[key].append(line[:400])
                    if any("DF_CONN|IQ|" in line for line in record["receiver_lines"]):
                        record["status"] = "IQ_REPORT_OBSERVED"
                        break
                    if any("DF_CONN|RAW_REQUEST|code=" in line
                           for line in record["receiver_lines"]):
                        break
                    if any("DF_CONN|RAW_RX_PARAM|code=" in line and
                           "code=0" not in line for line in record["receiver_lines"]):
                        break
                record["elapsed_s"] = round(time.monotonic() - started, 3)
                antenna = next((line for line in record["receiver_lines"]
                                if "DF_CONN|ANT_INFO|" in line), "")
                reception = next((line for line in record["receiver_lines"]
                                  if "DF_CONN|AOA_RX_ENABLE|" in line), "")
                raw_receiver = next((line for line in record["receiver_lines"]
                                     if "DF_CONN|RAW_RX_PARAM|" in line), "")
                raw_request = next((line for line in record["receiver_lines"]
                                    if "DF_CONN|RAW_REQUEST|" in line), "")
                if "DF_CONN|CONNECTED|error=0" not in record["receiver_lines"]:
                    raise RuntimeError("receiver did not connect")
                if "CTE responses enabled on connected peer" not in record["responder_lines"]:
                    raise RuntimeError("responder did not enable CTE")
                if "count=1" in antenna and "code=-22" in reception:
                    if "code=0" in raw_receiver and "code=0" in raw_request:
                        record["status"] = "CONTROLLER_ACCEPTED_HOST_REJECTED"
                    elif "code=0" in raw_receiver:
                        record["status"] = "CONTROLLER_RX_ACCEPTED_HOST_REJECTED"
                    else:
                        record["status"] = "HOST_SINGLE_ANTENNA_REJECTED"
                elif "code=0" in reception:
                    record["status"] = "RX_ENABLED_IQ_NOT_PROVEN"
    except Exception as error:
        record["failure_class"] = type(error).__name__
        detail = str(error).replace(rx_uid, "<probe>").replace(tx_uid, "<probe>")
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
        json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("M31_DF_CONNECTED_RX=" + record["status"])
    return 0 if record["status"] in {
        "IQ_REPORT_OBSERVED", "HOST_SINGLE_ANTENNA_REJECTED",
        "CONTROLLER_ACCEPTED_HOST_REJECTED",
        "CONTROLLER_RX_ACCEPTED_HOST_REJECTED",
        "RX_ENABLED_IQ_NOT_PROVEN",
    } else 1


if __name__ == "__main__":
    raise SystemExit(main())
