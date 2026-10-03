#!/usr/bin/env python3
"""! @brief 세 NU54DK에서 M32-W11 유한 GATT soak를 실행합니다. """

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys


HIL = Path(__file__).resolve().parent
REPOSITORY = HIL.parents[2]
APPLICATION_ROOT = REPOSITORY / "tests" / "zephyr" / "m32_regression_soak_hil"
if str(HIL) not in sys.path:
    sys.path.insert(0, str(HIL))

from ble_pair_hil_common import (  # noqa: E402
    BOARD_ROOT,
    BlePairHilFailure,
    RoleEndpoint,
    build_nonce,
    file_sha256,
    git_revision,
    protocol_lines,
    take_exact,
    validate_build_record,
    validate_hex_image,
    validate_image_unchanged,
)
from m6_serial_echo import DaplinkVolume, import_pyserial, read_details  # noqa: E402
from m28_ble_3board import (  # noqa: E402
    ROLES,
    ThreeBoardExecutionFailure,
    execute_three_board,
)
from m32_ble_capability import ExpectedIdentity  # noqa: E402
from m32_ble_capability_run import collect_register_identity, discover  # noqa: E402
from v04_protocol import ProbeLocks  # noqa: E402


TEST_ID = "M32-SOAK-01:primary"
PACKET_DENOMINATOR = 10000
ALLOWED_LOSS = 100
LATENCY_LIMIT_MS = 500
RECOVERY_TIMEOUT_MS = 30000
SOAK_DURATION_SECONDS = 1800


class RegressionSoakFailure(BlePairHilFailure):
    """! @brief W11 mapping·image·protocol·evidence 실패를 나타냅니다. """


def _parse_role(transcript: bytes, nonce: str, role: str) -> dict[str, int | str]:
    """! @brief 한 역할의 10,000 packet·gap·cleanup 결과를 검증합니다. """
    lines = protocol_lines(transcript, "M28B3", nonce)
    ready = f"NUCODE_M28B3_READY:role={role}:test=SOAK".encode("ascii")
    cursor = take_exact(
        lines,
        0,
        ready,
    )
    while cursor < len(lines) and lines[cursor] == ready:
        cursor += 1
    suffix = f":nonce={nonce}".encode("ascii")
    if role in ("peripheral", "mixed"):
        cursor = take_exact(
            lines,
            cursor,
            f"NUCODE_M28B3_{role}:ADVERTISE:PASS:test=SOAK".encode("ascii")
            + suffix,
        )
    expected_tx = PACKET_DENOMINATOR if role in ("mixed", "central") else 0
    expected_rx = PACKET_DENOMINATOR if role in ("peripheral", "mixed") else 0
    cursor = take_exact(
        lines,
        cursor,
        (
            f"NUCODE_M28B3_{role}:TRACE:PASS:test=SOAK:source=rf-gatt"
            f":tx={expected_tx}:rx={expected_rx}"
        ).encode("ascii")
        + suffix,
    )
    if cursor >= len(lines):
        raise RegressionSoakFailure(f"{role} SOAK result 누락")
    link_count = 2 if role == "mixed" else 1
    sequence_field = "sequence_per_link" if role == "mixed" else "sequence"
    pattern = re.compile(
        (
            rf"NUCODE_M28B3_{role}:SOAK:PASS:duration_s={SOAK_DURATION_SECONDS}"
            rf":links={link_count}:{sequence_field}={PACKET_DENOMINATOR}"
            r":loss=0:corrupt=0:duplicate=0:unexpected_disconnect=0"
            r":recovery_failures=0:drops=0:max_gap_ms=([0-9]+)"
            r":cleanup_ms=([0-9]+):cleanup=pass"
            rf":nonce={nonce}"
        ).encode("ascii")
    )
    matched = pattern.fullmatch(lines[cursor])
    if matched is None:
        raise RegressionSoakFailure(f"{role} SOAK result 불일치")
    cursor += 1
    maximum_gap_ms = int(matched.group(1))
    cleanup_ms = int(matched.group(2))
    if maximum_gap_ms > LATENCY_LIMIT_MS or cleanup_ms > RECOVERY_TIMEOUT_MS:
        raise RegressionSoakFailure(f"{role} gap 또는 cleanup 상한 초과")
    if expected_rx != 0 and maximum_gap_ms == 0:
        raise RegressionSoakFailure(f"{role} 수신 gap 관측 누락")
    cursor = take_exact(
        lines,
        cursor,
        f"NUCODE_M28B3_{role}:FINAL:PASS:test=SOAK".encode("ascii") + suffix,
    )
    if cursor != len(lines):
        raise RegressionSoakFailure(f"{role} FINAL 뒤 protocol token 존재")
    return {
        "role": role,
        "transmitted": expected_tx,
        "received": expected_rx,
        "loss": 0,
        "corrupt": 0,
        "duplicate": 0,
        "maximum_gap_ms": maximum_gap_ms,
        "cleanup_ms": cleanup_ms,
        "cleanup": "pass",
    }


def _output_paths(prefix: Path) -> tuple[Path, dict[str, Path]]:
    """! @brief 덮어쓰지 않을 JSON·역할별 transcript 경로를 반환합니다. """
    evidence = prefix.with_suffix(".json")
    transcripts = {
        role: prefix.with_name(f"{prefix.name}.{role}.transcript.log")
        for role in ROLES
    }
    existing = [path for path in (evidence, *transcripts.values()) if path.exists()]
    if existing:
        raise RegressionSoakFailure("기존 W11 soak evidence를 덮어쓰지 않습니다")
    evidence.parent.mkdir(parents=True, exist_ok=True)
    return evidence, transcripts


def _save(
    evidence_path: Path,
    transcript_paths: dict[str, Path],
    evidence: dict,
    transcripts: dict[str, bytes],
    raw_uids: tuple[str, ...],
) -> None:
    """! @brief raw UID를 거부하고 성공·실패 원본을 원자적 순서로 보존합니다. """
    for role, raw in transcripts.items():
        lowered = raw.lower()
        if any(uid.encode("ascii") in lowered for uid in raw_uids):
            raise RegressionSoakFailure("raw probe UID가 transcript에 포함됨")
        transcript_paths[role].write_bytes(raw)
    evidence["transcripts"] = {
        role: {
            "name": transcript_paths[role].name,
            "size": len(transcripts[role]),
            "sha256": hashlib.sha256(transcripts[role]).hexdigest(),
        }
        for role in ROLES
    }
    evidence["observed_utc"] = datetime.now(timezone.utc).isoformat()
    evidence_path.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def execute(args: argparse.Namespace) -> dict:
    """! @brief exact source와 세 V2 probe에서 W11 soak를 한 번 실행합니다. """
    prefix = args.output_prefix.resolve()
    evidence_path, transcript_paths = _output_paths(prefix)
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
        raise RegressionSoakFailure("board/SDK revision lock mismatch")
    dirty = subprocess.run(
        ["git", "-C", str(REPOSITORY), "status", "--porcelain=v1", "--untracked-files=all"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    if dirty and not args.development:
        raise RegressionSoakFailure("exact HIL에는 clean source commit이 필요합니다")

    serial_module, list_ports = import_pyserial()
    endpoints: dict[str, RoleEndpoint] = {}
    public_boards: dict[str, dict] = {}
    raw_uids: list[str] = []
    for role in ROLES:
        digest = getattr(args, f"probe_{role}_sha256")
        uid, volume, vcom = discover(digest, list_ports)
        details = read_details(Path(volume))
        if details is None:
            raise RegressionSoakFailure(f"{role} DAPLink details 누락")
        endpoints[role] = RoleEndpoint(
            uid,
            DaplinkVolume(Path(volume), details),
            vcom,
        )
        public_boards[role] = {
            "probe_sha256": digest,
            "volume": volume,
            "vcom": vcom,
        }
        raw_uids.append(uid)
    if len(set(raw_uids)) != len(ROLES):
        raise RegressionSoakFailure("세 역할이 서로 다른 probe에 매핑되지 않음")

    images = {
        role: validate_hex_image(getattr(args, f"hex_{role}")) for role in ROLES
    }
    image_sizes = {role: images[role].stat().st_size for role in ROLES}
    image_hashes = {role: file_sha256(images[role]) for role in ROLES}
    if len(set(image_hashes.values())) != len(ROLES):
        raise RegressionSoakFailure("세 역할 image가 서로 달라야 합니다")
    build_records = {
        role: validate_build_record(
            images[role], identity.core, identity.board, APPLICATION_ROOT
        )
        for role in ROLES
    }

    nonce = build_nonce()
    transcripts = {role: b"" for role in ROLES}
    results: dict[str, dict[str, int | str]] = {}
    flash_records: dict[str, dict[str, str]] = {}
    status = "FAIL"
    reason: str | None = None
    try:
        with ProbeLocks(raw_uids):
            for role in ROLES:
                public_boards[role]["registers"] = collect_register_identity(
                    endpoints[role].board_id,
                    endpoints[role].volume.root.as_posix(),
                )
            execution = execute_three_board(
                serial_module=serial_module,
                endpoints=endpoints,
                images=images,
                test_name="SOAK",
                nonce=nonce,
                baud_rate=115200,
                flash_timeout=120.0,
                result_timeout=2100.0,
                flash_backend="pyocd-sector",
                hardware_reset=True,
                preserve_nrf54l_access=True,
                ready_replay_settle_seconds=0.25,
            )
        for role in ROLES:
            role_execution = getattr(execution, role)
            transcripts[role] = role_execution.transcript
            validate_image_unchanged(
                images[role], image_sizes[role], image_hashes[role]
            )
            results[role] = _parse_role(role_execution.transcript, nonce, role)
            flash_records[role] = {
                "mode": role_execution.flash_sequence,
                "bytes": role_execution.flash_bytes,
            }
        status = "PASS_CANDIDATE" if dirty else "PASS"
    except Exception as error:
        if isinstance(error, ThreeBoardExecutionFailure):
            transcripts.update(error.transcripts)
        reason = f"{type(error).__name__}: {error}"
        for uid in raw_uids:
            reason = reason.replace(uid, "<redacted-identity>")
        reason = re.sub(r"(?i)(?:uid|probe_id)=[^\s,;]+", "uid=<redacted>", reason)

    evidence = {
        "test_ids": [TEST_ID],
        "status": status,
        "scope": "three_board_bounded_gatt_soak",
        "source_clean": not bool(dirty),
        "identity": asdict(identity),
        "boards": public_boards,
        "images": {
            role: {
                "sha256": image_hashes[role],
                "size": image_sizes[role],
                "build": build_records[role],
                "flash": flash_records.get(role),
            }
            for role in ROLES
        },
        "duration_seconds": SOAK_DURATION_SECONDS,
        "packet_denominator_per_link": PACKET_DENOMINATOR,
        "allowed_loss_packets": ALLOWED_LOSS,
        "observed_loss_packets": 0 if status.startswith("PASS") else None,
        "latency_limit_ms": LATENCY_LIMIT_MS,
        "recovery_timeout_s": RECOVERY_TIMEOUT_MS // 1000,
        "results": results,
        "reason": reason,
        "safety": {
            "cmsis_dap": "v2-only",
            "auto_unlock": False,
            "erase": "sector",
            "reset": "software",
            "automatic_recover": False,
            "mass_erase": False,
        },
    }
    _save(
        evidence_path,
        transcript_paths,
        evidence,
        transcripts,
        tuple(raw_uids),
    )
    return evidence


def main() -> int:
    """! @brief raw UID 없이 W11 soak 인자를 받고 기계 판정을 출력합니다. """
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
        print(
            f"M32_SOAK_HIL_FAIL: {type(error).__name__}: {message[:400]}",
            file=sys.stderr,
        )
        return 1
    print(f"M32_SOAK_HIL_STATUS={result['status']};TEST={TEST_ID}")
    return 0 if result["status"].startswith("PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
