#!/usr/bin/env python3
"""! @brief 격리된 PowerShell 5.1 설치기의 검증 로그와 종료 상태를 시험합니다. """

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PREREQUISITES_ROOT = REPOSITORY_ROOT / "tools" / "nu54-prerequisites"

FAKE_NRFUTIL_SOURCE = r"""
using System;
using System.IO;
using System.Text;

public static class FixtureNrfutil
{
    public static int Main(string[] args)
    {
        File.AppendAllText(
            Environment.GetEnvironmentVariable("NU54_TEST_NATIVE_CALLS"),
            String.Join(" ", args) + Environment.NewLine,
            new UTF8Encoding(false));
        if (args.Length == 1 && args[0] == "--version")
        {
            Console.WriteLine("nrfutil 8.2.1");
            return 0;
        }
        if (args.Length == 2 && args[0] == "sdk-manager" && args[1] == "--version")
        {
            Console.WriteLine("sdk-manager 1.16.1");
            return 0;
        }
        if ((args.Length == 3 && args[0] == "install" && args[1] == "--set") ||
            (args.Length == 7 && args[0] == "sdk-manager" &&
             args[1] == "toolchain" && args[2] == "install") ||
            (args.Length == 6 && args[0] == "sdk-manager" &&
             args[1] == "sdk" && args[2] == "install"))
        {
            Console.WriteLine("fixture native command completed");
            return 0;
        }
        Console.Error.WriteLine("Unexpected fixture nrfutil arguments");
        return 42;
    }
}
"""

FAKE_VERIFIER_SOURCE = r"""
[CmdletBinding()]
param(
    [string]$PlatformRoot,
    [string]$NcsRoot,
    [switch]$Json,
    [switch]$SkipReadyMarker
)

$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = $utf8NoBom
$OutputEncoding = $utf8NoBom
$ErrorActionPreference = 'Stop'
$readyPath = Join-Path $env:NUCODE_PREREQUISITE_STATE_ROOT 'ready.json'
$ready = $null
if (Test-Path -LiteralPath $readyPath)
{
    $ready = Get-Content -LiteralPath $readyPath -Raw -Encoding UTF8 | ConvertFrom-Json
}
$stage = if ($SkipReadyMarker)
{
    'installed-bytes'
}
elseif ($ready -and $ready.PSObject.Properties['fixture_initial_marker'])
{
    'reuse'
}
else
{
    'ready-marker'
}
$record = [ordered]@{
    stage = $stage
    ncs_root = $NcsRoot
    platform_root = $PlatformRoot
    json = [bool]$Json
    skip_ready_marker = [bool]$SkipReadyMarker
    powershell_version = $PSVersionTable.PSVersion.ToString()
}
[IO.File]::AppendAllText(
    $env:NU54_TEST_VERIFIER_CALLS,
    (($record | ConvertTo-Json -Compress) + "`n"),
    $utf8NoBom
)

$exitCode = 0
if ($stage -eq 'reuse' -and $env:NU54_TEST_SCENARIO -ne 'reuse-success')
{
    $exitCode = 7
}
elseif ($stage -eq 'installed-bytes' -and $env:NU54_TEST_SCENARIO -eq 'bytes-failure')
{
    $exitCode = 9
}
elseif ($stage -eq 'ready-marker' -and $env:NU54_TEST_SCENARIO -eq 'marker-failure')
{
    $exitCode = 11
}
if ($exitCode -ne 0)
{
    [Console]::Error.WriteLine("fixture 검증 실패: $stage")
    [Console]::Error.WriteLine("fixture 필수 file 없음: $(Join-Path $NcsRoot 'v3.4.0\nrf\west.yml')")
    exit $exitCode
}
[Console]::Out.WriteLine('{"schema_version":1,"status":"ready"}')
exit 0
"""


@unittest.skipUnless(os.name == "nt", "Windows PowerShell 5.1 설치기 통합 시험입니다.")
class M10InstallerLoggingTests(unittest.TestCase):
    """! @brief 실제 설치기와 가짜 외부 도구로 초기 실패 복구와 최종 실패를 구분합니다. """

    @classmethod
    def setUpClass(cls) -> None:
        """! @brief 네트워크 호출이 없는 임시 native nrfutil 대역을 한 번 생성합니다. """

        cls.temporary = tempfile.TemporaryDirectory(prefix="nu54-m10-logging-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.fixture_root = Path(cls.temporary.name)
        cls.powershell = (
            Path(os.environ["SystemRoot"])
            / "System32"
            / "WindowsPowerShell"
            / "v1.0"
            / "powershell.exe"
        )
        cls.compiler_root = cls.fixture_root / "compiler"
        cls.compiler_root.mkdir()
        cls.fake_nrfutil = cls.compiler_root / "nrfutil.exe"
        source = cls.compiler_root / "FixtureNrfutil.cs"
        source.write_text(FAKE_NRFUTIL_SOURCE, encoding="utf-8")
        compiler_script = cls.compiler_root / "compile-fixture.ps1"
        compiler_script.write_text(
            "param([string]$Source, [string]$Output)\n"
            "$ErrorActionPreference = 'Stop'\n"
            "Add-Type -TypeDefinition ([IO.File]::ReadAllText($Source)) "
            "-OutputAssembly $Output -OutputType ConsoleApplication\n",
            encoding="utf-8-sig",
        )
        compiler_environment = os.environ.copy()
        compiler_environment.update(
            {"TEMP": str(cls.compiler_root), "TMP": str(cls.compiler_root)}
        )
        compiled = subprocess.run(
            [
                str(cls.powershell),
                "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                "-File", str(compiler_script), "-Source", str(source),
                "-Output", str(cls.fake_nrfutil),
            ],
            cwd=cls.compiler_root,
            env=compiler_environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=60,
            check=False,
        )
        if compiled.returncode != 0:
            raise RuntimeError(
                "격리 nrfutil 대역을 컴파일하지 못했습니다: "
                + repr(compiled.stdout + compiled.stderr)
            )

    def setUp(self) -> None:
        """! @brief 사용자 SDK·설정과 겹치지 않는 설치 root 및 환경을 준비합니다. """

        self.root = self.fixture_root / self._testMethodName
        self.platform = self.root / "platform root with spaces"
        self.package_tools = self.platform / "tools" / "nu54-prerequisites"
        self.package_tools.mkdir(parents=True)
        self.user_profile = self.root / "user"
        self.local_data = self.root / "local-data"
        self.state = self.root / "state"
        self.ncs_install = self.root / "sdk root with spaces"
        self.child_temp = self.root / "temp"
        for directory in (self.user_profile, self.local_data, self.state, self.child_temp):
            directory.mkdir(parents=True)
        self.application = self.local_data / "NUCODE" / "NU54DK_Arduino_Core"
        self.nrfutil = self.application / "tools" / "nrfutil.exe"
        self.nrfutil.parent.mkdir(parents=True)
        shutil.copy2(self.fake_nrfutil, self.nrfutil)
        self.installer = self.package_tools / "install-nordic.ps1"
        shutil.copy2(PREREQUISITES_ROOT / self.installer.name, self.installer)
        shutil.copy2(
            PREREQUISITES_ROOT / "nrfutil-requirements.json",
            self.package_tools / "nrfutil-requirements.json",
        )
        pins = json.loads((PREREQUISITES_ROOT / "pins.json").read_text(encoding="utf-8"))
        pins["nrfutil"]["sha256"] = hashlib.sha256(self.nrfutil.read_bytes()).hexdigest()
        pins["nrfutil"]["url"] = (self.root / "download-not-allowed.exe").as_uri()
        (self.package_tools / "pins.json").write_text(
            json.dumps(pins) + "\n", encoding="utf-8"
        )
        (self.package_tools / "verify-nordic.ps1").write_text(
            FAKE_VERIFIER_SOURCE, encoding="utf-8-sig"
        )
        (self.state / "ready.json").write_text(
            '{"fixture_initial_marker":true,"status":"ready"}\n', encoding="utf-8"
        )
        self.native_calls = self.root / "native-calls.log"
        self.verifier_calls = self.root / "verifier-calls.jsonl"
        self.environment = os.environ.copy()
        self.environment.update(
            {
                "USERPROFILE": str(self.user_profile),
                "LOCALAPPDATA": str(self.local_data),
                "APPDATA": str(self.root / "app-data"),
                "TEMP": str(self.child_temp),
                "TMP": str(self.child_temp),
                "PATH": os.pathsep.join(
                    (str(self.powershell.parent), str(Path(os.environ["SystemRoot"]) / "System32"))
                ),
                "NUCODE_PREREQUISITE_STATE_ROOT": str(self.state),
                "NUCODE_NCS_ROOT": str(self.ncs_install / "v3.4.0"),
                "NUCODE_TOOLCHAIN_ROOT": str(self.ncs_install / "toolchains" / "dcbdc366a1"),
                "NU54_TEST_NATIVE_CALLS": str(self.native_calls),
                "NU54_TEST_VERIFIER_CALLS": str(self.verifier_calls),
            }
        )

    def run_installer(self, scenario: str) -> subprocess.CompletedProcess[str]:
        """! @brief 실제 설치기 복사본을 실행하고 stdout과 stderr를 별도로 보존합니다. """

        environment = {**self.environment, "NU54_TEST_SCENARIO": scenario}
        result = subprocess.run(
            [
                str(self.powershell),
                "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                "-File", str(self.installer),
                "-PlatformRoot", str(self.platform), "-NcsRoot", str(self.ncs_install),
            ],
            cwd=self.root,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            errors="strict",
            timeout=60,
            check=False,
        )
        self.diagnostic = f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
        logs = list((self.application / "logs").glob("prerequisites-*.log"))
        self.assertEqual(len(logs), 1, self.diagnostic)
        self.log = logs[0].read_text(encoding="utf-8-sig")
        self.calls = (
            [
                json.loads(line)
                for line in self.verifier_calls.read_text(encoding="utf-8").splitlines()
            ]
            if self.verifier_calls.exists()
            else []
        )
        for call in self.calls:
            self.assertEqual(Path(call["ncs_root"]), self.ncs_install)
            self.assertEqual(Path(call["platform_root"]), self.platform)
            self.assertTrue(call["json"])
            self.assertTrue(call["powershell_version"].startswith("5.1."), call)
        return result

    def assert_verification_log(self, stages: list[tuple[str, int]]) -> None:
        """! @brief 단계별 호출 순서·종료 code와 진단 원문을 검사합니다. """

        self.assertEqual([call["stage"] for call in self.calls], [stage for stage, _ in stages])
        positions = []
        for stage, exit_code in stages:
            marker = f"verification={stage} exit_code={exit_code}"
            self.assertEqual(self.log.count(marker), 1, self.log)
            positions.append(self.log.index(marker))
            if exit_code:
                self.assertIn(f"fixture 검증 실패: {stage}", self.log)
                self.assertIn("fixture 필수 file 없음:", self.log)
        self.assertEqual(positions, sorted(positions), self.log)

    def test_stale_marker_recovers_without_failure_on_stderr(self) -> None:
        """! @brief 초기 marker 실패는 로그에 남기고 복구 성공을 최종 실패처럼 출력하지 않습니다. """

        result = self.run_installer("stale-success")
        self.assertEqual(result.returncode, 0, self.diagnostic)
        self.assertEqual(result.stderr, "", self.diagnostic)
        self.assertIn("Nordic prerequisite installation PASS.", result.stdout)
        self.assertIn("복구 설치를 진행합니다", result.stdout)
        self.assertNotIn("fixture 검증 실패:", result.stdout)
        self.assert_verification_log([("reuse", 7), ("installed-bytes", 0), ("ready-marker", 0)])
        ready = json.loads((self.state / "ready.json").read_text(encoding="utf-8"))
        self.assertEqual(ready["status"], "ready")
        self.assertNotIn("fixture_initial_marker", ready)
        self.assertFalse((self.state / "installing.json").exists())
        self.assertFalse((self.state / "incomplete.json").exists())
        native = self.native_calls.read_text(encoding="utf-8")
        self.assertIn("sdk-manager toolchain install", native)
        self.assertIn("sdk-manager sdk install v3.4.0", native)

    def assert_final_failure(self, scenario: str, phase: str, stages: list[tuple[str, int]]) -> None:
        """! @brief 복구 중 최종 검증 실패가 exit 1과 incomplete marker로 보존되는지 검사합니다. """

        result = self.run_installer(scenario)
        self.assertEqual(result.returncode, 1, self.diagnostic)
        self.assertNotIn("Nordic prerequisite installation PASS.", result.stdout)
        self.assertIn("Nordic prerequisite installation failed", result.stderr)
        self.assertIn(f"fixture 검증 실패: {stages[-1][0]}", result.stderr)
        self.assertNotIn("fixture 검증 실패: reuse", result.stderr)
        self.assert_verification_log(stages)
        incomplete = json.loads((self.state / "incomplete.json").read_text(encoding="utf-8"))
        self.assertEqual(incomplete["status"], "incomplete")
        self.assertEqual(incomplete["phase"], phase)
        self.assertIn(f"fixture 검증 실패: {stages[-1][0]}", incomplete["error"])

    def test_final_byte_failure_is_not_reported_as_success(self) -> None:
        """! @brief 설치 byte 검증 실패를 초기 복구 실패와 구분해 최종 실패로 반환합니다. """

        self.assert_final_failure(
            "bytes-failure", "설치 byte와 revision 최종 검증",
            [("reuse", 7), ("installed-bytes", 9)],
        )
        self.assertFalse((self.state / "ready.json").exists())

    def test_final_marker_failure_is_not_reported_as_success(self) -> None:
        """! @brief 완료 marker 재검증 실패도 PASS 없이 incomplete 상태로 반환합니다. """

        self.assert_final_failure(
            "marker-failure", "완료 marker 재검증",
            [("reuse", 7), ("installed-bytes", 0), ("ready-marker", 11)],
        )

    def test_valid_marker_reuses_without_native_install_commands(self) -> None:
        """! @brief 유효한 marker는 한 번만 검증하고 native 설치 명령 없이 재사용합니다. """

        result = self.run_installer("reuse-success")
        self.assertEqual(result.returncode, 0, self.diagnostic)
        self.assertEqual(result.stderr, "", self.diagnostic)
        self.assertIn("이미 검증된 Nordic prerequisite를 재사용합니다.", result.stdout)
        self.assertNotIn("복구 설치를 진행합니다", result.stdout)
        self.assert_verification_log([("reuse", 0)])
        self.assertFalse(self.native_calls.exists())
        self.assertFalse((self.state / "installing.json").exists())
        self.assertFalse((self.state / "incomplete.json").exists())

    def test_fresh_install_verifies_bytes_and_new_marker(self) -> None:
        """! @brief 완료 marker가 없는 최초 설치도 두 최종 검증 후 성공합니다. """

        (self.state / "ready.json").unlink()
        result = self.run_installer("fresh-success")
        self.assertEqual(result.returncode, 0, self.diagnostic)
        self.assertEqual(result.stderr, "", self.diagnostic)
        self.assertIn("Nordic prerequisite installation PASS.", result.stdout)
        self.assertNotIn("복구 설치를 진행합니다", result.stdout)
        self.assert_verification_log([("installed-bytes", 0), ("ready-marker", 0)])
        ready = json.loads((self.state / "ready.json").read_text(encoding="utf-8"))
        self.assertEqual(ready["status"], "ready")
        self.assertFalse((self.state / "installing.json").exists())
        self.assertFalse((self.state / "incomplete.json").exists())

    def test_missing_child_powershell_fails_closed(self) -> None:
        """! @brief 검증 subprocess를 시작하지 못하면 성공으로 판정하지 않습니다. """

        (self.state / "ready.json").unlink()
        self.environment["PATH"] = str(self.child_temp)
        result = self.run_installer("missing-powershell")
        self.assertEqual(result.returncode, 1, self.diagnostic)
        self.assertNotIn("Nordic prerequisite installation PASS.", result.stdout)
        self.assertIn("Nordic prerequisite installation failed", result.stderr)
        self.assertIn("powershell.exe", result.stderr)
        self.assertEqual(self.calls, [])
        self.assertNotIn("verification=installed-bytes exit_code=0", self.log)
        self.assertFalse((self.state / "ready.json").exists())
        incomplete = json.loads((self.state / "incomplete.json").read_text(encoding="utf-8"))
        self.assertEqual(incomplete["status"], "incomplete")
        self.assertEqual(incomplete["phase"], "설치 byte와 revision 최종 검증")
        self.assertIn("powershell.exe", incomplete["error"])


if __name__ == "__main__":
    unittest.main()
