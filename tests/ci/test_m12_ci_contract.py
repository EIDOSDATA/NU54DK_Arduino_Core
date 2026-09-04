#!/usr/bin/env python3
"""! @brief M12 workflow와 재현 build lock의 fail-closed 계약을 검증합니다. """

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import re
import tempfile
import unittest


REPOSITORY = Path(__file__).resolve().parents[2]
LOCK_SCRIPT = REPOSITORY / "tools" / "ci" / "verify_ci_lock.py"
SPEC = importlib.util.spec_from_file_location("nu54_m12_lock_test", LOCK_SCRIPT)
assert SPEC and SPEC.loader
LOCK_MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(LOCK_MODULE)


class M12CiContractTests(unittest.TestCase):
    """! @brief GitHub-hosted software와 self-hosted HIL 경계를 검사합니다. """

    ## @brief 매 시험에서 canonical lock을 읽습니다.
    def setUp(self) -> None:
        self.lock = LOCK_MODULE.strict_json_object(LOCK_MODULE.LOCK_PATH)

    ## @brief 기존 package·prerequisite·gitlink와 lock이 같은지 검증합니다.
    def test_lock_matches_repository_contract(self) -> None:
        LOCK_MODULE.validate_lock(self.lock)

    ## @brief cache key가 exact revision·toolchain·digest를 모두 포함하는지 검증합니다.
    def test_cache_keys_include_exact_identity(self) -> None:
        keys = LOCK_MODULE.cache_keys(self.lock)
        linux = keys["linux_cache_key"]
        windows = keys["windows_cache_key"]
        self.assertIn(self.lock["ncs"]["revision"], linux)
        self.assertIn(self.lock["zephyr"]["revision"], linux)
        self.assertIn(self.lock["linux_toolchain_container"]["toolchain_id"], linux)
        self.assertIn(
            self.lock["linux_toolchain_container"]["digest"].removeprefix("sha256:"),
            linux,
        )
        self.assertIn(self.lock["ncs"]["revision"], windows)
        self.assertIn(self.lock["zephyr"]["revision"], windows)
        self.assertIn(self.lock["windows_toolchain"]["bundle_id"], windows)

    ## @brief PR software workflow가 필수 공개 gate를 자동 실행하는지 검증합니다.
    def test_pull_request_workflow_has_required_gates(self) -> None:
        path = REPOSITORY / ".github" / "workflows" / "m12-software-gates.yml"
        text = path.read_text(encoding="utf-8")
        self.assertRegex(text, r"(?m)^\s*pull_request:\s*$")
        for job in (
            "contract",
            "peripheral-inventory",
            "host",
            "core-semantic",
            "documents",
            "package",
            "example-discovery",
        ):
            self.assertRegex(text, rf"(?m)^  {re.escape(job)}:\s*$")
        self.assertNotIn("pull_request_target", text)

    ## @brief M23 manifest가 software CI와 exact NCS build CI 양쪽에서 fail-closed인지 검사합니다.
    def test_m23_inventory_gates_generated_and_exact_dts_sources(self) -> None:
        software = (
            REPOSITORY / ".github" / "workflows" / "m12-software-gates.yml"
        ).read_text(encoding="utf-8")
        job = software.split("\n  peripheral-inventory:\n", 1)[1].split(
            "\n  host:\n", 1
        )[0]
        self.assertIn("runs-on: ubuntu-24.04", job)
        self.assertIn("python tools/ci/run_m12_gate.py inventory", job)
        self.assertNotIn("continue-on-error", job)

        reproducible = (
            REPOSITORY / ".github" / "workflows" / "m12-reproducible-build.yml"
        ).read_text(encoding="utf-8")
        linux_job = reproducible.split("\n  zephyr-build:\n", 1)[1].split(
            "\n  arduino-build:\n", 1
        )[0]
        command = "python3 tools/peripheral/verify_m23_inventory.py"
        self.assertIn(command, linux_job)
        self.assertIn('--ncs-root "$NCS_CI_WORKSPACE"', linux_job)
        self.assertLess(linux_job.index("prepare_ncs_workspace.py"), linux_job.index(command))
        self.assertLess(linux_job.index(command), linux_job.index("run_zephyr_build.py"))
        self.assertNotIn("continue-on-error", linux_job)

    ## @brief M24 serial-fabric 계약도 software와 exact NCS build 양쪽에서 fail-closed입니다.
    def test_m24_serial_contract_gates_routes_and_exact_dts_sources(self) -> None:
        software = (
            REPOSITORY / ".github" / "workflows" / "m12-software-gates.yml"
        ).read_text(encoding="utf-8")
        job = software.split("\n  peripheral-inventory:\n", 1)[1].split(
            "\n  host:\n", 1
        )[0]
        self.assertIn("M24 serial-fabric contract", job)
        self.assertIn("python tools/ci/run_m12_gate.py inventory", job)
        self.assertNotIn("continue-on-error", job)

        gate = (REPOSITORY / "tools" / "ci" / "run_m12_gate.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('"verify_m24_serial_contract.py"', gate)

        reproducible = (
            REPOSITORY / ".github" / "workflows" / "m12-reproducible-build.yml"
        ).read_text(encoding="utf-8")
        linux_job = reproducible.split("\n  zephyr-build:\n", 1)[1].split(
            "\n  arduino-build:\n", 1
        )[0]
        m23 = "python3 tools/peripheral/verify_m23_inventory.py"
        m24 = "python3 tools/peripheral/verify_m24_serial_contract.py"
        build = "python3 tools/ci/run_zephyr_build.py"
        self.assertIn(m24, linux_job)
        self.assertIn('--ncs-root "$NCS_CI_WORKSPACE"', linux_job)
        self.assertLess(linux_job.index(m23), linux_job.index(m24))
        self.assertLess(linux_job.index(m24), linux_job.index(build))
        self.assertNotIn("continue-on-error", linux_job)

    def test_m26_system_contract_is_fail_closed_in_both_software_gates(self) -> None:
        gate = (REPOSITORY / "tools" / "ci" / "run_m12_gate.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('"verify_m26_system_contract.py"', gate)
        workflow = (
            REPOSITORY / ".github" / "workflows" / "m12-reproducible-build.yml"
        ).read_text(encoding="utf-8")
        m24 = "python3 tools/peripheral/verify_m24_serial_contract.py"
        m26 = "python3 tools/peripheral/verify_m26_system_contract.py"
        build = "python3 tools/ci/run_zephyr_build.py"
        self.assertIn(m26, workflow)
        self.assertLess(workflow.index(m24), workflow.index(m26))
        self.assertLess(workflow.index(m26), workflow.index(build))

    def test_m27_release_contract_is_checked_before_v04_build(self) -> None:
        gate = (REPOSITORY / "tools" / "ci" / "run_m12_gate.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('"m27_release.py"', gate)
        workflow = (
            REPOSITORY / ".github" / "workflows" / "m12-reproducible-build.yml"
        ).read_text(encoding="utf-8")
        contract = "python3 tools/release/m27_release.py contract"
        build = "python3 tools/ci/run_zephyr_build.py"
        self.assertIn(contract, workflow)
        self.assertLess(workflow.index(contract), workflow.index(build))
        self.assertIn('      - "v0.4.0-rc.*"', workflow)
        self.assertNotIn("continue-on-error", workflow)

    def test_host_gate_runs_m26_onboard_runner_unit_contract(self) -> None:
        gate = (REPOSITORY / "tools" / "ci" / "run_m12_gate.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('"test_m26_onboard.py"', gate)

    ## @brief M14 native 의미 시험이 실행 가능한 Ubuntu job에서 직접 수행되는지 검증합니다.
    def test_m14_native_semantic_gate_runs_on_ubuntu(self) -> None:
        path = REPOSITORY / ".github" / "workflows" / "m12-software-gates.yml"
        text = path.read_text(encoding="utf-8")
        job = text.split("\n  core-semantic:\n", 1)[1].split("\n  documents:\n", 1)[0]
        self.assertIn("runs-on: ubuntu-24.04", job)
        self.assertIn(
            "python -m unittest -v tests.host.test_m14_core_contract",
            job,
        )
        self.assertNotIn("continue-on-error", job)

    ## @brief PowerShell runtime 계약이 있는 host suite가 Windows에서 실행되는지 검증합니다.
    def test_host_gate_uses_windows_runner(self) -> None:
        path = REPOSITORY / ".github" / "workflows" / "m12-software-gates.yml"
        text = path.read_text(encoding="utf-8")
        host = text.split("\n  host:\n", 1)[1].split("\n  documents:\n", 1)[0]
        self.assertIn("runs-on: windows-2025", host)
        self.assertIn("--only-binary=:all: --require-hashes", host)
        self.assertIn("tools/ci/requirements-host.txt", host)

    ## @brief host 전용 YAML parser wheel의 버전과 Windows x64 byte hash를 고정합니다.
    def test_host_requirements_are_exact_and_hashed(self) -> None:
        requirements = (REPOSITORY / "tools" / "ci" / "requirements-host.txt").read_text(
            encoding="utf-8"
        )
        self.assertRegex(
            requirements.strip(),
            r"^PyYAML==6\.0\.3 --hash=sha256:[0-9a-f]{64}$",
        )

    ## @brief Linux build가 공식 image tag가 아닌 digest를 사용하는지 검증합니다.
    def test_reproducible_build_uses_digest_and_exact_cache(self) -> None:
        path = REPOSITORY / ".github" / "workflows" / "m12-reproducible-build.yml"
        text = path.read_text(encoding="utf-8")
        expected_image = (
            f"{self.lock['linux_toolchain_container']['image']}@"
            f"{self.lock['linux_toolchain_container']['digest']}"
        )
        self.assertIn(expected_image, text)
        self.assertNotIn(
            f"{self.lock['linux_toolchain_container']['image']}:v3.4.0", text
        )
        self.assertIn("steps.lock.outputs.linux_cache_key", text)
        self.assertIn("steps.lock.outputs.windows_cache_key", text)
        self.assertIn("defaults:\n      run:\n        shell: bash", text)
        self.assertNotIn("ACCEPT_JLINK_LICENSE", text)

    ## @brief v0.3.0 RC tag가 대표 target과 Arduino build workflow를 자동 실행하는지 검증합니다.
    def test_reproducible_build_runs_for_v030_rc_tags(self) -> None:
        path = REPOSITORY / ".github" / "workflows" / "m12-reproducible-build.yml"
        text = path.read_text(encoding="utf-8")
        self.assertIn('      - "v0.3.0-rc.*"', text)

    ## @brief 고정 Nordic container가 M14 QEMU를 실제 실행하고 증적을 업로드하는지 검증합니다.
    def test_reproducible_build_runs_m14_qemu_runtime_and_uploads_evidence(self) -> None:
        path = REPOSITORY / ".github" / "workflows" / "m12-reproducible-build.yml"
        text = path.read_text(encoding="utf-8")
        linux_job = text.split("\n  zephyr-build:\n", 1)[1].split(
            "\n  arduino-build:\n", 1
        )[0]
        command = "python3 tools/ci/run_m14_qemu.py"
        self.assertIn(command, linux_job)
        self.assertIn('--workspace "$NCS_CI_WORKSPACE"', linux_job)
        self.assertIn('--outdir "$M12_EVIDENCE/m14-qemu"', linux_job)
        self.assertIn("path: ${{ env.M12_EVIDENCE }}", linux_job)
        self.assertLess(linux_job.index(command), linux_job.index("actions/upload-artifact@"))
        self.assertNotIn("continue-on-error", linux_job)

    ## @brief 고정 Nordic container가 M17 feasibility를 실행하고 전체 증적을 업로드합니다.
    def test_reproducible_build_runs_m17_feasibility_in_pinned_container(self) -> None:
        path = REPOSITORY / ".github" / "workflows" / "m12-reproducible-build.yml"
        text = path.read_text(encoding="utf-8")
        linux_job = text.split("\n  zephyr-build:\n", 1)[1].split(
            "\n  arduino-build:\n", 1
        )[0]
        command = "python3 tools/ci/run_m17_feasibility.py"
        self.assertIn(command, linux_job)
        self.assertIn('--workspace "$NCS_CI_WORKSPACE"', linux_job)
        self.assertIn('--outdir "$M12_EVIDENCE/m17-feasibility"', linux_job)
        self.assertIn("--west west", linux_job)
        self.assertLess(
            linux_job.index("python3 tools/ci/run_zephyr_build.py"),
            linux_job.index(command),
        )
        self.assertLess(linux_job.index(command), linux_job.index("actions/upload-artifact@"))
        self.assertNotIn("continue-on-error", linux_job)

    ## @brief Windows job이 smoke 뒤 exact CLI로 고정 외부 library compile gate를 실행합니다.
    def test_windows_build_runs_m17_external_arduino_after_smoke(self) -> None:
        path = REPOSITORY / ".github" / "workflows" / "m12-reproducible-build.yml"
        text = path.read_text(encoding="utf-8")
        windows_job = text.split("\n  arduino-build:\n", 1)[1]
        command = "python .\\tools\\ci\\run_m17_external_arduino.py"
        self.assertIn(command, windows_job)
        self.assertIn("Get-Command arduino-cli.exe -ErrorAction Stop", windows_job)
        self.assertIn("--arduino-cli $cli", windows_job)
        self.assertIn(
            "--lock .\\tools\\ci\\m17-external-libraries.lock.json",
            windows_job,
        )
        self.assertIn("'m17-external-arduino.json'", windows_job)
        self.assertIn("'m17-external-arduino.log'", windows_job)
        self.assertIn("$externalExitCode = $LASTEXITCODE", windows_job)
        self.assertIn(
            "if ($externalExitCode -ne 0) { exit $externalExitCode }",
            windows_job,
        )
        self.assertLess(windows_job.index("run_smoke.py"), windows_job.index(command))
        self.assertLess(windows_job.index(command), windows_job.index("actions/upload-artifact@"))
        self.assertNotIn("continue-on-error", windows_job)

    ## @brief 재현 build가 릴리스 도입 기능군별 독립 matrix와 증적을 사용합니다.
    def test_reproducible_build_uses_release_era_parallel_matrix(self) -> None:
        path = REPOSITORY / ".github" / "workflows" / "m12-reproducible-build.yml"
        text = path.read_text(encoding="utf-8")
        linux_job, windows_job = text.split("\n  arduino-build:\n", 1)
        self.assertIn("group: [v0.1.0, v0.2.0, v0.3.0, v0.4.0]", linux_job)
        self.assertIn(
            "group: [v0.1.0, v0.2.0, v0.3.0-ble, v0.3.0-compat]",
            windows_job,
        )
        self.assertEqual(text.count("fail-fast: false"), 2)
        self.assertIn('--group "${{ matrix.group }}"', linux_job)
        self.assertIn("--group '${{ matrix.group }}'", windows_job)
        self.assertIn("m12-zephyr-${{ matrix.group }}-${{ github.sha }}", linux_job)
        self.assertIn("m12-arduino-${{ matrix.group }}-${{ github.sha }}", windows_job)
        self.assertIn("if: matrix.group == 'v0.2.0'", windows_job)

    ## @brief Windows Arduino 재현 build가 짧은 임시 경로와 실패 log를 보존하는지 검증합니다.
    def test_windows_arduino_build_uses_short_temp_and_preserves_failure_log(self) -> None:
        path = REPOSITORY / ".github" / "workflows" / "m12-reproducible-build.yml"
        text = path.read_text(encoding="utf-8")
        self.assertIn("NUCODE_CI_TEMP: D:\\t", text)
        self.assertIn("$env:TEMP = $env:NUCODE_CI_TEMP", text)
        self.assertIn("$env:TMP = $env:NUCODE_CI_TEMP", text)
        self.assertIn("$ErrorActionPreference = 'Continue'", text)
        self.assertIn("$commandExitCode = $LASTEXITCODE", text)
        self.assertIn("arduino-build.log", text)

    ## @brief 양쪽 재현 build cache 경로가 상위 경로 이동 없이 정규화됐는지 검증합니다.
    def test_reproducible_cache_paths_are_normalized(self) -> None:
        path = REPOSITORY / ".github" / "workflows" / "m12-reproducible-build.yml"
        text = path.read_text(encoding="utf-8")
        linux_job, windows_job = text.split("\n  arduino-build:\n", 1)
        self.assertIn("NCS_CI_WORKSPACE: /tmp/nu54dk-ncs-v3.4.0", linux_job)
        self.assertNotIn("/../", linux_job)
        self.assertIn("NUCODE_NCS_INSTALL_ROOT: D:\\ncs", windows_job)
        self.assertIn('-NcsRoot "$env:NUCODE_NCS_INSTALL_ROOT"', windows_job)
        self.assertIn('--workspace "$env:NUCODE_NCS_ROOT"', windows_job)
        self.assertNotIn("\\..\\", windows_job)
        cache_step = windows_job.split(
            "- name: Restore Windows Builder cache", 1
        )[1].split("\n      - name:", 1)[0]
        self.assertIn("~\\AppData\\Local\\NUCODE\\NU54DK_Arduino_Core", cache_step)
        self.assertIn("steps.lock.outputs.windows_cache_key }}-builder-v1", cache_step)
        self.assertNotIn("NUCODE_NCS_INSTALL_ROOT", cache_step)
        self.assertNotIn("NUCODE_PREREQUISITE_STATE_ROOT", cache_step)

    ## @brief HIL workflow가 PR에서 실행되지 않고 secret·장치 lock을 요구하는지 검증합니다.
    def test_hil_is_manual_self_hosted_and_locked(self) -> None:
        path = REPOSITORY / ".github" / "workflows" / "m12-nu54dk-hil.yml"
        text = path.read_text(encoding="utf-8")
        self.assertRegex(text, r"(?m)^\s*workflow_dispatch:\s*$")
        self.assertNotIn("pull_request:", text)
        self.assertNotIn("push:", text)
        self.assertIn("[self-hosted, Windows, X64, nu54dk-hil]", text)
        self.assertIn("concurrency:", text)
        self.assertIn("secrets.NU54DK_HIL_AUTHORIZATION", text)

    ## @brief 모든 외부 action이 mutable tag가 아닌 40자리 commit으로 고정됐는지 검증합니다.
    def test_actions_are_pinned_to_commits(self) -> None:
        workflows = (REPOSITORY / ".github" / "workflows").glob("m12-*.yml")
        uses: list[str] = []
        for workflow in workflows:
            uses.extend(
                re.findall(r"(?m)^\s*-?\s*uses:\s*([^\s]+)\s*$", workflow.read_text(encoding="utf-8"))
            )
        self.assertTrue(uses)
        for reference in uses:
            self.assertRegex(reference, r"^[^@]+@[0-9a-f]{40}$", reference)

    ## @brief job-level env에서 사용할 수 없는 runner context를 차단합니다.
    def test_workflows_do_not_use_runner_context_in_job_env(self) -> None:
        for workflow in (REPOSITORY / ".github" / "workflows").glob("m12-*.yml"):
            text = workflow.read_text(encoding="utf-8")
            self.assertNotIn("${{ runner.temp }}", text, workflow.name)

    ## @brief artifact 경로에는 GitHub uploader가 거부하는 상위 경로 이동을 허용하지 않습니다.
    def test_artifact_paths_stay_inside_workspace(self) -> None:
        for workflow in (REPOSITORY / ".github" / "workflows").glob("m12-*.yml"):
            text = workflow.read_text(encoding="utf-8")
            for variable in ("M12_EVIDENCE", "HIL_EVIDENCE"):
                for value in re.findall(rf"(?m)^\s*{variable}:\s*(.+?)\s*$", text):
                    self.assertNotIn("/../", value, workflow.name)
                    self.assertNotIn("\\..\\", value, workflow.name)

    ## @brief container checkout에서도 gitlink 검증이 저장소 단위 safe.directory를 지정합니다.
    def test_gitlink_check_scopes_safe_directory(self) -> None:
        source = LOCK_SCRIPT.read_text(encoding="utf-8")
        self.assertIn('f"safe.directory={REPOSITORY}"', source)

    ## @brief M17 feasibility의 모든 Git 조회도 전역 변경 없이 대상 저장소만 신뢰합니다.
    def test_m17_feasibility_scopes_git_safe_directory(self) -> None:
        source = (
            REPOSITORY / "tools" / "ci" / "run_m17_feasibility.py"
        ).read_text(encoding="utf-8")
        self.assertIn('f"safe.directory={repository}"', source)
        self.assertNotIn('"config", "--global"', source)

    ## @brief CMake build record도 조회 대상 저장소 하나만 Git safe.directory로 지정합니다.
    def test_build_record_scopes_git_safe_directory(self) -> None:
        for relative in (
            "zephyr/CMakeLists.txt",
            "zephyr/cmake/write_build_record.cmake",
        ):
            source = (REPOSITORY / relative).read_text(encoding="utf-8")
            self.assertGreaterEqual(
                source.count('safe.directory=${directory}'), 4, relative
            )

    ## @brief Windows 2025에도 binary가 존재하는 exact Python을 사용합니다.
    def test_workflows_pin_available_python(self) -> None:
        for workflow in (REPOSITORY / ".github" / "workflows").glob("m12-*.yml"):
            text = workflow.read_text(encoding="utf-8")
            if "actions/setup-python@" in text:
                self.assertIn("python-version: 3.12.10", text, workflow.name)
                self.assertNotIn("python-version: 3.12.11", text, workflow.name)

    ## @brief 표준 주변장치·아날로그 library example이 canonical 위치에만 있는지 검증합니다.
    def test_example_discovery_inputs_are_canonical(self) -> None:
        expected = (
            "libraries/EEPROM/examples/EEPROMPersistence/EEPROMPersistence.ino",
            "libraries/LittleFS/examples/LittleFSPersistence/LittleFSPersistence.ino",
            "libraries/NUCODE_NU54DK/examples/Blink/Blink.ino",
            "libraries/NUCODE_NU54DK/examples/InterruptButton/InterruptButton.ino",
            "libraries/NUCODE_NU54DK/examples/AnalogReadA0/AnalogReadA0.ino",
            "libraries/NUCODE_NU54DK/examples/AnalogChannels/AnalogChannels.ino",
            "libraries/NUCODE_NU54DK/examples/AnalogResolution/AnalogResolution.ino",
            "libraries/NUCODE_NU54DK/examples/PWMFade/PWMFade.ino",
            "libraries/NUCODE_NU54DK/examples/DynamicPWM/DynamicPWM.ino",
            "libraries/NUCODE_NU54DK/examples/Serial1RuntimePins/Serial1RuntimePins.ino",
            "libraries/NUCODE_NU54DK/examples/SerialEcho/SerialEcho.ino",
            "libraries/NUCODE_NU54DK/examples/SPI00RuntimePins/SPI00RuntimePins.ino",
            "libraries/NUCODE_NU54DK/examples/ToneOutput/ToneOutput.ino",
            "libraries/NUCODE_NU54DK/examples/WireRuntimePins/WireRuntimePins.ino",
            "libraries/NUCODE_NU54DK/examples/BoardInfo/BoardInfo.ino",
            "libraries/NUCODE_NU54DK/examples/CounterAlarm/CounterAlarm.ino",
            "libraries/NUCODE_NU54DK/examples/SettingsStorage/SettingsStorage.ino",
            "libraries/NUCODE_NU54DK/examples/SystemOffWake/SystemOffWake.ino",
            "libraries/NUCODE_NU54DK/examples/WatchdogBasic/WatchdogBasic.ino",
            "libraries/SPI/examples/SPITransaction/SPITransaction.ino",
            "libraries/Wire/examples/WirePmicId/WirePmicId.ino",
            "libraries/Servo/examples/Sweep/Sweep.ino",
        )
        for relative in expected:
            self.assertTrue((REPOSITORY / relative).is_file(), relative)
        legacy_root = REPOSITORY / "examples"
        self.assertFalse(legacy_root.exists() and any(legacy_root.rglob("*.ino")))

    ## @brief Windows host gate가 AC-03 HIL protocol runner의 unit 계약도 실행하는지 검증합니다.
    def test_host_gate_runs_ac03_hil_runner_unit_contract(self) -> None:
        source = (REPOSITORY / "tools" / "ci" / "run_m12_gate.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('REPOSITORY / "tests" / "hil" / "nu54dk"', source)
        self.assertIn('"test_ac03_storage.py"', source)
        self.assertIn('"test_m24_uarte_onboard.py"', source)
        self.assertIn('"test_m24_twim_onboard.py"', source)

    ## @brief 대표 Twister build가 공유 compiler cache에 의존하지 않는지 검증합니다.
    def test_zephyr_build_disables_ccache(self) -> None:
        source = (REPOSITORY / "tools" / "ci" / "run_zephyr_build.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('"USE_CCACHE=0"', source)

    ## @brief 보드 없이 가능한 M14 production target 세 묶음이 원격 build gate에 포함되는지 검사합니다.
    def test_zephyr_build_includes_m14_production_and_hil_images(self) -> None:
        path = REPOSITORY / "tools" / "ci" / "run_zephyr_build.py"
        spec = importlib.util.spec_from_file_location("nu54_m14_build_gate", path)
        self.assertIsNotNone(spec)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertTrue(
            {
                ("m14_core_contract", "nucode.m14.core_contract"),
                ("m14_variant_contract", "nucode.m14.variant_contract"),
                ("m14_pin_hil", "nucode.m14.pin_hil"),
            }.issubset(set(module.SUITES))
        )

    ## @brief M23 identity와 공통 ownership target 계약이 대표 build에서 빠지지 않습니다.
    def test_zephyr_build_includes_m23_inventory_contract(self) -> None:
        path = REPOSITORY / "tools" / "ci" / "run_zephyr_build.py"
        spec = importlib.util.spec_from_file_location("nu54_m23_build_gate", path)
        self.assertIsNotNone(spec)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertIn(
            ("m23_inventory_contract", "nucode.m23.inventory_contract"),
            module.SUITES,
        )

    ## @brief M24 공통 serial-fabric semantic target이 v0.4 build에서 빠지지 않습니다.
    def test_zephyr_build_includes_m24_serial_fabric_contract(self) -> None:
        path = REPOSITORY / "tools" / "ci" / "run_zephyr_build.py"
        spec = importlib.util.spec_from_file_location("nu54_m24_build_gate", path)
        self.assertIsNotNone(spec)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertIn(
            ("m24_serial_fabric_contract", "nucode.m24.fabric"),
            module.SUITE_GROUPS["v0.4.0"],
        )
        self.assertIn(
            ("m24_uarte_driver_contract", "nucode.m24.uarte"),
            module.SUITE_GROUPS["v0.4.0"],
        )
        self.assertIn(
            ("m24_spi_driver_contract", "nucode.m24.spi"),
            module.SUITE_GROUPS["v0.4.0"],
        )
        self.assertIn(
            ("m24_twi_driver_contract", "nucode.m24.twi"),
            module.SUITE_GROUPS["v0.4.0"],
        )
        self.assertTrue(
            {
                ("m24_uarte_onboard_hil", "nucode.m24.uarte20_hil"),
                ("m24_uarte_onboard_hil", "nucode.m24.uarte21_hil"),
                ("m24_uarte_onboard_hil", "nucode.m24.uarte22_hil"),
                ("m24_uarte_onboard_hil", "nucode.m24.uarte30_hil"),
            }.issubset(set(module.SUITE_GROUPS["v0.4.0"]))
        )
        self.assertTrue(
            {
                ("m24_twim_onboard_hil", "nucode.m24.twim20_hil"),
                ("m24_twim_onboard_hil", "nucode.m24.twim21_hil"),
                ("m24_twim_onboard_hil", "nucode.m24.twim22_hil"),
            }.issubset(set(module.SUITE_GROUPS["v0.4.0"]))
        )
        self.assertIn(
            ("m25_analog_fabric_contract", "nucode.m25.analog"),
            module.SUITE_GROUPS["v0.4.0"],
        )
        self.assertIn(
            ("m25_event_fabric_contract", "nucode.m25.event"),
            module.SUITE_GROUPS["v0.4.0"],
        )
        self.assertIn(
            ("m25_stream_fabric_contract", "nucode.m25.stream"),
            module.SUITE_GROUPS["v0.4.0"],
        )
        self.assertIn(
            ("m25_onboard_hil", "nucode.m25.onboard_hil"),
            module.SUITE_GROUPS["v0.4.0"],
        )

    ## @brief AC-01 production contract와 자동 loopback HIL image가 원격 build gate에 포함되는지 검사합니다.
    def test_zephyr_build_includes_ac01_contract_and_hil_image(self) -> None:
        path = REPOSITORY / "tools" / "ci" / "run_zephyr_build.py"
        spec = importlib.util.spec_from_file_location("nu54_ac01_build_gate", path)
        self.assertIsNotNone(spec)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertTrue(
            {
                ("ac01_contract", "nucode.ac01.contract"),
                ("ac01_hil", "nucode.ac01.gpio_hil"),
            }.issubset(set(module.SUITES))
        )

    ## @brief AC-02A/B ownership·주변장치·아날로그 계약과 두 HIL image를 build gate에 포함합니다.
    def test_zephyr_build_includes_ac02_contracts_and_hil_images(self) -> None:
        path = REPOSITORY / "tools" / "ci" / "run_zephyr_build.py"
        spec = importlib.util.spec_from_file_location("nu54_ac02_build_gate", path)
        self.assertIsNotNone(spec)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertTrue(
            {
                ("ac02a_ownership_contract", "nucode.ac02a.ownership_contract"),
                ("ac02b_b2_contract", "nucode.ac02b.b2_contract"),
                ("ac02b_analog_contract", "nucode.ac02b.analog_contract"),
                ("ac02b_hil_dut", "nucode.ac02b.hil_dut"),
                ("ac02b_hil_peer", "nucode.ac02b.hil_peer"),
            }.issubset(set(module.SUITES))
        )

    ## @brief AC-03 storage contract와 reset persistence HIL image를 build gate에 포함합니다.
    def test_zephyr_build_includes_ac03_contract_and_hil_image(self) -> None:
        path = REPOSITORY / "tools" / "ci" / "run_zephyr_build.py"
        spec = importlib.util.spec_from_file_location("nu54_ac03_build_gate", path)
        self.assertIsNotNone(spec)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertTrue(
            {
                ("ac03_storage_contract", "nucode.ac03.storage_contract"),
                ("ac03_hil", "nucode.ac03.storage_hil"),
            }.issubset(set(module.SUITES))
        )

    ## @brief M15 board/system, 자동 HIL과 수동 wake image가 원격 build gate에 포함되는지 검사합니다.
    def test_zephyr_build_includes_m15_contract_and_system_off_image(self) -> None:
        path = REPOSITORY / "tools" / "ci" / "run_zephyr_build.py"
        spec = importlib.util.spec_from_file_location("nu54_m15_build_gate", path)
        self.assertIsNotNone(spec)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertTrue(
            {
                ("m15_board", "nucode.m15.board"),
                ("m15_hil", "nucode.m15.auto_hil"),
                ("m15_wake", "nucode.m15.wake"),
            }.issubset(set(module.SUITES))
        )

    ## @brief M16 HIL role image 두 개가 공통 build gate에서 명시적으로 분리되는지 검사합니다.
    def test_zephyr_build_has_fail_closed_m16_role_images(self) -> None:
        path = REPOSITORY / "tools" / "ci" / "run_zephyr_build.py"
        spec = importlib.util.spec_from_file_location("nu54_m16_build_gate", path)
        self.assertIsNotNone(spec)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(
            module.M16_ROLE_SUITES,
            (
                ("peripheral", "nucode.m16.ble_hil_peripheral"),
                ("central", "nucode.m16.ble_hil_central"),
            ),
        )
        self.assertTrue(
            {
                ("m16_ble_hil", "nucode.m16.ble_hil_peripheral"),
                ("m16_ble_hil", "nucode.m16.ble_hil_central"),
            }.issubset(set(module.SUITES))
        )
        source = path.read_text(encoding="utf-8")
        self.assertIn('"m16_role_builds": m16_role_builds', source)
        self.assertIn('records[0]["hex_sha256"] == records[1]["hex_sha256"]', source)
        cmake = (
            REPOSITORY / "tests" / "zephyr" / "m16_ble_hil" / "CMakeLists.txt"
        ).read_text(encoding="utf-8")
        self.assertIn("zephyr_get(M16_ROLE)", cmake)

    ## @brief M16 role 검증기가 central compile definition 누락을 fail-closed로 거부합니다.
    def test_m16_role_validator_rejects_missing_central_definition(self) -> None:
        path = REPOSITORY / "tools" / "ci" / "run_zephyr_build.py"
        spec = importlib.util.spec_from_file_location("nu54_m16_role_validator", path)
        self.assertIsNotNone(spec)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temporary:
            build = Path(temporary)
            image = build / "m16_ble_hil"
            (image / "zephyr").mkdir(parents=True)
            (build / "CMakeCache.txt").write_text(
                "M16_ROLE:UNINITIALIZED=central\n", encoding="utf-8"
            )
            (image / "compile_commands.json").write_text(
                json.dumps(
                    [
                        {
                            "file": str(
                                module.M16_APPLICATION / "src" / "main.cpp"
                            ),
                            "command": "arm-zephyr-eabi-g++ -c main.cpp",
                        }
                    ]
                ),
                encoding="utf-8",
            )
            (image / "build_info.yml").write_text(
                "source-dir: '"
                + module.M16_APPLICATION.as_posix()
                + "'\nqualifiers: 'nrf54l15/cpuapp/nu54dk'\n",
                encoding="utf-8",
            )
            (image / "nucode_arduino_core_build.yml").write_text(
                "board: 'nrf54l15dk'\n"
                "board_qualifiers: 'nrf54l15/cpuapp/nu54dk'\n",
                encoding="utf-8",
            )
            (image / "zephyr" / "zephyr.hex").write_bytes(b"hex")
            (image / "zephyr" / "zephyr.elf").write_bytes(b"elf")
            with self.assertRaisesRegex(module.BuildFailure, "compile definition"):
                module.validate_m16_role_build(build, "central")

    ## @brief Windows build가 MAX_PATH 위험을 실행 전에 차단하는지 검증합니다.
    def test_zephyr_build_requires_short_windows_outdir(self) -> None:
        path = REPOSITORY / "tools" / "ci" / "run_zephyr_build.py"
        spec = importlib.util.spec_from_file_location("nu54_short_outdir", path)
        self.assertIsNotNone(spec)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        source = path.read_text(encoding="utf-8")
        self.assertLessEqual(module.WINDOWS_OUTDIR_MAX_LENGTH, 8)
        self.assertIn("WINDOWS_OUTDIR_MAX_LENGTH", source)
        self.assertIn("validate_outdir_path(outdir)", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
