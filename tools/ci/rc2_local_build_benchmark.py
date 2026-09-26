#!/usr/bin/env python3
"""! @brief 설치된 RC2 package의 여섯 Feature set 증분 build 성능을 측정합니다. """

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Any, Sequence


CASES = (
    ("standard", "NUCODE_NU54DK/Blink"),
    ("ble", "NUCODE_BLE/NUSPeripheral"),
    ("adaptive", "NUCODE_BLE_ChannelSounding/RasInitiator"),
    ("fabric", "NUCODE_Peripheral_Fabric/FabricCapabilities"),
    ("secure_ble_dfu", "NUCODE_BLE_DFU/SecureDfuPeripheral"),
    ("ble_audio_io", "NUCODE_BLE_Audio/ExternalPdmMicrophoneSource"),
)
FQBN = "nucode:zephyr:nu54dk"


class Rc2BenchmarkFailure(RuntimeError):
    """! @brief 설치 package 또는 build 성능 증거가 불완전함을 나타냅니다. """


## @brief 파일 SHA-256을 block 단위로 계산합니다.
def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


## @brief 중복 key 없는 UTF-8 JSON object를 읽습니다.
def read_object(path: Path) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise Rc2BenchmarkFailure(f"중복 JSON key입니다: {path}: {key}")
            result[key] = value
        return result

    try:
        value = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicates
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise Rc2BenchmarkFailure(f"JSON을 읽지 못했습니다: {path}: {error}") from error
    if not isinstance(value, dict):
        raise Rc2BenchmarkFailure(f"JSON root가 object가 아닙니다: {path}")
    return value


## @brief Arduino CLI 출력을 raw byte log로 보존하고 strict UTF-8을 검증합니다.
def run_compile(
    command: Sequence[str | Path], *, environment: dict[str, str], log_path: Path,
) -> tuple[float, str]:
    started = time.perf_counter()
    result = subprocess.run(
        [str(value) for value in command],
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    elapsed = time.perf_counter() - started
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_bytes(result.stdout)
    try:
        output = result.stdout.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise Rc2BenchmarkFailure(
            f"Arduino CLI 출력이 UTF-8이 아닙니다: {log_path}: byte {error.start}"
        ) from error
    if result.returncode != 0:
        raise Rc2BenchmarkFailure(
            f"Arduino compile이 종료 코드 {result.returncode}로 실패했습니다: {log_path}"
        )
    return elapsed, output


## @brief 한 build manifest의 phase·ccache·artifact 측정값을 추출합니다.
def manifest_metrics(build: Path) -> dict[str, Any]:
    manifests = list(build.glob("*.nu54-build.json"))
    if len(manifests) != 1:
        raise Rc2BenchmarkFailure(f"build manifest가 정확히 하나가 아닙니다: {build}")
    document = read_object(manifests[0])
    context = document.get("context")
    metrics = document.get("metrics")
    artifacts = document.get("artifacts")
    if not isinstance(context, dict) or not isinstance(metrics, dict) or not isinstance(artifacts, dict):
        raise Rc2BenchmarkFailure(f"build manifest 필수 object가 없습니다: {manifests[0]}")
    artifact_hashes: dict[str, str] = {}
    for role in ("hex", "elf"):
        record = artifacts.get(role)
        path = Path(str(record.get("path", ""))) if isinstance(record, dict) else Path()
        if not path.is_file() or file_sha256(path) != record.get("sha256"):
            raise Rc2BenchmarkFailure(f"{role} artifact hash가 다릅니다: {manifests[0]}")
        artifact_hashes[role] = str(record["sha256"])
    return {
        "configure_seconds": metrics.get("configure_seconds"),
        "build_seconds": metrics.get("build_seconds"),
        "worker_count": metrics.get("worker_count"),
        "configure_target_count": metrics.get("configure_target_count"),
        "build_target_count": metrics.get("build_target_count"),
        "ccache_delta": metrics.get("ccache_delta"),
        "cache_reused": context.get("cache_reused"),
        "configure_reason": context.get("configure_reason"),
        "source_manifest_changed": context.get("source_manifest_changed"),
        "artifacts": artifact_hashes,
        "manifest_sha256": file_sha256(manifests[0]),
    }


## @brief metadata identity가 가리키는 설치 package 예제 directory를 반환합니다.
def installed_example(platform: Path, identity: str) -> Path:
    library, example = identity.split("/", 1)
    path = platform / "libraries" / library / "examples" / example
    if not (path / f"{example}.ino").is_file():
        raise Rc2BenchmarkFailure(f"설치 package 예제가 없습니다: {identity}")
    return path


## @brief cold·no-change·Sketch 수정 build를 여섯 Feature set에서 측정합니다.
def execute(arguments: argparse.Namespace) -> dict[str, Any]:
    platform = arguments.platform.resolve()
    workspace = arguments.workspace.resolve()
    if workspace.exists():
        raise Rc2BenchmarkFailure(f"기존 workspace를 덮어쓰지 않습니다: {workspace}")
    release = read_object(platform / "release-manifest.json")
    metadata = read_object(platform / "libraries" / "example-metadata.json")
    if release.get("version") != arguments.expected_version:
        raise Rc2BenchmarkFailure("설치 package version이 benchmark 대상과 다릅니다")
    if metadata.get("example_count") != 113:
        raise Rc2BenchmarkFailure("설치 package 예제 metadata 분모가 113이 아닙니다")
    workspace.mkdir(parents=True)
    environment = dict(os.environ)
    environment.update({
        "NUCODE_BUILD_CACHE_ROOT": str(workspace / "cache"),
        "NUCODE_BUILD_JOBS": str(arguments.jobs),
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
    })
    results: list[dict[str, Any]] = []
    for profile, identity in CASES:
        source = installed_example(platform, identity)
        sketch = workspace / "sketches" / profile / source.name
        shutil.copytree(source, sketch)
        build = workspace / "build" / profile
        command = (
            arguments.arduino_cli.resolve(),
            "compile",
            "--config-file",
            arguments.config.resolve(),
            "--fqbn",
            FQBN,
            "--board-options",
            f"feature_set={profile}",
            "--build-path",
            build,
            sketch,
        )
        phases: list[dict[str, Any]] = []
        for phase in ("cold", "no-change", "sketch-change"):
            if phase == "sketch-change":
                ino = sketch / f"{sketch.name}.ino"
                with ino.open("a", encoding="utf-8", newline="\n") as stream:
                    stream.write("\n/** @brief RC2 증분 benchmark 전용 무해한 주석입니다. */\n")
            elapsed, output = run_compile(
                command,
                environment=environment,
                log_path=workspace / "logs" / f"{profile}-{phase}.log",
            )
            measured = manifest_metrics(build)
            measured.update({
                "phase": phase,
                "wall_seconds": round(elapsed, 6),
                "progress_markers": output.count("[NU54 ") + output.count("[NU54] "),
                "utf8_replacement_characters": output.count("\ufffd"),
            })
            phases.append(measured)
        results.append({"profile": profile, "identity": identity, "phases": phases})
    return {
        "schema_version": 1,
        "status": "PASS",
        "test": "rc2_installed_package_six_profile_incremental_benchmark",
        "observed_utc": datetime.now(timezone.utc).isoformat(),
        "package": {
            "version": release["version"],
            "core_revision": release["core_revision"],
            "board_revision": release["board_revision"],
            "runtime_payload_sha256": release["runtime_payload_sha256"],
            "platform": platform.as_posix(),
        },
        "jobs": arguments.jobs,
        "feature_sets": results,
    }


## @brief benchmark evidence를 원자적으로 기록합니다.
def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--arduino-cli", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--platform", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-version", default="0.5.0-rc.2")
    parser.add_argument("--jobs", type=int, choices=range(1, 65), default=max(1, os.cpu_count() or 1))
    parsed = parser.parse_args(arguments)
    if parsed.output.exists():
        parser.error("기존 evidence를 덮어쓰지 않습니다")
    result = execute(parsed)
    parsed.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = parsed.output.with_suffix(parsed.output.suffix + ".tmp")
    temporary.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    temporary.replace(parsed.output)
    print(f"RC2_LOCAL_BUILD_BENCHMARK_PASS=profiles:{len(result['feature_sets'])}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Rc2BenchmarkFailure as error:
        print(f"RC2_LOCAL_BUILD_BENCHMARK_FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
