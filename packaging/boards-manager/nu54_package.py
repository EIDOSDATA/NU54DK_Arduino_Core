#!/usr/bin/env python3
"""! @brief 신뢰된 설치 경로에서만 내부 package를 로드하는 패키저 CLI 진입점입니다. """
from __future__ import annotations
import hashlib as _hashlib
import importlib.util as _importlib_util
from pathlib import Path as _Path
import re as _re
import sys as _sys


## @brief -I에서도 CWD·PYTHONPATH 없이 같은 설치본의 package를 명시적으로 로드합니다.
def _load_implementation():
    directory = _Path(__file__).resolve().parent / "nu54_package_impl"
    identity = str(directory) + ":" + __name__
    name = "_nu54_package_runtime_" + _hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
    base_name = name
    sequence = 0
    while name in _sys.modules:
        sequence += 1
        name = f"{base_name}_{sequence}"
    spec = _importlib_util.spec_from_file_location(
        name, directory / "__init__.py", submodule_search_locations=[str(directory)]
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("[NU54:E_PACKAGE_PACKAGE] 내부 package package를 로드할 수 없습니다.")
    module = _importlib_util.module_from_spec(spec)
    _sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


implementation = _load_implementation()
for _name in implementation.__all__:
    globals()[_name] = getattr(implementation, _name)


## @brief 기존 M27의 로컬 candidate 확장을 단일 model과 호환 export에 반영합니다.
def configure_release_candidates(versions):
    model = implementation.model
    model.RELEASE_CANDIDATE_VERSIONS = tuple(versions)
    model.PACKAGE_VERSIONS = model.SUPPORTED_VERSIONS + model.RELEASE_CANDIDATE_VERSIONS + model.STABLE_VERSIONS
    model.WINDOWS_SAFE_VERSIONS = (
        model.FAILED_M10_PREVIEW_VERSIONS + model.SAFE_PREVIEW_VERSIONS
        + model.RELEASE_CANDIDATE_VERSIONS + model.STABLE_VERSIONS
    )
    for name in ("RELEASE_CANDIDATE_VERSIONS", "PACKAGE_VERSIONS", "WINDOWS_SAFE_VERSIONS"):
        globals()[name] = getattr(model, name)
        setattr(implementation, name, getattr(model, name))


## @brief 공개 전 stable 후보를 현재 프로세스에만 고정해 패키징합니다.
def configure_unpublished_stable(version, commit):
    """! @brief 영구 allowlist를 바꾸지 않고 승인 전 stable 후보 하나를 구성합니다. """
    model = implementation.model
    if version in model.STABLE_VERSIONS or version in model.PACKAGE_VERSIONS:
        raise model.PackageError(f"이미 등록된 package version입니다: {version}")
    if not _re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
        raise model.PackageError(f"stable version 형식이 유효하지 않습니다: {version}")
    if not _re.fullmatch(r"[0-9a-f]{40}", commit):
        raise model.PackageError("stable 후보 commit은 40자리 소문자 SHA-1이어야 합니다.")

    model.STABLE_VERSIONS = model.STABLE_VERSIONS + (version,)
    model.STABLE_RELEASE_COMMITS[version] = commit
    model.STABLE_LEGAL_REVIEW_STATUSES[version] = model.LEGAL_REVIEW_REQUIRED
    model.PACKAGE_VERSIONS = (
        model.SUPPORTED_VERSIONS
        + model.RELEASE_CANDIDATE_VERSIONS
        + model.STABLE_VERSIONS
    )
    model.WINDOWS_SAFE_VERSIONS = (
        model.FAILED_M10_PREVIEW_VERSIONS
        + model.SAFE_PREVIEW_VERSIONS
        + model.RELEASE_CANDIDATE_VERSIONS
        + model.STABLE_VERSIONS
    )
    implementation.channels.STABLE_VERSIONS = model.STABLE_VERSIONS
    for name in (
        "STABLE_VERSIONS",
        "STABLE_RELEASE_COMMITS",
        "STABLE_LEGAL_REVIEW_STATUSES",
        "PACKAGE_VERSIONS",
        "WINDOWS_SAFE_VERSIONS",
    ):
        globals()[name] = getattr(model, name)
        setattr(implementation, name, getattr(model, name))


if __name__ == "__main__":
    ## @brief -I가 환경 변수를 무시해도 CLI 도움말·진단을 UTF-8로 출력합니다.
    for _stream in (_sys.stdout, _sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8")
    raise SystemExit(main())
