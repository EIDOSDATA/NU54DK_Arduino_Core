#!/usr/bin/env python3
"""! @brief 공통 backend의 읽기 전용 Host 진단을 실행하는 얇은 진입점입니다. """
import importlib
import importlib.util
from pathlib import Path
import sys

if __name__ == '__main__':
    source = Path(__file__).resolve().parents[1] / 'nu54-builder/src/nu54_builder.py'
    spec = importlib.util.spec_from_file_location('nu54_host_doctor', source)
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='backslashreplace')
    raise SystemExit(importlib.import_module(builder.implementation.__name__ + '.host_diagnostics').main())
