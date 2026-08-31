#!/usr/bin/env python3
"""! @brief M15 System OFF HIL parser suite를 공통 host gate에 연결합니다. """

from __future__ import annotations

import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "hil" / "nu54dk" / "test_m15_system_off.py"
MODULE_SPEC = importlib.util.spec_from_file_location("nu54_m15_system_off_hil", MODULE_PATH)
assert MODULE_SPEC and MODULE_SPEC.loader
MODULE = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(MODULE)
M15SystemOffHilTests = MODULE.M15SystemOffHilTests


__all__ = ["M15SystemOffHilTests"]
