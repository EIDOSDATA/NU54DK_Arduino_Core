#!/usr/bin/env python3
"""Explicit T10-confirmed external fixture runner. Default is preflight only."""
from __future__ import annotations
import argparse
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import sys

import v04_fixture as fixture
import v04_campaign as campaign
import v04_pair as pair
from v04_protocol import ProbeLocks, ProtocolError, validate_pair


def unique_fields(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ProtocolError(f"duplicate confirmation field: {key}")
        result[key] = value
    return result


def arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dut", required=True)
    parser.add_argument("--peer", required=True)
    parser.add_argument("--build-root", type=Path, required=True)
    parser.add_argument("--pyocd", type=Path, required=True)
    parser.add_argument("--fixture", type=int, choices=(101, 102, 103, 201, 202, 203, 301),
                        required=True)
    parser.add_argument("--confirmation", type=Path)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--execute-fixture", action="store_true")
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--duration-seconds", type=float, default=0)
    parser.add_argument("--progress-interval-seconds", type=float, default=5)
    args = parser.parse_args(argv)
    campaign.validate_options(args.repetitions, args.duration_seconds,
                              args.progress_interval_seconds)
    if args.execute_fixture and (args.confirmation is None or args.evidence is None):
        raise ProtocolError("external execution requires explicit T10 confirmation and new evidence path")
    return args


def main(argv=None):
    args = arguments(argv)
    uids = validate_pair(args.dut, args.peer)
    if not args.pyocd.is_file():
        raise ProtocolError("pyOCD executable missing")
    images = [pair.inspect_image(pair.ROOT, args.build_root.resolve(), role) for role in (1, 2)]
    catalog, selected = fixture.fixture_contract(args.fixture)
    evidence = {
        "schema_version": 1, "type": "v04-pair-external-fixture",
        "status": "preflight", "fixture_id": args.fixture, "fixture_revision": catalog["revision"],
        "catalog_sha256": pair.sha256_file(fixture.CATALOG),
        "core_revision": images[0]["core_revision"], "board_revision": images[0]["board_revision"],
        "scope": "uart-async-and-serial-sync-async-single-double-buffer",
        "external_wiring_executed": False,
        "campaign": {"repetitions": args.repetitions,
                     "duration_seconds": args.duration_seconds,
                     "progress_interval_seconds": args.progress_interval_seconds,
                     "interrupted_duration_reused": False},
        "devices": [{"role": image["role"], "uid_sha256": hashlib.sha256(uid.encode()).hexdigest(),
                     "hex_sha256": image["sha256"], "elf_sha256": image["elf_sha256"],
                     "record_sha256": image["record_sha256"]} for uid, image in zip(uids, images)],
        "results": [],
    }
    if not args.execute_fixture:
        print(json.dumps({**evidence, "fixture": selected,
                          "confirmation_template": fixture.confirmation_template(
                              images, uids, args.fixture)}, ensure_ascii=False, indent=2))
        print("V04_FIXTURE_PREFLIGHT_ONLY; no probe access, flash, reset or external output")
        return 0
    confirmation_bytes = args.confirmation.read_bytes()
    confirmation = json.loads(confirmation_bytes, object_pairs_hook=unique_fields)
    fixture.validate_confirmation(confirmation, images, uids, args.fixture)
    evidence["confirmation_sha256"] = hashlib.sha256(confirmation_bytes).hexdigest()
    evidence["confirmed_at_unix"] = confirmation["confirmed_at_unix"]
    # Confirmation validation and exclusive evidence creation both precede USB access.
    with pair.evidence_session(args.evidence, evidence) as journal:
        from pyocd.core.helpers import ConnectHelper
        with ProbeLocks(uids), ExitStack() as stack:
            available = {probe.unique_id.lower() for probe in ConnectHelper.get_all_connected_probes(blocking=False)}
            if not set(uids).issubset(available):
                raise ProtocolError("both confirmed probes required; no automatic substitution")
            devices = []
            for uid, image in zip(uids, images):
                device, flash = pair.boot_exact(stack, ConnectHelper, args.pyocd, uid, image)
                devices.append(device)
                evidence["devices"][image["role"] - 1]["flash"] = flash

            def append(case_id, result):
                entry = {"id": case_id, "status": "passed", **result}
                evidence["results"].append(entry)
                journal.write(json.dumps(entry) + "\n")
                journal.flush()

            # True means execution was attempted, not that wiring was instrumented/verified.
            evidence["external_wiring_executed"] = True
            evidence["campaign"].update(campaign.run_cycles(
                lambda _cycle: fixture.run_confirmed(
                    devices, images, uids, confirmation, args.fixture, append),
                append, args.repetitions, args.duration_seconds,
                args.progress_interval_seconds))
    print("V04_FIXTURE_PASS=uart-async-and-serial-sync-async-single-double-buffer; "
          "forced-error modes remain NOT RUN")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ProtocolError, OSError, ValueError) as error:
        print(f"V04_FIXTURE_FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
