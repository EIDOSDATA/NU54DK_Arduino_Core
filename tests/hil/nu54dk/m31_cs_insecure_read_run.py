"""Check that 20 plaintext Ranging Features reads fail with ATT encryption error."""

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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--client-probe-sha256", required=True)
    parser.add_argument("--reflector-probe-sha256", required=True)
    parser.add_argument("--client-image", type=Path, required=True)
    parser.add_argument("--reflector-image", type=Path, required=True)
    parser.add_argument("--core-revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-clean", action="store_true")
    parser.add_argument("--cycles", type=int, default=20)
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
    client_uid, client_volume, client_port = discover(args.client_probe_sha256, ports)
    reflector_uid, reflector_volume, reflector_port = discover(
        args.reflector_probe_sha256, ports
    )
    if client_uid == reflector_uid or client_port == reflector_port:
        raise RuntimeError("role mapping overlap")
    record = {
        "status": "FAIL",
        "test": "unencrypted_ranging_features_read_20",
        "source_clean": args.source_clean,
        "core_revision": args.core_revision,
        "client_probe_sha256": args.client_probe_sha256,
        "reflector_probe_sha256": args.reflector_probe_sha256,
        "client_port": client_port,
        "reflector_port": reflector_port,
        "client_image_sha256": hashlib.sha256(args.client_image.read_bytes()).hexdigest(),
        "reflector_image_sha256": hashlib.sha256(args.reflector_image.read_bytes()).hexdigest(),
        "cycles_expected": args.cycles,
        "rejected": 0,
        "cycles": [],
        "client_lines": [],
        "reflector_lines": [],
    }
    try:
        with ProbeLocks([client_uid, reflector_uid]):
            record["client_registers"] = collect_register_identity(
                client_uid, client_volume
            )
            record["reflector_registers"] = collect_register_identity(
                reflector_uid, reflector_volume
            )
            with serial.Serial(client_port, 115200, timeout=0.05) as client, \
                    serial.Serial(reflector_port, 115200, timeout=0.05) as reflector:
                client.reset_input_buffer()
                reflector.reset_input_buffer()
                record["reflector_flash"] = flash_image_pyocd(
                    "cs_reflector", reflector_uid, args.reflector_image,
                    120.0, hardware_reset=True
                )
                record["client_flash"] = flash_image_pyocd(
                    "cs_insecure_client", client_uid, args.client_image,
                    120.0, hardware_reset=True
                )
                client.reset_input_buffer()
                reflector.reset_input_buffer()
                hardware_reset(reflector_uid)
                hardware_reset(client_uid)
                started = time.monotonic()
                pattern = re.compile(r"CS insecure read rejected att=15 count=(\d+)")
                for cycle in range(args.cycles):
                    if cycle > 0:
                        hardware_reset(client_uid)
                    first_line = len(record["client_lines"])
                    cycle_started = time.monotonic()
                    deadline = cycle_started + 45.0
                    found = False
                    while time.monotonic() < deadline and not found:
                        for port, key in ((client, "client_lines"),
                                          (reflector, "reflector_lines")):
                            line = port.readline().decode(
                                "utf-8", errors="replace"
                            ).strip()
                            if not line:
                                continue
                            record[key].append(line[:400])
                            if key != "client_lines":
                                continue
                            if any(marker in line for marker in (
                                "CS insecure read ACCEPTED",
                                "CS insecure unexpected att=",
                                "CS insecure discovery failed",
                                "CS insecure read start failed",
                                "CS insecure scan failed",
                                "CS insecure connect failed",
                            )):
                                raise RuntimeError("insecure client failed expected rejection")
                            match = pattern.search(line)
                            if match is not None:
                                if int(match.group(1)) != 1:
                                    raise RuntimeError("single-read counter mismatch")
                                found = True
                    recent = record["client_lines"][first_line:]
                    if not found or not any(
                        "CS insecure peer connected" in line for line in recent
                    ) or not any(
                        "CS insecure RAS discovered" in line for line in recent
                    ):
                        raise RuntimeError("plaintext RAS rejection cycle incomplete")
                    record["rejected"] = cycle + 1
                    record["cycles"].append({
                        "cycle": cycle + 1,
                        "elapsed_s": round(time.monotonic() - cycle_started, 3),
                    })
                record["elapsed_s"] = round(time.monotonic() - started, 3)
                if any("CS reflector secure L2" in line
                       for line in record["reflector_lines"]):
                    raise RuntimeError("reflector link became encrypted")
                record["status"] = "PASS"
    except Exception as error:
        record["failure_class"] = type(error).__name__
        detail = str(error).replace(client_uid, "<probe>")
        detail = detail.replace(reflector_uid, "<probe>")
        record["failure_detail"] = re.sub(
            r"\b[0-9A-Fa-f]{16,}\b", "<probe>", detail[:120]
        )
    for key in ("client_lines", "reflector_lines"):
        record[key] = [
            re.sub(r"\b[0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5}\b",
                   "<bt-address>", line)
            for line in record[key]
        ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("M31_CS_INSECURE_READ=" + record["status"] +
          ";REJECTED=" + str(record["rejected"]))
    return 0 if record["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
