#!/usr/bin/env python3
"""! @brief 세 NU54DK에서 W07 Mesh 1.1 management HIL을 실행합니다. """

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


ROLES = ("client", "server", "target")
PROTOCOL = "M32MESH11|1"
ITERATION_TARGET = 10
OPERATION_TARGET = 350
REMOTE_NODE_TARGET = 2
MESH_CAPACITY_MINIMUMS = {
    "cdb_subnets": 2,
    "cdb_app_keys": 1,
    "local_subnets": 2,
    "local_app_keys": 1,
    "model_app_keys": 1,
}
APPLICATION_ROOT = REPOSITORY / "tests/zephyr/m32_mesh_management_hil"
SEMANTICS = ("mesh_management", "target_isolation", "cleanup")


class MeshManagementFailure(RuntimeError):
    """! @brief mapping·flash·UART·Mesh 1.1 분모 실패를 나타냅니다. """


def _fields(line: str) -> dict[str, str]:
    """! @brief 중복 없는 key=value field만 반환합니다. """
    output: dict[str, str] = {}
    for field in line.split("|")[3:]:
        if "=" not in field:
            continue
        key, value = field.split("=", 1)
        if key in output:
            raise MeshManagementFailure(f"duplicate field: {key}")
        output[key] = value
    return output


def _integer(fields: dict[str, str], key: str) -> int:
    """! @brief 필수 decimal field를 음이 아닌 정수로 변환합니다. """
    value = fields.get(key, "")
    if re.fullmatch(r"[0-9]+", value) is None:
        raise MeshManagementFailure(f"invalid integer field: {key}")
    return int(value)


def _validate_capacity(fields: dict[str, str]) -> dict[str, int]:
    """! @brief CDB node와 Subnet Bridge key 용량을 topology와 대조합니다. """
    node_slots = _integer(fields, "cdb_node_slots")
    local_slots = _integer(fields, "cdb_local_slots")
    if local_slots != 1:
        raise MeshManagementFailure("CDB local provisioner slot mismatch")
    remote_capacity = node_slots - local_slots
    if remote_capacity < REMOTE_NODE_TARGET:
        raise MeshManagementFailure(
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
            raise MeshManagementFailure(
                f"Mesh capacity mismatch: {key} required={minimum}, actual={value}"
            )
        observed[key] = value
    return observed


def _line(port: object, deadline: float) -> str:
    """! @brief DAPLink 잡음에서 Mesh 1.1 protocol 줄만 반환합니다. """
    while time.monotonic() < deadline:
        payload = port.readline()
        if len(payload) > 768:
            raise MeshManagementFailure("serial line overlong")
        line = payload.decode("ascii", errors="replace").strip()
        if line.startswith(PROTOCOL + "|"):
            return line
    raise MeshManagementFailure("serial line timeout")


def _reject_target_fault(role: str, line: str) -> None:
    """! @brief Zephyr fatal·stack fault를 session timeout 전에 즉시 거부합니다. """
    lowered = line.lower()
    if any(
        marker in lowered
        for marker in ("stack overflow", "fatal error", "usage fault", "hard fault")
    ):
        raise MeshManagementFailure(f"{role} target fault: {line[:120]}")


def _save(prefix: Path, evidence: dict, transcript: list[str]) -> None:
    """! @brief 성공·실패 attempt를 덮어쓰기 없이 보존합니다. """
    raw = ("\n".join(transcript) + "\n").encode("ascii", errors="replace")
    if b"uid=" in raw.lower() or b"probe_id=" in raw.lower():
        raise MeshManagementFailure("raw probe UID in transcript")
    if prefix.with_suffix(".json").exists() or prefix.with_suffix(
        ".transcript.log"
    ).exists():
        raise MeshManagementFailure("기존 attempt evidence를 덮어쓰지 않습니다")
    prefix.parent.mkdir(parents=True, exist_ok=True)
    evidence["transcript_sha256"] = hashlib.sha256(raw).hexdigest()
    evidence["observed_utc"] = datetime.now(timezone.utc).isoformat()
    prefix.with_suffix(".transcript.log").write_bytes(raw)
    prefix.with_suffix(".json").write_text(
        json.dumps(evidence, indent=2) + "\n", encoding="utf-8"
    )


def _validate_result(role: str, fields: dict[str, str]) -> None:
    """! @brief 역할별 Remote Provisioning·기능군·negative 결과를 판정합니다. """
    if fields.get("recovery") != "pass":
        raise MeshManagementFailure(f"{role} recovery boundary")
    if role != "client":
        if _integer(fields, "provisioned") != 1 or fields.get(
            "management_server"
        ) != "pass":
            raise MeshManagementFailure(f"{role} server boundary")
        return
    expected = {
        "remote_provisioned": 1,
        "feature_groups": 7,
        "iterations": ITERATION_TARGET,
        "operations": OPERATION_TARGET,
        "malformed_rejected": 1,
        "out_of_range_rejected": 1,
        "replay_rejected": 1,
        "wrong_subnet_rejected": 1,
    }
    for key, value in expected.items():
        if _integer(fields, key) != value:
            raise MeshManagementFailure(f"client {key} denominator mismatch")
    if _integer(fields, "remote_reports") < 1:
        raise MeshManagementFailure("client remote scan report denominator")


def build_dispatch_cycle_records(results: dict[str, dict[str, str]],
                                 capacities: dict[str, dict[str, int]]) -> list[dict]:
    """! @brief 10 iteration×두 독립 remote node 결과를 20 cycle로 변환합니다. """

    if set(results) != set(ROLES) or set(capacities) != set(ROLES):
        raise MeshManagementFailure("dispatcher Mesh management role mismatch")
    for role in ROLES:
        _validate_result(role, results[role])
        if capacities[role].get("cdb_remote_capacity", 0) < REMOTE_NODE_TARGET:
            raise MeshManagementFailure("dispatcher Mesh capacity witness mismatch")
    statuses = {token: "PASS" for token in SEMANTICS}
    return [
        {
            "cycle": (iteration * REMOTE_NODE_TARGET) + offset + 1,
            "status": "PASS",
            "semantics": dict(statuses),
        }
        for iteration in range(ITERATION_TARGET)
        for offset, _role in enumerate(("server", "target"))
    ]


def _expect(
    role: str,
    port: object,
    record: str,
    nonce: str,
    core: str,
    transcript: list[str],
    timeout_seconds: float,
) -> dict[str, str]:
    """! @brief 역할·nonce·revision이 일치하는 record를 기다립니다. """
    deadline = time.monotonic() + timeout_seconds
    while True:
        line = _line(port, deadline)
        transcript.append(f"{role}: {line}")
        fields = _fields(line)
        if "|FAIL|" in line:
            raise MeshManagementFailure(
                f"{role} target FAIL: {fields.get('stage', 'unknown')}"
            )
        if fields.get("nonce") != nonce or fields.get("core") != core:
            raise MeshManagementFailure(f"{role} identity mismatch")
        if line.startswith(f"{PROTOCOL}|{record}|"):
            if fields.get("role") != role:
                raise MeshManagementFailure(f"{record} role mismatch")
            return fields


def _read_session(
    ports: dict[str, object], nonce: str, core: str, transcript: list[str]
) -> dict[str, dict[str, str]]:
    """! @brief 세 UART에서 BEGIN·RESULT·END를 함께 수집합니다. """
    begins: set[str] = set()
    ends: set[str] = set()
    results: dict[str, dict[str, str]] = {}
    deadline = time.monotonic() + 900.0
    while time.monotonic() < deadline and ends != set(ROLES):
        progressed = False
        for role, port in ports.items():
            payload = port.readline()
            if not payload:
                continue
            progressed = True
            if len(payload) > 768:
                raise MeshManagementFailure("serial line overlong")
            line = payload.decode("ascii", errors="replace").strip()
            if not line.startswith(PROTOCOL + "|"):
                if line:
                    transcript.append(f"{role}-raw: {line}")
                    _reject_target_fault(role, line)
                continue
            transcript.append(f"{role}: {line}")
            fields = _fields(line)
            if "|FAIL|" in line:
                raise MeshManagementFailure(
                    f"{role} target FAIL: {fields.get('stage', 'unknown')}"
                )
            if fields.get("nonce") != nonce or fields.get("core") != core:
                raise MeshManagementFailure(f"{role} identity mismatch")
            if line.startswith(f"{PROTOCOL}|BEGIN|"):
                if fields.get("role") != role or role in begins:
                    raise MeshManagementFailure("BEGIN mismatch")
                begins.add(role)
            elif line.startswith(f"{PROTOCOL}|RESULT|"):
                if fields.get("role") != role or role in results:
                    raise MeshManagementFailure("RESULT mismatch")
                _validate_result(role, fields)
                results[role] = fields
            elif line.startswith(f"{PROTOCOL}|END|"):
                if fields.get("role") != role or fields.get("status") != "pass":
                    raise MeshManagementFailure("END mismatch")
                ends.add(role)
        if not progressed:
            time.sleep(0.005)
    if begins != set(ROLES) or ends != set(ROLES) or set(results) != set(ROLES):
        raise MeshManagementFailure("role result timeout")
    return results


def execute(args: argparse.Namespace) -> dict:
    """! @brief 세 V2 probe의 image와 3-role Mesh 1.1 session을 검증합니다. """
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
        raise MeshManagementFailure("board/SDK revision lock mismatch")
    dirty = subprocess.run(
        ["git", "-C", str(REPOSITORY), "status", "--porcelain=v1", "--untracked-files=all"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    if dirty and not args.development:
        raise MeshManagementFailure("exact HIL에는 clean source commit이 필요합니다")

    serial_module, list_ports = import_pyserial()
    boards: dict[str, dict] = {}
    for role in ROLES:
        digest = getattr(args, f"probe_{role}_sha256")
        image = getattr(args, f"hex_{role}").resolve()
        if not image.is_file() or image.suffix.lower() != ".hex":
            raise MeshManagementFailure(f"{role} target image missing")
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
        raise MeshManagementFailure("세 역할이 서로 다른 probe에 매핑되지 않음")
    images = {role: boards[role]["image"] for role in ROLES}
    sidecars: dict = {}
    build_records: dict = {}
    if not dirty:
        sidecars, build_records = prepare_direct_program(
            prefix.with_suffix(".json"), ROLES, images, identity.core,
            identity.board, APPLICATION_ROOT,
        )

    nonce = hashlib.sha256(
        f"{time.time_ns()}:{identity.core}".encode("ascii")
    ).hexdigest()[:32]
    transcript: list[str] = []
    results: dict[str, dict[str, str]] = {}
    capacities: dict[str, dict[str, int]] = {}
    status = "FAIL"
    reason: str | None = None
    cleanup: dict[str, dict[str, str]] = {}
    exact_program = None
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
        ports: dict[str, object] = {}
        stopped_roles: set[str] = set()
        try:
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
                    raise MeshManagementFailure(f"{role} READY mismatch")
                capacities[role] = _validate_capacity(fields)

            clear = (
                f"{PROTOCOL}|CLEAR|nonce={nonce}|core={identity.core}\n"
            ).encode("ascii")
            for role in ("server", "target", "client"):
                ports[role].write(clear)
                ports[role].flush()
                _expect(role, ports[role], "CLEARED", nonce, identity.core,
                        transcript, 30.0)
            start = (
                f"{PROTOCOL}|START|nonce={nonce}|core={identity.core}\n"
            ).encode("ascii")
            for role in ("server", "target"):
                ports[role].write(start)
                ports[role].flush()
            time.sleep(0.25)
            ports["client"].write(start)
            ports["client"].flush()
            results = _read_session(ports, nonce, identity.core, transcript)

            stop = f"{PROTOCOL}|STOP|nonce={nonce}\n".encode("ascii")
            for role in ROLES:
                ports[role].write(stop)
                ports[role].flush()
            for role in ROLES:
                stopped = _expect(role, ports[role], "STOPPED", nonce,
                                  identity.core, transcript, 30.0)
                if stopped.get("cleanup") != "pass":
                    raise MeshManagementFailure(f"{role} cleanup mismatch")
                stopped_roles.add(role)
            status = "PASS_CANDIDATE" if dirty else "PASS"
        except Exception as error:
            reason = f"{type(error).__name__}: {error}"
            reason = re.sub(r"(?i)\b[0-9a-f]{16,64}\b", "<redacted-identity>", reason)
            reason = re.sub(
                r"(?i)(?:uid|probe_id)=[^\s,;]+", "uid=<redacted>", reason
            )
        finally:
            cleanup = cleanup_direct_ports(
                ports,
                {
                    role: f"{PROTOCOL}|STOP|nonce={nonce}\n".encode("ascii")
                    for role in ports
                },
                stopped_roles,
                transcript,
            )
        if status == "PASS":
            exact_program = complete_direct_program(
                REPOSITORY, identity.core, ROLES, images,
                {role: boards[role]["uid"] for role in ROLES},
                {role: boards[role]["probe_sha256"] for role in ROLES},
                sidecars,
                {
                    role: {
                        "mode": boards[role]["flash_mode"],
                        "bytes": str(boards[role]["flash_bytes"]),
                    }
                    for role in ROLES
                },
                build_records,
            )

    public_boards = {
        role: {key: value for key, value in board.items() if key not in {"uid", "image"}}
        for role, board in boards.items()
    }
    client = results.get("client", {})
    evidence = {
        "test_ids": ["M32-MESH11-01:management"],
        "status": status,
        "scope": "three_board_mesh_1_1_remote_provisioning_management",
        "source_clean": not bool(dirty),
        "identity": vars(identity),
        "boards": public_boards,
        "nonce": nonce,
        "results": results,
        "capacities": capacities,
        "iterations": int(client.get("iterations", "0")),
        "operation_denominator": int(client.get("operations", "0")),
        "negative_denominators": {
            key: int(client.get(key, "0"))
            for key in (
                "malformed_rejected",
                "out_of_range_rejected",
                "replay_rejected",
                "wrong_subnet_rejected",
            )
        },
        "reason": reason,
        "cleanup": cleanup,
    }
    if status == "PASS" and exact_program is not None:
        cycle_records = build_dispatch_cycle_records(results, capacities)
        evidence["dispatch_cycle_records"] = cycle_records
        evidence["m33_dispatch_attestation"] = dispatch_attestation(
            "m32_mesh_management", identity.core, 20, SEMANTICS, ROLES,
            exact_program, cycle_records=cycle_records,
        )
    _save(prefix, evidence, transcript)
    return evidence


def main() -> int:
    """! @brief raw UID 없이 W07 Mesh 1.1 exact HIL을 실행합니다. """
    parser = argparse.ArgumentParser()
    for role in ROLES:
        parser.add_argument(f"--probe-{role}-sha256", required=True)
        parser.add_argument(f"--hex-{role}", required=True, type=Path)
    parser.add_argument("--sdk-root", required=True, type=Path)
    parser.add_argument("--output-prefix", required=True, type=Path)
    parser.add_argument("--development", action="store_true")
    args = parser.parse_args()
    try:
        result = execute(args)
    except Exception as error:
        message = re.sub(r"(?i)\b[0-9a-f]{16,64}\b", "<redacted-identity>", str(error))
        print(
            f"M32_MESH11_HIL_FAIL: {type(error).__name__}: {message[:400]}",
            file=sys.stderr,
        )
        return 1
    print(
        f"M32_MESH11_HIL_STATUS={result['status']};"
        f"SOURCE_CLEAN={str(result['source_clean']).lower()}"
    )
    return 0 if result["status"] == "PASS" or (
        args.development and result["status"] == "PASS_CANDIDATE"
    ) else 1


if __name__ == "__main__":
    sys.exit(main())
