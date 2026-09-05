#!/usr/bin/env python3
"""! @brief M10 Nordic prerequisite와 Git-less package 계약을 검증합니다. """

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPOSITORY_ROOT / "tools" / "nu54-builder" / "src" / "nu54_builder.py"
MODULE_SPEC = importlib.util.spec_from_file_location("nu54_builder_m10", MODULE_PATH)
if MODULE_SPEC is None or MODULE_SPEC.loader is None:
    raise RuntimeError(f"nu54-builder module을 불러올 수 없습니다: {MODULE_PATH}")
MODULE = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(MODULE)


class M10PrerequisiteContractTests(unittest.TestCase):
    """! @brief 배포 pin, 완료 marker와 archive revision의 fail-closed 동작을 시험합니다. """

    def setUp(self) -> None:
        """! @brief 실제 사용자 설치와 분리된 임시 package fixture를 생성합니다. """

        self.temporary = tempfile.TemporaryDirectory(prefix="n54-m10-prerequisite-")
        self.root = Path(self.temporary.name)
        self.platform = self.root / "platform"
        self.state = self.root / "state"
        self.local_data = self.root / "local-data"
        self.nrfutil = (
            self.local_data
            / "NUCODE"
            / "NU54DK_Arduino_Core"
            / "tools"
            / "nrfutil.exe"
        )
        self.nrfutil.parent.mkdir(parents=True)
        self.nrfutil.write_bytes(b"fixture")
        self.ncs_install = self.root / "ncs"
        self.ncs_root = self.ncs_install / MODULE.NCS_VERSION
        self.toolchain = self.ncs_install / "toolchains" / MODULE.TOOLCHAIN_BUNDLE_ID
        self.toolchain.mkdir(parents=True)
        self.bundled_git = self.toolchain / "bin" / "git.exe"
        self.bundled_git.parent.mkdir()
        self.bundled_git.write_bytes(b"git-fixture")
        self.toolchain_manifest = self.toolchain / "manifest.json"
        self.toolchain_manifest.write_text(
            json.dumps({"bundle_id": MODULE.TOOLCHAIN_BUNDLE_ID}) + "\n",
            encoding="utf-8",
        )
        prerequisite = self.platform / "tools" / "nu54-prerequisites"
        prerequisite.mkdir(parents=True)
        self.pins_path = prerequisite / "pins.json"
        self.pins_path.write_bytes(
            (REPOSITORY_ROOT / "tools" / "nu54-prerequisites" / "pins.json").read_bytes()
        )
        self.pins_hash = MODULE.file_sha256(self.pins_path)
        self.manifest = {
            "schema_version": 1,
            "core_revision": "1" * 40,
            "board_revision": "2" * 40,
            "ncs_revision": MODULE.NCS_REVISION,
            "zephyr_revision": MODULE.ZEPHYR_REVISION,
            "toolchain_bundle_id": MODULE.TOOLCHAIN_BUNDLE_ID,
            "prerequisites_pins_sha256": self.pins_hash,
        }
        self.write_manifest()
        self.ready = {
            "schema_version": 1,
            "status": "ready",
            "pins_sha256": self.pins_hash,
            "nrfutil_path": self.nrfutil.as_posix(),
            "nrfutil_sha256": MODULE.NRFUTIL_SHA256,
            "nrfutil_version": MODULE.NRFUTIL_VERSION,
            "sdk_manager_version": MODULE.SDK_MANAGER_VERSION,
            "ncs_version": MODULE.NCS_VERSION,
            "ncs_revision": MODULE.NCS_REVISION,
            "zephyr_revision": MODULE.ZEPHYR_REVISION,
            "toolchain_bundle_id": MODULE.TOOLCHAIN_BUNDLE_ID,
            "ncs_root": self.ncs_install.as_posix(),
            "toolchain_root": self.toolchain.as_posix(),
        }
        self.state.mkdir()
        self.write_ready()
        self.previous_state = os.environ.get("NUCODE_PREREQUISITE_STATE_ROOT")
        self.previous_local_data = os.environ.get("LOCALAPPDATA")
        os.environ["NUCODE_PREREQUISITE_STATE_ROOT"] = str(self.state)
        os.environ["LOCALAPPDATA"] = str(self.local_data)

    def tearDown(self) -> None:
        """! @brief 시험용 환경 변수와 임시 directory를 복원합니다. """

        if self.previous_state is None:
            os.environ.pop("NUCODE_PREREQUISITE_STATE_ROOT", None)
        else:
            os.environ["NUCODE_PREREQUISITE_STATE_ROOT"] = self.previous_state
        if self.previous_local_data is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = self.previous_local_data
        self.temporary.cleanup()

    def write_manifest(self) -> None:
        """! @brief 현재 release manifest fixture를 기록합니다. """

        (self.platform / "release-manifest.json").write_text(
            json.dumps(self.manifest, sort_keys=True) + "\n", encoding="utf-8"
        )

    def write_ready(self) -> None:
        """! @brief 현재 prerequisite 완료 marker fixture를 기록합니다. """

        (self.state / "ready.json").write_text(
            json.dumps(self.ready, sort_keys=True) + "\n", encoding="utf-8"
        )

    def validate(self) -> None:
        """! @brief 외부 Git 조회만 고정해 package 계약 검증을 실행합니다. """

        def revision(path: Path, *_args: object, **_kwargs: object) -> str:
            return MODULE.ZEPHYR_REVISION if Path(path).name == "zephyr" else MODULE.NCS_REVISION

        real_file_sha256 = MODULE.file_sha256

        def hash_file(path: Path) -> str:
            if MODULE.path_key(path) == MODULE.path_key(self.nrfutil):
                return MODULE.NRFUTIL_SHA256
            return real_file_sha256(path)

        with (
            mock.patch.object(MODULE.implementation.environment, "exact_git_revision", side_effect=revision),
            mock.patch.object(MODULE.implementation.environment, "file_sha256", side_effect=hash_file),
        ):
            MODULE.validate_packaged_prerequisites(
                self.platform, self.ncs_root, self.toolchain
            )

    def test_pin_file_fixes_official_bytes_and_all_nordic_versions(self) -> None:
        """! @brief 공식 URL, byte hash와 SDK/Toolchain revision이 정확히 고정됩니다. """

        pins = json.loads(self.pins_path.read_text(encoding="utf-8"))
        self.assertEqual(pins["nrfutil"]["version"], "8.2.1")
        self.assertEqual(
            pins["nrfutil"]["sha256"],
            "1d291d8a9d6bb5bec18454f8d95064aed7f62e8997ec1c4511f13bdf1124c037",
        )
        self.assertTrue(pins["nrfutil"]["url"].startswith("https://files.nordicsemi.com/"))
        self.assertEqual(pins["sdk_manager"]["version"], "1.16.1")
        self.assertEqual(pins["ncs"]["revision"], MODULE.NCS_REVISION)
        self.assertEqual(pins["zephyr"]["revision"], MODULE.ZEPHYR_REVISION)
        self.assertEqual(pins["toolchain"]["bundle_id"], MODULE.TOOLCHAIN_BUNDLE_ID)

    def test_sdk_manager_requirement_uses_exact_version_operator(self) -> None:
        """! @brief nRF Util installation set이 sdk-manager patch version까지 고정합니다. """

        requirements = json.loads(
            (REPOSITORY_ROOT / "tools" / "nu54-prerequisites" / "nrfutil-requirements.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(requirements["commands"]["sdk-manager"], "=1.16.1")

    def test_matching_release_manifest_and_ready_marker_are_accepted(self) -> None:
        """! @brief package, pin과 설치 marker의 3-way identity가 같으면 승인합니다. """

        self.validate()

    def test_changed_pin_hash_is_rejected(self) -> None:
        """! @brief package pin byte가 바뀌면 과거 완료 marker를 재사용하지 않습니다. """

        self.pins_path.write_text(self.pins_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        with self.assertRaisesRegex(MODULE.AdapterError, "pin hash"):
            self.validate()

    def test_incomplete_or_wrong_ready_marker_is_rejected(self) -> None:
        """! @brief incomplete 상태와 다른 Toolchain marker를 모두 fail-closed 처리합니다. """

        for field, value in (
            ("status", "incomplete"),
            ("toolchain_bundle_id", "wrong"),
            ("ncs_version", "v0.0.0"),
            ("nrfutil_path", (self.root / "wrong" / "nrfutil.exe").as_posix()),
        ):
            with self.subTest(field=field):
                original = self.ready[field]
                self.ready[field] = value
                self.write_ready()
                with self.assertRaises(MODULE.AdapterError):
                    self.validate()
                self.ready[field] = original
                self.write_ready()

        for field in ("ncs_version", "nrfutil_path"):
            with self.subTest(missing=field):
                original = self.ready.pop(field)
                self.write_ready()
                with self.assertRaises(MODULE.AdapterError):
                    self.validate()
                self.ready[field] = original
                self.write_ready()

    def test_verifier_checks_reused_marker_version_and_normalized_nrfutil_path(self) -> None:
        """! @brief verifier가 Builder와 같은 ready marker version/path 계약을 적용합니다. """

        verifier = (
            REPOSITORY_ROOT / "tools" / "nu54-prerequisites" / "verify-nordic.ps1"
        ).read_text(encoding="utf-8-sig")
        self.assertIn(
            "Assert-Equal 'marker NCS version' ([string]$ready.ncs_version) ([string]$pins.ncs.version)",
            verifier,
        )
        self.assertIn("Assert-Equal 'marker nRF Util path'", verifier)
        self.assertIn("(Resolve-FullPath ([string]$ready.nrfutil_path))", verifier)
        self.assertIn("(Resolve-FullPath $nrfutilPath)", verifier)

    def test_packaged_toolchain_discovery_requires_only_pinned_bundle(self) -> None:
        """! @brief package는 env와 registry의 다른 bundle을 무시하고 exact pin만 선택합니다. """

        def make_bundle(root: Path) -> None:
            (root / "opt" / "bin").mkdir(parents=True, exist_ok=True)
            (root / "environment.json").write_text("{}\n", encoding="utf-8")
            (root / "opt" / "bin" / "python.exe").write_bytes(b"python")

        make_bundle(self.toolchain)
        wrong = self.ncs_install / "toolchains" / "wrong-bundle"
        make_bundle(wrong)
        registry = self.ncs_install / "toolchains" / "toolchains.json"
        registry.write_text(
            json.dumps(
                [
                    {
                        "toolchains": [
                            {
                                "ncs_versions": [MODULE.NCS_VERSION],
                                "identifier": {"bundle_id": "wrong-bundle"},
                            }
                        ]
                    }
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        with mock.patch.dict(
            os.environ, {"NUCODE_TOOLCHAIN_ROOT": str(wrong)}, clear=False
        ):
            self.assertEqual(
                MODULE.discover_toolchain_root(self.ncs_root, exact_required=True),
                self.toolchain.resolve(),
            )
            self.assertEqual(
                MODULE.discover_toolchain_root(self.ncs_root, exact_required=False),
                wrong.resolve(),
            )

        alternate_ncs = self.root / "alternate" / MODULE.NCS_VERSION
        fallback = alternate_ncs.parent / "toolchains" / "wrong-bundle"
        make_bundle(fallback)
        with mock.patch.dict(
            os.environ, {"NUCODE_TOOLCHAIN_ROOT": str(fallback)}, clear=False
        ):
            with self.assertRaisesRegex(MODULE.AdapterError, "고정 NCS Toolchain bundle"):
                MODULE.discover_toolchain_root(alternate_ncs, exact_required=True)

    def test_explicit_ncs_root_is_authoritative(self) -> None:
        """! @brief 명시한 NCS root만 선택하고 기본 설치 후보를 조회하지 않습니다. """

        explicit = self.root / "isolated" / MODULE.NCS_VERSION
        (explicit / "zephyr").mkdir(parents=True)
        (explicit / "nrf").mkdir()
        (explicit / "zephyr" / "CMakeLists.txt").write_text(
            "# fixture\n", encoding="utf-8"
        )
        (explicit / "nrf" / "west.yml").write_text(
            "manifest: fixture\n", encoding="utf-8"
        )

        with mock.patch.dict(
            os.environ, {"NUCODE_NCS_ROOT": str(explicit)}, clear=False
        ):
            self.assertEqual(
                MODULE.discover_ncs_root(prefer_user_profile=True), explicit.resolve()
            )

    def test_invalid_explicit_ncs_root_does_not_fall_back(self) -> None:
        """! @brief 격리 NCS가 없을 때 기존 사용자·C 드라이브 설치로 새지 않습니다. """

        missing = self.root / "missing" / MODULE.NCS_VERSION
        fallback_home = self.root / "fallback-home"
        fallback = fallback_home / "ncs" / MODULE.NCS_VERSION
        (fallback / "zephyr").mkdir(parents=True)
        (fallback / "nrf").mkdir()
        (fallback / "zephyr" / "CMakeLists.txt").write_text(
            "# fixture\n", encoding="utf-8"
        )
        (fallback / "nrf" / "west.yml").write_text(
            "manifest: fixture\n", encoding="utf-8"
        )

        with (
            mock.patch.dict(
                os.environ, {"NUCODE_NCS_ROOT": str(missing)}, clear=False
            ),
            mock.patch.object(MODULE.Path, "home", return_value=fallback_home),
        ):
            with self.assertRaisesRegex(MODULE.AdapterError, "명시한 NUCODE_NCS_ROOT"):
                MODULE.discover_ncs_root(prefer_user_profile=True)

    def test_empty_explicit_ncs_root_does_not_fall_back(self) -> None:
        """! @brief 환경 변수를 빈 값으로 명시해도 기존 NCS를 선택하지 않습니다. """

        with mock.patch.dict(os.environ, {"NUCODE_NCS_ROOT": ""}, clear=False):
            with self.assertRaisesRegex(MODULE.AdapterError, "값이 비어"):
                MODULE.discover_ncs_root(prefer_user_profile=True)

    def test_toolchain_manifest_bundle_id_is_verified(self) -> None:
        """! @brief directory 이름과 내부 Nordic bundle metadata가 모두 pin과 같아야 합니다. """

        self.toolchain_manifest.write_text(
            json.dumps({"bundle_id": "different"}) + "\n", encoding="utf-8"
        )
        with self.assertRaisesRegex(MODULE.AdapterError, "manifest bundle_id"):
            self.validate()

    def test_packaged_revisions_use_bundled_git_with_empty_path(self) -> None:
        """! @brief system Git이 없어도 NCS/Zephyr는 Toolchain Git으로만 조회합니다. """

        board = self.platform / "board_package" / "NU54DK_Zephyr_DTS"
        (board / "boards" / "nucode" / "nu54dk").mkdir(parents=True)
        (board / "boards" / "nucode" / "nu54dk" / "board.yml").write_text(
            "board: fixture\n", encoding="utf-8"
        )
        (self.ncs_root / "nrf").mkdir(parents=True)
        (self.ncs_root / "zephyr").mkdir(parents=True)
        (self.ncs_root / "nrf" / "west.yml").write_text("manifest: fixture\n", encoding="utf-8")
        (self.ncs_root / "zephyr" / "VERSION").write_text("VERSION_MAJOR=4\n", encoding="utf-8")
        compiler = self.toolchain / "compiler.exe"
        compiler.write_bytes(b"compiler-fixture")
        sketch = self.root / "sketch"
        sketch.mkdir()
        calls: list[tuple[str, str | None]] = []

        def revision(path: Path, *_args: object, **kwargs: object) -> str:
            executable = kwargs.get("git_executable")
            calls.append((Path(path).name, str(executable) if executable else None))
            if executable is None:
                return "unknown"
            self.assertEqual(MODULE.path_key(executable), MODULE.path_key(self.bundled_git))
            return MODULE.ZEPHYR_REVISION if Path(path).name == "zephyr" else MODULE.NCS_REVISION

        real_file_sha256 = MODULE.file_sha256

        def hash_file(path: Path) -> str:
            if MODULE.path_key(path) == MODULE.path_key(self.nrfutil):
                return MODULE.NRFUTIL_SHA256
            return real_file_sha256(path)

        tools = {
            "ncs_root": self.ncs_root,
            "toolchain_root": self.toolchain,
            "git": self.bundled_git,
            "compiler": compiler,
            "environment": {},
        }
        paths = {"platform_root": self.platform, "sketch_root": sketch}
        args = type(
            "Arguments",
            (),
            {"fqbn": "nucode:zephyr:nu54dk", "board": MODULE.DEFAULT_BOARD},
        )()
        with (
            mock.patch.dict(os.environ, {"PATH": ""}),
            mock.patch.object(MODULE.implementation.environment, "exact_git_revision", side_effect=revision),
            mock.patch.object(MODULE.implementation.environment, "file_sha256", side_effect=hash_file),
            mock.patch.object(MODULE.implementation.environment, "compiler_version", return_value="fixture-gcc"),
            mock.patch.object(MODULE.implementation.cache, "exact_git_revision", side_effect=revision),
            mock.patch.object(MODULE.implementation.cache, "compiler_version", return_value="fixture-gcc"),
        ):
            MODULE.validate_packaged_prerequisites(
                self.platform, self.ncs_root, self.toolchain
            )
            manifest = MODULE.cache_input_manifest(paths, args, tools)

        self.assertEqual(manifest["ncs"]["nrf_revision"], MODULE.NCS_REVISION)
        self.assertEqual(manifest["ncs"]["zephyr_revision"], MODULE.ZEPHYR_REVISION)
        explicit = [entry for entry in calls if entry[0] in {"nrf", "zephyr"}]
        self.assertGreaterEqual(len(explicit), 4)
        self.assertTrue(all(executable == str(self.bundled_git) for _, executable in explicit))

    def test_gitless_revision_falls_back_only_to_valid_release_manifest(self) -> None:
        """! @brief 상위 Git을 오인하지 않고 40자리 archive revision만 사용합니다. """

        self.assertEqual(
            MODULE.exact_git_revision(self.platform, self.platform, "core_revision"),
            "1" * 40,
        )
        self.manifest["core_revision"] = "short"
        self.write_manifest()
        with self.assertRaisesRegex(MODULE.AdapterError, "core_revision"):
            MODULE.exact_git_revision(self.platform, self.platform, "core_revision")

    @unittest.skipUnless(os.name == "nt", "PowerShell parser 검증은 Windows에서만 실행합니다.")
    def test_powershell_install_and_verify_scripts_parse(self) -> None:
        """! @brief clean Windows에서 실행할 두 PowerShell script가 parser 오류 없이 읽힙니다. """

        for filename in ("install-nordic.ps1", "verify-nordic.ps1"):
            script = REPOSITORY_ROOT / "tools" / "nu54-prerequisites" / filename
            escaped_script = str(script).replace("'", "''")
            command = (
                "$e=$null;$t=$null;"
                "[void][Management.Automation.Language.Parser]::ParseFile("
                f"'{escaped_script}',[ref]$t,[ref]$e);"
                "if($e.Count){$e|ForEach-Object{$_.Message};exit 1}"
            )
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, f"{filename}: {result.stdout}")

    def test_powershell_scripts_do_not_depend_on_hash_module_autoload(self) -> None:
        """! @brief clean PowerShell에서 SHA-256 cmdlet 자동 로드에 의존하지 않습니다. """

        for filename in ("install-nordic.ps1", "verify-nordic.ps1"):
            script = (
                REPOSITORY_ROOT / "tools" / "nu54-prerequisites" / filename
            ).read_text(encoding="utf-8-sig")
            self.assertNotIn("Get-FileHash", script, filename)
            self.assertIn("[Security.Cryptography.SHA256]::Create()", script, filename)

    def test_verify_script_initializes_utf8_before_runtime_setup(self) -> None:
        """! @brief 검증 subprocess도 첫 출력 전에 UTF-8 출력을 고정합니다. """

        verifier = (
            REPOSITORY_ROOT / "tools" / "nu54-prerequisites" / "verify-nordic.ps1"
        ).read_text(encoding="utf-8-sig")
        self.assertLess(
            verifier.index("[Console]::OutputEncoding = $utf8NoBom"),
            verifier.index("Set-StrictMode -Version Latest"),
        )

    @unittest.skipUnless(os.name == "nt", "Windows PowerShell 5.1 계약 시험입니다.")
    def test_installer_uses_powershell_51_compatible_log_append(self) -> None:
        """! @brief PS 5.1에서 허용되지 않는 Tee 매개 변수 조합을 차단합니다. """

        installer = (
            REPOSITORY_ROOT / "tools" / "nu54-prerequisites" / "install-nordic.ps1"
        ).read_text(encoding="utf-8-sig")
        self.assertIn(
            "Add-Content -LiteralPath $script:logPath -Encoding UTF8 -Value $outputLine",
            installer,
        )
        self.assertNotIn("Tee-Object", installer)

        log_path = self.root / "powershell-51-tee.log"
        escaped_log = str(log_path).replace("'", "''")
        command = (
            f"'probe' | ForEach-Object {{ Add-Content -LiteralPath '{escaped_log}' "
            "-Encoding UTF8 -Value ([string]$_) }"
        )
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(log_path.read_text(encoding="utf-8-sig").strip(), "probe")

    def test_post_install_propagates_powershell_exit_code(self) -> None:
        """! @brief Arduino hook가 설치 실패를 성공으로 숨기지 않습니다. """

        hook = (REPOSITORY_ROOT / "post_install.bat").read_text(encoding="utf-8")
        self.assertIn("chcp 65001 >nul 2>&1", hook)
        self.assertLess(
            hook.index("chcp 65001 >nul 2>&1"), hook.index("powershell.exe")
        )
        self.assertIn('set "NU54_PLATFORM_ROOT=%~dp0."', hook)
        self.assertIn('-File "%NU54_INSTALLER%" -PlatformRoot "%NU54_PLATFORM_ROOT%"', hook)
        self.assertIn("set \"NU54_RESULT=%ERRORLEVEL%\"", hook)
        self.assertIn("exit /b %NU54_RESULT%", hook)

    @unittest.skipUnless(os.name == "nt", "CMD와 Windows PowerShell 통합 시험입니다.")
    def test_post_install_cmd_preserves_quoted_platform_root_and_exit_code(self) -> None:
        """! @brief trailing slash와 공백이 있는 package root를 실제 CMD 호출로 보존합니다. """

        package_root = self.root / "package root with spaces"
        installer = package_root / "tools" / "nu54-prerequisites" / "install-nordic.ps1"
        installer.parent.mkdir(parents=True)
        hook = package_root / "post_install.bat"
        shutil.copy2(REPOSITORY_ROOT / "post_install.bat", hook)

        def execute(exit_code: int) -> subprocess.CompletedProcess[str]:
            installer.write_text(
                "[CmdletBinding()]\n"
                "param([string]$PlatformRoot)\n"
                "$resolved=[IO.Path]::GetFullPath($PlatformRoot).TrimEnd('\\','/')\n"
                "[Console]::Out.WriteLine(\"ROOT=$resolved\")\n"
                f"exit {exit_code}\n",
                encoding="utf-8-sig",
            )
            return subprocess.run(
                ["cmd.exe", "/d", "/c", str(hook)],
                cwd=package_root,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                check=False,
            )

        success = execute(0)
        self.assertEqual(success.returncode, 0, success.stdout)
        self.assertIn(f"ROOT={package_root.resolve()}", success.stdout)
        failure = execute(37)
        self.assertEqual(failure.returncode, 37, failure.stdout)
        self.assertIn(f"ROOT={package_root.resolve()}", failure.stdout)

    @unittest.skipUnless(
        os.name == "nt", "CMD와 Windows PowerShell UTF-8 통합 시험입니다."
    )
    def test_post_install_cmd_emits_strict_utf8_for_korean_output(self) -> None:
        """! @brief Arduino gRPC에 전달할 한글 출력을 엄격한 UTF-8로 보장합니다. """

        package_root = self.root / "utf8 package root"
        installer = (
            package_root / "tools" / "nu54-prerequisites" / "install-nordic.ps1"
        )
        installer.parent.mkdir(parents=True)
        hook = package_root / "post_install.bat"
        shutil.copy2(REPOSITORY_ROOT / "post_install.bat", hook)
        installer.write_text(
            "[CmdletBinding()]\n"
            "param([string]$PlatformRoot)\n"
            "Write-Host '[NU54DK] 설치 완료'\n",
            encoding="utf-8-sig",
        )

        result = subprocess.run(
            ["cmd.exe", "/d", "/c", str(hook)],
            cwd=package_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        decoded = result.stdout.decode("utf-8", errors="strict")
        self.assertIn("[NU54DK] 설치 완료", decoded)

    def test_installer_sets_utf8_before_any_runtime_output(self) -> None:
        """! @brief 설치기가 첫 출력 전에 PS 5.1 console과 native pipe를 UTF-8로 고정합니다. """

        installer = (
            REPOSITORY_ROOT / "tools" / "nu54-prerequisites" / "install-nordic.ps1"
        ).read_text(encoding="utf-8-sig")
        contracts = (
            "$utf8NoBom = New-Object System.Text.UTF8Encoding($false)",
            "[Console]::InputEncoding = $utf8NoBom",
            "[Console]::OutputEncoding = $utf8NoBom",
            "$OutputEncoding = $utf8NoBom",
        )
        positions = [installer.index(contract) for contract in contracts]
        self.assertEqual(positions, sorted(positions))
        first_output = min(
            installer.index("Write-Host"),
            installer.index("Write-Output") if "Write-Output" in installer else len(installer),
        )
        self.assertTrue(all(position < first_output for position in positions))
        self.assertNotIn("[Console]::OutputEncoding = [Text.Encoding]::Default", installer)

    def test_installer_is_user_scoped_resumable_and_version_checked(self) -> None:
        """! @brief 설치기는 사용자 경로와 단계 marker만 사용하고 고정 version을 확인합니다. """

        installer = (
            REPOSITORY_ROOT / "tools" / "nu54-prerequisites" / "install-nordic.ps1"
        ).read_text(encoding="utf-8-sig")
        for contract in (
            "Join-Path $env:USERPROFILE 'ncs'",
            "Join-Path $stateRoot 'installing.json'",
            "Join-Path $stateRoot 'incomplete.json'",
            "Join-Path $stateRoot 'ready.json'",
            "'sdk-manager', 'toolchain', 'install'",
            "'sdk-manager', 'sdk', 'install'",
            "[string]$pins.nrfutil.version",
            "[string]$pins.sdk_manager.version",
        ):
            self.assertIn(contract, installer)
        lowered = installer.casefold()
        self.assertNotIn("setx", lowered)
        self.assertNotIn("start-process -verb runas", lowered)
        self.assertNotIn("machine]::setenvironmentvariable", lowered)

    def test_builder_launcher_searches_exact_user_toolchain_first(self) -> None:
        """! @brief Arduino process가 PATH 없이 사용자 profile의 고정 Python을 찾습니다. """

        launcher = (
            REPOSITORY_ROOT / "tools" / "nu54-builder" / "nu54-builder.cmd"
        ).read_text(encoding="utf-8")
        user_bundle = "%USERPROFILE%\\ncs\\toolchains\\dcbdc366a1\\opt\\bin\\python.exe"
        self.assertIn(user_bundle, launcher)
        self.assertLess(launcher.index(user_bundle), launcher.index("C:\\ncs\\toolchains\\*"))

    def test_builder_launcher_isolates_embedded_python_runtime(self) -> None:
        """! @brief 외부 Python 환경이 NCS Toolchain 표준 library를 오염시키지 못하게 합니다. """

        launcher = (
            REPOSITORY_ROOT / "tools" / "nu54-builder" / "nu54-builder.cmd"
        ).read_text(encoding="ascii")
        self.assertIn('set "PYTHONHOME="', launcher)
        self.assertIn('set "PYTHONPATH="', launcher)
        self.assertIn('set "PYTHONNOUSERSITE=1"', launcher)
        self.assertIn('set "PATH=%NU54_PYTHON_DIR%;%PATH%"', launcher)
        self.assertIn('"%NU54_PYTHON%" -I ', launcher)


if __name__ == "__main__":
    unittest.main()
