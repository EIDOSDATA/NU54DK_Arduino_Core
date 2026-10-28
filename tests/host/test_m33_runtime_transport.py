#!/usr/bin/env python3
"""! @brief runtime의 명시 transport 선택과 read-only attach 경계를 장치 없이 검증합니다. """
from __future__ import annotations

import builtins
from contextlib import contextmanager, nullcontext
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
for directory in (ROOT / "tools/bluetooth", ROOT / "tests/hil/nu54dk"):
    sys.path.insert(0, str(directory))

import m33_diagnostics as diagnostics
import m33_probe_transport as transport
import m33_profile_idle_fixture as idle
import m33_sdk_risk_common as risk
import m32_regression_soak_run as soak


JLINK = {"kind": "jlink-swd", "fixture_sha256": "a" * 64,
         "dll_sha256": "b" * 64, "board": "nrf54l15dk"}


class RuntimeTransportTests(unittest.TestCase):
    """! @brief 명시 fixture가 없을 때의 기존 DAP 동작과 J-Link fail-closed를 검사합니다. """

    def test_jlink_read_only_session_closes_selected_exact_probe(self):
        """! @brief J-Link read-only 사용자는 generic discovery 없이 exact backend를 닫습니다. """
        probe = SimpleNamespace(unique_id="12345")
        session = SimpleNamespace(target=object())
        events = []

        @contextmanager
        def selected_session(selected):
            """! @brief 선택 probe와 context 종료를 기록합니다. """
            self.assertIs(probe, selected)
            events.append("open")
            try:
                yield session
            finally:
                events.append("close")

        backend = SimpleNamespace(discover=lambda: ([probe], []), session=selected_session)
        with mock.patch.object(transport, "descriptor", return_value=JLINK), \
                mock.patch.object(diagnostics, "create_preparation_backend", return_value=backend), \
                mock.patch.object(diagnostics, "private_debug_output", side_effect=nullcontext), \
                mock.patch.dict(sys.modules, {"pyocd.core.helpers": None}):
            with idle.read_only_session("12345") as actual:
                self.assertIs(session, actual)
        self.assertEqual(["open", "close"], events)

    def test_jlink_read_only_session_rejects_absent_or_duplicate_probe(self):
        """! @brief 대상이 없거나 중복이면 session을 시작하지 않습니다. """
        for probes in ([], [SimpleNamespace(unique_id="12345")] * 2):
            with self.subTest(count=len(probes)):
                backend = SimpleNamespace(discover=lambda: (probes, []), session=mock.Mock())
                with mock.patch.object(transport, "descriptor", return_value=JLINK), \
                        mock.patch.object(diagnostics, "create_preparation_backend", return_value=backend), \
                        mock.patch.object(diagnostics, "private_debug_output", side_effect=nullcontext):
                    with self.assertRaisesRegex(ValueError, "exact read-only"):
                        with idle.read_only_session("12345"):
                            self.fail("unmapped session opened")
                backend.session.assert_not_called()

    def test_jlink_read_only_close_failure_is_not_hidden(self):
        """! @brief backend close 실패를 read-only PASS로 감추지 않습니다. """
        @contextmanager
        def failing_session(_probe):
            """! @brief 종료 실패를 주입합니다. """
            yield object()
            raise RuntimeError("close failed")

        backend = SimpleNamespace(discover=lambda: ([SimpleNamespace(unique_id="12345")], []),
                                  session=failing_session)
        with mock.patch.object(transport, "descriptor", return_value=JLINK), \
                mock.patch.object(diagnostics, "create_preparation_backend", return_value=backend), \
                mock.patch.object(diagnostics, "private_debug_output", side_effect=nullcontext):
            with self.assertRaisesRegex(RuntimeError, "close failed"):
                with idle.read_only_session("12345"):
                    pass

    def test_default_read_only_attach_keeps_cmsis_guards(self):
        """! @brief 기본 경로의 attach·unlock 금지·resume 금지·v2 설정을 보존합니다. """
        session = nullcontext()
        connect = mock.Mock(return_value=session)
        helpers = ModuleType("pyocd.core.helpers")
        helpers.ConnectHelper = SimpleNamespace(session_with_chosen_probe=connect)
        with mock.patch.object(transport, "descriptor", return_value={"kind": "cmsis-dap-v2"}), \
                mock.patch.object(diagnostics, "create_preparation_backend") as selected, \
                mock.patch.dict(sys.modules, {"pyocd.core.helpers": helpers}):
            with idle.read_only_session("dap-uid") as actual:
                self.assertIs(session, actual)
        selected.assert_not_called()
        connect.assert_called_once_with(
            unique_id="dap-uid", target_override="nrf54l", frequency=500000,
            options={"connect_mode": "attach", "auto_unlock": False,
                     "resume_on_disconnect": False, "cmsis_dap.limit_packets": True,
                     "cmsis_dap.prefer_v1": False})

    def test_jlink_preload_does_not_import_generic_pyocd(self):
        """! @brief 선택 backend 설치 전에 generic pyOCD DLL discovery를 유발하지 않습니다. """
        original_import = builtins.__import__

        def guarded_import(name, *args, **kwargs):
            """! @brief legacy pyOCD 사전 import만 금지합니다. """
            if name == "pyocd":
                self.fail("generic pyOCD import before selected backend")
            return original_import(name, *args, **kwargs)

        for module in (risk, soak):
            with self.subTest(module=module.__name__), \
                    mock.patch.object(transport, "descriptor", return_value=JLINK), \
                    mock.patch.object(transport, "ensure_pyocd_available") as ensure, \
                    mock.patch.object(builtins, "__import__", side_effect=guarded_import):
                module._load_pyocd_site_packages()
                ensure.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
