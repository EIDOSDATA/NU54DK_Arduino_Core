#!/usr/bin/env python3
"""! @brief 두 NU54DK에서 W09 IEEE 802.15.4·ESB exact HIL을 순차 실행합니다. """

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time


HIL = Path(__file__).resolve().parent
REPOSITORY = HIL.parents[2]
if str(HIL) not in sys.path:
    sys.path.insert(0, str(HIL))

from ble_pair_hil_common import BOARD_ROOT, flash_image_pyocd, git_revision  # noqa: E402
from m33_sdk_risk_common import (  # noqa: E402
    cleanup_direct_ports,
    complete_direct_program,
    dispatch_attestation,
    prepare_direct_program,
)
from m6_serial_echo import import_pyserial  # noqa: E402
from m32_ble_capability import ExpectedIdentity  # noqa: E402
from m32_ble_capability_run import collect_register_identity, discover  # noqa: E402
from v04_protocol import ProbeLocks  # noqa: E402


PACKET_TARGET = 2000
ITERATION_TARGET = 20
ALLOWED_LOSS = 20
LATENCY_LIMIT_MS = 100
PROTOCOLS = {
    "radio154": {
        "wire": "M32R154|1",
        "roles": ("transmitter", "receiver"),
        "test_id": "M32-154-01:primary",
    },
    "esb": {
        "wire": "M32ESB|1",
        "roles": ("ptx", "prx"),
        "test_id": "M32-ESB-01:primary",
    },
}
ATTESTATION_ROLES = ("dut", "peer")
SEMANTICS = ("ieee802154_packets", "esb_packets", "role_swap", "cleanup")
APPLICATION_ROOTS = {
    "radio154": REPOSITORY / "tests/zephyr/m32_radio154_hil",
    "esb": REPOSITORY / "tests/zephyr/m32_esb_hil",
}


class StandaloneRadioFailure(RuntimeError):
    """! @brief mapping·flash·UART·packet 분모 실패를 나타냅니다. """


def _line(port: object, wire: str, deadline: float) -> str:
    """! @brief DAPLink 잡음에서 지정 radio protocol 줄만 반환합니다. """
    while time.monotonic() < deadline:
        payload = port.readline()
        if len(payload) > 512:
            raise StandaloneRadioFailure("serial line overlong")
        line = payload.decode("ascii", errors="replace").strip()
        if line.startswith(wire + "|"):
            return line
    raise StandaloneRadioFailure("serial line timeout")


def _fields(line: str) -> dict[str, str]:
    """! @brief 중복 없는 key=value field만 반환합니다. """
    output: dict[str, str] = {}
    for field in line.split("|")[3:]:
        if "=" not in field:
            continue
        key, value = field.split("=", 1)
        if key in output:
            raise StandaloneRadioFailure(f"duplicate field: {key}")
        output[key] = value
    return output


def _integer(fields: dict[str, str], key: str) -> int:
    """! @brief 필수 decimal field를 음이 아닌 정수로 변환합니다. """
    value = fields.get(key, "")
    if re.fullmatch(r"[0-9]+", value) is None:
        raise StandaloneRadioFailure(f"invalid integer field: {key}")
    return int(value)


def _save(prefix: Path, evidence: dict, transcript: list[str]) -> None:
    """! @brief 실패 원본을 포함한 attempt를 덮어쓰기 없이 저장합니다. """
    raw = ("\n".join(transcript) + "\n").encode("ascii", errors="replace")
    if b"uid=" in raw.lower() or b"probe_id=" in raw.lower():
        raise StandaloneRadioFailure("raw probe UID in transcript")
    if prefix.with_suffix(".json").exists() or prefix.with_suffix(
        ".transcript.log"
    ).exists():
        raise StandaloneRadioFailure("기존 attempt evidence를 덮어쓰지 않습니다")
    prefix.parent.mkdir(parents=True, exist_ok=True)
    evidence["transcript_sha256"] = hashlib.sha256(raw).hexdigest()
    evidence["observed_utc"] = datetime.now(timezone.utc).isoformat()
    prefix.with_suffix(".transcript.log").write_bytes(raw)
    prefix.with_suffix(".json").write_text(
        json.dumps(evidence, indent=2) + "\n", encoding="utf-8"
    )


def _probe_role(port: object, wire: str, role: str, core: str,
                transcript: list[str]) -> None:
    """! @brief flash된 image의 protocol·role·revision을 UART로 대조합니다. """
    port.reset_input_buffer()
    port.write(f"{wire}|PROBE\n".encode("ascii"))
    port.flush()
    line = _line(port, wire, time.monotonic() + 10.0)
    transcript.append(f"{role}: {line}")
    fields = _fields(line)
    if (
        not line.startswith(f"{wire}|READY|")
        or fields.get("role") != role
        or fields.get("core") != core
    ):
        raise StandaloneRadioFailure(f"{role} READY mismatch")


def _read_result_end(port: object, wire: str, role: str, nonce: str,
                     core: str, transcript: list[str], timeout_s: float) -> dict[str, str]:
    """! @brief 한 역할의 RESULT 다음 END를 strict identity로 읽습니다. """
    result: dict[str, str] | None = None
    ended = False
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline and not ended:
        line = _line(port, wire, deadline)
        transcript.append(f"{role}: {line}")
        fields = _fields(line)
        if "|FAIL|" in line:
            raise StandaloneRadioFailure(
                f"{role} target FAIL: {fields.get('stage')}"
            )
        if fields.get("nonce") != nonce or fields.get("core") != core:
            raise StandaloneRadioFailure(f"{role} identity mismatch")
        if line.startswith(f"{wire}|RESULT|"):
            if result is not None or fields.get("role") != role:
                raise StandaloneRadioFailure(f"{role} RESULT mismatch")
            result = fields
        elif line.startswith(f"{wire}|END|"):
            if fields.get("role") != role or fields.get("status") != "pass":
                raise StandaloneRadioFailure(f"{role} END mismatch")
            ended = True
    if result is None or not ended:
        raise StandaloneRadioFailure(f"{role} result timeout")
    return result


def _validate_result(protocol: str, results: dict[str, dict[str, str]]) -> dict:
    """! @brief 2,000 packet·20 iteration·negative·latency 분모를 판정합니다. """
    definition = PROTOCOLS[protocol]
    transmit_role, receive_role = definition["roles"]
    transmit = results[transmit_role]
    receive = results[receive_role]
    if _integer(transmit, "requested") != PACKET_TARGET:
        raise StandaloneRadioFailure(f"{protocol} requested denominator mismatch")
    acknowledged = _integer(transmit, "acknowledged")
    unique = _integer(receive, "unique")
    if PACKET_TARGET - acknowledged > ALLOWED_LOSS:
        raise StandaloneRadioFailure(f"{protocol} ACK loss limit")
    if PACKET_TARGET - unique > ALLOWED_LOSS:
        raise StandaloneRadioFailure(f"{protocol} receive loss limit")
    if _integer(receive, "corrupt") != 0 or _integer(receive, "dropped") != 0:
        raise StandaloneRadioFailure(f"{protocol} corrupt or dropped packet")
    if _integer(transmit, "max_latency_ms") > LATENCY_LIMIT_MS:
        raise StandaloneRadioFailure(f"{protocol} latency limit")
    for role, fields in results.items():
        if _integer(fields, "iterations") != ITERATION_TARGET:
            raise StandaloneRadioFailure(f"{protocol} {role} iteration mismatch")
        if _integer(fields, "invalid_length_rejected") != 1:
            raise StandaloneRadioFailure(f"{protocol} {role} length negative")
        negative = "invalid_channel_rejected" if protocol == "radio154" else (
            "invalid_rate_rejected"
        )
        if _integer(fields, negative) != 1:
            raise StandaloneRadioFailure(f"{protocol} {role} config negative")
    return {
        "expected_packets": PACKET_TARGET,
        "acknowledged_packets": acknowledged,
        "unique_packets": unique,
        "lost_acknowledgements": PACKET_TARGET - acknowledged,
        "lost_unique_packets": PACKET_TARGET - unique,
    }


def build_dispatch_cycle_records(protocol_results: dict[str, dict]) -> list[dict]:
    """! @brief 두 radio의 실제 20 iteration과 역할 교대를 cycle로 변환합니다. """

    if set(protocol_results) != set(PROTOCOLS):
        raise StandaloneRadioFailure("dispatcher standalone protocol mismatch")
    first_probes: dict[str, str] = {}
    for protocol, definition in PROTOCOLS.items():
        phase = protocol_results[protocol]
        results = phase.get("results", {})
        if set(results) != set(definition["roles"]):
            raise StandaloneRadioFailure("dispatcher standalone role mismatch")
        expected = _validate_result(protocol, results)
        if phase.get("denominator") != expected:
            raise StandaloneRadioFailure("dispatcher standalone denominator mismatch")
        cleanup = phase.get("cleanup", {})
        if set(cleanup) != set(definition["roles"]) or any(
                row.get("stop") != "PASS" or row.get("serial_close") != "PASS"
                for row in cleanup.values()):
            raise StandaloneRadioFailure("dispatcher standalone cleanup mismatch")
        probe_mapping = phase.get("probe_mapping", {})
        if set(probe_mapping) != set(ATTESTATION_ROLES):
            raise StandaloneRadioFailure("dispatcher standalone probe mapping mismatch")
        first_probes[protocol] = probe_mapping["dut"]
    if first_probes["radio154"] == first_probes["esb"]:
        raise StandaloneRadioFailure("dispatcher standalone role swap missing")
    statuses = {token: "PASS" for token in SEMANTICS}
    return [
        {"cycle": cycle, "status": "PASS", "semantics": dict(statuses)}
        for cycle in range(1, ITERATION_TARGET + 1)
    ]


def _run_protocol(protocol: str, boards: dict[str, dict], serial_module: object,
                  nonce: str, core: str, transcript: list[str],
                  exact_inputs: dict | None,
                  cleanup_records: dict[str, dict]) -> dict:
    """! @brief 한 radio protocol의 flash·2,000 packet·STOP을 실행합니다. """
    definition = PROTOCOLS[protocol]
    wire = definition["wire"]
    transmit_role, receive_role = definition["roles"]
    for role in (transmit_role, receive_role):
        board = boards[role]
        board["registers"] = collect_register_identity(board["uid"], board["volume"])
        board["flash_mode"], board["flash_bytes"] = flash_image_pyocd(
            role,
            board["uid"],
            board["image"],
            120.0,
            hardware_reset=True,
            preserve_nrf54l_access=True,
        )
    time.sleep(2.0)
    ports: dict[str, object] = {}
    stopped_roles: set[str] = set()
    output: dict | None = None
    try:
        for role in (transmit_role, receive_role):
            ports[role] = serial_module.Serial(
                boards[role]["vcom"], 115200, timeout=0.05
            )
        for role, port in ports.items():
            _probe_role(port, wire, role, core, transcript)
        for role in (receive_role, transmit_role):
            ports[role].write(
                f"{wire}|START|nonce={nonce}|core={core}\n".encode("ascii")
            )
            ports[role].flush()
            line = _line(ports[role], wire, time.monotonic() + 15.0)
            transcript.append(f"{role}: {line}")
            fields = _fields(line)
            if (
                not line.startswith(f"{wire}|BEGIN|")
                or fields.get("role") != role
                or fields.get("nonce") != nonce
                or fields.get("core") != core
            ):
                raise StandaloneRadioFailure(f"{role} BEGIN mismatch")

        results = {
            transmit_role: _read_result_end(
                ports[transmit_role], wire, transmit_role, nonce, core,
                transcript, 240.0
            )
        }
        time.sleep(0.5)
        ports[receive_role].write(f"{wire}|FINISH|nonce={nonce}\n".encode("ascii"))
        ports[receive_role].flush()
        results[receive_role] = _read_result_end(
            ports[receive_role], wire, receive_role, nonce, core, transcript, 15.0
        )
        denominator = _validate_result(protocol, results)

        for role in (transmit_role, receive_role):
            ports[role].write(f"{wire}|STOP|nonce={nonce}\n".encode("ascii"))
            ports[role].flush()
            line = _line(ports[role], wire, time.monotonic() + 30.0)
            transcript.append(f"{role}: {line}")
            fields = _fields(line)
            if (
                not line.startswith(f"{wire}|STOPPED|role={role}")
                or fields.get("cleanup") != "pass"
                or fields.get("nonce") != nonce
                or fields.get("core") != core
            ):
                raise StandaloneRadioFailure(f"{role} STOP mismatch")
            stopped_roles.add(role)
        output = {"results": results, "denominator": denominator}
    finally:
        cleanup_records[protocol] = cleanup_direct_ports(
            ports,
            {
                role: f"{wire}|STOP|nonce={nonce}\n".encode("ascii")
                for role in ports
            },
            stopped_roles,
            transcript,
        )
    if output is None:
        raise StandaloneRadioFailure(f"{protocol} result missing after cleanup")
    output["cleanup"] = cleanup_records[protocol]
    output["probe_mapping"] = {
        "dut": boards[transmit_role]["probe_sha256"],
        "peer": boards[receive_role]["probe_sha256"],
    }
    if exact_inputs is not None:
        output["exact_program"] = complete_direct_program(
            REPOSITORY,
            core,
            ATTESTATION_ROLES,
            exact_inputs["images"],
            exact_inputs["probe_ids"],
            exact_inputs["probe_hashes"],
            exact_inputs["sidecars"],
            {
                "dut": {
                    "mode": boards[transmit_role]["flash_mode"],
                    "bytes": str(boards[transmit_role]["flash_bytes"]),
                },
                "peer": {
                    "mode": boards[receive_role]["flash_mode"],
                    "bytes": str(boards[receive_role]["flash_bytes"]),
                },
            },
            exact_inputs["build_records"],
        )
    return output


def execute(args: argparse.Namespace) -> dict:
    """! @brief 두 probe에 네 image를 순차 flash하고 두 단독 radio를 판정합니다. """
    prefix = args.output_prefix.resolve()
    lock = json.loads(
        (REPOSITORY / "tools/ci/ncs-3.4.0.lock.json").read_text(encoding="utf-8")
    )
    sdk = args.sdk_root.resolve()
    identity = ExpectedIdentity(
        git_revision(REPOSITORY), git_revision(BOARD_ROOT),
        git_revision(sdk / "nrf"), git_revision(sdk / "zephyr")
    )
    if (
        identity.board != lock["board"]["revision"]
        or identity.ncs != lock["ncs"]["revision"]
        or identity.zephyr != lock["zephyr"]["revision"]
    ):
        raise StandaloneRadioFailure("board/SDK revision lock mismatch")
    dirty = subprocess.run(
        ["git", "-C", str(REPOSITORY), "status", "--porcelain=v1", "--untracked-files=all"],
        capture_output=True, text=True, check=True
    ).stdout.strip()
    if dirty and not args.development:
        raise StandaloneRadioFailure("exact HIL에는 clean source commit이 필요합니다")

    serial_module, list_ports = import_pyserial()
    probe_definitions = {
        "first": args.probe_first_sha256,
        "second": args.probe_second_sha256,
    }
    endpoints: dict[str, dict] = {}
    for name, digest in probe_definitions.items():
        uid, volume, vcom = discover(digest, list_ports)
        endpoints[name] = {
            "uid": uid, "volume": volume, "vcom": vcom,
            "probe_sha256": digest,
        }
    if endpoints["first"]["uid"] == endpoints["second"]["uid"]:
        raise StandaloneRadioFailure("두 역할이 같은 probe에 매핑됨")

    image_definitions = {
        "transmitter": args.hex_radio154_transmitter.resolve(),
        "receiver": args.hex_radio154_receiver.resolve(),
        "ptx": args.hex_esb_ptx.resolve(),
        "prx": args.hex_esb_prx.resolve(),
    }
    for role, image in image_definitions.items():
        if not image.is_file() or image.suffix.lower() != ".hex":
            raise StandaloneRadioFailure(f"{role} target image missing")

    boards: dict[str, dict] = {}
    for role in ("transmitter", "prx"):
        boards[role] = dict(endpoints["first"])
        boards[role]["image"] = image_definitions[role]
        boards[role]["image_sha256"] = hashlib.sha256(
            image_definitions[role].read_bytes()
        ).hexdigest()
    for role in ("receiver", "ptx"):
        boards[role] = dict(endpoints["second"])
        boards[role]["image"] = image_definitions[role]
        boards[role]["image_sha256"] = hashlib.sha256(
            image_definitions[role].read_bytes()
        ).hexdigest()

    transcript: list[str] = []
    protocol_results: dict[str, dict] = {}
    cleanup_records: dict[str, dict] = {}
    exact_inputs: dict[str, dict] = {}
    if not dirty:
        for protocol, definition in PROTOCOLS.items():
            transmit_role, receive_role = definition["roles"]
            images = {
                "dut": boards[transmit_role]["image"],
                "peer": boards[receive_role]["image"],
            }
            sidecars, build_records = prepare_direct_program(
                prefix.with_name(f"{prefix.name}-{protocol}.native.json"),
                ATTESTATION_ROLES,
                images,
                identity.core,
                identity.board,
                APPLICATION_ROOTS[protocol],
            )
            exact_inputs[protocol] = {
                "images": images,
                "probe_ids": {
                    "dut": boards[transmit_role]["uid"],
                    "peer": boards[receive_role]["uid"],
                },
                "probe_hashes": {
                    "dut": boards[transmit_role]["probe_sha256"],
                    "peer": boards[receive_role]["probe_sha256"],
                },
                "sidecars": sidecars,
                "build_records": build_records,
            }
    status = "FAIL"
    reason: str | None = None
    with ProbeLocks([endpoints["first"]["uid"], endpoints["second"]["uid"]]):
        try:
            for protocol in ("radio154", "esb"):
                nonce = hashlib.sha256(
                    f"{protocol}:{time.time_ns()}:{identity.core}".encode("ascii")
                ).hexdigest()[:32]
                protocol_results[protocol] = _run_protocol(
                    protocol, boards, serial_module, nonce, identity.core, transcript,
                    exact_inputs.get(protocol), cleanup_records,
                )
                protocol_results[protocol]["nonce"] = nonce
            status = "PASS_CANDIDATE" if dirty else "PASS"
        except Exception as error:
            reason = f"{type(error).__name__}: {error}"
            reason = re.sub(r"(?i)\b[0-9a-f]{16,64}\b", "<redacted-identity>", reason)
            reason = re.sub(r"(?i)(?:uid|probe_id)=[^\s,;]+", "uid=<redacted>", reason)

    public_boards = {
        role: {key: value for key, value in board.items() if key not in {"uid", "image"}}
        for role, board in boards.items()
    }
    evidence = {
        "test_ids": [definition["test_id"] for definition in PROTOCOLS.values()],
        "status": status,
        "scope": "two_board_standalone_ieee802154_and_esb_contract",
        "source_clean": not bool(dirty),
        "identity": vars(identity),
        "boards": public_boards,
        "iterations": ITERATION_TARGET,
        "packet_denominator_per_protocol": PACKET_TARGET,
        "allowed_loss_packets_per_protocol": ALLOWED_LOSS,
        "latency_limit_ms": LATENCY_LIMIT_MS,
        "protocols": protocol_results,
        "cleanup": cleanup_records,
        "reason": reason,
    }
    if status == "PASS":
        cycle_records = build_dispatch_cycle_records(protocol_results)
        evidence["dispatch_cycle_records"] = cycle_records
        evidence["program_phases"] = {
            protocol: protocol_results[protocol]["exact_program"]
            for protocol in PROTOCOLS
        }
        evidence["m33_dispatch_attestation"] = dispatch_attestation(
            "m32_standalone_radio", identity.core, ITERATION_TARGET,
            SEMANTICS, ATTESTATION_ROLES,
            protocol_results["esb"]["exact_program"],
            cycle_records=cycle_records,
        )
    _save(prefix, evidence, transcript)
    return evidence


def main() -> int:
    """! @brief raw UID 없이 두 probe와 네 role image를 지정합니다. """
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe-first-sha256", required=True)
    parser.add_argument("--probe-second-sha256", required=True)
    parser.add_argument("--hex-radio154-transmitter", required=True, type=Path)
    parser.add_argument("--hex-radio154-receiver", required=True, type=Path)
    parser.add_argument("--hex-esb-ptx", required=True, type=Path)
    parser.add_argument("--hex-esb-prx", required=True, type=Path)
    parser.add_argument("--sdk-root", required=True, type=Path)
    parser.add_argument("--output-prefix", required=True, type=Path)
    parser.add_argument("--development", action="store_true")
    args = parser.parse_args()
    try:
        result = execute(args)
    except Exception as error:
        message = re.sub(r"(?i)\b[0-9a-f]{16,64}\b", "<redacted-identity>", str(error))
        print(
            f"M32_RADIO_HIL_FAIL: {type(error).__name__}: {message[:400]}",
            file=sys.stderr,
        )
        return 1
    print(
        f"M32_RADIO_HIL_STATUS={result['status']};"
        f"SOURCE_CLEAN={str(result['source_clean']).lower()}"
    )
    return 0 if result["status"] == "PASS" or (
        args.development and result["status"] == "PASS_CANDIDATE"
    ) else 1


if __name__ == "__main__":
    sys.exit(main())
