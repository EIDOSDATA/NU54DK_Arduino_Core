#!/usr/bin/env python3
"""! @brief 같은 설치본의 Serial·ELF debug 검증 backend를 격리 실행합니다. """
import importlib
import importlib.util
from pathlib import Path
import sys

if __name__ == '__main__':
    source = Path(__file__).resolve().parents[1]/'nu54-builder/src/nu54_builder.py'
    spec = importlib.util.spec_from_file_location('nu54_host_check_entry',source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for stream in (sys.stdout,sys.stderr):
        if hasattr(stream,'reconfigure'):
            stream.reconfigure(encoding='utf-8',errors='backslashreplace')
    raise SystemExit(importlib.import_module(module.implementation.__name__+'.host_validation').main())
