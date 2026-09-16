"""Run an exact-image Arduino RAS pair procedure and recovery check."""

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
from v04_protocol import ProbeLocks


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def hardware_reset(uid):
    command = [
        sys.executable, "-I", "-m", "pyocd", "reset", "--uid", uid,
        "--target", "nrf54l", "--frequency", "500000", "--connect",
        "under-reset", "-O", "cmsis_dap.limit_packets=true", "-O",
        "cmsis_dap.prefer_v1=false", "-O", "auto_unlock=false",
        "--method", "hw",
    ]
    completed = subprocess.run(command, capture_output=True, timeout=30)
    if completed.returncode != 0:
        raise RuntimeError("hardware reset failed")


def collect_until(initiator, reflector, record, expected, timeout):
    first_initiator = len(record["initiator_lines"])
    first_reflector = len(record["reflector_lines"])
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for port, key in ((initiator, "initiator_lines"),
                          (reflector, "reflector_lines")):
            line = port.readline().decode("utf-8", errors="replace").strip()
            if line:
                record[key].append(line[:400])
        recent = {
            "i": record["initiator_lines"][first_initiator:],
            "r": record["reflector_lines"][first_reflector:],
        }
        if all(any(phrase in line for line in recent[role])
               for role, phrase in expected):
            return True
    return False


def read_procedures(initiator, reflector, record, count, timeout):
    pattern = re.compile(
        r"^CS_RAW counter=(\d+) local=(\d+) peer=(\d+) rtt=(\d+) "
        r"tone=(\d+) valid_rtt=(\d+) distance_m=([0-9.]+)$"
    )
    deadline = time.monotonic() + timeout
    previous_counter = None
    while time.monotonic() < deadline and record["procedures"] < count:
        for port, key in ((initiator, "initiator_lines"),
                          (reflector, "reflector_lines")):
            line = port.readline().decode("utf-8", errors="replace").strip()
            if not line:
                continue
            record[key].append(line[:400])
            if key != "initiator_lines":
                continue
            match = pattern.match(line)
            if match is None:
                if line.startswith("CS_RAW"):
                    raise RuntimeError("malformed ranging output")
                continue
            counter, local, peer, rtt, tone, valid, distance = match.groups()
            counter, local, peer, rtt, tone, valid = map(
                int, (counter, local, peer, rtt, tone, valid)
            )
            if (previous_counter is not None and
                    counter != ((previous_counter + 1) & 0xFFFF)):
                raise RuntimeError("ranging counter gap")
            if not (local == peer and local > 0 and rtt > 0 and tone > 0 and
                    0 < valid <= rtt and 0.0 <= float(distance) < 1000.0):
                raise RuntimeError("invalid ranging result")
            previous_counter = counter
            record["procedures"] += 1
    if record["procedures"] != count:
        raise RuntimeError("procedure count timeout")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--initiator-probe-sha256", required=True)
    parser.add_argument("--reflector-probe-sha256", required=True)
    parser.add_argument("--initiator-image", type=Path, required=True)
    parser.add_argument("--reflector-image", type=Path, required=True)
    parser.add_argument("--core-revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--flash", action="store_true")
    parser.add_argument("--post-flash-reset", action="store_true")
    parser.add_argument("--disconnect-cycles", type=int, default=0)
    parser.add_argument("--procedures", type=int, default=100)
    parser.add_argument("--procedure-timeout", type=float, default=600.0)
    args = parser.parse_args()
    if args.disconnect_cycles < 0 or args.disconnect_cycles > 20:
        parser.error("disconnect cycles must be between 0 and 20")
    if args.procedures < 1 or args.procedures > 100:
        parser.error("procedures must be between 1 and 100")
    if args.procedure_timeout <= 0.0 or args.procedure_timeout > 600.0:
        parser.error("procedure timeout must be within 600 seconds")
    if args.post_flash_reset and not args.flash:
        parser.error("post-flash reset requires flash")
    serial, ports = import_pyserial()
    init_uid, init_volume, init_port = discover(args.initiator_probe_sha256, ports)
    refl_uid, refl_volume, refl_port = discover(args.reflector_probe_sha256, ports)
    if init_uid == refl_uid or init_port == refl_port:
        raise RuntimeError("role mapping overlap")
    record = {
        "status": "FAIL",
        "core_revision": args.core_revision,
        "initiator_probe_sha256": args.initiator_probe_sha256,
        "reflector_probe_sha256": args.reflector_probe_sha256,
        "initiator_image_sha256": sha256(args.initiator_image),
        "reflector_image_sha256": sha256(args.reflector_image),
        "initiator_port": init_port,
        "reflector_port": refl_port,
        "mode": ("sector_flash_pair_reset" if args.post_flash_reset else
                 "sector_flash_and_reset" if args.flash else "hardware_reset_only"),
        "procedures": 0,
        "stop_restart_cycles": 0,
        "disconnect_reconnect_cycles": 0,
        "initiator_lines": [],
        "reflector_lines": [],
    }
    try:
        with ProbeLocks([init_uid, refl_uid]):
            record["initiator_registers"] = collect_register_identity(
                init_uid, init_volume
            )
            record["reflector_registers"] = collect_register_identity(
                refl_uid, refl_volume
            )
            with serial.Serial(init_port, 115200, timeout=0.05) as initiator, \
                    serial.Serial(refl_port, 115200, timeout=0.05) as reflector:
                initiator.reset_input_buffer()
                reflector.reset_input_buffer()
                if args.flash:
                    record["reflector_flash"] = flash_image_pyocd(
                        "cs_reflector", refl_uid, args.reflector_image,
                        120.0, hardware_reset=True
                    )
                    record["initiator_flash"] = flash_image_pyocd(
                        "cs_initiator", init_uid, args.initiator_image,
                        120.0, hardware_reset=True
                    )
                    if args.post_flash_reset:
                        initiator.reset_input_buffer()
                        reflector.reset_input_buffer()
                        hardware_reset(refl_uid)
                        hardware_reset(init_uid)
                else:
                    hardware_reset(refl_uid)
                    hardware_reset(init_uid)
                started = time.monotonic()
                read_procedures(initiator, reflector, record,
                                args.procedures, args.procedure_timeout)
                record["procedure_elapsed_s"] = round(
                    time.monotonic() - started, 3
                )
                for cycle in range(20):
                    initiator.write(b"s")
                    initiator.flush()
                    if not collect_until(
                        initiator, reflector, record,
                        [("i", "CS procedures stop requested"),
                         ("r", "CS procedures disabled")], 8.0
                    ):
                        raise RuntimeError("stop confirmation timeout")
                    initiator.write(b"r")
                    initiator.flush()
                    if not collect_until(
                        initiator, reflector, record,
                        [("i", "CS procedures restart requested"),
                         ("r", "CS procedures enabled"),
                         ("i", "CS_RAW counter=")], 8.0
                    ):
                        raise RuntimeError("restart confirmation timeout")
                    record["stop_restart_cycles"] = cycle + 1
                for cycle in range(args.disconnect_cycles):
                    initiator.write(b"d")
                    initiator.flush()
                    if not collect_until(
                        initiator, reflector, record,
                        [("i", "CS disconnect requested"),
                         ("i", "CS initiator disconnected"),
                         ("r", "CS reflector disconnected"),
                         ("i", "CS initiator connected; securing"),
                         ("r", "CS reflector connected"),
                         ("i", "CS_RAW counter=")], 30.0
                    ):
                        raise RuntimeError("disconnect recovery timeout")
                    record["disconnect_reconnect_cycles"] = cycle + 1
                record["status"] = "PASS"
    except Exception as error:
        record["failure_class"] = type(error).__name__
        detail = str(error).replace(init_uid, "<probe>").replace(refl_uid, "<probe>")
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
    print("M31_CS_RAS_PAIR=" + record["status"] +
          ";PROCEDURES=" + str(record["procedures"]) +
          ";CYCLES=" + str(record["stop_restart_cycles"]) +
          ";RECONNECTS=" + str(record["disconnect_reconnect_cycles"]))
    return 0 if record["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
