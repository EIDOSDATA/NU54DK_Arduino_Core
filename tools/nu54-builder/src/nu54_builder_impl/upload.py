"""! @brief 검증된 artifact의 runner·probe·flash 실행 경계를 소유합니다. """

from __future__ import annotations

from pathlib import Path
from typing import Any
from typing import Sequence
import argparse
import datetime as dt
import hashlib
import locale
import os
import re
import shlex
import shutil
import subprocess
from .artifacts import validate_flash_manifest
from .build import load_context
from .common import AdapterError, CONTEXT_DIRECTORY, ChildCommandError, canonical_path, path_key
from .environment import tool_environment
from .host import canonical_host_os, resolve_toolchain_executable
from .locking import build_lock, probe_lock
from .paths import adapter_paths, paths_from_context


PROBE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{3,127}$")
PROBE_ID_PLACEHOLDERS = {
    "cmsis-dap unique id",
    "j-link serial number",
    "probe unique id",
    "probe uid",
    "j-link-serial-required",
}


## @brief probe identity를 일반 console과 공유 log용으로 마스킹합니다.
def mask_probe_id(probe_id: str) -> str:
    value = probe_id.strip()
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}…{value[-4:]}"


## @brief 원시 probe identity 대신 공유 가능한 SHA-256을 반환합니다.
def probe_id_sha256(probe_id: str) -> str:
    return hashlib.sha256(probe_id.encode("utf-8")).hexdigest()


## @brief placeholder와 형식 오류를 probe 열거 전에 거부합니다.
def validate_probe_id(value: str | None, *, runner: str) -> str:
    requested = (value or "").strip()
    if not requested:
        return ""
    lowered = requested.casefold()
    if runner == "pyocd" and lowered == "auto-single":
        return ""
    if (
        lowered in PROBE_ID_PLACEHOLDERS
        or "{upload.field." in lowered
        or lowered.startswith("enter ")
        or lowered.endswith(" unique id")
        or lowered.endswith(" serial number")
    ):
        raise AdapterError(
            "[NU54:E_PROBE_UID_PLACEHOLDER] Probe identifier placeholder is not a target. "
            "Arduino IDE 2.x에서는 UID 입력 메뉴를 지원하지 않습니다. probe 한 대만 연결하거나 "
            "Arduino CLI의 `--upload-field probe_id=<UID>`를 사용하십시오."
        )
    if not PROBE_ID_PATTERN.fullmatch(requested):
        raise AdapterError(
            "[NU54:E_PROBE_UID_INVALID] Probe identifier format is invalid. "
            f"runner={runner}; 공백 없는 4~128자 영문자·숫자·`.`·`_`·`:`·`-` 값을 사용하십시오."
        )
    return requested


## @brief UTF-8을 우선하고 legacy Windows byte는 Unicode로 변환해 console UTF-8로 다시 출력합니다.
def decode_child_output(data: bytes) -> str:
    try:
        return data.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        encodings = [locale.getpreferredencoding(False), "mbcs", "cp949"]
        for encoding in encodings:
            if not encoding:
                continue
            try:
                return data.decode(encoding, errors="strict")
            except (LookupError, UnicodeDecodeError):
                continue
        return data.decode("cp949", errors="replace")


## @brief child output과 command에서 exact probe identity를 제거합니다.
def redact_probe_identity(text: str, probe_id: str) -> str:
    if not probe_id:
        return text
    return re.sub(re.escape(probe_id), mask_probe_id(probe_id), text, flags=re.IGNORECASE)


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
        raise AdapterError(
            f"[NU54:E_PYOCD_EXEC] pyOCD probe enumeration failed. 고정 Nordic toolchain과 "
            f"USB driver를 확인하십시오: {error}"
        ) from error
    return sorted(
        {str(probe.unique_id) for probe in probes if getattr(probe, "unique_id", None)},
        key=str.casefold,
    )


## @brief 명시값과 발견 목록에서 잘못된 자동 선택 없이 pyOCD probe 하나를 결정합니다.
def select_pyocd_probe(requested: str | None, discovered: Sequence[str] | None = None) -> str:
    probe_ids = list(discovered) if discovered is not None else discover_pyocd_probe_ids()
    requested_id = validate_probe_id(requested, runner="pyocd")
    if requested_id:
        matches = [value for value in probe_ids if value.casefold() == requested_id.casefold()]
        if not matches:
            raise AdapterError(
                "[NU54:E_PROBE_NOT_FOUND] Requested CMSIS-DAP UID is not connected. "
                f"requested={mask_probe_id(requested_id)}; "
                f"detected={', '.join(mask_probe_id(value) for value in probe_ids) or 'none'}. "
                "USB/전원과 UID·COM·보드 역할 매핑을 다시 확인하십시오."
            )
        return matches[0]
    if not probe_ids:
        raise AdapterError(
            "[NU54:E_PROBE_NONE] No CMSIS-DAP probe detected. 데이터 USB cable, target 전원, "
            "Windows 장치 관리자의 CMSIS-DAP를 확인하십시오."
        )
    if len(probe_ids) != 1:
        raise AdapterError(
            "[NU54:E_PROBE_AMBIGUOUS] Multiple CMSIS-DAP probes require an exact UID. detected="
            + ", ".join(mask_probe_id(value) for value in probe_ids)
            + ". Arduino CLI에서 `--upload-field probe_id=<UID>`를 사용하고 COM·보드 역할을 대조하십시오."
        )
    return probe_ids[0]


## @brief 설치된 SEGGER J-Link 실행 directory를 찾습니다.
def discover_jlink_directory(environment: dict[str, str]) -> Path:
    host_os = canonical_host_os("windows" if os.name == "nt" else os.uname().sysname)
    executable_name = "JLink.exe" if host_os == "windows" else "JLinkExe"
    server_name = "JLinkGDBServerCL.exe" if host_os == "windows" else "JLinkGDBServerCLExe"
    candidates: list[Path] = []
    configured = os.environ.get("NUCODE_JLINK_ROOT")
    if configured:
        candidates.append(canonical_path(configured))
    executable = shutil.which(executable_name, path=environment.get("PATH"))
    if executable:
        candidates.append(canonical_path(executable).parent)
    roots = (
        (Path("C:/Program Files/SEGGER"), Path("C:/Program Files (x86)/SEGGER"))
        if host_os == "windows"
        else (Path("/opt/SEGGER"), Path("/Applications/SEGGER"))
    )
    for root in roots:
        if root.is_dir():
            candidates.extend(sorted(root.glob("JLink_*"), reverse=True))
    visited: set[str] = set()
    for candidate in candidates:
        key = path_key(candidate)
        if key in visited:
            continue
        visited.add(key)
        if (candidate / executable_name).is_file() and (candidate / server_name).is_file():
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
        resolve_toolchain_executable(tools["toolchain_root"], "pyocd")
    elif runner == "jlink":
        jlink_directory = discover_jlink_directory(environment)
        environment["PATH"] = str(jlink_directory) + os.pathsep + environment.get("PATH", "")
    return environment


## @brief 선택 runner와 probe로 erase 없는 west flash 명령을 만듭니다.
def build_flash_command(
    tools: dict[str, Any], zephyr_build: Path, runner: str, probe_id: str,
    *, swd_frequency: int | None = None, connect_mode: str = "normal",
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
        command.extend((
            "--dt-flash=n",
            "--tool-opt=-Osmart_flash=false",
            "--tool-opt=-Oauto_unlock=false",
        ))
        if swd_frequency is not None:
            if swd_frequency < 100_000 or swd_frequency > 4_000_000:
                raise AdapterError(
                    "[NU54:E_SWD_DIAGNOSTIC_OPTION] SWD frequency는 100000~4000000 Hz여야 합니다."
                )
            command.append(f"--tool-opt=-Ofrequency={swd_frequency}")
        if connect_mode == "under-reset":
            command.append("--tool-opt=-Oconnect_mode=under-reset")
        elif connect_mode != "normal":
            raise AdapterError(
                f"[NU54:E_SWD_DIAGNOSTIC_OPTION] 지원하지 않는 connect mode입니다: {connect_mode}"
            )
    forbidden = {"--erase", "--recover"}
    if forbidden.intersection(str(value) for value in command):
        raise AdapterError("[NU54:E_FLASH_UNSAFE_OPTION] 일반 upload에 destructive option이 포함됐습니다.")
    return command


## @brief runner 출력의 최초 원인을 사용자 조치가 있는 안정 오류로 분류합니다.
def classify_flash_failure(output: str, runner: str, return_code: int) -> ChildCommandError:
    lowered = output.casefold()
    if any(
        pattern in lowered
        for pattern in (
            "no ack",
            "swd fault",
            "cannot read ap",
            "failed to read ap",
            "unable to find a matching cortex-m",
        )
    ):
        return ChildCommandError(
            "[NU54:E_SWD_NO_ACK] SWD/JTAG access returned No ACK. target 전원·VTref·GND·SWDIO·"
            "SWDCLK, DISABLE_SWD와 다른 debugger 점유를 확인하십시오. 필요하면 명시적으로 "
            "`--swd-frequency 1000000` 또는 `--connect-mode under-reset` 진단을 실행하십시오. "
            "자동 recover·unlock·mass erase는 실행하지 않았습니다.",
            return_code,
        )
    if any(
        pattern in lowered
        for pattern in (
            "target voltage: 0",
            "target power is not detected",
            "no target power",
            "vtref = 0",
        )
    ):
        return ChildCommandError(
            "[NU54:E_TARGET_POWER] Target power or VTref is not detected. 보드 전원과 "
            "debugger VTref/GND 연결을 확인하십시오.",
            return_code,
        )
    if any(
        pattern in lowered
        for pattern in (
            "failed to connect to target",
            "cannot connect to target",
            "target is not responding",
            "unable to connect to target",
        )
    ):
        return ChildCommandError(
            "[NU54:E_TARGET_UNRESPONSIVE] Probe is present but the target did not respond. "
            "전원·SWD 배선·debug-control과 다른 debugger 점유를 확인하십시오.",
            return_code,
        )
    if any(
        pattern in lowered
        for pattern in (
            "programming failed",
            "failed to program",
            "verify failed",
            "flash operation failed",
            "erase failed",
        )
    ):
        return ChildCommandError(
            "[NU54:E_FLASH_WRITE] Flash program or verify failed after runner start. image와 "
            "target identity를 확인하고 sector upload를 안전하게 다시 시도하십시오.",
            return_code,
        )
    code = "E_PYOCD_EXEC" if runner == "pyocd" else "E_JLINK_EXEC"
    action = (
        "고정 Nordic toolchain의 pyOCD와 USB driver를 확인하십시오."
        if runner == "pyocd"
        else "SEGGER J-Link Software 설치와 외장 J-Link SWD/VTref/GND 연결을 확인하십시오."
    )
    return ChildCommandError(
        f"[NU54:{code}] {runner} runner exited with code {return_code}. {action}",
        return_code,
    )


## @brief flash child process의 출력과 결과를 console 및 build log에 기록합니다.
def run_flash_process(
    command: Sequence[str | Path], *, cwd: Path, environment: dict[str, str], log_path: Path,
    runner: str, probe_id: str, hex_path: Path, hex_sha256: str
) -> None:
    normalized = [str(value) for value in command]
    started = dt.datetime.now(dt.timezone.utc)
    try:
        result = subprocess.run(
            normalized,
            cwd=cwd,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
    except OSError as error:
        code = "E_PYOCD_EXEC" if runner == "pyocd" else "E_JLINK_EXEC"
        raise AdapterError(
            f"[NU54:{code}] {runner} runner process could not start. 설치 경로와 실행 권한을 "
            f"확인하십시오: {error}"
        ) from error
    output = redact_probe_identity(decode_child_output(result.stdout), probe_id)
    if output:
        print(output, end="" if output.endswith("\n") else "\n")
    finished = dt.datetime.now(dt.timezone.utc)
    lines = [
        f"started_at_utc={started.isoformat()}",
        f"finished_at_utc={finished.isoformat()}",
        f"runner={runner}",
        f"probe_id={mask_probe_id(probe_id)}",
        f"probe_id_sha256={probe_id_sha256(probe_id)}",
        f"hex={hex_path.as_posix()}",
        f"hex_sha256={hex_sha256}",
        f"dt_flash={'false' if runner == 'pyocd' else 'runner-default'}",
        f"smart_flash={'false' if runner == 'pyocd' else 'runner-default'}",
        "mass_erase_requested=false",
        "recover_requested=false",
        f"exit_code={result.returncode}",
        "command=" + redact_probe_identity(shlex.join(normalized), probe_id),
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
        raise classify_flash_failure(output, runner, result.returncode)


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
            for runner_build in inputs.get("runner_builds", [inputs["zephyr_build"]]):
                validate_runner_configuration(runner_build, args.runner)
            if args.runner == "pyocd":
                requested = args.probe_id or os.environ.get("NUCODE_PROBE_UID")
                probe_id = select_pyocd_probe(requested)
            else:
                probe_id = validate_probe_id(
                    args.probe_id or os.environ.get("NUCODE_PROBE_UID"), runner="jlink"
                )
                if not probe_id:
                    raise AdapterError(
                        "[NU54:E_PROBE_AMBIGUOUS] J-Link upload requires an exact serial. "
                        "Arduino CLI의 `--upload-field probe_id=<serial>`을 사용하고 외장 J-Link의 "
                        "SWD·VTref·GND 연결을 확인하십시오."
                    )
            command = build_flash_command(
                tools,
                inputs["zephyr_build"],
                args.runner,
                probe_id,
                swd_frequency=args.swd_frequency,
                connect_mode=args.connect_mode,
            )
            print(
                "NU54_UPLOAD_START "
                f"runner={args.runner} probe={mask_probe_id(probe_id)} board={args.board} "
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
            print(f"NU54_UPLOAD_PASS runner={args.runner} probe={mask_probe_id(probe_id)}")
