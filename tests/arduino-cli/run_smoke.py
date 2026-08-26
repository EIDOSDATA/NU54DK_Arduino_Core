#!/usr/bin/env python3
"""! @brief NU54DK Arduino CLI M5 end-to-end 회귀를 실행합니다. """

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
    for name in ("board_package", "cores", "third_party", "tools", "variants", "zephyr"):
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
        raise SmokeFailure("M5 build unexpectedly enabled sysbuild")
    for extension in ("elf", "hex", "bin", "map", "nu54-build.json"):
        artifact = build_path / f"{project_name}.{extension}"
        if not artifact.is_file() or artifact.stat().st_size == 0:
            raise SmokeFailure(f"missing artifact: {artifact}")
    return context


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


## @brief sketch 수정 전후 같은 Ninja tree를 재사용하고 pristine을 반복하지 않는지 검증합니다.
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


## @brief 선택된 M5 smoke test를 격리된 hardware root에서 실행합니다.
def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cli", type=Path, default=default_cli())
    parser.add_argument(
        "--tests",
        nargs="+",
        choices=("blink", "library", "config", "error", "parallel", "incremental"),
        default=("blink", "library", "config", "error", "parallel", "incremental"),
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
