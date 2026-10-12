#!/usr/bin/env python3
"""! @brief W06 Mesh DFU 네 역할을 단일 signed candidate에 묶어 build-only로 생성합니다. """

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
from typing import Any, Callable, Sequence

from m33_w06_artifacts import (
    ArtifactFailure,
    git_content_changes,
    toolchain_bundle_root,
    toolchain_environment,
    toolchain_python,
    validate_mesh_dfu_bindings,
)
from run_zephyr_build import BOARD_TARGET, LOCK_MODULE, REPOSITORY


ROLES = ("candidate", "distributor", "target_a", "target_b")
APPLICATION = "tests/zephyr/m32_mesh_dfu_hil"
SIGNED_BIN = "m32_mesh_dfu_hil/zephyr/zephyr.signed.bin"


def pinned_python_environment(
    workspace: Path,
    toolchain_root: Path,
    lock: dict[str, Any],
    inherited: dict[str, str],
) -> dict[str, str]:
    """! @brief 고정 bundle의 Python HOME/PATH를 복원하고 사용자 site를 제외합니다.
    @note -I는 PYTHONHOME/PYTHONPATH를 무시하므로 이 환경의 child에 전달하지 않습니다.
    """

    bundle = toolchain_bundle_root(toolchain_root)
    python = toolchain_python(bundle)
    if (python != Path(sys.executable).resolve() or
            lock["windows_toolchain"]["bundle_id"].casefold() not in
            bundle.as_posix().casefold()):
        raise ArtifactFailure(
            "Mesh DFU interpreter가 고정 toolchain Python과 다릅니다"
        )
    environment = {**inherited, **toolchain_environment(bundle, workspace)}
    expected_path = os.pathsep.join(str(path) for path in (
        python.parent,
        python.parent / "Lib",
        python.parent / "Lib/site-packages",
    ))
    if environment.get("PYTHONPATH") != expected_path:
        raise ArtifactFailure(
            "Mesh DFU 고정 Python module 경로가 예상 bundle layout과 다릅니다"
        )
    environment.update({
        "PYTHONHOME": str(python.parent),
        "PYTHONNOUSERSITE": "1",
    })
    return environment


def check_source(
    expected_core: str,
    phase: str,
    revision_reader: Callable[[Path], str],
    content_reader: Callable[[Path], Sequence[str]],
) -> None:
    """! @brief exact HEAD와 Core/board clean을 역할 경계마다 검사합니다. """

    if revision_reader(REPOSITORY) != expected_core:
        raise ArtifactFailure(
            f"Mesh DFU source HEAD가 {phase} 경계에서 변경됐습니다"
        )
    roots = (
        ("Core", REPOSITORY),
        ("board", REPOSITORY / "board_package/NU54DK_Zephyr_DTS"),
    )
    for label, root in roots:
        if content_reader(root):
            raise ArtifactFailure(
                f"Mesh DFU {label} source가 {phase} 경계에서 clean하지 않습니다"
            )


def candidate_identity(path: Path) -> dict[str, Any]:
    """! @brief candidate의 byte hash·size·MCUboot 2.0.0+0 header를 고정합니다. """

    data = path.read_bytes()
    if (len(data) < 32 or
            struct.unpack_from("<I", data, 0)[0] != 0x96F3B83D or
            struct.unpack_from("<H", data, 8)[0] != 0x800 or
            struct.unpack_from("<BBHI", data, 20) != (2, 0, 0, 0)):
        raise ArtifactFailure(
            "Mesh DFU candidate signed header/version이 다릅니다"
        )
    return {
        "sha256": hashlib.sha256(data).hexdigest(),
        "size": len(data),
    }


def build_command(
    workspace: Path,
    outdir: Path,
    role: str,
    jobs: int,
    candidate: dict[str, Any] | None,
) -> list[str]:
    """! @brief YAML 기본값을 거치지 않는 한 역할의 sysbuild 명령을 만듭니다.
    @param candidate candidate 역할은 None, 나머지는 선행 signed byte의 hash·size입니다.
    """

    if role not in ROLES or jobs not in (1, 2):
        raise ArtifactFailure("Mesh DFU build role 또는 jobs가 잘못됐습니다")
    if (role == "candidate") != (candidate is None):
        raise ArtifactFailure("Mesh DFU 선행 candidate binding 입력이 잘못됐습니다")
    command = [
        sys.executable,
        "-B",
        "-s",
        "-P",
        "-m",
        "west",
        "build",
        "--sysbuild",
        "-p",
        "always",
        "-b",
        BOARD_TARGET,
        "-d",
        str(outdir),
        "--build-opt=-j" + str(jobs),
        str(REPOSITORY / APPLICATION),
        "--",
        "-DBOARD_ROOT=" +
        (REPOSITORY / "board_package/NU54DK_Zephyr_DTS").as_posix(),
        "-DEXTRA_ZEPHYR_MODULES=" + REPOSITORY.as_posix(),
        "-DUSE_CCACHE=0",
        "-DZephyrAppConfiguration_ROOT=" +
        (REPOSITORY / "tools/ci/cmake").as_posix(),
        "-DM32_MDFU_ROLE=" + role,
        "-DEXTRA_CONF_FILE=" +
        ("candidate.conf" if role == "candidate" else "mesh.conf"),
    ]
    if candidate is not None:
        if (re.fullmatch(r"[0-9a-f]{64}", str(candidate.get("sha256"))) is None or
                candidate["sha256"] == "0" * 64 or
                type(candidate.get("size")) is not int or
                candidate["size"] <= 1):
            raise ArtifactFailure("Mesh DFU candidate hash/size가 잘못됐습니다")
        command.extend((
            "-DM32_MDFU_CANDIDATE_SHA256=" + candidate["sha256"],
            "-DM32_MDFU_CANDIDATE_SIZE=" + str(candidate["size"]),
        ))
    return command


def execute_set(
    workspace: Path,
    outdir: Path,
    expected_core: str,
    jobs: int,
    environment: dict[str, str],
    executor: Callable[..., Any] = subprocess.run,
    revision_reader: Callable[[Path], str] = LOCK_MODULE.git_revision,
    content_reader: Callable[[Path], Sequence[str]] = git_content_changes,
) -> dict[str, Any]:
    """! @brief candidate 한 번과 세 역할을 순차 생성하고 byte 변경을 거부합니다.
    @param executor Host 주입 검사를 위한 build-only 실행 경계입니다.
    @param revision_reader 역할 경계의 exact source 검사를 주입합니다.
    @param content_reader Core/board clean 검사를 주입합니다.
    """

    outdir = outdir.resolve()
    if (re.fullmatch(r"[0-9a-f]{40}", expected_core) is None or
            jobs not in (1, 2) or outdir.exists() or
            outdir == Path(outdir.anchor) or
            outdir.is_relative_to(REPOSITORY.resolve()) or
            outdir.is_relative_to(workspace.resolve())):
        raise ArtifactFailure(
            "Mesh DFU build에는 저장소/SDK 밖의 fresh output이 필요합니다"
        )
    check_source(
        expected_core, "before-create", revision_reader, content_reader
    )
    outdir.mkdir(parents=True, exist_ok=False)
    roots = {role: outdir / role for role in ROLES}
    candidate_path = roots["candidate"] / SIGNED_BIN
    binding = None
    commands = []
    for role in ROLES:
        check_source(
            expected_core, "before-" + role,
            revision_reader, content_reader,
        )
        if binding is not None and candidate_identity(candidate_path) != binding:
            raise ArtifactFailure(
                "Mesh DFU candidate가 역할 build 전에 변경됐습니다"
            )
        command = build_command(workspace, roots[role], role, jobs, binding)
        commands.append(command)
        result = executor(
            command,
            cwd=workspace,
            env=environment,
            shell=False,
            check=False,
        )
        if result.returncode != 0:
            raise ArtifactFailure(
                f"Mesh DFU {role} build 실패: exit={result.returncode}"
            )
        check_source(
            expected_core, "after-" + role,
            revision_reader, content_reader,
        )
        if role == "candidate":
            binding = candidate_identity(candidate_path)
        elif candidate_identity(candidate_path) != binding:
            raise ArtifactFailure(
                "Mesh DFU candidate가 역할 build 중 변경됐습니다"
            )
    check_source(
        expected_core, "before-validation", revision_reader, content_reader
    )
    validation = validate_mesh_dfu_bindings(roots)
    if (validation["candidate_sha256"] != binding["sha256"] or
            validation["candidate_size"] != binding["size"]):
        raise ArtifactFailure(
            "Mesh DFU 최종 candidate binding이 선행 byte와 다릅니다"
        )
    check_source(
        expected_core, "before-publication", revision_reader, content_reader
    )
    evidence = {
        "schema_version": 1,
        "kind": "m32_mesh_dfu_bound_build",
        "status": "passed",
        "functional_hil": False,
        "source_revision": expected_core,
        "roles": list(ROLES),
        "commands": commands,
        "binding": validation,
    }
    output = outdir / "mesh-dfu-build-binding.json"
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(
            evidence,
            stream,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    return evidence


def main(arguments: Sequence[str] | None = None) -> int:
    """! @brief 상위 W06 builder의 승인된 SDK patch 경계에서 네 역할을 생성합니다. """

    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument("--toolchain-root", type=Path, required=True)
    parser.add_argument("--expected-core", required=True)
    parser.add_argument("--jobs", type=int, choices=(1, 2), default=2)
    args = parser.parse_args(arguments)
    workspace = args.workspace.resolve()
    lock = LOCK_MODULE.strict_json_object(
        REPOSITORY / "tools/ci/ncs-3.4.0.lock.json"
    )
    LOCK_MODULE.validate_lock(lock)
    LOCK_MODULE.validate_workspace(workspace, lock)
    board_root = REPOSITORY / "board_package/NU54DK_Zephyr_DTS"
    if LOCK_MODULE.git_revision(board_root) != lock["board"]["revision"]:
        raise ArtifactFailure("Mesh DFU board revision이 lock과 다릅니다")
    patches = LOCK_MODULE.SDK_PATCH_MODULE.approved_zephyr_patches(lock)
    expected_changes = {
        path for record in patches for path in record["files"]
    }
    actual_changes = set(
        LOCK_MODULE.SDK_PATCH_MODULE._content_changes(workspace / "zephyr")
    )
    if (os.environ.get("NUCODE_ZEPHYR_PATCHES_APPLIED") != "1" or
            actual_changes != expected_changes):
        raise ArtifactFailure(
            "Mesh DFU는 상위 W06의 승인된 SDK patch 경계가 필요합니다"
        )
    environment = pinned_python_environment(
        workspace, args.toolchain_root, lock, dict(os.environ)
    )
    environment.update({
        "ZEPHYR_BASE": str(workspace / "zephyr"),
        "CCACHE_DISABLE": "1",
        "ZephyrAppConfiguration_ROOT":
            (REPOSITORY / "tools/ci/cmake").as_posix(),
        "NUCODE_ZEPHYR_PATCHSET_SHA256":
            LOCK_MODULE.SDK_PATCH_MODULE.patchset_sha256(patches),
    })
    execute_set(
        workspace,
        args.outdir,
        args.expected_core,
        args.jobs,
        environment,
    )
    print("M32_MDFU_BOUND_BUILD_PASS=4;FUNCTIONAL_HIL=NOT_RUN")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ArtifactFailure, LOCK_MODULE.LockFailure, OSError) as error:
        print(f"M32_MDFU_BOUND_BUILD_FAIL: {error}", file=sys.stderr)
        raise SystemExit(1) from error
