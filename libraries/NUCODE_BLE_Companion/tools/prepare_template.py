#!/usr/bin/env python3
"""! @brief 고정 SDK source를 NU54DK 독립 application으로 생성·build합니다. flash는 지원하지 않습니다. """
from __future__ import annotations
import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

SDK_REVISION = "99553055607b2e9885fbc80ccd11fa9da81c2df0"
BOARD = "nrf54l15dk/nrf54l15/cpuapp/nu54dk"
KINDS = {
    "fast_pair_input": "fast_pair/input_device",
    "fast_pair_locator": "fast_pair/locator_tag",
    "enocean": "enocean",
    "mds": "peripheral_mds",
}
P256_ORDER = int("FFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551", 16)
SDK_DEBUG_KEY_HASHES = {
    "c02fbe85d9d1fd3dba50345b12456a0579bfeed427b9f59e8d606d229820ad9f",
    "6216d925383bb688565c925c3480ea7166106fea3d68c40da50078f22f398c5e",
}


def credentials(kind: str, document: dict, allow_test: bool = False) -> tuple[list[str], list[str]]:
    """! @brief credential·use case·환경을 검증하며 비밀을 오류 메시지에 포함하지 않습니다. """
    if not isinstance(document, dict) or document.get("schema_version") != 1 or document.get("use_case") != kind:
        raise ValueError("credential schema/use_case mismatch")
    environment = document.get("environment")
    if environment not in ("test", "production") or (environment == "test" and not allow_test):
        raise ValueError("test credential requires explicit --allow-test-credentials")
    if kind.startswith("fast_pair_"):
        allowed = {"schema_version", "use_case", "environment", "model_id", "anti_spoofing_key_base64"}
        if set(document) != allowed:
            raise ValueError("missing or unknown credential field")
        model = document["model_id"]
        encoded = document["anti_spoofing_key_base64"]
        if not isinstance(model, str) or not re.fullmatch(r"[0-9a-fA-F]{6}", model):
            raise ValueError("model_id must be exactly six hexadecimal digits")
        if model.lower() in ("000000", "ffffff", "123456", "abcdef"):
            raise ValueError("placeholder model_id is forbidden")
        if environment == "production" and model.lower() in ("2a410b", "4a436b"):
            raise ValueError("SDK debug model is forbidden for production")
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (TypeError, ValueError):
            raise ValueError("invalid anti-spoofing key encoding") from None
        if len(raw) != 32 or not 0 < int.from_bytes(raw, "big") < P256_ORDER:
            raise ValueError("anti-spoofing key is not a valid P-256 scalar")
        if environment == "production" and (len(set(raw)) < 8 or hashlib.sha256(raw).hexdigest() in SDK_DEBUG_KEY_HASHES):
            raise ValueError("placeholder or SDK debug anti-spoofing key is forbidden for production")
        return [f"SB_CONFIG_BT_FAST_PAIR_MODEL_ID=0x{model}",
                f'SB_CONFIG_BT_FAST_PAIR_ANTI_SPOOFING_PRIVATE_KEY="{encoded}"'], [encoded]
    if kind == "mds":
        if set(document) != {"schema_version", "use_case", "environment", "project_key", "device_id"}:
            raise ValueError("missing or unknown credential field")
        key, device = document["project_key"], document["device_id"]
        if not isinstance(key, str) or not re.fullmatch(r"[0-9a-fA-F]{32}", key) or len(set(key)) < 4:
            raise ValueError("project key must be a non-placeholder 32-digit hexadecimal value")
        if environment == "production" and key[:16].lower() == key[16:].lower():
            raise ValueError("repeated placeholder project key is forbidden for production")
        if not isinstance(device, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", device):
            raise ValueError("invalid device_id")
        if environment == "production" and any(word in device.lower() for word in ("dummy", "test", "example")):
            raise ValueError("placeholder device_id is forbidden for production")
        return [f'CONFIG_MEMFAULT_NCS_PROJECT_KEY="{key}"', f'CONFIG_MEMFAULT_NCS_DEVICE_ID="{device}"'], [key]
    raise ValueError("this template does not take credentials")


def source_manifest(path: Path) -> dict:
    """! @brief SDK sample 파일별 digest를 기록해 복제 원본을 추적합니다. """
    return {p.relative_to(path).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(path.rglob("*")) if p.is_file()}


def prepare(kind: str, sdk: Path, output: Path, credential_file: Path | None,
            allow_test: bool, repository: Path) -> tuple[dict, list[str]]:
    """! @brief 존재하지 않는 외부 디렉터리에 SDK sample과 board 설정을 준비합니다. """
    sdk, output, repository = sdk.resolve(), output.resolve(), repository.resolve()
    if output == repository or output.is_relative_to(repository) or output == sdk or output.is_relative_to(sdk):
        raise ValueError("output must be outside the repository and SDK")
    if output.exists():
        raise ValueError("output already exists; choose a new empty destination")
    actual = subprocess.check_output(["git", "-C", str(sdk / "nrf"), "rev-parse", "HEAD"], text=True).strip()
    if actual != SDK_REVISION:
        raise ValueError("NCS revision differs from the fixed 3.4.0 source")
    lock = json.loads((repository / "tools/ci/ncs-3.4.0.lock.json").read_text(encoding="utf-8"))
    zephyr = subprocess.check_output(["git", "-C", str(sdk / "zephyr"), "rev-parse", "HEAD"], text=True).strip()
    board = subprocess.check_output(["git", "-C", str(repository / "board_package/NU54DK_Zephyr_DTS"), "rev-parse", "HEAD"], text=True).strip()
    if zephyr != lock["zephyr"]["revision"] or board != lock["board"]["revision"]:
        raise ValueError("Zephyr or board source differs from the fixed lock")
    private_lines: list[str] = []
    secrets: list[str] = []
    if kind != "enocean":
        if credential_file is None:
            raise ValueError("external credentials are required; no SDK defaults are accepted")
        credential_file = credential_file.resolve()
        if credential_file.is_relative_to(repository) or credential_file.is_relative_to(sdk):
            raise ValueError("credentials must be outside the repository and SDK")
        private_lines, secrets = credentials(kind, json.loads(credential_file.read_text(encoding="utf-8")), allow_test)
    source = sdk / "nrf/samples/bluetooth" / KINDS[kind]
    original = source_manifest(source)
    target = output / "source"
    shutil.copytree(source, target)
    application_cmake = target / "CMakeLists.txt"
    cmake_text = application_cmake.read_text(encoding="utf-8")
    marker = "find_package(Zephyr REQUIRED"
    if cmake_text.count(marker) != 1:
        raise ValueError("fixed SDK application CMake anchor mismatch")
    application_cmake.write_text(cmake_text.replace(marker, "set(USE_CCACHE 0)\n" + marker, 1), encoding="utf-8")
    config_dir = target / ("configuration" if kind == "fast_pair_locator" else "")
    app_options = ["CONFIG_LOG_BACKEND_RTT=n"]
    sys_options = ["SB_CONFIG_BOOTLOADER_MCUBOOT=n", "SB_CONFIG_PARTITION_MANAGER=n"]
    if kind.startswith("fast_pair_"):
        # 생성물에서도 SDK에 내장된 debug credential 기본값을 사용하지 않습니다.
        kconfig = target / "Kconfig.sysbuild"
        text = kconfig.read_text(encoding="utf-8")
        text = re.sub(r'(config BT_FAST_PAIR_MODEL_ID\s*\n)\s*default[^\n]*', r'\1\tdefault 0', text)
        text = re.sub(r'(config BT_FAST_PAIR_ANTI_SPOOFING_PRIVATE_KEY\s*\n)\s*default[^\n]*', r'\1\tdefault ""', text)
        kconfig.write_text(text, encoding="utf-8")
        sys_options.extend(private_lines)
        board_dir = config_dir / "boards"
        board_dir.mkdir(exist_ok=True)
        base = "nrf54l15dk_nrf54l15_cpuapp"
        shutil.copyfile(Path(__file__).resolve().parents[1] / "templates/loaderless-fast-pair.overlay",
                        board_dir / (base + "_nu54dk.overlay"))
        app_options.extend(["CONFIG_USE_DT_CODE_PARTITION=y", "CONFIG_BT_FAST_PAIR_LOG_LEVEL_INF=y"])
        # NU54DK TX power 정밀 보정은 미검증이므로 DK 값을 보장된 교정값으로 안내하지 않습니다.
        upstream_board = source / ("configuration/boards" if kind == "fast_pair_locator" else "boards") / (base + ".conf")
        if upstream_board.exists():
            shutil.copyfile(upstream_board, board_dir / (base + "_nu54dk.conf"))
        if kind == "fast_pair_locator":
            sys_options.append("SB_CONFIG_APP_DFU=n")
            variant = target / "sysbuild/configuration" / (base + "_nu54dk")
            variant.mkdir(parents=True)
            (variant / "sysbuild.conf").write_text("# NU54DK loaderless: private-sysbuild.conf provides explicit options.\n", encoding="utf-8")
        if kind == "fast_pair_input":
            app_options.extend(["CONFIG_SHELL=y", "CONFIG_SHELL_BACKEND_SERIAL=y"])
            shutil.copyfile(Path(__file__).resolve().parents[1] / "templates/fast_pair_reset.c", target / "src/companion_reset.c")
            shutil.copyfile(Path(__file__).resolve().parents[1] / "templates/fast_pair_reset_guard.h", target / "src/companion_reset_guard.h")
            main_file = target / "src/main.c"
            main_text = main_file.read_text(encoding="utf-8")
            markers = ("static void advertising_start(void)\n{", "static void button_changed(uint32_t button_state, uint32_t has_changed)\n{")
            for marker in markers:
                if main_text.count(marker) != 1:
                    raise ValueError("fixed SDK reset guard source anchor mismatch")
                main_text = main_text.replace(marker, marker + "\n    if (companion_reset_locked)\n    {\n        return;\n    }\n", 1)
            main_text = main_text.replace("static struct bt_conn *peer;", "static struct bt_conn *peer;\nstatic bool companion_reset_locked;", 1)
            main_text += '\n#include "companion_reset_guard.h"\n'
            main_file.write_text(main_text, encoding="utf-8")
            with (target / "CMakeLists.txt").open("a", encoding="utf-8") as stream:
                stream.write("\ntarget_sources(app PRIVATE src/companion_reset.c)\n")
    else:
        app_options.extend(private_lines)
    (output / "private-sysbuild.conf").write_text("\n".join(sys_options) + "\n", encoding="utf-8")
    (output / "private-app.conf").write_text("\n".join(app_options) + "\n", encoding="utf-8")
    command = ["west", "build", "--sysbuild", "-b", BOARD, "-d", str(output / "build"), str(target), "--",
               f"-DBOARD_ROOT={(repository / 'board_package/NU54DK_Zephyr_DTS').as_posix()}",
               "-DUSE_CCACHE=0",
               f"-DSB_EXTRA_CONF_FILE={(output / 'private-sysbuild.conf').as_posix()}",
               f"-DEXTRA_CONF_FILE={(output / 'private-app.conf').as_posix()}"]
    manifest = {"schema_version": 1, "kind": kind, "ncs_revision": actual,
                "zephyr_revision": zephyr, "board_revision": board, "board": BOARD,
                "source_path": "nrf/samples/bluetooth/" + KINDS[kind], "upstream_files": original,
                "command": command, "automatic_flash": False, "external_interoperability": "NOT_RUN",
                "credential_mode": "none" if kind == "enocean" else json.loads(credential_file.read_text(encoding="utf-8"))["environment"],
                "generated_source_sha256": source_manifest(target),
                "known_boundaries": ["loaderless; no DFU", "no automatic upload or erase", "external peer NOT_RUN"]}
    (output / "template-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest, secrets


def main() -> int:
    """! @brief template 생성과 선택적 build만 수행하며 외부 credential을 출력하지 않습니다. """
    parser = argparse.ArgumentParser()
    parser.add_argument("--kind", choices=KINDS, required=True)
    parser.add_argument("--sdk-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--credentials", type=Path)
    parser.add_argument("--allow-test-credentials", action="store_true")
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--toolchain-root", type=Path)
    args = parser.parse_args()
    repository = Path(__file__).resolve().parents[3]
    try:
        manifest, secrets = prepare(args.kind, args.sdk_root, args.output, args.credentials,
                                    args.allow_test_credentials, repository)
        if args.build:
            if args.toolchain_root is None or args.toolchain_root.name != "dcbdc366a1":
                raise ValueError("fixed toolchain dcbdc366a1 is required for build")
            sys.path.insert(0, str(repository / "tools/nu54-builder/src"))
            from nu54_builder_impl.environment import apply_toolchain_environment
            environment = apply_toolchain_environment(args.toolchain_root.resolve())
            environment["ZEPHYR_BASE"] = str(args.sdk_root.resolve() / "zephyr")
            environment["CMAKE_BUILD_PARALLEL_LEVEL"] = "2"
            command = manifest["command"]
            command[0:1] = [str(args.toolchain_root.resolve() / "opt/bin/python.exe"), "-m", "west"]
            result = subprocess.run(command, cwd=args.sdk_root, env=environment, capture_output=True, timeout=1800)
            log = (result.stdout + result.stderr).decode("utf-8", errors="replace")
            for secret in secrets:
                log = log.replace(secret, "<redacted>")
            (args.output / "build.log").write_text(log, encoding="utf-8")
            manifest["build_exit_code"] = result.returncode
            manifest["artifacts"] = {p.relative_to(args.output).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                                     for p in sorted((args.output / "build").rglob("*"))
                                     if p.is_file() and (p.name == "zephyr.elf" or p.suffix == ".hex")}
            (args.output / "template-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            print(json.dumps({"kind": args.kind, "build_exit_code": result.returncode, "artifacts": manifest["artifacts"]}))
            return result.returncode
        print(json.dumps({"kind": args.kind, "manifest": str(args.output / "template-manifest.json")}))
        return 0
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        # JSON parse·subprocess 오류 내용에는 credential byte가 있을 수 있어 본문을 출력하지 않습니다.
        print(f"template rejected: {type(error).__name__}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
