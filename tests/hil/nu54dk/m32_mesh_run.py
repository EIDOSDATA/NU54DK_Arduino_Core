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

from ble_pair_hil_common import BOARD_ROOT, flash_image_pyocd, git_revision  # noqa: E402
from m6_serial_echo import import_pyserial  # noqa: E402
from m32_ble_capability import ExpectedIdentity  # noqa: E402
from m32_ble_capability_run import collect_register_identity, discover  # noqa: E402
from v04_protocol import ProbeLocks  # noqa: E402


ROLES = ("provisioner", "node_a", "node_b")
PROTOCOL = "M32MESH|1"
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


def execute(args: argparse.Namespace) -> dict:
    """! @brief 세 image를 V2 sector flash하고 W06 3-role traffic을 검증합니다. """
    prefix = args.output_prefix.resolve()
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
    for role in ROLES:
        digest = getattr(args, f"probe_{role}_sha256")
        image = getattr(args, f"hex_{role}").resolve()
        if not image.is_file() or image.suffix.lower() != ".hex":
            raise MeshExecutionFailure(f"{role} target image missing")
        uid, volume, vcom = discover(digest, list_ports)
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

    nonce = hashlib.sha256(
        f"{time.time_ns()}:{identity.core}".encode("ascii")
    ).hexdigest()[:32]
    transcript: list[str] = []
    results: dict[str, dict[str, str]] = {}
    capacities: dict[str, dict[str, int]] = {}
    status = "FAIL"
    reason: str | None = None

    with ProbeLocks([board["uid"] for board in boards.values()]):
        for role in ROLES:
            board = boards[role]
            board["registers"] = collect_register_identity(board["uid"], board["volume"])
            board["flash_mode"], board["flash_bytes"] = flash_image_pyocd(
                role,
                board["uid"],
                board["image"],
                120.0,
                hardware_reset=True,
                cmsis_dap_v1=False,
                preserve_nrf54l_access=True,
            )
        time.sleep(2.0)
        ports = {
            role: serial_module.Serial(board["vcom"], 115200, timeout=0.05)
            for role, board in boards.items()
        }
        try:
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

            clear = (
                f"{PROTOCOL}|CLEAR|nonce={nonce}|core={identity.core}\n"
            ).encode("ascii")
            for role in ("node_a", "node_b", "provisioner"):
                _command(ports, (role,), clear)
                cleared = _expect_record(
                    role, ports[role], "CLEARED", nonce, identity.core, transcript, 30.0
                )
                if role != "provisioner" and _integer(
                    cleared, "unprovisioned_rejected"
                ) != 1:
                    raise MeshExecutionFailure(f"{role} unprovisioned boundary")

            start = (
                f"{PROTOCOL}|START|nonce={nonce}|core={identity.core}\n"
            ).encode("ascii")
            _command(ports, ("node_a", "node_b"), start)
            time.sleep(0.25)
            _command(ports, ("provisioner",), start)
            results = _read_session(ports, nonce, identity.core, transcript)

            stop = f"{PROTOCOL}|STOP|nonce={nonce}\n".encode("ascii")
            _command(ports, ROLES, stop)
            for role in ROLES:
                stopped = _expect_record(
                    role, ports[role], "STOPPED", nonce, identity.core, transcript, 30.0
                )
                if stopped.get("cleanup") != "pass":
                    raise MeshExecutionFailure(f"{role} cleanup mismatch")
            status = "PASS_CANDIDATE" if dirty else "PASS"
        except Exception as error:
            reason = f"{type(error).__name__}: {error}"
            reason = re.sub(r"(?i)\b[0-9a-f]{16,64}\b", "<redacted-identity>", reason)
            reason = re.sub(
                r"(?i)(?:uid|probe_id)=[^\s,;]+", "uid=<redacted>", reason
            )
        finally:
            for port in ports.values():
                port.close()

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
        "nonce": nonce,
        "results": results,
        "capacities": capacities,
        "message_denominators": {
            "base": BASE_MESSAGE_TARGET,
            "secured": SECURED_MESSAGE_TARGET,
            "acknowledged": int(provisioner.get("acknowledged", "0")),
        },
        "negative_denominators": {
            "unprovisioned_access": sum(
                int(results.get(role, {}).get("unprovisioned_rejected", "0"))
                for role in ("node_a", "node_b")
            ),
            "invalid_destination": int(
                provisioner.get("invalid_destination_rejected", "0")
            ),
            "wrong_key": int(provisioner.get("wrong_key_rejected", "0")),
        },
        "latency_limit_ms": LATENCY_LIMIT_MS,
        "reason": reason,
    }
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
