#!/usr/bin/env python3
"""! @brief 고정 Nordic RAS sample을 SDK 변경 없이 계측용 복사본으로 만듭니다. """

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import shutil
import subprocess


SAMPLE_SUBDIR = Path("nrf/samples/bluetooth/channel_sounding")
SOURCE_HASHES = {
    "ras_initiator": "0a73126c3bb131890f999477c17fa1b61ff6b8314b0c9878a1bc7933a29d9d54",
    "ras_reflector": "70bb221c0b199a25b31b8271169ab0c029e1d3c18e25d2f3638f7b5746b74a78",
}
INSTRUMENTED_HASHES = {
    "ras_initiator": "e6b670c61dcac7ed31f56e879cbd68c91c5e4067179fd47aa7187d839199b289",
    "ras_reflector": "881b23d5a428601e247797eb325ae70df08c2240de6cb1905cf65e89c1ea634a",
}


def digest(path: Path, *, normalize_lines: bool = False) -> str:
    """! @brief 필요할 때 줄 끝을 LF로 정규화해 SHA-256을 반환합니다. """

    data = path.read_bytes()
    if normalize_lines:
        data = data.replace(bytes((13, 10)), bytes((10,)))
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    """! @brief 입력 sample을 검사하고 비어 있는 출력 경로에만 복사합니다. """

    parser = argparse.ArgumentParser()
    parser.add_argument("--ncs-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    sample_root = arguments.ncs_root.resolve() / SAMPLE_SUBDIR
    output = arguments.output.resolve()
    if output.exists():
        raise RuntimeError("output already exists; choose a fresh directory")
    for role, expected in SOURCE_HASHES.items():
        source = sample_root / role / "src/main.c"
        if not source.is_file() or digest(source) != expected:
            raise RuntimeError(f"pinned Nordic source hash mismatch: {role}")
    output.mkdir(parents=True)
    for role in SOURCE_HASHES:
        shutil.copytree(sample_root / role, output / role)
    patch = Path(__file__).with_name("native-instrumentation.patch").resolve()
    subprocess.run(["git", "apply", "--whitespace=nowarn", str(patch)],
                   cwd=output, check=True)
    for role, expected in INSTRUMENTED_HASHES.items():
        actual = digest(output / role / "src/main.c", normalize_lines=True)
        if actual != expected:
            raise RuntimeError(f"instrumented source hash mismatch: {role}: {actual}")
    print("Nordic RAS comparison fixture: source hashes verified")


if __name__ == "__main__":
    main()
