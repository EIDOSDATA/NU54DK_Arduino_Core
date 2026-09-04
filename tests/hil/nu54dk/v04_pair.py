#!/usr/bin/env python3
"""Exact two-board SWD mailbox runner. This revision only drives onboard tests."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import datetime as dt
import hashlib
import json
from pathlib import Path
import secrets
import struct
import sys
import time

from m24_uarte_onboard import flash_image, git_output, matching_port_names, parse_build_record, sha256_file
from v04_protocol import MAGIC, VERSION, SIZE, ProbeLocks, ProtocolError, decode, encode, validate_pair

ROOT = Path(__file__).resolve().parents[3]
RAM_BEGIN, RAM_END = 0x20000000, 0x20040000


def inspect_image(repository: Path, build_root: Path, role: int) -> dict:
    from elftools.elf.elffile import ELFFile
    commit = git_output(repository, "rev-parse", "HEAD")
    if git_output(repository, "status", "--porcelain"):
        raise ProtocolError("exact clean checkout required before flashing")
    board = git_output(repository, "rev-parse", "HEAD:board_package/NU54DK_Zephyr_DTS")
    actual_board = git_output(repository / "board_package/NU54DK_Zephyr_DTS", "rev-parse", "HEAD")
    if board != actual_board:
        raise ProtocolError("board gitlink mismatch")
    scenario = f"nucode.v04.pair_{'dut' if role == 1 else 'peer'}"
    candidates = list(build_root.glob(f"**/{scenario}/v04_pair_hil/zephyr/zephyr.hex"))
    if len(candidates) != 1:
        raise ProtocolError(f"exactly one image required for {scenario}, found {len(candidates)}")
    image = candidates[0].resolve()
    elf = image.with_suffix(".elf")
    record_path = image.parent.parent / "nucode_arduino_core_build.yml"
    record = parse_build_record(record_path)
    expected = {"core_revision": commit[:12], "board_revision": board[:12], "board": "nrf54l15dk", "board_qualifiers": "nrf54l15/cpuapp/nu54dk"}
    if any(record.get(key) != value for key, value in expected.items()):
        raise ProtocolError(f"stale or foreign build record: {scenario}")
    symbols = {}
    with elf.open("rb") as stream:
        symbol_table = ELFFile(stream).get_section_by_name(".symtab")
        if symbol_table is None:
            raise ProtocolError("ELF symbol table missing")
        for name, size in (("v04_request", SIZE), ("v04_response", SIZE), ("v04_identity", 64)):
            entries = symbol_table.get_symbol_by_name(name) or []
            if len(entries) != 1:
                raise ProtocolError(f"missing/ambiguous mailbox symbol {name}")
            address = int(entries[0]["st_value"])
            if int(entries[0]["st_size"]) != size or address % 4 or not RAM_BEGIN <= address <= RAM_END - size:
                raise ProtocolError(f"mailbox symbol outside expected SRAM: {name}")
            symbols[name] = address
    spans = sorted((symbols[name], symbols[name] + (64 if name == "v04_identity" else SIZE)) for name in symbols)
    if any(a[1] > b[0] for a, b in zip(spans, spans[1:])):
        raise ProtocolError("mailbox symbols overlap")
    return {"path": image, "elf": elf, "sha256": sha256_file(image), "elf_sha256": sha256_file(elf),
            "record_sha256": sha256_file(record_path), "core_revision": commit, "board_revision": board,
            "role": role, "symbols": symbols}


def verify_identity(raw: bytes, role: int, commit: str) -> None:
    if len(raw) != 64 or struct.unpack("<3I", raw[:12]) != (MAGIC, VERSION, role):
        raise ProtocolError("unexpected runtime role/protocol identity")
    if raw[16:56] != commit.encode("ascii"):
        raise ProtocolError("runtime firmware commit mismatch")


class Device:
    def __init__(self, target, image: dict, nonce: bytes):
        self.target, self.image, self.nonce = target, image, nonce
        self.sequence = 0
        self.poisoned = False

    def command(self, opcode: int, values=(), timeout: float = 10) -> list[int]:
        if self.poisoned or not 0 < timeout <= 60:
            raise ProtocolError("session is poisoned or timeout invalid; reflash/restart required")
        self.sequence += 1
        role = self.image["role"]
        packet = encode(self.nonce, self.sequence, role, opcode, values)
        request, response = self.image["symbols"]["v04_request"], self.image["symbols"]["v04_response"]
        try:
            # Request commit marker is written last; firmware response does likewise.
            self.target.write32(response, 0)
            self.target.write32(request, 0)
            self.target.write_memory_block8(request + 4, packet[4:])
            self.target.flush()
            self.target.write32(request, MAGIC)
            self.target.flush()
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                marker = self.target.read32(response)
                if marker:
                    raw = bytes(self.target.read_memory_block8(response, SIZE))
                    status, output = decode(raw, self.nonce, self.sequence, role, opcode)
                    if status:
                        raise ProtocolError(f"firmware failure role={role} op={opcode} seq={self.sequence} status={status} result={output}")
                    return output
                time.sleep(0.005)
            raise ProtocolError(f"mailbox timeout role={role} op={opcode} seq={self.sequence}")
        except BaseException:
            self.poisoned = True
            raise


def signed(word: int) -> int:
    return word - (1 << 32) if word & (1 << 31) else word


def run_onboard(device: Device, rounds: int, append) -> None:
    challenge = list(struct.unpack("<4I", secrets.token_bytes(16)))
    reply = device.command(1, challenge)
    if reply != [value ^ (0xA5000000 | device.image["role"]) for value in challenge]:
        raise ProtocolError("independent ping oracle failed")
    append("V04-PAIR-PING", {"challenge": challenge, "response": reply})
    for instance in (20, 21, 22):
        for rate in (400000, 100000):
            reply = device.command(2, (instance, rounds, rate))
            if reply != [rounds, 0x41, 0, 0]:
                raise ProtocolError(f"PMIC oracle failed: {reply}")
            append(f"V04-PMIC-READ/twim{instance}/{rate}", {"rounds": rounds, "result": reply})
    for instance in (0, 10, 20, 21, 22, 23, 24):
        channels = 8 if instance == 10 else 6
        for channel in range(channels):
            reply = device.command(3, (instance, channel, 10000))
            if len(reply) != 3 or not 9500 <= reply[0] <= 10500 or reply[1:] != [0, 0]:
                raise ProtocolError(f"timer capture oracle failed: {reply}")
            append(f"V04-EVENT/timer{instance:02}/capture{channel}", {"result": reply, "requested_us": 10000})
    for samples in (1, 32):
        for input_code in (0x80, 0x82):
            for round_number in range(rounds):
                reply = device.command(4, (input_code, samples))
                if len(reply) != 5 or reply[:3] != [samples, 0, 1]:
                    raise ProtocolError(f"ADC lifecycle oracle failed: {reply}")
                low, high = signed(reply[3]), signed(reply[4])
                # gain=1/4, internal 0.9 V => 3.6 V full scale. Functional,
                # deliberately broad rail ranges; this is not calibrated voltage QA.
                if not 0 < low <= high <= 4095 or (input_code == 0x80 and not 2500 <= low <= high <= 4000) or (input_code == 0x82 and not 1000 <= low <= high <= 3000):
                    raise ProtocolError(f"ADC internal range oracle failed input={input_code}: {reply}")
                append(f"V04-ADC-INTERNAL/{input_code:02x}/{samples}/{round_number}", {"result": reply})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dut", required=True)
    parser.add_argument("--peer", required=True)
    parser.add_argument("--build-root", type=Path, required=True)
    parser.add_argument("--pyocd", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--rounds", type=int, default=100)
    parser.add_argument("--execute-onboard", action="store_true", help="explicitly authorize flash of both exact role images")
    args = parser.parse_args()
    uids = validate_pair(args.dut, args.peer)
    if not 1 <= args.rounds <= 100 or not args.pyocd.is_file():
        raise ProtocolError("invalid rounds or pyOCD executable")
    images = [inspect_image(ROOT, args.build_root.resolve(), role) for role in (1, 2)]
    from pyocd.core.helpers import ConnectHelper
    from serial.tools import list_ports
    probes = {probe.unique_id.lower() for probe in ConnectHelper.get_all_connected_probes(blocking=False)}
    if not set(uids).issubset(probes):
        raise ProtocolError("both exact probes must be connected; no automatic substitute")
    ports = [matching_port_names(list_ports.comports(), uid) for uid in uids]
    if set(ports[0]) & set(ports[1]):
        raise ProtocolError("DUT/peer COM sets overlap")
    evidence = {"schema_version": 1, "type": "v04-pair-onboard", "status": "preflight", "core_revision": images[0]["core_revision"],
                "board_revision": images[0]["board_revision"], "rounds": args.rounds, "external_wiring_executed": False,
                "plan_sha256": sha256_file(Path(__file__).with_name("v04_test_plan.json")),
                "devices": [{"role": image["role"], "uid_sha256": hashlib.sha256(uid.encode()).hexdigest(), "ports": coms,
                             "hex_sha256": image["sha256"], "elf_sha256": image["elf_sha256"], "record_sha256": image["record_sha256"]}
                            for uid, image, coms in zip(uids, images, ports)], "results": []}
    if not args.execute_onboard:
        print(json.dumps(evidence, ensure_ascii=False, indent=2))
        print("V04_PAIR_PREFLIGHT_ONLY; no flash or board reset performed")
        return 0
    args.evidence.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive create preserves earlier failures/results and prohibits accidental overwrite.
    with args.evidence.open("x", encoding="utf-8") as output:
        output.write(json.dumps({**evidence, "status": "running"}, ensure_ascii=False) + "\n")
    journal = args.evidence.with_suffix(args.evidence.suffix + ".jsonl")
    with journal.open("x", encoding="utf-8") as log:
        try:
            with ProbeLocks(uids), ExitStack() as stack:
                for uid, image in zip(uids, images):
                    if sha256_file(image["path"]) != image["sha256"] or sha256_file(image["elf"]) != image["elf_sha256"]:
                        raise ProtocolError("image changed after preflight")
                    flash = flash_image(args.pyocd, uid, image["path"], 120)
                    session = ConnectHelper.session_with_chosen_probe(unique_id=uid, target_override="nrf54l", frequency=1000000,
                        blocking=False, no_config=True, options={"auto_unlock": False, "connect_mode": "attach", "resume_on_disconnect": False})
                    if session is None:
                        raise ProtocolError("selected probe disappeared after flash")
                    stack.enter_context(session)
                    target = session.target
                    target.reset_and_halt()
                    if target.get_state().name != "HALTED" or target.read32(0xE000ED00) != 0x411FD210:
                        raise ProtocolError("controlled start CPU identity failed")
                    # SRAM survives some reset types. Never accept a prior boot's
                    # ready marker while the new image is still initializing.
                    for address in image["symbols"].values():
                        target.write32(address, 0)
                    target.flush()
                    target.resume()
                    deadline = time.monotonic() + 5
                    while target.read32(image["symbols"]["v04_identity"]) != MAGIC:
                        if time.monotonic() > deadline:
                            raise ProtocolError("firmware boot identity timeout")
                        time.sleep(0.01)
                    verify_identity(bytes(target.read_memory_block8(image["symbols"]["v04_identity"], 64)), image["role"], image["core_revision"])
                    device = Device(target, image, secrets.token_bytes(16))
                    def append(case_id, result, current_role=image["role"]):
                        entry = {"id": case_id, "role": current_role, "status": "passed", **result}
                        evidence["results"].append(entry)
                        log.write(json.dumps(entry) + "\n")
                        log.flush()
                    evidence["devices"][image["role"] - 1]["flash"] = flash
                    run_onboard(device, args.rounds, append)
                    print(f"V04_PAIR_ONBOARD_ROLE_PASS={image['role']}", flush=True)
            evidence["status"] = "passed"
        except BaseException as error:
            evidence["status"] = "interrupted" if isinstance(error, KeyboardInterrupt) else "failed"
            evidence["error"] = str(error)
            raise
        finally:
            evidence["completed_at_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
            args.evidence.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"V04_PAIR_ONBOARD_PASS={len(evidence['results'])}; external HIL remains NOT RUN")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"V04_PAIR_FAIL: {error}", file=sys.stderr)
        raise SystemExit(1) from error
