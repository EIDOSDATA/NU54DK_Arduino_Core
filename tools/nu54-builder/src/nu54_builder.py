#!/usr/bin/env python3
"""! @brief 신뢰된 설치 경로에서만 내부 builder를 로드하는 기존 CLI 진입점입니다. """
from __future__ import annotations
import hashlib as _hashlib
import importlib.util as _importlib_util
from pathlib import Path as _Path
import sys as _sys


## @brief -I에서도 CWD·PYTHONPATH 없이 같은 설치본의 package를 명시적으로 로드합니다.
def _load_implementation():
    directory = _Path(__file__).resolve().parent / "nu54_builder_impl"
    identity = str(directory) + ":" + __name__
    name = "_nu54_builder_runtime_" + _hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
    spec = _importlib_util.spec_from_file_location(
        name, directory / "__init__.py", submodule_search_locations=[str(directory)]
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("[NU54:E_BUILDER_PACKAGE] 내부 builder package를 로드할 수 없습니다.")
    module = _importlib_util.module_from_spec(spec)
    _sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


implementation = _load_implementation()
for _name in implementation.__all__:
    globals()[_name] = getattr(implementation, _name)

if __name__ == "__main__":
    raise SystemExit(main())
