"""Check that a same-name, wrong-service advertiser is not selected."""

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
    for role in ("initiator", "reflector", "wrong"):
        parser.add_argument(f"--{role}-probe-sha256", required=True)
        parser.add_argument(f"--{role}-image", type=Path, required=True)
    parser.add_argument("--core-revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    serial, ports = import_pyserial()
    role_map = {}
    for role in ("initiator", "reflector", "wrong"):
        role_map[role] = discover(getattr(args, f"{role}_probe_sha256"), ports)
    if len({value[0] for value in role_map.values()}) != 3 or \
            len({value[2] for value in role_map.values()}) != 3:
        raise RuntimeError("three role mappings overlap")
    record = {
        "status": "FAIL",
        "core_revision": args.core_revision,
        "test": "same_name_wrong_service_third_peer",
        "procedures": 0,
    }
    for role, (_, _, port) in role_map.items():
        record[f"{role}_probe_sha256"] = getattr(args, f"{role}_probe_sha256")
        record[f"{role}_port"] = port
        record[f"{role}_image_sha256"] = hashlib.sha256(
            getattr(args, f"{role}_image").read_bytes()
        ).hexdigest()
        record[f"{role}_lines"] = []
    try:
        with ProbeLocks([value[0] for value in role_map.values()]):
            for role, (uid, volume, _) in role_map.items():
                record[f"{role}_registers"] = collect_register_identity(uid, volume)
            with serial.Serial(role_map["initiator"][2], 115200, timeout=0.05) as initiator, \
                    serial.Serial(role_map["reflector"][2], 115200, timeout=0.05) as reflector, \
                    serial.Serial(role_map["wrong"][2], 115200, timeout=0.05) as wrong:
                for port in (initiator, reflector, wrong):
                    port.reset_input_buffer()
                record["wrong_flash"] = flash_image_pyocd(
                    "cs_wrong_peer", role_map["wrong"][0], args.wrong_image,
                    120.0, hardware_reset=True
                )
                hardware_reset(role_map["reflector"][0])
                hardware_reset(role_map["initiator"][0])
                started = time.monotonic()
                deadline = started + 120.0
                while time.monotonic() < deadline and record["procedures"] < 100:
                    for role, port in (("initiator", initiator),
                                       ("reflector", reflector), ("wrong", wrong)):
                        line = port.readline().decode("utf-8", errors="replace").strip()
                        if line:
                            if role == "wrong" and "CS wrong peer advertising" in line:
                                line = "CS wrong peer advertising"
                            record[f"{role}_lines"].append(line[:400])
                            if role == "initiator" and line.startswith("CS_RAW counter="):
                                record["procedures"] += 1
                            if role == "wrong" and "wrong peer connected" in line:
                                raise RuntimeError("wrong peer accepted")
                record["elapsed_s"] = round(time.monotonic() - started, 3)
                raw = [line for line in record["initiator_lines"]
                       if line.startswith("CS_RAW counter=")]
                counters = [int(re.search(r"counter=(\d+)", line).group(1))
                            for line in raw]
                if counters != list(range(100)):
                    raise RuntimeError("100 ranging counters missing")
                if not any("wrong peer advertising" in line
                           for line in record["wrong_lines"]):
                    raise RuntimeError("wrong peer advertisement not observed")
                if not any("CS reflector connected" in line
                           for line in record["reflector_lines"]):
                    raise RuntimeError("reflector connection not observed")
                if not all(re.search(r"local=(\d+) peer=\1 .*valid_rtt=[1-9]", line)
                           for line in raw):
                    raise RuntimeError("raw result mismatch")
                record["status"] = "PASS"
    except Exception as error:
        record["failure_class"] = type(error).__name__
        detail = str(error)
        for uid, _, _ in role_map.values():
            detail = detail.replace(uid, "<probe>")
        record["failure_detail"] = re.sub(
            r"\b[0-9A-Fa-f]{16,}\b", "<probe>", detail[:120]
        )
    for role in role_map:
        record[f"{role}_lines"] = [
            re.sub(r"\b[0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5}\b",
                   "<bt-address>", line)
            for line in record[f"{role}_lines"]
        ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("M31_CS_WRONG_PEER=" + record["status"] +
          ";PROCEDURES=" + str(record["procedures"]))
    return 0 if record["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
