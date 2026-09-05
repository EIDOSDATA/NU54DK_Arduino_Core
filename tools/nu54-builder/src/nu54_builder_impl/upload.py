"""! @brief 검증된 artifact의 runner·probe·flash 실행 경계를 소유합니다. """

from __future__ import annotations

from pathlib import Path
from typing import Any
from typing import Sequence
import argparse
import datetime as dt
import os
import shlex
import shutil
import subprocess
from .artifacts import validate_flash_manifest
from .build import load_context
from .common import AdapterError, CONTEXT_DIRECTORY, ChildCommandError, canonical_path, path_key
from .environment import tool_environment
from .locking import build_lock, probe_lock
from .paths import adapter_paths, paths_from_context


## @brief Zephyr runners.yaml을 YAML parser로 읽고 선택 runner의 고정 인자를 검증합니다.
def validate_runner_configuration(zephyr_build: Path, runner: str) -> Path:
    runners_path = zephyr_build / "zephyr" / "runners.yaml"
    if not runners_path.is_file():
        raise AdapterError(f"[NU54:E_RUNNER_UNAVAILABLE] runners.yaml이 없습니다: {runners_path}")
    try:
        import yaml

        document = yaml.safe_load(runners_path.read_text(encoding="utf-8"))
    except Exception as error:
        raise AdapterError(f"[NU54:E_RUNNER_UNAVAILABLE] runners.yaml을 읽지 못했습니다: {error}") from error
    if not isinstance(document, dict):
        raise AdapterError("[NU54:E_RUNNER_UNAVAILABLE] runners.yaml root가 object가 아닙니다.")
    available = document.get("runners")
    if not isinstance(available, list) or runner not in available:
        names = ", ".join(str(value) for value in available) if isinstance(available, list) else "없음"
        raise AdapterError(
            f"[NU54:E_RUNNER_UNAVAILABLE] 선택 runner가 build에 없습니다: {runner}; available: {names}"
        )
    runner_arguments = document.get("args", {}).get(runner, [])
    if not isinstance(runner_arguments, list):
        raise AdapterError(f"[NU54:E_RUNNER_UNAVAILABLE] {runner} runner argument 형식이 잘못되었습니다.")
    normalized_arguments = [str(value).casefold() for value in runner_arguments]
    unsafe_runner_arguments = [
        value
        for value in normalized_arguments
        if value in {"--erase", "--recover", "-e"}
        or value.startswith(("--erase=", "--recover="))
        or "mass-erase" in value
        or "chip-erase" in value
    ]
    if unsafe_runner_arguments:
        raise AdapterError(
            "[NU54:E_FLASH_UNSAFE_OPTION] runners.yaml에 destructive option이 있습니다: "
            + ", ".join(unsafe_runner_arguments)
        )
    if runner == "pyocd" and "--target=nrf54l" not in runner_arguments:
        raise AdapterError("[NU54:E_PYOCD_TARGET] pyOCD target이 nrf54l이 아닙니다.")
    if runner == "jlink" and not {
        "--device=nRF54L15_M33",
        "--speed=4000",
    }.issubset(set(runner_arguments)):
        raise AdapterError("[NU54:E_RUNNER_JLINK_UNAVAILABLE] J-Link device 또는 speed metadata가 다릅니다.")
    return runners_path


## @brief pyOCD API를 사용해 연결된 CMSIS-DAP probe UID를 열거합니다.
def discover_pyocd_probe_ids() -> list[str]:
    try:
        from pyocd.core.helpers import ConnectHelper

        probes = ConnectHelper.get_all_connected_probes(blocking=False, print_wait_message=False)
    except Exception as error:
        raise AdapterError(f"[NU54:E_PROBE_NOT_FOUND] pyOCD probe 열거에 실패했습니다: {error}") from error
    return sorted(
        {str(probe.unique_id) for probe in probes if getattr(probe, "unique_id", None)},
        key=str.casefold,
    )


## @brief 명시값과 발견 목록에서 잘못된 자동 선택 없이 pyOCD probe 하나를 결정합니다.
def select_pyocd_probe(requested: str | None, discovered: Sequence[str] | None = None) -> str:
    probe_ids = list(discovered) if discovered is not None else discover_pyocd_probe_ids()
    requested_id = requested.strip() if requested else ""
    if requested_id:
        matches = [value for value in probe_ids if value.casefold() == requested_id.casefold()]
        if not matches:
            raise AdapterError(
                f"[NU54:E_PROBE_NOT_FOUND] 요청한 CMSIS-DAP UID가 없습니다: {requested_id}; "
                f"detected: {', '.join(probe_ids) or '없음'}"
            )
        return matches[0]
    if not probe_ids:
        raise AdapterError("[NU54:E_PROBE_NOT_FOUND] 연결된 CMSIS-DAP probe가 없습니다.")
    if len(probe_ids) != 1:
        raise AdapterError(
            "[NU54:E_PROBE_AMBIGUOUS] 여러 CMSIS-DAP probe가 연결되어 UID 지정이 필요합니다: "
            + ", ".join(probe_ids)
        )
    return probe_ids[0]


## @brief 설치된 SEGGER J-Link 실행 directory를 찾습니다.
def discover_jlink_directory(environment: dict[str, str]) -> Path:
    candidates: list[Path] = []
    configured = os.environ.get("NUCODE_JLINK_ROOT")
    if configured:
        candidates.append(canonical_path(configured))
    executable = shutil.which("JLink.exe", path=environment.get("PATH"))
    if executable:
        candidates.append(canonical_path(executable).parent)
    for root in (Path("C:/Program Files/SEGGER"), Path("C:/Program Files (x86)/SEGGER")):
        if root.is_dir():
            candidates.extend(sorted(root.glob("JLink_*"), reverse=True))
    visited: set[str] = set()
    for candidate in candidates:
        key = path_key(candidate)
        if key in visited:
            continue
        visited.add(key)
        if (candidate / "JLink.exe").is_file() and (candidate / "JLinkGDBServerCL.exe").is_file():
            return candidate.resolve()
    raise AdapterError(
        "[NU54:E_RUNNER_JLINK_UNAVAILABLE] SEGGER J-Link Software를 찾지 못했습니다. "
        "NUCODE_JLINK_ROOT를 설정하십시오."
    )


## @brief runner에 필요한 실행 파일과 UTF-8 child process 환경을 구성합니다.
def flash_environment(tools: dict[str, Any], runner: str) -> dict[str, str]:
    environment = tools["environment"].copy()
    environment["PYTHONUTF8"] = "1"
    environment["PYTHONIOENCODING"] = "utf-8"
    if runner == "pyocd":
        pyocd = tools["toolchain_root"] / "opt" / "bin" / "Scripts" / "pyocd.exe"
        if not pyocd.is_file():
            raise AdapterError(f"[NU54:E_RUNNER_UNAVAILABLE] pyOCD 실행 파일이 없습니다: {pyocd}")
    elif runner == "jlink":
        jlink_directory = discover_jlink_directory(environment)
        environment["PATH"] = str(jlink_directory) + os.pathsep + environment.get("PATH", "")
    return environment


## @brief 선택 runner와 probe로 erase 없는 west flash 명령을 만듭니다.
def build_flash_command(
    tools: dict[str, Any], zephyr_build: Path, runner: str, probe_id: str
) -> list[str | Path]:
    command: list[str | Path] = [
        tools["west"],
        "-z",
        tools["zephyr_base"],
        "flash",
        "-d",
        zephyr_build,
        "-r",
        runner,
        "--no-rebuild",
        "--dev-id",
        probe_id,
    ]
    if runner == "pyocd":
        command.extend(("--dt-flash=n", "--tool-opt=-Osmart_flash=false"))
    forbidden = {"--erase", "--recover"}
    if forbidden.intersection(str(value) for value in command):
        raise AdapterError("[NU54:E_FLASH_UNSAFE_OPTION] 일반 upload에 destructive option이 포함됐습니다.")
    return command


## @brief flash child process의 출력과 결과를 console 및 build log에 기록합니다.
def run_flash_process(
    command: Sequence[str | Path], *, cwd: Path, environment: dict[str, str], log_path: Path,
    runner: str, probe_id: str, hex_path: Path, hex_sha256: str
) -> None:
    normalized = [str(value) for value in command]
    started = dt.datetime.now(dt.timezone.utc)
    result = subprocess.run(
        normalized,
        cwd=cwd,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    output = result.stdout.decode("utf-8", errors="replace")
    if output:
        print(output, end="" if output.endswith("\n") else "\n")
    finished = dt.datetime.now(dt.timezone.utc)
    lines = [
        f"started_at_utc={started.isoformat()}",
        f"finished_at_utc={finished.isoformat()}",
        f"runner={runner}",
        f"probe_id={probe_id}",
        f"hex={hex_path.as_posix()}",
        f"hex_sha256={hex_sha256}",
        f"dt_flash={'false' if runner == 'pyocd' else 'runner-default'}",
        f"smart_flash={'false' if runner == 'pyocd' else 'runner-default'}",
        "mass_erase_requested=false",
        "recover_requested=false",
        f"exit_code={result.returncode}",
        "command=" + shlex.join(normalized),
        "--- child output ---",
        output.rstrip(),
        "--- end ---",
        "",
    ]
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write("\n".join(lines))
        stream.flush()
        os.fsync(stream.fileno())
    if result.returncode != 0:
        raise ChildCommandError(
            f"[NU54:E_FLASH_WRITE] flash가 종료 코드 {result.returncode}로 실패했습니다: "
            + shlex.join(normalized),
            result.returncode,
        )


## @brief build context와 현재 NCS/toolchain identity가 같은지 확인합니다.
def validate_flash_tool_identity(context: dict[str, Any], tools: dict[str, Any]) -> None:
    expected_paths = {
        "ncs_root": tools["ncs_root"],
        "toolchain_root": tools["toolchain_root"],
        "cxx_compiler": tools["compiler"],
    }
    for key, current in expected_paths.items():
        stored = context.get(key)
        if not isinstance(stored, str) or path_key(stored) != path_key(current):
            raise AdapterError(
                f"[NU54:E_FLASH_TOOLCHAIN_MISMATCH] build context의 {key}가 현재 환경과 다릅니다."
            )
    if context.get("toolchain_bundle_id") != tools["toolchain_root"].name:
        raise AdapterError(
            "[NU54:E_FLASH_TOOLCHAIN_MISMATCH] build와 현재 toolchain bundle이 다릅니다."
        )


## @brief 검증된 Full Zephyr image를 선택 runner로 일반 upload합니다.
def flash(args: argparse.Namespace) -> None:
    if args.runner not in {"pyocd", "jlink"}:
        raise AdapterError(f"[NU54:E_RUNNER_UNAVAILABLE] 지원하지 않는 runner입니다: {args.runner}")
    tools = tool_environment(canonical_path(args.platform_root))
    environment = flash_environment(tools, args.runner)
    session_paths = adapter_paths(args)
    with build_lock(session_paths["state_root"], operation="flash-session"):
        session_context = load_context(args, create=False)
        contextual_paths = paths_from_context(session_paths, session_context)
        with build_lock(contextual_paths["workspace"], operation="flash-cache"):
            validate_flash_tool_identity(session_context, tools)
            inputs = validate_flash_manifest(args)
            if inputs["manifest"].get("context") != session_context:
                raise AdapterError(
                    "[NU54:E_FLASH_CONTEXT] session context가 artifact manifest와 다릅니다."
                )
            validate_runner_configuration(inputs["zephyr_build"], args.runner)
            if args.runner == "pyocd":
                probe_id = select_pyocd_probe(args.probe_id)
            else:
                probe_id = (args.probe_id or "").strip()
                if not probe_id:
                    raise AdapterError(
                        "[NU54:E_PROBE_AMBIGUOUS] J-Link upload에는 명시적인 probe serial이 필요합니다."
                    )
            command = build_flash_command(
                tools, inputs["zephyr_build"], args.runner, probe_id
            )
            print(
                "NU54_UPLOAD_START "
                f"runner={args.runner} probe={probe_id} board={args.board} "
                f"hex_sha256={inputs['hex_sha256']}"
            )
            with probe_lock(probe_id):
                run_flash_process(
                    command,
                    cwd=tools["ncs_root"],
                    environment=environment,
                    log_path=inputs["build_path"] / CONTEXT_DIRECTORY / "logs" / "flash.log",
                    runner=args.runner,
                    probe_id=probe_id,
                    hex_path=inputs["hex"],
                    hex_sha256=inputs["hex_sha256"],
                )
            print(f"NU54_UPLOAD_PASS runner={args.runner} probe={probe_id}")
