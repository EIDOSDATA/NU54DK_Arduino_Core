"""Check plaintext Ranging Features rejection, optionally on one ACL."""

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


def stop_client(client, reflector, record, timeout=5.0):
    """Request a bounded disconnect and preserve both UART transcripts."""
    client.write(b"s")
    client.flush()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for port, key in ((client, "client_lines"),
                          (reflector, "reflector_lines")):
            line = port.readline().decode("utf-8", errors="replace").strip()
            if line:
                record[key].append(line[:400])
                if (key == "client_lines" and
                        "CS insecure peer disconnected reason=" in line):
                    try:
                        reason = int(line.rsplit("=", 1)[1])
                    except ValueError:
                        reason = None
                    if (reason is not None and
                            reason not in record["disconnect_reasons"]):
                        record["disconnect_reasons"].append(reason)
        client_done = any(
            marker in line
            for line in record["client_lines"]
            for marker in (
                "CS insecure peer disconnected reason=",
                "CS insecure stop complete",
            )
        )
        reflector_done = (
            not any("CS insecure peer connected" in line
                    for line in record["client_lines"]) or
            any("CS reflector disconnected" in line
                for line in record["reflector_lines"])
        )
        if client_done and reflector_done:
            record["stop_confirmed"] = True
            return
    record["stop_confirmed"] = False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--client-probe-sha256", required=True)
    parser.add_argument("--reflector-probe-sha256", required=True)
    parser.add_argument("--client-image", type=Path, required=True)
    parser.add_argument("--reflector-image", type=Path, required=True)
    parser.add_argument("--core-revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-clean", action="store_true")
    parser.add_argument("--same-acl", action="store_true")
    parser.add_argument("--cycles", type=int, default=20)
    args = parser.parse_args()
    if not 1 <= args.cycles <= 20:
        parser.error("cycles must be between 1 and 20")
    if args.output.exists():
        parser.error("refusing to overwrite existing evidence")
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
        "mode": "same_acl" if args.same_acl else "separate_acl",
        "same_acl": args.same_acl,
        "connections": 0,
        "disconnect_reasons": [],
        "unexpected_disconnects": 0,
        "stop_confirmed": False,
        "read_timestamps_ms": [],
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
                campaign_deadline = started + 600.0
                pattern = re.compile(
                    r"CS insecure read rejected att=15 count=(\d+) ms=(\d+)"
                )
                disconnect_pattern = re.compile(
                    r"CS insecure peer disconnected reason=(\d+)"
                )
                run_error = None
                try:
                    for cycle in range(args.cycles):
                        if time.monotonic() >= campaign_deadline:
                            raise RuntimeError("campaign timeout")
                        if cycle > 0:
                            if args.same_acl:
                                time.sleep(0.1)
                                client.write(b"r")
                                client.flush()
                            else:
                                hardware_reset(client_uid)
                        first_line = len(record["client_lines"])
                        cycle_started = time.monotonic()
                        deadline = min(cycle_started + 60.0, campaign_deadline)
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
                                disconnect = disconnect_pattern.search(line)
                                if disconnect is not None:
                                    record["disconnect_reasons"].append(
                                        int(disconnect.group(1))
                                    )
                                    if args.same_acl:
                                        record["unexpected_disconnects"] += 1
                                        raise RuntimeError(
                                            "same-ACL client disconnected early"
                                        )
                                if any(marker in line for marker in (
                                    "CS insecure read ACCEPTED",
                                    "CS insecure unexpected att=",
                                    "CS insecure discovery failed",
                                    "CS insecure read start failed",
                                    "CS insecure scan failed",
                                    "CS insecure connect failed",
                                    "CS insecure retry rejected",
                                )):
                                    raise RuntimeError(
                                        "insecure client failed expected rejection"
                                    )
                                match = pattern.search(line)
                                if match is not None:
                                    expected = cycle + 1 if args.same_acl else 1
                                    count, timestamp = map(int, match.groups())
                                    if count != expected:
                                        raise RuntimeError("read counter mismatch")
                                    if (args.same_acl and
                                            record["read_timestamps_ms"] and
                                            timestamp - record[
                                                "read_timestamps_ms"
                                            ][-1] < 50):
                                        raise RuntimeError(
                                            "same-ACL retry pacing mismatch"
                                        )
                                    record["read_timestamps_ms"].append(
                                        timestamp
                                    )
                                    found = True
                        recent = record["client_lines"][first_line:]
                        if not found:
                            raise RuntimeError(
                                "plaintext RAS rejection cycle incomplete"
                            )
                        if args.same_acl and cycle > 0 and not any(
                            "CS insecure retry requested" in line
                            for line in recent
                        ):
                            raise RuntimeError("same-ACL retry was not accepted")
                        if not args.same_acl and not all(any(
                            marker in line for line in recent
                        ) for marker in (
                            "CS insecure peer connected",
                            "CS insecure RAS discovered",
                        )):
                            raise RuntimeError(
                                "separate-ACL connection cycle incomplete"
                            )
                        record["rejected"] = cycle + 1
                        record["cycles"].append({
                            "cycle": cycle + 1,
                            "elapsed_s": round(
                                time.monotonic() - cycle_started, 3
                            ),
                        })
                except Exception as error:
                    run_error = error
                finally:
                    stop_client(client, reflector, record)
                if run_error is not None:
                    raise run_error
                if not record["stop_confirmed"]:
                    raise RuntimeError("insecure client STOP incomplete")
                record["connections"] = sum(
                    "CS insecure peer connected count=" in line
                    for line in record["client_lines"]
                )
                if args.same_acl:
                    if record["connections"] != 1:
                        raise RuntimeError("same-ACL connection count mismatch")
                    if sum("CS insecure RAS discovered" in line
                           for line in record["client_lines"]) != 1:
                        raise RuntimeError("same-ACL discovery count mismatch")
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
