"""! @brief fcbbfac5 CSIP 7개 HIL 시나리오를 fresh storage에서 실행합니다. """

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys


WORK = Path(__file__).resolve().parent
CORE_ROOT = Path(r"C:\Users\eidos\GitHub\NU54DK_Arduino_Core")
CORE_REVISION = "fcbbfac5fe348c51be0fb4e30f2b8415099b8758"
RUNNER = WORK / "csip_hil.py"
ERASER = WORK / "erase_storage_by_probe_hash.py"
FLASHER = WORK / "flash_by_probe_hash.py"
DEBUGGER = WORK / "pyocd_commands_by_hash.py"
ARTIFACTS = WORK / "csip-artifacts-fcbbfac5"
NEUTRAL_IMAGES = Path(r"C:\w\m31w06-images-fcbbfac5")
EXPECTED_TOOL_HASHES = {
    "runner": "7e13b9ddd6cd8dab6bb57f0d38c7ec3b819b8592d70ca756c04fc34069f11f60",
    "eraser": "99174653a5e4204f505c37fb06d71ce06d430a2c65db0a9e322ee3cba23e78e4",
    "flasher": "3cdbd5d87aa8a39240bf06124ee0f5bfeafbfdf9c9c96c2705ab07d066497d16",
    "debugger": "a2d9c1a83198a3e28c6d2562320697edbbc3adba03ce10c8e6295ffde310a7a2",
}

COORDINATOR_SOURCE_SHA256 = (
    "b7f12a192da55f6dc7bd2c072776dbe9cd99ad7a4319e1ccb6581d2c56299fb7"
)
MEMBER_SOURCE_SHA256 = (
    "68bc8eb82a0b4753f73c80e9e15517517d412bdb75fb79b9f337284a3f726f68"
)

STOCK = {
    "coordinator": {
        "image": Path(r"C:\w\m31w06-coordinator-fcbbfac5\CsipSetCoordinator.ino.hex"),
        "sha256": "841cd72d4728050e3e4baa1e6c6eecf7f9def2d1874465125442bcd963746663",
    },
    "member_one": {
        "image": Path(r"C:\w\m31w06-member-fcbbfac5\CsipSetMember.ino.hex"),
        "sha256": "ad654a7f6941615ad39d85468485cf72bb4805aea4eba2fe527c02aaaf76dc32",
    },
    "member_two": {
        "image": Path(r"C:\w\m31w06-member-fcbbfac5\CsipSetMember.ino.hex"),
        "sha256": "ad654a7f6941615ad39d85468485cf72bb4805aea4eba2fe527c02aaaf76dc32",
    },
}

BOARDS = {
    "coordinator": {
        "port": "COM10",
        "probe": "e44e2ba24dbcbdd3c41e05192773a058ed7dbbca2354dda703a004646ea9a334",
        "flash_role": "source",
    },
    "member_one": {
        "port": "COM14",
        "probe": "4574ee31f25fe05f154395ea4d8c6aa0583b04a4f7a0ea97fe3d13b05eea8ca0",
        "flash_role": "sink",
    },
    "member_two": {
        "port": "COM13",
        "probe": "32f71533ff6ba27fd38ed32a17bf6d80a90d4f4980221051ed5c5a2e7fdb63a9",
        "flash_role": "sink",
    },
}

FAULTS = {
    "wrong-sirk": {
        "role": "member_two",
        "image": Path(r"C:\w\m31w06-fault-wrong-sirk-fcbbfac5\CsipSetMember.ino.hex"),
        "flash_image": NEUTRAL_IMAGES / "wrong-sirk.hex",
        "sha256": "2495bbb9a86e5fcf22f3cf0200e09454bc322ff16555ab70ac9fbf09f9cfbcf3",
        "manifest": ARTIFACTS / "wrong-sirk" / "manifest.json",
    },
    "security-sync-failure": {
        "role": "coordinator",
        "image": Path(r"C:\w\m31w06-fault-security-sync-fcbbfac5\CsipSetCoordinator.ino.hex"),
        "flash_image": NEUTRAL_IMAGES / "security-sync.hex",
        "sha256": "b98ee10bcbd8bcca90503870a6e7ae3bffe5de9551aa24aa6711f32c5010320e",
        "manifest": ARTIFACTS / "security-sync-failure" / "manifest.json",
    },
    "security-async-failure": {
        "role": "coordinator",
        "image": Path(r"C:\w\m31w06-fault-security-async-l3-fcbbfac5\CsipSetCoordinator.ino.hex"),
        "flash_image": NEUTRAL_IMAGES / "security-async.hex",
        "sha256": "c81d908a8eb15407a745a4617cf46ac1a0acfd00ba1d640b3989fdb228ce05ff",
        "manifest": ARTIFACTS / "security-async-failure" / "manifest.json",
    },
    "watchdog": {
        "role": "coordinator",
        "image": Path(r"C:\w\m31w06-fault-watchdog-fcbbfac5\CsipSetCoordinator.ino.hex"),
        "flash_image": NEUTRAL_IMAGES / "watchdog.hex",
        "sha256": "7792913f2a38e0c7b6b66c0b2ae80f5956e2ab5f2fa344a31334352d596ceee8",
        "manifest": ARTIFACTS / "watchdog" / "manifest.json",
    },
}

SCENARIOS = (
    "positive",
    "wrong-rank",
    "wrong-sirk",
    "security-sync-failure",
    "security-async-failure",
    "watchdog",
    "recovery",
)
IDENTIFIER_PATTERN = re.compile(r"(?i)(?<![0-9a-f])[0-9a-f]{16,}(?![0-9a-f])")


def run(command: list[str], label: str) -> None:
    """! @brief 하위 명령을 실행하고 실패 시 즉시 중단합니다. """
    print(f"CAMPAIGN_STAGE={label}", flush=True)
    completed = subprocess.run(command, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"{label} failed rc={completed.returncode}")


def sha256_file(path: Path) -> str:
    """! @brief 파일 SHA-256을 계산합니다. """
    return hashlib.sha256(path.read_bytes()).hexdigest()


def current_tool_hashes() -> dict[str, str]:
    """! @brief 현재 campaign helper hash를 계산합니다. """
    paths = {
        "runner": RUNNER,
        "eraser": ERASER,
        "flasher": FLASHER,
        "debugger": DEBUGGER,
    }
    return {name: sha256_file(path) for name, path in paths.items()}


def verify_tools() -> dict[str, str]:
    """! @brief hardware 접근 전에 모든 helper hash를 fail-closed 검증합니다. """
    actual = current_tool_hashes()
    if actual != EXPECTED_TOOL_HASHES:
        raise RuntimeError("campaign helper provenance mismatch")
    return actual


def sanitize_failure(error: Exception) -> str:
    """! @brief 실패 설명에서 긴 장치 식별자를 제거합니다. """
    return IDENTIFIER_PATTERN.sub("<device-identifier>", str(error))


def scenario_images(mode: str) -> dict[str, dict[str, object]]:
    """! @brief 시나리오별 runner image와 flash용 중립 경로를 구성합니다. """
    images = {
        role: {
            "image": values["image"],
            "flash_image": values["image"],
            "sha256": values["sha256"],
        }
        for role, values in STOCK.items()
    }
    if mode in FAULTS:
        fault = FAULTS[mode]
        images[str(fault["role"])] = {
            "image": fault["image"],
            "flash_image": fault["flash_image"],
            "sha256": fault["sha256"],
        }
    return images


def run_scenario(mode: str, output: Path) -> None:
    """! @brief 한 시나리오를 halt·erase·flash·runner 순서로 실행합니다. """
    scenario_dir = output / mode
    scenario_dir.mkdir(parents=True, exist_ok=False)
    images = scenario_images(mode)

    for role in ("coordinator", "member_one", "member_two"):
        run(
            [sys.executable, str(DEBUGGER), str(BOARDS[role]["probe"]), "halt"],
            f"{mode}:halt:{role}",
        )
    for role in ("coordinator", "member_one", "member_two"):
        run(
            [
                sys.executable,
                str(ERASER),
                str(BOARDS[role]["probe"]),
                "--receipt",
                str(scenario_dir / f"{role}-storage.json"),
                "--leave-halted",
            ],
            f"{mode}:erase:{role}",
        )
    for role in ("member_one", "member_two", "coordinator"):
        image = Path(images[role]["flash_image"])
        expected_hash = str(images[role]["sha256"])
        if sha256_file(image) != expected_hash:
            raise RuntimeError(f"{mode}:{role} flash image hash mismatch")
        run(
            [
                sys.executable,
                str(FLASHER),
                str(BOARDS[role]["probe"]),
                str(image),
                "--image-sha256",
                expected_hash,
                "--core-revision",
                CORE_REVISION,
                "--role",
                str(BOARDS[role]["flash_role"]),
                "--receipt",
                str(scenario_dir / f"{role}-flash.json"),
                "--leave-halted",
            ],
            f"{mode}:flash:{role}",
        )
        run(
            [sys.executable, str(DEBUGGER), str(BOARDS[role]["probe"]), "halt"],
            f"{mode}:post-flash-halt:{role}",
        )

    command = [sys.executable, str(RUNNER), mode]
    for role in ("coordinator", "member_one", "member_two"):
        option = role.replace("_", "-")
        command.extend(
            [
                f"--{option}-port",
                str(BOARDS[role]["port"]),
                f"--{option}-probe-sha256",
                str(BOARDS[role]["probe"]),
                f"--{option}-image",
                str(images[role]["image"]),
                f"--{option}-image-sha256",
                str(images[role]["sha256"]),
            ]
        )
    command.extend(
        [
            "--core-root",
            str(CORE_ROOT),
            "--core-revision",
            CORE_REVISION,
            "--coordinator-example-sha256",
            COORDINATOR_SOURCE_SHA256,
            "--member-example-sha256",
            MEMBER_SOURCE_SHA256,
            "--evidence",
            str(scenario_dir / f"{mode}.summary.json"),
            "--transcript",
            str(scenario_dir / f"{mode}.transcript.log"),
            "--execute-reset",
        ]
    )
    if mode in FAULTS:
        fault = FAULTS[mode]
        command.extend(
            [
                "--fault-role",
                str(fault["role"]),
                "--fault-image-sha256",
                str(fault["sha256"]),
                "--fault-manifest",
                str(fault["manifest"]),
            ]
        )
    run(command, f"{mode}:hil")


def main() -> int:
    """! @brief 모든 시나리오를 no-overwrite evidence directory에 실행합니다. """
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    campaign_path = Path(__file__).resolve()
    initial_campaign_hash = sha256_file(campaign_path)
    tool_hashes: dict[str, str] = {}
    completed: list[str] = []
    active_scenario: str | None = None
    summary_path = output / "campaign.summary.json"
    try:
        tool_hashes = verify_tools()
        for mode in SCENARIOS:
            active_scenario = mode
            run_scenario(mode, output)
            completed.append(mode)
        active_scenario = None
        if verify_tools() != tool_hashes:
            raise RuntimeError("campaign helper changed during execution")
        if sha256_file(campaign_path) != initial_campaign_hash:
            raise RuntimeError("campaign source changed during execution")
    except Exception as error:
        try:
            observed_tool_hashes = current_tool_hashes()
        except Exception:
            observed_tool_hashes = {}
        summary = {
            "schema": "nucode.m31.csip-full-campaign.v3",
            "status": "FAIL",
            "core_revision": CORE_REVISION,
            "requested_scenarios": list(SCENARIOS),
            "completed_scenarios": completed,
            "failed_scenario": active_scenario,
            "failure_type": type(error).__name__,
            "failure_detail": sanitize_failure(error),
            "initial_tool_sha256": tool_hashes,
            "final_tool_sha256": observed_tool_hashes,
            "initial_campaign_sha256": initial_campaign_hash,
            "final_campaign_sha256": sha256_file(campaign_path),
        }
        with summary_path.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(summary, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        raise

    summary = {
        "schema": "nucode.m31.csip-full-campaign.v3",
        "status": "PASS",
        "core_revision": CORE_REVISION,
        "requested_scenarios": list(SCENARIOS),
        "completed_scenarios": completed,
        "initial_tool_sha256": tool_hashes,
        "final_tool_sha256": current_tool_hashes(),
        "initial_campaign_sha256": initial_campaign_hash,
        "final_campaign_sha256": sha256_file(campaign_path),
    }
    with summary_path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(summary, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print("M31_CSIP_FULL_CAMPAIGN=PASS;SCENARIOS=7", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
