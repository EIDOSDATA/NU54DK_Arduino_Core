"""Reject a Ranging UUID advertiser with no GATT Ranging Service repeatedly."""

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
from m31_cs_ras_pair_run import collect_until, hardware_reset
from v04_protocol import ProbeLocks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--initiator-probe-sha256", required=True)
    parser.add_argument("--spoof-probe-sha256", required=True)
    parser.add_argument("--initiator-image", type=Path, required=True)
    parser.add_argument("--spoof-image", type=Path, required=True)
    parser.add_argument("--core-revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cycles", type=int, default=20)
    parser.add_argument("--reset-only", action="store_true")
    parser.add_argument("--source-clean", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.cycles <= 20:
        parser.error("cycles must be between 1 and 20")
    if args.source_clean:
        root = Path(__file__).resolve().parents[3]
        revision = subprocess.check_output(
            ("git", "rev-parse", "HEAD"), cwd=root, text=True
        ).strip()
        changed = subprocess.check_output(
            ("git", "status", "--porcelain"), cwd=root, text=True
        ).strip()
        if changed or args.core_revision != revision:
            parser.error("exact HIL requires clean source and full HEAD revision")

    serial, ports = import_pyserial()
    init_uid, init_volume, init_port = discover(args.initiator_probe_sha256, ports)
    spoof_uid, spoof_volume, spoof_port = discover(args.spoof_probe_sha256, ports)
    if init_uid == spoof_uid or init_port == spoof_port:
        raise RuntimeError("role mapping overlap")
    record = {
        "status": "FAIL",
        "test": "advertised_ranging_uuid_without_gatt_service",
        "core_revision": args.core_revision,
        "source_clean": args.source_clean,
        "initiator_probe_sha256": args.initiator_probe_sha256,
        "spoof_probe_sha256": args.spoof_probe_sha256,
        "initiator_port": init_port,
        "spoof_port": spoof_port,
        "initiator_image_sha256": hashlib.sha256(args.initiator_image.read_bytes()).hexdigest(),
        "spoof_image_sha256": hashlib.sha256(args.spoof_image.read_bytes()).hexdigest(),
        "cycles_expected": args.cycles,
        "cycles_rejected": 0,
        "disconnect_commands": 0,
        "mode": "hardware_reset_only" if args.reset_only else "sector_flash_pair_reset",
        "initiator_lines": [],
        "reflector_lines": [],
    }
    try:
        with ProbeLocks([init_uid, spoof_uid]):
            record["initiator_registers"] = collect_register_identity(init_uid, init_volume)
            record["spoof_registers"] = collect_register_identity(spoof_uid, spoof_volume)
            with serial.Serial(init_port, 115200, timeout=0.05) as initiator, \
                    serial.Serial(spoof_port, 115200, timeout=0.05) as spoof:
                initiator.reset_input_buffer()
                spoof.reset_input_buffer()
                if not args.reset_only:
                    record["spoof_flash"] = flash_image_pyocd(
                        "cs_missing_ras", spoof_uid, args.spoof_image,
                        120.0, hardware_reset=True
                    )
                    record["initiator_flash"] = flash_image_pyocd(
                        "cs_initiator", init_uid, args.initiator_image,
                        120.0, hardware_reset=True
                    )
                initiator.reset_input_buffer()
                spoof.reset_input_buffer()
                hardware_reset(spoof_uid)
                hardware_reset(init_uid)
                started = time.monotonic()
                for cycle in range(args.cycles):
                    if cycle > 0:
                        initiator.write(b"d")
                        initiator.flush()
                        record["disconnect_commands"] += 1
                    if not collect_until(
                        initiator, spoof, record,
                        [("i", "CS initiator connected; securing"),
                         ("i", "CS initiator failed: -2")], 30.0
                    ):
                        raise RuntimeError("missing GATT service not rejected")
                    if any("CS_RAW counter=" in line or "CS procedures requested" in line
                           for line in record["initiator_lines"]):
                        raise RuntimeError("spoof produced ranging output")
                    record["cycles_rejected"] = cycle + 1
                record["initiator_disconnects"] = sum(
                    "CS initiator disconnected" in line
                    for line in record["initiator_lines"]
                )
                record["spoof_disconnects"] = sum(
                    "CS missing service disconnected" in line
                    for line in record["reflector_lines"]
                )
                initiator_failures = sum(
                    "CS initiator failed: -2" in line
                    for line in record["initiator_lines"]
                )
                spoof_connections = sum(
                    "CS missing service connected" in line
                    for line in record["reflector_lines"]
                )
                record["initiator_failures"] = initiator_failures
                record["spoof_connections"] = spoof_connections
                if (initiator_failures != args.cycles or
                        spoof_connections < args.cycles or
                        record["initiator_disconnects"] < args.cycles - 1 or
                        record["spoof_disconnects"] < args.cycles - 1):
                    raise RuntimeError("reject or connection count mismatch")
                record["elapsed_s"] = round(time.monotonic() - started, 3)
                record["status"] = "PASS"
    except Exception as error:
        record["failure_class"] = type(error).__name__
        detail = str(error).replace(init_uid, "<probe>").replace(spoof_uid, "<probe>")
        record["failure_detail"] = re.sub(
            r"\b[0-9A-Fa-f]{16,}\b", "<probe>", detail[:120]
        )
    for key in ("initiator_lines", "reflector_lines"):
        record[key] = [
            re.sub(r"\b[0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5}\b",
                   "<bt-address>", line)
            for line in record[key]
        ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("M31_CS_MISSING_SERVICE=" + record["status"] +
          ";REJECTED=" + str(record["cycles_rejected"]))
    return 0 if record["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
