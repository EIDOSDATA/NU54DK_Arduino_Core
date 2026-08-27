#!/usr/bin/env python3
"""! @brief NU54DK Arduino CLI M5~M7 end-to-end 회귀를 실행합니다. """

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Sequence


FQBN = "nucode:zephyr:nu54dk"


class SmokeFailure(RuntimeError):
    """! @brief smoke test 계약 위반을 나타냅니다. """


## @brief Arduino IDE에 포함된 CLI 1.5.1의 기본 절대 경로를 반환합니다.
def default_cli() -> Path:
    return Path("C:/Program Files/Arduino IDE/resources/app/lib/backend/resources/arduino-cli.exe")


## @brief 실행 결과를 합친 UTF-8 text로 반환합니다.
def run(command: Sequence[str | Path], *, expect_success: bool = True) -> tuple[int, str]:
    result = subprocess.run(
        [str(value) for value in command],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if expect_success and result.returncode != 0:
        raise SmokeFailure(f"command failed ({result.returncode}): {' '.join(map(str, command))}\n{result.stdout}")
    return result.returncode, result.stdout


## @brief repository를 임시 Arduino hardware package로 복사합니다.
def stage_platform(repository: Path, user_root: Path) -> Path:
    platform = user_root / "hardware" / "nucode" / "zephyr"
    platform.mkdir(parents=True)
    for name in ("boards.txt", "platform.txt", "LICENSE"):
        shutil.copy2(repository / name, platform / name)
    for name in (
        "board_package",
        "cores",
        "dts",
        "libraries",
        "third_party",
        "tools",
        "variants",
        "zephyr",
    ):
        shutil.copytree(
            repository / name,
            platform / name,
            ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"),
        )
    return platform


## @brief Arduino CLI가 사용할 격리 config file을 생성합니다.
def write_cli_config(path: Path, user_root: Path) -> None:
    path.write_text(f"directories:\n  user: {user_root.as_posix()}\n", encoding="utf-8")


## @brief 공통 compile command를 만듭니다.
def compile_command(cli: Path, config: Path, build_path: Path, sketch: Path, libraries: Path | None = None) -> list[str | Path]:
    command: list[str | Path] = [
        cli,
        "compile",
        "--fqbn",
        FQBN,
        "--config-file",
        config,
        "--build-path",
        build_path,
    ]
    if libraries is not None:
        command.extend(("--libraries", libraries))
    command.append(sketch)
    return command


## @brief build context와 Zephyr artifact의 기본 계약을 검증합니다.
def assert_build(build_path: Path, project_name: str) -> dict:
    context_path = build_path / "nu54-zephyr" / "context.json"
    if not context_path.is_file():
        raise SmokeFailure(f"missing context: {context_path}")
    context = json.loads(context_path.read_text(encoding="utf-8"))
    if context.get("sysbuild") is not False:
        raise SmokeFailure("smoke build unexpectedly enabled sysbuild")
    for extension in ("elf", "hex", "bin", "map", "nu54-build.json"):
        artifact = build_path / f"{project_name}.{extension}"
        if not artifact.is_file() or artifact.stat().st_size == 0:
            raise SmokeFailure(f"missing artifact: {artifact}")
    return context


## @brief materialized Kconfig에서 boolean symbol의 최종 값을 읽습니다.
def read_kconfig_boolean(configuration: str, symbol: str) -> bool:
    lines = set(configuration.splitlines())
    if f"{symbol}=y" in lines:
        return True
    if f"# {symbol} is not set" in lines:
        return False
    raise SmokeFailure(f"Kconfig boolean symbol was not materialized: {symbol}")


## @brief live build record에서 작은따옴표로 감싼 필드를 읽습니다.
def read_build_record_field(record: Path, field: str) -> str:
    content = record.read_text(encoding="utf-8")
    match = re.search(rf"^  {re.escape(field)}: '((?:''|[^'])*)'$", content, re.MULTILINE)
    if match is None:
        raise SmokeFailure(f"live build record field was not materialized: {field}")
    return match.group(1).replace("''", "'")


## @brief CMake GLOB_RECURSE 선언에서 core root 기준 상대 경로 집합을 읽습니다.
def read_cmake_glob_scope(cmake_file: Path, collection: str, root_variable: str) -> set[str]:
    content = cmake_file.read_text(encoding="utf-8")
    match = re.search(
        rf"file\(GLOB_RECURSE\s+{re.escape(collection)}\b(.*?)\n\s*\)",
        content,
        re.DOTALL,
    )
    if match is None:
        raise SmokeFailure(f"CMake core input scope was not found: {cmake_file}: {collection}")
    return set(re.findall(rf'"\$\{{{re.escape(root_variable)}\}}/([^\"]+)"', match.group(1)))


## @brief 공개 header, library metadata, DTS binding이 live core provenance에 포함되는지 검증합니다.
def test_live_build_record_scope(context: dict, root: Path) -> None:
    platform = Path(context["platform_root"])
    configure_scope = read_cmake_glob_scope(
        platform / "zephyr" / "CMakeLists.txt",
        "NUCODE_CORE_BUILD_INPUTS",
        "NUCODE_ARDUINO_CORE_ROOT",
    )
    live_scope = read_cmake_glob_scope(
        platform / "zephyr" / "cmake" / "write_build_record.cmake",
        "core_inputs",
        "NUCODE_CORE_ROOT",
    )
    if live_scope != configure_scope:
        raise SmokeFailure(
            "configure/live core provenance scope mismatch: "
            f"configure={sorted(configure_scope)}, live={sorted(live_scope)}"
        )

    core = root / "build-record-core"
    application = root / "build-record-application"
    board = root / "build-record-board"
    record = root / "nucode_arduino_core_build.yml"
    fixture_files = (
        Path("cores/arduino/Arduino.h"),
        Path("dts/bindings/misc/nucode,arduino-adc-input.yaml"),
        Path("libraries/SPI/library.properties"),
        Path("third_party/ArduinoCore-API/api/ArduinoAPI.h"),
        Path("third_party/ArduinoCore-API.provenance.yml"),
        Path("variants/nu54dk/variant.h"),
        Path("zephyr/module.yml"),
        Path("zephyr/cmake/write_build_record.cmake"),
    )
    for relative_path in fixture_files:
        source = platform / relative_path
        destination = core / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    application.mkdir()
    board.mkdir()
    (application / "fixture.ino").write_text("void setup() {}\nvoid loop() {}\n", encoding="utf-8")
    (board / "fixture.dts").write_text("/dts-v1/;\n/ {};\n", encoding="utf-8")

    git = shutil.which("git")
    cmake = Path(context["toolchain_root"]) / "opt" / "bin" / "cmake.exe"
    if git is None or not cmake.is_file():
        raise SmokeFailure("live build record regression requires git and the NCS cmake executable")
    run((git, "init", core))
    run((git, "-C", core, "add", "cores", "dts", "libraries", "third_party", "variants", "zephyr"))
    run(
        (
            git,
            "-C",
            core,
            "-c",
            "user.name=NUCODE Smoke",
            "-c",
            "user.email=smoke@nucode.invalid",
            "commit",
            "-m",
            "빌드 기록 검증 기준선",
        )
    )

    writer = core / "zephyr" / "cmake" / "write_build_record.cmake"
    writer_command = (
        cmake,
        f"-DNUCODE_GIT_EXECUTABLE={Path(git).as_posix()}",
        f"-DNUCODE_CORE_ROOT={core.as_posix()}",
        f"-DNUCODE_BOARD_PACKAGE_ROOT={board.as_posix()}",
        f"-DNUCODE_APPLICATION_SOURCE_DIR={application.as_posix()}",
        f"-DNUCODE_NRF_DIR={(Path(context['ncs_root']) / 'nrf').as_posix()}",
        f"-DNUCODE_ZEPHYR_BASE={(Path(context['ncs_root']) / 'zephyr').as_posix()}",
        f"-DNUCODE_BUILD_RECORD={record.as_posix()}",
        "-DNUCODE_BOARD=nrf54l15dk/nrf54l15/cpuapp/nu54dk",
        "-DNUCODE_BOARD_QUALIFIERS=nrf54l15/cpuapp/nu54dk",
        "-DNUCODE_TOOLCHAIN_VARIANT=zephyr",
        f"-DNUCODE_TOOLCHAIN_PATH={Path(context['toolchain_root']).as_posix()}",
        f"-DNUCODE_CXX_COMPILER={Path(context['cxx_compiler']).as_posix()}",
        "-P",
        writer,
    )
    run(writer_command)
    baseline_hash = read_build_record_field(record, "core_source_sha256")
    baseline_revision = read_build_record_field(record, "core_revision")
    if baseline_hash == "unknown" or baseline_revision == "unknown" or baseline_revision.endswith("-dirty"):
        raise SmokeFailure("live build record baseline provenance is invalid")

    mutations = (
        (
            "public header",
            core / "cores" / "arduino" / "Arduino.h",
            "\n/** @brief 빌드 기록 변경 검증용 표식입니다. */\n".encode("utf-8"),
        ),
        (
            "library metadata",
            core / "libraries" / "SPI" / "library.properties",
            "\n# 빌드 기록 변경 검증용 표식입니다.\n".encode("utf-8"),
        ),
        (
            "DTS binding",
            core / "dts" / "bindings" / "misc" / "nucode,arduino-adc-input.yaml",
            "\n# 빌드 기록 변경 검증용 표식입니다.\n".encode("utf-8"),
        ),
    )
    for label, target, suffix in mutations:
        original = target.read_bytes()
        target.write_bytes(original + suffix)
        run(writer_command)
        changed_hash = read_build_record_field(record, "core_source_sha256")
        changed_revision = read_build_record_field(record, "core_revision")
        if changed_hash == baseline_hash:
            raise SmokeFailure(f"{label} mutation did not change live core_source_sha256")
        if not changed_revision.endswith("-dirty"):
            raise SmokeFailure(f"{label} mutation did not mark live core_revision dirty")

        target.write_bytes(original)
        run(writer_command)
        if read_build_record_field(record, "core_source_sha256") != baseline_hash:
            raise SmokeFailure(f"{label} mutation was not isolated from the next regression case")
        if read_build_record_field(record, "core_revision") != baseline_revision:
            raise SmokeFailure(f"{label} mutation did not restore the clean core revision")


## @brief board discovery와 Blink full build를 검증합니다.
def test_blink(cli: Path, config: Path, root: Path, repository: Path) -> None:
    _, listing = run((cli, "board", "listall", "NU54DK", "--config-file", config, "--json"))
    if FQBN not in listing:
        raise SmokeFailure("NU54DK FQBN was not discovered")
    build = root / "공백 경로" / "build-blink"
    run(compile_command(cli, config, build, repository / "examples" / "01.Basics" / "Blink"))
    assert_build(build, "Blink.ino")
    generated = (build / "sketch" / "Blink.ino.cpp").read_text(encoding="utf-8")
    prototype = generated.find("void writeBuiltinLed(bool high);")
    definition = generated.find("void writeBuiltinLed(bool high)\n{")
    if prototype < 0 or definition < 0 or prototype > definition:
        raise SmokeFailure("Arduino prototype generation was not preserved")


## @brief 직접 library와 depends library source가 manifest에 들어가는지 검증합니다.
def test_local_library(cli: Path, config: Path, root: Path, repository: Path) -> None:
    fixture = repository / "tests" / "arduino-cli"
    build = root / "build-library"
    run(compile_command(cli, config, build, fixture / "local_library", fixture / "libraries"))
    context = assert_build(build, "local_library.ino")
    sources = (Path(context["app_dir"]) / "sources.cmake").read_text(encoding="utf-8")
    for expected in ("local_library.ino.cpp", "LocalAccumulator.cpp", "LeafValue.cpp"):
        if expected not in sources:
            raise SmokeFailure(f"source manifest omitted {expected}")


## @brief sketch config와 overlay가 최종 Zephyr 출력에 반영되는지 검증합니다.
def test_config_overlay(cli: Path, config: Path, root: Path, repository: Path) -> None:
    sketch = repository / "tests" / "arduino-cli" / "config_overlay"
    build = root / "build-config-overlay"
    run(compile_command(cli, config, build, sketch))
    context = assert_build(build, "config_overlay.ino")
    zephyr = Path(context["zephyr_build_dir"]) / "zephyr"
    if "CONFIG_THREAD_NAME=y" not in (zephyr / ".config").read_text(encoding="utf-8"):
        raise SmokeFailure("prj.conf marker was not merged")
    devicetree = (zephyr / "zephyr.dts").read_text(encoding="utf-8")
    if "nucode-m5-fixture" not in devicetree or "fixture-value = < 0x36 >" not in devicetree:
        raise SmokeFailure("app.overlay marker was not merged")


## @brief 의도적 compile error가 nonzero와 원본 .ino line을 보존하는지 검증합니다.
def test_compile_error(cli: Path, config: Path, root: Path, repository: Path) -> None:
    sketch = repository / "tests" / "arduino-cli" / "compile_error"
    marker_line = next(
        index
        for index, line in enumerate((sketch / "compile_error.ino").read_text(encoding="utf-8").splitlines(), start=1)
        if "EXPECT_ERROR_LINE" in line
    )
    command = compile_command(cli, config, root / "build-error", sketch)
    command.insert(-1, "--verbose")
    return_code, output = run(
        command,
        expect_success=False,
    )
    if return_code == 0:
        raise SmokeFailure("intentional compile error unexpectedly succeeded")
    pattern = rf"compile_error\.ino:{marker_line}(?::\d+)?:.*nucode_intentional_compile_error"
    if not re.search(pattern, output):
        raise SmokeFailure(f"original .ino diagnostic line was not preserved\n{output}")


## @brief 두 sketch의 동시 build directory와 workspace가 서로 다른지 검증합니다.
def test_parallel(cli: Path, config: Path, root: Path, repository: Path) -> None:
    source = (repository / "examples" / "01.Basics" / "Blink" / "Blink.ino").read_text(encoding="utf-8")
    sketches: list[Path] = []
    for name in ("ParallelA", "ParallelB"):
        sketch = root / "sketches" / name
        sketch.mkdir(parents=True)
        (sketch / f"{name}.ino").write_text(source, encoding="utf-8")
        sketches.append(sketch)
    builds = [root / "build-parallel-a", root / "build-parallel-b"]
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(run, compile_command(cli, config, build, sketch))
            for build, sketch in zip(builds, sketches)
        ]
        for future in futures:
            future.result()
    contexts = [assert_build(build, f"{sketch.name}.ino") for build, sketch in zip(builds, sketches)]
    if contexts[0]["zephyr_build_dir"] == contexts[1]["zephyr_build_dir"]:
        raise SmokeFailure("parallel builds shared a Zephyr workspace")


## @brief sketch와 DTS module 입력 변경 때 같은 tree를 안전하게 재구성하는지 검증합니다.
def test_incremental(cli: Path, config: Path, root: Path, repository: Path) -> None:
    source = (repository / "examples" / "01.Basics" / "Blink" / "Blink.ino").read_text(encoding="utf-8")
    sketch = root / "sketches" / "Incremental"
    sketch.mkdir(parents=True)
    ino = sketch / "Incremental.ino"
    ino.write_text(source, encoding="utf-8")
    build = root / "build-incremental"
    command = compile_command(cli, config, build, sketch)
    run(command)
    first = assert_build(build, "Incremental.ino")
    ino.write_text(source.replace("delay(250);", "delay(251);", 1), encoding="utf-8")
    run(command)
    second = assert_build(build, "Incremental.ino")
    if first["zephyr_build_dir"] != second["zephyr_build_dir"]:
        raise SmokeFailure("incremental compile changed the Zephyr workspace")
    if second.get("pristine_configure_count") != 1:
        raise SmokeFailure("incremental compile repeated a pristine configure")

    platform = root / "user" / "hardware" / "nucode" / "zephyr"
    module_manifest = platform / "zephyr" / "module.yml"
    binding = platform / "dts" / "bindings" / "misc" / "nucode,arduino-adc-input.yaml"
    module_manifest.write_text(
        module_manifest.read_text(encoding="utf-8")
        + "\n# 모듈 지문 변경 검증용 표식입니다.\n",
        encoding="utf-8",
    )
    run(command)
    third = assert_build(build, "Incremental.ino")
    if third["zephyr_build_dir"] != second["zephyr_build_dir"]:
        raise SmokeFailure("module.yml fingerprint update changed the Zephyr workspace")
    if third.get("configuration_fingerprint") == second.get("configuration_fingerprint"):
        raise SmokeFailure("module.yml 변경이 fingerprint에 반영되지 않았습니다")
    if third.get("configure_skipped") is not False:
        raise SmokeFailure("module.yml 변경 뒤 configure가 생략되었습니다")
    if third.get("pristine_configure_count") != 1:
        raise SmokeFailure("module.yml fingerprint update repeated a pristine configure")

    binding.write_text(
        binding.read_text(encoding="utf-8")
        + "\n# DTS 바인딩 지문 변경 검증용 표식입니다.\n",
        encoding="utf-8",
    )
    run(command)
    fourth = assert_build(build, "Incremental.ino")
    if fourth["zephyr_build_dir"] != third["zephyr_build_dir"]:
        raise SmokeFailure("DTS binding fingerprint update changed the Zephyr workspace")
    if fourth.get("configuration_fingerprint") == third.get("configuration_fingerprint"):
        raise SmokeFailure("DTS binding 변경이 fingerprint에 반영되지 않았습니다")
    if fourth.get("configure_skipped") is not False:
        raise SmokeFailure("DTS binding 변경 뒤 configure가 생략되었습니다")
    if fourth.get("pristine_configure_count") != 1:
        raise SmokeFailure("DTS binding fingerprint update repeated a pristine configure")


## @brief M6 Serial과 GPIO interrupt 공개 예제를 Arduino CLI로 끝까지 빌드합니다.
def test_m6_examples(cli: Path, config: Path, root: Path, repository: Path) -> None:
    examples = (
        ("serial-echo", repository / "examples" / "04.Communication" / "SerialEcho", "SerialEcho.ino"),
        (
            "interrupt-button",
            repository / "examples" / "02.Digital" / "InterruptButton",
            "InterruptButton.ino",
        ),
    )
    for build_name, sketch, project_name in examples:
        build = root / f"build-m6-{build_name}"
        run(compile_command(cli, config, build, sketch))
        assert_build(build, project_name)


## @brief M7 주변장치 공개 예제와 sketch별 Zephyr 설정 병합을 검증합니다.
def test_m7_examples(cli: Path, config: Path, root: Path, repository: Path) -> None:
    peripheral_symbols = (
        "CONFIG_NUCODE_ARDUINO_WIRE",
        "CONFIG_NUCODE_ARDUINO_SPI",
        "CONFIG_NUCODE_ARDUINO_ADC",
        "CONFIG_NUCODE_ARDUINO_PWM",
    )
    examples = (
        (
            "wire-pmic-id",
            repository / "examples" / "04.Communication" / "WirePmicId",
            "WirePmicId.ino",
            "CONFIG_NUCODE_ARDUINO_WIRE",
            "nucode,arduino-wire",
        ),
        (
            "spi-transaction",
            repository / "examples" / "04.Communication" / "SPITransaction",
            "SPITransaction.ino",
            "CONFIG_NUCODE_ARDUINO_SPI",
            "nucode,arduino-spi",
        ),
        (
            "analog-read-a0",
            repository / "examples" / "03.Analog" / "AnalogReadA0",
            "AnalogReadA0.ino",
            "CONFIG_NUCODE_ARDUINO_ADC",
            "nucode,arduino-adc",
        ),
        (
            "pwm-fade",
            repository / "examples" / "03.Analog" / "PWMFade",
            "PWMFade.ino",
            "CONFIG_NUCODE_ARDUINO_PWM",
            "nucode,arduino-pwm",
        ),
    )
    for build_name, sketch, project_name, enabled_symbol, devicetree_marker in examples:
        if (
            not (sketch / project_name).is_file()
            or not (sketch / "prj.conf").is_file()
            or not (sketch / "app.overlay").is_file()
        ):
            raise SmokeFailure(f"incomplete M7 example: {sketch}")
        build = root / f"build-m7-{build_name}"
        run(compile_command(cli, config, build, sketch))
        context = assert_build(build, project_name)
        zephyr = Path(context["zephyr_build_dir"]) / "zephyr"
        configuration = (zephyr / ".config").read_text(encoding="utf-8")
        for symbol in peripheral_symbols:
            expected = symbol == enabled_symbol
            if read_kconfig_boolean(configuration, symbol) is not expected:
                expected_value = "y" if expected else "n"
                raise SmokeFailure(
                    f"M7 example Kconfig matrix mismatch: {sketch}: "
                    f"{symbol} expected {expected_value}"
                )

        materialized_overlay = (
            Path(context["app_dir"]) / "app.overlay"
        ).read_text(encoding="utf-8")
        sketch_overlay = (sketch / "app.overlay").read_text(encoding="utf-8").rstrip()
        if sketch_overlay not in materialized_overlay:
            raise SmokeFailure(f"M7 example app.overlay source was not merged: {sketch}")

        devicetree = (zephyr / "zephyr.dts").read_text(encoding="utf-8")
        if devicetree_marker not in devicetree:
            raise SmokeFailure(f"M7 example devicetree contract was not merged: {sketch}")

    test_live_build_record_scope(context, root)


## @brief 선택된 M5~M7 smoke test를 격리된 hardware root에서 실행합니다.
def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cli", type=Path, default=default_cli())
    parser.add_argument(
        "--tests",
        nargs="+",
        choices=("blink", "library", "config", "error", "parallel", "incremental", "m6", "m7"),
        default=("blink", "library", "config", "error", "parallel", "incremental", "m6", "m7"),
    )
    args = parser.parse_args(arguments)
    repository = Path(__file__).resolve().parents[2]
    cli = args.cli.resolve()
    if not cli.is_file():
        raise SmokeFailure(f"arduino-cli was not found: {cli}")

    with tempfile.TemporaryDirectory(prefix="n54m5-") as temporary_name:
        root = Path(temporary_name)
        user_root = root / "user"
        stage_platform(repository, user_root)
        config = root / "arduino-cli.yaml"
        write_cli_config(config, user_root)
        tests = {
            "blink": test_blink,
            "library": test_local_library,
            "config": test_config_overlay,
            "error": test_compile_error,
            "parallel": test_parallel,
            "incremental": test_incremental,
            "m6": test_m6_examples,
            "m7": test_m7_examples,
        }
        for name in args.tests:
            tests[name](cli, config, root, repository)
            print(f"PASS: {name}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SmokeFailure as error:
        print(f"FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
