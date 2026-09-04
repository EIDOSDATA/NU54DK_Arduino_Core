#!/usr/bin/env python3
"""프로젝트 소유 C/C++를 Allman/4칸으로 검사하거나 명시적으로 정렬합니다.

한국어 Doxygen 내용의 정확성과 전처리기 내부 중괄호는 별도 리뷰 대상입니다.
이 도구의 PASS만으로 문서 주석·모든 매크로·실행 의미 검증을 대신하지 않습니다.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
SUFFIXES = {".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx", ".ino", ".tpp"}
EXCLUDED = {"third_party", "board_package"}
REQUIRED_VERSION = "22.1.8"


def source_files():
    result = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                            cwd=ROOT, check=True, capture_output=True)
    paths = set(result.stdout.decode("utf-8").split("\0")) - {""}
    return [ROOT / path for path in sorted(paths)
            if Path(path).parts[0] not in EXCLUDED and Path(path).suffix.lower() in SUFFIXES
            and (ROOT / path).is_file()]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clang-format", default="clang-format")
    parser.add_argument("--write", action="store_true", help="명시적으로 전체 first-party 파일 정렬")
    parser.add_argument("--list", action="store_true", help="대상 목록만 표시, 정렬/검사 없음")
    args = parser.parse_args()
    paths = source_files()
    if not paths:
        raise SystemExit("C/C++ 파일 목록이 비어 있습니다.")
    if args.list:
        for path in paths:
            print(path.relative_to(ROOT).as_posix())
        print(f"CPP_STYLE_FILES={len(paths)}; LIST_ONLY")
        return 0
    version = subprocess.run([args.clang_format, "--version"], capture_output=True, text=True, check=True)
    if f"clang-format version {REQUIRED_VERSION}" not in version.stdout:
        raise SystemExit(f"clang-format {REQUIRED_VERSION} 필요: {version.stdout.strip()}")
    failed = []
    for path in paths:
        command = [args.clang_format, "--style=file", "--Werror"]
        command += ["-i"] if args.write else ["--dry-run"]
        result = subprocess.run(command + [str(path)], cwd=ROOT, capture_output=True, text=True)
        if result.returncode:
            failed.append(path.relative_to(ROOT).as_posix())
            print(result.stderr[:2000])
    print(f"CPP_STYLE_FILES={len(paths)}; FAILED={len(failed)}; WRITE={int(args.write)}")
    for path in failed:
        print(f"CPP_STYLE_FAIL={path}")
    return int(bool(failed))


if __name__ == "__main__":
    raise SystemExit(main())
