#!/usr/bin/env python3
"""! @brief 같은 이름의 잘못된 service peer를 배제하는 CS HIL을 실행합니다. """

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import time
from typing import Any


HIL = Path(__file__).resolve().parent
REPOSITORY = HIL.parents[2]
sys.path.insert(0, str(HIL))

from ble_pair_hil_common import flash_image_pyocd  # noqa: E402
from m6_serial_echo import import_pyserial  # noqa: E402
from m31_ble_capability_run import collect_register_identity, discover  # noqa: E402
from m31_cs_negative_attestation import (  # noqa: E402
    build_wrong_peer_records,
    complete_program_phase,
    make_attestation,
    phase_contract,
    prepare_program_phase,
)
from v04_protocol import ProbeLocks  # noqa: E402


ROLES = ("initiator", "reflector", "wrong_peer")
APPLICATION_ROOTS = {
    "initiator": (
        REPOSITORY
        / "libraries/NUCODE_BLE_ChannelSounding/examples/RasInitiator"
    ),
    "reflector": (
        REPOSITORY
        / "libraries/NUCODE_BLE_ChannelSounding/examples/RasReflector"
    ),
    "wrong_peer": HIL / "fixtures/RasWrongPeer",
}


def _capture(
    ports: dict[str, Any], record: dict[str, Any], duration: float
) -> None:
    """! @brief 세 UART의 현재 raw line을 bounded transcript에 추가합니다. """

    deadline = time.monotonic() + duration
    while time.monotonic() < deadline:
        progressed = False
        for role, port in ports.items():
            if int(getattr(port, "in_waiting", 0)) <= 0:
                continue
            line = port.readline().decode("utf-8", errors="replace").strip()
            if not line:
                continue
            progressed = True
            if role == "wrong_peer" and "CS wrong peer advertising" in line:
                line = "CS wrong peer advertising"
            record[f"{role}_lines"].append(line[:400])
            if role == "wrong_peer" and "wrong peer connected" in line:
                raise RuntimeError("wrong peer accepted")
        if not progressed:
            time.sleep(0.005)


def _cleanup(
    ports: dict[str, Any], record: dict[str, Any], timeout: float = 10.0
) -> dict[str, dict[str, str]]:
    """! @brief initiator STOP·ACL disconnect와 third-peer 무연결을 확인합니다. """

    stop = False
    disconnected = False
    try:
        ports["initiator"].write(b"s")
        ports["initiator"].flush()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            _capture(ports, record, 0.05)
            stop = any(
                line == "CS procedures stop requested"
                for line in record["initiator_lines"]
            ) and any(
                line == "CS procedures disabled"
                for line in record["reflector_lines"]
            )
            if stop:
                break
        ports["initiator"].write(b"d")
        ports["initiator"].flush()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            _capture(ports, record, 0.05)
            disconnected = any(
                line == "CS initiator disconnected"
                for line in record["initiator_lines"]
            ) and any(
                line == "CS reflector disconnected"
                for line in record["reflector_lines"]
            )
            if disconnected:
                break
    except Exception as error:
        record["cleanup_error"] = type(error).__name__
    return {
        "initiator": {
            "stop": "PASS" if stop else "FAIL",
            "disconnect": "PASS" if disconnected else "FAIL",
            "serial_close": "PENDING",
        },
        "reflector": {
            "stop": "NOT_APPLICABLE",
            "disconnect": "PASS" if disconnected else "FAIL",
            "serial_close": "PENDING",
        },
        "wrong_peer": {
            "stop": "NOT_APPLICABLE",
            "disconnect": "NOT_APPLICABLE",
            "serial_close": "PENDING",
        },
    }


def main() -> int:
    """! @brief 세 보드에서 wrong-peer 배제와 RAS 100회를 검증합니다. """

    parser = argparse.ArgumentParser()
    for role in ("initiator", "reflector"):
        parser.add_argument(f"--{role}-probe-sha256", required=True)
        parser.add_argument(f"--{role}-image", type=Path, required=True)
    parser.add_argument(
        "--wrong-peer-probe-sha256",
        "--wrong-probe-sha256",
        dest="wrong_peer_probe_sha256",
        required=True,
    )
    parser.add_argument(
        "--wrong-peer-image",
        "--wrong-image",
        dest="wrong_peer_image",
        type=Path,
        required=True,
    )
    parser.add_argument("--core-revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-clean", action="store_true")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("refusing to overwrite existing evidence")

    serial, inventory = import_pyserial()
    role_map = {
        role: discover(getattr(args, f"{role}_probe_sha256"), inventory)
        for role in ROLES
    }
    if (
        len({value[0] for value in role_map.values()}) != len(ROLES)
        or len({value[2] for value in role_map.values()}) != len(ROLES)
    ):
        raise RuntimeError("three role mappings overlap")
    images = {role: getattr(args, f"{role}_image") for role in ROLES}
    phase = prepare_program_phase(
        args.output,
        "wrong_peer",
        args.core_revision,
        images,
        APPLICATION_ROOTS,
    )
    record: dict[str, Any] = {
        "status": "FAIL",
        "source_clean": True,
        "core_revision": args.core_revision,
        "board_revision": phase.board_revision,
        "negative_phase": phase_contract(phase),
        "test": "same_name_wrong_service_third_peer",
        "procedures": 0,
    }
    for role, (_, _, port_name) in role_map.items():
        record[f"{role}_probe_sha256"] = getattr(
            args, f"{role}_probe_sha256"
        )
        record[f"{role}_port"] = port_name
        record[f"{role}_image_sha256"] = hashlib.sha256(
            images[role].read_bytes()
        ).hexdigest()
        record[f"{role}_lines"] = []

    opened_ports: dict[str, Any] = {}
    flash_results: dict[str, tuple[str, str]] = {}
    cleanup: dict[str, dict[str, str]] = {}
    try:
        with ProbeLocks([value[0] for value in role_map.values()]):
            for role, (uid, volume, _) in role_map.items():
                record[f"{role}_registers"] = collect_register_identity(
                    uid, volume
                )
            try:
                for role in ROLES:
                    opened_ports[role] = serial.Serial(
                        role_map[role][2],
                        115200,
                        timeout=0.05,
                        write_timeout=2.0,
                    )
                    opened_ports[role].reset_input_buffer()
                for role in ROLES:
                    flash_results[role] = flash_image_pyocd(
                        f"cs_wrong_{role}",
                        role_map[role][0],
                        images[role],
                        120.0,
                        hardware_reset=True,
                    )

                started = time.monotonic()
                deadline = started + 120.0
                while (
                    time.monotonic() < deadline
                    and record["procedures"] < 100
                ):
                    before = len(record["initiator_lines"])
                    _capture(opened_ports, record, 0.05)
                    record["procedures"] += sum(
                        line.startswith("CS_RAW counter=")
                        for line in record["initiator_lines"][before:]
                    )
                record["elapsed_s"] = round(time.monotonic() - started, 3)
                cleanup = _cleanup(opened_ports, record)
            finally:
                if opened_ports and not cleanup:
                    cleanup = _cleanup(opened_ports, record)
                for port in opened_ports.values():
                    try:
                        port.close()
                    except Exception:
                        pass
                for role in ROLES:
                    cleanup.setdefault(
                        role,
                        {
                            "stop": "FAIL",
                            "disconnect": "FAIL",
                            "serial_close": "FAIL",
                        },
                    )
                    cleanup[role]["serial_close"] = (
                        "PASS"
                        if getattr(opened_ports.get(role), "is_open", None)
                        is False
                        else "FAIL"
                    )
                record["cleanup"] = cleanup
    except Exception as error:
        record["failure_class"] = type(error).__name__
        detail = str(error)
        for uid, _, _ in role_map.values():
            detail = detail.replace(uid, "<probe>")
        record["failure_detail"] = re.sub(
            r"\b[0-9A-Fa-f]{16,}\b", "<probe>", detail[:120]
        )

    if "failure_class" not in record:
        try:
            exact_program = complete_program_phase(
                phase,
                args.core_revision,
                {role: role_map[role][0] for role in ROLES},
                {
                    role: getattr(args, f"{role}_probe_sha256")
                    for role in ROLES
                },
                flash_results,
            )
            cycle_records = build_wrong_peer_records(record, cleanup)
            record["dispatch_cycle_records"] = cycle_records
            record["program_phase"] = exact_program
            record["m33_dispatch_attestation"] = make_attestation(
                phase, args.core_revision, exact_program, cycle_records
            )
            record["status"] = "PASS"
        except Exception as error:
            record["failure_class"] = type(error).__name__
            record["failure_detail"] = str(error)[:120]

    for role in ROLES:
        record[f"{role}_lines"] = [
            re.sub(
                r"\b[0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5}\b",
                "<bt-address>",
                line,
            )
            for line in record[f"{role}_lines"]
        ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        "M31_CS_WRONG_PEER="
        + record["status"]
        + ";PROCEDURES="
        + str(record["procedures"])
    )
    return 0 if record["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
