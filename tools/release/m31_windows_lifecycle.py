#!/usr/bin/env python3
"""! @brief M31 RC를 격리 Windows Boards Manager에 설치하고 예제·수명주기를 검증합니다. """

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import http.server
import importlib.util
import json
import os
from pathlib import Path
import shutil
import socketserver
import subprocess
import sys
import threading
import time
from typing import Any, Sequence


REPOSITORY = Path(__file__).resolve().parents[2]
RELEASE_TOOL = Path(__file__).with_name("m31_release.py")
VERSION = "0.5.0-rc.1"
PREVIOUS_VERSION = "0.4.1"
FQBN = "nucode:zephyr:nu54dk"
EXPECTED_EXAMPLES = 113


class M31LifecycleFailure(RuntimeError):
    """! @brief 격리 설치·예제·수명주기 계약 위반을 나타냅니다. """


## @brief release plan 검증 모듈을 로드합니다.
def load_release_tool() -> Any:
    specification = importlib.util.spec_from_file_location(
        "nu54_m31_lifecycle_release", RELEASE_TOOL
    )
    if specification is None or specification.loader is None:
        raise M31LifecycleFailure(f"release tool을 읽을 수 없습니다: {RELEASE_TOOL}")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


## @brief 파일 SHA-256을 계산합니다.
def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


## @brief JSON을 UTF-8로 읽습니다.
def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise M31LifecycleFailure(f"JSON을 읽을 수 없습니다: {path}: {error}") from error


## @brief Arduino CLI 설정을 격리 data/download/user root에 기록합니다.
def write_config(path: Path, data: Path, downloads: Path, user: Path, index_url: str) -> None:
    path.write_text(
        "board_manager:\n"
        "  additional_urls:\n"
        "    - https://raw.githubusercontent.com/EIDOSDATA/NU54DK_Arduino_Core/main/package_nucode_nu54dk_index.json\n"
        f"    - {index_url}\n"
        "directories:\n"
        f"  data: {data.as_posix()}\n"
        f"  downloads: {downloads.as_posix()}\n"
        f"  user: {user.as_posix()}\n"
        "logging:\n"
        "  level: info\n",
        encoding="utf-8",
        newline="\n",
    )


## @brief subprocess를 shell 없이 실행하고 log hash와 종료 상태를 반환합니다.
def run_command(
    arguments: Sequence[str | Path], *, environment: dict[str, str], timeout: int,
    log_path: Path, expect_success: bool = True
) -> dict[str, Any]:
    started = time.monotonic()
    result = subprocess.run(
        [str(item) for item in arguments],
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(result.stdout, encoding="utf-8", newline="\n")
    if expect_success and result.returncode != 0:
        raise M31LifecycleFailure(
            f"명령이 실패했습니다: {arguments[1] if len(arguments) > 1 else arguments[0]}: "
            f"exit={result.returncode}: {result.stdout[-1200:]}"
        )
    if not expect_success and result.returncode == 0:
        raise M31LifecycleFailure("실패해야 하는 negative 명령이 성공했습니다")
    return {
        "exit_code": result.returncode,
        "elapsed_s": round(time.monotonic() - started, 3),
        "log_sha256": sha256_file(log_path),
        "output": result.stdout,
    }


## @brief 설치 platform 아래 공개 Arduino 예제 113개를 열거합니다.
def installed_examples(platform: Path) -> list[tuple[str, Path, str]]:
    result: list[tuple[str, Path, str]] = []
    libraries = platform / "libraries"
    for library in sorted(libraries.iterdir(), key=lambda item: item.name.casefold()):
        if not library.is_dir() or not (library / "library.properties").is_file():
            continue
        example_root = library / "examples"
        if not example_root.is_dir():
            continue
        profile = (
            "secure_ble_dfu"
            if library.name == "NUCODE_BLE_DFU"
            else "ble" if library.name.startswith("NUCODE_BLE") else "standard"
        )
        for example in sorted(example_root.iterdir(), key=lambda item: item.name.casefold()):
            sketch = example / f"{example.name}.ino"
            if example.is_dir() and sketch.is_file():
                identity = f"{library.name}/{example.name}"
                result.append((identity, example, profile))
    if len(result) != EXPECTED_EXAMPLES or len({item[0] for item in result}) != EXPECTED_EXAMPLES:
        raise M31LifecycleFailure(f"설치 예제 분모가 {EXPECTED_EXAMPLES}이 아닙니다: {len(result)}")
    return result


## @brief 설치 예제 하나를 독립 build path에서 clean compile합니다.
def compile_example(
    cli: Path, config: Path, environment: dict[str, str], build_root: Path,
    log_root: Path, identity: str, sketch: Path, profile: str
) -> dict[str, Any]:
    key = identity.replace("/", "__")
    build = build_root / key
    log = log_root / f"{key}.log"
    record = run_command(
        (
            cli, "compile", "--config-file", config, "--clean", "--fqbn", FQBN,
            "--board-options", f"feature_set={profile}", "--build-path", build, sketch,
        ),
        environment=environment,
        timeout=1800,
        log_path=log,
    )
    manifests = list(build.glob("*.nu54-build.json"))
    images = list(build.glob("*.hex"))
    if len(manifests) != 1 or len(images) != 1:
        raise M31LifecycleFailure(f"설치 예제 artifact가 정확히 하나가 아닙니다: {identity}")
    manifest = read_json(manifests[0])
    context = manifest.get("context", {})
    if context.get("profile") != profile:
        raise M31LifecycleFailure(f"설치 예제 profile이 다릅니다: {identity}")
    return {
        "identity": identity,
        "status": "PASS",
        "profile": profile,
        "sketch_sha256": sha256_file(sketch / f"{sketch.name}.ino"),
        "manifest_sha256": sha256_file(manifests[0]),
        "hex_sha256": sha256_file(images[0]),
        "build_relative": build.relative_to(build_root.parent).as_posix(),
        "elapsed_s": record["elapsed_s"],
        "log_sha256": record["log_sha256"],
    }


## @brief 예제를 직렬 또는 worker별 독립 cache를 사용하는 병렬 묶음으로 compile합니다.
def compile_examples(
    cli: Path, config: Path, environment: dict[str, str], build_root: Path,
    log_root: Path, examples: list[tuple[str, Path, str]], jobs: int,
    cache_root: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if jobs == 1:
        results = [
            compile_example(
                cli, config, environment, build_root, log_root,
                identity, sketch, profile,
            )
            for identity, sketch, profile in examples
        ]
        return results, {"mode": "serial", "workers": 1, "cache_roots": 1}

    stop = threading.Event()
    worker_roots = [cache_root / f"lifecycle-worker-{index}" for index in range(jobs)]
    for root in worker_roots:
        root.mkdir(parents=True, exist_ok=True)

    def worker(
        index: int, assigned: list[tuple[str, Path, str]]
    ) -> list[dict[str, Any]]:
        worker_environment = dict(environment)
        worker_environment["NUCODE_BUILD_CACHE_ROOT"] = str(worker_roots[index])
        records: list[dict[str, Any]] = []
        for identity, sketch, profile in assigned:
            if stop.is_set():
                break
            try:
                records.append(
                    compile_example(
                        cli, config, worker_environment, build_root, log_root,
                        identity, sketch, profile,
                    )
                )
            except Exception:
                stop.set()
                raise
        return records

    groups = [examples[index::jobs] for index in range(jobs)]
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=jobs) as executor:
        futures = [
            executor.submit(worker, index, group)
            for index, group in enumerate(groups)
        ]
        for future in as_completed(futures):
            results.extend(future.result())
    return results, {
        "mode": "parallel_isolated_worker_caches",
        "workers": jobs,
        "cache_roots": len(worker_roots),
    }


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    """! @brief 로컬 package server의 요청 로그를 외부 출력에 남기지 않습니다. """

    def log_message(self, _format: str, *_arguments: object) -> None:
        return


## @brief core list JSON에서 설치 version을 정확히 확인합니다.
def assert_installed_version(output: str, expected: str | None) -> None:
    try:
        document = json.loads(output)
    except json.JSONDecodeError as error:
        raise M31LifecycleFailure("Arduino core list 출력이 JSON이 아닙니다") from error
    entries = document.get("platforms", []) if isinstance(document, dict) else document
    versions = [
        item.get("installed_version") or item.get("version")
        for item in entries
        if isinstance(item, dict) and item.get("id") == "nucode:zephyr"
    ]
    if expected is None:
        if versions:
            raise M31LifecycleFailure(f"core uninstall 뒤에도 설치 version이 남았습니다: {versions}")
    elif versions != [expected]:
        raise M31LifecycleFailure(f"설치 version이 다릅니다: 기대={expected}, 실제={versions}")


## @brief local HTTP RC와 공개 stable index를 사용해 격리 수명주기를 실행합니다.
def execute(arguments: argparse.Namespace) -> dict[str, Any]:
    workspace = arguments.workspace.resolve()
    if workspace.exists():
        raise M31LifecycleFailure(f"기존 workspace를 덮어쓰지 않습니다: {workspace}")
    plan_path = arguments.plan.resolve()
    release_tool = load_release_tool()
    plan = release_tool.validate_plan(plan_path, repository=arguments.repository.resolve())
    cli = arguments.arduino_cli.resolve()
    state = arguments.prerequisite_state_root.resolve()
    ready_path = state / "ready.json"
    ready = read_json(ready_path)
    if (
        ready.get("status") != "ready"
        or ready.get("ncs_version") != "v3.4.0"
        or ready.get("ncs_revision") != "99553055607b2e9885fbc80ccd11fa9da81c2df0"
        or ready.get("zephyr_revision") != "bf801e4e3d19e1ffa76164346480cb7734dd2800"
        or ready.get("toolchain_bundle_id") != "dcbdc366a1"
    ):
        raise M31LifecycleFailure("고정 Nordic prerequisite ready marker가 유효하지 않습니다")
    ncs_root = Path(ready["ncs_root"]) / ready["ncs_version"]
    toolchain_root = Path(ready["toolchain_root"])
    cache_root = (
        arguments.cache_root.resolve()
        if arguments.cache_root is not None
        else workspace / "cache"
    )
    if not ncs_root.is_dir() or not toolchain_root.is_dir():
        raise M31LifecycleFailure("고정 NCS 또는 toolchain root가 없습니다")
    cache_root.mkdir(parents=True, exist_ok=True)
    workspace.mkdir(parents=True)
    data = workspace / "data"
    downloads = workspace / "downloads"
    user = workspace / "sketchbook"
    build_root = workspace / "build"
    logs = workspace / "logs"
    server_root = workspace / "server"
    for path in (data, downloads, user, build_root, logs, server_root):
        path.mkdir()
    archive_record = plan["artifacts"]["archive"]
    index_record = plan["artifacts"]["index"]
    archive = (plan_path.parent / archive_record["path"]).resolve()
    official_index = (plan_path.parent / index_record["path"]).resolve()
    served_archive = server_root / archive.name
    shutil.copy2(archive, served_archive)
    if sha256_file(served_archive) != archive_record["sha256"]:
        raise M31LifecycleFailure("로컬 server archive byte가 plan과 다릅니다")
    prerequisite_before = sha256_file(ready_path)

    handler = lambda *args, **kwargs: QuietHandler(  # noqa: E731
        *args, directory=str(server_root), **kwargs
    )
    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler)
    server.daemon_threads = True
    port = server.server_address[1]
    index_name = "package_nucode_m31_local_index.json"
    local_index = read_json(official_index)
    platform_record = local_index["packages"][0]["platforms"][0]
    platform_record["url"] = f"http://127.0.0.1:{port}/{archive.name}"
    (server_root / index_name).write_text(
        json.dumps(local_index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    config = workspace / "arduino-cli.yaml"
    write_config(
        config, data, downloads, user,
        f"http://127.0.0.1:{port}/{index_name}",
    )
    environment = dict(os.environ)
    environment.update(
        {
            "NUCODE_PREREQUISITE_STATE_ROOT": str(state),
            "NUCODE_NCS_ROOT": str(ncs_root),
            "NUCODE_TOOLCHAIN_ROOT": str(toolchain_root),
            "NUCODE_BUILD_CACHE_ROOT": str(cache_root),
            "PYTHONUTF8": "1",
        }
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    steps: list[dict[str, Any]] = []

    def step(name: str, command: Sequence[str | Path], timeout: int,
             expect_success: bool = True) -> dict[str, Any]:
        result = run_command(
            command,
            environment=environment,
            timeout=timeout,
            log_path=logs / f"{len(steps) + 1:02}-{name}.log",
            expect_success=expect_success,
        )
        steps.append(
            {
                "name": name,
                "status": "PASS",
                "exit_code": result["exit_code"],
                "elapsed_s": result["elapsed_s"],
                "log_sha256": result["log_sha256"],
            }
        )
        return result

    try:
        step("cli_identity", (cli, "version", "--json"), 120)
        step("update_index", (cli, "core", "update-index", "--config-file", config), 900)
        step(
            "install_previous",
            (cli, "core", "install", f"nucode:zephyr@{PREVIOUS_VERSION}",
             "--config-file", config, "--run-post-install"),
            arguments.install_timeout,
        )
        listed = step("list_previous", (cli, "core", "list", "--json", "--config-file", config), 120)
        assert_installed_version(listed["output"], PREVIOUS_VERSION)
        step(
            "upgrade_candidate",
            (cli, "core", "install", f"nucode:zephyr@{VERSION}",
             "--config-file", config, "--run-post-install"),
            arguments.install_timeout,
        )
        listed = step("list_candidate", (cli, "core", "list", "--json", "--config-file", config), 120)
        assert_installed_version(listed["output"], VERSION)
        platform = data / "packages" / "nucode" / "hardware" / "zephyr" / VERSION
        release_manifest = read_json(platform / "release-manifest.json")
        if (
            release_manifest.get("core_revision") != plan["core_revision"]
            or release_manifest.get("board_revision") != plan["board_revision"]
            or release_manifest.get("runtime_payload_sha256") != plan["runtime_payload_sha256"]
        ):
            raise M31LifecycleFailure("설치 candidate provenance가 RC plan과 다릅니다")
        examples = installed_examples(platform)
        example_logs = logs / "examples"
        example_logs.mkdir()
        example_builds = build_root / "examples"
        example_builds.mkdir()
        selected_examples = examples
        if arguments.compile_mode == "representative":
            selected_examples = [
                item for item in examples
                if item[0] == "NUCODE_BLE_DirectionFinding/CteBeacon"
            ]
            if len(selected_examples) != 1:
                raise M31LifecycleFailure("대표 lifecycle 예제 분모가 1이 아닙니다")
        results, execution = compile_examples(
            cli,
            config,
            environment,
            example_builds,
            example_logs,
            selected_examples,
            arguments.jobs,
            cache_root,
        )
        results.sort(key=lambda item: item["identity"].casefold())
        if len(results) != len(selected_examples) or any(
            item["status"] != "PASS" for item in results
        ):
            raise M31LifecycleFailure("설치 예제 전수 compile이 완료되지 않았습니다")
        steps.append(
            {
                "name": "installed_examples",
                "status": "PASS",
                "denominator": EXPECTED_EXAMPLES,
                "compiled": len(results),
                "compile_mode": arguments.compile_mode,
                "failed": 0,
            }
        )
        cte = next(item for item in results if item["identity"] == "NUCODE_BLE_DirectionFinding/CteBeacon")
        cte_build = workspace / cte["build_relative"]
        cte_hex = next(cte_build.glob("*.hex"))
        step(
            "negative_unknown_version",
            (cli, "core", "install", "nucode:zephyr@0.5.0-rc.2",
             "--config-file", config),
            300,
            expect_success=False,
        )
        step("uninstall_candidate", (cli, "core", "uninstall", "nucode:zephyr", "--config-file", config), 900)
        listed = step("list_uninstalled", (cli, "core", "list", "--json", "--config-file", config), 120)
        assert_installed_version(listed["output"], None)
        if sha256_file(ready_path) != prerequisite_before:
            raise M31LifecycleFailure("core uninstall이 prerequisite ready marker를 변경했습니다")
        step(
            "reinstall_candidate",
            (cli, "core", "install", f"nucode:zephyr@{VERSION}",
             "--config-file", config, "--run-post-install"),
            arguments.install_timeout,
        )
        listed = step("list_reinstalled", (cli, "core", "list", "--json", "--config-file", config), 120)
        assert_installed_version(listed["output"], VERSION)
        reinstalled = data / "packages" / "nucode" / "hardware" / "zephyr" / VERSION
        rediscovered = installed_examples(reinstalled)
        if len(rediscovered) != EXPECTED_EXAMPLES:
            raise M31LifecycleFailure("reinstall 뒤 예제 발견 분모가 달라졌습니다")
        cache_rebuild = compile_example(
            cli,
            config,
            environment,
            build_root / "cache-rebuild",
            logs / "cache-rebuild",
            "NUCODE_BLE_DirectionFinding/CteBeacon",
            reinstalled / "libraries" / "NUCODE_BLE_DirectionFinding" / "examples" / "CteBeacon",
            "ble",
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)
    return {
        "schema_version": 1,
        "work_id": "M31-W08",
        "status": "PASS",
        "test": "windows_boards_manager_lifecycle",
        "observed_utc": datetime.now(timezone.utc).isoformat(),
        "source_revision": plan["core_revision"],
        "release_version": VERSION,
        "previous_version": PREVIOUS_VERSION,
        "host_scope": "Windows 10/11 x64",
        "package": {
            "archive_sha256": archive_record["sha256"],
            "runtime_payload_sha256": plan["runtime_payload_sha256"],
            "board_revision": plan["board_revision"],
        },
        "isolation": {
            "fresh_arduino_data": True,
            "fresh_download_cache": True,
            "fresh_sketchbook": True,
            "existing_prerequisite_reused": True,
            "existing_verified_build_cache_reused": arguments.cache_root is not None,
            "public_installation_modified": False,
        },
        "examples": {
            "discovered": EXPECTED_EXAMPLES,
            "compiled": len(results),
            "compile_mode": arguments.compile_mode,
            "failed": 0,
            "results": results,
        },
        "execution": execution,
        "representative": {
            "identity": "NUCODE_BLE_DirectionFinding/CteBeacon",
            "build_relative": cte["build_relative"],
            "hex_sha256": sha256_file(cte_hex),
        },
        "lifecycle": {
            "install_previous": "PASS",
            "upgrade_candidate": "PASS",
            "unknown_version_rejected": True,
            "uninstall": "PASS",
            "prerequisite_preserved": True,
            "reinstall": "PASS",
            "rediscovered_examples": EXPECTED_EXAMPLES,
            "cache_rebuild": cache_rebuild["status"],
        },
        "steps": steps,
    }


## @brief 격리 Windows lifecycle을 실행하고 evidence를 원자적으로 기록합니다.
def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, default=REPOSITORY)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--arduino-cli", type=Path, required=True)
    parser.add_argument("--prerequisite-state-root", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument(
        "--compile-mode", choices=("full", "representative"), default="full"
    )
    parser.add_argument("--install-timeout", type=int, default=3600)
    parsed = parser.parse_args(arguments)
    if parsed.jobs not in {1, 2}:
        parser.error("--jobs는 1 또는 2여야 합니다")
    if parsed.output.exists():
        parser.error("기존 evidence를 덮어쓰지 않습니다")
    result = execute(parsed)
    parsed.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = parsed.output.with_suffix(parsed.output.suffix + ".tmp")
    temporary.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(parsed.output)
    print(
        f"M31_WINDOWS_LIFECYCLE_PASS=examples:{result['examples']['compiled']};"
        f"steps:{len(result['steps'])}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except M31LifecycleFailure as error:
        print(f"M31_WINDOWS_LIFECYCLE_FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
