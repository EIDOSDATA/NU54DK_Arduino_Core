#!/usr/bin/env python3
"""! @brief W02 Arduino ISO 예제를 보존 가능한 C-drive staging에서 빌드합니다. """

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

from run_smoke import assert_build, compile_command, default_cli, stage_packaged_platform, stage_platform, write_cli_config


EXAMPLES = (
    "CISCentral", "CISPeripheral", "BISSource", "BISReceiver",
    "BISEncryptedSource", "BISEncryptedReceiver", "BISTimeSource",
    "BISTimeReceiver", "CISToBISBridge", "CISToBISPeer",
    "CISToBISReceiver",
)


## @brief Git source 상태를 읽고 exact build의 clean 전제조건을 검사합니다.
def source_identity(repository: Path, require_clean: bool) -> dict[str, object]:
    revision = subprocess.check_output(("git", "rev-parse", "HEAD"), cwd=repository, text=True).strip()
    status = subprocess.check_output(("git", "status", "--porcelain"), cwd=repository, text=True)
    clean = not status.strip()
    if require_clean and not clean:
        raise ValueError("exact Arduino 예제 build에는 clean Git source가 필요합니다")
    return {"revision": revision, "source_clean": clean}


## @brief Arduino CLI verbose log와 HEX를 staging 안에 보존합니다.
def build_examples(root: Path, names: tuple[str, ...], require_clean: bool, direct_checkout: bool, reuse_stage: bool, package_root: Path | None) -> None:
    repository = Path(__file__).resolve().parents[2]
    if sum((direct_checkout, reuse_stage, package_root is not None)) > 1:
        raise ValueError("Arduino staging 방식을 하나만 선택해야 합니다")
    if root.exists() and not (direct_checkout or reuse_stage):
        raise ValueError(f"fresh output-root가 필요합니다: {root}")
    if reuse_stage and require_clean:
        raise ValueError("exact build는 이전 개발 staging을 재사용하지 않습니다")
    identity = source_identity(repository, require_clean)
    user_root = root / "user"
    if direct_checkout:
        platform = user_root / "hardware" / "nucode" / "zephyr"
        if not platform.is_dir() or platform.resolve() != repository.resolve():
            raise ValueError("--direct-checkout에는 실제 저장소를 가리키는 준비된 C-drive junction이 필요합니다")
    elif reuse_stage:
        if not (user_root / "hardware" / "nucode" / "zephyr" / "boards.txt").is_file():
            raise ValueError("재사용할 Arduino staging이 없습니다")
    elif package_root is not None:
        release_path = package_root / "release-manifest.json"
        document = json.loads(release_path.read_text(encoding="utf-8"))
        if document.get("core_revision") != identity["revision"]:
            raise ValueError("package core revision과 실제 checkout HEAD가 다릅니다")
        identity["package_version"] = document.get("version")
        identity["package_release_manifest_sha256"] = hashlib.sha256(release_path.read_bytes()).hexdigest()
        stage_packaged_platform(package_root, user_root)
    else:
        stage_platform(repository, user_root)
    config = root / "arduino-cli.yaml"
    write_cli_config(config, user_root, root / "data", root / "downloads")
    cli = default_cli()
    images: dict[str, object] = {}
    for name in names:
        platform = user_root / "hardware" / "nucode" / "zephyr"
        sketch = (repository if reuse_stage else platform) / "libraries" / "NUCODE_BLE_ISO" / "examples" / name
        build = root / "build" / name
        build.mkdir(parents=True, exist_ok=True)
        command = compile_command(cli, config, build, sketch)
        command[-1:-1] = ("--verbose", "--board-options", "feature_set=ble")
        log = root / f"{name}.build.log"
        with log.open("w", encoding="utf-8", errors="replace") as output:
            result = subprocess.run(command, stdout=output, stderr=subprocess.STDOUT, text=True, check=False)
        if result.returncode != 0:
            print(f"M31_ARDUINO_BUILD_FAIL={name};LOG={log}", file=sys.stderr)
            raise RuntimeError(f"Arduino compile exit {result.returncode}: {name}")
        context = assert_build(build, f"{name}.ino")
        hex_path = build / f"{name}.ino.hex"
        artifact_path = build / f"{name}.ino.nu54-build.json"
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        build_log = log.read_text(encoding="utf-8", errors="replace")
        flash = re.findall(r"^\s*FLASH:\s*(\d+) B", build_log, flags=re.MULTILINE)
        ram = re.findall(r"^\s*RAM:\s*(\d+) B", build_log, flags=re.MULTILINE)
        images[name] = {
            "hex": str(hex_path),
            "sha256": hashlib.sha256(hex_path.read_bytes()).hexdigest(),
            "context": str(build / "nu54-zephyr" / "context.json"),
            "log": str(log),
            "artifact_manifest": str(artifact_path),
            "artifact_manifest_sha256": hashlib.sha256(artifact_path.read_bytes()).hexdigest(),
            "identity_revisions": artifact.get("source_inputs", {}).get("m31_iso_revisions"),
            "flash_bytes": int(flash[-1]) if flash else None,
            "ram_bytes": int(ram[-1]) if ram else None,
            "profile": context.get("profile"),
            "selected_features": [item.get("id") for item in context.get("selected_features", [])],
        }
        print(f"M31_ARDUINO_BUILD_PASS={name};SHA256={images[name]['sha256']}", flush=True)
    manifest = {**identity, "images": images}
    (root / "m31-arduino-build-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--examples", nargs="+", choices=EXAMPLES, default=EXAMPLES)
    parser.add_argument("--require-clean", action="store_true")
    parser.add_argument("--direct-checkout", action="store_true")
    parser.add_argument("--reuse-stage", action="store_true")
    parser.add_argument("--package-root", type=Path)
    args = parser.parse_args()
    build_examples(args.output_root.resolve(), tuple(args.examples), args.require_clean, args.direct_checkout, args.reuse_stage, args.package_root.resolve() if args.package_root else None)
