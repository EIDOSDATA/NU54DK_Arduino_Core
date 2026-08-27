#!/usr/bin/env python3
"""! @brief M10 clean Windows SSH 실행기의 정적 안전 계약을 검증합니다. """

from __future__ import annotations

import base64
import json
from pathlib import Path
import subprocess
import unittest
import uuid


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
M10_ROOT = REPOSITORY_ROOT / "tools" / "remote-windows" / "m10"
LOCAL_RUNNER = M10_ROOT / "invoke-m10-clean-windows.ps1"
TARGET_RUNNER = M10_ROOT / "run-m10-target.ps1"


class M10RemoteRunnerContractTests(unittest.TestCase):
    """! @brief package 설치와 원격 증거 수집 계약이 fail-closed인지 검증합니다. """

    @classmethod
    def setUpClass(cls) -> None:
        """! @brief 두 PowerShell 실행기 원문을 한 번만 읽습니다. """

        cls.local_text = LOCAL_RUNNER.read_text(encoding="utf-8")
        cls.target_bytes = TARGET_RUNNER.read_bytes()
        cls.target_text = cls.target_bytes.decode("ascii")

    def invoke_probe_parser(self, output: str) -> subprocess.CompletedProcess[str]:
        """! @brief target의 실제 probe parser 함수만 분리해 sample output에 실행합니다. """

        encoded_output = output.replace("'", "''")
        escaped_path = str(TARGET_RUNNER).replace("'", "''")
        command = (
            "$tokens=$null;$errors=$null;"
            f"$ast=[System.Management.Automation.Language.Parser]::ParseFile('{escaped_path}',"
            "[ref]$tokens,[ref]$errors);"
            "$function=$ast.Find({param($node)"
            "$node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and "
            "$node.Name -eq 'Get-PyOcdProbeCount'},$true);"
            "Invoke-Expression $function.Extent.Text;"
            f"$text='{encoded_output}';"
            "try{$count=Get-PyOcdProbeCount -Text $text;Write-Output \"COUNT=$count\"}"
            "catch{[Console]::Error.WriteLine($_.Exception.Message);exit 2}"
        )
        return subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                command,
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )

    def invoke_uninstall_recovery(
        self, initially_installed: bool
    ) -> subprocess.CompletedProcess[str]:
        """! @brief uninstall 함수에 설치/제거 상태 전이를 주입해 직접 실행합니다. """

        escaped_path = str(TARGET_RUNNER).replace("'", "''")
        initial_value = "$true" if initially_installed else "$false"
        command = (
            "$tokens=$null;$errors=$null;"
            f"$ast=[System.Management.Automation.Language.Parser]::ParseFile('{escaped_path}',"
            "[ref]$tokens,[ref]$errors);"
            "$function=$ast.Find({param($node)"
            "$node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and "
            "$node.Name -eq 'Ensure-Nu54CoreAbsent'},$true);"
            "Invoke-Expression $function.Extent.Text;"
            f"$script:states=New-Object 'System.Collections.Generic.Queue[bool]';"
            f"$script:states.Enqueue({initial_value});$script:states.Enqueue($false);"
            "$script:uninstallCalls=0;"
            "function Test-Nu54CoreInstalled{return $script:states.Dequeue()};"
            "function Invoke-Arduino{$script:uninstallCalls++;return $null};"
            "function Add-RunLog{};"
            "try{$result=Ensure-Nu54CoreAbsent;"
            "$output=[ordered]@{result=$result;calls=$script:uninstallCalls};"
            "$output|ConvertTo-Json -Compress}"
            "catch{[Console]::Error.WriteLine($_.Exception.Message);exit 2}"
        )
        return subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                command,
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )

    def script_function_command(
        self, script: Path, names: tuple[str, ...], body: str
    ) -> str:
        """! @brief 지정 script 함수 AST와 시험 본문을 하나의 PowerShell command로 만듭니다. """

        escaped_path = str(script).replace("'", "''")
        quoted_names = ",".join(f"'{name}'" for name in names)
        return (
            "$tokens=$null;$errors=$null;"
            f"$ast=[System.Management.Automation.Language.Parser]::ParseFile('{escaped_path}',"
            "[ref]$tokens,[ref]$errors);"
            f"foreach($name in @({quoted_names})){{"
            "$function=$ast.Find({param($node)"
            "$node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and "
            "$node.Name -eq $name},$true);"
            "Invoke-Expression $function.Extent.Text};"
            + body
        )

    def target_function_command(self, names: tuple[str, ...], body: str) -> str:
        """! @brief 지정 target 함수 AST와 시험 본문을 하나의 PowerShell command로 만듭니다. """

        return self.script_function_command(TARGET_RUNNER, names, body)

    def invoke_script_functions(
        self, script: Path, names: tuple[str, ...], body: str
    ) -> subprocess.CompletedProcess[str]:
        """! @brief 지정 script 함수 AST만 로드해 독립적인 runtime 계약을 실행합니다. """

        command = self.script_function_command(script, names, body)
        return subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                command,
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )

    def invoke_target_functions(
        self, names: tuple[str, ...], body: str
    ) -> subprocess.CompletedProcess[str]:
        """! @brief 지정 target 함수 AST만 로드해 독립적인 runtime 계약을 실행합니다. """

        return self.invoke_script_functions(TARGET_RUNNER, names, body)

    def test_powershell_51_parser_accepts_both_scripts(self) -> None:
        """! @brief Windows PowerShell parser가 두 파일을 오류 없이 해석합니다. """

        for script in (LOCAL_RUNNER, TARGET_RUNNER):
            with self.subTest(script=script.name):
                escaped_path = str(script).replace("'", "''")
                parser = (
                    "$tokens=$null;$errors=$null;"
                    "[System.Management.Automation.Language.Parser]::ParseFile("
                    f"'{escaped_path}',[ref]$tokens,[ref]$errors)|Out-Null;"
                    "$errors|ForEach-Object{[Console]::Error.WriteLine($_.Message)};"
                    "if($errors.Count){exit 1}"
                )
                completed = subprocess.run(
                    [
                        "powershell.exe",
                        "-NoProfile",
                        "-NonInteractive",
                        "-Command",
                        parser,
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_target_runner_is_ascii_only(self) -> None:
        """! @brief 대상 PC 전송 파일에 code page 의존 문자가 없음을 검증합니다. """

        self.assertTrue(self.target_bytes)
        self.assertTrue(all(value < 128 for value in self.target_bytes))
        self.assertIn(
            "$nonAsciiBytes = @(\n    [IO.File]::ReadAllBytes($targetRunner)",
            self.local_text,
        )

    def test_public_index_uses_repository_owner(self) -> None:
        """! @brief 기본 index가 공개 EIDOSDATA 저장소를 가리키는지 검증합니다. """

        expected = (
            "https://raw.githubusercontent.com/EIDOSDATA/"
            "NU54DK_Arduino_Core/main/package_nucode_nu54dk_preview_index.json"
        )
        self.assertIn(expected, self.local_text)
        self.assertNotIn("Nucode01/NU54DK_Arduino_Core", self.local_text)

    def test_ssh_authentication_fails_closed(self) -> None:
        """! @brief SSH가 password fallback과 미확인 host key를 허용하지 않습니다. """

        for required in (
            "BatchMode=yes",
            "IdentitiesOnly=yes",
            "StrictHostKeyChecking=yes",
            "UserKnownHostsFile=",
            "ServerAliveInterval=30",
            "ServerAliveCountMax=4",
        ):
            self.assertIn(required, self.local_text)
        self.assertNotIn("StrictHostKeyChecking=no", self.local_text)
        self.assertNotIn("password=", self.local_text.lower())

    def test_target_uses_isolated_arduino_directories(self) -> None:
        """! @brief run별 data, downloads, sketchbook과 build를 분리합니다. """

        for marker in (
            "arduino-data",
            "downloads",
            "sketchbook",
            "arduino-cli.yaml",
            "--config-file",
            "--build-path",
        ):
            self.assertIn(marker, self.target_text)
        self.assertNotIn("git clone", self.target_text.lower())
        self.assertNotIn("--build-cache-path", self.target_text)

    def test_complete_lifecycle_is_checkpointed(self) -> None:
        """! @brief 설치부터 uninstall 및 reinstall까지 모든 단계 이름을 고정합니다. """

        ordered_steps = (
            "preflight",
            "update_index",
            "install_initial",
            "board_details_initial",
            "blink_cold_compile",
            "blink_warm_compile",
            "probe_and_upload",
            "upgrade_latest",
            "downgrade_initial",
            "uninstall_preserves_ncs",
            "reinstall_latest",
        )
        positions = [self.target_text.index(f"'{name}'") for name in ordered_steps]
        self.assertEqual(positions, sorted(positions))
        for marker in (
            "Resume fingerprint does not match",
            "state.json",
            "Save-State",
            "Save-Evidence",
        ):
            self.assertIn(marker, self.target_text)

    def test_nordic_verifier_is_invoked_from_installed_platform(self) -> None:
        """! @brief 설치된 core 내부 verifier를 JSON mode로 명시 실행합니다. """

        for marker in (
            "tools\\nu54-prerequisites\\verify-nordic.ps1",
            "-PlatformRoot",
            "-NcsRoot",
            "-Json",
            "toolchain_bundle_id",
            "pins_sha256",
        ):
            self.assertIn(marker, self.target_text)

    def test_versions_and_post_install_are_explicit(self) -> None:
        """! @brief preview version과 post-install 실행을 암묵적으로 선택하지 않습니다. """

        for marker in (
            "0.0.94",
            "0.0.95",
            "--run-post-install",
            "post-install-direct-",
            "@('/d', '/c', 'call', $postInstall)",
            "core', 'uninstall', 'nucode:zephyr",
            "Shared NCS was removed by core uninstall",
            "Shared NCS changed during core uninstall",
        ):
            self.assertIn(marker, self.target_text)

    def test_failed_post_install_can_be_retried_for_an_installed_core(self) -> None:
        """! @brief CLI가 설치됨으로 남긴 core도 post-install을 직접 재실행합니다. """

        fixture = "nu54-post-install-" + uuid.uuid4().hex
        body = (
            f"$root=Join-Path ([IO.Path]::GetTempPath()) '{fixture}';"
            "New-Item -ItemType Directory -Path $root -Force|Out-Null;"
            "Set-Content -LiteralPath (Join-Path $root 'post_install.bat') -Value '@exit /b 0';"
            "$script:InstallTimeoutSeconds=30;$script:directCalls=0;"
            "function Invoke-Arduino{param($Label,$Arguments,$TimeoutSeconds);return $null};"
            "function Assert-CoreVersion{param($Version)};"
            "function Get-PlatformRoot{param($Version);return $root};"
            "function Invoke-NativeCommand{param($FilePath,$Arguments,$Label,$TimeoutSeconds);"
            "$script:directCalls++;return [pscustomobject]@{exit_code=0}};"
            "function Invoke-NordicVerification{param($Version);"
            "return [pscustomobject]@{pins_sha256='fixture'}};"
            "function Get-InstalledReleaseIdentity{param($Version);"
            "return [pscustomobject]@{prerequisites_pins_sha256='fixture'}};"
            "try{$result=Install-CoreVersion -Version '0.0.94';"
            "Write-Output ('DIRECT_CALLS='+$script:directCalls);"
            "Write-Output ('DIRECT_RESULT='+$result.post_install_direct)}"
            "finally{Remove-Item -LiteralPath $root -Recurse -Force -ErrorAction SilentlyContinue}"
        )
        completed = self.invoke_target_functions(("Install-CoreVersion",), body)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("DIRECT_CALLS=1", completed.stdout)
        self.assertIn("DIRECT_RESULT=True", completed.stdout)

    def test_probe_identity_and_credentials_are_redacted(self) -> None:
        """! @brief probe UID와 자격 증명 형태를 두 실행기에서 제거합니다. """

        for text in (self.local_text, self.target_text):
            self.assertIn("<redacted-device-id>", text)
            self.assertIn("<redacted>", text)
            self.assertIn("[0-9a-f]{16,}", text)
        self.assertNotIn("IdentityFile = $IdentityFile", self.local_text)

    def test_probe_is_required_unless_explicitly_relaxed(self) -> None:
        """! @brief 기본 HIL은 probe를 요구하고 조사 실행만 명시적으로 생략합니다. """

        for marker in (
            "[switch]$AllowMissingProbe",
            "require_probe = (-not $AllowMissingProbe.IsPresent)",
        ):
            self.assertIn(marker, self.local_text)
        for marker in (
            "-Name 'require_probe' -DefaultValue $true",
            "if ($script:RequireProbe)",
            "probe is required but no pyOCD probe is attached",
            "skipped-no-probe",
        ):
            self.assertIn(marker, self.target_text)

    def test_pyocd_api_probe_count_accepts_only_one_integer(self) -> None:
        """! @brief pyOCD API의 비식별 count 한 개만 안전하게 해석합니다. """

        for sample, expected in (("0\r\n", 0), ("1\n", 1), ("2", 2)):
            with self.subTest(expected=expected):
                result = self.invoke_probe_parser(sample)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(f"COUNT={expected}", result.stdout)

    def test_pyocd_api_probe_count_rejects_ambiguous_output(self) -> None:
        """! @brief 빈 값, 음수와 부가 출력이 섞인 count를 fail-closed 처리합니다. """

        ambiguous_samples = (
            "",
            "-1\n",
            "warning only\n",
            "1\nwarning\n",
            "1 2\n",
        )
        for sample in ambiguous_samples:
            with self.subTest(sample=sample[:30]):
                result = self.invoke_probe_parser(sample)
                self.assertNotEqual(result.returncode, 0)

    def test_multi_probe_failure_preserves_count_in_evidence(self) -> None:
        """! @brief 선택 없는 multi-probe 실패 evidence에 실제 count와 차단 사유를 남깁니다. """

        for marker in (
            "probe_count = $probeCount",
            "blocked-ambiguous-probe",
            "no explicit probe was selected",
            "Exception.Data.Contains('nu54_result')",
        ):
            self.assertIn(marker, self.target_text)

    def test_pyocd_api_count_uses_utf8_and_ten_uploads(self) -> None:
        """! @brief 한국어 Windows에서도 probe 열거와 RC 10회 HIL이 재현되는지 고정합니다. """

        for marker in (
            "$startInfo.EnvironmentVariables['PYTHONUTF8'] = '1'",
            "$startInfo.EnvironmentVariables['PYTHONIOENCODING'] = 'utf-8'",
            "from pyocd.core.helpers import ConnectHelper",
            "$uploadAttempts = 10",
            "upload_attempts = $uploadAttempts",
        ):
            self.assertIn(marker, self.target_text)

    def test_uninstall_crash_window_recovers_when_core_is_already_absent(self) -> None:
        """! @brief uninstall 뒤 checkpoint 전 중단된 재개가 재삭제 없이 성공합니다. """

        result = self.invoke_uninstall_recovery(initially_installed=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["calls"], 0)
        self.assertFalse(payload["result"]["core_was_installed"])
        self.assertFalse(payload["result"]["uninstall_invoked"])
        self.assertTrue(payload["result"]["recovered_after_prior_uninstall"])

    def test_idempotent_uninstall_runs_once_when_core_is_installed(self) -> None:
        """! @brief 정상 설치 상태에서는 uninstall을 정확히 한 번 호출합니다. """

        result = self.invoke_uninstall_recovery(initially_installed=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["calls"], 1)
        self.assertTrue(payload["result"]["core_was_installed"])
        self.assertTrue(payload["result"]["uninstall_invoked"])
        self.assertFalse(payload["result"]["recovered_after_prior_uninstall"])

    def test_arduino_cli_15_uses_supported_json_flags(self) -> None:
        """! @brief 대상 Arduino CLI 1.5 계열이 지원하는 global JSON flag를 사용합니다. """

        self.assertIn("'version', '--json'", self.target_text)
        self.assertIn("'core', 'list', '--json'", self.target_text)
        self.assertIn("'board', 'details', '--fqbn', $script:Fqbn, '--json'", self.target_text)
        self.assertNotIn("--format", self.target_text)

    def test_resume_fingerprint_pins_runner_cli_index_and_archives(self) -> None:
        """! @brief mutable main URL이나 실행기 교체가 기존 PASS checkpoint와 섞이지 않습니다. """

        for marker in (
            "schema_version = 2",
            "actual_runner_sha256 = $script:ActualRunnerSha256",
            "actual_arduino_cli_sha256 = $script:ActualArduinoCliSha256",
            "index_sha256 = $script:ExpectedIndexSha256",
            "archives = $script:ArchiveIdentities",
            "Cached package index SHA-256 does not match",
            "Resume fingerprint does not match",
        ):
            self.assertIn(marker, self.target_text)
        for marker in (
            "target_runner_sha256 = $targetRunnerSha256",
            "index_sha256 = $indexIdentity.sha256",
            "archives = $indexIdentity.archives",
            "package-index.snapshot.json",
        ):
            self.assertIn(marker, self.local_text)

    def test_clean_baseline_requires_absent_ncs_and_prerequisite_state(self) -> None:
        """! @brief fresh M10 run은 기존 Nordic 설치를 clean 설치로 오인하지 않습니다. """

        for marker in (
            "initial_environment = $script:InitialEnvironment",
            "ncs_exists = (Test-Path",
            "prerequisite_state_exists = (Test-Path",
            "ready_marker_exists = (Test-Path",
            "Clean Windows baseline already contains NCS",
        ):
            self.assertIn(marker, self.target_text)

    def test_exact_arduino_cli_identity_is_asserted_and_recorded(self) -> None:
        """! @brief version 문자열뿐 아니라 commit과 실행 파일 hash도 고정합니다. """

        for marker in (
            "1.5.2-rc.1",
            "fef6e48df",
            "ba1890afcfc08524f76191b5cc801b0779cb25e81a5e6693eb0e26b50a3f3538",
            "ExpectedArduinoCliVersion",
            "ExpectedArduinoCliCommit",
        ):
            self.assertIn(marker, self.local_text)
        for marker in (
            "$cliIdentity.VersionString -ne $script:ExpectedArduinoCliVersion",
            "$cliIdentity.Commit -ne $script:ExpectedArduinoCliCommit",
            "$script:ActualArduinoCliSha256 -ne $script:ExpectedArduinoCliSha256",
            "executable_sha256 = $script:ActualArduinoCliSha256",
        ):
            self.assertIn(marker, self.target_text)

    def test_installed_release_byte_provenance_is_in_evidence(self) -> None:
        """! @brief 설치 archive와 release manifest의 commit/checksum identity를 남깁니다. """

        for marker in (
            "release-manifest.json",
            "core_revision",
            "board_revision",
            "release_manifest_sha256",
            "archive_sha256",
            "archive_size",
            "index_sha256",
            "prerequisites_pins_sha256",
            "Installed release and Nordic verifier pins differ",
            "prevalidated archive",
        ):
            self.assertIn(marker, self.target_text)

    def test_index_cannot_redirect_to_an_arbitrary_archive(self) -> None:
        """! @brief index의 filename과 EIDOSDATA release URL을 version별로 고정합니다. """

        for marker in (
            '"nucode-nu54dk-zephyr-$version.zip"',
            '"https://github.com/EIDOSDATA/NU54DK_Arduino_Core/releases/download/m10-preview-$version/$expectedFileName"',
            "Get-PublicArchiveIdentity",
            "archive SHA-256이 package index와 다릅니다",
            "release-manifest\\.json",
            "core_revision = [string]$manifest.core_revision",
            "release_manifest_sha256",
        ):
            self.assertIn(marker, self.local_text)

    def test_checkpoint_writes_are_atomic_and_write_through(self) -> None:
        """! @brief state/evidence가 같은 directory의 임시 파일에서 원자 교체됩니다. """

        for marker in (
            "function Write-AtomicUtf8NoBom",
            "[IO.FileOptions]::WriteThrough",
            "$stream.Flush($true)",
            "[IO.File]::Replace",
            "[IO.File]::Move",
        ):
            self.assertIn(marker, self.target_text)
        self.assertGreaterEqual(self.target_text.count("Write-AtomicUtf8NoBom `"), 2)

        body = (
            "$root=Join-Path $env:TEMP ('nu54-atomic-'+[Guid]::NewGuid().ToString('N'));"
            "New-Item -ItemType Directory -Path $root|Out-Null;"
            "$path=Join-Path $root 'state.json';"
            "try{Write-AtomicUtf8NoBom -Path $path -Text 'old';"
            "Write-AtomicUtf8NoBom -Path $path -Text 'new';"
            "$result=[ordered]@{content=[IO.File]::ReadAllText($path);"
            "temporary_count=@(Get-ChildItem -LiteralPath $root -Force|"
            "Where-Object{$_.Name -ne 'state.json'}).Count};"
            "$result|ConvertTo-Json -Compress}"
            "finally{Remove-Item -LiteralPath $root -Recurse -Force}"
        )
        result = self.invoke_target_functions(("Write-AtomicUtf8NoBom",), body)
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload, {"content": "new", "temporary_count": 0})

    def test_run_identity_has_one_global_mutex_owner(self) -> None:
        """! @brief 같은 RunId의 두 process가 Arduino data와 checkpoint를 공유하지 않습니다. """

        for marker in (
            "Global\\NUCODE_NU54DK_M10_",
            "[Threading.AbandonedMutexException]",
            "Another process already owns this M10 run identity",
            "Enter-RunMutex -RunRoot $script:RunRoot",
            "Exit-RunMutex -Handle $script:RunMutexHandle",
        ):
            self.assertIn(marker, self.target_text)

        run_root = (
            "C:\\Users\\nu54ci\\NU54CI\\M10\\runs\\unit-" + uuid.uuid4().hex
        )
        holder_body = (
            f"$handle=Enter-RunMutex -RunRoot '{run_root}';"
            "try{Write-Output 'READY';[Console]::Out.Flush();"
            "[Console]::In.ReadLine()|Out-Null}"
            "finally{Exit-RunMutex -Handle $handle}"
        )
        holder_command = self.target_function_command(
            ("Enter-RunMutex", "Exit-RunMutex"), holder_body
        )
        holder = subprocess.Popen(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                holder_command,
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            self.assertIsNotNone(holder.stdout)
            self.assertEqual(holder.stdout.readline().strip(), "READY")
            contender_body = (
                f"try{{$handle=Enter-RunMutex -RunRoot '{run_root}';"
                "Exit-RunMutex -Handle $handle;Write-Output 'ACQUIRED';exit 3}"
                "catch{Write-Output 'BLOCKED';exit 0}"
            )
            contender = self.invoke_target_functions(
                ("Enter-RunMutex", "Exit-RunMutex"), contender_body
            )
            self.assertEqual(contender.returncode, 0, contender.stderr)
            self.assertIn("BLOCKED", contender.stdout)
        finally:
            if holder.stdin is not None:
                holder.stdin.write("release\n")
                holder.stdin.flush()
            holder_stdout, holder_stderr = holder.communicate(timeout=10)
            self.assertEqual(holder.returncode, 0, holder_stdout + holder_stderr)

        reacquire_body = (
            f"$handle=Enter-RunMutex -RunRoot '{run_root}';"
            "try{Write-Output 'REACQUIRED'}finally{Exit-RunMutex -Handle $handle}"
        )
        reacquired = self.invoke_target_functions(
            ("Enter-RunMutex", "Exit-RunMutex"), reacquire_body
        )
        self.assertEqual(reacquired.returncode, 0, reacquired.stderr)
        self.assertIn("REACQUIRED", reacquired.stdout)

    def test_timeout_and_exit_code_contract_is_fail_closed(self) -> None:
        """! @brief native command가 timeout과 exit code를 모두 검사합니다. """

        for text in (self.local_text, self.target_text):
            self.assertIn("WaitForExit", text)
            self.assertIn("AllowedExitCodes", text)
            self.assertIn("taskkill.exe", text)
            self.assertIn("System.Diagnostics.ProcessStartInfo", text)
            self.assertIn("$exitCode = $process.ExitCode", text)
            self.assertNotIn("Start-Process", text)
        self.assertIn("evidence bundle", self.local_text)
        self.assertIn("M10 TARGET RUN FAIL", self.target_text)

    def test_native_output_is_disk_spooled_and_tail_bounded(self) -> None:
        """! @brief 장시간 native 출력은 file로 흘리고 제한된 tail만 메모리에 반환합니다. """

        for text in (self.local_text, self.target_text):
            self.assertNotIn("ReadToEndAsync", text)
            self.assertIn("BaseStream.CopyToAsync", text)
            self.assertIn("function Read-BoundedTextTail", text)
            self.assertIn("MaximumBytes = 1048576", text)
            self.assertIn(".stdout.log", text)
            self.assertIn(".stderr.log", text)
            self.assertIn("Remove-Item -LiteralPath $stdoutPath, $stderrPath", text)
            self.assertIn("[void]$stdoutTask.GetAwaiter().GetResult()", text)
            self.assertIn("[void]$stderrTask.GetAwaiter().GetResult()", text)

        fixture = "nu54-output-spool-" + uuid.uuid4().hex
        body = (
            f"$root=Join-Path ([IO.Path]::GetTempPath()) '{fixture}';"
            "New-Item -ItemType Directory -Path $root -Force|Out-Null;"
            "$script:TemporaryRoot=$root;$script:RunRoot=$root;"
            "$script:RunLogPath=Join-Path $root 'runner.log';"
            "$powerShell=Join-Path $env:SystemRoot 'System32\\WindowsPowerShell\\v1.0\\powershell.exe';"
            "function Add-RunLog{param($Text)};"
            "$payload=\"[Console]::Out.Write(('A' * 2097152) + 'OUT-END');"
            "[Console]::Error.Write(('B' * 2097152) + 'ERR-END')\";"
            "try{$result=Invoke-NativeCommand -FilePath $powerShell "
            "-Arguments @('-NoProfile','-NonInteractive','-Command',$payload) "
            "-Label 'bounded-output' -TimeoutSeconds 30;"
            "$summary=[ordered]@{stdout_length=$result.stdout.Length;"
            "stderr_length=$result.stderr.Length;"
            "stdout_truncated=$result.stdout.StartsWith('[output truncated');"
            "stderr_truncated=$result.stderr.StartsWith('[output truncated');"
            "stdout_ended=$result.stdout.EndsWith('OUT-END');"
            "stderr_ended=$result.stderr.EndsWith('ERR-END');"
            "temporary_count=@(Get-ChildItem -LiteralPath $root -File).Count};"
            "$summary|ConvertTo-Json -Compress}"
            "finally{Remove-Item -LiteralPath $root -Recurse -Force}"
        )
        completed = self.invoke_target_functions(
            (
                "Convert-ToCommandArgument",
                "Protect-Text",
                "Add-RunLog",
                "Read-BoundedTextTail",
                "Invoke-NativeCommand",
            ),
            body,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        summary = json.loads(completed.stdout)
        self.assertLessEqual(summary["stdout_length"], 1048700)
        self.assertLessEqual(summary["stderr_length"], 1048700)
        self.assertTrue(summary["stdout_truncated"])
        self.assertTrue(summary["stderr_truncated"])
        self.assertTrue(summary["stdout_ended"])
        self.assertTrue(summary["stderr_ended"])
        self.assertEqual(summary["temporary_count"], 0)

        local_fixture = "nu54-local-output-spool-" + uuid.uuid4().hex
        local_body = (
            f"$root=Join-Path ([IO.Path]::GetTempPath()) '{local_fixture}';"
            "New-Item -ItemType Directory -Path $root -Force|Out-Null;"
            "$script:LocalTemporaryRoot=$root;"
            "$script:LocalLogPath=Join-Path $root 'orchestrator.log';"
            "[IO.File]::WriteAllText($script:LocalLogPath,'');"
            "$powerShell=Join-Path $env:SystemRoot 'System32\\WindowsPowerShell\\v1.0\\powershell.exe';"
            "$payload=\"[Console]::Out.Write(('C' * 2097152) + 'LOCAL-END')\";"
            "try{$result=Invoke-LocalNative -FilePath $powerShell "
            "-Arguments @('-NoProfile','-NonInteractive','-Command',$payload) "
            "-Label 'bounded-local-output' -TimeoutSeconds 30 6>$null;"
            "$summary=[ordered]@{stdout_length=$result.stdout.Length;"
            "stdout_truncated=$result.stdout.StartsWith('[output truncated');"
            "stdout_ended=$result.stdout.EndsWith('LOCAL-END');"
            "temporary_count=@(Get-ChildItem -LiteralPath $root -File|"
            "Where-Object{$_.Name -ne 'orchestrator.log'}).Count};"
            "$summary|ConvertTo-Json -Compress}"
            "finally{Remove-Item -LiteralPath $root -Recurse -Force}"
        )
        local_completed = self.invoke_script_functions(
            LOCAL_RUNNER,
            (
                "Convert-ToNativeArgument",
                "Protect-LogText",
                "Read-BoundedTextTail",
                "Invoke-LocalNative",
            ),
            local_body,
        )
        self.assertEqual(local_completed.returncode, 0, local_completed.stderr)
        local_summary = json.loads(local_completed.stdout)
        self.assertLessEqual(local_summary["stdout_length"], 1048700)
        self.assertTrue(local_summary["stdout_truncated"])
        self.assertTrue(local_summary["stdout_ended"])
        self.assertEqual(local_summary["temporary_count"], 0)

    def test_native_command_returns_one_object_under_strict_mode(self) -> None:
        """! @brief PS 5.1 Task 결과가 success stream에 섞여 JSON 결과를 배열로 만들지 않습니다. """

        fixture = "nu54-native-result-" + uuid.uuid4().hex
        json_text = json.dumps(
            {
                "Application": "arduino-cli",
                "VersionString": "1.5.2-rc.1",
                "Commit": "fef6e48df",
            },
            separators=(",", ":"),
        )
        encoded_json = base64.b64encode(json_text.encode("utf-8")).decode("ascii")
        body = (
            "Set-StrictMode -Version Latest;"
            f"$root=Join-Path ([IO.Path]::GetTempPath()) '{fixture}';"
            "New-Item -ItemType Directory -Path $root -Force|Out-Null;"
            "$script:TemporaryRoot=$root;$script:RunRoot=$root;"
            "$script:RunLogPath=Join-Path $root 'runner.log';"
            "$powerShell=Join-Path $env:SystemRoot "
            "'System32\\WindowsPowerShell\\v1.0\\powershell.exe';"
            "$payload=\"[Console]::Out.Write([Text.Encoding]::UTF8.GetString(\""
            f"+\"[Convert]::FromBase64String('{encoded_json}')))\";"
            "try{$result=@(Invoke-NativeCommand -FilePath $powerShell "
            "-Arguments @('-NoProfile','-NonInteractive','-Command',$payload) "
            "-Label 'strict-json' -TimeoutSeconds 30 6>$null);"
            "if($result.Count -ne 1){throw ('unexpected-result-count='+$result.Count)};"
            "$identity=$result[0].stdout|ConvertFrom-Json;"
            "$summary=[ordered]@{count=$result.Count;exit_code=$result[0].exit_code;"
            "application=$identity.Application;version=$identity.VersionString};"
            "$summary|ConvertTo-Json -Compress}"
            "finally{Remove-Item -LiteralPath $root -Recurse -Force}"
        )
        completed = self.invoke_target_functions(
            (
                "Convert-ToCommandArgument",
                "Protect-Text",
                "Add-RunLog",
                "Read-BoundedTextTail",
                "Invoke-NativeCommand",
            ),
            body,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        summary = json.loads(completed.stdout)
        self.assertEqual(
            summary,
            {
                "count": 1,
                "exit_code": 0,
                "application": "arduino-cli",
                "version": "1.5.2-rc.1",
            },
        )

        local_fixture = "nu54-local-result-" + uuid.uuid4().hex
        local_body = (
            "Set-StrictMode -Version Latest;"
            f"$root=Join-Path ([IO.Path]::GetTempPath()) '{local_fixture}';"
            "New-Item -ItemType Directory -Path $root -Force|Out-Null;"
            "$script:LocalTemporaryRoot=$root;"
            "$script:LocalLogPath=Join-Path $root 'orchestrator.log';"
            "[IO.File]::WriteAllText($script:LocalLogPath,'');"
            "$powerShell=Join-Path $env:SystemRoot "
            "'System32\\WindowsPowerShell\\v1.0\\powershell.exe';"
            "$payload=\"[Console]::Out.Write([Text.Encoding]::UTF8.GetString(\""
            f"+\"[Convert]::FromBase64String('{encoded_json}')))\";"
            "try{$result=@(Invoke-LocalNative -FilePath $powerShell "
            "-Arguments @('-NoProfile','-NonInteractive','-Command',$payload) "
            "-Label 'strict-json' -TimeoutSeconds 30 6>$null);"
            "if($result.Count -ne 1){throw ('unexpected-result-count='+$result.Count)};"
            "$identity=$result[0].stdout|ConvertFrom-Json;"
            "$summary=[ordered]@{count=$result.Count;exit_code=$result[0].exit_code;"
            "application=$identity.Application;version=$identity.VersionString};"
            "$summary|ConvertTo-Json -Compress}"
            "finally{Remove-Item -LiteralPath $root -Recurse -Force}"
        )
        local_completed = self.invoke_script_functions(
            LOCAL_RUNNER,
            (
                "Convert-ToNativeArgument",
                "Protect-LogText",
                "Read-BoundedTextTail",
                "Invoke-LocalNative",
            ),
            local_body,
        )
        self.assertEqual(local_completed.returncode, 0, local_completed.stderr)
        self.assertEqual(json.loads(local_completed.stdout), summary)


if __name__ == "__main__":
    unittest.main()
