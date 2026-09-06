"""! @brief 패키저의 결정적 ZIP·sidecar 기록 책임입니다. """
from __future__ import annotations
from pathlib import Path, PurePosixPath
import os
import stat
import zipfile
from .inputs import (
    ensure_safe_relative_path,
)
from .model import (
    ZIP_TIMESTAMP,
)
from .serialization import (
    sha256_bytes,
)


## @brief 고정 timestamp, mode, 순서로 ZIP 한 개를 기록합니다.
def write_deterministic_zip(
    destination: Path, root: str, files: dict[str, tuple[bytes, int]]
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    if temporary.exists():
        temporary.unlink()
    try:
        ## @note 압축기 구현 차이까지 제거하기 위해 작은 core package는 STORE 방식으로 고정합니다.
        with zipfile.ZipFile(
            temporary,
            mode="w",
            compression=zipfile.ZIP_STORED,
            allowZip64=False,
            strict_timestamps=True,
        ) as archive:
            for path, (data, mode) in sorted(files.items(), key=lambda pair: pair[0].encode("utf-8")):
                ensure_safe_relative_path(path)
                info = zipfile.ZipInfo(f"{root}/{path}", date_time=ZIP_TIMESTAMP)
                info.compress_type = zipfile.ZIP_STORED
                info.create_system = 3
                info.external_attr = ((stat.S_IFREG | mode) & 0xFFFF) << 16
                archive.writestr(info, data, compress_type=zipfile.ZIP_STORED)
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()


## @brief archive와 sidecar의 외부 checksum 목록을 생성합니다.
def write_external_checksums(paths: list[Path], destination: Path) -> None:
    lines = [f"{sha256_bytes(path.read_bytes())}  {path.name}" for path in sorted(paths, key=lambda p: p.name)]
    destination.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
