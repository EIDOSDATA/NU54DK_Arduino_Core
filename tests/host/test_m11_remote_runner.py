#!/usr/bin/env python3
"""! @brief M11 RC Windows SSH 실행기의 고정 안전 계약을 검증합니다. """

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
RUNNER = REPOSITORY_ROOT / "tools" / "release" / "invoke-m11-rc-windows.ps1"


class M11RemoteRunnerContractTests(unittest.TestCase):
    """! @brief 원격 RC gate가 exact source·artifact·SSH pin을 보존하는지 검증합니다. """

    @classmethod
    def setUpClass(cls) -> None:
        """! @brief PowerShell 실행기 원문을 한 번만 읽습니다. """

        cls.text = RUNNER.read_text(encoding="utf-8")

    def invoke_functions(
        self, names: tuple[str, ...], body: str
    ) -> subprocess.CompletedProcess[str]:
        """! @brief 지정 함수 AST만 Windows PowerShell 5.1에서 실행합니다. """

        escaped_path = str(RUNNER).replace("'", "''")
        quoted_names = ",".join(f"'{name}'" for name in names)
        command = (
            "$tokens=$null;$errors=$null;"
            f"$ast=[System.Management.Automation.Language.Parser]::ParseFile('{escaped_path}',"
            "[ref]$tokens,[ref]$errors);"
            f"foreach($name in @({quoted_names})){{"
            "$function=$ast.Find({param($node)"
            "$node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and "
            "$node.Name -eq $name},$true);"
            "if($null -eq $function){throw ('missing function: '+$name)};"
            "Invoke-Expression $function.Extent.Text};"
            + body
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
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )

    def test_01_powershell_51_parser_accepts_runner(self) -> None:
        """! @brief Windows PowerShell 5.1 parser가 전체 script를 해석합니다. """

        escaped_path = str(RUNNER).replace("'", "''")
        command = (
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
                command,
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_02_ssh_authentication_and_host_key_are_fail_closed(self) -> None:
        """! @brief password fallback과 확인하지 않은 host key를 허용하지 않습니다. """

        for marker in (
            "BatchMode=yes",
            "IdentitiesOnly=yes",
            "StrictHostKeyChecking=yes",
            "UserKnownHostsFile=",
            "ssh-keygen.exe",
            "known-host-pin-preflight",
            "ServerAliveInterval=30",
            "ServerAliveCountMax=4",
            "IdentityFile에는 공개키가 아니라 private key",
            "ReparsePoint",
        ):
            self.assertIn(marker, self.text)
        self.assertNotIn("StrictHostKeyChecking=no", self.text)
        self.assertNotIn("PasswordAuthentication=yes", self.text)

    def test_03_public_exact_commit_and_submodule_are_forced(self) -> None:
        """! @brief credential 없는 공개 clone 뒤 exact detached commit만 사용합니다. """

        for marker in (
            "https://github.com/EIDOSDATA/NU54DK_Arduino_Core.git",
            "GIT_CONFIG_NOSYSTEM = '1'",
            "GIT_CONFIG_GLOBAL = $emptyGitConfig",
            "GIT_TERMINAL_PROMPT = '0'",
            "-c credential.helper= -c core.longpaths=true clone --no-checkout",
            "clone --no-checkout",
            "checkout --detach $coreRevision",
            "-c core.longpaths=true -C $repositoryRoot checkout --detach",
            "submodule update --init --recursive",
            "status --porcelain=v1 --untracked-files=all --ignore-submodules=none",
            "Remote repository is not the exact clean RC commit",
        ):
            self.assertIn(marker, self.text)
        for forbidden in (
            "https://$",
            "Invoke-Expression $remote",
            "RepositoryToken",
            "GitHubToken",
        ):
            self.assertNotIn(forbidden, self.text)

    def test_04_m10_ready_marker_selects_pinned_python_and_git(self) -> None:
        """! @brief M10 완료 marker와 고정 Toolchain 실행 파일만 사용합니다. """

        for marker in (
            "NUCODE\\NU54DK_Arduino_Core\\prerequisites\\ready.json",
            "schema_version -ne 1",
            "status -ne 'ready'",
            "ncs_version -ne $expectedNcs",
            "toolchain_bundle_id -ne $expectedToolchain",
            "opt\\bin\\python.exe",
            "bin\\git.exe",
            "dcbdc366a1",
            "v3.4.0",
        ):
            self.assertIn(marker, self.text)

    def test_05_arduino_cli_identity_and_gate_set_are_fixed(self) -> None:
        """! @brief exact Arduino CLI와 세 개의 repo-owned gate만 실행합니다. """

        self.assertIn(
            "ba1890afcfc08524f76191b5cc801b0779cb25e81a5e6693eb0e26b50a3f3538",
            self.text,
        )
        gate_block = self.text[self.text.index("$gates = @(") :]
        positions = [
            gate_block.index(f"id = '{gate}'")
            for gate in (
                "arduino_cli_fixed_package",
                "zephyr_regression",
                "hil_rc_pyocd",
            )
        ]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("'run-gate'", gate_block)
        self.assertIn("'--serial-port', '__SERIAL_PORT__'", gate_block)
        self.assertNotIn("[string[]]$Gate", self.text)

    def test_06_plan_and_every_artifact_are_checked_before_transfer(self) -> None:
        """! @brief plan allowlist의 전체 byte·크기·경로를 로컬에서 검증합니다. """

        for marker in (
            "'archive'",
            "'checksums'",
            "'index'",
            "'licenses'",
            "'manifest'",
            "'notices'",
            "'sbom'",
            "local-validate-plan",
            "artifact byte identity가 plan과 다릅니다",
            "artifact가 ReleaseRoot 밖에 있습니다",
            "Transferred RC plan or artifact byte validation failed",
        ):
            self.assertIn(marker, self.text)

    def test_07_release_bundle_runtime_rejects_modified_artifact(self) -> None:
        """! @brief 실제 bundle validator가 변조한 artifact를 fail-closed 처리합니다. """

        artifact_keys = (
            "archive",
            "checksums",
            "index",
            "licenses",
            "manifest",
            "notices",
            "sbom",
        )
        with tempfile.TemporaryDirectory(prefix="nu54-m11-remote-test-") as temporary:
            root = Path(temporary)
            artifacts: dict[str, dict[str, object]] = {}
            for index, key in enumerate(artifact_keys):
                path = root / f"{key}.fixture"
                data = f"fixture-{index}\n".encode()
                path.write_bytes(data)
                artifacts[key] = {
                    "file_name": path.name,
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "size": len(data),
                }
            plan = {
                "schema_version": 1,
                "milestone": "M11",
                "kind": "release-candidate-plan",
                "version": "0.1.0-rc.1",
                "release_tag": "v0.1.0-rc.1",
                "source_repository": "https://github.com/EIDOSDATA/NU54DK_Arduino_Core",
                "core_revision": "1" * 40,
                "board_revision": "2" * 40,
                "runtime_payload_sha256": "3" * 64,
                "artifacts": artifacts,
            }
            plan_path = root / "m11-rc-plan.json"
            plan_path.write_text(
                json.dumps(plan, ensure_ascii=False), encoding="utf-8"
            )
            escaped_root = str(root).replace("'", "''")
            escaped_plan = str(plan_path).replace("'", "''")
            body = (
                "$script:ExpectedVersion='0.1.0-rc.1';"
                "$script:ExpectedArtifactKeys=@('archive','checksums','index','licenses',"
                "'manifest','notices','sbom');"
                f"$result=Get-ReleaseBundle -PlanPath '{escaped_plan}' -Root '{escaped_root}';"
                "Write-Output ('COUNT='+$result.files.Count)"
            )
            completed = self.invoke_functions(
                ("Get-ByteSha256", "Get-FileSha256", "Assert-RegularFile", "Get-ReleaseBundle"),
                body,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("COUNT=8", completed.stdout)

            (root / "archive.fixture").write_bytes(b"tampered\n")
            rejected = self.invoke_functions(
                ("Get-ByteSha256", "Get-FileSha256", "Assert-RegularFile", "Get-ReleaseBundle"),
                body,
            )
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn("byte identity", rejected.stderr)

    def test_08_evidence_log_and_hil_result_are_always_retrieved(self) -> None:
        """! @brief 성공과 실패 모두에서 고정 companion 파일 회수를 시도합니다. """

        for file_name in (
            "arduino_cli_fixed_package.evidence.json",
            "arduino_cli_fixed_package.evidence.log",
            "zephyr_regression.evidence.json",
            "zephyr_regression.evidence.log",
            "hil_rc_pyocd.evidence.json",
            "hil_rc_pyocd.evidence.log",
            "hil_rc_pyocd.evidence.result.json",
        ):
            self.assertIn(file_name, self.text)
        self.assertIn("} finally {\n    foreach ($fileName", self.text)
        self.assertIn("local-validate-remote-evidence", self.text)
        self.assertIn("validate_gate_evidence", self.text)
        self.assertIn("NU54_M11_REMOTE_RESULTS_IMPORTED", self.text)
        self.assertIn(
            "ReleaseRoot에 같은 M11 remote result가 이미 존재합니다",
            self.text,
        )
        self.assertIn(
            "ReleaseRoot로 가져온 M11 remote result byte가 다릅니다",
            self.text,
        )

    def test_09_timeout_and_output_capture_are_bounded(self) -> None:
        """! @brief 장시간 gate도 disk spool, timeout과 process-tree 종료를 사용합니다. """

        for marker in (
            "BaseStream.CopyToAsync",
            "Read-BoundedTextTail",
            "MaximumBytes = 1048576",
            "taskkill.exe",
            "/PID $process.Id /T /F",
            "[void]$stdoutTask.GetAwaiter().GetResult()",
            "[void]$stderrTask.GetAwaiter().GetResult()",
            "$minimumSshTimeout",
            "종료 코드 ${exitCode}로 실패",
        ):
            self.assertIn(marker, self.text)

        unsafe_interpolation = re.compile(
            r"\$[A-Za-z_][A-Za-z0-9_]*[가-힣]"
        )
        self.assertIsNone(unsafe_interpolation.search(self.text))

    def test_09b_remote_gate_uses_uploaded_ascii_launcher(self) -> None:
        """! @brief 긴 remote command를 SSH command line에 직접 넣지 않습니다. """

        for marker in (
            "$runRoot = '__RUN_ROOT__'",
            "Replace('__RUN_ROOT__', $remoteRunWindows)",
            "Remote M11 gate launcher는 Windows PowerShell 5.1 호환 ASCII",
            "$localGateScript = Join-Path $script:LocalTemporaryRoot 'run-m11-gates.ps1'",
            "$remoteGateScriptWindows = \"$remoteRunWindows\\run-m11-gates.ps1\"",
            "'upload-m11-gate-launcher'",
            "'-File'",
            "$remoteGateScriptWindows",
        ):
            self.assertIn(marker, self.text)
        self.assertNotIn("$encodedGates", self.text)

    def test_10_credentials_device_and_endpoint_are_redacted(self) -> None:
        """! @brief endpoint, token, probe UID와 COM port 원문을 제거합니다. """

        body = (
            "$script:SensitiveLogValues=@('192.168.1.10','nu54ci@192.168.1.10');"
            "$sample='nu54ci@192.168.1.10 token=secret-value serial_number=abcdef0123456789 "
            "COM42 github_pat_abcdefghijklmnop';"
            "Protect-LogText -Text $sample"
        )
        completed = self.invoke_functions(("Protect-LogText",), body)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        for secret in (
            "192.168.1.10",
            "secret-value",
            "abcdef0123456789",
            "COM42",
            "github_pat_abcdefghijklmnop",
        ):
            self.assertNotIn(secret, completed.stdout)
        for replacement in (
            "<redacted-endpoint>",
            "<redacted>",
            "<redacted-device-id>",
            "<redacted-device-port>",
        ):
            self.assertIn(replacement, completed.stdout)

    def test_11_result_omits_endpoint_and_records_hashes(self) -> None:
        """! @brief orchestrator JSON에는 endpoint 원문 대신 hash와 gate byte를 남깁니다. """

        for marker in (
            "evidence_type = 'remote-gate-orchestrator'",
            "endpoint_sha256 = Get-ByteSha256",
            "identity_file_sha256 = Get-FileSha256",
            "known_hosts_sha256 = Get-FileSha256",
            "evidence_sha256 = Get-FileSha256",
            "log_sha256 = Get-FileSha256",
            "result_sha256",
            "target_endpoint = $true",
        ):
            self.assertIn(marker, self.text)
        self.assertNotIn("target_host = $TargetHost", self.text)

    def test_12_remote_paths_are_unique_and_never_deleted_for_reuse(self) -> None:
        """! @brief run별 새 경로를 요구해 이전 evidence와 checkout을 섞지 않습니다. """

        for marker in (
            "M11 remote run directory already exists",
            "같은 M11 run output이 이미 존재",
            "[Guid]::NewGuid().ToString('N').Substring(0, 8)",
            "$RemoteWorkRoot\\runs\\$($script:CurrentRunId)",
        ):
            self.assertIn(marker, self.text)
        self.assertNotIn("Remove-Item -LiteralPath $remoteRun", self.text)


if __name__ == "__main__":
    unittest.main()
