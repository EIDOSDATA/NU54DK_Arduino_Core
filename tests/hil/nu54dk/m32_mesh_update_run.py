#!/usr/bin/env python3
"""! @brief 세 NU54DK에서 W08 BLOB traffic HIL을 실행합니다. """

from __future__ import annotations

import argparse
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
    clear_nrf54l_rram_pyocd,
    file_sha256,
    flash_image_pyocd,
    git_revision,
    reset_target_pyocd,
)
from m6_serial_echo import import_pyserial  # noqa: E402
from m32_ble_capability import ExpectedIdentity  # noqa: E402
from m32_ble_capability_run import collect_register_identity, discover  # noqa: E402
from m32_mesh_run import _fields, _integer, _save  # noqa: E402
from v04_protocol import ProbeLocks  # noqa: E402


ROLES = ("blob_client", "target_a", "target_b")
PROTOCOL = "M32BLOB|1"
ITERATION_TARGET = 10
CHUNKS_PER_TARGET = 2560
CLIENT_CHUNKS = CHUNKS_PER_TARGET * 2
REMOTE_NODE_TARGET = 2
SETTINGS_STORAGE_START = 0x174000
SETTINGS_STORAGE_SIZE = 0x9000


class MeshUpdateFailure(RuntimeError):
    """! @brief mapping·flash·UART·BLOB 분모 실패를 나타냅니다. """


def _validate_capacity(fields: dict[str, str]) -> dict[str, int]:
    """! @brief CDB node slot이 local provisioner와 두 target을 수용하는지 확인합니다. """
    node_slots = _integer(fields, "cdb_node_slots")
    local_slots = _integer(fields, "cdb_local_slots")
    remote_capacity = node_slots - local_slots
    if local_slots != 1 or remote_capacity < REMOTE_NODE_TARGET:
        raise MeshUpdateFailure(
            "CDB remote node capacity mismatch: "
            f"required={REMOTE_NODE_TARGET}, actual={remote_capacity}"
        )
    return {
        "cdb_node_slots": node_slots,
        "cdb_local_slots": local_slots,
        "cdb_remote_capacity": remote_capacity,
    }


def _reject_target_fault(role: str, line: str) -> None:
    """! @brief Zephyr fatal·stack fault를 session timeout 전에 즉시 거부합니다. """
    lowered = line.lower()
    if any(
        marker in lowered
        for marker in ("stack overflow", "fatal error", "usage fault", "hard fault")
    ):
        raise MeshUpdateFailure(f"{role} target fault: {line[:120]}")


def _validate_result(role: str, fields: dict[str, str]) -> None:
    """! @brief 역할별 BLOB chunk·digest·negative 분모를 판정합니다. """
    if _integer(fields, "iterations") != ITERATION_TARGET:
        raise MeshUpdateFailure(f"{role} iteration denominator")
    if _integer(fields, "chunk_size") != 128:
        raise MeshUpdateFailure(f"{role} chunk size")
    if fields.get("object_digest") != "pass":
        raise MeshUpdateFailure(f"{role} object digest")
    if role == "blob_client":
        if _integer(fields, "targets") != 2 or _integer(
            fields, "chunks"
        ) != CLIENT_CHUNKS:
            raise MeshUpdateFailure("client target/chunk denominator")
        if fields.get("suspend_resume") != "pass" or _integer(
            fields, "wrong_key_rejected"
        ) != 1:
            raise MeshUpdateFailure("client recovery/negative boundary")
        if _integer(fields, "object_size") != 32768:
            raise MeshUpdateFailure("client object size")
        return
    if _integer(fields, "chunks") != CHUNKS_PER_TARGET or _integer(
        fields, "bad_digest_rejected"
    ) != 1:
        raise MeshUpdateFailure(f"{role} chunk/digest boundary")


def _record_result(
    results: dict[str, dict[str, str]], role: str, fields: dict[str, str]
) -> None:
    """! @brief VCOM 재개방 뒤 동일한 최종 결과의 재수신을 허용합니다. """
    _validate_result(role, fields)
    previous = results.get(role)
    if previous is None:
        results[role] = fields
    elif previous != fields:
        raise MeshUpdateFailure(f"{role} repeated RESULT mismatch")


def _read_protocol_line(
    role: str,
    port: object,
    transcript: list[str],
    deadline: float,
) -> str:
    """! @brief raw fault를 보존하며 BLOB protocol 한 줄을 기다립니다. """
    while time.monotonic() < deadline:
        payload = port.readline()
        if not payload:
            continue
        if len(payload) > 768:
            raise MeshUpdateFailure("serial line overlong")
        line = payload.decode("ascii", errors="replace").strip()
        if line.startswith(PROTOCOL + "|"):
            return line
        if line:
            transcript.append(f"{role}-raw: {line}")
            _reject_target_fault(role, line)
    raise MeshUpdateFailure(f"{role} serial line timeout")


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
        line = _read_protocol_line(role, port, transcript, deadline)
        transcript.append(f"{role}: {line}")
        fields = _fields(line)
        if "|FAIL|" in line:
            raise MeshUpdateFailure(
                f"{role} target FAIL: {fields.get('stage', 'unknown')}"
            )
        if fields.get("nonce") != nonce or fields.get("core") != core:
            raise MeshUpdateFailure(f"{role} identity mismatch")
        if line.startswith(f"{PROTOCOL}|{record}|"):
            if fields.get("role") != role:
                raise MeshUpdateFailure(f"{record} role mismatch")
            return fields


def _read_session(
    ports: dict[str, object],
    port_names: dict[str, str],
    serial_module: object,
    nonce: str,
    core: str,
    transcript: list[str],
) -> dict[str, dict[str, str]]:
    """! @brief 세 UART에서 BEGIN·RESULT·END를 함께 수집합니다. """
    begins: set[str] = set()
    ends: set[str] = set()
    results: dict[str, dict[str, str]] = {}
    deadline = time.monotonic() + 10800.0
    last_seen = {role: time.monotonic() for role in ROLES}
    reopen_attempts = {role: 0 for role in ROLES}
    while time.monotonic() < deadline and ends != set(ROLES):
        progressed = False
        for role, port in ports.items():
            payload = port.readline()
            if not payload:
                continue
            progressed = True
            last_seen[role] = time.monotonic()
            reopen_attempts[role] = 0
            if len(payload) > 768:
                raise MeshUpdateFailure("serial line overlong")
            line = payload.decode("ascii", errors="replace").strip()
            if not line.startswith(PROTOCOL + "|"):
                if line:
                    transcript.append(f"{role}-raw: {line}")
                    _reject_target_fault(role, line)
                continue
            transcript.append(f"{role}: {line}")
            fields = _fields(line)
            if "|FAIL|" in line:
                raise MeshUpdateFailure(
                    f"{role} target FAIL: {fields.get('stage', 'unknown')}"
                )
            if fields.get("nonce") != nonce or fields.get("core") != core:
                raise MeshUpdateFailure(f"{role} identity mismatch")
            if line.startswith(f"{PROTOCOL}|BEGIN|"):
                if fields.get("role") != role or role in begins:
                    raise MeshUpdateFailure("BEGIN mismatch")
                begins.add(role)
            elif line.startswith(f"{PROTOCOL}|RESULT|"):
                if fields.get("role") != role:
                    raise MeshUpdateFailure("RESULT mismatch")
                _record_result(results, role, fields)
            elif line.startswith(f"{PROTOCOL}|END|"):
                if fields.get("role") != role or fields.get("status") != "pass":
                    raise MeshUpdateFailure("END mismatch")
                ends.add(role)
        if not progressed:
            now = time.monotonic()
            reopen_roles = [
                role
                for role in ROLES
                if role not in ends
                and now - last_seen[role] > 45.0
                and reopen_attempts[role] < 2
            ]
            for role in reopen_roles:
                ports[role].close()
                time.sleep(0.2)
                ports[role] = serial_module.Serial(
                    port_names[role], 115200, timeout=0.05
                )
                reopen_attempts[role] += 1
                last_seen[role] = now
                transcript.append(
                    f"{role}-raw: VCOM_REOPEN attempt={reopen_attempts[role]}"
                )
            stale_roles = [
                role
                for role in ROLES
                if role not in ends and now - last_seen[role] > 90.0
            ]
            if stale_roles:
                raise MeshUpdateFailure(
                    f"{','.join(stale_roles)} serial progress timeout"
                )
            time.sleep(0.005)
    if begins != set(ROLES) or ends != set(ROLES) or set(results) != set(ROLES):
        raise MeshUpdateFailure("role result timeout")
    return results


def execute(args: argparse.Namespace) -> dict:
    """! @brief 세 V2 probe에서 10회 × 256-chunk BLOB을 검증합니다. """
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
        raise MeshUpdateFailure("board/SDK revision lock mismatch")
    dirty = subprocess.run(
        ["git", "-C", str(REPOSITORY), "status", "--porcelain=v1", "--untracked-files=all"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    if dirty and not args.development:
        raise MeshUpdateFailure("exact HIL에는 clean source commit이 필요합니다")

    serial_module, list_ports = import_pyserial()
    boards: dict[str, dict] = {}
    for role in ROLES:
        digest = getattr(args, f"probe_{role}_sha256")
        image = getattr(args, f"hex_{role}").resolve()
        if not image.is_file() or image.suffix.lower() != ".hex":
            raise MeshUpdateFailure(f"{role} target image missing")
        uid, volume, vcom = discover(digest, list_ports)
        build_root = image.parents[2]
        boot_image = build_root / "mcuboot" / "zephyr" / "zephyr.hex"
        signed_image = image.with_name("zephyr.signed.hex")
        if not boot_image.is_file() or not signed_image.is_file():
            raise MeshUpdateFailure(f"{role} sysbuild image missing")
        boards[role] = {
            "uid": uid,
            "image": image,
            "boot_image": boot_image,
            "signed_image": signed_image,
            "probe_sha256": digest,
            "volume": volume,
            "vcom": vcom,
            "image_sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
            "boot_image_sha256": file_sha256(boot_image),
            "signed_image_sha256": file_sha256(signed_image),
        }
    if len({board["uid"] for board in boards.values()}) != len(ROLES):
        raise MeshUpdateFailure("세 역할이 서로 다른 probe에 매핑되지 않음")

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
            board["boot_flash_mode"], board["boot_flash_bytes"] = flash_image_pyocd(
                f"{role}-bootloader",
                board["uid"],
                board["boot_image"],
                120.0,
                cmsis_dap_v1=False,
                preserve_nrf54l_access=True,
                defer_reset=True,
            )
            board["signed_flash_mode"], board["signed_flash_bytes"] = flash_image_pyocd(
                f"{role}-signed",
                board["uid"],
                board["signed_image"],
                120.0,
                cmsis_dap_v1=False,
                preserve_nrf54l_access=True,
                defer_reset=True,
            )
            board["settings_clear"] = clear_nrf54l_rram_pyocd(
                role,
                board["uid"],
                SETTINGS_STORAGE_START,
                SETTINGS_STORAGE_SIZE,
                120.0,
            )
        for role in ROLES:
            board = boards[role]
            board["reset_barrier"] = reset_target_pyocd(
                role,
                board["uid"],
                30.0,
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
                line = _read_protocol_line(
                    role, ports[role], transcript, time.monotonic() + 10.0
                )
                transcript.append(f"{role}: {line}")
                fields = _fields(line)
                if (
                    not line.startswith(f"{PROTOCOL}|READY|")
                    or fields.get("role") != role
                    or fields.get("core") != identity.core
                ):
                    raise MeshUpdateFailure(f"{role} READY mismatch")
                capacities[role] = _validate_capacity(fields)
            clear = (
                f"{PROTOCOL}|CLEAR|nonce={nonce}|core={identity.core}\n"
            ).encode("ascii")
            for role in ("target_a", "target_b", "blob_client"):
                ports[role].write(clear)
                ports[role].flush()
                _expect(role, ports[role], "CLEARED", nonce, identity.core,
                        transcript, 30.0)
            start = (
                f"{PROTOCOL}|START|nonce={nonce}|core={identity.core}\n"
            ).encode("ascii")
            for role in ("target_a", "target_b"):
                ports[role].write(start)
                ports[role].flush()
            time.sleep(0.25)
            ports["blob_client"].write(start)
            ports["blob_client"].flush()
            results = _read_session(
                ports,
                {role: board["vcom"] for role, board in boards.items()},
                serial_module,
                nonce,
                identity.core,
                transcript,
            )
            stop = f"{PROTOCOL}|STOP|nonce={nonce}\n".encode("ascii")
            for role in ROLES:
                ports[role].write(stop)
                ports[role].flush()
            for role in ROLES:
                stopped = _expect(role, ports[role], "STOPPED", nonce,
                                  identity.core, transcript, 30.0)
                if stopped.get("cleanup") != "pass":
                    raise MeshUpdateFailure(f"{role} cleanup mismatch")
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
        role: {
            key: value
            for key, value in board.items()
            if key not in {"uid", "image", "boot_image", "signed_image"}
        }
        for role, board in boards.items()
    }
    evidence = {
        "test_ids": ["M32-BLOB-01:traffic"],
        "status": status,
        "scope": "three_board_blob_push_digest_recovery",
        "source_clean": not bool(dirty),
        "identity": vars(identity),
        "boards": public_boards,
        "nonce": nonce,
        "iterations": ITERATION_TARGET,
        "chunk_denominator": CLIENT_CHUNKS,
        "capacities": capacities,
        "results": results,
        "reason": reason,
    }
    _save(prefix, evidence, transcript)
    return evidence


def main() -> int:
    """! @brief raw UID 없이 W08 BLOB traffic HIL을 실행합니다. """
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
        print(f"M32_BLOB_HIL_FAIL: {type(error).__name__}: {message[:400]}", file=sys.stderr)
        return 1
    print(
        f"M32_BLOB_HIL_STATUS={result['status']};"
        f"SOURCE_CLEAN={str(result['source_clean']).lower()}"
    )
    return 0 if result["status"] == "PASS" or (
        args.development and result["status"] == "PASS_CANDIDATE"
    ) else 1


if __name__ == "__main__":
    sys.exit(main())
