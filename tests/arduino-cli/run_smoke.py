#!/usr/bin/env python3
"""! @brief NU54DK Arduino CLI M5~M9 end-to-end 회귀를 실행합니다. """

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
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
ARDUINO_TESTS = (
    "blink",
    "library",
    "config",
    "error",
    "parallel",
    "incremental",
    "m6",
    "m7",
    "m8",
    "m9",
    "m11",
    "m15",
    "m16",
    "m19m20",
    "m21",
    "ac02b",
    "ac03",
    "examples",
)
DEFAULT_TESTS = tuple(test for test in ARDUINO_TESTS if test != "incremental")
ARDUINO_GROUPS = {
    "v0.1.0": ("blink", "m6", "m7"),
    "v0.2.0": ("m15", "m16"),
    "v0.3.0": ("m19m20", "m21", "ac02b", "ac03", "examples"),
}
ARDUINO_MATRIX_GROUPS = {
    "v0.1.0": ARDUINO_GROUPS["v0.1.0"],
    "v0.2.0": ARDUINO_GROUPS["v0.2.0"],
    "v0.3.0-ble": ("m19m20", "m21"),
    "v0.3.0-compat": ("ac02b", "ac03", "examples"),
}
ARDUINO_SELECTIONS = {**ARDUINO_GROUPS, **ARDUINO_MATRIX_GROUPS}


## @brief NU54DK 보드 공통 예제 라이브러리의 저장소 경로를 반환합니다.
def board_examples(repository: Path) -> Path:
    return repository / "libraries" / "NUCODE_NU54DK" / "examples"


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


## @brief 임시 source snapshot을 독립 Git repository로 초기화합니다.
def initialize_snapshot_repository(root: Path, label: str) -> None:
    git = shutil.which("git")
    if git is None:
        raise SmokeFailure("source snapshot regression requires git")
    run((git, "init", root))
    run((git, "-C", root, "add", "--all"))
    run(
        (
            git,
            "-C",
            root,
            "-c",
            "user.name=NUCODE Smoke",
            "-c",
            "user.email=smoke@nucode.invalid",
            "commit",
            "-m",
            f"{label} 회귀 snapshot",
        )
    )


## @brief source repository를 임시 Arduino hardware 개발 checkout으로 복사합니다.
def stage_platform(repository: Path, user_root: Path) -> Path:
    platform = user_root / "hardware" / "nucode" / "zephyr"
    platform.mkdir(parents=True)
    for name in (".gitattributes", "boards.txt", "platform.txt", "post_install.bat", "LICENSE"):
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
    initialize_snapshot_repository(
        platform / "board_package" / "NU54DK_Zephyr_DTS", "NU54DK board"
    )
    initialize_snapshot_repository(platform, "NU54DK Arduino Core")
    return platform


## @brief 추출한 배포 package를 byte 변경 없이 임시 Arduino hardware로 복사합니다.
def stage_packaged_platform(package_root: Path, user_root: Path) -> Path:
    package_root = package_root.resolve()
    if not (package_root / "release-manifest.json").is_file():
        raise SmokeFailure(
            f"extracted package root has no release-manifest.json: {package_root}"
        )
    if (package_root / ".git").exists():
        raise SmokeFailure(f"--platform-root requires a Git-less package: {package_root}")

    platform = user_root / "hardware" / "nucode" / "zephyr"
    platform.parent.mkdir(parents=True)
    shutil.copytree(
        package_root,
        platform,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    return platform


## @brief Arduino CLI가 사용할 data·download·user 경로를 모두 격리합니다.
def write_cli_config(
    path: Path,
    user_root: Path,
    data_root: Path,
    downloads_root: Path,
) -> None:
    path.write_text(
        "directories:\n"
        f"  data: {data_root.as_posix()}\n"
        f"  downloads: {downloads_root.as_posix()}\n"
        f"  user: {user_root.as_posix()}\n",
        encoding="utf-8",
    )


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


## @brief 생성된 devicetree가 NU54DK 외부 LFXO 부하 커패시터를 사용하는지 검사합니다.
def assert_external_lfxo(devicetree_path: Path) -> None:
    devicetree = devicetree_path.read_text(encoding="utf-8")
    match = re.search(r"\blfxo:\s+lfxo\s*\{(?P<body>.*?)^\s*\};", devicetree, re.DOTALL | re.MULTILINE)
    if match is None:
        raise SmokeFailure("generated devicetree has no labeled LFXO node")
    body = match.group("body")
    if 'load-capacitors = "external";' not in body:
        raise SmokeFailure("generated LFXO does not use external load capacitors")
    if "load-capacitance-femtofarad" in body:
        raise SmokeFailure("generated LFXO still enables an internal load capacitor")


## @brief build context, Zephyr artifact와 NU54DK LFXO의 기본 계약을 검증합니다.
def assert_build(build_path: Path, project_name: str) -> dict:
    context_path = build_path / "nu54-zephyr" / "context.json"
    if not context_path.is_file():
        raise SmokeFailure(f"missing context: {context_path}")
    context = json.loads(context_path.read_text(encoding="utf-8"))
    if context.get("sysbuild") is not False:
        raise SmokeFailure("smoke build unexpectedly enabled sysbuild")
    cache_key = context.get("cache_key")
    cache_dir = Path(str(context.get("cache_dir", "")))
    if not isinstance(cache_key, str) or not re.fullmatch(r"[0-9a-f]{64}", cache_key):
        raise SmokeFailure("build context has no full M9 cache key")
    assert_external_lfxo(Path(context["zephyr_build_dir"]) / "zephyr" / "zephyr.dts")
    if not cache_dir.is_dir():
        raise SmokeFailure(f"persistent cache directory is missing: {cache_dir}")
    for metadata in ("input-manifest.json", "state.json", "access.json"):
        if not (cache_dir / metadata).is_file():
            raise SmokeFailure(f"cache metadata is missing: {cache_dir / metadata}")
    for extension in ("elf", "hex", "bin", "map", "nu54-build.json"):
        artifact = build_path / f"{project_name}.{extension}"
        if not artifact.is_file() or artifact.stat().st_size == 0:
            raise SmokeFailure(f"missing artifact: {artifact}")
    manifest_path = build_path / f"{project_name}.nu54-build.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("cache", {}).get("key") != cache_key:
        raise SmokeFailure("artifact manifest cache key does not match the session context")
    input_manifest = json.loads((cache_dir / "input-manifest.json").read_text(encoding="utf-8"))
    canonical_input = json.dumps(
        input_manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    if hashlib.sha256(canonical_input).hexdigest() != cache_key:
        raise SmokeFailure("cache input manifest does not reproduce the session cache key")
    for extension in ("elf", "hex", "bin", "map"):
        artifact = build_path / f"{project_name}.{extension}"
        record = manifest.get("artifacts", {}).get(extension, {})
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        if record.get("path") != artifact.resolve().as_posix():
            raise SmokeFailure(f"artifact manifest path mismatch: {artifact}")
        if record.get("size") != artifact.stat().st_size or record.get("sha256") != digest:
            raise SmokeFailure(f"artifact manifest integrity mismatch: {artifact}")
    source_inputs = manifest.get("source_inputs")
    if not isinstance(source_inputs, dict) or not isinstance(source_inputs.get("sources"), list):
        raise SmokeFailure("artifact manifest has no M9 source provenance")
    for record in source_inputs["sources"]:
        if not isinstance(record, dict):
            raise SmokeFailure("artifact source provenance record is not an object")
        source = Path(str(record.get("source_path", "")))
        compiled = Path(str(record.get("compiled_path", "")))
        if not source.is_file() or not compiled.is_file():
            raise SmokeFailure(f"artifact source provenance path is missing: {record}")
        if hashlib.sha256(source.read_bytes()).hexdigest() != record.get("sha256"):
            raise SmokeFailure(f"artifact source provenance hash mismatch: {source}")
    build_record = source_inputs.get("live_build_record")
    if not isinstance(build_record, dict):
        raise SmokeFailure("artifact manifest has no live build record provenance")
    build_record_path = Path(str(build_record.get("path", "")))
    if (
        not build_record_path.is_file()
        or hashlib.sha256(build_record_path.read_bytes()).hexdigest()
        != build_record.get("sha256")
    ):
        raise SmokeFailure("live build record provenance hash mismatch")
    return context


## @brief Arduino build manifest에 기록된 artifact SHA-256을 읽습니다.
def artifact_hash(build_path: Path, project_name: str, extension: str = "elf") -> str:
    manifest = json.loads(
        (build_path / f"{project_name}.nu54-build.json").read_text(encoding="utf-8")
    )
    value = manifest.get("artifacts", {}).get(extension, {}).get("sha256")
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise SmokeFailure(f"artifact hash is missing: {project_name}.{extension}")
    return value


## @brief 현재 artifact manifest의 source provenance 한 건을 원본 경로로 찾습니다.
def source_provenance(build_path: Path, project_name: str, source: Path) -> dict:
    manifest = json.loads(
        (build_path / f"{project_name}.nu54-build.json").read_text(encoding="utf-8")
    )
    matches = [
        record
        for record in manifest.get("source_inputs", {}).get("sources", [])
        if isinstance(record, dict)
        and Path(str(record.get("source_path", ""))).resolve() == source.resolve()
    ]
    if len(matches) != 1:
        raise SmokeFailure(f"source provenance is not unique: {source}: {matches}")
    return matches[0]


## @brief M9 context에서 공개 가능한 성능·cache 증거 field만 추출합니다.
def m9_snapshot(label: str, context: dict) -> dict:
    cache_dir = Path(context["cache_dir"])
    cache_bytes = sum(
        path.stat().st_size
        for path in cache_dir.rglob("*")
        if path.is_file()
    )
    fields = (
        "cache_key",
        "cache_dir",
        "configure_reason",
        "configure_skipped",
        "pristine_configure_count",
        "recovery_count",
        "source_manifest_changed",
        "configure_duration_seconds",
        "link_configure_duration_seconds",
        "build_duration_seconds",
        "ccache_stats_delta",
    )
    snapshot = {"label": label, "cache_bytes": cache_bytes}
    snapshot.update({field: context.get(field) for field in fields})
    return snapshot


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
    run(compile_command(cli, config, build, board_examples(repository) / "Blink"))
    assert_build(build, "Blink.ino")
    generated = (build / "sketch" / "Blink.ino.cpp").read_text(encoding="utf-8")
    prototype = generated.find("void writeBuiltinLed(bool high);")
    definition = generated.find("void writeBuiltinLed(bool high)\n{")
    if prototype < 0 or definition < 0 or prototype > definition:
        raise SmokeFailure("Arduino prototype generation was not preserved")


## @brief 여러 INO 탭의 결합, prototype 생성과 최종 Full Zephyr link를 검증합니다.
def test_multi_tab(cli: Path, config: Path, root: Path, repository: Path) -> None:
    sketch = repository / "tests" / "arduino-cli" / "multi_tab"
    build = root / "build-m11-multi-tab"
    run(compile_command(cli, config, build, sketch))
    context = assert_build(build, "multi_tab.ino")

    generated = build / "sketch" / "multi_tab.ino.cpp"
    content = generated.read_text(encoding="utf-8")
    required_markers = (
        "multiTabResult = combineTabValues(20U);",
        "unsigned int tabBaseValue(void)",
        "unsigned int combineTabValues(unsigned int value)",
    )
    for marker in required_markers:
        if marker not in content:
            raise SmokeFailure(f"multi-tab generated source omitted marker: {marker}")

    prototype = content.find("unsigned int combineTabValues(unsigned int value);")
    call = content.find("multiTabResult = combineTabValues(20U);")
    definition = content.find("unsigned int combineTabValues(unsigned int value)\n{")
    if prototype < 0 or call < 0 or definition < 0 or not (prototype < call < definition):
        raise SmokeFailure("secondary INO tab prototype/order contract was not preserved")

    sources = (Path(context["app_dir"]) / "sources.cmake").read_text(encoding="utf-8")
    if "multi_tab.ino.cpp" not in sources:
        raise SmokeFailure("multi-tab generated translation unit was not linked into Zephyr")


## @brief Arduino 공개 API와 직접 Zephyr API를 함께 쓰는 sketch를 검증합니다.
def test_zephyr_coexist(cli: Path, config: Path, root: Path, repository: Path) -> None:
    sketch = repository / "tests" / "arduino-cli" / "zephyr_coexist"
    build = root / "build-m11-zephyr-coexist"
    run(compile_command(cli, config, build, sketch))
    context = assert_build(build, "zephyr_coexist.ino")

    generated = (build / "sketch" / "zephyr_coexist.ino.cpp").read_text(
        encoding="utf-8"
    )
    for marker in (
        "#include <Arduino.h>",
        "#include <zephyr/kernel.h>",
        "k_uptime_get()",
        "k_sleep(K_MSEC(1))",
        "digitalWrite(LED_BUILTIN",
        "unsigned int zephyrMixedValue(unsigned int value);",
        "zephyrMixedValue(41U)",
    ):
        if marker not in generated:
            raise SmokeFailure(f"Arduino/Zephyr coexist generated source omitted marker: {marker}")

    prototype = generated.find("unsigned int zephyrMixedValue(unsigned int value);")
    call = generated.find("zephyrMixedValue(41U)")
    definition = generated.find(
        "NU54_M11_VALUE_TYPE zephyrMixedValue(NU54_M11_VALUE_TYPE value)"
    )
    if prototype < 0 or call < 0 or definition < 0 or not (prototype < call < definition):
        raise SmokeFailure("Zephyr coexist macro prototype/order contract was not preserved")

    configuration = (
        Path(context["zephyr_build_dir"]) / "zephyr" / ".config"
    ).read_text(encoding="utf-8")
    if "CONFIG_NUCODE_ARDUINO_CORE=y" not in configuration:
        raise SmokeFailure("Arduino/Zephyr coexist sketch disabled the Arduino Core")


## @brief M11의 sketch 입력·Zephyr 공존 회귀 fixture를 순서대로 실행합니다.
def test_m11_fixtures(cli: Path, config: Path, root: Path, repository: Path) -> None:
    test_multi_tab(cli, config, root, repository)
    test_zephyr_coexist(cli, config, root, repository)


## @brief 직접 library와 depends library source가 manifest에 들어가는지 검증합니다.
def test_local_library(cli: Path, config: Path, root: Path, repository: Path) -> None:
    fixture = repository / "tests" / "arduino-cli"
    staged_fixture = root / "m9-library-fixture"
    sketch = staged_fixture / "local_library"
    libraries = root / "user" / "libraries"
    shutil.copytree(fixture / "local_library", sketch)
    shutil.copytree(fixture / "libraries", libraries)
    library_header = libraries / "LocalAccumulator" / "src" / "LocalAccumulator.h"
    library_source = libraries / "LocalAccumulator" / "src" / "LocalAccumulator.cpp"
    build = root / "build-library"
    command = compile_command(cli, config, build, sketch)
    run(command)
    context = assert_build(build, "local_library.ino")
    baseline_elf = artifact_hash(build, "local_library.ino")
    sources = (Path(context["app_dir"]) / "sources.cmake").read_text(encoding="utf-8")
    for expected in ("local_library.ino.cpp", "LocalAccumulator.cpp", "LeafValue.cpp"):
        if expected not in sources:
            raise SmokeFailure(f"source manifest omitted {expected}")
    library_header.write_text(
        library_header.read_text(encoding="utf-8").replace(
            "int localAccumulate(int value);",
            "#define LOCAL_ACCUMULATOR_BIAS 0\n\nint localAccumulate(int value);",
        ),
        encoding="utf-8",
    )
    library_source.write_text(
        library_source.read_text(encoding="utf-8").replace(
            "return value + leafValue();",
            "return value + leafValue() + LOCAL_ACCUMULATOR_BIAS + 1;",
        ),
        encoding="utf-8",
    )
    run(command)
    edited = assert_build(build, "local_library.ino")
    if edited["cache_key"] != context["cache_key"]:
        raise SmokeFailure("library source body edit changed the M9 cache key")
    if edited["zephyr_build_dir"] != context["zephyr_build_dir"]:
        raise SmokeFailure("library source body edit changed the Zephyr build tree")
    if edited.get("pristine_configure_count") != 1:
        raise SmokeFailure("library source edit repeated a pristine configure")
    if artifact_hash(build, "local_library.ino") == baseline_elf:
        raise SmokeFailure("library source edit was not reflected in the final ELF")
    if int(edited.get("ccache_stats_delta", {}).get("cache_miss", 0)) < 1:
        raise SmokeFailure("library source edit did not compile a changed source")
    edited_source_record = source_provenance(
        build, "local_library.ino", library_source
    )
    if Path(edited_source_record["compiled_path"]).resolve() != library_source.resolve():
        raise SmokeFailure("external library source did not retain its private-header directory")
    if edited_source_record["sha256"] != hashlib.sha256(library_source.read_bytes()).hexdigest():
        raise SmokeFailure("edited library source hash was not recorded in provenance")

    source_edited_elf = artifact_hash(build, "local_library.ino")
    library_header.write_text(
        library_header.read_text(encoding="utf-8").replace(
            "#define LOCAL_ACCUMULATOR_BIAS 0", "#define LOCAL_ACCUMULATOR_BIAS 2"
        ),
        encoding="utf-8",
    )
    run(command)
    header_edited = assert_build(build, "local_library.ino")
    if header_edited["cache_key"] != context["cache_key"]:
        raise SmokeFailure("library header edit changed the M9 cache key")
    if header_edited["zephyr_build_dir"] != context["zephyr_build_dir"]:
        raise SmokeFailure("library header edit changed the Zephyr build tree")
    if header_edited.get("pristine_configure_count") != 1:
        raise SmokeFailure("library header edit repeated a pristine configure")
    if artifact_hash(build, "local_library.ino") == source_edited_elf:
        raise SmokeFailure("library header edit was not reflected in the final ELF")
    if int(header_edited.get("ccache_stats_delta", {}).get("cache_miss", 0)) < 1:
        raise SmokeFailure("library header dependency edit did not rebuild a source")

    # 같은 Arduino object 이름에서 library root만 바뀌어도 이전 record를 재사용하지 않아야 합니다.
    alternate_libraries = staged_fixture / "alternate-libraries"
    shutil.copytree(libraries, alternate_libraries)
    retired_libraries = staged_fixture / "retired-libraries"
    libraries.rename(retired_libraries)
    alternate_source = (
        alternate_libraries / "LocalAccumulator" / "src" / "LocalAccumulator.cpp"
    )
    alternate_source.write_text(
        alternate_source.read_text(encoding="utf-8").replace(
            "LOCAL_ACCUMULATOR_BIAS + 1;", "LOCAL_ACCUMULATOR_BIAS + 3;"
        ),
        encoding="utf-8",
    )
    previous_elf = artifact_hash(build, "local_library.ino")
    run(compile_command(cli, config, build, sketch, alternate_libraries))
    switched = assert_build(build, "local_library.ino")
    if switched["cache_key"] != context["cache_key"]:
        raise SmokeFailure("library search root switch changed the M9 cache key")
    if switched["zephyr_build_dir"] != context["zephyr_build_dir"]:
        raise SmokeFailure("library search root switch changed the Zephyr build tree")
    if artifact_hash(build, "local_library.ino") == previous_elf:
        raise SmokeFailure("library search root switch reused a stale source record")
    switched_record = source_provenance(
        build, "local_library.ino", alternate_source
    )
    if Path(switched_record["compiled_path"]).resolve() != alternate_source.resolve():
        raise SmokeFailure("library search root switch retained the previous source path")


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
    source = (board_examples(repository) / "Blink" / "Blink.ino").read_text(encoding="utf-8")
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


## @brief M9 cache hit, source edit, key invalidation과 손상 복구를 실제 build로 검증합니다.
def test_incremental(cli: Path, config: Path, root: Path, repository: Path) -> None:
    evidence: list[dict] = []
    source = (board_examples(repository) / "Blink" / "Blink.ino").read_text(encoding="utf-8")
    sketch = root / "sketches" / "Incremental"
    sketch.mkdir(parents=True)
    ino = sketch / "Incremental.ino"
    ino.write_text(source, encoding="utf-8")
    build = root / "build-incremental"
    command = compile_command(cli, config, build, sketch)
    run(command)
    first = assert_build(build, "Incremental.ino")
    cold_elf = artifact_hash(build, "Incremental.ino")
    evidence.append(m9_snapshot("cold", first))
    if first.get("configure_skipped") is not False:
        raise SmokeFailure("cold build unexpectedly skipped the first configure")
    if first.get("pristine_configure_count") != 1:
        raise SmokeFailure("cold build did not run exactly one pristine configure")

    run(command)
    unchanged = assert_build(build, "Incremental.ino")
    if artifact_hash(build, "Incremental.ino") != cold_elf:
        raise SmokeFailure("no-change build changed the final ELF")
    evidence.append(m9_snapshot("no-change", unchanged))
    if unchanged["cache_key"] != first["cache_key"]:
        raise SmokeFailure("no-change build changed the M9 cache key")
    if unchanged["zephyr_build_dir"] != first["zephyr_build_dir"]:
        raise SmokeFailure("no-change build changed the persistent Zephyr tree")
    if unchanged.get("configure_skipped") is not True:
        raise SmokeFailure("no-change build repeated prepare configure")
    if unchanged.get("source_manifest_changed") is not False:
        raise SmokeFailure("no-change build rewrote sources.cmake")
    ccache_delta = unchanged.get("ccache_stats_delta", {})
    for required_stat in ("cache_miss", "direct_cache_hit", "preprocessed_cache_hit"):
        if required_stat not in ccache_delta:
            raise SmokeFailure(f"no-change build has no ccache statistic: {required_stat}")
    compile_activity = sum(
        int(ccache_delta.get(key, 0))
        for key in ("cache_miss", "direct_cache_hit", "preprocessed_cache_hit")
    )
    if compile_activity != 0:
        raise SmokeFailure(f"no-change build invoked compiler through ccache: {ccache_delta}")

    ino.write_text(source.replace("delay(250);", "delay(251);", 1), encoding="utf-8")
    run(command)
    second = assert_build(build, "Incremental.ino")
    edited_elf = artifact_hash(build, "Incremental.ino")
    evidence.append(m9_snapshot("sketch-edit", second))
    if unchanged["cache_key"] != second["cache_key"]:
        raise SmokeFailure("Sketch body edit changed the M9 cache key")
    if unchanged["zephyr_build_dir"] != second["zephyr_build_dir"]:
        raise SmokeFailure("incremental compile changed the Zephyr workspace")
    if second.get("pristine_configure_count") != 1:
        raise SmokeFailure("incremental compile repeated a pristine configure")
    if edited_elf == cold_elf:
        raise SmokeFailure("Sketch source edit was not reflected in the final ELF")
    if int(second.get("ccache_stats_delta", {}).get("cache_miss", 0)) < 1:
        raise SmokeFailure("Sketch source edit did not compile a changed source")
    generated_sketch = build / "sketch" / "Incremental.ino.cpp"
    sketch_record = source_provenance(build, "Incremental.ino", generated_sketch)
    mirror = Path(sketch_record["compiled_path"])
    if (
        sketch_record.get("logical_identity")
        != "arduino-generated:sketch/Incremental.ino.cpp"
        or not mirror.is_file()
        or "delay(251);" not in mirror.read_text(encoding="utf-8")
        or sketch_record.get("sha256")
        != hashlib.sha256(generated_sketch.read_bytes()).hexdigest()
    ):
        raise SmokeFailure("edited Sketch source was not materialized in the cache mirror")

    alternate_build = root / "build-incremental-alternate"
    run(compile_command(cli, config, alternate_build, sketch))
    alternate = assert_build(alternate_build, "Incremental.ino")
    evidence.append(m9_snapshot("alternate-build-path", alternate))
    if alternate["cache_key"] != second["cache_key"]:
        raise SmokeFailure("Arduino build path leaked into the M9 cache key")
    if alternate["zephyr_build_dir"] != second["zephyr_build_dir"]:
        raise SmokeFailure("same Sketch in another build path did not reuse the cache tree")
    if artifact_hash(alternate_build, "Incremental.ino") != edited_elf:
        raise SmokeFailure("alternate Arduino build path exported a different ELF")

    parallel_builds = (
        root / "build-incremental-parallel-a",
        root / "build-incremental-parallel-b",
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(run, compile_command(cli, config, parallel_build, sketch))
            for parallel_build in parallel_builds
        ]
        for future in futures:
            future.result()
    for index, parallel_build in enumerate(parallel_builds, start=1):
        parallel_context = assert_build(parallel_build, "Incremental.ino")
        evidence.append(m9_snapshot(f"parallel-same-key-{index}", parallel_context))
        if parallel_context["cache_key"] != second["cache_key"]:
            raise SmokeFailure("same-key parallel build selected a different cache key")
        if parallel_context["zephyr_build_dir"] != second["zephyr_build_dir"]:
            raise SmokeFailure("same-key parallel build did not serialize one cache tree")

    (sketch / "prj.conf").write_text("CONFIG_THREAD_NAME=y\n", encoding="utf-8")
    run(command)
    configured = assert_build(build, "Incremental.ino")
    evidence.append(m9_snapshot("prj-conf-edit", configured))
    if configured["cache_key"] == second["cache_key"]:
        raise SmokeFailure("prj.conf edit did not select a new cache key")
    if configured["zephyr_build_dir"] == second["zephyr_build_dir"]:
        raise SmokeFailure("prj.conf edit reused an incompatible Zephyr tree")
    if configured.get("pristine_configure_count") != 1:
        raise SmokeFailure("new prj.conf key did not start with one pristine configure")
    configured_output = (
        Path(configured["zephyr_build_dir"]) / "zephyr" / ".config"
    ).read_text(encoding="utf-8")
    if "CONFIG_THREAD_NAME=y" not in configured_output:
        raise SmokeFailure("M9 prj.conf key did not materialize its Kconfig marker")

    (sketch / "app.overlay").write_text(
        "/ { nucode-m9-fixture { compatible = \"nucode,m9-fixture\"; }; };\n",
        encoding="utf-8",
    )
    run(command)
    overlaid = assert_build(build, "Incremental.ino")
    evidence.append(m9_snapshot("overlay-edit", overlaid))
    if overlaid["cache_key"] == configured["cache_key"]:
        raise SmokeFailure("app.overlay edit did not select a new cache key")
    if overlaid.get("pristine_configure_count") != 1:
        raise SmokeFailure("new overlay key did not start with one pristine configure")
    overlaid_output = (
        Path(overlaid["zephyr_build_dir"]) / "zephyr" / "zephyr.dts"
    ).read_text(encoding="utf-8")
    if "nucode-m9-fixture" not in overlaid_output:
        raise SmokeFailure("M9 overlay key did not materialize its devicetree marker")

    platform = root / "user" / "hardware" / "nucode" / "zephyr"
    module_manifest = platform / "zephyr" / "module.yml"
    binding = platform / "dts" / "bindings" / "misc" / "nucode,arduino-adc-input.yaml"
    module_manifest_bytes = module_manifest.read_bytes()
    binding_bytes = binding.read_bytes()
    module_manifest.write_text(
        module_manifest.read_text(encoding="utf-8")
        + "\n# 모듈 지문 변경 검증용 표식입니다.\n",
        encoding="utf-8",
    )
    run(command)
    third = assert_build(build, "Incremental.ino")
    evidence.append(m9_snapshot("module-edit", third))
    if third["zephyr_build_dir"] == overlaid["zephyr_build_dir"]:
        raise SmokeFailure("module.yml 변경이 새 Zephyr tree를 선택하지 않았습니다")
    if third.get("cache_key") == overlaid.get("cache_key"):
        raise SmokeFailure("module.yml 변경이 cache key에 반영되지 않았습니다")
    if third.get("configure_skipped") is not False:
        raise SmokeFailure("module.yml 변경 뒤 configure가 생략되었습니다")
    if third.get("pristine_configure_count") != 1:
        raise SmokeFailure("module.yml 새 key의 pristine configure 횟수가 잘못되었습니다")

    binding.write_text(
        binding.read_text(encoding="utf-8")
        + "\n# DTS 바인딩 지문 변경 검증용 표식입니다.\n",
        encoding="utf-8",
    )
    run(command)
    fourth = assert_build(build, "Incremental.ino")
    evidence.append(m9_snapshot("dts-binding-edit", fourth))
    if fourth["zephyr_build_dir"] == third["zephyr_build_dir"]:
        raise SmokeFailure("DTS binding 변경이 새 Zephyr tree를 선택하지 않았습니다")
    if fourth.get("cache_key") == third.get("cache_key"):
        raise SmokeFailure("DTS binding 변경이 cache key에 반영되지 않았습니다")
    if fourth.get("configure_skipped") is not False:
        raise SmokeFailure("DTS binding 변경 뒤 configure가 생략되었습니다")
    if fourth.get("pristine_configure_count") != 1:
        raise SmokeFailure("DTS binding 새 key의 pristine configure 횟수가 잘못되었습니다")

    build_graph = Path(fourth["zephyr_build_dir"]) / "build.ninja"
    build_graph.unlink()
    run(command)
    recovered = assert_build(build, "Incremental.ino")
    evidence.append(m9_snapshot("build-graph-recovery", recovered))
    if recovered["cache_key"] != fourth["cache_key"]:
        raise SmokeFailure("build graph recovery changed the valid cache key")
    if recovered.get("configure_reason") != "build-graph-recovery":
        raise SmokeFailure("missing build.ninja recovery reason was not recorded")
    if recovered.get("recovery_count") != 1:
        raise SmokeFailure("build graph recovery count was not recorded")
    if recovered.get("pristine_configure_count") != 2:
        raise SmokeFailure("build graph recovery did not run one explicit pristine configure")
    (root / "m9-evidence.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "fqbn": FQBN,
                "scenarios": evidence,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    module_manifest.write_bytes(module_manifest_bytes)
    binding.write_bytes(binding_bytes)


## @brief M6 Serial과 GPIO interrupt 공개 예제를 Arduino CLI로 끝까지 빌드합니다.
def test_m6_examples(cli: Path, config: Path, root: Path, repository: Path) -> None:
    examples = (
        ("serial-echo", board_examples(repository) / "SerialEcho", "SerialEcho.ino"),
        (
            "interrupt-button",
            board_examples(repository) / "InterruptButton",
            "InterruptButton.ino",
        ),
    )
    for build_name, sketch, project_name in examples:
        build = root / f"build-m6-{build_name}"
        run(compile_command(cli, config, build, sketch))
        assert_build(build, project_name)


## @brief M7 주변장치 공개 예제와 M13 표준 profile 병합을 검증합니다.
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
            repository / "libraries" / "Wire" / "examples" / "WirePmicId",
            "WirePmicId.ino",
            "CONFIG_NUCODE_ARDUINO_WIRE",
            "nucode,arduino-wire",
        ),
        (
            "spi-transaction",
            repository / "libraries" / "SPI" / "examples" / "SPITransaction",
            "SPITransaction.ino",
            "CONFIG_NUCODE_ARDUINO_SPI",
            "nucode,arduino-spi",
        ),
        (
            "analog-read-a0",
            board_examples(repository) / "AnalogReadA0",
            "AnalogReadA0.ino",
            "CONFIG_NUCODE_ARDUINO_ADC",
            "nucode,arduino-adc",
        ),
        (
            "pwm-fade",
            board_examples(repository) / "PWMFade",
            "PWMFade.ino",
            "CONFIG_NUCODE_ARDUINO_PWM",
            "nucode,arduino-pwm",
        ),
    )
    for build_name, sketch, project_name, enabled_symbol, devicetree_marker in examples:
        if not (sketch / project_name).is_file():
            raise SmokeFailure(f"incomplete M7 example: {sketch}")
        if (sketch / "prj.conf").exists() or (sketch / "app.overlay").exists():
            raise SmokeFailure(f"M13 public example contains a Zephyr sidecar: {sketch}")
        build = root / f"build-m7-{build_name}"
        run(compile_command(cli, config, build, sketch))
        context = assert_build(build, project_name)
        if context.get("profile") != "standard":
            raise SmokeFailure(f"M7 example did not use the standard profile: {sketch}")
        zephyr = Path(context["zephyr_build_dir"]) / "zephyr"
        configuration = (zephyr / ".config").read_text(encoding="utf-8")
        for symbol in peripheral_symbols:
            if not read_kconfig_boolean(configuration, symbol):
                raise SmokeFailure(
                    f"M13 standard profile omitted an M7 symbol: {sketch}: {symbol}"
                )

        materialized_overlay = (
            Path(context["app_dir"]) / "app.overlay"
        ).read_text(encoding="utf-8")
        profile_overlay = (
            repository / "variants" / "nu54dk" / "profiles" / "standard" / "app.overlay"
        ).read_text(encoding="utf-8").rstrip()
        if profile_overlay not in materialized_overlay:
            raise SmokeFailure(f"M13 standard profile overlay was not merged: {sketch}")

        devicetree = (zephyr / "zephyr.dts").read_text(encoding="utf-8")
        if devicetree_marker not in devicetree:
            raise SmokeFailure(f"M7 example devicetree contract was not merged: {sketch}")

        selected_features = {
            item.get("id")
            for item in context.get("selected_features", [])
            if isinstance(item, dict)
        }
        expected_feature = {
            "CONFIG_NUCODE_ARDUINO_WIRE": "nucode.wire",
            "CONFIG_NUCODE_ARDUINO_SPI": "nucode.spi",
        }.get(enabled_symbol)
        if expected_feature is not None and expected_feature not in selected_features:
            raise SmokeFailure(
                f"M13 selected library feature was not recorded: {sketch}: {expected_feature}"
            )

    test_live_build_record_scope(context, root)


## @brief AC-02B 동적 주변장치·아날로그 공개 예제를 표준 profile로 빌드합니다.
def test_ac02b_examples(cli: Path, config: Path, root: Path, repository: Path) -> None:
    required_symbols = (
        "CONFIG_NUCODE_ARDUINO_SERIAL1",
        "CONFIG_NUCODE_ARDUINO_WIRE",
        "CONFIG_NUCODE_ARDUINO_SPI",
        "CONFIG_NUCODE_ARDUINO_ADC",
        "CONFIG_NUCODE_ARDUINO_PWM",
    )
    examples = tuple(
        (
            name,
            board_examples(repository) / name,
            f"{name}.ino",
            {
                "SPI00RuntimePins": "nucode.spi",
                "WireRuntimePins": "nucode.wire",
            }.get(name),
        )
        for name in (
            "AnalogChannels",
            "AnalogResolution",
            "DynamicPWM",
            "Serial1RuntimePins",
            "SPI00RuntimePins",
            "ToneOutput",
            "WireRuntimePins",
        )
    ) + (
        (
            "ServoSweep",
            repository / "libraries" / "Servo" / "examples" / "Sweep",
            "Sweep.ino",
            "nucode.servo",
        ),
    )

    for build_name, sketch, project_name, expected_feature in examples:
        if not (sketch / project_name).is_file():
            raise SmokeFailure(f"incomplete AC-02B example: {sketch}")
        if (sketch / "prj.conf").exists() or (sketch / "app.overlay").exists():
            raise SmokeFailure(f"AC-02B public example contains a Zephyr sidecar: {sketch}")

        build = root / f"build-ac02b-{build_name.lower()}"
        run(compile_command(cli, config, build, sketch))
        context = assert_build(build, project_name)
        if context.get("profile") != "standard":
            raise SmokeFailure(f"AC-02B example did not use the standard profile: {sketch}")

        configuration = (
            Path(context["zephyr_build_dir"]) / "zephyr" / ".config"
        ).read_text(encoding="utf-8")
        for symbol in required_symbols:
            if not read_kconfig_boolean(configuration, symbol):
                raise SmokeFailure(
                    f"AC-02B standard profile omitted a symbol: {sketch}: {symbol}"
                )

        selected_features = {
            item.get("id")
            for item in context.get("selected_features", [])
            if isinstance(item, dict)
        }
        if expected_feature is not None and expected_feature not in selected_features:
            raise SmokeFailure(
                f"AC-02B library feature was not selected: {sketch}: {expected_feature}"
            )


## @brief AC-03 EEPROM·LittleFS 예제와 두 profile의 loaderless partition을 빌드합니다.
def test_ac03_storage_examples(
    cli: Path, config: Path, root: Path, repository: Path
) -> None:
    examples = (
        (
            "eeprom-standard",
            repository / "libraries" / "EEPROM" / "examples" / "EEPROMPersistence",
            "EEPROMPersistence.ino",
            "standard",
            "nucode.eeprom",
            ("CONFIG_SETTINGS_ZMS",),
        ),
        (
            "littlefs-standard",
            repository / "libraries" / "LittleFS" / "examples" / "LittleFSPersistence",
            "LittleFSPersistence.ino",
            "standard",
            "nucode.littlefs",
            ("CONFIG_FILE_SYSTEM_LITTLEFS", "CONFIG_FILE_SYSTEM_MKFS"),
        ),
        (
            "littlefs-ble",
            repository / "libraries" / "LittleFS" / "examples" / "LittleFSPersistence",
            "LittleFSPersistence.ino",
            "ble",
            "nucode.littlefs",
            ("CONFIG_FILE_SYSTEM_LITTLEFS", "CONFIG_FILE_SYSTEM_MKFS"),
        ),
    )
    for build_name, sketch, project_name, profile, feature, symbols in examples:
        if not (sketch / project_name).is_file():
            raise SmokeFailure(f"incomplete AC-03 example: {sketch}")
        build = root / f"build-ac03-{build_name}"
        command = list(compile_command(cli, config, build, sketch))
        if profile == "ble":
            command[-1:-1] = ("--board-options", "feature_set=ble")
        run(command)
        context = assert_build(build, project_name)
        if context.get("profile") != profile:
            raise SmokeFailure(
                f"AC-03 example profile mismatch: {sketch}: {context.get('profile')}"
            )
        selected_features = {
            item.get("id")
            for item in context.get("selected_features", [])
            if isinstance(item, dict)
        }
        if feature not in selected_features:
            raise SmokeFailure(f"AC-03 feature was not selected: {sketch}: {feature}")
        zephyr = Path(context["zephyr_build_dir"]) / "zephyr"
        configuration = (zephyr / ".config").read_text(encoding="utf-8")
        for linker_symbol in (
            "CONFIG_USE_DT_CODE_PARTITION",
            "CONFIG_FLASH_USES_MAPPED_PARTITION",
        ):
            if not read_kconfig_boolean(configuration, linker_symbol):
                raise SmokeFailure(
                    f"AC-03 linker partition symbol is disabled: {build_name}: {linker_symbol}"
                )
        for symbol in symbols:
            if not read_kconfig_boolean(configuration, symbol):
                raise SmokeFailure(f"AC-03 symbol is disabled: {build_name}: {symbol}")
        devicetree = (zephyr / "zephyr.dts").read_text(encoding="utf-8")
        expected_partitions = (
            ('label = "image-0";', "reg = < 0x0 0x16c000 >;"),
            ('label = "arduino-fs";', "reg = < 0x16c000 0x8000 >;"),
            ('label = "storage";', "reg = < 0x174000 0x9000 >;"),
        )
        for label, region in expected_partitions:
            if label not in devicetree or region not in devicetree:
                raise SmokeFailure(
                    f"AC-03 fixed partition missing: {build_name}: {label}: {region}"
                )
        memory_map = (zephyr / "zephyr.map").read_text(encoding="utf-8")
        if not re.search(
            r"^FLASH\s+0x0+\s+0x0*16c000\s+xr\s*$",
            memory_map,
            re.MULTILINE,
        ):
            raise SmokeFailure(
                f"AC-03 linker FLASH region is not the loaderless image: {build_name}"
            )


## @brief M15 board/system 공개 예제와 feature conf·overlay 병합을 검증합니다.
def test_m15_examples(cli: Path, config: Path, root: Path, repository: Path) -> None:
    required_symbols = (
        "CONFIG_HWINFO",
        "CONFIG_WATCHDOG",
        "CONFIG_WDT_NRFX",
        "CONFIG_POWEROFF",
        "CONFIG_PM_DEVICE",
        "CONFIG_SETTINGS",
        "CONFIG_SETTINGS_ZMS",
        "CONFIG_SETTINGS_ZMS_LOAD_SUBTREE_PATH",
    )
    examples = (
        "BoardInfo",
        "CounterAlarm",
        "SettingsStorage",
        "SystemOffWake",
        "WatchdogBasic",
    )
    for example_name in examples:
        sketch = board_examples(repository) / example_name
        project_name = f"{example_name}.ino"
        if not (sketch / project_name).is_file():
            raise SmokeFailure(f"incomplete M15 example: {sketch}")
        if (sketch / "prj.conf").exists() or (sketch / "app.overlay").exists():
            raise SmokeFailure(f"M15 public example contains a Zephyr sidecar: {sketch}")

        build = root / f"build-m15-{example_name.lower()}"
        run(compile_command(cli, config, build, sketch))
        context = assert_build(build, project_name)
        if context.get("profile") != "standard":
            raise SmokeFailure(f"M15 example did not use the standard profile: {sketch}")
        selected_features = {
            item.get("id")
            for item in context.get("selected_features", [])
            if isinstance(item, dict)
        }
        if "nucode.board" not in selected_features:
            raise SmokeFailure(f"M15 board feature was not recorded: {sketch}")

        zephyr = Path(context["zephyr_build_dir"]) / "zephyr"
        configuration = (zephyr / ".config").read_text(encoding="utf-8")
        for symbol in required_symbols:
            if not read_kconfig_boolean(configuration, symbol):
                raise SmokeFailure(f"M15 feature omitted {symbol}: {sketch}")
        sources = (Path(context["app_dir"]) / "sources.cmake").read_text(
            encoding="utf-8"
        )
        if "NUCODE_NU54DK.cpp" not in sources:
            raise SmokeFailure(f"M15 board implementation source was not linked: {sketch}")

        devicetree = (zephyr / "zephyr.dts").read_text(encoding="utf-8")
        if "nordic,nrf-wdt" not in devicetree:
            raise SmokeFailure(f"M15 WDT overlay was not merged: {sketch}")

    system_off_source = (
        board_examples(repository) / "SystemOffWake" / "SystemOffWake.ino"
    ).read_text(encoding="utf-8")
    if (
        'strcmp(command, "BUTTON")' not in system_off_source
        or 'strcmp(command, "TIMER")' not in system_off_source
        or "NU54DK.enterSystemOffOnButton(WakeButton::sw0)"
        not in system_off_source
        or "NU54DK.enterSystemOffAfter(2000000ULL)" not in system_off_source
        or "prepareButtonWake" in system_off_source
        or "prepareTimedWake" in system_off_source
    ):
        raise SmokeFailure("SystemOffWake가 명시적 Serial 명령 gate를 유지하지 않습니다")


## @brief 선택한 BLE NUS/Core/GATT 예제를 BLE profile로 끝까지 빌드합니다.
def test_ble_examples(
    cli: Path,
    config: Path,
    root: Path,
    repository: Path,
    examples: Sequence[str],
) -> None:
    library = repository / "libraries" / "NUCODE_BLE"
    for example_name in examples:
        sketch = library / "examples" / example_name
        project_name = f"{example_name}.ino"
        if not (sketch / project_name).is_file():
            raise SmokeFailure(f"incomplete BLE example: {sketch}")
        build = root / f"build-ble-{example_name.casefold()}"
        command = list(compile_command(cli, config, build, sketch))
        command[-1:-1] = ("--board-options", "feature_set=ble")
        run(command)
        context = assert_build(build, project_name)
        if context.get("profile") != "ble":
            raise SmokeFailure(f"BLE example did not use BLE profile: {sketch}")
        selected_features = {
            item.get("id")
            for item in context.get("selected_features", [])
            if isinstance(item, dict)
        }
        if "nucode.ble.nus" not in selected_features:
            raise SmokeFailure(f"BLE feature was not selected: {sketch}")
        configuration = (
            Path(context["zephyr_build_dir"]) / "zephyr" / ".config"
        ).read_text(encoding="utf-8")
        required_symbols = ["CONFIG_NUCODE_BLE_CORE", "CONFIG_NUCODE_BLE_GATT"]
        if example_name.startswith("NUS"):
            required_symbols.extend(
                ("CONFIG_BT_NUS", "CONFIG_BT_NUS_CLIENT", "CONFIG_NUCODE_BLE_NUS")
            )
        for symbol in required_symbols:
            if not read_kconfig_boolean(configuration, symbol):
                raise SmokeFailure(f"BLE symbol is disabled: {example_name}: {symbol}")


## @brief v0.2.0에서 도입한 M16 NUS 예제만 빌드합니다.
def test_m16_examples(cli: Path, config: Path, root: Path, repository: Path) -> None:
    test_ble_examples(
        cli,
        config,
        root,
        repository,
        ("NUSPeripheral", "NUSCentral"),
    )


## @brief v0.3.0에서 도입한 M19 GAP·M20 GATT 예제만 빌드합니다.
def test_m19_m20_examples(
    cli: Path, config: Path, root: Path, repository: Path
) -> None:
    test_ble_examples(
        cli,
        config,
        root,
        repository,
        ("GAPPeripheral", "GAPCentral", "CustomGattPeripheral", "CustomGattCentral"),
    )


## @brief M21 SecureKeyboard 예제를 BLE security feature로 끝까지 빌드합니다.
def test_m21_example(cli: Path, config: Path, root: Path, repository: Path) -> None:
    security_sketch = (
        repository
        / "libraries"
        / "NUCODE_BLE_Security"
        / "examples"
        / "SecureKeyboard"
    )
    if not (security_sketch / "SecureKeyboard.ino").is_file():
        raise SmokeFailure(f"incomplete BLE security example: {security_sketch}")
    security_build = root / "build-ble-securekeyboard"
    security_command = list(compile_command(cli, config, security_build, security_sketch))
    security_command[-1:-1] = ("--board-options", "feature_set=ble")
    run(security_command)
    security_context = assert_build(security_build, "SecureKeyboard.ino")
    if security_context.get("profile") != "ble":
        raise SmokeFailure(
            f"BLE security example did not use BLE profile: {security_sketch}"
        )
    security_features = {
        item.get("id")
        for item in security_context.get("selected_features", [])
        if isinstance(item, dict)
    }
    if "nucode.ble.security" not in security_features:
        raise SmokeFailure(f"BLE security feature was not selected: {security_sketch}")
    security_configuration = (
        Path(security_context["zephyr_build_dir"]) / "zephyr" / ".config"
    ).read_text(encoding="utf-8")
    for symbol in (
        "CONFIG_BT_SMP",
        "CONFIG_SETTINGS_ZMS",
        "CONFIG_BT_HIDS",
        "CONFIG_BT_HIDS_DEFAULT_PERM_RW_ENCRYPT",
    ):
        if not read_kconfig_boolean(security_configuration, symbol):
            raise SmokeFailure(f"BLE security symbol is disabled: {symbol}")


## @brief platform library 예제가 Arduino IDE용 목록에 나타나는지 검증합니다.
def test_example_discovery(cli: Path, config: Path, root: Path, repository: Path) -> None:
    del root, repository
    _, output = run(
        (cli, "lib", "examples", "--fqbn", FQBN, "--config-file", config, "--json")
    )
    document = json.loads(output)
    records = document.get("examples")
    if not isinstance(records, list):
        raise SmokeFailure("Arduino CLI example listing has no examples array")

    expected = {
        "NUCODE NU54DK": {
            "Blink",
            "InterruptButton",
            "AnalogReadA0",
            "AnalogChannels",
            "AnalogResolution",
            "PWMFade",
            "DynamicPWM",
            "Serial1RuntimePins",
            "SerialEcho",
            "SPI00RuntimePins",
            "ToneOutput",
            "WireRuntimePins",
            "BoardInfo",
            "CounterAlarm",
            "SettingsStorage",
            "SystemOffWake",
            "WatchdogBasic",
        },
        "Servo": {"Sweep"},
        "EEPROM": {"EEPROMPersistence"},
        "LittleFS": {"LittleFSPersistence"},
        "SPI": {"SPITransaction"},
        "Wire": {"WirePmicId"},
        "NUCODE BLE": {
            "CustomGattCentral",
            "CustomGattPeripheral",
            "GAPCentral",
            "GAPPeripheral",
            "NUSCentral",
            "NUSPeripheral",
        },
        "NUCODE BLE Security": {"SecureKeyboard"},
    }
    discovered: dict[str, set[str]] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        library = record.get("library")
        if not isinstance(library, dict):
            continue
        example_paths = record.get("examples", [])
        if not isinstance(example_paths, list) or not all(
            isinstance(path, str) for path in example_paths
        ):
            raise SmokeFailure("Arduino CLI example listing has an invalid examples field")
        discovered[str(library.get("name", ""))] = {
            Path(path).name for path in example_paths
        }

    for library, sketches in expected.items():
        listing = discovered.get(library, set())
        if listing != sketches:
            raise SmokeFailure(
                f"{library} example set mismatch: "
                f"expected={sorted(sketches)}, actual={sorted(listing)}"
            )


## @brief M8 upload sketch, manifest와 pyOCD/J-Link runner 계약을 compile 단계에서 검증합니다.
def test_m8_upload_build(cli: Path, config: Path, root: Path, repository: Path) -> None:
    sketch = repository / "tests" / "arduino-cli" / "m8_upload"
    build = root / "build-m8-upload"
    command = compile_command(cli, config, build, sketch)
    command[-1:-1] = ("--board-options", "upload_probe=pyocd")
    run(command)
    context = assert_build(build, "m8_upload.ino")
    manifest_path = build / "m8_upload.ino.nu54-build.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("sysbuild") is not False:
        raise SmokeFailure("M8 upload manifest unexpectedly enabled sysbuild")
    if manifest.get("fqbn") != f"{FQBN}:upload_probe=pyocd":
        raise SmokeFailure("M8 upload menu selection was not recorded in the manifest")

    uid_build = root / "build-m8-upload-uid"
    uid_command = compile_command(cli, config, uid_build, sketch)
    uid_command[-1:-1] = ("--board-options", "upload_probe=pyocd_uid")
    run(uid_command)
    assert_build(uid_build, "m8_upload.ino")
    uid_manifest = json.loads(
        (uid_build / "m8_upload.ino.nu54-build.json").read_text(encoding="utf-8")
    )
    if uid_manifest.get("fqbn") != f"{FQBN}:upload_probe=pyocd_uid":
        raise SmokeFailure("M8 explicit UID upload menu was not recorded in the manifest")

    field_value = "NU54_UPLOAD_FIELD_EXPANSION_DO_NOT_MATCH_A_REAL_PROBE"
    field_command: list[str | Path] = [
        cli,
        "upload",
        "--verbose",
        "--fqbn",
        FQBN,
        "--config-file",
        config,
        "--build-path",
        uid_build,
        "--board-options",
        "upload_probe=pyocd_uid",
        "--upload-field",
        f"probe_id={field_value}",
        sketch,
    ]
    return_code, field_output = run(field_command, expect_success=False)
    normalized_field_output = field_output.replace('"', "").replace("'", "")
    if return_code == 0:
        raise SmokeFailure("M8 upload-field sentinel unexpectedly selected a real probe")
    if f"--runner pyocd --probe-id {field_value}" not in normalized_field_output:
        raise SmokeFailure("Arduino CLI did not expand the explicit UID upload field")
    runners = Path(context["zephyr_build_dir"]) / "zephyr" / "runners.yaml"
    content = runners.read_text(encoding="utf-8")
    for expected in ("- pyocd", "- jlink", "--target=nrf54l", "--device=nRF54L15_M33"):
        if expected not in content:
            raise SmokeFailure(f"M8 runner contract is missing: {expected}")

    platform = Path(context["platform_root"])
    platform_text = (platform / "platform.txt").read_text(encoding="utf-8")
    boards_text = (platform / "boards.txt").read_text(encoding="utf-8")
    builder_text = (
        platform / "tools" / "nu54-builder" / "src" / "nu54_builder.py"
    ).read_text(encoding="utf-8")
    for expected in (
        "tools.nu54_pyocd.upload.pattern=",
        "--runner pyocd {upload.verbose}",
        "tools.nu54_pyocd_uid.upload.field.probe_id=CMSIS-DAP unique ID",
        'tools.nu54_pyocd_uid.upload.pattern={nu54.builder}',
        '--runner pyocd --probe-id "{upload.field.probe_id}"',
        "--runner jlink",
        "nu54-builder",
    ):
        if expected not in platform_text:
            raise SmokeFailure(f"M8 upload recipe is missing: {expected}")
    if "tools.nu54_pyocd.upload.field." in platform_text:
        raise SmokeFailure("M8 default pyOCD recipe must not require an upload field")
    if "smart_flash=false" not in builder_text:
        raise SmokeFailure("M8 pyOCD stability option is missing")
    for expected in (
        "upload.tool.default=nu54_pyocd",
        "menu.upload_probe.pyocd_uid=CMSIS-DAP with UID (pyOCD)",
        "menu.upload_probe.pyocd_uid.upload.tool.default=nu54_pyocd_uid",
        "menu.upload_probe.jlink",
    ):
        if expected not in boards_text:
            raise SmokeFailure(f"M8 board upload property is missing: {expected}")


## @brief 선택된 M5~M9 smoke test를 격리된 hardware와 cache root에서 실행합니다.
def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cli", type=Path, default=default_cli())
    parser.add_argument("--evidence", type=Path)
    parser.add_argument(
        "--platform-root",
        type=Path,
        help="검증할 ZIP에서 직접 추출한 Git-less Arduino platform root",
    )
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument(
        "--tests",
        nargs="+",
        choices=ARDUINO_TESTS,
    )
    selection.add_argument(
        "--group",
        choices=tuple(ARDUINO_SELECTIONS),
        help="현재 source에서 검증할 릴리스 도입 기능군",
    )
    args = parser.parse_args(arguments)
    repository = Path(__file__).resolve().parents[2]
    cli = args.cli.resolve()
    if not cli.is_file():
        raise SmokeFailure(f"arduino-cli was not found: {cli}")

    with tempfile.TemporaryDirectory(prefix="n54m5-") as temporary_name:
        root = Path(temporary_name)
        previous_cache_root = os.environ.get("NUCODE_BUILD_CACHE_ROOT")
        os.environ["NUCODE_BUILD_CACHE_ROOT"] = str(root / "cache")
        user_root = root / "user"
        try:
            if args.platform_root is None:
                stage_platform(repository, user_root)
            else:
                stage_packaged_platform(args.platform_root, user_root)
            config = root / "arduino-cli.yaml"
            write_cli_config(
                config,
                user_root,
                root / "data",
                root / "downloads",
            )
            tests = {
                "blink": test_blink,
                "library": test_local_library,
                "config": test_config_overlay,
                "error": test_compile_error,
                "parallel": test_parallel,
                "incremental": test_incremental,
                "m6": test_m6_examples,
                "m7": test_m7_examples,
                "m8": test_m8_upload_build,
                "m9": test_incremental,
                "m11": test_m11_fixtures,
                "m15": test_m15_examples,
                "m16": test_m16_examples,
                "m19m20": test_m19_m20_examples,
                "m21": test_m21_example,
                "ac02b": test_ac02b_examples,
                "ac03": test_ac03_storage_examples,
                "examples": test_example_discovery,
            }
            selected_tests = (
                ARDUINO_SELECTIONS[args.group]
                if args.group is not None
                else (tuple(args.tests) if args.tests is not None else DEFAULT_TESTS)
            )
            selected_group = args.group or "custom"
            for name in selected_tests:
                print(f"SMOKE_TEST_START={selected_group}/{name}", flush=True)
                try:
                    tests[name](cli, config, root, repository)
                except SmokeFailure as error:
                    raise SmokeFailure(f"{selected_group}/{name}: {error}") from error
                print(f"PASS: {name}", flush=True)
            print(
                f"ARDUINO_SMOKE_GROUP_PASS={selected_group};"
                f"TESTS={len(selected_tests)}",
                flush=True,
            )
            m9_evidence = root / "m9-evidence.json"
            if args.evidence and m9_evidence.is_file():
                evidence_path = args.evidence.resolve()
                evidence_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(m9_evidence, evidence_path)
        finally:
            if previous_cache_root is None:
                os.environ.pop("NUCODE_BUILD_CACHE_ROOT", None)
            else:
                os.environ["NUCODE_BUILD_CACHE_ROOT"] = previous_cache_root
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SmokeFailure as error:
        print(f"FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
