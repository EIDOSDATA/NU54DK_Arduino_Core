#!/usr/bin/env python3
"""! @brief checkout platform 표시가 canonical Core 소스 버전과 일치하는지 검사합니다. """
import argparse
import importlib.util
from pathlib import Path
import re
import sys

REPOSITORY = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "nu54_identity_builder", REPOSITORY / "tools/nu54-builder/src/nu54_builder.py"
)
BUILDER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = BUILDER
SPEC.loader.exec_module(BUILDER)


## @brief 소스 checkout의 표시만 동기화하며 설치 archive version은 생성하지 않습니다.
def verify(root: Path, write: bool = False) -> dict[str, str]:
    identity = BUILDER.load_product_identity(root)
    if identity["source_version"] != identity["package_version"]:
        if not write:
            raise BUILDER.AdapterError("[NU54:E_PRODUCT_IDENTITY] checkout platform version drift")
        platform = root / "platform.txt"
        content = platform.read_text(encoding="utf-8")
        content = re.sub(r"^version=.*$", lambda _: "version=" + identity["source_version"],
                         content, flags=re.MULTILINE)
        platform.write_text(content, encoding="utf-8", newline="\n")
        identity = BUILDER.load_product_identity(root)
    return identity


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    arguments = parser.parse_args()
    try:
        identity = verify(REPOSITORY, arguments.write)
    except BUILDER.AdapterError as error:
        print(error, file=sys.stderr)
        return 1
    print(f"PRODUCT_IDENTITY_PASS=source:{identity['source_version']};checkout:{identity['package_version']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
