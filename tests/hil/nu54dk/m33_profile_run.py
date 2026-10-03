#!/usr/bin/env python3
"""! @brief 명시 실행 승인으로 profile 역할 image를 sector flash하고 nonce 증거를 보존합니다. """
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time

from ble_pair_hil_common import BOARD_ROOT, flash_image_pyocd, git_revision
from m6_serial_echo import import_pyserial
from m32_ble_capability_run import collect_register_identity, discover
from v04_protocol import ProbeLocks

ROOT = Path(__file__).resolve().parents[3]
PROTOCOL = "M33PROFILE|1"
NATIVE_PASSKEY_EVENTS = {1, 2}
NATIVE_BOND_RESTORED_CANDIDATE = 9
NATIVE_BOND_VERIFIED = 10
NATIVE_SECURITY_CHANGED = 14


class StartBarrierFailure(ValueError):
    """! @brief 시작 barrier의 역할과 단계를 오류 증거에 보존합니다. """
    def __init__(self, role: str, stage: str):
        super().__init__(f"{role}: start barrier missing: {stage}")
        self.role = role
        self.stage = stage


def fields(line: str) -> dict[str, str]:
    """! @brief 중복 key·과대 줄은 해석하지 않습니다. """
    if len(line) > 512:
        raise ValueError("protocol line too long")
    result = {}
    for field in line.split("|")[3:]:
        if "=" in field:
            key, value = field.split("=", 1)
            if key in result:
                raise ValueError("duplicate protocol key")
            result[key] = value
    return result


def canonical_digest(value) -> str:
    """! @brief 순서와 공백에 무관한 JSON 값의 SHA-256을 계산합니다. """
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def load_build_identities(entries: list[list[str]] | None, family: str,
                          boards: dict) -> dict[str, dict[str, str]]:
    """! @brief 실행 image를 source snapshot이 있는 exact build record에 결합합니다. """
    if family == "native" and (entries is None or len(entries) != 3):
        raise ValueError("native run requires three exact build records")
    if entries is None:
        return {}
    records = {}
    for role, filename in entries:
        if role in records or role not in boards:
            raise ValueError("build record role mismatch")
        path = Path(filename).resolve()
        record = json.loads(path.read_text(encoding="utf-8"))
        expected_family = "standard" if family == "native" and role == "watcher" else family
        if (record.get("schema") != "nucode-m33-profile-build-v1"
                or record.get("source_revision") != git_revision(ROOT)
                or record.get("role") != role or record.get("family") != expected_family):
            raise ValueError("build record family/role mismatch")
        image_sha256 = record.get("sha256")
        if image_sha256 != boards[role]["image_sha256"]:
            raise ValueError("build record image hash mismatch")
        image_path = Path(record.get("image", "")).resolve()
        board_image = Path(boards[role].get("image", image_path)).resolve()
        if image_path != board_image or not image_path.is_file() or hashlib.sha256(
                image_path.read_bytes()).hexdigest() != image_sha256:
            raise ValueError("build record image path mismatch")
        descriptors = {**record.get("artifacts", {}), **record.get("provenance", {})}
        if set(descriptors) != {"elf", "config", "sysbuild", "compile_commands", "build_info"}:
            raise ValueError("build record artifact provenance missing")
        paths = {}
        for name, descriptor in descriptors.items():
            if not isinstance(descriptor, dict):
                raise ValueError("build record artifact descriptor invalid")
            artifact = Path(descriptor.get("path", "")).resolve()
            expected = descriptor.get("sha256")
            if (not artifact.is_file() or not isinstance(expected, str)
                    or not re.fullmatch(r"[0-9a-f]{64}", expected)
                    or hashlib.sha256(artifact.read_bytes()).hexdigest() != expected):
                raise ValueError("build record artifact hash mismatch: " + name)
            paths[name] = artifact
        from m33_profile_build_record import validate_compile_identity
        command_sha256 = validate_compile_identity(
            paths["compile_commands"], expected_family, role, record["source_revision"], ROOT)
        command = record.get("command_identity")
        if command != {"sha256": command_sha256,
                       "compile_commands_sha256": descriptors["compile_commands"]["sha256"],
                       "build_info_sha256": descriptors["build_info"]["sha256"]}:
            raise ValueError("build record command identity mismatch")
        config = paths["config"].read_text(encoding="utf-8")
        sysbuild = paths["sysbuild"].read_text(encoding="utf-8")
        if (not re.search(r"^CONFIG_SOC_NRF54L15_CPUAPP=y\r?$", config, re.MULTILINE)
                or re.findall(r"^(SB_CONFIG_FLPRCORE_\w+)=y\r?$", sysbuild, re.MULTILINE)
                   != ["SB_CONFIG_FLPRCORE_NONE"]):
            raise ValueError("build record target configuration mismatch")
        sources = record.get("owned_source_sha256")
        if not isinstance(sources, dict) or not sources:
            raise ValueError("build record source snapshot missing")
        for name, digest in sources.items():
            if not isinstance(name, str):
                raise ValueError("build record source name is invalid")
            source = (ROOT / name).resolve()
            if (not source.is_relative_to(ROOT)
                    or not isinstance(digest, str)
                    or not re.fullmatch(r"[0-9a-f]{64}", digest)
                    or not source.is_file()
                    or hashlib.sha256(source.read_bytes()).hexdigest() != digest):
                raise ValueError("build record source hash mismatch: " + str(name))
        records[role] = {
            "manifest_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "image_sha256": image_sha256,
            "source_sha256": canonical_digest(sources),
        }
    if set(records) != set(boards):
        raise ValueError("build record role set mismatch")
    if family == "native" and len({record["source_sha256"] for record in records.values()}) != 1:
        raise ValueError("native role source snapshots differ")
    return records


def new_native_security() -> dict[str, dict]:
    """! @brief native 양쪽 역할의 보안 event 원시 분모를 초기화합니다. """
    return {role: {"passkey_events": 0, "security_changed_levels": [],
                   "bond_restored_candidates": 0, "bond_verified": 0}
            for role in ("server", "client")}


def track_native_security(security: dict[str, dict], role: str, kind: str,
                          value: dict[str, str]) -> None:
    """! @brief native security progress를 역할별로 손실 없이 집계합니다. """
    if kind != "PROGRESS" or value.get("reason") != "security-event" or role not in security:
        return
    try:
        event = int(value["security_event"])
        level = int(value["level"])
    except (KeyError, ValueError) as error:
        raise ValueError("native security event is malformed") from error
    record = security[role]
    if event in NATIVE_PASSKEY_EVENTS:
        record["passkey_events"] += 1
    elif event == NATIVE_BOND_RESTORED_CANDIDATE:
        record["bond_restored_candidates"] += 1
    elif event == NATIVE_BOND_VERIFIED:
        record["bond_verified"] += 1
    elif event == NATIVE_SECURITY_CHANGED:
        record["security_changed_levels"].append(level)


def validate_native_security(phase: str, results: dict, stats: dict,
                             security: dict[str, dict]) -> None:
    """! @brief fresh pairing과 재부팅 bond 복원을 서로 대체할 수 없게 검증합니다. """
    if (phase not in ("fresh", "restored") or not isinstance(results, dict)
            or not isinstance(stats, dict) or not isinstance(security, dict)
            or set(security) != {"server", "client"}
            or not isinstance(results.get("client"), dict)
            or any(not isinstance(record, dict) for record in security.values())):
        raise ValueError("native security phase missing")
    summaries = {"server": stats, "client": results["client"]}
    for role, record in security.items():
        passkeys = record.get("passkey_events")
        levels = record.get("security_changed_levels")
        expected_passkeys = 1 if phase == "fresh" else 0
        if passkeys != expected_passkeys or summaries[role].get("passkey_events") != str(passkeys):
            raise ValueError(f"native {phase} {role} passkey denominator")
        if levels != [4, 4, 4]:
            raise ValueError(f"native {phase} {role} exact L4 denominator")
        if phase == "restored" and (record.get("bond_restored_candidates") != 3
                                     or record.get("bond_verified") != 3):
            raise ValueError(f"native restored {role} persistence denominator")


def public_board_identity(boards: dict) -> dict:
    """! @brief pair 연결에 필요한 익명 probe/image identity만 반환합니다. """
    if not isinstance(boards, dict):
        return {}
    return {role: {key: board.get(key) for key in ("probe_sha256", "image_sha256")}
            for role, board in boards.items() if isinstance(board, dict)}


def validate_native_predecessor(path: Path, revisions: dict, boards: dict,
                                build_identity: dict) -> str:
    """! @brief restored 실행을 직전 fresh 성공 증거와 exact image/source에 결합합니다. """
    raw = path.read_bytes()
    evidence = json.loads(raw)
    if (evidence.get("schema") != "nucode-m33-profile-hil-v1"
            or evidence.get("family") != "native"
            or evidence.get("native_security_phase") != "fresh"
            or evidence.get("status") not in ("PASS", "DEVELOPMENT_PASS")
            or evidence.get("reason") is not None
            or evidence.get("late_failures") != []
            or evidence.get("native_prior_evidence_sha256") is not None
            or evidence.get("revisions") != revisions
            or evidence.get("build_identity") != build_identity
            or public_board_identity(evidence.get("boards", {})) != public_board_identity(boards)):
        raise ValueError("restored predecessor identity mismatch")
    validate_native_security("fresh", evidence.get("results", {}),
                             evidence.get("server", {}), evidence.get("native_security", {}))
    return hashlib.sha256(raw).hexdigest()


def validate_results(family: str, results: dict, stats: dict) -> None:
    """! @brief 실제 수신·오류 거부·두 link 관측의 분모를 확인합니다. """
    if family == "standard":
        for role, minimum in (("client", 30), ("watcher", 25)):
            value = results[role]
            if int(value.get("profiles", -1)) != 7 or int(value.get("measurements", -1)) < minimum:
                raise ValueError(f"{role}: profile/measurement denominator")
            if int(value.get("rejected", -1)) != 3:
                raise ValueError(f"{role}: negative denominator")
            if value.get("att_gap_rejects") != "3":
                raise ValueError(f"{role}: GAP/detailed ATT pair denominator")
        if (int(stats.get("max_links", -1)) != 2 or int(stats.get("email_deliveries", -1)) < 5
                or int(stats.get("alert_denied", -1)) < 5):
            raise ValueError("two-link ANS evidence missing")
        positive = results["client"].get("bms_positive")
        if positive not in ("0", "1") or stats.get("bms_positive") != positive:
            raise ValueError("BMS scoped positive denominator")
        if int(stats.get("bond_deletions", -1)) != int(positive):
            raise ValueError("unexpected bond deletion")
        if results["client"].get("bms_client_cleanup") != positive:
            raise ValueError("BMS client fresh-bond cleanup missing")
        teardown = results["client"].get("bms_teardown_errors")
        if teardown not in ("0", "1") or (positive == "0" and teardown != "0"):
            raise ValueError("BMS bounded teardown denominator")
        if positive == "0" and stats.get("bms_skipped") != "1":
            raise ValueError("BMS omission lacks explicit NOT_RUN")
        sends = stats.get("send_stats", {})
        if set(sends) != {f"{slot}:{profile}" for slot in range(2) for profile in range(5)}:
            raise ValueError("link/profile send denominator missing")
        for key, value in sends.items():
            if int(value.get("sent", -1)) < 5 or value.get("no_ccc") != "1":
                raise ValueError("link/profile send denominator: " + key)
        if (stats.get("no_ccc_errors") != "10" or stats.get("pending_errors") != "0"
                or stats.get("dropped_events") != "0"):
            raise ValueError("expected error/event overflow denominator")
    else:
        value = results["client"]
        for key, expected in (("object_operations", 14), ("glucose", 2), ("native_checks", 7), ("single_link", 1),
                              ("native_sessions", 3), ("normal_reconnects", 1), ("coc_cancels", 1),
                              ("cancel_reconnects", 1), ("reconnect_reads", 1), ("reconnect_writes", 1),
                              ("authenticated_links", 3)):
            if int(value.get(key, -1)) != expected:
                raise ValueError(f"native denominator: {key}")
        if (int(stats.get("object_writes", -1)) != 3 or int(stats.get("single_link", -1)) != 1
                or int(stats.get("native_links", -1)) != 3 or int(stats.get("native_disconnects", -1)) < 2
                or int(stats.get("authenticated_links", -1)) != 3):
            raise ValueError("native server evidence missing")


def failure_details(role: str, value: dict[str, str]) -> dict[str, str]:
    """! @brief target의 제한된 실패 단계·원시 오류를 JSON 증거에도 보존합니다. """
    details = {"role": role[:16]}
    for key in ("reason", "stage", "ble_error", "ble_driver", "security_error", "security_driver",
                "profile_index", "phase", "count", "measurements", "rejected", "quiet_since",
                "last_gatt", "last_gatt_at", "last_gatt_status", "last_att_error", "level",
                "peer_valid", "connected", "object_stage", "event_type", "event_status",
                "object_id", "object_length", "object_error", "type_ok", "length_ok", "data_ok",
                "accepted", "object_busy", "gap_event", "link_role", "hci_reason", "same_peer",
                "link_valid", "link_connected", "event_handle_valid", "security_event",
                "native_links", "stop_commands", "alert_slot", "alert_ccc", "alert_sent",
                "bms_teardown_errors", "glucose_stage", "char_valid", "char_properties",
                "value_handle", "ccc_handle", "client_busy", "discovered", "response_length", "response_bytes"):
        if key in value:
            details[key] = value[key][:96]
    return details


def start_roles(family: str, ports: dict, start: bytes, receive, consume,
                clock=time.monotonic) -> None:
    """! @brief 광고·보안 준비 barrier를 관측한 뒤 다음 역할을 시작합니다. """
    plan = (("watcher", "advertising-ready"), ("server", "hub-ready"), ("client", None)) if family == "standard" else (("server", None), ("client", None))
    for role, barrier in plan:
        ports[role].write(start)
        ports[role].flush()
        if barrier is None:
            continue
        deadline = clock() + 30.0
        ready = False
        while clock() < deadline and not ready:
            for observed_role in ports:
                response = receive(observed_role)
                if response is None:
                    continue
                kind, value = response
                consume(observed_role, kind, value)
                if observed_role == role and kind == "PROGRESS" and value.get("reason") == barrier:
                    ready = True
                    break
        if not ready:
            raise StartBarrierFailure(role, barrier)


def validate_stop_record(kind: str, value: dict, nonce: str, stopped: bool) -> bool:
    """! @brief late FAIL·nonce·중복 STOP과 실제 자원 미정리를 성공으로 접지 않습니다. """
    if value.get("nonce") != nonce:
        raise ValueError("STOP nonce mismatch")
    if kind == "FAIL":
        raise ValueError("late target FAIL: " + value.get("reason", "unknown"))
    if kind == "STOPPED":
        if stopped:
            raise ValueError("duplicate STOPPED")
        for key in ("native_links", "links", "pending", "scan", "advertising", "watchdog"):
            if value.get(key) != "0":
                raise ValueError("STOP cleanup denominator: " + key)
        return True
    return stopped


def bms_transition(stage: int, role: str, kind: str, value: dict) -> tuple[int, str, str]:
    """! @brief 신규 bond 소유증명과 scoped 삭제 결과 뒤에만 client 단계를 넘깁니다. """
    if (stage == 0 and role == "client" and kind == "BMS_READY"
            and value.get("negative_checks") == "2" and value.get("client_fresh") == "1"):
        return 1, "server", "ARM"
    if stage == 1 and role == "server" and kind == "BMS_ARMED" and value.get("fresh") == "1":
        return 2, "client", "BMS_DELETE"
    if stage == 1 and role == "server" and kind == "BMS_SKIPPED" and value.get("reason") == "preexisting-or-unproven-bond":
        return 4, "client", "BMS_SKIP"
    if (stage == 2 and role == "server" and kind == "BMS_DELETED"
            and all(value.get(key) == "1" for key in ("accepted", "fresh", "watcher_unchanged", "requester_absent"))):
        return 3, "client", "BMS_DONE"
    if (stage == 3 and role == "client" and kind == "BMS_CLEANED"
            and all(value.get(key) == "1" for key in ("fresh", "server_absent", "existing_unchanged", "disconnected"))):
        return 5, "", ""
    raise ValueError("BMS handshake/ownership evidence mismatch")


def execute(args: argparse.Namespace) -> dict:
    """! @brief erase/recover 없이 고정 SDK·hash role mapping·UART completion을 확인합니다. """
    required = {"server", "client", "watcher"}
    if len(args.role) != len(required) or {entry[0] for entry in args.role} != required:
        raise ValueError("role mapping mismatch")
    if args.family == "native" and args.native_security_phase not in ("fresh", "restored"):
        raise ValueError("native security phase is required")
    if args.family == "standard" and (args.native_security_phase is not None
                                      or args.native_prior_evidence is not None):
        raise ValueError("native security options are invalid for standard family")
    if args.native_security_phase == "fresh" and args.native_prior_evidence is not None:
        raise ValueError("fresh native run must not have a predecessor")
    if args.native_security_phase == "restored" and args.native_prior_evidence is None:
        raise ValueError("restored native run requires fresh predecessor evidence")
    prefix = args.output_prefix.resolve()
    json_path = prefix.with_suffix(".json")
    log_path = prefix.with_suffix(".transcript.log")
    if json_path.exists() or log_path.exists():
        raise ValueError("existing attempt must not be overwritten")
    lock = json.loads((ROOT / "tools/ci/ncs-3.4.0.lock.json").read_text(encoding="utf-8"))
    sdk = args.sdk_root.resolve()
    revisions = {"core": git_revision(ROOT), "board": git_revision(BOARD_ROOT),
                 "ncs": git_revision(sdk / "nrf"), "zephyr": git_revision(sdk / "zephyr")}
    for key in ("board", "ncs", "zephyr"):
        if revisions[key] != lock[key]["revision"]:
            raise ValueError(f"{key} revision differs from NCS 3.4.0 lock")
    dirty = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain=v1", "--untracked-files=all"],
                           capture_output=True, text=True, check=True).stdout
    if dirty and not args.development:
        raise ValueError("dirty source requires --development; it cannot produce release PASS")
    serial, list_ports = import_pyserial()
    boards = {}
    for role, digest, filename in args.role:
        image = Path(filename).resolve()
        if not image.is_file() or image.suffix.lower() != ".hex":
            raise ValueError("existing role .hex required")
        uid, volume, vcom = discover(digest, list_ports)
        boards[role] = {"uid": uid, "volume": volume, "vcom": vcom, "image": image,
                        "probe_sha256": digest, "image_sha256": hashlib.sha256(image.read_bytes()).hexdigest()}
    if len({board["uid"] for board in boards.values()}) != len(boards):
        raise ValueError("roles must map to distinct physical probes")
    build_identity = load_build_identities(args.build_record, args.family, boards)
    predecessor_sha256 = None
    if args.native_prior_evidence is not None:
        predecessor_sha256 = validate_native_predecessor(
            args.native_prior_evidence.resolve(), revisions, boards, build_identity)
    if not args.execute:
        return {"status": "NOT_RUN", "reason": "preflight only; --execute authorizes selected image sector flash",
                "family": args.family, "native_security_phase": args.native_security_phase,
                "native_prior_evidence_sha256": predecessor_sha256,
                "build_identity": build_identity}
    nonce = hashlib.sha256(f"{time.time_ns()}:{revisions['core']}".encode()).hexdigest()[:32]
    transcript, results, stats, ends = [], {}, {}, set()
    ports = {}
    reason = None
    target_failure = None
    begins = set()
    progress_fields = {}
    late_failures = []
    cleanup = {}
    bms_stage = 0
    bms_evidence = {}
    native_security = new_native_security()

    def consume(role: str, kind: str, value: dict) -> None:
        nonlocal target_failure, bms_stage
        if value.get("nonce") != nonce:
            raise ValueError("nonce mismatch")
        if kind == "FAIL":
            target_failure = failure_details(role, {**progress_fields.get(role, {}), **value})
            raise ValueError(f"{role}: {value.get('reason', 'target failure')}")
        if kind == "PROGRESS":
            progress_fields.setdefault(role, {}).update(failure_details(role, value))
            if args.family == "native":
                track_native_security(native_security, role, kind, value)
        if kind.startswith("BMS_"):
            if args.family != "standard":
                raise ValueError("unexpected native BMS handshake")
            bms_stage, destination, verb = bms_transition(bms_stage, role, kind, value)
            bms_evidence[kind] = value
            if destination:
                ports[destination].write(f"{PROTOCOL}|{verb}|nonce={nonce}\n".encode())
                ports[destination].flush()
        if kind == "BEGIN":
            if role in begins:
                raise ValueError("duplicate BEGIN")
            begins.add(role)
        elif kind == "RESULT":
            if role in results:
                raise ValueError("duplicate RESULT")
            results[role] = value
        elif kind == "END":
            if value.get("status") != "pass" or role in ends:
                raise ValueError("END status/duplicate")
            ends.add(role)

    def receive(role: str, timeout: float = 0.0) -> tuple[str, dict] | None:
        deadline = time.monotonic() + timeout
        while True:
            payload = ports[role].readline()
            if payload:
                line = payload.decode("ascii", errors="replace").strip()
                if line.startswith(PROTOCOL + "|"):
                    transcript.append(f"{role}: {line}")
                    value = fields(line)
                    if value.get("role") != role or value.get("core") != revisions["core"]:
                        raise ValueError("target role/revision mismatch")
                    return line.split("|")[2], value
            if time.monotonic() >= deadline:
                return None

    with ProbeLocks([board["uid"] for board in boards.values()]):
        try:
            for role, board in boards.items():
                board["registers"] = collect_register_identity(board["uid"], board["volume"])
                board["flash_mode"], board["flash_bytes"] = flash_image_pyocd(
                    role, board["uid"], board["image"], 120.0,
                    hardware_reset=True, preserve_nrf54l_access=True)
            time.sleep(2.0)
            for role, board in boards.items():
                ports[role] = serial.Serial(board["vcom"], 115200, timeout=0.05)
                ports[role].reset_input_buffer()
                ports[role].write(f"{PROTOCOL}|PROBE\n".encode())
                response = receive(role, 10.0)
                if response is None or response[0] != "READY":
                    raise ValueError("missing READY")
            start = f"{PROTOCOL}|START|nonce={nonce}|core={revisions['core']}\n".encode()
            start_roles(args.family, ports, start, receive, consume)
            clients = required - {"server"} if args.family == "standard" else {"client"}
            deadline = time.monotonic() + 180.0
            while time.monotonic() < deadline and ends != clients:
                for role in ports:
                    response = receive(role)
                    if response is None:
                        continue
                    kind, value = response
                    consume(role, kind, value)
            expected_begins = required if args.family == "standard" else {"server", "client"}
            if begins != expected_begins or ends != clients or set(results) != clients:
                raise ValueError("missing role completion")
        except Exception as error:
            reason = str(error)
            if isinstance(error, StartBarrierFailure):
                target_failure = failure_details(error.role, {
                    **progress_fields.get(error.role, {}), "reason": "start-barrier-timeout",
                    "stage": error.stage})
        finally:
            for role, port in ports.items():
                try:
                    port.write(f"{PROTOCOL}|STOP|nonce={nonce}\n".encode())
                    deadline = time.monotonic() + 15.0
                    stopped = False
                    while time.monotonic() < deadline:
                        response = receive(role)
                        if response is None:
                            continue
                        kind, value = response
                        try:
                            previously_stopped = stopped
                            stopped = validate_stop_record(kind, value, nonce, stopped)
                        except ValueError as error:
                            reason = reason or f"{role}: {error}"
                            detail = failure_details(role, {**progress_fields.get(role, {}), **value})
                            if len(late_failures) < 16:
                                late_failures.append(detail)
                            target_failure = target_failure or detail
                            continue
                        if role == "server" and kind in ("SERVER_STATS", "NATIVE_STATS", "ERROR_STATS"):
                            stats.update(value)
                        if role == "server" and kind == "SEND_STATS":
                            key = value.get("slot", "") + ":" + value.get("profile", "")
                            if key in stats.setdefault("send_stats", {}):
                                raise ValueError("duplicate SEND_STATS")
                            stats["send_stats"][key] = value
                        if stopped and not previously_stopped:
                            cleanup[role] = value
                            deadline = min(deadline, time.monotonic() + 0.2)
                        elif kind not in ("STOPPED", "SERVER_STATS", "NATIVE_STATS", "SEND_STATS", "ERROR_STATS"):
                            try:
                                consume(role, kind, value)
                            except ValueError as error:
                                reason = reason or f"{role}: {error}"
                    if not stopped:
                        raise ValueError("STOP acknowledgement missing")
                except Exception as error:
                    reason = reason or f"{role}: {error}"
                finally:
                    port.close()
    if reason is None:
        try:
            validate_results(args.family, results, stats)
            if args.family == "standard" and bms_stage not in (4, 5):
                raise ValueError("BMS handshake did not reach verified cleanup")
            if args.family == "native":
                validate_native_security(args.native_security_phase, results, stats, native_security)
        except (ValueError, KeyError) as error:
            reason = str(error)
    raw = ("\n".join(transcript) + "\n").encode("ascii", errors="replace")
    if b"uid=" in raw.lower() or b"probe_id=" in raw.lower():
        raise ValueError("raw probe UID in transcript")
    evidence = {"schema": "nucode-m33-profile-hil-v1", "family": args.family,
                "status": "FAIL" if reason else "DIAGNOSTIC_PASS" if args.diagnostic_only else "DEVELOPMENT_PARTIAL" if bms_stage == 4 else "DEVELOPMENT_PASS" if dirty else "PASS",
                "reason": reason, "revisions": revisions, "development": bool(dirty),
                "diagnostic_only": args.diagnostic_only,
                "native_security_phase": args.native_security_phase,
                "native_prior_evidence_sha256": predecessor_sha256,
                "native_security": native_security if args.family == "native" else {},
                "build_identity": build_identity,
                "failure_details": target_failure,
                "late_failures": late_failures, "cleanup": cleanup,
                "observed_utc": datetime.now(timezone.utc).isoformat(),
                "transcript_sha256": hashlib.sha256(raw).hexdigest(),
                "results": results, "server": stats,
                "bms_evidence": bms_evidence,
                "not_run": ["BMS scoped positive: preexisting or unproven bond"] if bms_stage == 4 else [],
                "excluded": ["BMS reboot persistence", "native second-peer rejection", "Apple/Google interoperability"],
                "boards": {role: {key: value for key, value in board.items() if key not in ("uid", "volume", "vcom", "image")}
                           for role, board in boards.items()}}
    prefix.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("xb") as output:
        output.write(raw)
    with json_path.open("x", encoding="utf-8") as output:
        json.dump(evidence, output, indent=2)
        output.write("\n")
    return evidence


def main() -> int:
    """! @brief 기본은 읽기 전용 preflight이며 --execute 없이는 flash하지 않습니다. """
    parser = argparse.ArgumentParser()
    parser.add_argument("--family", choices=("standard", "native"), required=True)
    parser.add_argument("--role", nargs=3, action="append", metavar=("ROLE", "PROBE_SHA256", "HEX"), required=True)
    parser.add_argument("--sdk-root", type=Path, required=True)
    parser.add_argument("--output-prefix", type=Path, required=True)
    parser.add_argument("--build-record", nargs=2, action="append", metavar=("ROLE", "JSON"),
                        help="role image와 source snapshot을 결합한 exact build record")
    parser.add_argument("--native-security-phase", choices=("fresh", "restored"))
    parser.add_argument("--native-prior-evidence", type=Path,
                        help="restored 실행 직전의 fresh 성공 evidence")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--development", action="store_true")
    parser.add_argument("--diagnostic-only", action="store_true",
                        help="mixed source or diagnostic runs cannot become completion PASS")
    try:
        evidence = execute(parser.parse_args())
    except (ValueError, OSError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"M33 Profile HIL FAIL: {error}")
        return 1
    print(json.dumps(evidence, sort_keys=True))
    return int(evidence["status"] == "FAIL")


if __name__ == "__main__":
    raise SystemExit(main())
