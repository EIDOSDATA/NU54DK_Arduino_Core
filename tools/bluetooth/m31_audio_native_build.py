#!/usr/bin/env python3
"""! @brief 고정 NCS Audio sample을 NU54DK target으로 개별 빌드해 적용성을 기록합니다. """

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
LOCK = json.loads((ROOT / "tools/ci/ncs-3.4.0.lock.json").read_text(encoding="utf-8"))
BOARD = "nrf54l15dk/nrf54l15/cpuapp/nu54dk"
SAMPLES = {
    "bap_unicast_client": "zephyr/samples/bluetooth/bap_unicast_client",
    "bap_unicast_server": "zephyr/samples/bluetooth/bap_unicast_server",
    "bap_broadcast_source": "zephyr/samples/bluetooth/bap_broadcast_source",
    "bap_broadcast_sink": "zephyr/samples/bluetooth/bap_broadcast_sink",
    "bap_broadcast_assistant": "zephyr/samples/bluetooth/bap_broadcast_assistant",
    "cap_initiator": "zephyr/samples/bluetooth/cap_initiator",
    "cap_acceptor": "zephyr/samples/bluetooth/cap_acceptor",
    "pbp_public_broadcast_source": "zephyr/samples/bluetooth/pbp_public_broadcast_source",
    "pbp_public_broadcast_sink": "zephyr/samples/bluetooth/pbp_public_broadcast_sink",
    "ccp_call_control_client": "zephyr/samples/bluetooth/ccp_call_control_client",
    "ccp_call_control_server": "zephyr/samples/bluetooth/ccp_call_control_server",
    "tmap_central": "zephyr/samples/bluetooth/tmap_central",
    "tmap_peripheral": "zephyr/samples/bluetooth/tmap_peripheral",
    "tmap_bmr": "zephyr/samples/bluetooth/tmap_bmr",
    "tmap_bms": "zephyr/samples/bluetooth/tmap_bms",
    "hap_ha": "zephyr/samples/bluetooth/hap_ha",
}


def revision(path: Path) -> str:
    """! @brief 저장소의 exact HEAD를 읽습니다. """
    return subprocess.check_output(("git", "rev-parse", "HEAD"), cwd=path, text=True).strip()


def sha256(path: Path) -> str:
    """! @brief 산출물 hash를 계산합니다. """
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_size(text: str, region: str) -> int | None:
    """! @brief Zephyr size 표에서 사용 byte를 읽습니다. """
    match = re.search(rf"^\s*{region}:\s*(\d+) B", text, flags=re.MULTILINE)
    return int(match.group(1)) if match else None


def main() -> int:
    """! @brief 선택한 sample을 서로 다른 clean build directory에서 실행합니다. """
    parser = argparse.ArgumentParser()
    parser.add_argument("--ncs-root", type=Path, default=Path("C:/Users/eidos/ncs/v3.4.0"))
    parser.add_argument("--toolchain-root", type=Path,
                        default=Path("C:/Users/eidos/ncs/toolchains/dcbdc366a1"))
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--samples", nargs="+", choices=tuple(SAMPLES), default=tuple(SAMPLES))
    parser.add_argument("--require-all-pass", action="store_true")
    args = parser.parse_args()

    ncs_root = args.ncs_root.resolve()
    output_root = args.output_root.resolve()
    board_root = (ROOT / "board_package/NU54DK_Zephyr_DTS").resolve()
    west = (args.toolchain_root / "opt/bin/Scripts/west.exe").resolve()
    expected_nrf = LOCK["ncs"]["revision"]
    expected_zephyr = LOCK["zephyr"]["revision"]
    observed_nrf = revision(ncs_root / "nrf")
    observed_zephyr = revision(ncs_root / "zephyr")
    if observed_nrf != expected_nrf or observed_zephyr != expected_zephyr:
        raise ValueError("고정 NCS/Zephyr revision과 실제 checkout이 다릅니다")
    if output_root.exists() and any(output_root.iterdir()):
        raise ValueError(f"빈 output root가 필요합니다: {output_root}")
    output_root.mkdir(parents=True, exist_ok=True)

    environment = os.environ.copy()
    tool_bin = args.toolchain_root / "opt/bin"
    environment["PATH"] = os.pathsep.join((str(tool_bin), str(tool_bin / "Scripts"),
                                            environment.get("PATH", "")))
    environment["PYTHONUTF8"] = "1"
    results: dict[str, object] = {}
    for name in args.samples:
        source = ncs_root / SAMPLES[name]
        build = output_root / "build" / name
        log = output_root / f"{name}.build.log"
        command = (
            str(west), "build", "--sysbuild", "-p", "always", "-b", BOARD,
            "-d", str(build), str(source), "--", f"-DBOARD_ROOT={board_root}",
        )
        with log.open("w", encoding="utf-8", errors="replace") as output:
            process = subprocess.run(command, cwd=ncs_root, env=environment,
                                     stdout=output, stderr=subprocess.STDOUT, text=True,
                                     check=False)
        log_text = log.read_text(encoding="utf-8", errors="replace")
        image = build / name / "zephyr/zephyr.hex"
        if not image.is_file():
            candidates = sorted(build.glob("*/zephyr/zephyr.hex"))
            image = candidates[0] if len(candidates) == 1 else image
        passed = process.returncode == 0 and image.is_file()
        results[name] = {
            "source": SAMPLES[name],
            "status": "PASS" if passed else "FAIL",
            "exit_code": process.returncode,
            "log": str(log),
            "log_sha256": sha256(log),
            "image": str(image) if image.is_file() else None,
            "image_sha256": sha256(image) if image.is_file() else None,
            "flash_bytes": parse_size(log_text, "FLASH"),
            "ram_bytes": parse_size(log_text, "RAM"),
            "warning_count": len(re.findall(r"\bwarning:", log_text, flags=re.IGNORECASE)),
        }
        print(f"M31_AUDIO_NATIVE_{results[name]['status']}={name}", flush=True)

    manifest = {
        "schema_version": 1,
        "board": BOARD,
        "nrf_revision": observed_nrf,
        "zephyr_revision": observed_zephyr,
        "board_revision": revision(ROOT / "board_package/NU54DK_Zephyr_DTS"),
        "results": results,
        "counts": {
            "total": len(results),
            "pass": sum(item["status"] == "PASS" for item in results.values()),
            "fail": sum(item["status"] == "FAIL" for item in results.values()),
        },
    }
    (output_root / "m31-audio-native-build-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if args.require_all_pass and manifest["counts"]["fail"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
