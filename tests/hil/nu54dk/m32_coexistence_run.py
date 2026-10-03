#!/usr/bin/env python3
"""! @brief 세 NU54DK에서 W10 BLE·radio 공존 HIL을 순차 실행합니다. """

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

from ble_pair_hil_common import BOARD_ROOT, flash_image_pyocd, git_revision  # noqa: E402
from m6_serial_echo import import_pyserial  # noqa: E402
from m32_ble_capability import ExpectedIdentity  # noqa: E402
from m32_ble_capability_run import collect_register_identity, discover  # noqa: E402
from m32_mesh_run import _fields, _integer, _save  # noqa: E402
from v04_protocol import ProbeLocks  # noqa: E402


PROTOCOL = "M32COEX|1"
BOARD_ROLES = ("dut", "radio", "ble")
SCENARIOS = {
    "ble_154": ("dut", "radio_peer", "ble_peer"),
    "ble_esb": ("dut", "radio_peer", "ble_peer"),
    "ble_mesh": ("dut", "mesh_peer", "ble_peer"),
}
ITERATION_TARGET = 20
PACKET_TARGET = 4000
ALLOWED_LOSS = 80
SERVICE_GAP_LIMIT_MS = 500


class CoexistenceFailure(RuntimeError):
    """! @brief mapping·flash·UART·공존 분모 실패를 나타냅니다. """


def _image_argument_name(scenario: str, role: str) -> str:
    """! @brief scenario와 논리 역할을 argparse attribute로 변환합니다. """
    return f"hex_{scenario}_{role}".replace("-", "_")


def _validate_result(scenario: str, role: str, fields: dict[str, str]) -> None:
    """! @brief 역할별 4,000-frame·재시작·negative 분모를 판정합니다. """
    if _integer(fields, "iterations") != ITERATION_TARGET:
        raise CoexistenceFailure(f"{scenario}/{role} iteration denominator")
    if role == "dut":
        if _integer(fields, "ble_received") + ALLOWED_LOSS < PACKET_TARGET or _integer(
            fields, "radio_received"
        ) + ALLOWED_LOSS < PACKET_TARGET:
            raise CoexistenceFailure(f"{scenario}/dut receive denominator")
        for key in ("ble_loss", "radio_loss"):
            if _integer(fields, key) > ALLOWED_LOSS:
                raise CoexistenceFailure(f"{scenario}/dut {key}")
        for key in ("ble_corrupt", "radio_corrupt", "starvation"):
            if _integer(fields, key) != 0:
                raise CoexistenceFailure(f"{scenario}/dut {key}")
        for key in ("ble_restarts", "radio_restarts"):
            if _integer(fields, key) != 1:
                raise CoexistenceFailure(f"{scenario}/dut {key}")
        for key in ("ble_gap_ms", "radio_gap_ms"):
            if _integer(fields, key) > SERVICE_GAP_LIMIT_MS:
                raise CoexistenceFailure(f"{scenario}/dut {key}")
        if scenario != "ble_mesh" and _integer(
            fields, "double_owner_rejected"
        ) != 1:
            raise CoexistenceFailure(f"{scenario}/dut ownership negative")
        return
    if role == "ble_peer":
        if (
            _integer(fields, "sent") != PACKET_TARGET
            or _integer(fields, "reconnects") != 1
            or _integer(fields, "write_failures") != 0
        ):
            raise CoexistenceFailure(f"{scenario}/ble_peer boundary")
        return
    if role == "radio_peer":
        sent = _integer(fields, "sent")
        acknowledged = _integer(fields, "acknowledged")
        failures = _integer(fields, "failures")
        if sent != PACKET_TARGET or acknowledged + ALLOWED_LOSS < PACKET_TARGET:
            raise CoexistenceFailure(f"{scenario}/radio_peer traffic denominator")
        if failures > ALLOWED_LOSS or acknowledged + failures != sent:
            raise CoexistenceFailure(f"{scenario}/radio_peer failure boundary")
        for key in (
            "restarts",
            "invalid_configuration_rejected",
            "invalid_length_rejected",
            "double_owner_rejected",
        ):
            if _integer(fields, key) != 1:
                raise CoexistenceFailure(f"{scenario}/radio_peer {key}")
        return
    if (
        _integer(fields, "sent") != PACKET_TARGET
        or _integer(fields, "acknowledged") != PACKET_TARGET
        or _integer(fields, "restarts") != 1
        or _integer(fields, "failures") != 0
        or _integer(fields, "configuration_retries") > 3
        or _integer(fields, "acknowledgment_retries") > ALLOWED_LOSS
    ):
        raise CoexistenceFailure(f"{scenario}/mesh_peer boundary")


def _expect_record(
    scenario: str,
    role: str,
    port: object,
    record: str,
    nonce: str,
    core: str,
    transcript: list[str],
    timeout_seconds: float,
) -> dict[str, str]:
    """! @brief 한 UART에서 identity가 일치하는 지정 record를 기다립니다. """
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        payload = port.readline()
        if not payload:
            continue
        if len(payload) > 768:
            raise CoexistenceFailure(f"{scenario}/{role} serial line overlong")
        line = payload.decode("ascii", errors="replace").strip()
        if not line.startswith(PROTOCOL + "|"):
            if line:
                transcript.append(f"{scenario}/{role}-raw: {line}")
            continue
        transcript.append(f"{scenario}/{role}: {line}")
        fields = _fields(line)
        if "|FAIL|" in line:
            raise CoexistenceFailure(
                f"{scenario}/{role} target FAIL: {fields.get('stage', 'unknown')}"
            )
        if fields.get("nonce") != nonce or fields.get("core") != core:
            raise CoexistenceFailure(f"{scenario}/{role} identity mismatch")
        if line.startswith(f"{PROTOCOL}|{record}|"):
            if fields.get("role") != role:
                raise CoexistenceFailure(f"{scenario}/{record} role mismatch")
            return fields
    raise CoexistenceFailure(f"{scenario}/{role} {record} timeout")


def _read_scenario(
    scenario: str,
    roles: tuple[str, str, str],
    ports: dict[str, object],
    nonce: str,
    core: str,
    transcript: list[str],
) -> dict[str, dict[str, str]]:
    """! @brief 두 peer 완료 뒤 DUT 판정을 요청하고 세 결과를 수집합니다. """
    begins: set[str] = set()
    ends: set[str] = set()
    results: dict[str, dict[str, str]] = {}
    finish_sent = False
    finish_due: float | None = None
    peer_roles = set(roles) - {"dut"}
    deadline = time.monotonic() + 900.0
    while time.monotonic() < deadline and ends != set(roles):
        progressed = False
        for role, port in ports.items():
            payload = port.readline()
            if not payload:
                continue
            progressed = True
            if len(payload) > 768:
                raise CoexistenceFailure(f"{scenario}/{role} serial line overlong")
            line = payload.decode("ascii", errors="replace").strip()
            if not line.startswith(PROTOCOL + "|"):
                if line:
                    transcript.append(f"{scenario}/{role}-raw: {line}")
                continue
            transcript.append(f"{scenario}/{role}: {line}")
            fields = _fields(line)
            if "|FAIL|" in line:
                raise CoexistenceFailure(
                    f"{scenario}/{role} target FAIL: {fields.get('stage', 'unknown')}"
                )
            if fields.get("nonce") != nonce or fields.get("core") != core:
                raise CoexistenceFailure(f"{scenario}/{role} identity mismatch")
            if fields.get("scenario") != scenario:
                raise CoexistenceFailure(f"{scenario}/{role} scenario mismatch")
            if line.startswith(f"{PROTOCOL}|BEGIN|"):
                if fields.get("role") != role or role in begins:
                    raise CoexistenceFailure(f"{scenario} BEGIN mismatch")
                begins.add(role)
            elif line.startswith(f"{PROTOCOL}|RESULT|"):
                if fields.get("role") != role or role in results:
                    raise CoexistenceFailure(f"{scenario} RESULT mismatch")
                _validate_result(scenario, role, fields)
                results[role] = fields
            elif line.startswith(f"{PROTOCOL}|END|"):
                if fields.get("role") != role or fields.get("status") != "pass":
                    raise CoexistenceFailure(f"{scenario} END mismatch")
                ends.add(role)
        if finish_due is None and peer_roles.issubset(ends):
            finish_due = time.monotonic() + 1.0
        if not finish_sent and finish_due is not None and time.monotonic() >= finish_due:
            ports["dut"].write(f"{PROTOCOL}|FINISH|nonce={nonce}\n".encode("ascii"))
            ports["dut"].flush()
            finish_sent = True
        if not progressed:
            time.sleep(0.005)
    expected = set(roles)
    if begins != expected or ends != expected or set(results) != expected:
        raise CoexistenceFailure(f"{scenario} role result timeout")
    return results


def _run_scenario(
    scenario: str,
    roles: tuple[str, str, str],
    boards: dict[str, dict],
    images: dict[str, Path],
    serial_module: object,
    nonce: str,
    core: str,
    transcript: list[str],
) -> dict[str, dict[str, str]]:
    """! @brief 한 조합의 세 image를 V2 sector flash 후 실행합니다. """
    logical_to_board = {
        "dut": "dut",
        roles[1]: "radio",
        "ble_peer": "ble",
    }
    for role in roles:
        board = boards[logical_to_board[role]]
        mode, written = flash_image_pyocd(
            f"{scenario}-{role}",
            board["uid"],
            images[role],
            120.0,
            hardware_reset=True,
            cmsis_dap_v1=False,
            preserve_nrf54l_access=True,
        )
        board["flashes"][scenario] = {"mode": mode, "bytes": written}
    time.sleep(2.0)
    ports = {
        role: serial_module.Serial(
            boards[logical_to_board[role]]["vcom"], 115200, timeout=0.05
        )
        for role in roles
    }
    try:
        for port in ports.values():
            port.reset_input_buffer()
        for role in roles:
            ports[role].write(f"{PROTOCOL}|PROBE\n".encode("ascii"))
            ports[role].flush()
            deadline = time.monotonic() + 10.0
            while True:
                payload = ports[role].readline()
                if time.monotonic() >= deadline:
                    raise CoexistenceFailure(f"{scenario}/{role} READY timeout")
                if not payload:
                    continue
                line = payload.decode("ascii", errors="replace").strip()
                if not line.startswith(PROTOCOL + "|"):
                    if line:
                        transcript.append(f"{scenario}/{role}-raw: {line}")
                    continue
                transcript.append(f"{scenario}/{role}: {line}")
                fields = _fields(line)
                if (
                    not line.startswith(f"{PROTOCOL}|READY|")
                    or fields.get("role") != role
                    or fields.get("core") != core
                    or fields.get("scenario") != scenario
                ):
                    raise CoexistenceFailure(f"{scenario}/{role} READY mismatch")
                break
        clear = f"{PROTOCOL}|CLEAR|nonce={nonce}|core={core}\n".encode("ascii")
        for role in roles:
            ports[role].write(clear)
            ports[role].flush()
            _expect_record(
                scenario, role, ports[role], "CLEARED", nonce, core, transcript, 30.0
            )
        start = f"{PROTOCOL}|START|nonce={nonce}|core={core}\n".encode("ascii")
        ports["dut"].write(start)
        ports["dut"].flush()
        time.sleep(0.25)
        for role in roles:
            if role == "dut":
                continue
            ports[role].write(start)
            ports[role].flush()
        results = _read_scenario(
            scenario, roles, ports, nonce, core, transcript
        )
        stop = f"{PROTOCOL}|STOP|nonce={nonce}\n".encode("ascii")
        for role in roles:
            ports[role].write(stop)
            ports[role].flush()
        for role in roles:
            stopped = _expect_record(
                scenario, role, ports[role], "STOPPED", nonce, core, transcript, 30.0
            )
            if stopped.get("cleanup") != "pass":
                raise CoexistenceFailure(f"{scenario}/{role} cleanup mismatch")
        return results
    finally:
        for port in ports.values():
            port.close()


def execute(args: argparse.Namespace) -> dict:
    """! @brief 세 V2 probe에서 W10 세 공존 조합을 검증합니다. """
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
        raise CoexistenceFailure("board/SDK revision lock mismatch")
    dirty = subprocess.run(
        ["git", "-C", str(REPOSITORY), "status", "--porcelain=v1", "--untracked-files=all"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    if dirty and not args.development:
        raise CoexistenceFailure("exact HIL에는 clean source commit이 필요합니다")

    serial_module, list_ports = import_pyserial()
    boards: dict[str, dict] = {}
    for board_role in BOARD_ROLES:
        digest = getattr(args, f"probe_{board_role}_sha256")
        uid, volume, vcom = discover(digest, list_ports)
        boards[board_role] = {
            "uid": uid,
            "probe_sha256": digest,
            "volume": volume,
            "vcom": vcom,
            "flashes": {},
        }
    if len({board["uid"] for board in boards.values()}) != len(BOARD_ROLES):
        raise CoexistenceFailure("세 역할이 서로 다른 probe에 매핑되지 않음")

    scenario_images: dict[str, dict[str, Path]] = {}
    image_hashes: dict[str, dict[str, str]] = {}
    for scenario, roles in SCENARIOS.items():
        scenario_images[scenario] = {}
        image_hashes[scenario] = {}
        for role in roles:
            image = getattr(args, _image_argument_name(scenario, role)).resolve()
            if not image.is_file() or image.suffix.lower() != ".hex":
                raise CoexistenceFailure(f"{scenario}/{role} target image missing")
            scenario_images[scenario][role] = image
            image_hashes[scenario][role] = hashlib.sha256(image.read_bytes()).hexdigest()

    nonce_seed = hashlib.sha256(
        f"{time.time_ns()}:{identity.core}".encode("ascii")
    ).hexdigest()
    transcript: list[str] = []
    results: dict[str, dict[str, dict[str, str]]] = {}
    status = "FAIL"
    reason: str | None = None
    with ProbeLocks([board["uid"] for board in boards.values()]):
        for board in boards.values():
            board["registers"] = collect_register_identity(
                board["uid"], board["volume"]
            )
        try:
            for index, (scenario, roles) in enumerate(SCENARIOS.items()):
                nonce = hashlib.sha256(
                    f"{nonce_seed}:{index}:{scenario}".encode("ascii")
                ).hexdigest()[:32]
                results[scenario] = _run_scenario(
                    scenario,
                    roles,
                    boards,
                    scenario_images[scenario],
                    serial_module,
                    nonce,
                    identity.core,
                    transcript,
                )
            status = "PASS_CANDIDATE" if dirty else "PASS"
        except Exception as error:
            reason = f"{type(error).__name__}: {error}"
            reason = re.sub(r"(?i)\b[0-9a-f]{16,64}\b", "<redacted-identity>", reason)
            reason = re.sub(
                r"(?i)(?:uid|probe_id)=[^\s,;]+", "uid=<redacted>", reason
            )

    public_boards = {
        role: {key: value for key, value in board.items() if key != "uid"}
        for role, board in boards.items()
    }
    evidence = {
        "test_ids": [
            "M32-COEX-01:ble_154",
            "M32-COEX-01:ble_esb",
            "M32-COEX-01:ble_mesh",
        ],
        "status": status,
        "scope": "three_board_ble_internal_radio_coexistence",
        "source_clean": not bool(dirty),
        "identity": vars(identity),
        "boards": public_boards,
        "image_sha256": image_hashes,
        "iterations_per_scenario": ITERATION_TARGET,
        "packets_per_protocol": PACKET_TARGET,
        "allowed_loss": ALLOWED_LOSS,
        "service_gap_limit_ms": SERVICE_GAP_LIMIT_MS,
        "results": results,
        "reason": reason,
    }
    _save(prefix, evidence, transcript)
    return evidence


def main() -> int:
    """! @brief raw UID 없이 W10 공존 HIL을 실행합니다. """
    parser = argparse.ArgumentParser()
    for board_role in BOARD_ROLES:
        parser.add_argument(
            f"--probe-{board_role}-sha256", required=True
        )
    for scenario, roles in SCENARIOS.items():
        option_scenario = scenario.replace("_", "-")
        for role in roles:
            option_role = role.replace("_", "-")
            parser.add_argument(
                f"--hex-{option_scenario}-{option_role}", required=True, type=Path
            )
    parser.add_argument("--sdk-root", required=True, type=Path)
    parser.add_argument("--output-prefix", required=True, type=Path)
    parser.add_argument("--development", action="store_true")
    args = parser.parse_args()
    try:
        result = execute(args)
    except Exception as error:
        message = re.sub(r"(?i)\b[0-9a-f]{16,64}\b", "<redacted-identity>", str(error))
        print(
            f"M32_COEX_HIL_FAIL: {type(error).__name__}: {message[:400]}",
            file=sys.stderr,
        )
        return 1
    print(
        f"M32_COEX_HIL_STATUS={result['status']};"
        f"SOURCE_CLEAN={str(result['source_clean']).lower()}"
    )
    return 0 if result["status"] == "PASS" or (
        args.development and result["status"] == "PASS_CANDIDATE"
    ) else 1


if __name__ == "__main__":
    sys.exit(main())
