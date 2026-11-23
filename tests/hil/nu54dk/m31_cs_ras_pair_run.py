"""Run an exact-image Arduino RAS pair procedure and recovery check."""

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

from ble_pair_hil_common import (
    flash_image_pyocd,
    reset_target_pyocd_sha256,
    validate_build_record,
)
from m6_serial_echo import import_pyserial
from m31_ble_capability_run import collect_register_identity, discover
from v04_protocol import ProbeLocks


ROOT = Path(__file__).resolve().parents[3]
LOCK = json.loads((ROOT / "tools/ci/ncs-3.4.0.lock.json").read_text(encoding="utf-8"))
APPLICATIONS = {
    "initiator": ROOT / "libraries/NUCODE_BLE_ChannelSounding/examples/RasInitiator",
    "reflector": ROOT / "libraries/NUCODE_BLE_ChannelSounding/examples/RasReflector",
}
CS_RAW = re.compile(
    r"^CS_RAW counter=(\d+) local=(\d+) peer=(\d+) rtt=(\d+) "
    r"tone=(\d+) valid_rtt=(\d+) distance_m=([0-9.]+)$"
)


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def hardware_reset(probe_sha256: str):
    """! @brief SHA-256 probe에 software reset만 수행합니다. """

    reset_target_pyocd_sha256("cs", probe_sha256, 30.0)


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


def collect_stable_quiescence(initiator, reflector, record,
                              timeout: float = 2.0) -> bool:
    """! @brief quiesce ACK 뒤 재연결·CS·radio 재시작이 없는 bounded 구간을 검사합니다. """

    forbidden = {
        "initiator_lines": (
            "CS initiator connected", "CS_RAW counter=", "CS procedures requested",
            "scan restart failed",
        ),
        "reflector_lines": (
            "CS reflector connected", "CS procedures enabled",
            "CS reflector advertising",
        ),
    }
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for port, key in ((initiator, "initiator_lines"),
                          (reflector, "reflector_lines")):
            try:
                line = port.readline().decode("utf-8", errors="replace").strip()
            except Exception:
                return False
            if not line:
                continue
            record[key].append(line[:400])
            if any(marker in line for marker in forbidden[key]):
                return False
    return True


def close_serial(port, record: dict, role: str) -> None:
    """! @brief 부분 open을 포함해 serial close 성공 여부를 evidence에 남깁니다. """

    try:
        port.close()
    except Exception:
        record["cleanup"][f"{role}_serial_close"] = "FAIL"
    else:
        record["cleanup"][f"{role}_serial_close"] = "PASS"


def emergency_quiesce(port, record: dict) -> None:
    """! @brief 정상 cleanup 전에 빠져나온 역할에도 quiesce 명령을 최선으로 전송합니다. """

    if record["cleanup"].get("quiesce") == "PASS":
        return
    try:
        port.write(b"q")
        port.flush()
    except Exception:
        pass


def record_counter_transition(previous_counter, counter, gaps):
    """! @brief CS counter의 순방향 누락은 기록하고 중복·역행은 거부합니다. """
    if previous_counter is None:
        return
    delta = (counter - previous_counter) & 0xFFFF
    if delta == 0 or delta >= 0x8000:
        raise RuntimeError("duplicate or backward CS counter")
    if delta > 1:
        gaps.append({"before": previous_counter, "after": counter})


def read_procedures(initiator, reflector, record, count, timeout):
    deadline = time.monotonic() + timeout
    previous_counter = None
    record["counter_gap_policy"] = "observe_only"
    record["counter_gaps"] = []
    while time.monotonic() < deadline and record["procedures"] < count:
        for port, key in ((initiator, "initiator_lines"),
                          (reflector, "reflector_lines")):
            line = port.readline().decode("utf-8", errors="replace").strip()
            if not line:
                continue
            record[key].append(line[:400])
            if key != "initiator_lines":
                continue
            match = CS_RAW.fullmatch(line)
            if match is None:
                if line.startswith("CS_RAW"):
                    raise RuntimeError("malformed ranging output")
                continue
            counter, local, peer, rtt, tone, valid, distance = match.groups()
            counter, local, peer, rtt, tone, valid = map(
                int, (counter, local, peer, rtt, tone, valid)
            )
            record_counter_transition(
                previous_counter, counter, record["counter_gaps"]
            )
            if not (local == peer and local > 0 and rtt > 0 and tone > 0 and
                    0 < valid <= rtt and 0.0 <= float(distance) < 1000.0):
                raise RuntimeError("invalid ranging result")
            previous_counter = counter
            record["procedures"] += 1
            record["procedure_records"].append({
                "procedure": record["procedures"],
                "counter": counter,
                "local_steps": local,
                "peer_steps": peer,
                "rtt_steps": rtt,
                "tone_steps": tone,
                "valid_rtt_samples": valid,
                "distance_m": float(distance),
                "initiator_line": len(record["initiator_lines"]) - 1,
                "status": "PASS",
            })
    if record["procedures"] != count:
        raise RuntimeError("procedure count timeout")


def _positions(lines: list[str], phrases: tuple[str, ...]) -> list[int]:
    """! @brief 한 역할 UART slice에서 상태 문구의 strict 순서를 반환합니다. """

    result = []
    cursor = 0
    for phrase in phrases:
        match = next((index for index in range(cursor, len(lines))
                      if phrase in lines[index]), None)
        if match is None:
            raise ValueError(f"CS transition event missing: {phrase}")
        result.append(match)
        cursor = match + 1
    return result


def _transition_record(record: dict, cycle: int, kind: str,
                       initiator_start: int, reflector_start: int,
                       initiator_end: int | None = None,
                       reflector_end: int | None = None) -> dict:
    """! @brief 원본 UART 범위에서 stop/restart 또는 ACL 재연결 순서를 재구성합니다. """

    if initiator_end is None:
        initiator_end = len(record["initiator_lines"])
    if reflector_end is None:
        reflector_end = len(record["reflector_lines"])
    initiator = record["initiator_lines"][initiator_start:initiator_end]
    reflector = record["reflector_lines"][reflector_start:reflector_end]
    if kind == "stop_restart":
        initiator_events = (
            "CS procedures stop requested",
            "CS procedures restart requested",
            "CS_RAW counter=",
        )
        reflector_events = ("CS procedures disabled", "CS procedures enabled")
    elif kind == "disconnect_reconnect":
        initiator_events = (
            "CS disconnect requested",
            "CS initiator disconnected",
            "CS initiator connected; securing",
            "CS_RAW counter=",
        )
        reflector_events = ("CS reflector disconnected", "CS reflector connected")
    elif kind == "cleanup":
        initiator_events = (
            "CS quiesce requested role=initiator",
            "CS_QUIESCED role=initiator active_acl=0 pending=0 scan=0 cs=0",
        )
        reflector_events = (
            "CS quiesce requested role=reflector",
            "CS_QUIESCED role=reflector active_acl=0 pending=0 advertising=0 cs=0",
        )
    else:
        raise ValueError("unknown CS transition kind")
    _positions(initiator, initiator_events)
    _positions(reflector, reflector_events)
    return {
        "cycle": cycle,
        "status": "PASS",
        "initiator_range": [initiator_start, initiator_end],
        "reflector_range": [reflector_start, reflector_end],
        "initiator_events": list(initiator_events),
        "reflector_events": list(reflector_events),
    }


def validate_raw_evidence(record: dict, procedures: int,
                          reconnect_cycles: int) -> None:
    """! @brief raw RAS·radio restart·ACL teardown·최종 cleanup 분모를 재검증합니다. """

    rows = record.get("procedure_records")
    if (not isinstance(rows, list) or len(rows) != procedures or
            [row.get("procedure") for row in rows] != list(range(1, procedures + 1))):
        raise ValueError("CS procedure denominator mismatch")
    previous = None
    for row in rows:
        if (set(row) != {"procedure", "counter", "local_steps", "peer_steps", "rtt_steps",
                         "tone_steps", "valid_rtt_samples", "distance_m",
                         "initiator_line", "status"} or
                row["status"] != "PASS" or row["local_steps"] != row["peer_steps"] or
                row["local_steps"] <= 0 or row["rtt_steps"] <= 0 or
                row["tone_steps"] <= 0 or
                not 0 < row["valid_rtt_samples"] <= row["rtt_steps"] or
                not 0.0 <= row["distance_m"] < 1000.0):
            raise ValueError("CS procedure semantic mismatch")
        line_index = row["initiator_line"]
        if (not isinstance(line_index, int) or line_index < 0 or
                line_index >= len(record.get("initiator_lines", []))):
            raise ValueError("CS procedure transcript index mismatch")
        match = CS_RAW.fullmatch(record["initiator_lines"][line_index])
        if match is None:
            raise ValueError("CS procedure raw line mismatch")
        counter, local, peer, rtt, tone, valid, distance = match.groups()
        raw = {
            "procedure": row["procedure"],
            "counter": int(counter),
            "local_steps": int(local),
            "peer_steps": int(peer),
            "rtt_steps": int(rtt),
            "tone_steps": int(tone),
            "valid_rtt_samples": int(valid),
            "distance_m": float(distance),
            "initiator_line": line_index,
            "status": "PASS",
        }
        if raw != row:
            raise ValueError("CS procedure typed/raw mismatch")
        if previous is not None:
            delta = (row["counter"] - previous) & 0xFFFF
            if delta == 0 or delta >= 0x8000:
                raise ValueError("CS procedure counter order mismatch")
        previous = row["counter"]
    phases = (
        ("stop_restart_records", "stop_restart", 20),
        ("disconnect_reconnect_records", "disconnect_reconnect", reconnect_cycles),
    )
    for key, kind, count in phases:
        records = record.get(key)
        if (not isinstance(records, list) or len(records) != count or
                [row.get("cycle") for row in records] != list(range(1, count + 1))):
            raise ValueError(f"CS {kind} denominator mismatch")
        for row in records:
            rebuilt = _transition_record(
                record, row["cycle"], kind,
                row["initiator_range"][0], row["reflector_range"][0],
                row["initiator_range"][1], row["reflector_range"][1],
            )
            if rebuilt != row:
                raise ValueError(f"CS {kind} raw range mismatch")
    cleanup = record.get("cleanup")
    if (not isinstance(cleanup, dict) or
            cleanup != {
                "quiesce": "PASS",
                "initiator_acl": "PASS",
                "reflector_acl": "PASS",
                "zero_link": "PASS",
                "stability_window": "PASS",
                "initiator_serial_close": "PASS",
                "reflector_serial_close": "PASS",
            }):
        raise ValueError("CS final cleanup mismatch")
    cleanup_record = record.get("cleanup_record")
    if not isinstance(cleanup_record, dict):
        raise ValueError("CS final cleanup raw range missing")
    rebuilt = _transition_record(
        record, 0, "cleanup",
        cleanup_record["initiator_range"][0],
        cleanup_record["reflector_range"][0],
        cleanup_record["initiator_range"][1],
        cleanup_record["reflector_range"][1],
    )
    if rebuilt != cleanup_record:
        raise ValueError("CS final cleanup raw range mismatch")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--initiator-probe-sha256", required=True)
    parser.add_argument("--reflector-probe-sha256", required=True)
    parser.add_argument("--initiator-image", type=Path, required=True)
    parser.add_argument("--reflector-image", type=Path, required=True)
    parser.add_argument("--core-revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-clean", action="store_true")
    parser.add_argument("--flash", action="store_true")
    parser.add_argument("--post-flash-reset", action="store_true")
    parser.add_argument("--disconnect-cycles", type=int, default=0)
    parser.add_argument("--procedures", type=int, default=100)
    parser.add_argument("--procedure-timeout", type=float, default=600.0)
    parser.add_argument("--diagnose-timeout", action="store_true")
    args = parser.parse_args()
    if args.disconnect_cycles < 0 or args.disconnect_cycles > 20:
        parser.error("disconnect cycles must be between 0 and 20")
    if args.procedures < 1 or args.procedures > 100:
        parser.error("procedures must be between 1 and 100")
    if args.procedure_timeout <= 0.0 or args.procedure_timeout > 600.0:
        parser.error("procedure timeout must be within 600 seconds")
    if args.post_flash_reset and not args.flash:
        parser.error("post-flash reset requires flash")
    if args.output.exists():
        parser.error("refusing to overwrite existing evidence")
    if not args.source_clean:
        parser.error("exact HIL requires --source-clean")
    revision = subprocess.check_output(
        ("git", "rev-parse", "HEAD"), cwd=ROOT, text=True, timeout=30
    ).strip()
    changed = subprocess.check_output(
        ("git", "status", "--porcelain", "--untracked-files=all"),
        cwd=ROOT, text=True, timeout=30,
    ).strip()
    if changed or args.core_revision != revision:
        parser.error("exact HIL requires clean source and full HEAD revision")
    build_records = {
        "initiator": validate_build_record(
            args.initiator_image, args.core_revision, LOCK["board"]["revision"],
            APPLICATIONS["initiator"],
        ),
        "reflector": validate_build_record(
            args.reflector_image, args.core_revision, LOCK["board"]["revision"],
            APPLICATIONS["reflector"],
        ),
    }
    serial, ports = import_pyserial()
    init_uid, init_volume, init_port = discover(args.initiator_probe_sha256, ports)
    refl_uid, refl_volume, refl_port = discover(args.reflector_probe_sha256, ports)
    if init_uid == refl_uid or init_port == refl_port:
        raise RuntimeError("role mapping overlap")
    record = {
        "status": "FAIL",
        "source_clean": args.source_clean,
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
        "raw_ras": "NOT RUN",
        "distance_accuracy": "NOT RUN",
        "cleanup_confirmed": False,
        "build_records": build_records,
        "procedure_records": [],
        "stop_restart_records": [],
        "disconnect_reconnect_records": [],
        "cleanup_record": None,
        "cleanup": {
            "quiesce": "NOT_RUN",
            "initiator_acl": "NOT_RUN",
            "reflector_acl": "NOT_RUN",
            "zero_link": "NOT_RUN",
            "stability_window": "NOT_RUN",
            "initiator_serial_close": "NOT_RUN",
            "reflector_serial_close": "NOT_RUN",
        },
        "initiator_lines": [],
        "reflector_lines": [],
    }
    initiator = None
    reflector = None
    try:
        with ProbeLocks([init_uid, refl_uid]):
            record["initiator_registers"] = collect_register_identity(
                init_uid, init_volume
            )
            record["reflector_registers"] = collect_register_identity(
                refl_uid, refl_volume
            )
            run_error = None
            with ExitStack() as serial_stack:
                initiator = serial.Serial(init_port, 115200, timeout=0.05)
                serial_stack.callback(close_serial, initiator, record, "initiator")
                serial_stack.callback(emergency_quiesce, initiator, record)
                reflector = serial.Serial(refl_port, 115200, timeout=0.05)
                serial_stack.callback(close_serial, reflector, record, "reflector")
                serial_stack.callback(emergency_quiesce, reflector, record)
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
                        hardware_reset(args.reflector_probe_sha256)
                        hardware_reset(args.initiator_probe_sha256)
                else:
                    hardware_reset(args.reflector_probe_sha256)
                    hardware_reset(args.initiator_probe_sha256)
                started = time.monotonic()
                try:
                    try:
                        read_procedures(initiator, reflector, record,
                                        args.procedures,
                                        args.procedure_timeout)
                    except RuntimeError as error:
                        if (str(error) == "procedure count timeout" and
                                args.diagnose_timeout):
                            initiator.write(b"s")
                            initiator.flush()
                            record["timeout_stop_confirmed"] = collect_until(
                                initiator, reflector, record,
                                [("i", "CS procedures stop requested"),
                                 ("r", "CS procedures disabled")], 8.0
                            )
                            if record["timeout_stop_confirmed"]:
                                initiator.write(b"r")
                                initiator.flush()
                                record["timeout_restart_raw_confirmed"] = \
                                    collect_until(
                                        initiator, reflector, record,
                                        [("i", "CS procedures restart requested"),
                                         ("r", "CS procedures enabled"),
                                         ("i", "CS_RAW counter=")], 10.0
                                    )
                        raise
                    record["raw_ras"] = "PASS"
                    record["distance_accuracy"] = "BOUNDED_SANITY_PASS"
                    record["procedure_elapsed_s"] = round(
                        time.monotonic() - started, 3
                    )
                    for cycle in range(20):
                        initiator_start = len(record["initiator_lines"])
                        reflector_start = len(record["reflector_lines"])
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
                        record["stop_restart_records"].append(_transition_record(
                            record, cycle + 1, "stop_restart",
                            initiator_start, reflector_start,
                        ))
                    for cycle in range(args.disconnect_cycles):
                        initiator_start = len(record["initiator_lines"])
                        reflector_start = len(record["reflector_lines"])
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
                        record["disconnect_reconnect_records"].append(_transition_record(
                            record, cycle + 1, "disconnect_reconnect",
                            initiator_start, reflector_start,
                        ))
                except Exception as error:
                    run_error = error
                finally:
                    cleanup_initiator_start = len(record["initiator_lines"])
                    cleanup_reflector_start = len(record["reflector_lines"])
                    try:
                        initiator.write(b"q")
                        initiator.flush()
                    except Exception:
                        pass
                    try:
                        reflector.write(b"q")
                        reflector.flush()
                    except Exception:
                        pass
                    try:
                        quiesced = collect_until(
                            initiator, reflector, record,
                            [("i", "CS quiesce requested role=initiator"),
                             ("r", "CS quiesce requested role=reflector"),
                             ("i", "CS_QUIESCED role=initiator active_acl=0 "
                                   "pending=0 scan=0 cs=0"),
                             ("r", "CS_QUIESCED role=reflector active_acl=0 "
                                   "pending=0 advertising=0 cs=0")], 12.0
                        )
                    except Exception:
                        quiesced = False
                    record["cleanup"]["quiesce"] = \
                        "PASS" if quiesced else "FAIL"
                    record["cleanup"]["initiator_acl"] = \
                        "PASS" if quiesced else "FAIL"
                    record["cleanup"]["reflector_acl"] = \
                        "PASS" if quiesced else "FAIL"
                    record["cleanup"]["zero_link"] = \
                        "PASS" if quiesced else "FAIL"
                    stable = quiesced and collect_stable_quiescence(
                        initiator, reflector, record, 2.0
                    )
                    record["cleanup"]["stability_window"] = \
                        "PASS" if stable else "FAIL"
                    record["cleanup_confirmed"] = quiesced and stable
                    if quiesced:
                        record["cleanup_record"] = _transition_record(
                            record, 0, "cleanup", cleanup_initiator_start,
                            cleanup_reflector_start,
                        )
            if run_error is not None:
                raise run_error
            if not record["cleanup_confirmed"]:
                raise RuntimeError("CS quiesce/ACL cleanup incomplete")
            validate_raw_evidence(record, args.procedures,
                                  args.disconnect_cycles)
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
