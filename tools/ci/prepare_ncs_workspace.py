#!/usr/bin/env python3
"""! @brief 공식 toolchain container에서 exact NCS west workspace를 준비합니다. """

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Sequence


SCRIPT_ROOT = Path(__file__).resolve().parent
LOCK_MODULE_PATH = SCRIPT_ROOT / "verify_ci_lock.py"
SPEC = importlib.util.spec_from_file_location("nu54_m12_lock", LOCK_MODULE_PATH)
assert SPEC and SPEC.loader
LOCK_MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(LOCK_MODULE)


class WorkspaceFailure(RuntimeError):
    """! @brief NCS west workspace 준비 실패를 나타냅니다. """


## @brief command를 실행하고 실패 시 출력과 함께 중단합니다.
def run_checked(command: Sequence[str | Path], *, cwd: Path | None = None) -> str:
    normalized = [str(item) for item in command]
    print(f"[M12-NCS] exec: {subprocess.list2cmdline(normalized)}", flush=True)
    result = subprocess.run(
        normalized,
        cwd=cwd,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    print(result.stdout, end="")
    if result.returncode != 0:
        raise WorkspaceFailure(
            f"명령이 종료 코드 {result.returncode}로 실패했습니다: "
            f"{subprocess.list2cmdline(normalized)}"
        )
    return result.stdout.strip()


## @brief cache 유무와 관계없이 manifest repository를 exact commit으로 고정합니다.
def prepare_workspace(workspace: Path, lock: dict[str, Any]) -> None:
    workspace = workspace.resolve()
    workspace.parent.mkdir(parents=True, exist_ok=True)
    nrf = workspace / "nrf"
    initialize_west = not (workspace / ".west").is_dir()
    if initialize_west:
        if workspace.exists() and any(workspace.iterdir()):
            raise WorkspaceFailure(f".west 없이 비어 있지 않은 workspace를 거부합니다: {workspace}")
        run_checked(("git", "init", nrf))
        run_checked(
            ("git", "remote", "add", "origin", lock["ncs"]["repository"]),
            cwd=nrf,
        )
    if not (nrf / ".git").exists():
        raise WorkspaceFailure(f"NCS manifest repository가 없습니다: {nrf}")
    run_checked(
        ("git", "fetch", "--no-tags", "--depth=1", "origin", lock["ncs"]["revision"]),
        cwd=nrf,
    )
    run_checked(("git", "checkout", "--detach", lock["ncs"]["revision"]), cwd=nrf)
    if initialize_west:
        run_checked(("west", "init", "-l", nrf), cwd=workspace)
    run_checked(("west", "update", "--narrow"), cwd=workspace)
    LOCK_MODULE.validate_workspace(workspace, lock)
    toolchain_id = run_checked((nrf / "scripts" / "print_toolchain_checksum.sh",), cwd=nrf)
    if toolchain_id.splitlines()[-1] != lock["linux_toolchain_container"]["toolchain_id"]:
        raise WorkspaceFailure(
            "NCS source가 계산한 Linux toolchain ID가 container lock과 다릅니다."
        )


## @brief exact west workspace를 준비하고 identity evidence를 남깁니다.
def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--lock", type=Path, default=SCRIPT_ROOT / "ncs-3.4.0.lock.json")
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args(arguments)
    lock = LOCK_MODULE.strict_json_object(args.lock.resolve())
    LOCK_MODULE.validate_lock(lock)
    prepare_workspace(args.workspace, lock)
    evidence = {
        "schema_version": 1,
        "ncs_revision": LOCK_MODULE.git_revision(args.workspace.resolve() / "nrf"),
        "zephyr_revision": LOCK_MODULE.git_revision(args.workspace.resolve() / "zephyr"),
        "linux_toolchain_id": lock["linux_toolchain_container"]["toolchain_id"],
        "container_digest": lock["linux_toolchain_container"]["digest"],
    }
    encoded = json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.evidence is not None:
        args.evidence.resolve().parent.mkdir(parents=True, exist_ok=True)
        args.evidence.resolve().write_text(encoded, encoding="utf-8", newline="\n")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (WorkspaceFailure, LOCK_MODULE.LockFailure) as error:
        print(f"M12_NCS_WORKSPACE_FAIL: {error}", file=sys.stderr)
        raise SystemExit(1) from error
