#!/usr/bin/env python3
"""! @brief M31 exact 시험에서만 v0.5.0 private package 후보를 활성화합니다. """

from __future__ import annotations

from pathlib import Path
import runpy
import sys


ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "packaging" / "boards-manager" / "nu54_package.py"
VERSION = "0.5.0-rc.1"


## @brief 고정된 과거 후보 계약을 바꾸지 않고 로컬 build·validate만 실행합니다.
def main(argv: list[str]) -> int:
    if not argv or argv[0] not in ("build", "validate") or "--update-index" in argv:
        raise ValueError("M31 private package는 build·validate만 허용하며 index를 갱신하지 않습니다")
    package = runpy.run_path(str(PACKAGE))
    candidates = tuple(package["RELEASE_CANDIDATE_VERSIONS"])
    if VERSION in candidates:
        raise ValueError("M31 private 후보가 공개 package allowlist에 이미 등록됐습니다")
    package["configure_release_candidates"](candidates + (VERSION,))
    return package["main"](argv)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
