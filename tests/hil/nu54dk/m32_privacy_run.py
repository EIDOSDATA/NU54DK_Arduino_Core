#!/usr/bin/env python3
"""! @brief 세 SHA-256 NU54DK 역할의 W04 identity/privacy HIL 증거를 수집합니다. """

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


ROLES = ("identity_a", "identity_b", "peer")
PROTOCOL = "M32PRIV|1"
ITERATION_TARGET = 20
PACKET_TARGET = 200
CONNECTION_TARGET = 20
ALLOWED_LOSS = 0
LATENCY_LIMIT_MS = 1000


class PrivacyExecutionFailure(RuntimeError):
    """! @brief mapping·flash·UART·identity 분모 검증의 제한된 실패입니다. """


def _line(port: object, deadline: float) -> str:
    """! @brief DAPLink 잡음에서 M32 privacy protocol 줄만 반환합니다. """
    while time.monotonic() < deadline:
        payload = port.readline()
        if len(payload) > 512:
            raise PrivacyExecutionFailure("serial line overlong")
        line = payload.decode("ascii", errors="replace").strip()
        if line.startswith(PROTOCOL + "|"):
            return line
    raise PrivacyExecutionFailure("serial line timeout")


def _fields(line: str) -> dict[str, str]:
    """! @brief key=value field 중 중복이 없는 record만 허용합니다. """
    output: dict[str, str] = {}
    for field in line.split("|")[3:]:
        if "=" not in field:
            continue
        key, value = field.split("=", 1)
        if key in output:
            raise PrivacyExecutionFailure(f"duplicate field: {key}")
        output[key] = value
    return output


def _integer(fields: dict[str, str], key: str) -> int:
    """! @brief 필수 decimal field를 음이 아닌 정수로 변환합니다. """
    value = fields.get(key, "")
    if re.fullmatch(r"[0-9]+", value) is None:
        raise PrivacyExecutionFailure(f"invalid integer field: {key}")
    return int(value)


def _address(fields: dict[str, str]) -> tuple[str, int]:
    """! @brief READY의 canonical address와 public/random type을 검증합니다. """
    address = fields.get("address", "")
    if re.fullmatch(r"(?:[0-9A-F]{2}:){5}[0-9A-F]{2}", address) is None:
        raise PrivacyExecutionFailure("invalid READY address")
    address_type = _integer(fields, "type")
    if address_type not in (0, 1):
        raise PrivacyExecutionFailure("invalid READY address type")
    return address, address_type


def _save(prefix: Path, evidence: dict, transcript: list[str]) -> None:
    """! @brief attempt 원본과 SHA-256을 덮어쓰기 없이 보존합니다. """
    raw = ("\n".join(transcript) + "\n").encode("ascii", errors="replace")
    if b"uid=" in raw.lower() or b"probe_id=" in raw.lower():
        raise PrivacyExecutionFailure("raw probe UID in transcript")
    if prefix.with_suffix(".json").exists() or prefix.with_suffix(
        ".transcript.log"
    ).exists():
        raise PrivacyExecutionFailure("기존 attempt evidence를 덮어쓰지 않습니다")
    prefix.parent.mkdir(parents=True, exist_ok=True)
    evidence["transcript_sha256"] = hashlib.sha256(raw).hexdigest()
    evidence["observed_utc"] = datetime.now(timezone.utc).isoformat()
    prefix.with_suffix(".transcript.log").write_bytes(raw)
    prefix.with_suffix(".json").write_text(
        json.dumps(evidence, indent=2) + "\n", encoding="utf-8"
    )


def execute(args: argparse.Namespace) -> dict:
    """! @brief 세 image를 sector flash하고 identity/list 재연결과 STOP을 검증합니다. """
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
        raise PrivacyExecutionFailure("board/SDK revision lock mismatch")
    dirty = subprocess.run(
        ["git", "-C", str(REPOSITORY), "status", "--porcelain=v1", "--untracked-files=all"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    if dirty and not args.development:
        raise PrivacyExecutionFailure("exact HIL에는 clean source commit이 필요합니다")

    serial_module, list_ports = import_pyserial()
    boards: dict[str, dict] = {}
    for role in ROLES:
        digest = getattr(args, f"probe_{role}_sha256")
        image = getattr(args, f"hex_{role}").resolve()
        if not image.is_file() or image.suffix.lower() != ".hex":
            raise PrivacyExecutionFailure(f"{role} target image missing")
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
        raise PrivacyExecutionFailure("세 역할이 서로 다른 probe에 매핑되지 않음")

    nonce = hashlib.sha256(
        f"{time.time_ns()}:{identity.core}".encode("ascii")
    ).hexdigest()[:32]
    transcript: list[str] = []
    results: dict[str, dict[str, str]] = {}
    ready: dict[str, tuple[str, int]] = {}
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
                    raise PrivacyExecutionFailure(f"{role} READY mismatch")
                ready[role] = _address(fields)
            if len({value for value in ready.values()}) != len(ROLES):
                raise PrivacyExecutionFailure("local identity addresses are not unique")

            peer_address, peer_type = ready["peer"]
            a_address, a_type = ready["identity_a"]
            b_address, b_type = ready["identity_b"]
            start_a = (
                f"{PROTOCOL}|START|nonce={nonce}|core={identity.core}|"
                f"p={peer_address}|pt={peer_type}\n"
            ).encode("ascii")
            ports["identity_a"].write(start_a)
            ports["identity_a"].flush()
            line = _line(ports["identity_a"], time.monotonic() + 15.0)
            transcript.append(f"identity_a: {line}")
            fields = _fields(line)
            if (
                not line.startswith(f"{PROTOCOL}|BEGIN|")
                or fields.get("role") != "identity_a"
                or fields.get("nonce") != nonce
                or fields.get("core") != identity.core
            ):
                raise PrivacyExecutionFailure("identity_a BEGIN mismatch")

            start_b = (
                f"{PROTOCOL}|START|nonce={nonce}|core={identity.core}|"
                f"p={peer_address}|pt={peer_type}|a={a_address}|at={a_type}\n"
            ).encode("ascii")
            ports["identity_b"].write(start_b)
            ports["identity_b"].flush()
            b_begin = False
            b_negative = False
            phase_deadline = time.monotonic() + 30.0
            while time.monotonic() < phase_deadline and not (b_begin and b_negative):
                line = _line(ports["identity_b"], phase_deadline)
                transcript.append(f"identity_b: {line}")
                fields = _fields(line)
                if "|FAIL|" in line:
                    raise PrivacyExecutionFailure(
                        f"identity_b target FAIL: {fields.get('stage')}"
                    )
                if fields.get("nonce") != nonce or fields.get("core") != identity.core:
                    raise PrivacyExecutionFailure("identity_b phase identity mismatch")
                if line.startswith(f"{PROTOCOL}|BEGIN|"):
                    b_begin = fields.get("role") == "identity_b"
                elif line.startswith(f"{PROTOCOL}|NEG|"):
                    b_negative = (
                        fields.get("role") == "identity_b"
                        and _integer(fields, "unauthorized_peer_rejected") == 1
                    )

            if not (b_begin and b_negative):
                raise PrivacyExecutionFailure("identity_b unauthorized phase timeout")

            for role in ("identity_a", "identity_b"):
                ports[role].write(f"{PROTOCOL}|ARM|nonce={nonce}\n".encode("ascii"))
                ports[role].flush()
                line = _line(ports[role], time.monotonic() + 10.0)
                transcript.append(f"{role}: {line}")
                fields = _fields(line)
                if (
                    not line.startswith(f"{PROTOCOL}|ARMED|")
                    or fields.get("role") != role
                    or fields.get("nonce") != nonce
                    or fields.get("core") != identity.core
                ):
                    raise PrivacyExecutionFailure(f"{role} ARM mismatch")

            start_peer = (
                f"{PROTOCOL}|START|nonce={nonce}|core={identity.core}|"
                f"a={a_address}|at={a_type}|b={b_address}|bt={b_type}\n"
            ).encode("ascii")
            ports["peer"].write(start_peer)
            ports["peer"].flush()

            begins = {"identity_a", "identity_b"}
            ends: set[str] = set()
            deadline = time.monotonic() + 290.0
            while time.monotonic() < deadline and ends != set(ROLES):
                progressed = False
                for role in ROLES:
                    payload = ports[role].readline()
                    if not payload:
                        continue
                    progressed = True
                    if len(payload) > 512:
                        raise PrivacyExecutionFailure("serial line overlong")
                    line = payload.decode("ascii", errors="replace").strip()
                    if not line.startswith(PROTOCOL + "|"):
                        continue
                    transcript.append(f"{role}: {line}")
                    fields = _fields(line)
                    if "|FAIL|" in line:
                        raise PrivacyExecutionFailure(
                            f"{role} target FAIL: {fields.get('stage')}"
                        )
                    if fields.get("nonce") != nonce or fields.get("core") != identity.core:
                        raise PrivacyExecutionFailure(f"{role} identity mismatch")
                    if line.startswith(f"{PROTOCOL}|BEGIN|"):
                        if fields.get("role") != role or role in begins:
                            raise PrivacyExecutionFailure("BEGIN mismatch")
                        begins.add(role)
                    elif line.startswith(f"{PROTOCOL}|RESULT|"):
                        if fields.get("role") != role or role in results:
                            raise PrivacyExecutionFailure("RESULT mismatch")
                        results[role] = fields
                    elif line.startswith(f"{PROTOCOL}|END|"):
                        if fields.get("role") != role or fields.get("status") != "pass":
                            raise PrivacyExecutionFailure("END mismatch")
                        ends.add(role)
                if not progressed:
                    time.sleep(0.005)

            if begins != set(ROLES) or ends != set(ROLES) or set(results) != set(ROLES):
                raise PrivacyExecutionFailure("role result timeout")
            for role in ("identity_a", "identity_b"):
                fields = results[role]
                if _integer(fields, "connections") != CONNECTION_TARGET or _integer(
                    fields, "disconnections"
                ) != CONNECTION_TARGET:
                    raise PrivacyExecutionFailure(f"{role} reconnection denominator mismatch")
                for key in ("wrong_identity_rejected", "active_list_change_rejected"):
                    if _integer(fields, key) != 1:
                        raise PrivacyExecutionFailure(f"{role} {key} mismatch")
            if _integer(results["identity_a"], "unauthorized_peer_rejected") != 0 or _integer(
                results["identity_b"], "unauthorized_peer_rejected"
            ) != 1:
                raise PrivacyExecutionFailure("unauthorized peer negative mismatch")
            peer = results["peer"]
            for key in (
                "connections_a",
                "connections_b",
                "disconnections_a",
                "disconnections_b",
            ):
                if _integer(peer, key) != CONNECTION_TARGET:
                    raise PrivacyExecutionFailure(f"peer {key} denominator mismatch")
            if _integer(peer, "packets") != PACKET_TARGET:
                raise PrivacyExecutionFailure("peer packet denominator mismatch")
            if _integer(peer, "max_latency_ms") > LATENCY_LIMIT_MS:
                raise PrivacyExecutionFailure("peer latency limit")
            for role, fields in results.items():
                if fields.get("callback_context") != "pass":
                    raise PrivacyExecutionFailure(f"{role} callback context")

            for role in ROLES:
                ports[role].write(f"{PROTOCOL}|STOP|nonce={nonce}\n".encode("ascii"))
                ports[role].flush()
                line = _line(ports[role], time.monotonic() + 30.0)
                transcript.append(f"{role}: {line}")
                fields = _fields(line)
                if (
                    not line.startswith(f"{PROTOCOL}|STOPPED|role={role}")
                    or fields.get("cleanup") != "pass"
                    or fields.get("nonce") != nonce
                    or fields.get("core") != identity.core
                ):
                    raise PrivacyExecutionFailure(f"{role} STOP mismatch")
            status = "PASS_CANDIDATE" if dirty else "PASS"
        except Exception as error:
            reason = f"{type(error).__name__}: {error}"
            reason = re.sub(r"(?i)\b[0-9a-f]{16,64}\b", "<redacted-identity>", reason)
            reason = re.sub(r"(?i)(?:uid|probe_id)=[^\s,;]+", "uid=<redacted>", reason)
        finally:
            for port in ports.values():
                port.close()

    public_boards = {
        role: {key: value for key, value in board.items() if key not in {"uid", "image"}}
        for role, board in boards.items()
    }
    peer = results.get("peer", {})
    packets = int(peer.get("packets", "0"))
    evidence = {
        "test_ids": ["M32-PRIV-01:primary"],
        "status": status,
        "scope": "three_board_identity_privacy_accept_list_reconnection_contract",
        "source_clean": not bool(dirty),
        "identity": vars(identity),
        "boards": public_boards,
        "local_addresses": {
            role: {"address": value[0], "type": value[1]}
            for role, value in ready.items()
        },
        "nonce": nonce,
        "iterations": ITERATION_TARGET,
        "packet_denominator": PACKET_TARGET,
        "results": results,
        "negative_denominators": {
            "wrong_identity": sum(
                int(results.get(role, {}).get("wrong_identity_rejected", "0"))
                for role in ("identity_a", "identity_b")
            ),
            "unauthorized_peer": int(
                results.get("identity_b", {}).get("unauthorized_peer_rejected", "0")
            ),
            "active_list_change": sum(
                int(results.get(role, {}).get("active_list_change_rejected", "0"))
                for role in ("identity_a", "identity_b")
            ),
        },
        "allowed_loss": {"identity_reports": ALLOWED_LOSS},
        "lost": {"identity_reports": max(0, PACKET_TARGET - packets)},
        "latency_limit_ms": LATENCY_LIMIT_MS,
        "reason": reason,
    }
    _save(prefix, evidence, transcript)
    return evidence


def main() -> int:
    """! @brief raw UID 없이 세 역할의 exact W04 identity/privacy HIL을 실행합니다. """
    parser = argparse.ArgumentParser()
    for role in ROLES:
        parser.add_argument(f"--probe-{role.replace('_', '-')}-sha256", required=True)
        parser.add_argument(f"--hex-{role.replace('_', '-')}", required=True, type=Path)
    parser.add_argument("--sdk-root", required=True, type=Path)
    parser.add_argument("--output-prefix", required=True, type=Path)
    parser.add_argument("--development", action="store_true")
    args = parser.parse_args()
    try:
        result = execute(args)
    except Exception as error:
        message = re.sub(r"(?i)\b[0-9a-f]{16,64}\b", "<redacted-identity>", str(error))
        print(
            f"M32_PRIV_HIL_FAIL: {type(error).__name__}: {message[:400]}",
            file=sys.stderr,
        )
        return 1
    print(
        f"M32_PRIV_HIL_STATUS={result['status']};"
        f"SOURCE_CLEAN={str(result['source_clean']).lower()}"
    )
    return 0 if result["status"] == "PASS" or (
        args.development and result["status"] == "PASS_CANDIDATE"
    ) else 1


if __name__ == "__main__":
    sys.exit(main())
