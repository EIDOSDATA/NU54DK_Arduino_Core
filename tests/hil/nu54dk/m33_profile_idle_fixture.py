#!/usr/bin/env python3
"""! @brief native HIL의 미시작 watcher를 W04용 exact idle 증거로 내보냅니다. """
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys

from m32_ble_capability_run import discover
from m6_serial_echo import import_pyserial
from m33_profile_run import fields, validate_stop_record
from v04_protocol import ProbeLocks

ROOT = Path(__file__).resolve().parents[3]


def audit_idle_ram(target, symbols: dict, nonce: str) -> list[dict]:
    """! @brief 미시작·정리 완료 RAM을 두 번 읽어 현재 수명 상태를 증명합니다. """
    expected = {"nonce": (nonce + "\0").encode("ascii"), "started": b"\0", "cleanup_complete": b"\1",
                "stop_reported": b"\1", "failed": b"\0", "watchdog_channel": b"\xff" * 4}
    if set(symbols) != set(expected):
        raise ValueError("watcher lifecycle symbols incomplete")
    result = []
    for name, value in expected.items():
        symbol = symbols[name]
        if symbol["size"] != len(value):
            raise ValueError("watcher lifecycle symbol size mismatch")
        for _ in range(2):
            if bytes(target.read_memory_block8(symbol["address"], len(value))) != value:
                raise ValueError("watcher live lifecycle mismatch: " + name)
        result.append({"name": name, **symbol, "sha256": hashlib.sha256(value).hexdigest(),
                       "stable_reads": 2, "status": "PASS"})
    return result


def export(args: argparse.Namespace) -> dict:
    """! @brief STOP 이후 halt/reset/resume 없이 모든 HEX load byte를 읽어 대조합니다. """
    from pyocd.core.helpers import ConnectHelper
    sys.path.insert(0, str(ROOT / "tools/bluetooth"))
    from m33_diagnostics import inspect_hex, load_watcher_fixture, watcher_symbols
    evidence = json.loads(args.evidence.read_text(encoding="utf-8"))
    build = json.loads(args.build_record.read_text(encoding="utf-8"))
    if (evidence.get("family") != "native" or evidence.get("status") not in ("PASS", "DEVELOPMENT_PASS")
            or build.get("family") != "standard" or build.get("role") != "watcher"):
        raise ValueError("successful native HIL and exact standard watcher build required")
    cleanup = evidence["cleanup"]["watcher"]
    nonce = cleanup["nonce"]
    validate_stop_record("STOPPED", cleanup, nonce, False)
    source_hashes = build["owned_source_sha256"]
    for name, expected in source_hashes.items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
            raise ValueError("source changed after build: " + name)
    transcript = args.evidence.with_suffix(".transcript.log")
    if hashlib.sha256(transcript.read_bytes()).hexdigest() != evidence["transcript_sha256"]:
        raise ValueError("transcript hash mismatch")
    watcher_lines = [line.split(": ", 1)[1] for line in transcript.read_text().splitlines() if line.startswith("watcher: ")]
    kinds = [line.split("|")[2] for line in watcher_lines]
    if (kinds.count("READY") != 1 or kinds.count("STOPPED") != 1 or kinds.index("READY") > kinds.index("STOPPED")
            or any(kind in ("START", "BEGIN", "FAIL") for kind in kinds)):
        raise ValueError("watcher is not a never-started clean fixture")
    for line in watcher_lines:
        if fields(line).get("core") != evidence["revisions"]["core"]:
            raise ValueError("watcher source revision mismatch")
    sources = {"evidence": args.evidence, "transcript": transcript, "image": Path(build["image"]),
               **{key: Path(build["artifacts"][key]["path"]) for key in ("elf", "config", "sysbuild")}}
    if (hashlib.sha256(sources["image"].read_bytes()).hexdigest() != evidence["boards"]["watcher"]["image_sha256"]
            or "SB_CONFIG_FLPRCORE_NONE=y" not in sources["sysbuild"].read_text()):
        raise ValueError("watcher image/sysbuild mismatch")
    for key in ("elf", "config", "sysbuild"):
        if hashlib.sha256(sources[key].read_bytes()).hexdigest() != build["artifacts"][key]["sha256"]:
            raise ValueError("build artifact changed: " + key)
    output = args.output.resolve()
    if output.exists() or output.parent.exists():
        raise ValueError("new isolated fixture directory required")
    _, port_list = import_pyserial()
    digest = evidence["boards"]["watcher"]["probe_sha256"]
    uid, _, port = discover(digest, port_list)
    image = inspect_hex(sources["image"], evidence["boards"]["watcher"]["image_sha256"], None)
    symbols = watcher_symbols(sources["elf"].read_bytes())
    ranges, readback = [], []
    with ProbeLocks([uid]):
        session = ConnectHelper.session_with_chosen_probe(unique_id=uid, target_override="nrf54l", frequency=500000,
            options={"connect_mode": "attach", "auto_unlock": False, "resume_on_disconnect": False,
                     "cmsis_dap.limit_packets": True, "cmsis_dap.prefer_v1": False})
        if session is None:
            raise ValueError("watcher read-only attach unavailable")
        with session:
            for start, expected in image["ranges"]:
                observed = bytes(session.target.read_memory_block8(start, len(expected)))
                expected_hash = hashlib.sha256(expected).hexdigest()
                observed_hash = hashlib.sha256(observed).hexdigest()
                if expected_hash != observed_hash:
                    raise ValueError("live HEX load-range mismatch")
                ranges.append({"start": start, "length": len(expected), "sha256": expected_hash})
                readback.append({"start": start, "length": len(expected), "expected_sha256": expected_hash,
                                 "observed_sha256": observed_hash})
            lifecycle_ram = audit_idle_ram(session.target, symbols, nonce)
    output.parent.mkdir(parents=True)
    files = {}
    for key, source in sources.items():
        name = {"evidence": "evidence.json", "transcript": "transcript.log", "image": "image.hex",
                "elf": "image.elf", "config": "config.txt", "sysbuild": "sysbuild.txt"}[key]
        target = output.parent / name
        shutil.copy2(source, target)
        files[key] = {"path": name, "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}
    fixture = {"schema": "nucode-m33-w04-third-idle-v1", "role": "standard-watcher",
               "probe_sha256": digest, "port": port, "revisions": evidence["revisions"], "nonce": nonce,
               "files": files, "source_files": source_hashes, "load_ranges": ranges,
               "readback": readback, "lifecycle_ram": lifecycle_ram,
               "build_defines": {"M33_PROFILE_FAMILY": "standard", "M33_PROFILE_ROLE": "watcher"},
               "after_stopped_actions": ["uart_close", "read_only_audit"],
               "observed_utc": datetime.now(timezone.utc).isoformat(),
               "action_chain": ["sector_program", "software_reset", "READY", "STOP", "STOPPED", "uart_close", "read_only_audit"]}
    with output.open("x", encoding="utf-8") as stream:
        json.dump(fixture, stream, indent=2)
    fixture_hash = hashlib.sha256(output.read_bytes()).hexdigest()
    load_watcher_fixture(output, fixture_hash, digest)
    return {"status": "PASS", "fixture": str(output), "fixture_sha256": fixture_hash,
            "probe_sha256": digest, "load_ranges": len(ranges)}


def main() -> int:
    """! @brief exact 완료 증거와 build record를 받아 독립 idle fixture를 만듭니다. """
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--build-record", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    try:
        result = export(parser.parse_args())
    except (ValueError, OSError, KeyError) as error:
        print("idle fixture FAIL: " + str(error))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
