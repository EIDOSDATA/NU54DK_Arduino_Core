#!/usr/bin/env python3
"""! @brief M33 ecosystem template 네 종류를 고정 NCS에서 build해 typed 증거를 만듭니다. """

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


KINDS = ("fast_pair_input", "fast_pair_locator", "enocean", "mds")
SEMANTICS = (
    "credential_fail_closed",
    "fast_pair_input",
    "fast_pair_locator",
    "enocean_mds_build",
)
SOURCE_PATHS = {
    "fast_pair_input": "nrf/samples/bluetooth/fast_pair/input_device",
    "fast_pair_locator": "nrf/samples/bluetooth/fast_pair/locator_tag",
    "enocean": "nrf/samples/bluetooth/enocean",
    "mds": "nrf/samples/bluetooth/peripheral_mds",
}
TEST_CREDENTIALS = {
    "fast_pair_input": {
        "schema_version": 1,
        "use_case": "fast_pair_input",
        "environment": "test",
        "model_id": "0badc1",
        "anti_spoofing_key_base64":
            "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAE=",
    },
    "fast_pair_locator": {
        "schema_version": 1,
        "use_case": "fast_pair_locator",
        "environment": "test",
        "model_id": "0badc1",
        "anti_spoofing_key_base64":
            "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAE=",
    },
    "mds": {
        "schema_version": 1,
        "use_case": "mds",
        "environment": "test",
        "project_key": "0123456789abcdef0123456789abcdef",
        "device_id": "local-build-test",
    },
}
NEGATIVE_TEST_IDS = (
    "test_credentials_reject_missing_unknown_and_invalid_fast_pair_values",
    "test_credentials_reject_production_debug_and_low_entropy_values",
    "test_mds_credentials_reject_invalid_and_placeholder_values",
    "test_prepare_rejects_missing_internal_or_drifted_inputs",
)


class TemplateBuildFailure(RuntimeError):
    """! @brief 네 template의 build·비밀 경계·증거 검증 실패입니다. """


def digest(path: Path) -> str:
    """! @brief 파일 byte의 SHA-256을 반환합니다. """

    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_identity(repository: Path) -> tuple[str, bool]:
    """! @brief 현재 Core full revision과 clean 상태를 읽습니다. """

    revision = subprocess.check_output(
        ["git", "-C", str(repository), "rev-parse", "HEAD"], text=True,
        timeout=30,
    ).strip()
    dirty = subprocess.check_output(
        ["git", "-C", str(repository), "status", "--porcelain=v1",
         "--untracked-files=all"], text=True, timeout=30
    ).strip()
    return revision, not dirty


def require(condition: bool, message: str) -> None:
    """! @brief 조건이 거짓이면 비밀을 포함하지 않는 오류로 중단합니다. """

    if not condition:
        raise TemplateBuildFailure(message)


def _expected_artifacts(kind: str) -> set[str]:
    """! @brief kind별 실제 build 산출물의 최소 exact 경로를 반환합니다. """

    result = {
        "build/source/zephyr/zephyr.elf",
        "build/source/zephyr/zephyr.hex",
    }
    if kind.startswith("fast_pair_"):
        result.add(
            "build/modules/nrf/subsys/bluetooth/fast_pair/"
            "fp_provisioning_data.hex"
        )
    return result


def source_manifest(root: Path) -> dict[str, str]:
    """! @brief 고정 SDK sample source의 파일별 SHA-256을 반환합니다. """

    return {
        path.relative_to(root).as_posix(): digest(path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def expected_build_command(kind: str, directory: Path, toolchain: Path,
                           repository: Path) -> list[str]:
    """! @brief prepare_template.py가 기록해야 하는 exact west build argv를 재구성합니다. """

    return [
        str(toolchain.resolve() / "opt/bin/python.exe"),
        "-m", "west", "build", "--sysbuild", "-b",
        "nrf54l15dk/nrf54l15/cpuapp/nu54dk",
        "-d", str(directory / "build"), str(directory / "source"), "--",
        f"-DBOARD_ROOT={(repository / 'board_package/NU54DK_Zephyr_DTS').as_posix()}",
        "-DUSE_CCACHE=0",
        f"-DSB_EXTRA_CONF_FILE={(directory / 'private-sysbuild.conf').as_posix()}",
        f"-DEXTRA_CONF_FILE={(directory / 'private-app.conf').as_posix()}",
    ]


def _run_negative_contract(repository: Path, output: Path) -> dict:
    """! @brief credential fail-closed 4개 exact unit을 별도 subprocess로 실행합니다. """

    command = [
        sys.executable,
        "-B",
        "-m",
        "unittest",
        "tests.host.test_m33_ecosystem_templates.TemplateCredentialTests",
        "-v",
    ]
    result = subprocess.run(
        command, cwd=repository, capture_output=True, timeout=120,
        shell=False, check=False
    )
    raw = result.stdout + result.stderr
    log = output / "credential-negative.log"
    log.write_bytes(raw)
    text = raw.decode("utf-8", errors="replace")
    require(result.returncode == 0 and "Ran 4 tests" in text and
            text.rstrip().endswith("OK") and
            all(test_id in text for test_id in NEGATIVE_TEST_IDS),
            "credential negative contract did not pass exact four tests")
    return {
        "path": log.name,
        "sha256": digest(log),
        "test_ids": list(NEGATIVE_TEST_IDS),
        "exit_code": result.returncode,
    }


def _validate_result(kind: str, directory: Path, manifest: dict,
                     secrets: tuple[str, ...], sdk: Path, toolchain: Path,
                     repository: Path, lock: dict) -> dict:
    """! @brief prepare_template의 lock·명령·산출물·redaction을 byte 단위로 검증합니다. """

    manifest_path = directory / "template-manifest.json"
    log_path = directory / "build.log"
    require(manifest_path.is_file() and log_path.is_file(),
            f"{kind} manifest or build log missing")
    require(manifest.get("schema_version") == 1 and
            manifest.get("kind") == kind and
            manifest.get("source_path") == SOURCE_PATHS[kind] and
            manifest.get("ncs_revision") == lock["ncs"]["revision"] and
            manifest.get("zephyr_revision") == lock["zephyr"]["revision"] and
            manifest.get("board_revision") == lock["board"]["revision"] and
            manifest.get("board") == "nrf54l15dk/nrf54l15/cpuapp/nu54dk" and
            manifest.get("automatic_flash") is False and
            manifest.get("external_interoperability") == "NOT_RUN" and
            manifest.get("credential_mode") ==
            ("none" if kind == "enocean" else "test") and
            manifest.get("build_exit_code") == 0 and
            manifest.get("upstream_files") == source_manifest(
                sdk / SOURCE_PATHS[kind]
            ) and
            isinstance(manifest.get("generated_source_sha256"), dict) and
            bool(manifest["generated_source_sha256"]),
            f"{kind} manifest contract mismatch")
    command = manifest.get("command")
    require(command == expected_build_command(
        kind, directory, toolchain, repository
    ),
            f"{kind} exact build command mismatch")
    artifacts = manifest.get("artifacts")
    require(isinstance(artifacts, dict) and
            set(artifacts) == _expected_artifacts(kind),
            f"{kind} artifact denominator mismatch")
    for relative, expected_sha256 in artifacts.items():
        path = directory / relative
        require(path.is_file() and digest(path) == expected_sha256,
                f"{kind} artifact byte mismatch")
    config_relative = "build/source/zephyr/.config"
    config = directory / config_relative
    require(config.is_file() and config.stat().st_size > 0,
            f"{kind} resolved config artifact missing")
    retained_artifacts = dict(artifacts)
    retained_artifacts[config_relative] = digest(config)
    log_bytes = log_path.read_bytes()
    require(all(secret.encode("utf-8") not in log_bytes for secret in secrets),
            f"{kind} build log contains credential bytes")
    return {
        "kind": kind,
        "status": "PASS",
        "exit_code": 0,
        "runtime": "NOT_RUN",
        "source_path": manifest["source_path"],
        "credential_mode": manifest["credential_mode"],
        "manifest": {"path": f"{kind}.manifest.json",
                     "sha256": digest(manifest_path)},
        "build_log": {"path": f"{kind}.build.log", "sha256": digest(log_path)},
        "command": command,
        "command_sha256": hashlib.sha256(json.dumps(
            command, separators=(",", ":")
        ).encode("utf-8")).hexdigest(),
        "upstream_files": manifest["upstream_files"],
        "generated_source_sha256": manifest["generated_source_sha256"],
        "artifacts": retained_artifacts,
        "automatic_flash": False,
        "external_interoperability": "NOT_RUN",
    }


def validate_retained_artifacts(row: dict, output: Path) -> None:
    """! @brief hash 문자열 대신 외부 evidence에 보존한 실제 ELF/HEX byte를 검증합니다. """

    artifacts = row.get("artifacts")
    files = row.get("artifact_files")
    require(isinstance(artifacts, dict) and isinstance(files, dict) and
            set(files) == set(artifacts),
            "retained template artifact denominator mismatch")
    for relative, reference in files.items():
        require(isinstance(reference, dict) and
                set(reference) == {"path", "sha256", "size", "confidentiality"} and
                Path(reference["path"]).name == reference["path"] and
                reference["sha256"] == artifacts[relative] and
                isinstance(reference["size"], int) and reference["size"] > 0 and
                reference["confidentiality"] in {
                    "external-test-credential-evidence",
                    "external-build-evidence",
                }, "retained template artifact reference mismatch")
        path = output / reference["path"]
        require(path.is_file() and path.stat().st_size == reference["size"] and
                digest(path) == reference["sha256"],
                "retained template artifact byte mismatch")


def execute(args: argparse.Namespace) -> dict:
    """! @brief 임시 private tree에서 네 build를 수행하고 공개 가능한 hash만 보존합니다. """

    repository = Path(__file__).resolve().parents[3]
    revision, clean = git_identity(repository)
    require(clean and revision == args.expected_core_revision,
            "template build requires current clean exact Core source")
    output = args.work_root.resolve()
    sdk = args.sdk_root.resolve()
    toolchain = args.toolchain_root.resolve()
    lock = json.loads(
        (repository / "tools/ci/ncs-3.4.0.lock.json").read_text(encoding="utf-8")
    )
    require(toolchain.name == lock["windows_toolchain"]["bundle_id"],
            "template build requires the fixed Windows toolchain bundle")
    require(not output.exists() and
            not output.is_relative_to(repository.resolve()) and
            not output.is_relative_to(sdk) and
            not output.is_relative_to(toolchain),
            "new external template evidence directory required")
    output.mkdir(parents=True)
    locked_paths = {
        "ncs": sdk / "nrf",
        "zephyr": sdk / "zephyr",
        "board": repository / "board_package/NU54DK_Zephyr_DTS",
    }
    locked_start = {name: git_identity(path) for name, path in locked_paths.items()}
    require(all(locked_start[name] == (lock[name]["revision"], True)
                for name in locked_paths),
            "template build requires clean exact NCS/Zephyr/board sources")
    negative = _run_negative_contract(repository, output)
    prepare = Path(__file__).resolve().with_name("prepare_template.py")
    results = []
    with tempfile.TemporaryDirectory(prefix="m33-template-private-",
                                     dir=output.parent) as temporary:
        private = Path(temporary)
        credential_root = private / "credentials"
        credential_root.mkdir()
        for kind, document in TEST_CREDENTIALS.items():
            (credential_root / f"{kind}.json").write_text(
                json.dumps(document), encoding="utf-8"
            )
        for kind in KINDS:
            build = private / kind
            command = [
                str(toolchain / "opt/bin/python.exe"),
                str(prepare),
                "--kind", kind,
                "--sdk-root", str(sdk),
                "--output", str(build),
                "--build",
                "--toolchain-root", str(toolchain),
            ]
            secret_values: tuple[str, ...] = ()
            if kind != "enocean":
                credential = credential_root / f"{kind}.json"
                command.extend(("--credentials", str(credential),
                                "--allow-test-credentials"))
                secret_values = tuple(
                    str(value) for key, value in TEST_CREDENTIALS[kind].items()
                    if key in {"anti_spoofing_key_base64", "project_key"}
                )
            result = subprocess.run(
                command, cwd=repository, capture_output=True, timeout=2100,
                shell=False, check=False
            )
            require(result.returncode == 0,
                    f"{kind} prepare/build subprocess failed")
            manifest_path = build / "template-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            row = _validate_result(
                kind, build, manifest, secret_values, sdk, toolchain,
                repository, lock,
            )
            manifest["artifacts"] = dict(row["artifacts"])
            manifest_path.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            row["manifest"]["sha256"] = digest(manifest_path)
            shutil.copyfile(manifest_path, output / row["manifest"]["path"])
            shutil.copyfile(build / "build.log", output / row["build_log"]["path"])
            require(digest(output / row["manifest"]["path"]) ==
                    row["manifest"]["sha256"] and
                    digest(output / row["build_log"]["path"]) ==
                    row["build_log"]["sha256"],
                    f"{kind} public sidecar copy mismatch")
            artifact_files = {}
            for relative, expected_sha256 in row["artifacts"].items():
                source = build / relative
                token = hashlib.sha256(relative.encode("utf-8")).hexdigest()[:12]
                target = output / f"{kind}.artifact.{token}.{source.name}"
                shutil.copyfile(source, target)
                require(digest(target) == expected_sha256 and target.stat().st_size > 0,
                        f"{kind} retained artifact byte mismatch")
                artifact_files[relative] = {
                    "path": target.name,
                    "sha256": expected_sha256,
                    "size": target.stat().st_size,
                    "confidentiality": ("external-test-credential-evidence"
                                        if kind != "enocean" else
                                        "external-build-evidence"),
                }
            row["artifact_files"] = artifact_files
            validate_retained_artifacts(row, output)
            results.append(row)
    end_revision, end_clean = git_identity(repository)
    require(end_clean and end_revision == revision,
            "Core source changed during template builds")
    locked_end = {name: git_identity(path) for name, path in locked_paths.items()}
    require(locked_end == locked_start,
            "NCS/Zephyr/board source changed during template builds")
    document = {
        "schema_version": 1,
        "kind": "m33_ecosystem_template_builds",
        "status": "PASS",
        "source_revision": revision,
        "source_clean": True,
        "ncs_revision": lock["ncs"]["revision"],
        "zephyr_revision": lock["zephyr"]["revision"],
        "board_revision": lock["board"]["revision"],
        "credential_negative": negative,
        "results": results,
        "external_interoperability": "NOT_RUN",
        "m33_dispatch_attestation": {
            "schema_version": 1,
            "kind": "m33_native_campaign_attestation",
            "campaign_id": "m33_ecosystem_templates",
            "source_revision": revision,
            "source_clean": True,
            "semantic_status": {token: "PASS" for token in SEMANTICS},
            "cycle_records": [
                {"cycle": index, "status": "PASS",
                 "semantics": {token: "PASS" for token in SEMANTICS}}
                for index in range(1, len(KINDS) + 1)
            ],
            "hardware": [],
        },
    }
    forbidden = tuple(
        str(value).encode("utf-8")
        for credentials in TEST_CREDENTIALS.values()
        for key, value in credentials.items()
        if key in {"anti_spoofing_key_base64", "project_key"}
    )
    public_bytes = json.dumps(
        document, ensure_ascii=False, sort_keys=True
    ).encode("utf-8")
    require(all(secret not in public_bytes for secret in forbidden) and
            all(secret not in path.read_bytes()
                for path in output.iterdir()
                if path.is_file() and ".artifact." not in path.name
                for secret in forbidden),
            "public template evidence contains credential bytes")
    evidence = output / "companion-build-results.json"
    require(not evidence.exists(), "template aggregate evidence overwrite refused")
    evidence.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8"
    )
    return document


def main() -> int:
    """! @brief flash 없이 네 template build-semantic aggregate를 생성합니다. """

    parser = argparse.ArgumentParser()
    parser.add_argument("--work-root", required=True, type=Path)
    parser.add_argument("--sdk-root", required=True, type=Path)
    parser.add_argument("--toolchain-root", required=True, type=Path)
    parser.add_argument("--expected-core-revision", required=True)
    args = parser.parse_args()
    try:
        result = execute(args)
    except (OSError, ValueError, subprocess.SubprocessError,
            TemplateBuildFailure) as error:
        print(f"M33_TEMPLATE_BUILD_FAIL: {type(error).__name__}", file=sys.stderr)
        return 1
    print(f"M33_TEMPLATE_BUILD_STATUS={result['status']};KINDS={len(result['results'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
