#!/usr/bin/env python3
"""! @brief 기존 Arduino smoke adapter로 companion 공개 예제를 격리 build합니다. """
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import shutil
from datetime import datetime, timezone


def main():
    """! @brief source를 staging하고 예제별 log·build manifest를 보존합니다. """
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-root", required=True, type=Path)
    parser.add_argument("--example", choices=("AppleNotificationClient", "AppleMediaClient"), action="append")
    args = parser.parse_args()
    repository = Path(__file__).resolve().parents[3]
    spec = importlib.util.spec_from_file_location("smoke", repository / "tests/arduino-cli/run_smoke.py")
    smoke = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(smoke)
    root = args.work_root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    os.environ["NUCODE_BUILD_CACHE_ROOT"] = str(root / "cache")
    platform = root / "user/hardware/nucode/zephyr"
    if not platform.exists():
        smoke.stage_platform(repository, root / "user")
    else:
        shutil.copytree(repository / "libraries/NUCODE_BLE_Companion",
                        platform / "libraries/NUCODE_BLE_Companion", dirs_exist_ok=True)
    config = root / "arduino-cli.yaml"
    smoke.write_cli_config(config, root / "user", root / "data", root / "downloads")
    results = []
    for name in args.example or ("AppleNotificationClient", "AppleMediaClient"):
        build = root / name
        sketch = repository / "libraries/NUCODE_BLE_Companion/examples" / name
        command = smoke.compile_command(smoke.default_cli(), config, build, sketch)
        command[-1:-1] = ("--board-options", "feature_set=ble")
        result = subprocess.run([str(value) for value in command], capture_output=True, timeout=1800)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        log = root / f"{name}-{stamp}.log"
        log.write_bytes(result.stdout + result.stderr)
        detailed = build / "nu54-zephyr/logs/build.log"
        if detailed.is_file():
            shutil.copyfile(detailed, root / f"{name}-{stamp}-detailed.log")
        record = {"example": name, "exit_code": result.returncode, "command": [str(v) for v in command],
                  "log": str(log), "log_sha256": smoke.file_sha256(log)}
        if result.returncode == 0:
            smoke.assert_build(build, name + ".ino")
            record["elf_sha256"] = smoke.file_sha256(build / (name + ".ino.elf"))
        results.append(record)
        print(json.dumps(record), flush=True)
    (root / f"companion-build-results-{stamp}.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    return int(any(result["exit_code"] != 0 for result in results))


if __name__ == "__main__":
    raise SystemExit(main())
