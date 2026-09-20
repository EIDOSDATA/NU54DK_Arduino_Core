"""! @brief NU54DK storage partition을 hash-selected probe로 정확히 지웁니다. """

from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import hashlib
import io
import json
import logging
from pathlib import Path
import re

from pyocd.core.helpers import ConnectHelper
from pyocd.flash.flash import Flash


STORAGE_START = 0x174000
STORAGE_SIZE = 0x9000
STORAGE_RANGE = "0x174000-0x17d000"
TRANSFER_WORDS = 256
PROGRAM_CHUNK_SIZE = 0x1000
HASH_PATTERN = re.compile(r"[0-9a-f]{64}")
IDENTIFIER_PATTERN = re.compile(r"(?i)(?<![0-9a-f])[0-9a-f]{16,}(?![0-9a-f])")


def sha256_file(path: Path) -> str:
    """! @brief 파일 SHA-256을 계산합니다. """
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    """! @brief storage erase 출력과 provenance를 no-overwrite receipt로 남깁니다. """
    parser = argparse.ArgumentParser()
    parser.add_argument("probe_sha256")
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--leave-halted", action="store_true")
    args = parser.parse_args()
    probe_hash = args.probe_sha256.lower()
    receipt = args.receipt.resolve()
    if HASH_PATTERN.fullmatch(probe_hash) is None:
        raise RuntimeError("probe SHA-256 형식이 잘못되었습니다.")
    if receipt.exists():
        raise RuntimeError("기존 receipt를 덮어쓰지 않습니다.")

    logging.disable(logging.CRITICAL)
    hidden_stdout = io.StringIO()
    hidden_stderr = io.StringIO()
    try:
        with redirect_stdout(hidden_stdout), redirect_stderr(hidden_stderr):
            probes = ConnectHelper.get_all_connected_probes(
                blocking=False, print_wait_message=False
            )
            matches = [
                probe.unique_id
                for probe in probes
                if hashlib.sha256(probe.unique_id.encode("utf-8")).hexdigest()
                == probe_hash
            ]
    except Exception as error:
        raise RuntimeError(
            f"probe discovery failed type={type(error).__name__}"
        ) from None
    if len(matches) != 1:
        raise RuntimeError(f"probe hash match count={len(matches)}")
    unique_id = matches[0]
    options = {
        "connect_mode": "under-reset",
        "frequency": 500_000,
        "cmsis_dap.limit_packets": True,
        "cmsis_dap.prefer_v1": False,
        "auto_unlock": False,
        "resume_on_disconnect": False,
    }
    verified_words = 0
    programmed_bytes = 0
    failure_type = ""
    failure_message = ""
    try:
        with redirect_stdout(hidden_stdout), redirect_stderr(hidden_stderr):
            with ConnectHelper.session_with_chosen_probe(
                unique_id=unique_id,
                target_override="nrf54l",
                options=options,
            ) as session:
                target = session.board.target
                target.reset_and_halt()
                region = target.memory_map.get_region_for_address(STORAGE_START)
                flash = region.flash
                flash.init(Flash.Operation.PROGRAM)
                try:
                    for offset in range(0, STORAGE_SIZE, PROGRAM_CHUNK_SIZE):
                        length = min(PROGRAM_CHUNK_SIZE, STORAGE_SIZE - offset)
                        flash.program_page(
                            STORAGE_START + offset, bytes([0xFF]) * length
                        )
                        programmed_bytes += length
                finally:
                    flash.uninit()
                target.halt()
                try:
                    for offset in range(0, STORAGE_SIZE, TRANSFER_WORDS * 4):
                        word_count = min(TRANSFER_WORDS, (STORAGE_SIZE - offset) // 4)
                        values = target.read_memory_block32(
                            STORAGE_START + offset, word_count
                        )
                        if any(value != 0xFFFFFFFF for value in values):
                            raise RuntimeError("storage readback mismatch")
                        verified_words += word_count
                    if not args.leave_halted:
                        target.reset()
                finally:
                    if not args.leave_halted and target.get_state().name == "HALTED":
                        target.resume()
    except Exception as error:
        failure_type = type(error).__name__
        failure_message = str(error).replace(unique_id, "<probe-identifier>")
        failure_message = IDENTIFIER_PATTERN.sub(
            "<device-identifier>", failure_message
        )

    success = failure_type == "" and verified_words * 4 == STORAGE_SIZE
    helper_path = Path(__file__).resolve()
    document = {
        "schema": "nucode.storage-erase-receipt.v2",
        "status": "PASS" if success else "FAIL",
        "probe_sha256": probe_hash,
        "storage_range": STORAGE_RANGE,
        "method": "rram-full-range-ff-program",
        "bytes_programmed": programmed_bytes,
        "bytes_verified": verified_words * 4,
        "readback_all_ff": success,
        "left_halted": args.leave_halted,
        "failure_type": failure_type,
        "failure_message": failure_message,
        "helper_path": str(helper_path),
        "helper_sha256": sha256_file(helper_path),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "raw_probe_identifiers_recorded": False,
        "existing_files_overwritten": False,
    }
    receipt.parent.mkdir(parents=True, exist_ok=True)
    with receipt.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(document, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(
        f"STORAGE_ERASE={document['status']} probe_sha256={probe_hash} "
        f"range={STORAGE_RANGE} receipt={receipt}"
    )
    return 0 if success else 2


if __name__ == "__main__":
    raise SystemExit(main())
