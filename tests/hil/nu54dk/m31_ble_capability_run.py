#!/usr/bin/env python3
"""! @brief 익명화된 probe identity로 M31 capability image를 sector flash·검증합니다. """

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import string
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
)
from m6_serial_echo import (  # noqa: E402
    DAPLINK_TARGET,
    detail_value,
    find_serial_port,
    import_pyserial,
    read_details,
)
from m31_ble_capability import (  # noqa: E402
    ExpectedIdentity,
    validate_evidence_envelope,
)
from v04_protocol import ProbeLocks  # noqa: E402


class ExecutionFailure(RuntimeError):
    """! @brief flash·serial·mapping·증거 단계의 제한된 실패를 나타냅니다. """


def sha256_bytes(payload: bytes) -> str:
    """! @brief probe 원문 대신 artifact byte의 SHA-256을 계산합니다. """
    return hashlib.sha256(payload).hexdigest()


def discover(probe_sha256: str, list_ports: object) -> tuple[str, str, str]:
    """! @brief SHA-256 identity 하나에 정확히 하나의 MSD와 VCOM을 결합합니다. """
    if len(probe_sha256) != 64 or any(character not in "0123456789abcdef" for character in probe_sha256):
        raise ExecutionFailure("--probe-sha256은 소문자 SHA-256이어야 합니다")
    candidates = []
    for letter in string.ascii_uppercase:
        volume = Path(f"{letter}:/")
        details = read_details(volume)
        if details is None or detail_value(details, "Target Detect") != DAPLINK_TARGET:
            continue
        raw_uid = detail_value(details, "Unique ID")
        if not raw_uid:
            continue
        if sha256_bytes(raw_uid.lower().encode("ascii")) == probe_sha256:
            port = find_serial_port(raw_uid.lower(), "auto", list_ports)
            candidates.append((raw_uid.lower(), volume.as_posix(), port))
    if len(candidates) != 1:
        raise ExecutionFailure(f"probe SHA-256 mapping count={len(candidates)}")
    return candidates[0]


def _read_line(port: object, deadline: float) -> bytes:
    """! @brief CRLF까지 bounded UART byte만 반환합니다. """
    captured = bytearray()
    while time.monotonic() < deadline:
        incoming = port.read(1)
        if not incoming:
            continue
        captured.extend(incoming)
        if len(captured) > 1024:
            raise ExecutionFailure("UART line size limit")
        if incoming == b"\n":
            return bytes(captured)
    raise ExecutionFailure("UART line timeout")


def collect_register_identity(raw_uid: str, volume: str) -> dict[str, str]:
    """! @brief CMSIS-DAP V2의 정상 DP/AP 초기화 뒤 비파괴 레지스터만 읽습니다. """
    details = read_details(Path(volume))
    if details is None or detail_value(details, "Target Detect") != DAPLINK_TARGET:
        raise ExecutionFailure("DAPLink target identity 불일치")
    command = [
        sys.executable, "-I", "-m", "pyocd", "commander", "--uid", raw_uid,
        "--target", "nrf54l", "--frequency", "500000", "--connect", "under-reset",
        "-O", "cmsis_dap.limit_packets=true", "-O", "cmsis_dap.prefer_v1=false",
        "-O", "auto_unlock=false",
    ]
    read_commands = (
        "readdp 0x0\nreaddp 0x24\nreadap 0 0xfc\nreadap 0 0x00\n"
        "readap 2 0xfc\nreadap 2 0x14\nexit\n"
    )
    result = subprocess.run(command, input=read_commands, text=True,
                            capture_output=True, timeout=30, check=False)
    if result.returncode != 0:
        raise ExecutionFailure("CMSIS-DAP V2 DP/AP register query failure")
    output = result.stdout + "\n" + result.stderr
    patterns = {
        "dp_idcode": r"DP register 0x0 = 0x([0-9a-fA-F]{8})",
        "dp_targetid_observed": r"DP register 0x24 = 0x([0-9a-fA-F]{8})",
        "ahb_ap_idr": r"AP register 0xfc = 0x([0-9a-fA-F]{8})",
        "ahb_ap_csw": r"AP register 0x0 = 0x([0-9a-fA-F]{8})",
        "ctrl_ap_idr": r"AP register 0x20000fc = 0x([0-9a-fA-F]{8})",
        "approtect_status": r"AP register 0x2000014 = 0x([0-9a-fA-F]{8})",
    }
    values = {}
    for name, pattern in patterns.items():
        matched = re.search(pattern, output)
        if matched is None:
            raise ExecutionFailure(f"CMSIS-DAP V2 register record missing: {name}")
        values[name] = int(matched.group(1), 16)
    if values["dp_idcode"] != 0x6BA02477 or values["ahb_ap_idr"] != 0x84770001 or (
        values["ctrl_ap_idr"] != 0x32880000 or
        values["ahb_ap_csw"] & 0x40 == 0 or values["approtect_status"] != 0
    ):
        raise ExecutionFailure("Nordic DP/AP identity 또는 보호 상태 불일치")
    return {name: f"0x{value:08x}" for name, value in values.items()}


def collect_transcript(port: object, nonce: str, timeout_seconds: float) -> bytes:
    """! @brief 재시도 폭주 없이 PROBE→START→END를 한 번 수행합니다. """
    deadline = time.monotonic() + timeout_seconds
    port.reset_input_buffer()
    port.write(b"M31CAP|1|PROBE\n")
    port.flush()
    ready = None
    while time.monotonic() < deadline:
        line = _read_line(port, deadline)
        if b"M31CAP|1|FAIL" in line:
            raise ExecutionFailure("target capability PROBE FAIL")
        if line.rstrip(b"\r\n") == b"M31CAP|1|READY":
            ready = line
            break
    if ready is None:
        raise ExecutionFailure("target capability READY timeout")
    port.write(f"M31CAP|1|START|nonce={nonce}\n".encode("ascii"))
    port.flush()
    lines = [ready]
    for _index in range(11):
        line = _read_line(port, deadline)
        if b"M31CAP|1|FAIL" in line:
            raise ExecutionFailure("target capability START/HCI FAIL")
        lines.append(line)
        if line.startswith(b"M31CAP|1|END|"):
            break
    if len(lines) != 12 or not lines[-1].startswith(b"M31CAP|1|END|"):
        raise ExecutionFailure("target capability incomplete transcript")
    return b"".join(lines)


def execute(args: argparse.Namespace) -> dict:
    """! @brief identity·AP register·sector flash·UART oracle를 같은 attempt에 묶습니다. """
    image = args.hex.resolve()
    if not image.is_file() or image.suffix.lower() != ".hex":
        raise ExecutionFailure("유효한 target Intel HEX가 없습니다")
    lock = json.loads((REPOSITORY / "tools/ci/ncs-3.4.0.lock.json").read_text(encoding="utf-8"))
    ncs_root = args.sdk_root.resolve()
    identity = ExpectedIdentity(
        git_revision(REPOSITORY), git_revision(BOARD_ROOT),
        git_revision(ncs_root / "nrf"), git_revision(ncs_root / "zephyr"),
    )
    if identity.board != lock["board"]["revision"] or identity.ncs != lock["ncs"]["revision"] or (
        identity.zephyr != lock["zephyr"]["revision"]
    ):
        raise ExecutionFailure("source/board/SDK lock revision mismatch")
    dirty = subprocess.run(
        ["git", "-C", str(REPOSITORY), "status", "--porcelain=v1", "--untracked-files=all"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    if dirty and not args.development:
        raise ExecutionFailure("exact source HIL에는 clean commit이 필요합니다")
    serial_module, list_ports = import_pyserial()
    raw_uid, volume, vcom = discover(args.probe_sha256, list_ports)
    image_hash = sha256_bytes(image.read_bytes())
    nonce = hashlib.sha256(f"{time.time_ns()}:{image_hash}".encode("ascii")).hexdigest()[:32]
    output = args.output_prefix.resolve()
    if output.with_suffix(".json").exists() or output.with_suffix(".transcript.log").exists():
        raise ExecutionFailure("기존 attempt evidence를 덮어쓰지 않습니다")
    with ProbeLocks([raw_uid]):
        registers = collect_register_identity(raw_uid, volume)
        flash_mode, flash_bytes = flash_image_pyocd("capability", raw_uid, image, 120.0)
        time.sleep(2.0)
        with serial_module.Serial(vcom, 115200, timeout=0.2) as port:
            transcript = collect_transcript(port, nonce, args.timeout_seconds)
    result = validate_evidence_envelope({
        "hex_sha256": image_hash,
        "role": "capability_probe",
        "nonce": nonce,
        "transcript": transcript,
    }, image_hash, identity, args.controller_variant)
    evidence = {
        "test_id": "M31-CAP-01",
        "status": "PASS",
        "scope": f"{args.controller_variant}_hci_capability_query_only",
        "controller_variant": args.controller_variant,
        "source_clean": not bool(dirty),
        "probe_sha256": args.probe_sha256,
        "volume": volume,
        "vcom": vcom,
        "role": "capability_probe",
        "identity": vars(identity),
        "image_sha256": image_hash,
        "transcript_sha256": sha256_bytes(transcript),
        "controller_bits": result.controller_bits,
        "host_config": result.host_config,
        "raw_le_features_hex": result.feature_bytes.hex(),
        "probe_registers": registers,
        "flash_mode": flash_mode,
        "flash_bytes": flash_bytes,
        "nonce": nonce,
        "observed_utc": datetime.now(timezone.utc).isoformat(),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.with_suffix(".transcript.log").write_bytes(transcript)
    output.with_suffix(".json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    return evidence


def main() -> int:
    """! @brief raw UID를 명령 인자로 요구하지 않는 단일 probe 실행 CLI입니다. """
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe-sha256", required=True)
    parser.add_argument("--sdk-root", type=Path, required=True)
    parser.add_argument("--hex", type=Path, required=True)
    parser.add_argument("--output-prefix", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=float, default=60.0)
    parser.add_argument("--controller-variant", choices=("default_sdc", "zephyr_ll_candidate"),
                        default="default_sdc")
    parser.add_argument("--development", action="store_true",
                        help="미커밋 source의 탐색 시도를 기록하며 완료 증거로 사용하지 않습니다")
    args = parser.parse_args()
    try:
        evidence = execute(args)
    except BaseException as error:
        message = re.sub(r"(?i)\b[0-9a-f]{16,64}\b", "<redacted-identity>", str(error))
        message = re.sub(r"(?i)(?:uid|probe_id)=[^\s,;]+", "uid=<redacted>", message)
        print(f"M31_CAP_HIL_FAIL: {type(error).__name__}: {message[:500]}", file=sys.stderr)
        return 1
    print("M31_CAP_HIL_PASS=1;SCOPE=HCI_QUERY;SOURCE_CLEAN=" + str(evidence["source_clean"]).lower())
    return 0


if __name__ == "__main__":
    sys.exit(main())
