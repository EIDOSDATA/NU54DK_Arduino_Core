#!/usr/bin/env python3
"""! @brief 실패 HIL의 RAM 소유 증거가 있는 한 bond만 양쪽에서 정리합니다. """
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

from ble_pair_hil_common import flash_image_pyocd
from m32_ble_capability_run import discover
from m6_serial_echo import import_pyserial
from m33_profile_run import fields, validate_results, validate_stop_record
from v04_protocol import ProbeLocks


def validate_proof(attempt: dict, role: str, private: dict, public: dict) -> bytes:
    """! @brief exact 실패 image·probe·nonce·원래 목록과 peer 비포함을 모두 요구합니다. """
    if role not in ("server", "client") or attempt.get("family") != "standard" or attempt.get("status") != "FAIL":
        raise ValueError("failed standard attempt required")
    nonce = private.get("nonce", "")
    if not re.fullmatch(r"[0-9a-f]{32}", nonce):
        raise ValueError("invalid proof nonce")
    for proof in (private, public):
        if (proof.get("role") != role or proof.get("nonce") != nonce or proof.get("fresh_bond") is not True
                or any(proof.get(key) != attempt["boards"][role][key] for key in ("image_sha256", "probe_sha256"))):
            raise ValueError("proof identity mismatch")
    if nonce not in {entry.get("nonce") for entry in attempt.get("cleanup", {}).values()}:
        raise ValueError("attempt nonce not independently observed")
    if public.get("flags") != {"cleanup_complete": 1, "stop_reported": 1, "cleanup_expired": 0, "watchdog_channel": -1}:
        raise ValueError("previous fixture cleanup not proven")
    before, peer = private.get("before"), private.get("peer", "")
    if (not isinstance(before, list) or len(before) > 15 or len(set(before)) != len(before)
            or not all(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{14}", value) for value in [*before, peer])
            or peer in before or public.get("peer_not_in_startup") is not True
            or public.get("startup_bond_count") != len(before)):
        raise ValueError("unproven fresh peer")
    for key, value in (("before_sha256", "".join(before)), ("peer_sha256", peer)):
        if hashlib.sha256(bytes.fromhex(value)).hexdigest() != public.get(key):
            raise ValueError("private/public RAM proof mismatch")
    return f"M33PROFILE|1|CLEAN|nonce={nonce}|peer={peer}|before={''.join(before)}\n".encode("ascii")


def validate_ownership_chain(path: Path, original: dict) -> dict:
    """! @brief 승인된 008 원본부터 명시된 실행 순서의 exact 소유 연속성만 검증합니다. """
    chain = json.loads(path.read_text(encoding="utf-8"))
    if chain.get("schema") != "nucode-m33-profile-bond-chain-v1":
        raise ValueError("ownership chain schema")
    expected = ("cleanup008", "standard009", "standard010", "native003", "native004")
    extended = (*expected, "cleanup004", "standard011", "standard012", "native005")
    final = (*extended, "cleanup005", "standard013", "native006", "native007")
    reproduced = (*final, "cleanup007", "standard014", "native008", "native009")
    if tuple(chain.get("steps", {})) == reproduced:
        expected = reproduced
    elif tuple(chain.get("steps", {})) == final:
        expected = final
    elif tuple(chain.get("steps", {})) == extended:
        expected = extended
    elif tuple(chain.get("steps", {})) != expected:
        raise ValueError("ownership chain steps")
    checked, previous_time = {}, original["observed_utc"]
    source_baseline, source_latest, elf_latest = None, {}, {}
    cleanup_boards = {}
    for name in expected:
        step = chain["steps"][name]
        def load_exact(reference: dict) -> tuple[Path, bytes]:
            source = (path.parent / reference["path"]).resolve()
            raw = source.read_bytes()
            if hashlib.sha256(raw).hexdigest() != reference["sha256"]:
                raise ValueError("ownership chain file hash")
            return source, raw
        _, raw = load_exact(step["evidence"])
        evidence = json.loads(raw)
        _, transcript = load_exact(step["transcript"])
        if hashlib.sha256(transcript).hexdigest() != evidence["transcript_sha256"]:
            raise ValueError("ownership transcript mismatch")
        if evidence["revisions"] != original["revisions"] or evidence["observed_utc"] <= previous_time:
            raise ValueError("ownership revision/time discontinuity")
        previous_time = evidence["observed_utc"]
        for role in ("server", "client"):
            if evidence["boards"][role]["probe_sha256"] != original["boards"][role]["probe_sha256"]:
                raise ValueError("ownership board pair mismatch")
        if name.startswith("cleanup"):
            cleanup_boards = evidence["boards"]
            if (evidence.get("status") != "PASS" or
                    evidence.get("attempt_sha256") != chain["original_attempt_sha256"]):
                raise ValueError("original scoped cleanup missing")
            for role in ("server", "client"):
                if evidence["results"].get(role) != {"removed": 1, "existing_unchanged": True, "stopped": True}:
                    raise ValueError("original scoped cleanup denominator")
        else:
            if name in ("standard011", "standard013", "native007"):
                source_baseline = None
            completed = name.startswith("standard") or name in ("native007", "native008", "native009")
            if evidence.get("late_failures") or evidence.get("status") != ("DEVELOPMENT_PASS" if completed else "FAIL"):
                raise ValueError("ownership intermediate result")
            nonce = evidence["cleanup"]["server"]["nonce"]
            for role in ("server", "client", "watcher"):
                validate_stop_record("STOPPED", evidence["cleanup"][role], nonce, False)
                records = [fields(line.split(": ", 1)[1]) for line in transcript.decode("ascii").splitlines()
                           if line.startswith(role + ": M33PROFILE|1|")]
                if not records or any(record.get("nonce") not in ("", nonce) for record in records):
                    raise ValueError("ownership nonce continuity")
            if name.startswith("standard"):
                for token in ("server: M33PROFILE|1|BMS_DELETED|", "client: M33PROFILE|1|BMS_CLEANED|"):
                    lines = [line for line in transcript.decode("ascii").splitlines() if line.startswith(token)]
                    if len(lines) != 1 or "|fresh=1|" not in lines[0]:
                        raise ValueError("fresh pair deletion missing")
                for role in ("server", "client"):
                    if sum(line.startswith(role + ": ") and "|reason=fresh-test-bond" in line
                           for line in transcript.decode("ascii").splitlines()) != 1:
                        raise ValueError("fresh pair creation missing")
                if (evidence["results"]["client"].get("bms_positive") != "1" or
                        evidence["results"]["client"].get("bms_client_cleanup") != "1"):
                    raise ValueError("fresh pair cleanup missing")
            elif evidence.get("family") != "native" or evidence["server"].get("native_links") != ("3" if completed else "2" if name == "native006" else "1"):
                raise ValueError("native single pair not proven")
            if name in ("native007", "native008", "native009"):
                validate_results("native", evidence["results"], evidence["server"])
            for role in ("server", "client", "watcher"):
                _, manifest_raw = load_exact(step["manifests"][role])
                manifest = json.loads(manifest_raw)
                if manifest["sha256"] != evidence["boards"][role]["image_sha256"] or not manifest.get("owned_source_sha256"):
                    raise ValueError("ownership source image mismatch")
                sources = manifest["owned_source_sha256"]
                if source_baseline is None:
                    source_baseline = sources
                changed = {key for key in set(sources) | set(source_baseline)
                           if sources.get(key) != source_baseline.get(key)}
                permitted = {"tests/zephyr/m33_profile_hil/src/main.cpp"} if name == "native004" and role == "client" else set()
                if changed != permitted:
                    raise ValueError("ownership source continuity mismatch")
                source_latest[role] = evidence["boards"][role]["image_sha256"]
                elf_latest[role] = manifest["artifacts"]["elf"]["sha256"]
            if name in ("native003", "native005", "native006", "native008"):
                for role in ("server", "client"):
                    if not any(line.startswith(role + ": ") and "|security_event=8|" in line
                               for line in transcript.decode("ascii").splitlines()):
                        raise ValueError("native new bond creation missing")
            if name in ("native007", "native009"):
                for role in ("server", "client"):
                    if not any(line.startswith(role + ": ") and "|security_event=10|" in line
                               for line in transcript.decode("ascii").splitlines()):
                        raise ValueError("native bond restoration missing")
        checked[name] = step["evidence"]["sha256"]
    return {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "steps": checked,
            "base_cleanup_boards": cleanup_boards, "latest_images": source_latest,
            "latest_elf": elf_latest, "latest_nonce": evidence["cleanup"]["server"]["nonce"]}


def audit_live_chain(boards: dict, chain: dict, live_images: list) -> dict:
    """! @brief 이전 native image와 STOP RAM을 쓰기 없이 읽어 chain의 현재 끝점을 확인합니다. """
    from pyocd.core.helpers import ConnectHelper
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tools/bluetooth"))
    from m33_diagnostics import inspect_hex
    if len(live_images) != 2 or {item[0] for item in live_images} != {"server", "client"}:
        raise ValueError("chain requires exact two live HEX/ELF references")
    nm = Path("C:/ncs/toolchains/dcbdc366a1/opt/zephyr-sdk/gnu/arm-zephyr-eabi/bin/arm-zephyr-eabi-nm.exe")
    result = {}
    for role, image_name, elf_name in live_images:
        elf = Path(elf_name)
        if hashlib.sha256(elf.read_bytes()).hexdigest() != chain["latest_elf"][role]:
            raise ValueError("chain live ELF hash")
        image = inspect_hex(Path(image_name), chain["latest_images"][role], None)
        symbols = subprocess.run([str(nm), "-S", "-C", str(elf)], capture_output=True, text=True, check=True).stdout
        expected = {"nonce": (chain["latest_nonce"] + "\0").encode("ascii"),
                    "cleanup_complete": b"\1", "stop_reported": b"\1",
                    "cleanup_expired": b"\0", "watchdog_channel": b"\xff" * 4}
        locations = {}
        for name, value in expected.items():
            match = re.search(r"^([0-9a-f]+) ([0-9a-f]+) [a-zA-Z] \(anonymous namespace\)::" + name + r"$", symbols, re.MULTILINE)
            if match is None or int(match[2], 16) != len(value):
                raise ValueError("chain live RAM symbol mismatch")
            locations[name] = int(match[1], 16)
        session = ConnectHelper.session_with_chosen_probe(unique_id=boards[role]["uid"], target_override="nrf54l", frequency=500000,
            options={"connect_mode": "attach", "auto_unlock": False, "resume_on_disconnect": False,
                     "cmsis_dap.limit_packets": True, "cmsis_dap.prefer_v1": False})
        if session is None:
            raise ValueError("chain read-only attach unavailable")
        ranges = []
        with session:
            for start, value in image["ranges"]:
                actual = bytes(session.target.read_memory_block8(start, len(value)))
                if actual != value:
                    raise ValueError("chain live load range mismatch")
                ranges.append({"start": start, "length": len(value), "sha256": hashlib.sha256(actual).hexdigest()})
            for name, value in expected.items():
                if bytes(session.target.read_memory_block8(locations[name], len(value))) != value:
                    raise ValueError("chain live STOP RAM mismatch")
        result[role] = {"ranges": ranges, "ram": {name: {"address": locations[name], "sha256": hashlib.sha256(value).hexdigest()}
                                                    for name, value in expected.items()}}
    return result


def execute(args: argparse.Namespace) -> dict:
    """! @brief radio 시작 없이 exact 소유 peer를 삭제하고 기존 목록과 STOP을 검증합니다. """
    attempt = json.loads(args.attempt.read_text(encoding="utf-8"))
    chain = None
    if args.ownership_chain is not None:
        chain = validate_ownership_chain(args.ownership_chain, attempt)
        document = json.loads(args.ownership_chain.read_text(encoding="utf-8"))
        if document["original_attempt_sha256"] != hashlib.sha256(args.attempt.read_bytes()).hexdigest():
            raise ValueError("ownership original attempt hash")
    output = args.output_prefix.with_suffix(".json")
    transcript_path = args.output_prefix.with_suffix(".transcript.log")
    if output.exists() or transcript_path.exists():
        raise ValueError("existing cleanup evidence must not be overwritten")
    if len(args.role) != 2 or {entry[0] for entry in args.role} != {"server", "client"}:
        raise ValueError("exact two owned roles required")
    serial, port_list = import_pyserial()
    boards = {}
    for role, private_name, public_name, image_name in args.role:
        private_path, public_path, image = map(Path, (private_name, public_name, image_name))
        private = json.loads(private_path.read_text(encoding="utf-8"))
        public = json.loads(public_path.read_text(encoding="utf-8"))
        command = validate_proof(attempt, role, private, public)
        cleanup_nonce = private["nonce"]
        if chain is not None:
            cleanup_nonce = chain["latest_nonce"]
            command = command.replace(("|nonce=" + private["nonce"]).encode("ascii"),
                                      ("|nonce=" + cleanup_nonce).encode("ascii"), 1)
            scoped = chain["base_cleanup_boards"][role]
            for key in ("before_sha256", "peer_sha256"):
                if scoped[key] != public[key]:
                    raise ValueError("chain original scoped peer/list mismatch")
            if scoped["proof_sha256"] != hashlib.sha256(public_path.read_bytes()).hexdigest():
                raise ValueError("chain original RAM proof mismatch")
        if not image.is_file() or image.suffix != ".hex":
            raise ValueError("exact cleanup image required")
        uid, _, port = discover(private["probe_sha256"], port_list)
        boards[role] = {"uid": uid, "port": port, "command": command, "image": image,
                        "nonce": cleanup_nonce, "probe_sha256": private["probe_sha256"],
                        "image_sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
                        "proof_sha256": hashlib.sha256(public_path.read_bytes()).hexdigest(),
                        "before_sha256": public["before_sha256"], "peer_sha256": public["peer_sha256"]}
    if len({entry["uid"] for entry in boards.values()}) != 2 or len({entry["nonce"] for entry in boards.values()}) != 1:
        raise ValueError("pair ownership mismatch")
    if not args.execute:
        return {"status": "NOT_RUN", "reason": "owned pair proof and live mapping verified; no flash/deletion", "ownership_chain": chain}
    lines, results, reason = [], {}, None
    with ProbeLocks([entry["uid"] for entry in boards.values()]):
        if chain is not None:
            try:
                chain["live_audit"] = audit_live_chain(boards, chain, args.live_image or [])
            except (ValueError, OSError, KeyError) as error:
                return {"status": "NOT_RUN", "reason": str(error), "ownership_chain": chain}
        for role, board in boards.items():
            try:
                flash_image_pyocd(role, board["uid"], board["image"], 120.0,
                                 hardware_reset=True, preserve_nrf54l_access=True)
                time.sleep(1)
                with serial.Serial(board["port"], 115200, timeout=0.1) as port:
                    port.write(b"M33PROFILE|1|PROBE\n")
                    ready, cleaned, stopped, sent = False, False, False, False
                    deadline = time.monotonic() + 20.0
                    try:
                        while time.monotonic() < deadline and not stopped:
                            line = port.readline().decode("ascii", errors="replace").strip()
                            if not line.startswith("M33PROFILE|1|"):
                                continue
                            lines.append(role + ": " + line)
                            value = fields(line)
                            kind = line.split("|")[2]
                            if value.get("role") != role or value.get("core") != attempt["revisions"]["core"]:
                                raise ValueError("cleanup image identity mismatch")
                            if kind == "READY" and not ready:
                                ready = True
                                port.write(board["command"])
                                sent = True
                                continue
                            if value.get("nonce") != board["nonce"] or kind in ("FAIL", "BEGIN", "END"):
                                raise ValueError("cleanup failure/nonce/unexpected radio start")
                            if kind == "CLEANED":
                                if cleaned or value.get("removed") != "1" or value.get("existing_unchanged") != "1":
                                    raise ValueError("scoped cleanup denominator")
                                cleaned = True
                            stopped = validate_stop_record(kind, value, board["nonce"], stopped)
                        if not (ready and sent and cleaned and stopped):
                            raise ValueError("cleanup completion missing")
                    finally:
                        if not stopped:
                            port.write(f"M33PROFILE|1|STOP|nonce={board['nonce']}\n".encode())
                            deadline = time.monotonic() + 15.0
                            while time.monotonic() < deadline and not stopped:
                                line = port.readline().decode("ascii", errors="replace").strip()
                                if not line.startswith("M33PROFILE|1|"):
                                    continue
                                lines.append(role + ": " + line)
                                value = fields(line)
                                if ("|STOPPED|" in line and value.get("role") == role
                                        and value.get("core") == attempt["revisions"]["core"]):
                                    stopped = validate_stop_record("STOPPED", value, board["nonce"], False)
                            if not stopped:
                                raise ValueError("cleanup STOP not confirmed; do not run another HIL")
                    results[role] = {"removed": 1, "existing_unchanged": True, "stopped": True}
            except Exception as error:
                reason = f"{role}: {error}"
                break
    raw = ("\n".join(lines) + "\n").encode("ascii")
    evidence = {"schema": "nucode-m33-profile-owned-bond-cleanup-v1", "status": "FAIL" if reason else "PASS",
                "ownership_chain": chain,
                "reason": reason, "attempt_sha256": hashlib.sha256(args.attempt.read_bytes()).hexdigest(),
                "revisions": attempt["revisions"], "observed_utc": datetime.now(timezone.utc).isoformat(),
                "results": results, "transcript_sha256": hashlib.sha256(raw).hexdigest(),
                "boards": {role: {key: value for key, value in board.items() if key.endswith("sha256") or key == "nonce"}
                           for role, board in boards.items()}}
    output.parent.mkdir(parents=True, exist_ok=True)
    with transcript_path.open("xb") as stream:
        stream.write(raw)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(evidence, stream, indent=2)
    return evidence


def main() -> int:
    """! @brief 기본은 비파괴 preflight이며 명시 실행만 pair cleanup을 수행합니다. """
    parser = argparse.ArgumentParser()
    parser.add_argument("--attempt", type=Path, required=True)
    parser.add_argument("--role", nargs=4, action="append", required=True, metavar=("ROLE", "PRIVATE_PROOF", "PUBLIC_PROOF", "HEX"))
    parser.add_argument("--output-prefix", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--ownership-chain", type=Path)
    parser.add_argument("--live-image", nargs=3, action="append", metavar=("ROLE", "HEX", "ELF"))
    try:
        result = execute(parser.parse_args())
    except (ValueError, OSError, KeyError) as error:
        print("owned bond cleanup FAIL: " + str(error))
        return 1
    print(json.dumps(result, sort_keys=True))
    return int(result["status"] == "FAIL")


if __name__ == "__main__":
    raise SystemExit(main())
