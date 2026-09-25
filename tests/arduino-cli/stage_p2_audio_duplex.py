#!/usr/bin/env python3
"""! @brief 공개 양방향 Audio 예제를 P2 계측 sketch에 재현 가능하게 결합합니다. """

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil


ROOT = Path(__file__).resolve().parents[2]


def stage(output_root: Path) -> dict[str, dict[str, str]]:
    """! @brief 공개 예제 원문을 수정 없이 별도 staging 디렉터리에 복사합니다. """

    output_root = output_root.resolve()
    if output_root.exists() and any(output_root.iterdir()):
        raise ValueError(f"output directory is not empty: {output_root}")
    output_root.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, dict[str, str]] = {}
    for role in ("client", "server"):
        name = f"BapUnicastDuplex{role.title()}"
        source = (ROOT / "libraries" / "NUCODE_BLE_Audio" / "examples" /
                  name / f"{name}.ino")
        fixture = ROOT / "tests" / "arduino-cli" / f"p2_audio_duplex_{role}"
        destination = output_root / fixture.name
        shutil.copytree(fixture, destination)
        public_copy = destination / "PublicDuplex.h"
        shutil.copyfile(source, public_copy)
        source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        if hashlib.sha256(public_copy.read_bytes()).hexdigest() != source_hash:
            raise RuntimeError(f"{role} source copy differs")
        manifest[role] = {
            "public_source": str(source.relative_to(ROOT)).replace("\\", "/"),
            "public_source_sha256": source_hash,
            "staged_sketch": str(destination),
        }
    (output_root / "p2_audio_duplex_stage.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> None:
    """! @brief 독립된 Arduino CLI build 입력 디렉터리 두 개를 만듭니다. """

    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", required=True, type=Path)
    result = stage(parser.parse_args().output_root)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
