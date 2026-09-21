#!/usr/bin/env python3
"""! @brief 설치된 NUCODE BLE ISO 예제 11개를 발견·원본 대조·전수 빌드합니다. """

from __future__ import annotations

from argparse import ArgumentParser
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import re
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[2]
LIBRARY = ROOT / "libraries" / "NUCODE_BLE_ISO"
EXPECTED = {
    "BISEncryptedReceiver", "BISEncryptedSource", "BISReceiver", "BISSource",
    "BISTimeReceiver", "BISTimeSource", "CISCentral", "CISPeripheral",
    "CISToBISBridge", "CISToBISPeer", "CISToBISReceiver",
}
FLASH = re.compile(r"Sketch uses (\d+) bytes")
RAM = re.compile(r"Global variables use (\d+) bytes")


## @brief 파일 이름과 내용까지 포함한 library tree 지문을 계산합니다.
def tree_fingerprint(directory: Path) -> tuple[int, str]:
    files = sorted(path for path in directory.rglob("*") if path.is_file())
    digest = hashlib.sha256()
    for path in files:
        relative = path.relative_to(directory).as_posix()
        digest.update(relative.encode("utf-8") + b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return len(files), digest.hexdigest()


## @brief 한 예제의 image와 Arduino CLI build 출력을 증거로 묶습니다.
def build_example(cli: Path, config: Path, fqbn: str, sketch: Path,
                  directory: Path) -> dict:
    command = (str(cli), "compile", "--config-file", str(config),
               "--fqbn", fqbn, "--build-path", str(directory), str(sketch))
    started = time.monotonic()
    completed = subprocess.run(command, capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=900,
                               check=False)
    combined = completed.stdout + completed.stderr
    log = directory.parent / f"{sketch.name}.build.log"
    log.write_text(combined, encoding="utf-8")
    images = list(directory.glob("*.ino.hex"))
    flash = FLASH.search(combined)
    ram = RAM.search(combined)
    passed = (completed.returncode == 0 and len(images) == 1 and
              flash is not None and ram is not None)
    return {
        "example": sketch.name,
        "status": "PASS" if passed else "FAIL",
        "exit_code": completed.returncode,
        "elapsed_s": round(time.monotonic() - started, 3),
        "sketch_sha256": hashlib.sha256(
            (sketch / f"{sketch.name}.ino").read_bytes()).hexdigest(),
        "log_sha256": hashlib.sha256(log.read_bytes()).hexdigest(),
        "hex_sha256": hashlib.sha256(images[0].read_bytes()).hexdigest()
        if len(images) == 1 else None,
        "program_bytes": int(flash.group(1)) if flash else None,
        "ram_bytes": int(ram.group(1)) if ram else None,
        "failure_tail": combined.splitlines()[-15:] if not passed else [],
    }


## @brief clean source와 동일한 설치본의 11개 역할을 빠짐없이 검사합니다.
def main() -> int:
    parser = ArgumentParser()
    parser.add_argument("--arduino-cli", required=True, type=Path)
    parser.add_argument("--config-file", required=True, type=Path)
    parser.add_argument("--build-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--fqbn", default="nucode:zephyr:nu54dk:feature_set=ble")
    args = parser.parse_args()
    cli = args.arduino_cli.resolve()
    config = args.config_file.resolve()
    build_root = args.build_root.resolve()
    output = args.output.resolve()
    if not cli.is_file() or not config.is_file():
        parser.error("Arduino CLI executable과 config file이 필요합니다")
    if build_root.exists() or output.exists():
        parser.error("기존 build root나 evidence를 덮어쓰지 않습니다")
    if build_root.is_relative_to(ROOT) or output.is_relative_to(ROOT):
        parser.error("build root와 실행 중 evidence는 저장소 밖에 둡니다")
    dirty = subprocess.check_output(("git", "status", "--porcelain"),
                                    cwd=ROOT, text=True).strip()
    if dirty:
        parser.error("exact package build에는 clean source가 필요합니다")
    revision = subprocess.check_output(("git", "rev-parse", "HEAD"),
                                       cwd=ROOT, text=True).strip()
    listing = subprocess.run(
        (str(cli), "lib", "examples", "NUCODE BLE ISO", "--json",
         "--config-file", str(config)),
        capture_output=True, text=True, encoding="utf-8", check=True,
    )
    libraries = json.loads(listing.stdout)["examples"]
    if len(libraries) != 1 or libraries[0]["library"]["name"] != "NUCODE BLE ISO":
        raise RuntimeError("설치된 NUCODE BLE ISO library가 정확히 하나여야 합니다")
    installed = Path(libraries[0]["library"]["install_dir"]).resolve()
    sketches = [Path(value).resolve() for value in libraries[0]["examples"]]
    if (set(path.name for path in sketches) != EXPECTED or
        len(sketches) != len(EXPECTED) or
        any(path.parent != installed / "examples" for path in sketches)):
        raise RuntimeError("설치 ISO 예제 11개 discovery 결과가 계약과 다릅니다")
    repo_count, repo_tree = tree_fingerprint(LIBRARY)
    installed_count, installed_tree = tree_fingerprint(installed)
    if (repo_count != installed_count or repo_tree != installed_tree or
        installed.is_relative_to(ROOT)):
        raise RuntimeError("설치 library가 clean source와 동일한 별도 package여야 합니다")
    result = {
        "status": "IN_PROGRESS",
        "test": "m31_iso_installed_examples_all_build",
        "core_revision": revision,
        "source_clean": True,
        "observed_utc": datetime.now(timezone.utc).isoformat(),
        "fqbn": args.fqbn,
        "cli_sha256": hashlib.sha256(cli.read_bytes()).hexdigest(),
        "config_sha256": hashlib.sha256(config.read_bytes()).hexdigest(),
        "library": {
            "name": "NUCODE BLE ISO", "location": "platform",
            "container_platform": libraries[0]["library"]["container_platform"],
            "source_file_count": repo_count, "source_tree_sha256": repo_tree,
            "installed_tree_sha256": installed_tree,
        },
        "discovered": sorted(path.name for path in sketches),
        "builds": [],
    }
    build_root.mkdir(parents=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    for sketch in sorted(sketches):
        row = build_example(cli, config, args.fqbn, sketch,
                            build_root / sketch.name)
        result["builds"].append(row)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")
        print(f"{sketch.name}: {row['status']}", flush=True)
        if row["status"] != "PASS":
            result["status"] = "FAIL"
            break
    else:
        result["status"] = "PASS"
    result["finished_utc"] = datetime.now(timezone.utc).isoformat()
    result["source_clean_after"] = not bool(subprocess.check_output(
        ("git", "status", "--porcelain"), cwd=ROOT, text=True).strip())
    if not result["source_clean_after"]:
        result["status"] = "FAIL"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print(f"M31_ISO_INSTALLED_EXAMPLES={result['status']};"
          f"BUILDS={sum(row['status'] == 'PASS' for row in result['builds'])}/11")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
