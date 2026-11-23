#!/usr/bin/env python3
"""! @brief OS 공통 prerequisite backend를 설치본의 신뢰 경로에서 실행합니다. """
import importlib.util
from pathlib import Path
import sys


def main():
    """! @brief 전역 Python import 경로 없이 동일 설치본 builder를 읽습니다. """
    source = Path(__file__).resolve().parents[1] / 'nu54-builder/src/nu54_builder.py'
    spec = importlib.util.spec_from_file_location('nu54_prerequisite_entry', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    from importlib import import_module
    backend = import_module(module.implementation.__name__ + '.prerequisites')
    try:
        return backend.main()
    except (module.AdapterError, OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='backslashreplace')
    raise SystemExit(main())
