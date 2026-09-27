"""! @brief W03-06 CSIP fault build manifest를 hardware 없이 선검증합니다. """

from __future__ import annotations

import argparse
from pathlib import Path

import csip_hil


CORE_ROOT = Path(r"C:\Users\eidos\GitHub\NU54DK_Arduino_Core")
CORE_REVISION = "fcbbfac5fe348c51be0fb4e30f2b8415099b8758"
COORDINATOR_IMAGE = Path(
    r"C:\w\m31w06-coordinator-fcbbfac5\CsipSetCoordinator.ino.hex"
)
MEMBER_IMAGE = Path(r"C:\w\m31w06-member-fcbbfac5\CsipSetMember.ino.hex")
COORDINATOR_IMAGE_SHA256 = (
    "841cd72d4728050e3e4baa1e6c6eecf7f9def2d1874465125442bcd963746663"
)
MEMBER_IMAGE_SHA256 = (
    "ad654a7f6941615ad39d85468485cf72bb4805aea4eba2fe527c02aaaf76dc32"
)
COORDINATOR_EXAMPLE_SHA256 = (
    "b7f12a192da55f6dc7bd2c072776dbe9cd99ad7a4319e1ccb6581d2c56299fb7"
)
MEMBER_EXAMPLE_SHA256 = (
    "68bc8eb82a0b4753f73c80e9e15517517d412bdb75fb79b9f337284a3f726f68"
)
PROBES = {
    "coordinator": "e44e2ba24dbcbdd3c41e05192773a058ed7dbbca2354dda703a004646ea9a334",
    "member_one": "4574ee31f25fe05f154395ea4d8c6aa0583b04a4f7a0ea97fe3d13b05eea8ca0",
    "member_two": "32f71533ff6ba27fd38ed32a17bf6d80a90d4f4980221051ed5c5a2e7fdb63a9",
}
PORTS = {
    "coordinator": "COM10",
    "member_one": "COM14",
    "member_two": "COM13",
}
FAULTS = {
    "wrong-sirk": {
        "role": "member_two",
        "image": Path(
            r"C:\w\m31w06-fault-wrong-sirk-fcbbfac5\CsipSetMember.ino.hex"
        ),
        "sha256": "2495bbb9a86e5fcf22f3cf0200e09454bc322ff16555ab70ac9fbf09f9cfbcf3",
        "manifest": Path(
            r"C:\Users\eidos\Documents\Codex\2026-09-19\nu54dk-arduino-core-c-drive-origin\work\csip-artifacts-fcbbfac5\wrong-sirk\manifest.json"
        ),
    },
    "security-sync-failure": {
        "role": "coordinator",
        "image": Path(
            r"C:\w\m31w06-fault-security-sync-fcbbfac5\CsipSetCoordinator.ino.hex"
        ),
        "sha256": "b98ee10bcbd8bcca90503870a6e7ae3bffe5de9551aa24aa6711f32c5010320e",
        "manifest": Path(
            r"C:\Users\eidos\Documents\Codex\2026-09-19\nu54dk-arduino-core-c-drive-origin\work\csip-artifacts-fcbbfac5\security-sync-failure\manifest.json"
        ),
    },
    "security-async-failure": {
        "role": "coordinator",
        "image": Path(
            r"C:\w\m31w06-fault-security-async-l3-fcbbfac5\CsipSetCoordinator.ino.hex"
        ),
        "sha256": "c81d908a8eb15407a745a4617cf46ac1a0acfd00ba1d640b3989fdb228ce05ff",
        "manifest": Path(
            r"C:\Users\eidos\Documents\Codex\2026-09-19\nu54dk-arduino-core-c-drive-origin\work\csip-artifacts-fcbbfac5\security-async-failure\manifest.json"
        ),
    },
    "watchdog": {
        "role": "coordinator",
        "image": Path(
            r"C:\w\m31w06-fault-watchdog-fcbbfac5\CsipSetCoordinator.ino.hex"
        ),
        "sha256": "7792913f2a38e0c7b6b66c0b2ae80f5956e2ab5f2fa344a31334352d596ceee8",
        "manifest": Path(
            r"C:\Users\eidos\Documents\Codex\2026-09-19\nu54dk-arduino-core-c-drive-origin\work\csip-artifacts-fcbbfac5\watchdog\manifest.json"
        ),
    },
}


def build_arguments(mode: str, fault: dict[str, object]) -> list[str]:
    """! @brief mode별 exact image와 manifest 인자를 구성합니다. """
    images = {
        "coordinator": (COORDINATOR_IMAGE, COORDINATOR_IMAGE_SHA256),
        "member_one": (MEMBER_IMAGE, MEMBER_IMAGE_SHA256),
        "member_two": (MEMBER_IMAGE, MEMBER_IMAGE_SHA256),
    }
    role = str(fault["role"])
    images[role] = (Path(fault["image"]), str(fault["sha256"]))
    arguments = [mode]
    for selected_role in csip_hil.ROLES:
        option = selected_role.replace("_", "-")
        image, image_sha256 = images[selected_role]
        arguments.extend(
            [
                f"--{option}-port",
                PORTS[selected_role],
                f"--{option}-probe-sha256",
                PROBES[selected_role],
                f"--{option}-image",
                str(image),
                f"--{option}-image-sha256",
                image_sha256,
            ]
        )
    arguments.extend(
        [
            "--core-root",
            str(CORE_ROOT),
            "--core-revision",
            CORE_REVISION,
            "--coordinator-example-sha256",
            COORDINATOR_EXAMPLE_SHA256,
            "--member-example-sha256",
            MEMBER_EXAMPLE_SHA256,
            "--fault-role",
            role,
            "--fault-image-sha256",
            str(fault["sha256"]),
            "--fault-manifest",
            str(fault["manifest"]),
            "--evidence",
            str(Path(__file__).with_name(f"unused-{mode}.json")),
            "--execute-reset",
        ]
    )
    return arguments


def main() -> int:
    """! @brief 모든 fault manifest와 공개 source/image 결합을 검증합니다. """
    source_hashes = csip_hil.verify_source(CORE_ROOT, CORE_REVISION)
    for mode, fault in FAULTS.items():
        arguments = build_arguments(mode, fault)
        args = csip_hil.parse_arguments(arguments)
        parser = argparse.ArgumentParser(add_help=False)
        csip_hil.validate_arguments(args, parser)
        images = {
            role: getattr(args, f"{role}_image").resolve()
            for role in csip_hil.ROLES
        }
        image_hashes = {
            role: csip_hil.sha256_file(path) for role, path in images.items()
        }
        receipt = csip_hil.verify_fault_manifest(
            args, CORE_ROOT, source_hashes, images, image_hashes
        )
        print(
            f"M31_CSIP_MANIFEST_PREFLIGHT=PASS;MODE={mode};"
            f"MANIFEST_SHA256={receipt['sha256']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
