#!/usr/bin/env python3
"""! @brief SecureDfuPeripheral Arduino sysbuild의 signed artifact와 로그를 C 드라이브에 보존합니다. """

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from run_smoke import (
    assert_m30_secure_build,
    compile_command,
    default_cli,
    read_kconfig_boolean,
    stage_packaged_platform,
    stage_platform,
    write_cli_config,
)


ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = "SecureDfuPeripheral"


## @brief 외부 test signing key를 source와 분리하고 exact package revision을 확인합니다.
def build(output_root: Path, package_root: Path | None, key: Path, require_clean: bool) -> None:
    if output_root.exists():
        raise ValueError(f"fresh output-root가 필요합니다: {output_root}")
    if not key.is_file():
        raise ValueError("external DFU signing key file이 없습니다")
    revision = subprocess.check_output(("git", "rev-parse", "HEAD"), cwd=ROOT, text=True).strip()
    dirty = subprocess.check_output(("git", "status", "--porcelain"), cwd=ROOT, text=True).strip()
    if require_clean and dirty:
        raise ValueError("exact DFU Arduino build에는 clean source commit이 필요합니다")
    platform_version = None
    user_root = output_root / "user"
    if package_root is None:
        stage_platform(ROOT, user_root)
    else:
        release = json.loads((package_root / "release-manifest.json").read_text(encoding="utf-8"))
        if release.get("core_revision") != revision:
            raise ValueError("package core revision과 checkout HEAD가 다릅니다")
        platform_version = release.get("version")
        stage_packaged_platform(package_root, user_root)
    config = output_root / "arduino-cli.yaml"
    write_cli_config(config, user_root, output_root / "data", output_root / "downloads")
    sketch = user_root / "hardware" / "nucode" / "zephyr" / "libraries" / "NUCODE_BLE_DFU" / "examples" / EXAMPLE
    build_path = output_root / "build"
    build_path.mkdir(parents=True, exist_ok=True)
    command = list(compile_command(default_cli(), config, build_path, sketch))
    command[-1:-1] = ("--verbose", "--board-options", "feature_set=secure_ble_dfu")
    log = output_root / "SecureDfuPeripheral.build.log"
    with log.open("w", encoding="utf-8", errors="replace") as output:
        result = subprocess.run(command, stdout=output, stderr=subprocess.STDOUT, check=False)
    if result.returncode != 0:
        print(f"M31_DFU_EXAMPLE_BUILD_FAIL=LOG={log}", file=sys.stderr)
        raise RuntimeError(f"Arduino DFU example compile exit {result.returncode}")
    context = assert_m30_secure_build(build_path, f"{EXAMPLE}.ino", key)
    features = {
        item.get("id") for item in context.get("selected_features", [])
        if isinstance(item, dict)
    }
    if not {"nucode.ble.security", "nucode.ble.dfu"}.issubset(features):
        raise ValueError("DFU feature가 실제 build에 선택되지 않았습니다")
    configuration = (Path(context["zephyr_build_dir"]) / "app" / "zephyr" / ".config")
    if not configuration.is_file():
        configuration = Path(context["zephyr_build_dir"]) / "zephyr" / ".config"
    kconfig = configuration.read_text(encoding="utf-8")
    for symbol in (
        "CONFIG_BT_PERIPHERAL",
        "CONFIG_MCUMGR_TRANSPORT_BT",
        "CONFIG_MCUMGR_TRANSPORT_BT_PERM_RW_AUTHEN",
    ):
        if not read_kconfig_boolean(kconfig, symbol):
            raise ValueError(f"secure DFU profile symbol이 비활성입니다: {symbol}")
    artifact_path = build_path / f"{EXAMPLE}.ino.nu54-build.json"
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    manifest = {
        "source_revision": revision,
        "source_clean": not bool(dirty),
        "package_version": platform_version,
        "example": EXAMPLE,
        "profile": context.get("profile"),
        "selected_features": sorted(features),
        "signing_key_sha256": hashlib.sha256(key.read_bytes()).hexdigest(),
        "artifact_manifest_sha256": hashlib.sha256(artifact_path.read_bytes()).hexdigest(),
        "artifact_core_revision": artifact.get("source_inputs", {}).get("core_revision"),
        "log_sha256": hashlib.sha256(log.read_bytes()).hexdigest(),
    }
    (output_root / "m31-dfu-example-build-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"M31_DFU_EXAMPLE_BUILD_PASS={EXAMPLE};PROFILE={context.get('profile')}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--package-root", type=Path)
    parser.add_argument("--signing-key", type=Path, required=True)
    parser.add_argument("--require-clean", action="store_true")
    args = parser.parse_args()
    build(args.output_root.resolve(), args.package_root.resolve() if args.package_root else None,
          args.signing_key.resolve(), args.require_clean)
