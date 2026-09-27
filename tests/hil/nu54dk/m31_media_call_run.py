#!/usr/bin/env python3
"""! @brief 공개 Arduino MCP/MCS 또는 CCP/TBS 2-board 실기 증거를 수집합니다. """

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
    validate_hex_image,
    validate_image_unchanged,
)
from m6_serial_echo import import_pyserial  # noqa: E402
from m31_ble_capability import ExpectedIdentity  # noqa: E402
from m31_ble_capability_run import collect_register_identity, discover  # noqa: E402
from m31_cs_ras_pair_run import hardware_reset  # noqa: E402
from m31_media_call import parse_transcript, validate_evidence_envelope  # noqa: E402
from v04_protocol import ProbeLocks  # noqa: E402


ADDRESS_PATTERN = re.compile(r"\b[0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5}\b")
IDENTITY_PATTERN = re.compile(r"(?i)\b[0-9a-f]{16,64}\b")
MEDIA_OPERATIONS = (
    (b"p", "MEDIA_PLAY"),
    (b"u", "MEDIA_PAUSE"),
    (b"+", "MEDIA_SEEK"),
    (b"n", "MEDIA_NEXT"),
    (b"b", "MEDIA_PREVIOUS"),
    (b"i", "MEDIA_SELECT"),
    (b"r", "MEDIA_REFRESH"),
)
CONFIG_REQUIREMENTS = {
    "media": {
        "provider": ("CONFIG_BT_MCS=y", "CONFIG_BT_MPL_OBJECTS=y", "CONFIG_BT_OTS_SECONDARY_SVC=y"),
        "client": ("CONFIG_BT_MCC=y", "CONFIG_BT_MCC_OTS=y", "CONFIG_BT_OTS_CLIENT=y"),
    },
    "call": {
        "provider": ("CONFIG_BT_CCP_CALL_CONTROL_SERVER=y", "CONFIG_BT_TBS=y"),
        "client": ("CONFIG_BT_CCP_CALL_CONTROL_CLIENT=y", "CONFIG_BT_TBS_CLIENT_GTBS=y"),
    },
}
EXAMPLE_ROOTS = {
    "media": {
        "provider": REPOSITORY / "libraries/NUCODE_BLE_Audio/examples/MediaControlPlayer",
        "client": REPOSITORY / "libraries/NUCODE_BLE_Audio/examples/MediaControlClient",
    },
    "call": {
        "provider": REPOSITORY / "libraries/NUCODE_BLE_Audio/examples/CallControlServer",
        "client": REPOSITORY / "libraries/NUCODE_BLE_Audio/examples/CallControlClient",
    },
}


class MediaCallExecutionFailure(RuntimeError):
    """! @brief probe·flash·UART·profile 판정의 유한 실패입니다. """


def _hash(path: Path) -> str:
    """! @brief image/config byte의 SHA-256을 반환합니다. """
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sanitize(message: str) -> str:
    """! @brief 오류에 섞일 수 있는 raw probe identity를 제거합니다. """
    message = re.sub(r"(?i)(?:uid|probe_id|unique id)=[^\s,;]+", "uid=<redacted>", message)
    return IDENTITY_PATTERN.sub("<redacted-identity>", message)[:500]


def _resolve_image_revision(revision: str) -> str:
    """! @brief image source revision을 현재 checkout과 독립된 full commit으로 해석합니다. """
    result = subprocess.run(
        ("git", "-C", str(REPOSITORY), "rev-parse", "--verify", f"{revision}^{{commit}}"),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    resolved = result.stdout.strip()
    if result.returncode != 0 or not re.fullmatch(r"[0-9a-f]{40}", resolved):
        raise MediaCallExecutionFailure("image core revision을 commit으로 해석할 수 없습니다")
    return resolved


class SerialSession:
    """! @brief 두 VCOM의 bounded ASCII public protocol만 수집합니다. """

    def __init__(self, ports: dict[str, object]) -> None:
        self.ports = ports
        self.transcript: list[str] = []

    def marker(self, payload: str) -> None:
        """! @brief host orchestration 경계를 raw identity 없이 남깁니다. """
        self.transcript.append(f"host: {payload}")

    def send(self, role: str, command: bytes) -> None:
        """! @brief 공개 예제의 한 글자 Serial 명령만 전송합니다. """
        if role not in self.ports or len(command) != 1 or command < b"+" or command > b"z":
            raise MediaCallExecutionFailure("public Serial command 형식 오류")
        self.ports[role].write(command)
        self.ports[role].flush()

    def _events(self, tolerate_non_ascii: bool = False):
        for role, port in self.ports.items():
            payload = port.readline()
            if not payload:
                continue
            if len(payload) > 512:
                raise MediaCallExecutionFailure(f"{role} UART line overlong")
            try:
                line = payload.decode("ascii").strip()
            except UnicodeDecodeError as error:
                if tolerate_non_ascii:
                    continue
                raise MediaCallExecutionFailure(f"{role} non-ASCII UART") from error
            if not line:
                continue
            line = ADDRESS_PATTERN.sub("<bt-address>", line)
            if "uid=" in line.lower() or "probe_id=" in line.lower() or "unique id" in line.lower():
                raise MediaCallExecutionFailure("raw probe UID in UART")
            self.transcript.append(f"{role}: {line}")
            if any(marker in line for marker in (
                "Stack overflow", "*****", "FATAL", "HardFault", "BusFault", " start failed",
            )):
                raise MediaCallExecutionFailure(f"{role} fatal UART: {line}")
            yield role, line

    def wait(self, predicate, timeout: float, description: str,
             tolerate_non_ascii: bool = False) -> tuple[str, str]:
        """! @brief predicate가 실제 UART line에서 닫힐 때까지만 대기합니다. """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for role, line in self._events(tolerate_non_ascii):
                if predicate(role, line):
                    return role, line
        raise MediaCallExecutionFailure(f"{description} UART timeout")


def _verify_config(profile: str, role: str, path: Path) -> None:
    """! @brief 실행 image와 별도 입력된 role Kconfig의 필수 기능을 확인합니다. """
    lines = path.read_text(encoding="utf-8").splitlines()
    required = (*CONFIG_REQUIREMENTS[profile][role], "CONFIG_FPU=y", "CONFIG_LIBLC3=y")
    missing = [option for option in required if option not in lines]
    if missing:
        raise MediaCallExecutionFailure(f"{path.name} missing {','.join(missing)}")


def _client_operation(session: SerialSession, command: bytes, label: str,
                      expected_sequence: int) -> None:
    """! @brief 제출과 remote 완료가 모두 나온 한 normal operation만 승인합니다. """
    submitted = False

    def complete(role: str, line: str) -> bool:
        nonlocal submitted
        if role != "client":
            return False
        if line == f"{label} submitted=1":
            submitted = True
            return False
        if line == f"{label} complete=1 normal_ops={expected_sequence}":
            if not submitted:
                raise MediaCallExecutionFailure(f"{label} completion before submission")
            return True
        if line.startswith(f"{label} ") and ("complete=0" in line or "rejected=1" in line):
            raise MediaCallExecutionFailure(f"{label} normal operation rejected")
        return False

    session.send("client", command)
    session.wait(complete, 30.0, label)
    _wait_state(session, "player=" if label.startswith("MEDIA_") else "call index=")


def _negative_operation(session: SerialSession, command: bytes, label: str,
                        state_prefix: str, expect_submission: bool = True) -> None:
    """! @brief remote reject와 공개 refresh recovery, 새 snapshot을 한 묶음으로 확인합니다. """
    submitted = False
    rejected = False
    recovered = False
    state_updates = 0
    required_updates = 1 if label.startswith("MEDIA_") else 2

    def result(role: str, line: str) -> bool:
        nonlocal submitted, rejected, recovered, state_updates
        if role != "client":
            return False
        if line == f"{label} submitted=1":
            if not expect_submission:
                raise MediaCallExecutionFailure(f"{label} reached remote stack")
            submitted = True
        elif line.startswith(f"{label} rejected=1 result="):
            if expect_submission != submitted:
                raise MediaCallExecutionFailure(f"{label} submission boundary mismatch")
            rejected = True
        elif line == ("MEDIA_RECOVERY result=0 native=0" if label.startswith("MEDIA_") else
                      "CALL_RECOVERY result=0 native=0"):
            recovered = True
        elif rejected and recovered and line.startswith(state_prefix):
            state_updates += 1
            return state_updates >= required_updates
        if line.startswith(f"{label} rejected=0"):
            raise MediaCallExecutionFailure(f"{label} negative request accepted")
        return False

    session.send("client", command)
    session.wait(result, 35.0, label + " recovery")


def _pace(started: float, completed: int, total: int, seconds: float) -> None:
    """! @brief 100 operations가 전체 notification soak 구간에 분산되도록 제한합니다. """
    target = started + seconds * completed / total
    remaining = target - time.monotonic()
    if remaining > 0.0:
        time.sleep(remaining)


def _wait_state(session: SerialSession, prefix: str, state: int | None = None) -> None:
    """! @brief client snapshot이 기대 state와 notification counter를 포함하는지 확인합니다. """
    def matched(role: str, line: str) -> bool:
        if role != "client" or not line.startswith(prefix) or " notifications=" not in line:
            return False
        return state is None or f" state={state} " in line

    session.wait(matched, 30.0, prefix + " state")


def _media_campaign(session: SerialSession, soak_seconds: float) -> float:
    """! @brief read/control/object/opcode 100 ops와 두 negative 각 20회를 수행합니다. """
    started = time.monotonic()
    for index in range(100):
        command, label = MEDIA_OPERATIONS[index % len(MEDIA_OPERATIONS)]
        _client_operation(session, command, label, index + 1)
        _pace(started, index + 1, 100, soak_seconds)
    elapsed = time.monotonic() - started
    session.send("client", b"s")
    _wait_state(session, "player=")
    for _attempt in range(20):
        _negative_operation(
            session, b"k", "MEDIA_NEG_OPCODE", "player=", expect_submission=False
        )
    for _attempt in range(20):
        _negative_operation(
            session, b"z", "MEDIA_NEG_STALE_OBJECT", "player=", expect_submission=False
        )
    return elapsed


def _server_call(session: SerialSession, command: bytes, label: str,
                 state: int | None = None, counted: bool | None = None) -> None:
    """! @brief call server의 합성 network 명령과 client notification을 확인합니다. """
    if label == "CALL_INCOMING":
        session.marker(f"HIL|1|CALL_INCOMING|counted={1 if counted else 0}")
    session.send("server", command)
    session.wait(
        lambda role, line: role == "server" and line == f"{label} result=0 native=0",
        30.0,
        label,
    )
    if state is not None:
        _wait_state(session, "call index=", state)


def _call_campaign(session: SerialSession, soak_seconds: float) -> float:
    """! @brief 여섯 call 동작 100 ops와 stale/state-mismatch 각 20회를 수행합니다. """
    started = time.monotonic()
    completed = 0
    client_sequence = 0
    for _cycle in range(12):
        _server_call(session, b"i", "CALL_INCOMING", state=1, counted=True)
        completed += 1
        _pace(started, completed, 100, soak_seconds)
        for command, label in ((b"a", "CALL_ACCEPT"), (b"h", "CALL_HOLD"),
                               (b"r", "CALL_RETRIEVE"), (b"x", "CALL_TERMINATE")):
            client_sequence += 1
            _client_operation(session, command, label, client_sequence)
            completed += 1
            _pace(started, completed, 100, soak_seconds)
    for _cycle in range(10):
        client_sequence += 1
        _client_operation(session, b"o", "CALL_ORIGINATE", client_sequence)
        completed += 1
        _pace(started, completed, 100, soak_seconds)
        _server_call(session, b"a", "CALL_REMOTE_ANSWER", state=4)
        for command, label in ((b"h", "CALL_HOLD"), (b"r", "CALL_RETRIEVE"),
                               (b"x", "CALL_TERMINATE")):
            client_sequence += 1
            _client_operation(session, command, label, client_sequence)
            completed += 1
            _pace(started, completed, 100, soak_seconds)
    if completed != 100 or client_sequence != 88:
        raise MediaCallExecutionFailure("call normal operation 계획 분모 오류")
    elapsed = time.monotonic() - started
    for _attempt in range(20):
        _negative_operation(session, b"j", "CALL_NEG_STALE_INDEX", "call index=")
    for _attempt in range(20):
        _server_call(session, b"i", "CALL_INCOMING", state=1, counted=False)
        _negative_operation(session, b"v", "CALL_NEG_INVALID_TRANSITION", "call index=")
        _server_call(session, b"x", "CALL_REMOTE_TERMINATE", state=0)
    return elapsed


def _reconnect_campaign(session: SerialSession, client_uid: str, profile: str) -> None:
    """! @brief client reset마다 실제 disconnect·connect·profile discovery 20/20을 확인합니다. """
    provider = "Media" if profile == "media" else "Call"
    for attempt in range(1, 21):
        session.marker(f"HIL|1|RECONNECT|attempt={attempt}")
        disconnected = False
        connected = False
        discovered = False
        snapshot_ready = False
        hardware_reset(client_uid)

        def complete(role: str, line: str) -> bool:
            nonlocal disconnected, connected, discovered, snapshot_ready
            if role == ("player" if profile == "media" else "server"):
                disconnected |= line.startswith(f"{provider} controller disconnected reason=")
                connected |= line == f"{provider} controller connected"
            elif role == "client":
                if line == ("Media discovery result=0" if profile == "media" else
                            "Call discovery result=0"):
                    discovered = True
                elif discovered and line.startswith(
                    "player=" if profile == "media" else "call index="
                ) and " notifications=" in line:
                    snapshot_ready = True
            return disconnected and connected and discovered and snapshot_ready

        session.wait(complete, 45.0, f"reconnect {attempt}", tolerate_non_ascii=True)
        session.marker(f"HIL|1|RECONNECT_OK|attempt={attempt}")


def _save(prefix: Path, evidence: dict, transcript: list[str]) -> None:
    """! @brief attempt를 덮어쓰지 않고 익명화 transcript와 JSON을 함께 저장합니다. """
    log = ("\n".join(transcript) + "\n").encode("ascii")
    if b"uid=" in log.lower() or b"probe_id=" in log.lower() or b"unique id" in log.lower() or (
        IDENTITY_PATTERN.search(log.decode("ascii")) is not None
    ):
        raise MediaCallExecutionFailure("raw probe UID in evidence")
    evidence["transcript_sha256"] = hashlib.sha256(log).hexdigest()
    evidence["observed_utc"] = datetime.now(timezone.utc).isoformat()
    prefix.parent.mkdir(parents=True, exist_ok=True)
    prefix.with_suffix(".transcript.log").write_bytes(log)
    prefix.with_suffix(".json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def execute(args: argparse.Namespace) -> dict:
    """! @brief identity·register·flash·UART 기능을 한 exact attempt로 결합합니다. """
    prefix = args.output_prefix.resolve()
    if prefix.with_suffix(".json").exists() or prefix.with_suffix(".transcript.log").exists():
        raise MediaCallExecutionFailure("기존 attempt evidence를 덮어쓰지 않습니다")
    lock = json.loads((REPOSITORY / "tools/ci/ncs-3.4.0.lock.json").read_text(encoding="utf-8"))
    sdk = args.sdk_root.resolve()
    identity = ExpectedIdentity(
        git_revision(REPOSITORY, args.expected_core_revision),
        git_revision(BOARD_ROOT), git_revision(sdk / "nrf"),
        git_revision(sdk / "zephyr"),
    )
    if identity.board != lock["board"]["revision"] or identity.ncs != lock["ncs"]["revision"] or (
        identity.zephyr != lock["zephyr"]["revision"]
    ):
        raise MediaCallExecutionFailure("board/SDK revision lock mismatch")
    dirty = subprocess.run(
        ["git", "-C", str(REPOSITORY), "status", "--porcelain=v1", "--untracked-files=all"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    if dirty and not args.development:
        raise MediaCallExecutionFailure("exact HIL에는 clean source commit이 필요합니다")
    image_core_revision = identity.core
    if args.image_core_revision:
        image_core_revision = _resolve_image_revision(args.image_core_revision)

    role_names = ("player", "client") if args.profile == "media" else ("server", "client")
    inputs = {
        role_names[0]: (args.probe_provider_sha256, args.provider_image.resolve(),
                        args.provider_config.resolve(), "provider",
                        EXAMPLE_ROOTS[args.profile]["provider"]),
        "client": (args.probe_client_sha256, args.client_image.resolve(),
                   args.client_config.resolve(), "client",
                   EXAMPLE_ROOTS[args.profile]["client"]),
    }
    serial_module, list_ports = import_pyserial()
    boards = {}
    for role, (probe_hash, image_path, config, config_role, example_root) in inputs.items():
        if not config.is_file():
            raise MediaCallExecutionFailure(f"{role} image/config missing")
        image = validate_hex_image(str(image_path))
        _verify_config(args.profile, config_role, config)
        build_record = validate_build_record(
            image, image_core_revision, identity.board, example_root
        )
        uid, volume, vcom = discover(probe_hash, list_ports)
        boards[role] = {
            "uid": uid,
            "image": image,
            "config": config,
            "probe_sha256": probe_hash,
            "volume": volume,
            "vcom": vcom,
            "image_sha256": _hash(image),
            "image_size": image.stat().st_size,
            "config_sha256": _hash(config),
            "build_record": build_record,
        }
    if boards[role_names[0]]["uid"] == boards["client"]["uid"] or (
        boards[role_names[0]]["vcom"] == boards["client"]["vcom"]
    ):
        raise MediaCallExecutionFailure("provider/client probe 또는 COM mapping 중복")

    session = None
    status = "FAIL"
    reason = None
    measurement = None
    soak_elapsed = 0.0
    try:
        with ProbeLocks([board["uid"] for board in boards.values()]):
            for role, board in boards.items():
                board["probe_registers"] = collect_register_identity(board["uid"], board["volume"])
                board["flash_mode"], board["flash_bytes"] = flash_image_pyocd(
                    role, board["uid"], board["image"], args.flash_timeout, hardware_reset=True
                )
            ports = {
                role: serial_module.Serial(board["vcom"], 115200, timeout=0.03)
                for role, board in boards.items()
            }
            session = SerialSession(ports)
            try:
                for port in ports.values():
                    port.reset_input_buffer()
                hardware_reset(boards[role_names[0]]["uid"])
                time.sleep(2.0)
                hardware_reset(boards["client"]["uid"])
                client_booted = False
                provider_connected = False
                client_discovered = False

                def initialized(role: str, line: str) -> bool:
                    nonlocal client_booted, provider_connected, client_discovered
                    if role == role_names[0]:
                        expected = "Media controller connected" if args.profile == "media" else (
                            "Call controller connected"
                        )
                        provider_connected |= line == expected
                    elif role == "client":
                        client_booted |= line.startswith("Commands:")
                        expected = "Media discovery result=0" if args.profile == "media" else (
                            "Call discovery result=0"
                        )
                        client_discovered |= line == expected
                    return client_booted and provider_connected and client_discovered

                session.wait(initialized, 45.0, "initial profile discovery",
                             tolerate_non_ascii=True)
                _wait_state(session, "player=" if args.profile == "media" else "call index=")
                soak_elapsed = _media_campaign(session, args.soak_seconds) if (
                    args.profile == "media"
                ) else _call_campaign(session, args.soak_seconds)
                _reconnect_campaign(session, boards["client"]["uid"], args.profile)
                transcript = ("\n".join(session.transcript) + "\n").encode("ascii")
                measurement = parse_transcript(args.profile, transcript, soak_elapsed)
                for board in boards.values():
                    validate_image_unchanged(
                        board["image"], board["image_size"], board["image_sha256"]
                    )
                    if _hash(board["config"]) != board["config_sha256"]:
                        raise MediaCallExecutionFailure("시험 중 config byte가 변경됐습니다")
                ending_identity = ExpectedIdentity(
                    git_revision(REPOSITORY, args.expected_core_revision),
                    git_revision(BOARD_ROOT), git_revision(sdk / "nrf"),
                    git_revision(sdk / "zephyr"),
                )
                if ending_identity != identity:
                    raise MediaCallExecutionFailure("시험 중 source/SDK revision이 변경됐습니다")
                status = "PASS_CANDIDATE" if dirty else "PASS"
            finally:
                for port in ports.values():
                    port.close()
    except Exception as error:
        reason = f"{type(error).__name__}: {_sanitize(str(error))}"

    public_boards = {
        role: {
            key: value
            for key, value in board.items()
            if key not in {"uid", "image", "config"}
        }
        for role, board in boards.items()
    }
    transcript_lines = session.transcript if session is not None else []
    transcript = ("\n".join(transcript_lines) + "\n").encode("ascii")
    evidence = {
        "test_id": "M31-AUDIO-MEDIA-CALL-01",
        "status": status,
        "profile": args.profile,
        "scope": "two_board_public_serial_profile_contract",
        "source_clean": not bool(dirty),
        "identity": vars(identity),
        "image_core_revision": image_core_revision,
        "boards": public_boards,
        "normal_operations": 100,
        "negative_iterations_per_case": 20,
        "reconnects": 20,
        "soak_seconds": round(soak_elapsed, 3),
        "measurement": vars(measurement) if measurement is not None else None,
        "reason": reason,
    }
    if status == "PASS":
        validate_evidence_envelope(
            {**evidence, "transcript": transcript,
             "transcript_sha256": hashlib.sha256(transcript).hexdigest()},
            {role: board["image_sha256"] for role, board in public_boards.items()},
            identity,
        )
    _save(prefix, evidence, transcript_lines)
    return evidence


def build_parser() -> argparse.ArgumentParser:
    """! @brief raw UID 없이 source와 image revision을 분리한 CLI를 정의합니다. """
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=("media", "call"), required=True)
    parser.add_argument("--probe-provider-sha256", required=True)
    parser.add_argument("--probe-client-sha256", required=True)
    parser.add_argument("--provider-image", required=True, type=Path)
    parser.add_argument("--client-image", required=True, type=Path)
    parser.add_argument("--provider-config", required=True, type=Path)
    parser.add_argument("--client-config", required=True, type=Path)
    parser.add_argument("--sdk-root", required=True, type=Path)
    parser.add_argument("--expected-core-revision", required=True)
    parser.add_argument("--image-core-revision")
    parser.add_argument("--output-prefix", required=True, type=Path)
    parser.add_argument("--soak-seconds", type=float, default=180.0)
    parser.add_argument("--flash-timeout", type=float, default=300.0)
    parser.add_argument("--development", action="store_true")
    return parser


def main() -> int:
    """! @brief raw UID 없이 두 probe SHA-256과 role artifact만 받습니다. """
    parser = build_parser()
    args = parser.parse_args()
    if args.soak_seconds < 180.0:
        parser.error("--soak-seconds는 180 이상이어야 합니다")
    if not 30.0 <= args.flash_timeout <= 300.0:
        parser.error("--flash-timeout은 30..300초여야 합니다")
    if args.probe_provider_sha256 == args.probe_client_sha256:
        parser.error("provider/client probe SHA-256은 달라야 합니다")
    try:
        evidence = execute(args)
    except Exception as error:
        print(f"M31_MEDIA_CALL_HIL_FAIL: {type(error).__name__}: {_sanitize(str(error))}",
              file=sys.stderr)
        return 1
    print(
        f"M31_MEDIA_CALL_HIL_STATUS={evidence['status']};PROFILE={args.profile};"
        f"SOURCE_CLEAN={str(evidence['source_clean']).lower()}"
    )
    if evidence["status"] == "PASS" or args.development and evidence["status"] == "PASS_CANDIDATE":
        return 0
    if evidence.get("reason"):
        print(evidence["reason"], file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
