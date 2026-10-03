#!/usr/bin/env python3
"""! @brief 고정 NCS toolchain의 pyOCD를 격리 Python에서 실행합니다. """

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import runpy
import sys


TOOLCHAIN_BUNDLE_ID = "dcbdc366a1"
SITE_PACKAGES_ENVIRONMENT = "NUCODE_PYOCD_SITE_PACKAGES"


def _is_pyocd_site_packages(path: Path) -> bool:
    """! @brief 지정 경로가 pyOCD package를 포함하는지 검사합니다. """
    return path.is_dir() and (path / "pyocd" / "__init__.py").is_file()


def _resolve_site_packages() -> Path | None:
    """! @brief 명시 경로 또는 고정 Windows NCS bundle에서 pyOCD를 찾습니다. """
    explicit = os.environ.get(SITE_PACKAGES_ENVIRONMENT)
    if explicit:
        candidate = Path(explicit).resolve()
        if not _is_pyocd_site_packages(candidate):
            raise RuntimeError(
                f"{SITE_PACKAGES_ENVIRONMENT}에 pyOCD package가 없습니다: {candidate}"
            )
        return candidate

    if importlib.util.find_spec("pyocd") is not None:
        return None

    candidate = (
        Path("C:/ncs/toolchains")
        / TOOLCHAIN_BUNDLE_ID
        / "opt/bin/Lib/site-packages"
    )
    if _is_pyocd_site_packages(candidate):
        return candidate
    raise RuntimeError(
        "pyOCD를 찾지 못했습니다. "
        f"{SITE_PACKAGES_ENVIRONMENT}에 site-packages 경로를 지정하십시오."
    )


def _prefer_v1_requested(arguments: list[str]) -> bool:
    """! @brief probe 열거 전에 CMSIS-DAP V1 강제 option을 감지합니다. """
    for index, argument in enumerate(arguments[:-1]):
        if argument == "-O" and arguments[index + 1].casefold() == (
            "cmsis_dap.prefer_v1=true"
        ):
            return True
    return False


def main() -> int:
    """! @brief pyOCD module을 현재 인자 그대로 실행합니다. """
    try:
        site_packages = _resolve_site_packages()
    except RuntimeError as error:
        print(error, file=sys.stderr)
        return 2
    if site_packages is not None:
        sys.path.insert(0, str(site_packages))
    option_session = None
    if _prefer_v1_requested(sys.argv[1:]):
        from pyocd.core.session import Session

        ## @brief pyOCD probe 선택이 session 생성보다 먼저라 열거용 session을 유지합니다.
        option_session = Session(None, options={"cmsis_dap.prefer_v1": True})
    runpy.run_module("pyocd", run_name="__main__")
    del option_session
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
