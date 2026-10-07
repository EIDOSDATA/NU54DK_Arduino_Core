#!/usr/bin/env python3
"""! @brief 세 NU54DK에서 W06 Mesh provisioning·model traffic HIL을 실행합니다. """

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

from ble_pair_hil_common import (  # noqa: E402
    BOARD_ROOT,
    flash_image_pyocd,
    git_revision,
    validate_build_record,
)
from m33_sdk_risk_common import (  # noqa: E402
    copy_program_inputs,
    dispatch_attestation,
    exact_program_evidence,
    readback_programmed_images,
    require_exact_clean_source,
    reserve_sidecars,
    validate_programming_receipt,
)
from m6_serial_echo import import_pyserial  # noqa: E402
from m32_ble_capability import ExpectedIdentity  # noqa: E402
from m32_ble_capability_run import collect_register_identity, discover  # noqa: E402
from v04_protocol import ProbeLocks  # noqa: E402


ROLES = ("provisioner", "node_a", "node_b")
PROTOCOL = "M32MESH|1"
CYCLE_TARGET = 20
BASE_MESSAGE_TARGET = 300
SECURED_MESSAGE_TARGET = 200
TOTAL_MESSAGE_TARGET = BASE_MESSAGE_TARGET + SECURED_MESSAGE_TARGET
NODE_MESSAGE_TARGET = TOTAL_MESSAGE_TARGET // 2
LATENCY_LIMIT_MS = 2000
REMOTE_NODE_TARGET = 2
MESH_CAPACITY_MINIMUMS = {
    "cdb_subnets": 1,
    "cdb_app_keys": 1,
    "local_subnets": 1,
    "local_app_keys": 1,
    "model_app_keys": 1,
}
APPLICATION_ROOT = REPOSITORY / "tests/zephyr/m32_mesh_hil"


class MeshExecutionFailure(RuntimeError):
    """! @brief mapping·flash·UART·Mesh 분모 검증의 제한된 실패입니다. """


def _fields(line: str) -> dict[str, str]:
    """! @brief 중복 없는 key=value field만 반환합니다. """
    output: dict[str, str] = {}
    for field in line.split("|")[3:]:
        if "=" not in field:
            continue
        key, value = field.split("=", 1)
        if key in output:
            raise MeshExecutionFailure(f"duplicate field: {key}")
        output[key] = value
    return output


def _integer(fields: dict[str, str], key: str) -> int:
    """! @brief 필수 decimal field를 음이 아닌 정수로 변환합니다. """
    value = fields.get(key, "")
    if re.fullmatch(r"[0-9]+", value) is None:
        raise MeshExecutionFailure(f"invalid integer field: {key}")
    return int(value)


def _validate_capacity(fields: dict[str, str]) -> dict[str, int]:
    """! @brief firmware가 보고한 CDB·local/model 용량을 topology와 대조합니다. """
    node_slots = _integer(fields, "cdb_node_slots")
    local_slots = _integer(fields, "cdb_local_slots")
    if local_slots != 1:
        raise MeshExecutionFailure("CDB local provisioner slot mismatch")
    remote_capacity = node_slots - local_slots
    if remote_capacity < REMOTE_NODE_TARGET:
        raise MeshExecutionFailure(
            "CDB remote node capacity mismatch: "
            f"required={REMOTE_NODE_TARGET}, actual={remote_capacity}"
        )
    observed = {
        "cdb_node_slots": node_slots,
        "cdb_local_slots": local_slots,
        "cdb_remote_capacity": remote_capacity,
    }
    for key, minimum in MESH_CAPACITY_MINIMUMS.items():
        value = _integer(fields, key)
        if value < minimum:
            raise MeshExecutionFailure(
                f"Mesh capacity mismatch: {key} required={minimum}, actual={value}"
            )
        observed[key] = value
    return observed


def _line(port: object, deadline: float) -> str:
    """! @brief DAPLink 잡음에서 M32 Mesh protocol 줄만 반환합니다. """
    while time.monotonic() < deadline:
        payload = port.readline()
        if len(payload) > 768:
            raise MeshExecutionFailure("serial line overlong")
        line = payload.decode("ascii", errors="replace").strip()
        if line.startswith(PROTOCOL + "|"):
            return line
    raise MeshExecutionFailure("serial line timeout")


def _save(prefix: Path, evidence: dict, transcript: list[str]) -> None:
    """! @brief 성공·실패 attempt를 덮어쓰기 없이 보존합니다. """
    raw = ("\n".join(transcript) + "\n").encode("ascii", errors="replace")
    if b"uid=" in raw.lower() or b"probe_id=" in raw.lower():
        raise MeshExecutionFailure("raw probe UID in transcript")
    if prefix.with_suffix(".json").exists() or prefix.with_suffix(
        ".transcript.log"
    ).exists():
        raise MeshExecutionFailure("기존 attempt evidence를 덮어쓰지 않습니다")
    prefix.parent.mkdir(parents=True, exist_ok=True)
    evidence["transcript_sha256"] = hashlib.sha256(raw).hexdigest()
    evidence["observed_utc"] = datetime.now(timezone.utc).isoformat()
    prefix.with_suffix(".transcript.log").write_bytes(raw)
    prefix.with_suffix(".json").write_text(
        json.dumps(evidence, indent=2) + "\n", encoding="utf-8"
    )


def _validate_result(role: str, fields: dict[str, str]) -> None:
    """! @brief 역할별 provisioning·traffic·negative 분모를 판정합니다. """
    if fields.get("payload_integrity") != "pass":
        raise MeshExecutionFailure(f"{role} payload integrity")
    if role == "provisioner":
        expected = {
            "provisioned_nodes": 2,
            "configured_nodes": 2,
            "base_messages": BASE_MESSAGE_TARGET,
            "secured_messages": SECURED_MESSAGE_TARGET,
            "acknowledged": TOTAL_MESSAGE_TARGET,
            "invalid_destination_rejected": 1,
            "wrong_key_rejected": 1,
        }
        for key, value in expected.items():
            if _integer(fields, key) != value:
                raise MeshExecutionFailure(f"provisioner {key} denominator mismatch")
        if _integer(fields, "max_latency_ms") > LATENCY_LIMIT_MS:
            raise MeshExecutionFailure("provisioner model latency limit")
        return
    if _integer(fields, "received") != NODE_MESSAGE_TARGET:
        raise MeshExecutionFailure(f"{role} receive denominator mismatch")
    if _integer(fields, "unprovisioned_rejected") != 1:
        raise MeshExecutionFailure(f"{role} unprovisioned boundary")
    if fields.get("feature") != "pass":
        raise MeshExecutionFailure(f"{role} feature boundary")
    if fields.get("friendship") != "pass":
        raise MeshExecutionFailure(f"{role} friendship boundary")


def _validate_friend_clear(
    role: str, fields: dict[str, str]
) -> dict[str, int | str]:
    """! @brief TTL=0 Friend Clear가 첫 retry 전에 양 node에서 끝났는지 판정합니다. """
    if fields.get("cleanup") != "pass":
        raise MeshExecutionFailure(f"{role} cleanup mismatch")
    classification = fields.get("friend_clear")
    latency = _integer(fields, "friend_clear_ms")
    if role == "provisioner":
        if classification != "not_applicable" or latency != 0:
            raise MeshExecutionFailure("provisioner Friend Clear boundary")
    elif (
        classification != "pass"
        or fields.get("friend_clear_peer_ack") != "pass"
        or latency > 1000
    ):
        raise MeshExecutionFailure(f"{role} Friend Clear peer-ack boundary")
    return {"status": classification, "latency_ms": latency}


def _validate_cleared(role: str, fields: dict[str, str], cycle: int) -> dict:
    """! @brief 매 회 fresh settings와 이전 suspend 해제를 원시 record에서 검증합니다. """

    if fields.get("provisioned") != "0" or fields.get("settings_reset") != "pass":
        raise MeshExecutionFailure(f"{role} settings cleanup mismatch")
    resumed = _integer(fields, "resumed")
    expected_resume = int(cycle > 1)
    if resumed != expected_resume:
        raise MeshExecutionFailure(
            f"{role} session resume mismatch: expected={expected_resume}, actual={resumed}"
        )
    rejected = _integer(fields, "unprovisioned_rejected")
    if role != "provisioner" and rejected != 1:
        raise MeshExecutionFailure(f"{role} unprovisioned boundary")
    return {
        "provisioned": 0,
        "settings_reset": "PASS",
        "resumed_from_previous_cleanup": bool(resumed),
        "unprovisioned_access_rejected": rejected,
    }


def _cycle_transcript_sha256(lines: list[str]) -> str:
    """! @brief 한 세션에 실제 수집한 원시 UART 줄의 digest를 반환합니다. """

    if not lines:
        raise MeshExecutionFailure("empty Mesh cycle transcript")
    return hashlib.sha256(
        ("\n".join(lines) + "\n").encode("ascii", errors="replace")
    ).hexdigest()


def validate_cycle_records(records: list[dict], transcript: list[str]) -> None:
    """! @brief host가 자른 20개 독립 세션과 raw transcript 결합을 재검증합니다. """

    if len(records) != CYCLE_TARGET or len({row.get("nonce") for row in records}) != CYCLE_TARGET:
        raise MeshExecutionFailure("Mesh cycle denominator or nonce uniqueness mismatch")
    expected_start = records[0].get("transcript_line_start", 0)
    expected_semantics = {
        "provision_two_nodes": "PASS",
        "mesh_security": "PASS",
        "lpn_friend_clear": "PASS",
        "rejoin": "PASS",
        "cleanup": "PASS",
    }
    for expected_cycle, row in enumerate(records, start=1):
        if row.get("cycle") != expected_cycle or row.get("status") != "PASS":
            raise MeshExecutionFailure("Mesh host cycle sequence mismatch")
        nonce = row.get("nonce", "")
        if re.fullmatch(r"[0-9a-f]{32}", nonce) is None or \
                row.get("semantics") != expected_semantics:
            raise MeshExecutionFailure("Mesh cycle identity or semantics mismatch")
        start = row.get("transcript_line_start")
        end = row.get("transcript_line_end")
        if not isinstance(start, int) or not isinstance(end, int) or start != expected_start:
            raise MeshExecutionFailure("Mesh raw transcript range mismatch")
        if end < start or end > len(transcript):
            raise MeshExecutionFailure("Mesh raw transcript range boundary")
        raw_lines = transcript[start - 1:end]
        if row.get("transcript_sha256") != _cycle_transcript_sha256(raw_lines):
            raise MeshExecutionFailure("Mesh raw transcript digest mismatch")
        cleared = row.get("cleared", {})
        results = row.get("results", {})
        cleanup = row.get("cleanup", {})
        if set(cleared) != set(ROLES) or set(results) != set(ROLES) or \
                cleanup.get("status") != "PASS":
            raise MeshExecutionFailure("Mesh cycle raw semantic evidence mismatch")
        for role in ROLES:
            expected_rejected = 0 if role == "provisioner" else 1
            if cleared[role] != {
                "provisioned": 0,
                "settings_reset": "PASS",
                "resumed_from_previous_cleanup": expected_cycle > 1,
                "unprovisioned_access_rejected": expected_rejected,
            }:
                raise MeshExecutionFailure("Mesh settings cleanup evidence mismatch")
            _validate_result(role, results[role])
            for event in ("CLEARED", "BEGIN", "RESULT", "END", "STOPPED"):
                marker = f"{role}: {PROTOCOL}|{event}|"
                matches = [line for line in raw_lines if line.startswith(marker)]
                if len(matches) != 1 or f"nonce={nonce}" not in matches[0]:
                    raise MeshExecutionFailure("Mesh raw event denominator mismatch")
        if cleanup.get("command_sent") != {role: True for role in ROLES} or \
                cleanup.get("friend_local_callback") is not True or \
                cleanup.get("friend_peer_callback") is not True or \
                cleanup.get("peer_ack_sent") is not True or \
                cleanup.get("errors") != [] or \
                set(cleanup.get("records", {})) != set(ROLES):
            raise MeshExecutionFailure("Mesh cleanup handshake evidence mismatch")
        for role, friend in cleanup["records"].items():
            expected_status = "not_applicable" if role == "provisioner" else "pass"
            if friend.get("status") != expected_status or \
                    not isinstance(friend.get("latency_ms"), int) or \
                    friend["latency_ms"] > (0 if role == "provisioner" else 1000):
                raise MeshExecutionFailure("Mesh Friend Clear evidence mismatch")
        for role, event in (("node_a", "FRIEND_CLEAR_LOCAL"),
                            ("node_b", "FRIEND_CLEAR_PEER")):
            marker = f"{role}: {PROTOCOL}|{event}|"
            matches = [line for line in raw_lines if line.startswith(marker)]
            if len(matches) != 1 or f"nonce={nonce}" not in matches[0]:
                raise MeshExecutionFailure("Mesh Friend Clear raw event mismatch")
        expected_start = end + 1


def _command(
    ports: dict[str, object],
    roles: tuple[str, ...],
    command: bytes,
) -> None:
    """! @brief 지정 역할에 동일 bounded 명령을 순서대로 전송합니다. """
    for role in roles:
        ports[role].write(command)
        ports[role].flush()


def _expect_record(
    role: str,
    port: object,
    record: str,
    nonce: str,
    core: str,
    transcript: list[str],
    timeout_seconds: float = 15.0,
) -> dict[str, str]:
    """! @brief 역할·nonce·revision이 일치하는 단일 record를 기다립니다. """
    deadline = time.monotonic() + timeout_seconds
    while True:
        line = _line(port, deadline)
        transcript.append(f"{role}: {line}")
        fields = _fields(line)
        if "|FAIL|" in line:
            raise MeshExecutionFailure(
                f"{role} target FAIL: {fields.get('stage', 'unknown')}"
            )
        if fields.get("nonce") != nonce or fields.get("core") != core:
            raise MeshExecutionFailure(f"{role} identity mismatch")
        if line.startswith(f"{PROTOCOL}|{record}|"):
            if fields.get("role") != role:
                raise MeshExecutionFailure(f"{record} role mismatch")
            return fields


def _read_session(
    ports: dict[str, object],
    nonce: str,
    core: str,
    transcript: list[str],
) -> dict[str, dict[str, str]]:
    """! @brief 세 UART를 함께 읽어 BEGIN·RESULT·END를 엄격히 수집합니다. """
    begins: set[str] = set()
    ends: set[str] = set()
    results: dict[str, dict[str, str]] = {}
    deadline = time.monotonic() + 600.0
    while time.monotonic() < deadline and ends != set(ROLES):
        progressed = False
        for role, port in ports.items():
            payload = port.readline()
            if not payload:
                continue
            progressed = True
            if len(payload) > 768:
                raise MeshExecutionFailure("serial line overlong")
            line = payload.decode("ascii", errors="replace").strip()
            if not line.startswith(PROTOCOL + "|"):
                if line:
                    transcript.append(f"{role}-raw: {line}")
                continue
            transcript.append(f"{role}: {line}")
            fields = _fields(line)
            if "|FAIL|" in line:
                raise MeshExecutionFailure(
                    f"{role} target FAIL: {fields.get('stage', 'unknown')}"
                )
            if fields.get("nonce") != nonce or fields.get("core") != core:
                raise MeshExecutionFailure(f"{role} identity mismatch")
            if line.startswith(f"{PROTOCOL}|BEGIN|"):
                if fields.get("role") != role or role in begins:
                    raise MeshExecutionFailure("BEGIN mismatch")
                begins.add(role)
            elif line.startswith(f"{PROTOCOL}|RESULT|"):
                if fields.get("role") != role or role in results:
                    raise MeshExecutionFailure("RESULT mismatch")
                _validate_result(role, fields)
                results[role] = fields
            elif line.startswith(f"{PROTOCOL}|END|"):
                if fields.get("role") != role or fields.get("status") != "pass":
                    raise MeshExecutionFailure("END mismatch")
                ends.add(role)
        if not progressed:
            time.sleep(0.005)
    if begins != set(ROLES) or ends != set(ROLES) or set(results) != set(ROLES):
        raise MeshExecutionFailure("role result timeout")
    return results


def cleanup_ports(
    ports: dict[str, object],
    nonce: str,
    core: str,
    transcript: list[str],
    timeout_seconds: float = 30.0,
) -> dict:
    """! @brief Friend/LPN 순서를 지키며 열린 모든 endpoint의 STOP을 검증합니다. """

    report = {
        "required": bool(ports),
        "command_sent": {role: False for role in ROLES},
        "records": {},
        "friend_local_callback": False,
        "friend_peer_callback": False,
        "peer_ack_sent": False,
        "errors": [],
        "status": "NOT_REQUIRED" if not ports else "FAIL",
    }
    stop = f"{PROTOCOL}|STOP|nonce={nonce}\n".encode("ascii")
    for role in ("node_a", "node_b", "provisioner"):
        if role not in ports:
            report["errors"].append(f"{role} serial was not opened")
            continue
        try:
            _command(ports, (role,), stop)
            report["command_sent"][role] = True
        except Exception as error:
            report["errors"].append(f"{role} STOP: {type(error).__name__}: {error}")
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        progressed = False
        for role, port in ports.items():
            if role in report["records"]:
                continue
            try:
                payload = port.readline()
            except Exception as error:
                report["errors"].append(
                    f"{role} cleanup read: {type(error).__name__}: {error}"
                )
                continue
            if not payload:
                continue
            progressed = True
            line = payload.decode("ascii", errors="replace").strip()
            if not line.startswith(PROTOCOL + "|"):
                continue
            transcript.append(f"{role}: {line}")
            try:
                parsed = _fields(line)
            except Exception as error:
                report["errors"].append(
                    f"{role} cleanup parse: {type(error).__name__}: {error}"
                )
                continue
            if (
                role == "node_a"
                and line.startswith(f"{PROTOCOL}|FRIEND_CLEAR_LOCAL|")
                and parsed.get("role") == role
                and parsed.get("nonce") == nonce
                and parsed.get("core") == core
            ):
                report["friend_local_callback"] = True
                continue
            if (
                role == "node_b"
                and line.startswith(f"{PROTOCOL}|FRIEND_CLEAR_PEER|")
                and parsed.get("role") == role
                and parsed.get("nonce") == nonce
                and parsed.get("core") == core
            ):
                report["friend_peer_callback"] = True
                if "node_a" in ports and not report["peer_ack_sent"]:
                    try:
                        peer_ack = (
                            f"{PROTOCOL}|PEER_ACK|nonce={nonce}|core={core}\n"
                        ).encode("ascii")
                        _command(ports, ("node_a",), peer_ack)
                        report["peer_ack_sent"] = True
                    except Exception as error:
                        report["errors"].append(
                            "node_a PEER_ACK: "
                            f"{type(error).__name__}: {error}"
                        )
                continue
            if (
                line.startswith(f"{PROTOCOL}|STOPPED|")
                and parsed.get("role") == role
                and parsed.get("nonce") == nonce
                and parsed.get("core") == core
            ):
                try:
                    report["records"][role] = _validate_friend_clear(role, parsed)
                except Exception as error:
                    report["errors"].append(
                        f"{role} STOP validation: {type(error).__name__}: {error}"
                    )
        callbacks_complete = (
            set(ports) != set(ROLES)
            or (
                report["friend_local_callback"]
                and report["friend_peer_callback"]
                and report["peer_ack_sent"]
            )
        )
        if ports and callbacks_complete and all(
                report["command_sent"][role] and role in report["records"]
                for role in ports):
            report["status"] = "PASS"
            return report
        if not progressed:
            time.sleep(0.005)
    if ports:
        report["errors"].append("bounded Mesh cleanup evidence incomplete")
    return report


def close_ports(ports: dict[str, object]) -> dict[str, str]:
    """! @brief 부분 serial open을 포함해 handle close 결과를 보존합니다. """

    result = {role: "NOT_OPENED" for role in ROLES}
    for role, port in ports.items():
        try:
            port.close()
            result[role] = "PASS"
        except Exception as error:
            result[role] = f"FAIL:{type(error).__name__}:{error}"
    return result


def execute(args: argparse.Namespace) -> dict:
    """! @brief 세 image를 V2 sector flash하고 W06 3-role traffic을 검증합니다. """
    prefix = args.output_prefix.resolve()
    native_path = prefix.with_suffix(".json")
    if native_path.exists() or prefix.with_suffix(".transcript.log").exists():
        raise MeshExecutionFailure("기존 attempt evidence를 덮어쓰지 않습니다")
    lock = json.loads(
        (REPOSITORY / "tools/ci/ncs-3.4.0.lock.json").read_text(encoding="utf-8")
    )
    sdk = args.sdk_root.resolve()
    identity = ExpectedIdentity(
        git_revision(REPOSITORY),
        git_revision(BOARD_ROOT),
        git_revision(sdk / "nrf"),
        git_revision(sdk / "zephyr"),
    )
    if (
        identity.board != lock["board"]["revision"]
        or identity.ncs != lock["ncs"]["revision"]
        or identity.zephyr != lock["zephyr"]["revision"]
    ):
        raise MeshExecutionFailure("board/SDK revision lock mismatch")
    dirty = subprocess.run(
        ["git", "-C", str(REPOSITORY), "status", "--porcelain=v1", "--untracked-files=all"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    if dirty and not args.development:
        raise MeshExecutionFailure("exact HIL에는 clean source commit이 필요합니다")

    serial_module, list_ports = import_pyserial()
    boards: dict[str, dict] = {}
    images: dict[str, Path] = {}
    build_records: dict[str, dict[str, str]] = {}
    for role in ROLES:
        digest = getattr(args, f"probe_{role}_sha256")
        image = getattr(args, f"hex_{role}").resolve()
        if not image.is_file() or image.suffix.lower() != ".hex":
            raise MeshExecutionFailure(f"{role} target image missing")
        uid, volume, vcom = discover(digest, list_ports)
        images[role] = image
        build_records[role] = validate_build_record(
            image, identity.core, identity.board, APPLICATION_ROOT
        )
        boards[role] = {
            "uid": uid,
            "image": image,
            "probe_sha256": digest,
            "volume": volume,
            "vcom": vcom,
            "image_sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
        }
    if len({board["uid"] for board in boards.values()}) != len(ROLES):
        raise MeshExecutionFailure("세 역할이 서로 다른 probe에 매핑되지 않음")
    sidecars = reserve_sidecars(native_path, ROLES)
    copy_program_inputs(images, sidecars)
    program_images = {role: sidecars[role]["image"] for role in ROLES}

    transcript: list[str] = []
    results: dict[str, dict[str, str]] = {}
    capacities: dict[str, dict[str, int]] = {}
    friend_clear: dict[str, dict[str, int | str]] = {}
    nonces: list[str] = []
    cycle_records: list[dict] = []
    status = "FAIL"
    reason: str | None = None
    ports: dict[str, object] = {}
    active_nonce: str | None = None
    flash_records: dict[str, dict[str, str]] = {}
    readback_records: dict[str, dict] = {}
    programming_receipt = None
    cleanup: dict = {"required": False, "status": "NOT_REQUIRED", "records": {}}
    close_result = {role: "NOT_OPENED" for role in ROLES}

    try:
        with ProbeLocks([board["uid"] for board in boards.values()]):
            for role in ROLES:
                board = boards[role]
                board["registers"] = collect_register_identity(
                    board["uid"], board["volume"]
                )
                mode, byte_count = flash_image_pyocd(
                    role,
                    board["uid"],
                    program_images[role],
                    120.0,
                    hardware_reset=True,
                    cmsis_dap_v1=False,
                    preserve_nrf54l_access=True,
                )
                board["flash_mode"] = mode
                board["flash_bytes"] = byte_count
                flash_records[role] = {"mode": mode, "bytes": str(byte_count)}
            readback_records, programming_receipt = readback_programmed_images(
                {role: board["uid"] for role, board in boards.items()},
                {role: board["probe_sha256"] for role, board in boards.items()},
                program_images,
                sidecars,
            )
            time.sleep(2.0)
            for role, board in boards.items():
                ports[role] = serial_module.Serial(
                    board["vcom"], 115200, timeout=0.05
                )
            for port in ports.values():
                port.reset_input_buffer()
            for role in ROLES:
                ports[role].write(f"{PROTOCOL}|PROBE\n".encode("ascii"))
                ports[role].flush()
                line = _line(ports[role], time.monotonic() + 10.0)
                transcript.append(f"{role}: {line}")
                fields = _fields(line)
                if (
                    not line.startswith(f"{PROTOCOL}|READY|")
                    or fields.get("role") != role
                    or fields.get("core") != identity.core
                ):
                    raise MeshExecutionFailure(f"{role} READY mismatch")
                capacities[role] = _validate_capacity(fields)

            for cycle in range(1, CYCLE_TARGET + 1):
                cycle_start = len(transcript)
                nonce = hashlib.sha256(
                    f"{time.time_ns()}:{cycle}:{identity.core}".encode("ascii")
                ).hexdigest()[:32]
                if nonce in nonces:
                    raise MeshExecutionFailure("Mesh session nonce collision")
                nonces.append(nonce)
                active_nonce = nonce
                cleared_records: dict[str, dict] = {}
                clear = (
                    f"{PROTOCOL}|CLEAR|nonce={nonce}|core={identity.core}\n"
                ).encode("ascii")
                for role in ("node_a", "node_b", "provisioner"):
                    _command(ports, (role,), clear)
                    cleared = _expect_record(
                        role,
                        ports[role],
                        "CLEARED",
                        nonce,
                        identity.core,
                        transcript,
                        30.0,
                    )
                    cleared_records[role] = _validate_cleared(role, cleared, cycle)

                start = (
                    f"{PROTOCOL}|START|nonce={nonce}|core={identity.core}\n"
                ).encode("ascii")
                _command(ports, ("node_a", "node_b"), start)
                time.sleep(0.25)
                _command(ports, ("provisioner",), start)
                results = _read_session(ports, nonce, identity.core, transcript)
                cleanup = cleanup_ports(ports, nonce, identity.core, transcript)
                if cleanup["status"] != "PASS":
                    raise MeshExecutionFailure(
                        f"cycle {cycle} resource cleanup was not proven"
                    )
                active_nonce = None
                friend_clear = cleanup["records"]
                cycle_lines = transcript[cycle_start:]
                cycle_records.append(
                    {
                        "cycle": cycle,
                        "nonce": nonce,
                        "status": "PASS",
                        "transcript_sha256": _cycle_transcript_sha256(cycle_lines),
                        "transcript_line_start": cycle_start + 1,
                        "transcript_line_end": len(transcript),
                        "cleared": cleared_records,
                        "results": results,
                        "friend_clear": friend_clear,
                        "cleanup": cleanup,
                        "semantics": {
                            "provision_two_nodes": "PASS",
                            "mesh_security": "PASS",
                            "lpn_friend_clear": "PASS",
                            "rejoin": "PASS",
                            "cleanup": "PASS",
                        },
                    }
                )

            validate_cycle_records(cycle_records, transcript)
            status = "PASS_CANDIDATE" if dirty else "PASS"
    except Exception as error:
        reason = f"{type(error).__name__}: {error}"
        reason = re.sub(r"(?i)\b[0-9a-f]{16,64}\b", "<redacted-identity>", reason)
        reason = re.sub(
            r"(?i)(?:uid|probe_id)=[^\s,;]+", "uid=<redacted>", reason
        )
    finally:
        try:
            cleanup = cleanup_ports(
                ports,
                active_nonce or "0" * 32,
                identity.core,
                transcript,
            ) if active_nonce is not None else cleanup
        except Exception as error:
            cleanup = {
                "required": active_nonce is not None,
                "status": "FAIL",
                "records": {},
                "errors": [f"cleanup exception: {type(error).__name__}: {error}"],
            }
        finally:
            close_result = close_ports(ports)
        friend_clear = cleanup.get("records", {})
        if cleanup["status"] == "FAIL" or any(
                value.startswith("FAIL:") for value in close_result.values()):
            status = "FAIL"
            cleanup_reason = "resource cleanup was not proven"
            reason = cleanup_reason if reason is None else f"{reason}; {cleanup_reason}"

    exact_program: dict[str, dict] = {}
    attestation: dict | None = None
    if status.startswith("PASS"):
        try:
            if status == "PASS":
                require_exact_clean_source(REPOSITORY, identity.core)
            validate_programming_receipt(programming_receipt, ROLES, readback_records)
            exact_program = exact_program_evidence(
                ROLES,
                {role: boards[role]["probe_sha256"] for role in ROLES},
                sidecars,
                flash_records,
                build_records,
                readback_records,
            )
            if status == "PASS":
                attestation = dispatch_attestation(
                    "m32_mesh",
                    identity.core,
                    CYCLE_TARGET,
                    (
                        "provision_two_nodes",
                        "mesh_security",
                        "lpn_friend_clear",
                        "rejoin",
                        "cleanup",
                    ),
                    ROLES,
                    exact_program,
                )
        except Exception as error:
            status = "FAIL"
            reason = f"exact programming proof: {type(error).__name__}: {error}"

    public_boards = {
        role: {key: value for key, value in board.items() if key not in {"uid", "image"}}
        for role, board in boards.items()
    }
    provisioner = results.get("provisioner", {})
    evidence = {
        "test_ids": ["M32-MESH-01:traffic", "M32-MESHSEC-01:traffic"],
        "status": status,
        "scope": "three_board_mesh_provisioning_model_traffic",
        "source_clean": not bool(dirty),
        "identity": vars(identity),
        "boards": public_boards,
        "nonces": nonces,
        "cycles": len(cycle_records),
        "cycle_records": cycle_records,
        "results": results,
        "build_records": build_records,
        "cleanup": cleanup,
        "serial_close": close_result,
        "exact_programming": exact_program,
        "capacities": capacities,
        "message_denominators": {
            "base_per_cycle": BASE_MESSAGE_TARGET,
            "secured_per_cycle": SECURED_MESSAGE_TARGET,
            "acknowledged_per_cycle": int(provisioner.get("acknowledged", "0")),
            "base_total": BASE_MESSAGE_TARGET * len(cycle_records),
            "secured_total": SECURED_MESSAGE_TARGET * len(cycle_records),
            "acknowledged_total": sum(
                int(row["results"]["provisioner"]["acknowledged"])
                for row in cycle_records
            ),
        },
        "negative_denominators": {
            "unprovisioned_access_per_cycle": sum(
                int(results.get(role, {}).get("unprovisioned_rejected", "0"))
                for role in ("node_a", "node_b")
            ),
            "invalid_destination_per_cycle": int(
                provisioner.get("invalid_destination_rejected", "0")
            ),
            "wrong_key_per_cycle": int(provisioner.get("wrong_key_rejected", "0")),
            "unprovisioned_access_total": sum(
                int(row["results"][role]["unprovisioned_rejected"])
                for row in cycle_records
                for role in ("node_a", "node_b")
            ),
            "invalid_destination_total": sum(
                int(row["results"]["provisioner"]["invalid_destination_rejected"])
                for row in cycle_records
            ),
            "wrong_key_total": sum(
                int(row["results"]["provisioner"]["wrong_key_rejected"])
                for row in cycle_records
            ),
        },
        "sdk_risk_regression": {
            "mesh_lpn_friend_clear": {
                "condition": "ttl_zero_friend_clear_confirm_before_first_retry",
                "roles": friend_clear,
                "status": "PASS" if status.startswith("PASS") else "FAIL",
            },
        },
        "latency_limit_ms": LATENCY_LIMIT_MS,
        "reason": reason,
    }
    if attestation is not None:
        evidence["m33_dispatch_attestation"] = attestation
    _save(prefix, evidence, transcript)
    return evidence


def main() -> int:
    """! @brief raw UID 없이 세 역할의 W06 Mesh HIL을 실행합니다. """
    parser = argparse.ArgumentParser()
    for role in ROLES:
        option = role.replace("_", "-")
        parser.add_argument(f"--probe-{option}-sha256", required=True)
        parser.add_argument(f"--hex-{option}", required=True, type=Path)
    parser.add_argument("--sdk-root", required=True, type=Path)
    parser.add_argument("--output-prefix", required=True, type=Path)
    parser.add_argument("--development", action="store_true")
    args = parser.parse_args()
    try:
        result = execute(args)
    except Exception as error:
        message = re.sub(r"(?i)\b[0-9a-f]{16,64}\b", "<redacted-identity>", str(error))
        print(f"M32_MESH_HIL_FAIL: {type(error).__name__}: {message[:400]}", file=sys.stderr)
        return 1
    print(
        f"M32_MESH_HIL_STATUS={result['status']};"
        f"SOURCE_CLEAN={str(result['source_clean']).lower()}"
    )
    return 0 if result["status"] == "PASS" or (
        args.development and result["status"] == "PASS_CANDIDATE"
    ) else 1


if __name__ == "__main__":
    sys.exit(main())
