#!/usr/bin/env python3
"""! @brief M31 RC 설치 예제 113개 중 고정 Windows shard를 검증합니다. """

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import socketserver
import sys
import threading
from typing import Any, Sequence


REPOSITORY = Path(__file__).resolve().parents[2]
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import m31_windows_lifecycle as lifecycle  # noqa: E402


class M31ShardFailure(RuntimeError):
    """! @brief RC 설치 또는 shard 분모 위반을 나타냅니다. """


## @brief 정렬된 전체 예제에서 위치 modulo로 shard의 고정 집합을 선택합니다.
def select_shard(
    examples: list[tuple[str, Path, str]], shard_index: int, shard_count: int
) -> list[tuple[str, Path, str]]:
    if shard_count < 2 or not 0 <= shard_index < shard_count:
        raise M31ShardFailure("shard index/count가 유효하지 않습니다")
    return [
        item for position, item in enumerate(examples)
        if position % shard_count == shard_index
    ]


## @brief 고정 prerequisite marker와 실제 SDK/toolchain 경로를 검증합니다.
def fixed_environment(state: Path, cache_root: Path) -> dict[str, str]:
    ready = lifecycle.read_json(state / "ready.json")
    if (
        ready.get("status") != "ready"
        or ready.get("ncs_version") != "v3.4.0"
        or ready.get("ncs_revision") != "99553055607b2e9885fbc80ccd11fa9da81c2df0"
        or ready.get("zephyr_revision") != "bf801e4e3d19e1ffa76164346480cb7734dd2800"
        or ready.get("toolchain_bundle_id") != "dcbdc366a1"
    ):
        raise M31ShardFailure("고정 Nordic prerequisite ready marker가 유효하지 않습니다")
    ncs_root = Path(ready["ncs_root"]) / ready["ncs_version"]
    toolchain_root = Path(ready["toolchain_root"])
    if not ncs_root.is_dir() or not toolchain_root.is_dir():
        raise M31ShardFailure("고정 NCS 또는 toolchain root가 없습니다")
    cache_root.mkdir(parents=True, exist_ok=True)
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
    return environment


## @brief local HTTP RC를 설치하고 지정 shard만 clean compile합니다.
def execute(arguments: argparse.Namespace) -> dict[str, Any]:
    workspace = arguments.workspace.resolve()
    if workspace.exists():
        raise M31ShardFailure(f"기존 workspace를 덮어쓰지 않습니다: {workspace}")
    select_shard([], arguments.shard_index, arguments.shard_count)
    repository = arguments.repository.resolve()
    plan_path = arguments.plan.resolve()
    release_tool = lifecycle.load_release_tool()
    plan = release_tool.validate_plan(plan_path, repository=repository)
    state = arguments.prerequisite_state_root.resolve()
    environment = fixed_environment(state, arguments.cache_root.resolve())

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
    if lifecycle.sha256_file(served_archive) != archive_record["sha256"]:
        raise M31ShardFailure("로컬 server archive byte가 plan과 다릅니다")

    handler = lambda *args, **kwargs: lifecycle.QuietHandler(  # noqa: E731
        *args, directory=str(server_root), **kwargs
    )
    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler)
    server.daemon_threads = True
    port = server.server_address[1]
    index_name = "package_nucode_m31_local_index.json"
    local_index = lifecycle.read_json(official_index)
    local_index["packages"][0]["platforms"][0]["url"] = (
        f"http://127.0.0.1:{port}/{archive.name}"
    )
    (server_root / index_name).write_text(
        json.dumps(local_index, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    config = workspace / "arduino-cli.yaml"
    lifecycle.write_config(
        config, data, downloads, user,
        f"http://127.0.0.1:{port}/{index_name}",
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    steps: list[dict[str, Any]] = []

    def step(name: str, command: Sequence[str | Path], timeout: int) -> dict[str, Any]:
        result = lifecycle.run_command(
            command,
            environment=environment,
            timeout=timeout,
            log_path=logs / f"{len(steps) + 1:02}-{name}.log",
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
        step(
            "update_index",
            (arguments.arduino_cli.resolve(), "core", "update-index", "--config-file", config),
            900,
        )
        step(
            "install_candidate",
            (
                arguments.arduino_cli.resolve(), "core", "install",
                f"nucode:zephyr@{lifecycle.VERSION}", "--config-file", config,
                "--run-post-install",
            ),
            arguments.install_timeout,
        )
        listed = step(
            "list_candidate",
            (arguments.arduino_cli.resolve(), "core", "list", "--json", "--config-file", config),
            120,
        )
        lifecycle.assert_installed_version(listed["output"], lifecycle.VERSION)
        platform = data / "packages" / "nucode" / "hardware" / "zephyr" / lifecycle.VERSION
        manifest = lifecycle.read_json(platform / "release-manifest.json")
        if (
            manifest.get("core_revision") != plan["core_revision"]
            or manifest.get("board_revision") != plan["board_revision"]
            or manifest.get("runtime_payload_sha256") != plan["runtime_payload_sha256"]
        ):
            raise M31ShardFailure("설치 candidate provenance가 RC plan과 다릅니다")
        examples = lifecycle.installed_examples(platform)
        selected = select_shard(
            examples, arguments.shard_index, arguments.shard_count
        )
        expected = (
            lifecycle.EXPECTED_EXAMPLES + arguments.shard_count - 1 - arguments.shard_index
        ) // arguments.shard_count
        if len(selected) != expected:
            raise M31ShardFailure("고정 shard 분모가 다릅니다")
        result_records = []
        example_logs = logs / "examples"
        example_builds = build_root / "examples"
        example_logs.mkdir()
        example_builds.mkdir()
        for identity, sketch, profile in selected:
            result_records.append(
                lifecycle.compile_example(
                    arguments.arduino_cli.resolve(), config, environment,
                    example_builds, example_logs, identity, sketch, profile,
                )
            )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)

    return {
        "schema_version": 1,
        "work_id": "M31-W08",
        "status": "PASS",
        "test": "windows_installed_examples_shard",
        "observed_utc": datetime.now(timezone.utc).isoformat(),
        "source_revision": plan["core_revision"],
        "release_version": lifecycle.VERSION,
        "host_scope": "GitHub Actions windows-2025",
        "package": {
            "archive_sha256": archive_record["sha256"],
            "runtime_payload_sha256": plan["runtime_payload_sha256"],
            "board_revision": plan["board_revision"],
        },
        "shard": {
            "index": arguments.shard_index,
            "count": arguments.shard_count,
            "assignment": "sorted_identity_position_modulo",
            "global_denominator": lifecycle.EXPECTED_EXAMPLES,
            "assigned": len(selected),
            "compiled": len(result_records),
            "failed": 0,
        },
        "isolation": {
            "fresh_arduino_data": True,
            "fresh_download_cache": True,
            "fresh_sketchbook": True,
            "shard_specific_build_cache": True,
            "public_installation_modified": False,
        },
        "results": result_records,
        "steps": steps,
    }


## @brief shard 결과를 원자적으로 기록합니다.
def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, default=REPOSITORY)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--arduino-cli", type=Path, required=True)
    parser.add_argument("--prerequisite-state-root", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--shard-index", type=int, required=True)
    parser.add_argument("--shard-count", type=int, default=8)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--install-timeout", type=int, default=3600)
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
    print(
        f"M31_WINDOWS_SHARD_PASS=index:{result['shard']['index']};"
        f"compiled:{result['shard']['compiled']}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as error:
        print(f"M31_WINDOWS_SHARD_FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
