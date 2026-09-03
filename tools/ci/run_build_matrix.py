#!/usr/bin/env python3
"""! @brief 릴리스 도입 기능군 build를 병렬 실행하고 실패 위치를 요약합니다. """

from __future__ import annotations

import argparse
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Sequence


REPOSITORY = Path(__file__).resolve().parents[2]
ZEPHYR_GROUPS = ("v0.1.0", "v0.2.0", "v0.3.0", "v0.4.0")
ARDUINO_GROUPS = ("v0.1.0", "v0.2.0", "v0.3.0-ble", "v0.3.0-compat")
SHORT_ZEPHYR_OUTDIRS = {
    "v0.1.0": "z1",
    "v0.2.0": "z2",
    "v0.3.0": "z3",
    "v0.4.0": "z4",
}


class MatrixFailure(RuntimeError):
    """! @brief 병렬 build matrix의 입력 또는 실행 실패를 나타냅니다. """


@dataclass(frozen=True)
class BuildTask:
    """! @brief 한 릴리스 기능군 build의 실행 정보입니다. """

    group: str
    command: tuple[str, ...]
    log: Path


@dataclass(frozen=True)
class BuildResult:
    """! @brief 한 릴리스 기능군 build의 결과입니다. """

    group: str
    status: str
    return_code: int
    duration_seconds: float
    log: str
    failure_tail: tuple[str, ...]


## @brief runner에 유효한 릴리스 기능군을 반환합니다.
def supported_groups(runner: str) -> tuple[str, ...]:
    if runner == "zephyr":
        return ZEPHYR_GROUPS
    if runner == "arduino":
        return ARDUINO_GROUPS
    raise MatrixFailure(f"알 수 없는 runner입니다: {runner}")


## @brief 실행 전 검토와 unit test가 가능한 하위 명령 목록을 만듭니다.
def build_tasks(
    *,
    runner: str,
    groups: Sequence[str],
    python: Path,
    evidence_dir: Path,
    workspace: Path | None = None,
    out_root: Path | None = None,
    arduino_cli: Path | None = None,
    jobs: int = 2,
) -> tuple[BuildTask, ...]:
    allowed = supported_groups(runner)
    unknown = tuple(group for group in groups if group not in allowed)
    if unknown:
        raise MatrixFailure(f"{runner}에서 지원하지 않는 기능군입니다: {unknown}")
    if len(set(groups)) != len(groups):
        raise MatrixFailure("같은 기능군을 두 번 지정할 수 없습니다.")

    tasks: list[BuildTask] = []
    for group in groups:
        if runner == "zephyr":
            if workspace is None or out_root is None:
                raise MatrixFailure("Zephyr runner에는 --workspace와 --out-root가 필요합니다.")
            command = (
                str(python),
                str(REPOSITORY / "tools" / "ci" / "run_zephyr_build.py"),
                "--workspace",
                str(workspace),
                "--outdir",
                str(out_root / SHORT_ZEPHYR_OUTDIRS[group]),
                "--group",
                group,
                "--jobs",
                str(jobs),
            )
        else:
            if arduino_cli is None:
                raise MatrixFailure("Arduino runner에는 --arduino-cli가 필요합니다.")
            command = (
                str(python),
                str(REPOSITORY / "tests" / "arduino-cli" / "run_smoke.py"),
                "--cli",
                str(arduino_cli),
                "--group",
                group,
            )
        tasks.append(
            BuildTask(
                group=group,
                command=command,
                log=evidence_dir / f"{runner}-{group}.log",
            )
        )
    return tuple(tasks)


## @brief 한 하위 build의 전체 출력을 log로 보존하며 console에도 group prefix로 표시합니다.
def run_task(task: BuildTask) -> BuildResult:
    started = time.monotonic()
    lines: deque[str] = deque(maxlen=40)
    return_code = 1
    try:
        with task.log.open("w", encoding="utf-8", newline="\n") as log:
            environment = dict(os.environ)
            environment["PYTHONUNBUFFERED"] = "1"
            process = subprocess.Popen(
                task.command,
                cwd=REPOSITORY,
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            assert process.stdout is not None
            for line in process.stdout:
                log.write(line)
                log.flush()
                lines.append(line.rstrip())
                print(f"[{task.group}] {line}", end="", flush=True)
            return_code = process.wait()
    except OSError as error:
        message = f"runner start/log failure: {error}"
        lines.append(message)
        try:
            task.log.write_text(message + "\n", encoding="utf-8", newline="\n")
        except OSError:
            pass
    duration = round(time.monotonic() - started, 3)
    status = "passed" if return_code == 0 else "failed"
    tail = tuple(lines) if return_code != 0 else ()
    marker = "PASS" if return_code == 0 else "FAIL"
    print(
        f"BUILD_GROUP_{marker}={task.group};RETURN_CODE={return_code};"
        f"SECONDS={duration};LOG={task.log}"
    )
    return BuildResult(
        group=task.group,
        status=status,
        return_code=return_code,
        duration_seconds=duration,
        log=str(task.log),
        failure_tail=tail,
    )


## @brief 요청한 build matrix를 실행하거나 plan만 출력합니다.
def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runner", choices=("zephyr", "arduino"), required=True)
    parser.add_argument("--groups", nargs="+")
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--out-root", type=Path)
    parser.add_argument("--arduino-cli", type=Path)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--max-workers", type=int, choices=range(1, 9), default=2)
    parser.add_argument("--jobs", type=int, choices=range(1, 9), default=2)
    parser.add_argument("--plan", action="store_true")
    args = parser.parse_args(arguments)

    groups = tuple(args.groups or supported_groups(args.runner))
    evidence_dir = args.evidence_dir.resolve()
    tasks = build_tasks(
        runner=args.runner,
        groups=groups,
        python=args.python.resolve(),
        evidence_dir=evidence_dir,
        workspace=args.workspace.resolve() if args.workspace else None,
        out_root=args.out_root.resolve() if args.out_root else None,
        arduino_cli=args.arduino_cli.resolve() if args.arduino_cli else None,
        jobs=args.jobs,
    )
    plan = {
        "runner": args.runner,
        "groups": list(groups),
        "max_workers": min(args.max_workers, len(tasks)),
        "tasks": [
            {"group": task.group, "command": list(task.command), "log": str(task.log)}
            for task in tasks
        ],
    }
    if args.plan:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0
    if evidence_dir.exists():
        raise MatrixFailure(f"evidence directory는 실행 전에 없어야 합니다: {evidence_dir}")
    evidence_dir.mkdir(parents=True)

    started_at = datetime.now(timezone.utc).isoformat()
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=min(args.max_workers, len(tasks))) as executor:
        results = tuple(executor.map(run_task, tasks))
    status = "passed" if all(result.return_code == 0 for result in results) else "failed"
    summary = {
        "schema_version": 1,
        "gate": "release-era-build-matrix",
        "status": status,
        "runner": args.runner,
        "started_at": started_at,
        "duration_seconds": round(time.monotonic() - started, 3),
        "max_workers": min(args.max_workers, len(tasks)),
        "results": [asdict(result) for result in results],
    }
    summary_path = evidence_dir / "matrix-summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    if status == "failed":
        failed = ",".join(result.group for result in results if result.return_code != 0)
        print(f"BUILD_MATRIX_FAIL={failed};SUMMARY={summary_path}", file=sys.stderr)
        return 1
    print(f"BUILD_MATRIX_PASS={len(results)};SUMMARY={summary_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except MatrixFailure as error:
        print(f"BUILD_MATRIX_FAIL: {error}", file=sys.stderr)
        raise SystemExit(1) from error
