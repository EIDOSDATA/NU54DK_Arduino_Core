#!/usr/bin/env python3
"""! @brief 공개 CSIP Arduino 예제의 3보드 자동 HIL을 수행합니다.

원시 probe UID를 다루지 않고, 사전에 확인한 보드/COM/probe SHA-256 매핑만
사용합니다. 선택적으로 SHA-256 전용 pyOCD helper를 호출해 reset/halt/go를
수행하며 사용자 입력이나 전원 재인가는 요구하지 않습니다.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from typing import Any, Callable, Sequence


ROLES = ("coordinator", "member_one", "member_two")
BOARD_LABELS = {
    "coordinator": "G",
    "member_one": "F",
    "member_two": "E",
}
MEMBER_RANKS = {"member_one": 1, "member_two": 2}
HASH_PATTERN = re.compile(r"[0-9a-f]{64}")
REVISION_PATTERN = re.compile(r"[0-9a-f]{40}")
RANK_PATTERN = re.compile(r"^Member rank ([12]) of (\d+)$")
RESET_NOISE_NON_ASCII_ESCAPE_PATTERN = re.compile(r"\\x[89a-fA-F][0-9a-fA-F]")
RESET_NOISE_MARKER_PATTERN = re.compile(r"<reset-uart-noise chars=[1-9][0-9]*>")
RESET_NOISE_PREFIX_LIMIT = 768
ADDRESS_PATTERN = re.compile(r"\b[0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5}\b")
IDENTIFIER_PATTERN = re.compile(r"(?i)(?<![0-9a-f])[0-9a-f]{16,}(?![0-9a-f])")
FATAL_TOKENS = ("Stack overflow", "FATAL ERROR", "***** Hardware exception")
DEBUG_FAILURE_PATTERN = re.compile(
    r"(?i)(?:\btraceback\b|\berror\b|communication failure|no ack|unexpected ack)"
)
DEBUG_EVIDENCE_LIMIT = 800
TOTAL_TIMEOUT_SECONDS = 180.0
RECOVERY_TIMEOUT_SECONDS = 30.0
MARK_QUIET_SECONDS = 0.12
MARK_MAXIMUM_SECONDS = 0.75
ARDUINO_CLI_PATH = Path(r"C:\Program Files\Arduino CLI\arduino-cli.exe")
ARDUINO_CONFIG_PATH = Path(__file__).with_name("arduino-dev") / "arduino-cli.yaml"
ARDUINO_FQBN = "nucode:zephyr:nu54dk:feature_set=ble,upload_probe=pyocd"
EXPECTED_DEBUG_HELPER_SHA256 = (
    "a2d9c1a83198a3e28c6d2562320697edbbc3adba03ce10c8e6295ffde310a7a2"
)
DEBUG_HELPER_INTERNAL_TIMEOUT_SECONDS = 20.0
DEBUG_HELPER_CLEANUP_MARGIN_SECONDS = 1.0

FAULT_MUTATIONS = {
    "wrong-sirk": ("member_two", "wrong_sirk_key", "NUCODE_CSIP_FAULT_WRONG_SIRK"),
    "security-sync-failure": (
        "coordinator",
        "security_request_invalid_handle",
        "NUCODE_CSIP_FAULT_SECURITY_SYNC_FAILURE",
    ),
    "security-async-failure": (
        "coordinator",
        "security_level_negotiation_async_failure",
        "NUCODE_CSIP_FAULT_SECURITY_ASYNC_FAILURE",
    ),
    "watchdog": (
        "coordinator",
        "progress_deadline_forced_expiry",
        "NUCODE_CSIP_FAULT_WATCHDOG",
    ),
}

EXPECTED_BOARD_MAP = {
    "coordinator": {
        "board": "G",
        "port": "COM10",
        "probe_sha256": (
            "e44e2ba24dbcbdd3c41e05192773a058"
            "ed7dbbca2354dda703a004646ea9a334"
        ),
    },
    "member_one": {
        "board": "F",
        "port": "COM14",
        "probe_sha256": (
            "4574ee31f25fe05f154395ea4d8c6aa0"
            "583b04a4f7a0ea97fe3d13b05eea8ca0"
        ),
    },
    "member_two": {
        "board": "E",
        "port": "COM13",
        "probe_sha256": (
            "32f71533ff6ba27fd38ed32a17bf6d80"
            "a90d4f4980221051ed5c5a2e7fdb63a9"
        ),
    },
}

PUBLIC_EXAMPLES = {
    "coordinator": Path(
        "libraries/NUCODE_BLE_Audio/examples/CsipSetCoordinator/"
        "CsipSetCoordinator.ino"
    ),
    "member": Path(
        "libraries/NUCODE_BLE_Audio/examples/CsipSetMember/CsipSetMember.ino"
    ),
}

TOKENS = {
    "coordinator_search": "Searching for two set members",
    "coordinator_ready": "Set ready; send o to order, l to lock, u to release",
    "operation_rejected": "Set operation rejected",
    "member_rank_one": "Member rank 1 of 2",
    "member_rank_two": "Member rank 2 of 2",
    "member_rank_prompt": "Enter this member rank (1 or 2):",
    "member_ready": "Set member ready; send a to authorize SIRK read, f to force-release",
    "authorization_prompt": (
        "Set member bonded; physically verify the controller, then send a"
    ),
    "authorization_success": "Bonded controller identity authorized",
    "locked": "Set locked",
    "released": "Set released",
    "security_sync_failure": "Set coordinator security request failed",
    "security_async_failure": "Set coordinator security failed",
    "watchdog": "Set coordinator progress timeout",
}


class HilFailure(RuntimeError):
    """! @brief CSIP HIL 판정 실패를 나타냅니다. """


@dataclass(frozen=True)
class Event:
    """! @brief 한 UART에서 수집한 정제된 한 줄을 보존합니다. """

    sequence: int
    at_s: float
    role: str
    text: str


def utc_now() -> str:
    """! @brief UTC 시각을 ISO 8601 형식으로 반환합니다. """
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    """! @brief 입력 파일의 SHA-256만 계산합니다. """
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_source_bytes(path: Path) -> bytes:
    """! @brief checkout별 줄바꿈 차이를 제거한 source bytes를 반환합니다. """
    return path.read_bytes().replace(b"\r\n", b"\n")


def sha256_source_file(path: Path) -> str:
    """! @brief 줄바꿈을 LF로 정규화한 source SHA-256을 계산합니다. """
    return hashlib.sha256(canonical_source_bytes(path)).hexdigest()


def normalize_reset_noise_line(text: str) -> str:
    """! @brief 긴 reset UART noise를 길이 marker와 exact boot token으로 정규화합니다. """
    for token in (TOKENS["coordinator_search"], TOKENS["member_rank_prompt"]):
        if not text.endswith(token):
            continue
        prefix = text[: -len(token)]
        if RESET_NOISE_NON_ASCII_ESCAPE_PATTERN.search(prefix) is not None:
            return f"<reset-uart-noise chars={len(prefix)}>{token}"
    return text


def matches_token_after_reset_noise(text: str, token: str) -> bool:
    """! @brief reset 경계의 bounded 비ASCII UART noise 뒤 exact token만 허용합니다. """
    if text == token:
        return True
    if not text.endswith(token):
        return False
    prefix = text[: -len(token)]
    return (
        RESET_NOISE_MARKER_PATTERN.fullmatch(prefix) is not None
        or (
            0 < len(prefix) <= RESET_NOISE_PREFIX_LIMIT
            and RESET_NOISE_NON_ASCII_ESCAPE_PATTERN.search(prefix) is not None
        )
        or (
            0 < len(prefix) <= 4
            and all(
                ord(character) < 0x20 or ord(character) == 0x7F
                for character in prefix
            )
        )
    )


def verify_source(core_root: Path, expected_revision: str) -> dict[str, str]:
    """! @brief exact commit·clean checkout·공개 예제 hash를 확인합니다. """
    try:
        head = subprocess.check_output(
            ("git", "rev-parse", "HEAD"), cwd=core_root, text=True
        ).strip()
        dirty = subprocess.check_output(
            ("git", "status", "--porcelain=v1", "--untracked-files=all"),
            cwd=core_root,
            text=True,
        ).strip()
    except (OSError, subprocess.CalledProcessError) as error:
        raise HilFailure(f"Core source 확인 실패: {error}") from error
    if head != expected_revision:
        raise HilFailure(
            f"Core revision 불일치: expected={expected_revision}, actual={head}"
        )
    if dirty:
        raise HilFailure("Core source가 untracked 파일을 포함해 clean 상태가 아닙니다.")
    hashes: dict[str, str] = {}
    for role, relative_path in PUBLIC_EXAMPLES.items():
        source = core_root / relative_path
        if not source.is_file():
            raise HilFailure(f"공개 {role} 예제를 찾을 수 없습니다: {source}")
        hashes[role] = sha256_source_file(source)
    return hashes


def resolve_manifest_path(manifest_path: Path, value: Any, field: str) -> Path:
    """! @brief manifest의 상대 artifact 경로를 manifest 기준으로 해석합니다. """
    if not isinstance(value, str) or not value:
        raise HilFailure(f"fault manifest {field}가 비어 있습니다.")
    path = Path(value)
    if not path.is_absolute():
        path = manifest_path.parent / path
    path = path.resolve()
    if not path.is_file():
        raise HilFailure(f"fault manifest {field} 파일이 없습니다: {path}")
    return path


def verify_build_command(
    command: Any,
    source_directory: Path,
    build_path: Path,
    description: str,
) -> None:
    """! @brief Arduino CLI clean build 명령의 위치·중복·대상을 exact 검사합니다. """
    if not isinstance(command, list) or not all(
        isinstance(value, str) for value in command
    ):
        raise HilFailure(f"{description} build_command 형식이 잘못되었습니다.")
    if len(command) != 10:
        raise HilFailure(f"{description} build_command 인자 수가 exact 형식과 다릅니다.")
    expected_literals = {
        1: "compile",
        2: "--config-file",
        4: "--fqbn",
        5: ARDUINO_FQBN,
        6: "--clean",
        7: "--build-path",
    }
    if any(command[index] != value for index, value in expected_literals.items()):
        raise HilFailure(f"{description} build_command option 순서 또는 값이 다릅니다.")
    if Path(command[0]).resolve() != ARDUINO_CLI_PATH.resolve():
        raise HilFailure(f"{description} build_command가 exact Arduino CLI가 아닙니다.")
    if Path(command[3]).resolve() != ARDUINO_CONFIG_PATH.resolve():
        raise HilFailure(f"{description} build_command가 exact config를 쓰지 않습니다.")
    if Path(command[8]).resolve() != build_path.resolve():
        raise HilFailure(f"{description} build_command의 build path가 다릅니다.")
    if Path(command[9]).resolve() != source_directory.resolve():
        raise HilFailure(f"{description} build_command의 sketch target이 다릅니다.")


def verify_fault_manifest(
    args: argparse.Namespace,
    core_root: Path,
    source_hashes: dict[str, str],
    images: dict[str, Path],
    image_hashes: dict[str, str],
) -> dict[str, Any] | None:
    """! @brief mode별 fault source·patch·baseline·image 계보를 검증합니다. """
    if args.mode not in FAULT_MUTATIONS:
        return None
    manifest_path = args.fault_manifest.resolve()
    try:
        document = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise HilFailure(f"fault manifest 읽기 실패: {error}") from error
    if not isinstance(document, dict):
        raise HilFailure("fault manifest root는 object여야 합니다.")

    expected_role, expected_mutation, expected_marker = FAULT_MUTATIONS[args.mode]
    source_role = "member" if expected_role == "member_two" else "coordinator"
    required = {
        "schema": "nucode.m31.csip-fault-build.v1",
        "mode": args.mode,
        "role": expected_role,
        "mutation_id": expected_mutation,
        "required_source_marker": expected_marker,
        "core_revision": args.core_revision,
        "public_example_sha256": source_hashes[source_role],
        "image_sha256": image_hashes[expected_role],
        "fqbn": ARDUINO_FQBN,
    }
    for field, expected in required.items():
        if document.get(field) != expected:
            raise HilFailure(
                f"fault manifest {field} 불일치: expected={expected!r}, "
                f"actual={document.get(field)!r}"
            )

    fault_source = resolve_manifest_path(
        manifest_path, document.get("fault_source_path"), "fault_source_path"
    )
    patch_path = resolve_manifest_path(
        manifest_path, document.get("patch_path"), "patch_path"
    )
    baseline_image = resolve_manifest_path(
        manifest_path, document.get("baseline_image_path"), "baseline_image_path"
    )
    fault_image = resolve_manifest_path(
        manifest_path, document.get("image_path"), "image_path"
    )
    if fault_source.is_relative_to(core_root):
        raise HilFailure("fault source는 공개 Core checkout 밖의 artifact여야 합니다.")
    declared_hashes = {
        "fault_source_sha256": sha256_file(fault_source),
        "patch_sha256": sha256_file(patch_path),
        "baseline_image_sha256": sha256_file(baseline_image),
    }
    for field, actual in declared_hashes.items():
        declared = document.get(field)
        if HASH_PATTERN.fullmatch(declared or "") is None or declared != actual:
            raise HilFailure(
                f"fault manifest {field} 불일치: declared={declared!r}, actual={actual}"
            )
    if document["baseline_image_sha256"] == document["image_sha256"]:
        raise HilFailure("fault image는 exact baseline image와 달라야 합니다.")
    if expected_marker not in fault_source.read_text(encoding="utf-8"):
        raise HilFailure("fault source에 mode별 marker가 없습니다.")
    if expected_marker not in patch_path.read_text(encoding="utf-8"):
        raise HilFailure("fault patch에 mode별 marker가 없습니다.")
    if images[expected_role] != fault_image:
        raise HilFailure("fault manifest image_path가 role image와 다릅니다.")

    public_relative = PUBLIC_EXAMPLES[source_role]
    public_source = core_root / public_relative
    if fault_source.name != public_source.name:
        raise HilFailure("fault source 파일명은 exact 공개 sketch 이름이어야 합니다.")
    compilable_suffixes = {".ino", ".pde", ".c", ".cc", ".cpp", ".cxx", ".s"}
    compilable_sources = sorted(
        path.resolve()
        for path in fault_source.parent.rglob("*")
        if path.is_file() and path.suffix.casefold() in compilable_suffixes
    )
    if compilable_sources != [fault_source]:
        raise HilFailure("fault compile directory에는 exact fault sketch만 있어야 합니다.")
    with tempfile.TemporaryDirectory(prefix="csip-fault-verify-") as directory:
        reconstruction_root = Path(directory)
        reconstructed_source = reconstruction_root / public_relative
        reconstructed_source.parent.mkdir(parents=True, exist_ok=True)
        reconstructed_source.write_bytes(public_source.read_bytes())
        initialized = subprocess.run(
            ("git", "init", "--quiet"),
            cwd=reconstruction_root,
            capture_output=True,
            text=True,
            check=False,
        )
        checked = subprocess.run(
            ("git", "apply", "--check", str(patch_path)),
            cwd=reconstruction_root,
            capture_output=True,
            text=True,
            check=False,
        )
        applied = subprocess.run(
            ("git", "apply", str(patch_path)),
            cwd=reconstruction_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if initialized.returncode != 0 or checked.returncode != 0 or applied.returncode != 0:
            raise HilFailure("fault patch가 exact 공개 예제에 clean 적용되지 않습니다.")
        reconstructed_files = sorted(
            path.relative_to(reconstruction_root).as_posix()
            for path in reconstruction_root.rglob("*")
            if path.is_file() and ".git" not in path.parts
        )
        if reconstructed_files != [public_relative.as_posix()]:
            raise HilFailure("fault patch가 공개 예제 외의 추가 source를 만들었습니다.")
        if canonical_source_bytes(reconstructed_source) != canonical_source_bytes(
            fault_source
        ):
            raise HilFailure("공개 예제에 patch를 적용한 결과가 fault source와 다릅니다.")

    build_command = document.get("build_command")
    build_path_value = document.get("build_path")
    if not isinstance(build_path_value, str) or not build_path_value:
        raise HilFailure("fault manifest build_path가 없습니다.")
    build_path = Path(build_path_value).resolve()
    verify_build_command(build_command, fault_source.parent, build_path, "fault")
    if not ARDUINO_CLI_PATH.is_file() or not ARDUINO_CONFIG_PATH.is_file():
        raise HilFailure("exact Arduino CLI 또는 config가 없습니다.")
    if fault_image.parent != build_path:
        raise HilFailure("fault image가 manifest clean build path 밖에 있습니다.")

    baseline_manifest = resolve_manifest_path(
        manifest_path,
        document.get("baseline_manifest_path"),
        "baseline_manifest_path",
    )
    try:
        baseline_document = json.loads(baseline_manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise HilFailure(f"baseline manifest 읽기 실패: {error}") from error
    baseline_required = {
        "schema": "nucode.m31.csip-baseline-build.v1",
        "role": source_role,
        "core_revision": args.core_revision,
        "public_example_sha256": source_hashes[source_role],
        "image_sha256": declared_hashes["baseline_image_sha256"],
        "fqbn": ARDUINO_FQBN,
    }
    if not isinstance(baseline_document, dict) or any(
        baseline_document.get(field) != expected
        for field, expected in baseline_required.items()
    ):
        raise HilFailure("baseline manifest의 exact source/build 필드가 다릅니다.")
    baseline_source = resolve_manifest_path(
        baseline_manifest,
        baseline_document.get("source_path"),
        "baseline source_path",
    )
    baseline_receipt_image = resolve_manifest_path(
        baseline_manifest,
        baseline_document.get("image_path"),
        "baseline image_path",
    )
    if baseline_source != public_source or baseline_receipt_image != baseline_image:
        raise HilFailure("baseline manifest가 exact 공개 source/image를 가리키지 않습니다.")
    baseline_build_path_value = baseline_document.get("build_path")
    if not isinstance(baseline_build_path_value, str) or not baseline_build_path_value:
        raise HilFailure("baseline manifest build_path가 없습니다.")
    baseline_build_path = Path(baseline_build_path_value).resolve()
    verify_build_command(
        baseline_document.get("build_command"),
        public_source.parent,
        baseline_build_path,
        "baseline",
    )
    if baseline_image.parent != baseline_build_path:
        raise HilFailure("baseline image가 receipt build path 밖에 있습니다.")
    if expected_role == "member_two" and (
        image_hashes["member_one"] != declared_hashes["baseline_image_sha256"]
    ):
        raise HilFailure("wrong-SIRK baseline은 exact F/member-one stock image여야 합니다.")
    return {
        "path": str(manifest_path),
        "sha256": sha256_file(manifest_path),
        "mode": args.mode,
        "role": expected_role,
        "mutation_id": expected_mutation,
        "fault_source_sha256": declared_hashes["fault_source_sha256"],
        "patch_sha256": declared_hashes["patch_sha256"],
        "baseline_image_sha256": declared_hashes["baseline_image_sha256"],
        "baseline_manifest_path": str(baseline_manifest),
        "baseline_manifest_sha256": sha256_file(baseline_manifest),
    }


def sanitize_line(line: str) -> str:
    """! @brief UART의 주소와 긴 장치 식별자를 외부 증적에서 제거합니다. """
    line = ADDRESS_PATTERN.sub("<bt-address>", line)
    return IDENTIFIER_PATTERN.sub("<device-identifier>", line)


def inspect_debug_output(raw_output: str) -> tuple[str, bool]:
    """! @brief 전체 debug 출력을 검사하고 bounded 증적 문자열을 만듭니다. """
    stripped = raw_output.strip()
    failed = DEBUG_FAILURE_PATTERN.search(stripped) is not None
    sanitized = sanitize_line(stripped).replace("\r", "\\r").replace("\n", "\\n")
    if len(sanitized) <= DEBUG_EVIDENCE_LIMIT:
        return sanitized, failed

    digest = hashlib.sha256(stripped.encode("utf-8")).hexdigest()
    marker = f"...<truncated sha256={digest}>..."
    side = (DEBUG_EVIDENCE_LIMIT - len(marker)) // 2
    summary = sanitized[:side] + marker + sanitized[-side:]
    return summary[:DEBUG_EVIDENCE_LIMIT], failed


def debug_helper_invocation(
    helper: Path,
    probe_hash: str,
    commands: Sequence[str],
) -> tuple[str, ...]:
    """! @brief SHA-256와 공개 helper 인자만 포함한 명령을 구성합니다. """
    return (
        sys.executable,
        str(helper),
        probe_hash,
        *commands,
        "--connect",
        "halt",
    )


def compute_debug_outer_timeout(requested: float, remaining: float) -> float:
    """! @brief campaign 정리 여유를 남긴 helper outer timeout을 계산합니다. """
    outer_timeout = min(
        requested, remaining - DEBUG_HELPER_CLEANUP_MARGIN_SECONDS
    )
    minimum = (
        DEBUG_HELPER_INTERNAL_TIMEOUT_SECONDS
        + DEBUG_HELPER_CLEANUP_MARGIN_SECONDS
    )
    if outer_timeout <= minimum:
        raise HilFailure(
            "debug helper를 시작할 내부 timeout+정리 여유가 부족합니다."
        )
    return outer_timeout


class Campaign:
    """! @brief 세 UART와 SHA-256 기반 debug 동작을 조정합니다. """

    def __init__(
        self,
        serial_module: Any,
        ports: dict[str, str],
        probe_hashes: dict[str, str],
        baud: int,
        transcript_path: Path,
        execute_reset: bool,
        reset_helper: Path,
        reset_timeout: float,
        total_timeout: float,
    ) -> None:
        self.serial_module = serial_module
        self.ports = ports
        self.probe_hashes = probe_hashes
        self.baud = baud
        self.transcript_path = transcript_path
        self.execute_reset = execute_reset
        self.reset_helper = reset_helper
        self.reset_timeout = reset_timeout
        self.started = time.monotonic()
        self.deadline = self.started + total_timeout
        self.streams: dict[str, Any] = {}
        self.pending = {role: bytearray() for role in ROLES}
        self.events: list[Event] = []
        self.transcript: Any = None
        self.last_pump_had_bytes = False
        self.pre_reset_uart_quarantine: dict[str, dict[str, Any]] = {}

    def __enter__(self) -> Campaign:
        """! @brief 명시된 COM만 열고 기존 수신 자료는 폐기하지 않습니다. """
        self.transcript_path.parent.mkdir(parents=True, exist_ok=True)
        self.transcript = self.transcript_path.open(
            "x", encoding="utf-8", newline="\n"
        )
        try:
            for role in ROLES:
                self.streams[role] = self.serial_module.Serial(
                    self.ports[role],
                    self.baud,
                    timeout=0.02,
                    write_timeout=2.0,
                )
        except Exception:
            self.close()
            raise
        return self

    def __exit__(self, exception_type: Any, exception: Any, traceback: Any) -> None:
        """! @brief 성공·실패와 무관하게 UART와 transcript를 닫습니다. """
        self.close()

    def close(self) -> None:
        """! @brief 열린 자원을 중복 호출에 안전하게 정리합니다. """
        for stream in self.streams.values():
            try:
                stream.close()
            except Exception:
                pass
        self.streams.clear()
        if self.transcript is not None:
            self.transcript.close()
            self.transcript = None

    def mark(self) -> int:
        """! @brief pending UART를 quiet window까지 수집한 뒤 경계를 반환합니다. """
        started = time.monotonic()
        quiet_since: float | None = None
        while True:
            self.ensure_time("UART action 경계")
            self.pump()
            now = time.monotonic()
            if self.last_pump_had_bytes or any(self.pending.values()):
                quiet_since = None
            elif quiet_since is None:
                quiet_since = now
            elif (now - quiet_since) >= MARK_QUIET_SECONDS:
                return len(self.events)
            if (now - started) >= MARK_MAXIMUM_SECONDS:
                raise HilFailure("UART action 경계에서 실제 byte quiet를 확보하지 못했습니다.")
            time.sleep(0.005)

    def quarantine_pre_reset_uart(self, role: str) -> int:
        """! @brief halt 뒤 제어 reset 직전의 이전 UART byte를 계수하고 격리합니다. """
        stream = self.streams[role]
        pending = self.pending[role]
        count = len(pending)
        pending.clear()
        waiting = stream.in_waiting
        if waiting > 0:
            count += len(stream.read(waiting))
        reset_input_buffer = getattr(stream, "reset_input_buffer", None)
        input_buffer_purged = callable(reset_input_buffer)
        if input_buffer_purged:
            reset_input_buffer()
        self.pre_reset_uart_quarantine[role] = {
            "observed_bytes": count,
            "input_buffer_purged": input_buffer_purged,
        }
        self.record(
            "runner",
            f"pre-reset UART quarantine board={BOARD_LABELS[role]} "
            f"observed_bytes={count} "
            f"input_buffer_purged={str(input_buffer_purged).lower()}",
        )
        return count

    def remaining(self, description: str) -> float:
        """! @brief 전체 180초 계약 안에서 남은 시간을 반환합니다. """
        remaining = self.deadline - time.monotonic()
        if remaining <= 0.0:
            raise HilFailure(f"전체 180초 timeout: {description}")
        return remaining

    def ensure_time(self, description: str) -> None:
        """! @brief 전체 campaign deadline을 넘지 않았는지 확인합니다. """
        self.remaining(description)

    def bounded_timeout(self, requested: float, description: str) -> float:
        """! @brief 부분 timeout을 전체 campaign 잔여 시간으로 제한합니다. """
        return min(requested, self.remaining(description))

    def record(self, role: str, text: str) -> Event:
        """! @brief 정제된 한 줄을 시간순 증적에 추가합니다. """
        event = Event(
            sequence=len(self.events),
            at_s=round(time.monotonic() - self.started, 3),
            role=role,
            text=sanitize_line(text[:800]),
        )
        self.events.append(event)
        self.transcript.write(
            f"{event.at_s:09.3f}|{event.role}|{event.text}\n"
        )
        self.transcript.flush()
        if role in ROLES and any(token in event.text for token in FATAL_TOKENS):
            raise HilFailure(f"{role} fatal UART: {event.text}")
        return event

    def pump(self) -> list[Event]:
        """! @brief 세 UART의 현재 가용 줄을 공통 시간축으로 수집합니다. """
        captured: list[Event] = []
        self.last_pump_had_bytes = False
        for role, stream in self.streams.items():
            data = stream.read(stream.in_waiting or 1)
            if not data:
                continue
            self.last_pump_had_bytes = True
            self.pending[role].extend(data)
            while b"\n" in self.pending[role]:
                raw, _, remainder = self.pending[role].partition(b"\n")
                self.pending[role] = bytearray(remainder)
                text = raw.rstrip(b"\r").decode(
                    "utf-8", errors="backslashreplace"
                )
                fatal_token = next(
                    (token for token in FATAL_TOKENS if token in text), None
                )
                if fatal_token is not None:
                    self.record(
                        role,
                        f"{fatal_token} observed in UART line chars={len(text)}",
                    )
                text = normalize_reset_noise_line(text)
                captured.append(self.record(role, text))
        return captured

    def wait_event(
        self,
        predicate: Callable[[Event], bool],
        timeout: float,
        since: int,
        description: str,
    ) -> Event:
        """! @brief event 조건을 bounded timeout 안에서 기다립니다. """
        deadline = time.monotonic() + self.bounded_timeout(timeout, description)
        cursor = since
        while time.monotonic() < deadline:
            self.ensure_time(description)
            self.pump()
            while cursor < len(self.events):
                event = self.events[cursor]
                cursor += 1
                if predicate(event):
                    return event
            time.sleep(0.005)
        recent = " | ".join(
            f"{event.role}:{event.text}" for event in self.events[-12:]
        )
        raise HilFailure(f"timeout: {description}; recent={recent}")

    def wait_token(
        self,
        role: str,
        token: str,
        timeout: float,
        since: int,
        *,
        allow_reset_noise: bool = False,
    ) -> Event:
        """! @brief 특정 role의 exact 공개 token을 기다립니다. """
        return self.wait_event(
            lambda event: event.role == role
            and (
                event.text == token
                or (
                    allow_reset_noise
                    and matches_token_after_reset_noise(event.text, token)
                )
            ),
            timeout,
            since,
            f"{role}:{token}",
        )

    def assert_absent(
        self,
        role: str,
        tokens: Sequence[str],
        seconds: float,
        since: int,
    ) -> None:
        """! @brief quiet window 동안 금지 token이 없음을 확인합니다. """
        deadline = time.monotonic() + self.bounded_timeout(
            seconds, f"{role} 금지 token quiet window"
        )
        cursor = since
        while time.monotonic() < deadline:
            self.ensure_time(f"{role} 금지 token quiet window")
            self.pump()
            while cursor < len(self.events):
                event = self.events[cursor]
                cursor += 1
                if event.role == role and event.text in tokens:
                    raise HilFailure(
                        f"금지 token 관측: {role}:{event.text}"
                    )
            time.sleep(0.005)

    def command(self, role: str, command: str) -> None:
        """! @brief 공개 sketch가 정의한 한 글자 명령만 전송합니다. """
        if len(command) != 1 or command not in "12aoulf":
            raise HilFailure(f"허용되지 않은 공개 명령: {command!r}")
        payload = command.encode("ascii")
        written = self.streams[role].write(payload)
        self.streams[role].flush()
        if written != len(payload):
            raise HilFailure(f"{role} UART 명령이 일부만 기록됐습니다.")
        self.record("runner", f"command board={BOARD_LABELS[role]} value={command}")

    def debug_command(
        self,
        role: str,
        action: str,
        commands: Sequence[str],
    ) -> dict[str, Any]:
        """! @brief 원시 UID 없이 hash helper로 bounded debug 명령을 수행합니다. """
        if not self.execute_reset:
            raise HilFailure(f"{action}에는 --execute-reset이 필요합니다.")
        outer_timeout = compute_debug_outer_timeout(
            self.reset_timeout, self.remaining(action)
        )
        invocation = debug_helper_invocation(
            self.reset_helper,
            self.probe_hashes[role],
            commands,
        )
        try:
            completed = subprocess.run(
                invocation,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="backslashreplace",
                timeout=outer_timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise HilFailure(f"{action} helper 실행 실패: {error}") from error
        output, debug_failed = inspect_debug_output(
            completed.stdout + completed.stderr
        )
        self.record(
            "runner",
            f"debug board={BOARD_LABELS[role]} action={action} "
            f"rc={completed.returncode} output={output}",
        )
        if completed.returncode != 0 or debug_failed:
            raise HilFailure(
                f"{action} helper 실패: rc={completed.returncode} output={output}"
            )
        return {
            "board": BOARD_LABELS[role],
            "action": action,
            "returncode": completed.returncode,
            "sanitized_output": output,
        }

    def reset_and_go(self, role: str) -> dict[str, Any]:
        """! @brief 지정 보드를 hardware reset 후 즉시 실행합니다. """
        return self.debug_command(role, "reset-and-go", ("reset", "go"))

    def halt(self, role: str) -> dict[str, Any]:
        """! @brief 지정 보드를 halt하여 무선 loss를 유도합니다. """
        return self.debug_command(role, "halt", ("halt",))

    def boot_members(
        self,
        ranks: dict[str, int],
        timeout: float,
        reset_boundaries: dict[str, int],
    ) -> int:
        """! @brief 두 member의 boot prompt 뒤 요청 rank를 입력합니다. """
        for role in ("member_one", "member_two"):
            self.wait_token(
                role,
                TOKENS["member_rank_prompt"],
                timeout,
                reset_boundaries[role],
                allow_reset_noise=True,
            )
            self.command(role, str(ranks[role]))
        for role in ("member_one", "member_two"):
            self.wait_token(
                role,
                TOKENS["member_ready"],
                timeout,
                reset_boundaries[role],
            )
        return reset_boundaries["coordinator"]

    def authorize_until_ready(
        self,
        timeout: float,
        since: int,
        ranks: dict[str, int] | None = None,
        required_authorizations: set[str] | None = None,
    ) -> Event:
        """! @brief 검증된 보드 매핑의 매 exact 연결마다 a를 자동 전송합니다. """
        required = (
            set(MEMBER_RANKS)
            if required_authorizations is None
            else set(required_authorizations)
        )
        deadline = time.monotonic() + self.bounded_timeout(
            timeout, "두 member 승인과 검색"
        )
        cursor = since
        authorized_prompt_sequences: set[int] = set()
        rank_prompt_sequences: set[int] = set()
        authorization_success_sequences: dict[str, int] = {}
        while time.monotonic() < deadline:
            self.ensure_time("두 member 승인과 검색")
            self.pump()
            while cursor < len(self.events):
                event = self.events[cursor]
                cursor += 1
                if event.role == "coordinator" and event.text == TOKENS["coordinator_ready"]:
                    if required.issubset(authorization_success_sequences) and all(
                        sequence < event.sequence
                        for sequence in authorization_success_sequences.values()
                    ):
                        return event
                    continue
                if (
                    ranks is not None
                    and event.role in ranks
                    and matches_token_after_reset_noise(
                        event.text, TOKENS["member_rank_prompt"]
                    )
                    and event.sequence not in rank_prompt_sequences
                ):
                    rank_prompt_sequences.add(event.sequence)
                    self.command(event.role, str(ranks[event.role]))
                if (
                    event.role in MEMBER_RANKS
                    and event.text == TOKENS["authorization_prompt"]
                    and event.sequence not in authorized_prompt_sequences
                ):
                    authorized_prompt_sequences.add(event.sequence)
                    board = BOARD_LABELS[event.role]
                    self.record(
                        "runner",
                        f"authorize board={board} controller=G mapping=preverified",
                    )
                    authorization_since = self.mark()
                    self.command(event.role, "a")
                    success = self.wait_token(
                        event.role,
                        TOKENS["authorization_success"],
                        min(10.0, max(0.1, deadline - time.monotonic())),
                        authorization_since,
                    )
                    authorization_success_sequences[event.role] = success.sequence
            time.sleep(0.005)
        raise HilFailure("두 member가 ready가 되기 전에 승인/검색 timeout이 발생했습니다.")

    def validate_rank_block(self, since: int, ready_sequence: int) -> list[int]:
        """! @brief ready 직전 검색 결과가 size 2의 rank 1·2인지 검사합니다. """
        ranks: list[int] = []
        for event in self.events[since:ready_sequence]:
            if event.role != "coordinator":
                continue
            match = RANK_PATTERN.fullmatch(event.text)
            if match is None:
                continue
            rank, set_size = (int(value) for value in match.groups())
            if set_size != 2:
                raise HilFailure(f"잘못된 set size 출력: {event.text}")
            ranks.append(rank)
        if set(ranks) != {1, 2}:
            raise HilFailure(f"rank 1·2 검색 근거 부족: ranks={ranks}")
        if set(ranks[-2:]) != {1, 2}:
            raise HilFailure(f"최종 member rank 집합 불일치: ranks={ranks[-2:]}")
        return ranks

    def expect_rejection(self, command: str, timeout: float) -> None:
        """! @brief 현재 상태에서 금지된 명령의 즉시 거부를 확인합니다. """
        since = self.mark()
        self.command("coordinator", command)
        self.wait_token(
            "coordinator", TOKENS["operation_rejected"], timeout, since
        )

    def ordered_lock_release(self, timeout: float) -> dict[str, Any]:
        """! @brief ordered access 뒤 두 member의 lock·release 전파를 확인합니다. """
        ordered_since = self.mark()
        self.command("coordinator", "o")
        self.assert_absent(
            "coordinator",
            (TOKENS["operation_rejected"],),
            min(3.0, timeout),
            ordered_since,
        )

        lock_since = self.mark()
        self.command("coordinator", "l")
        for role in ("member_one", "member_two"):
            self.wait_token(role, TOKENS["locked"], timeout, lock_since)
        self.assert_absent(
            "coordinator", (TOKENS["operation_rejected"],), 0.5, lock_since
        )
        self.expect_rejection("l", timeout)

        release_since = self.mark()
        self.command("coordinator", "u")
        for role in ("member_one", "member_two"):
            self.wait_token(role, TOKENS["released"], timeout, release_since)
        self.assert_absent(
            "coordinator", (TOKENS["operation_rejected"],), 0.5, release_since
        )
        self.expect_rejection("u", timeout)
        return {
            "ordered_access": "accepted_without_rejection_then_lock_succeeded",
            "locked_members": 2,
            "released_members": 2,
            "invalid_state_rejections": 2,
        }

    def recovery_lock_release(self, timeout: float) -> dict[str, int]:
        """! @brief 재가입 직후 두 member의 lock·release 전파만 확인합니다. """
        lock_since = self.mark()
        self.command("coordinator", "l")
        for role in ("member_one", "member_two"):
            self.wait_token(role, TOKENS["locked"], timeout, lock_since)

        release_since = self.mark()
        self.command("coordinator", "u")
        for role in ("member_one", "member_two"):
            self.wait_token(role, TOKENS["released"], timeout, release_since)
        return {"locked_members": 2, "released_members": 2}


def prepare_boot(
    campaign: Campaign,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """! @brief 선택된 경우 F/E/G 순서로 reset-and-go를 자동 수행합니다. """
    reset_boundaries: dict[str, int] = {}
    if not campaign.execute_reset:
        reset_boundaries = {role: campaign.mark() for role in ROLES}
        campaign.record("runner", "boot reset=skipped preexisting-uart-state=required")
        return [], reset_boundaries
    actions = []
    for role in ("member_one", "member_two", "coordinator"):
        actions.append(campaign.halt(role))
    for role in ("member_one", "member_two", "coordinator"):
        campaign.quarantine_pre_reset_uart(role)
        reset_boundaries[role] = len(campaign.events)
        actions.append(campaign.reset_and_go(role))
    return actions, reset_boundaries


def run_positive(campaign: Campaign, timeout: float) -> dict[str, Any]:
    """! @brief 2-member 검색·순위·접근·잠금·해제·상태 거부를 검증합니다. """
    reset_actions, reset_boundaries = prepare_boot(campaign)
    rank_since = campaign.boot_members(MEMBER_RANKS, timeout, reset_boundaries)
    campaign.wait_token(
        "coordinator",
        TOKENS["coordinator_search"],
        timeout,
        rank_since,
        allow_reset_noise=True,
    )
    ready = campaign.authorize_until_ready(timeout * 3.0, rank_since)
    ranks = campaign.validate_rank_block(rank_since, ready.sequence)
    campaign.expect_rejection("u", timeout)
    operations = campaign.ordered_lock_release(timeout)
    return {
        "boot_debug_actions": reset_actions,
        "discovered_members": 2,
        "reported_ranks": ranks,
        "rank_set": sorted(set(ranks)),
        "prelock_release_rejected": True,
        **operations,
    }


def run_recovery(
    campaign: Campaign,
    timeout: float,
    recovery_timeout: float,
    cycles: int,
) -> dict[str, Any]:
    """! @brief E member loss·재join 뒤 set 동작을 20회 반복합니다. """
    reset_actions, reset_boundaries = prepare_boot(campaign)
    rank_since = campaign.boot_members(MEMBER_RANKS, timeout, reset_boundaries)
    ready = campaign.authorize_until_ready(timeout * 3.0, rank_since)
    campaign.validate_rank_block(rank_since, ready.sequence)
    elapsed: list[float] = []
    recovery_actions: list[dict[str, Any]] = []
    for cycle in range(1, cycles + 1):
        cycle_started = time.monotonic()
        cycle_since = campaign.mark()
        restart = campaign.reset_and_go("member_two")
        ready = campaign.authorize_until_ready(
            min(recovery_timeout, campaign.remaining(f"recovery {cycle}")),
            cycle_since,
            ranks=MEMBER_RANKS,
            required_authorizations={"member_two"},
        )
        ranks = campaign.validate_rank_block(cycle_since, ready.sequence)
        operations = campaign.recovery_lock_release(timeout)
        raw_seconds = time.monotonic() - cycle_started
        seconds = round(raw_seconds, 3)
        if raw_seconds > recovery_timeout:
            raise HilFailure(
                f"recovery {cycle}가 {recovery_timeout:.1f}초 bound를 "
                f"초과했습니다: {seconds}s"
            )
        elapsed.append(seconds)
        recovery_actions.append({"cycle": cycle, "reset": restart})
        campaign.record(
            "runner",
            f"recovery cycle={cycle}/{cycles} ranks={sorted(set(ranks))} "
            f"seconds={seconds} operations={operations['released_members']}",
        )
    return {
        "boot_debug_actions": reset_actions,
        "requested_cycles": cycles,
        "completed_cycles": cycles,
        "loss_role": "member_two",
        "loss_board": "E",
        "loss_trigger": "hardware-reset",
        "recovery_seconds": elapsed,
        "recovery_timeout_seconds": recovery_timeout,
        "debug_actions": recovery_actions,
        "exact_handle_authorization_each_rejoin": True,
        "lock_release_each_cycle": True,
    }


def run_wrong_rank(campaign: Campaign, timeout: float) -> dict[str, Any]:
    """! @brief stock member 두 개를 rank 1로 시작해 duplicate rank를 거부합니다. """
    reset_actions, reset_boundaries = prepare_boot(campaign)
    wrong_ranks = {"member_one": 1, "member_two": 1}
    since = campaign.boot_members(wrong_ranks, timeout, reset_boundaries)
    deadline = time.monotonic() + campaign.bounded_timeout(
        timeout * 2.0, "duplicate rank 거부"
    )
    cursor = since
    authorized: set[str] = set()
    while time.monotonic() < deadline and len(authorized) < 2:
        campaign.ensure_time("duplicate rank 거부")
        campaign.pump()
        while cursor < len(campaign.events):
            event = campaign.events[cursor]
            cursor += 1
            if event.role == "coordinator" and event.text == TOKENS["coordinator_ready"]:
                raise HilFailure("duplicate rank 구성이 ready로 잘못 수락됐습니다.")
            if event.role in MEMBER_RANKS and event.text == TOKENS["authorization_prompt"]:
                campaign.record(
                    "runner",
                    f"authorize board={BOARD_LABELS[event.role]} "
                    "controller=G mapping=preverified duplicate-rank=true",
                )
                authorization_since = campaign.mark()
                campaign.command(event.role, "a")
                campaign.wait_token(
                    event.role,
                    TOKENS["authorization_success"],
                    timeout,
                    authorization_since,
                )
                authorized.add(event.role)
        time.sleep(0.005)
    if len(authorized) != 2:
        raise HilFailure("duplicate rank 검사에서 두 연결 승인 근거가 부족합니다.")
    campaign.assert_absent(
        "coordinator",
        (TOKENS["coordinator_ready"], TOKENS["member_rank_two"]),
        min(timeout, 15.0),
        since,
    )
    campaign.expect_rejection("o", timeout)
    return {
        "boot_debug_actions": reset_actions,
        "configured_ranks": [1, 1],
        "authorized_connections": 2,
        "ready_observed": False,
        "rank_two_observed": False,
        "operation_rejected": True,
    }


def run_wrong_sirk(campaign: Campaign, timeout: float) -> dict[str, Any]:
    """! @brief 외부에서 준비한 wrong-SIRK E image가 set에 합류하지 못함을 확인합니다. """
    reset_actions, reset_boundaries = prepare_boot(campaign)
    since = campaign.boot_members(MEMBER_RANKS, timeout, reset_boundaries)
    authorization = campaign.wait_token(
        "member_one", TOKENS["authorization_prompt"], timeout, since
    )
    campaign.record(
        "runner",
        "authorize board=F controller=G mapping=preverified wrong-sirk-case=true",
    )
    authorization_since = campaign.mark()
    campaign.command("member_one", "a")
    campaign.wait_token(
        "member_one",
        TOKENS["authorization_success"],
        timeout,
        authorization_since,
    )
    campaign.wait_token(
        "coordinator", TOKENS["member_rank_one"], timeout, since
    )
    campaign.assert_absent(
        "member_two",
        (TOKENS["authorization_prompt"], TOKENS["authorization_success"]),
        min(timeout, 20.0),
        since,
    )
    campaign.assert_absent(
        "coordinator",
        (TOKENS["member_rank_two"], TOKENS["coordinator_ready"]),
        min(timeout, 20.0),
        since,
    )
    campaign.expect_rejection("o", timeout)
    return {
        "boot_debug_actions": reset_actions,
        "normal_member_discovered": True,
        "authorized_connections": 1,
        "wrong_sirk_member_ready_locally": True,
        "wrong_sirk_member_connected": False,
        "wrong_sirk_member_joined": False,
        "set_ready_observed": False,
        "operation_rejected": True,
    }


def run_failure_log(
    campaign: Campaign,
    timeout: float,
    mode: str,
) -> dict[str, Any]:
    """! @brief 외부 fault image가 만든 exact 보안·watchdog 로그를 검증합니다. """
    token_name = {
        "security-sync-failure": "security_sync_failure",
        "security-async-failure": "security_async_failure",
        "watchdog": "watchdog",
    }[mode]
    reset_actions, reset_boundaries = prepare_boot(campaign)
    since = campaign.boot_members(MEMBER_RANKS, timeout, reset_boundaries)
    event = campaign.wait_token(
        "coordinator", TOKENS[token_name], timeout * 3.0, since
    )
    forbidden = [TOKENS["coordinator_ready"]]
    if mode == "security-async-failure":
        forbidden.append(TOKENS["security_sync_failure"])
    campaign.assert_absent(
        "coordinator",
        tuple(forbidden),
        2.0,
        since,
    )
    result = {
        "boot_debug_actions": reset_actions,
        "expected_log": TOKENS[token_name],
        "observed": True,
        "at_s": event.at_s,
        "ready_after_fault": False,
    }
    if mode == "security-async-failure":
        result["synchronous_request_failed"] = False
    return result


def parse_arguments(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    """! @brief 공개 예제 HIL의 role·artifact·scenario 인자를 정의합니다. """
    parser = argparse.ArgumentParser(
        description=(
            "G coordinator, F/E rank 1/2 member용 CSIP HIL입니다. "
            "flash는 수행하지 않으며 reset/halt/go는 명시 옵션으로만 수행합니다."
        )
    )
    parser.add_argument(
        "mode",
        choices=(
            "positive",
            "recovery",
            "wrong-rank",
            "wrong-sirk",
            "security-sync-failure",
            "security-async-failure",
            "watchdog",
        ),
    )
    for role in ROLES:
        option = role.replace("_", "-")
        parser.add_argument(f"--{option}-port", required=True)
        parser.add_argument(f"--{option}-probe-sha256", required=True)
        parser.add_argument(f"--{option}-image", type=Path, required=True)
        parser.add_argument(f"--{option}-image-sha256", required=True)
    parser.add_argument("--core-root", type=Path, required=True)
    parser.add_argument("--core-revision", required=True)
    parser.add_argument("--coordinator-example-sha256", required=True)
    parser.add_argument("--member-example-sha256", required=True)
    parser.add_argument("--fault-role", choices=ROLES)
    parser.add_argument("--fault-image-sha256")
    parser.add_argument("--fault-manifest", type=Path)
    parser.add_argument("--cycles", type=int, default=20)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--total-timeout", type=float, default=TOTAL_TIMEOUT_SECONDS)
    parser.add_argument(
        "--recovery-timeout", type=float, default=RECOVERY_TIMEOUT_SECONDS
    )
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--transcript", type=Path)
    parser.add_argument("--execute-reset", action="store_true")
    parser.add_argument(
        "--reset-helper",
        type=Path,
        default=Path(__file__).with_name("pyocd_commands_by_hash.py"),
    )
    parser.add_argument("--reset-timeout", type=float, default=30.0)
    return parser.parse_args(arguments)


def validate_arguments(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    """! @brief probe·COM·image·fault 근거를 fail-closed 검사합니다. """
    if REVISION_PATTERN.fullmatch(args.core_revision) is None:
        parser.error("core revision은 40자리 소문자 commit hex여야 합니다.")
    if args.cycles != 20:
        parser.error("M31 recovery denominator는 정확히 20회여야 합니다.")
    if not 5.0 <= args.timeout <= RECOVERY_TIMEOUT_SECONDS:
        parser.error("operation timeout은 5..30초여야 합니다.")
    if not 1.0 <= args.total_timeout <= TOTAL_TIMEOUT_SECONDS:
        parser.error("전체 timeout은 최대 180초여야 합니다.")
    if not 1.0 <= args.recovery_timeout <= RECOVERY_TIMEOUT_SECONDS:
        parser.error("recovery timeout은 최대 30초여야 합니다.")
    if args.baud != 115200:
        parser.error("공개 예제 기준 baud는 115200입니다.")
    minimum_reset_timeout = (
        DEBUG_HELPER_INTERNAL_TIMEOUT_SECONDS
        + DEBUG_HELPER_CLEANUP_MARGIN_SECONDS
    )
    if not minimum_reset_timeout < args.reset_timeout <= RECOVERY_TIMEOUT_SECONDS:
        parser.error("reset outer timeout은 helper 20초+정리 여유보다 크고 30초 이하여야 합니다.")
    expected_examples = {
        "coordinator": args.coordinator_example_sha256,
        "member": args.member_example_sha256,
    }
    if any(
        HASH_PATTERN.fullmatch(value) is None
        for value in expected_examples.values()
    ):
        parser.error("공개 예제 SHA-256은 64자리 소문자 hex여야 합니다.")
    ports = {
        role: getattr(args, f"{role}_port") for role in ROLES
    }
    if len({port.casefold() for port in ports.values()}) != len(ROLES):
        parser.error("G/F/E COM port는 서로 달라야 합니다.")
    probe_hashes = {
        role: getattr(args, f"{role}_probe_sha256") for role in ROLES
    }
    if any(HASH_PATTERN.fullmatch(value) is None for value in probe_hashes.values()):
        parser.error("probe SHA-256은 64자리 소문자 hex여야 합니다.")
    if len(set(probe_hashes.values())) != len(ROLES):
        parser.error("G/F/E probe SHA-256은 서로 달라야 합니다.")
    for role in ROLES:
        expected = EXPECTED_BOARD_MAP[role]
        if ports[role].casefold() != expected["port"].casefold():
            parser.error(
                f"{role}/{expected['board']} COM 매핑은 "
                f"{expected['port']}여야 합니다."
            )
        if probe_hashes[role] != expected["probe_sha256"]:
            parser.error(
                f"{role}/{expected['board']} probe SHA-256 매핑이 다릅니다."
            )
    images = {role: getattr(args, f"{role}_image").resolve() for role in ROLES}
    image_hashes: dict[str, str] = {}
    for role, path in images.items():
        if not path.is_file():
            parser.error(f"{role} image가 없습니다: {path}")
        expected_hash = getattr(args, f"{role}_image_sha256")
        if HASH_PATTERN.fullmatch(expected_hash) is None:
            parser.error(f"{role} image SHA-256 형식이 잘못되었습니다.")
        actual_hash = sha256_file(path)
        if actual_hash != expected_hash:
            parser.error(
                f"{role} image hash 불일치: "
                f"expected={expected_hash}, actual={actual_hash}"
            )
        image_hashes[role] = actual_hash
    reviewed_helper = Path(__file__).with_name("pyocd_commands_by_hash.py").resolve()
    if args.reset_helper.resolve() != reviewed_helper or not reviewed_helper.is_file():
        parser.error("reviewed sibling SHA-256 debug helper만 허용합니다.")
    if sha256_file(reviewed_helper) != EXPECTED_DEBUG_HELPER_SHA256:
        parser.error("reviewed debug helper hash가 변경되었습니다.")
    if not args.execute_reset:
        parser.error("실제 HIL에는 live probe 확인과 자동 reset을 활성화해야 합니다.")
    fault_modes = set(FAULT_MUTATIONS)
    if args.mode in fault_modes:
        expected_fault_role = (
            "member_two" if args.mode == "wrong-sirk" else "coordinator"
        )
        if args.fault_role != expected_fault_role:
            parser.error(
                f"{args.mode} fault role은 {expected_fault_role}여야 합니다."
            )
        if args.fault_image_sha256 is None or HASH_PATTERN.fullmatch(
            args.fault_image_sha256
        ) is None:
            parser.error("fault mode에는 --fault-image-sha256 근거가 필요합니다.")
        if args.fault_image_sha256 != image_hashes[args.fault_role]:
            parser.error("fault SHA-256이 지정한 fault role image와 일치해야 합니다.")
        if args.fault_manifest is None or not args.fault_manifest.resolve().is_file():
            parser.error("fault mode에는 mode별 build manifest가 필요합니다.")
        if args.mode == "wrong-sirk":
            if args.fault_image_sha256 != image_hashes["member_two"]:
                parser.error("wrong-sirk fault image는 E/member-two image여야 합니다.")
            if image_hashes["member_two"] == image_hashes["member_one"]:
                parser.error("wrong-sirk E image는 정상 F image와 달라야 합니다.")
    elif (
        args.fault_image_sha256 is not None
        or args.fault_role is not None
        or args.fault_manifest is not None
    ):
        parser.error("이 mode에서는 fault role/image/manifest 인자를 허용하지 않습니다.")
    evidence = args.evidence.resolve()
    if evidence.exists():
        parser.error("기존 evidence를 덮어쓰지 않습니다.")
    transcript = (
        args.transcript.resolve()
        if args.transcript is not None
        else evidence.with_suffix(".transcript.log")
    )
    if transcript.exists():
        parser.error("기존 transcript를 덮어쓰지 않습니다.")
    if transcript == evidence:
        parser.error("evidence와 transcript 경로는 달라야 합니다.")


def run_fixture_tests() -> int:
    """! @brief hardware·serial 없이 identity와 no-overwrite 계약을 시험합니다. """
    raw = "peer=AA:BB:CC:DD:EE:FF uid=0123456789abcdef0123456789abcdef"
    sanitized = sanitize_line(raw)
    if "AA:BB" in sanitized or "0123456789abcdef" in sanitized:
        raise HilFailure("fixture identifier 정제 실패")
    if REVISION_PATTERN.fullmatch("a" * 40) is None:
        raise HilFailure("fixture revision 형식 실패")
    if HASH_PATTERN.fullmatch("b" * 64) is None:
        raise HilFailure("fixture SHA-256 형식 실패")
    invocation = debug_helper_invocation(
        Path("helper.py"), "c" * 64, ("reset", "go")
    )
    if invocation[-4:] != ("reset", "go", "--connect", "halt"):
        raise HilFailure("fixture helper 명령 구성 실패")
    if any("unique" in value.casefold() or "uid" in value.casefold() for value in invocation):
        raise HilFailure("fixture helper 명령에 원시 UID 개념이 포함됐습니다.")
    if EXPECTED_BOARD_MAP["coordinator"]["port"] != "COM10":
        raise HilFailure("fixture G COM 매핑 실패")
    if EXPECTED_BOARD_MAP["member_one"]["port"] != "COM14":
        raise HilFailure("fixture F COM 매핑 실패")
    if EXPECTED_BOARD_MAP["member_two"]["port"] != "COM13":
        raise HilFailure("fixture E COM 매핑 실패")
    mapped_hashes = {
        value["probe_sha256"] for value in EXPECTED_BOARD_MAP.values()
    }
    if len(mapped_hashes) != 3 or any(
        HASH_PATTERN.fullmatch(value) is None for value in mapped_hashes
    ):
        raise HilFailure("fixture probe SHA-256 매핑 실패")
    if TOTAL_TIMEOUT_SECONDS != 180.0 or RECOVERY_TIMEOUT_SECONDS != 30.0:
        raise HilFailure("fixture readiness 시간 계약 실패")
    dynamic_outer = compute_debug_outer_timeout(30.0, 25.0)
    if dynamic_outer != 24.0:
        raise HilFailure("fixture dynamic debug outer timeout 계산 실패")
    try:
        compute_debug_outer_timeout(30.0, 22.0)
    except HilFailure:
        pass
    else:
        raise HilFailure("fixture deadline 인접 debug launch 거부 실패")
    markers = {value[2] for value in FAULT_MUTATIONS.values()}
    if len(markers) != len(FAULT_MUTATIONS):
        raise HilFailure("fixture fault marker 고유성 실패")
    if DEBUG_FAILURE_PATTERN.search("Error probing AP#4: No ACK") is None:
        raise HilFailure("fixture debug helper 오류 판정 실패")
    late_output = ("clean output\n" * 100) + "Error probing AP#4: No ACK"
    evidence_output, late_failure = inspect_debug_output(late_output)
    if not late_failure or len(evidence_output) > DEBUG_EVIDENCE_LIMIT:
        raise HilFailure("fixture debug helper 후반 오류 판정 실패")
    reset_token = TOKENS["coordinator_search"]
    if not matches_token_after_reset_noise(r"\x86\x90\xde" + reset_token, reset_token):
        raise HilFailure("fixture 관측 reset UART noise token 검사 실패")
    if not matches_token_after_reset_noise("?" + r"\xfe\xfc\xdf" + reset_token, reset_token):
        raise HilFailure("fixture 4-byte reset UART noise token 검사 실패")
    if not matches_token_after_reset_noise("\x03" + reset_token, reset_token):
        raise HilFailure("fixture control-byte reset UART noise token 검사 실패")
    long_reset_noise = (r"\xfcL\xbb" * 20) + reset_token
    if not matches_token_after_reset_noise(long_reset_noise, reset_token):
        raise HilFailure("fixture bounded long reset UART noise token 검사 실패")
    normalized_reset_noise = normalize_reset_noise_line(
        (r"\xfcL" * 500) + reset_token
    )
    if (
        not matches_token_after_reset_noise(normalized_reset_noise, reset_token)
        or not normalized_reset_noise.startswith("<reset-uart-noise chars=")
    ):
        raise HilFailure("fixture overlong reset UART noise 정규화 실패")
    if matches_token_after_reset_noise(r"\x41" + reset_token, reset_token):
        raise HilFailure("fixture escaped ASCII token prefix 거부 실패")
    if matches_token_after_reset_noise("ABCDE" + reset_token, reset_token):
        raise HilFailure("fixture ASCII reset prefix 거부 실패")
    overlong_reset_noise = (
        r"\x80" + ("A" * RESET_NOISE_PREFIX_LIMIT) + reset_token
    )
    if matches_token_after_reset_noise(overlong_reset_noise, reset_token):
        raise HilFailure("fixture overlong reset prefix 거부 실패")

    class FixtureStream:
        """! @brief UART quiet 경계를 시험하는 메모리 stream입니다. """

        def __init__(self, payload: bytes, continuous: bool = False) -> None:
            self.payload = bytearray(payload)
            self.continuous = continuous

        @property
        def in_waiting(self) -> int:
            """! @brief 즉시 읽을 수 있는 fixture byte 수를 반환합니다. """
            return len(self.payload) or (1 if self.continuous else 0)

        def read(self, size: int) -> bytes:
            """! @brief 저장 byte 또는 continuous fixture byte를 반환합니다. """
            if self.payload:
                count = min(size, len(self.payload))
                data = bytes(self.payload[:count])
                del self.payload[:count]
                return data
            return b"x" if self.continuous else b""

    fixture_campaign = Campaign(
        None,
        {role: role for role in ROLES},
        {role: EXPECTED_BOARD_MAP[role]["probe_sha256"] for role in ROLES},
        115200,
        Path("fixture.log"),
        False,
        Path("helper.py"),
        5.0,
        3.0,
    )
    fixture_campaign.streams = {
        "coordinator": FixtureStream(b"old-line\n"),
        "member_one": FixtureStream(b""),
        "member_two": FixtureStream(b""),
    }
    fixture_campaign.transcript = io.StringIO()
    if fixture_campaign.mark() != 1:
        raise HilFailure("fixture complete-line quiet 경계 실패")

    noisy_payload = b"\x86\x90\xdeSearching for two set members\n"
    noisy_exact_campaign = Campaign(
        None,
        {role: role for role in ROLES},
        {role: EXPECTED_BOARD_MAP[role]["probe_sha256"] for role in ROLES},
        115200,
        Path("fixture.log"),
        False,
        Path("helper.py"),
        5.0,
        3.0,
    )
    noisy_exact_campaign.streams = {
        "coordinator": FixtureStream(noisy_payload),
        "member_one": FixtureStream(b""),
        "member_two": FixtureStream(b""),
    }
    noisy_exact_campaign.transcript = io.StringIO()
    try:
        noisy_exact_campaign.wait_token(
            "coordinator", reset_token, 0.020, 0
        )
    except HilFailure:
        pass
    else:
        raise HilFailure("fixture non-reset token noise 거부 실패")

    noisy_reset_campaign = Campaign(
        None,
        {role: role for role in ROLES},
        {role: EXPECTED_BOARD_MAP[role]["probe_sha256"] for role in ROLES},
        115200,
        Path("fixture.log"),
        False,
        Path("helper.py"),
        5.0,
        3.0,
    )
    noisy_reset_campaign.streams = {
        "coordinator": FixtureStream(noisy_payload),
        "member_one": FixtureStream(b""),
        "member_two": FixtureStream(b""),
    }
    noisy_reset_campaign.transcript = io.StringIO()
    noisy_reset_campaign.wait_token(
        "coordinator",
        reset_token,
        0.020,
        0,
        allow_reset_noise=True,
    )

    fatal_noise_campaign = Campaign(
        None,
        {role: role for role in ROLES},
        {role: EXPECTED_BOARD_MAP[role]["probe_sha256"] for role in ROLES},
        115200,
        Path("fixture.log"),
        False,
        Path("helper.py"),
        5.0,
        3.0,
    )
    fatal_noise_campaign.streams = {
        "coordinator": FixtureStream(
            b"FATAL ERROR\x80Searching for two set members\n"
        ),
        "member_one": FixtureStream(b""),
        "member_two": FixtureStream(b""),
    }
    fatal_noise_campaign.transcript = io.StringIO()
    try:
        fatal_noise_campaign.pump()
    except HilFailure:
        pass
    else:
        raise HilFailure("fixture fatal reset noise 우선 검출 실패")

    reverse_rank_campaign = Campaign(
        None,
        {role: role for role in ROLES},
        {role: EXPECTED_BOARD_MAP[role]["probe_sha256"] for role in ROLES},
        115200,
        Path("fixture.log"),
        False,
        Path("helper.py"),
        5.0,
        3.0,
    )
    reverse_rank_campaign.events = [
        Event(0, 0.0, "coordinator", "Member rank 2 of 2"),
        Event(1, 0.1, "coordinator", "Member rank 1 of 2"),
    ]
    if reverse_rank_campaign.validate_rank_block(0, 2) != [2, 1]:
        raise HilFailure("fixture reverse discovery rank 집합 실패")
    duplicate_rank_campaign = Campaign(
        None,
        {role: role for role in ROLES},
        {role: EXPECTED_BOARD_MAP[role]["probe_sha256"] for role in ROLES},
        115200,
        Path("fixture.log"),
        False,
        Path("helper.py"),
        5.0,
        3.0,
    )
    duplicate_rank_campaign.events = [
        Event(0, 0.0, "coordinator", "Member rank 1 of 2"),
        Event(1, 0.1, "coordinator", "Member rank 1 of 2"),
    ]
    try:
        duplicate_rank_campaign.validate_rank_block(0, 2)
    except HilFailure:
        pass
    else:
        raise HilFailure("fixture duplicate rank 집합 거부 실패")

    partial_campaign = Campaign(
        None,
        {role: role for role in ROLES},
        {role: EXPECTED_BOARD_MAP[role]["probe_sha256"] for role in ROLES},
        115200,
        Path("fixture.log"),
        False,
        Path("helper.py"),
        5.0,
        3.0,
    )
    partial_campaign.streams = {
        "coordinator": FixtureStream(b"partial"),
        "member_one": FixtureStream(b""),
        "member_two": FixtureStream(b""),
    }
    partial_campaign.transcript = io.StringIO()
    try:
        partial_campaign.mark()
    except HilFailure:
        pass
    else:
        raise HilFailure("fixture partial-byte quiet fail-closed 실패")

    quarantine_campaign = Campaign(
        None,
        {role: role for role in ROLES},
        {role: EXPECTED_BOARD_MAP[role]["probe_sha256"] for role in ROLES},
        115200,
        Path("fixture.log"),
        False,
        Path("helper.py"),
        5.0,
        3.0,
    )
    quarantine_campaign.streams = {
        "coordinator": FixtureStream(b"partial"),
        "member_one": FixtureStream(b""),
        "member_two": FixtureStream(b""),
    }
    quarantine_campaign.transcript = io.StringIO()
    quarantined = quarantine_campaign.quarantine_pre_reset_uart("coordinator")
    zero_quarantined = quarantine_campaign.quarantine_pre_reset_uart("member_one")
    if (
        quarantined != 7
        or zero_quarantined != 0
        or quarantine_campaign.pre_reset_uart_quarantine
        != {
            "coordinator": {
                "observed_bytes": 7,
                "input_buffer_purged": False,
            },
            "member_one": {
                "observed_bytes": 0,
                "input_buffer_purged": False,
            },
        }
        or any(quarantine_campaign.pending.values())
    ):
        raise HilFailure("fixture reset 전 partial 격리 실패")

    continuous_campaign = Campaign(
        None,
        {role: role for role in ROLES},
        {role: EXPECTED_BOARD_MAP[role]["probe_sha256"] for role in ROLES},
        115200,
        Path("fixture.log"),
        False,
        Path("helper.py"),
        5.0,
        3.0,
    )
    continuous_campaign.streams = {
        "coordinator": FixtureStream(b"", continuous=True),
        "member_one": FixtureStream(b""),
        "member_two": FixtureStream(b""),
    }
    continuous_campaign.transcript = io.StringIO()
    try:
        continuous_campaign.mark()
    except HilFailure:
        pass
    else:
        raise HilFailure("fixture continuous-byte quiet fail-closed 실패")

    with tempfile.TemporaryDirectory(prefix="csip-hil-") as directory:
        temporary_root = Path(directory)
        source_directory = temporary_root / "source"
        build_path = temporary_root / "build"
        source_directory.mkdir()
        build_path.mkdir()
        command = [
            str(ARDUINO_CLI_PATH),
            "compile",
            "--config-file",
            str(ARDUINO_CONFIG_PATH),
            "--fqbn",
            ARDUINO_FQBN,
            "--clean",
            "--build-path",
            str(build_path),
            str(source_directory),
        ]
        verify_build_command(command, source_directory, build_path, "fixture")
        duplicate_command = command[:-1] + ["--fqbn", ARDUINO_FQBN, command[-1]]
        try:
            verify_build_command(
                duplicate_command, source_directory, build_path, "fixture duplicate"
            )
        except HilFailure:
            pass
        else:
            raise HilFailure("fixture duplicate build option 거부 실패")

        path = temporary_root / "evidence.json"
        with path.open("x", encoding="utf-8") as stream:
            json.dump({"status": "fixture"}, stream)
        try:
            path.open("x", encoding="utf-8")
        except FileExistsError:
            pass
        else:
            raise HilFailure("fixture no-overwrite 실패")
    print("M31_CSIP_HIL_SELF_TEST=PASS;FIXTURES=28;HARDWARE=UNTOUCHED")
    return 0


def main(arguments: Sequence[str] | None = None) -> int:
    """! @brief 선택한 scenario를 수행하고 해시 기반 증적을 기록합니다. """
    selected_arguments = list(sys.argv[1:] if arguments is None else arguments)
    if selected_arguments == ["self-test"]:
        return run_fixture_tests()
    args = parse_arguments(arguments)
    validation_parser = argparse.ArgumentParser(add_help=False)
    try:
        validate_arguments(args, validation_parser)
    except SystemExit:
        raise
    core_root = args.core_root.resolve()
    source_hashes = verify_source(core_root, args.core_revision)
    expected_source_hashes = {
        "coordinator": args.coordinator_example_sha256,
        "member": args.member_example_sha256,
    }
    if source_hashes != expected_source_hashes:
        raise HilFailure(
            "공개 예제 hash 불일치: "
            f"expected={expected_source_hashes}, actual={source_hashes}"
        )
    try:
        import serial
    except ImportError as error:
        raise HilFailure("pyserial이 필요합니다.") from error

    ports = {role: getattr(args, f"{role}_port") for role in ROLES}
    probe_hashes = {
        role: getattr(args, f"{role}_probe_sha256") for role in ROLES
    }
    images = {role: getattr(args, f"{role}_image").resolve() for role in ROLES}
    image_hashes = {role: sha256_file(path) for role, path in images.items()}
    reset_helper = args.reset_helper.resolve()
    reset_helper_hash = sha256_file(reset_helper)
    fault_manifest = verify_fault_manifest(
        args, core_root, source_hashes, images, image_hashes
    )
    evidence_path = args.evidence.resolve()
    transcript_path = (
        args.transcript.resolve()
        if args.transcript is not None
        else evidence_path.with_suffix(".transcript.log")
    )
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    started_at = utc_now()
    result: dict[str, Any] = {}
    pre_reset_uart: dict[str, dict[str, Any]] = {}
    status = "FAIL"
    error_text: str | None = None
    campaign: Campaign | None = None
    try:
        with Campaign(
            serial,
            ports,
            probe_hashes,
            args.baud,
            transcript_path,
            args.execute_reset,
            reset_helper,
            args.reset_timeout,
            args.total_timeout,
        ) as active:
            campaign = active
            if args.mode == "positive":
                result = run_positive(active, args.timeout)
            elif args.mode == "recovery":
                result = run_recovery(
                    active,
                    args.timeout,
                    args.recovery_timeout,
                    args.cycles,
                )
            elif args.mode == "wrong-rank":
                result = run_wrong_rank(active, args.timeout)
            elif args.mode == "wrong-sirk":
                result = run_wrong_sirk(active, args.timeout)
            else:
                result = run_failure_log(active, args.timeout, args.mode)
            final_source_hashes = verify_source(core_root, args.core_revision)
            if final_source_hashes != source_hashes:
                raise HilFailure("campaign 중 공개 예제 source hash가 변경되었습니다.")
            final_image_hashes = {
                role: sha256_file(path) for role, path in images.items()
            }
            if final_image_hashes != image_hashes:
                raise HilFailure("campaign 중 role image hash가 변경되었습니다.")
            if sha256_file(reset_helper) != reset_helper_hash:
                raise HilFailure("campaign 중 reviewed debug helper가 변경되었습니다.")
            active.ensure_time("campaign 종료 검증")
            result["campaign_elapsed_seconds"] = round(
                time.monotonic() - active.started, 3
            )
            status = "PASS"
    except Exception as error:
        error_text = str(error)

    if campaign is not None:
        pre_reset_uart = dict(campaign.pre_reset_uart_quarantine)

    try:
        source_clean = verify_source(core_root, args.core_revision) == source_hashes
    except Exception:
        source_clean = False

    events = [] if campaign is None else [asdict(event) for event in campaign.events]
    document = {
        "schema": "nucode.m31.csip-hil.v1",
        "status": status,
        "mode": args.mode,
        "started_at": started_at,
        "finished_at": utc_now(),
        "core_revision": args.core_revision,
        "source_clean": source_clean,
        "pre_reset_uart_quarantine": pre_reset_uart,
        "public_example_sha256": source_hashes,
        "runner_behavior": {
            "flashes_devices": False,
            "power_cycles_devices": False,
            "interactive_input": False,
            "debug_control_enabled": args.execute_reset,
            "debug_control": "SHA-256 helper reset/halt/go",
            "debug_helper_path": str(reset_helper),
            "debug_helper_sha256": reset_helper_hash,
            "opens_only_explicit_com_ports": True,
            "raw_probe_identifiers_recorded": False,
            "existing_files_overwritten": False,
        },
        "board_map": {
            role: {
                "board": BOARD_LABELS[role],
                "port": ports[role],
                "probe_sha256": probe_hashes[role],
                "image_path": str(images[role]),
                "image_sha256": image_hashes[role],
            }
            for role in ROLES
        },
        "fault_image_sha256": args.fault_image_sha256,
        "fault_role": args.fault_role,
        "fault_build_manifest": fault_manifest,
        "time_contract": {
            "campaign_timeout_seconds": args.total_timeout,
            "recovery_timeout_seconds": args.recovery_timeout,
        },
        "expected_tokens": TOKENS,
        "result": result,
        "events": events,
        "error": error_text,
    }
    try:
        with evidence_path.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(document, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    except FileExistsError as error:
        raise HilFailure("종료 시 evidence가 생겨 덮어쓰지 않았습니다.") from error
    print(
        f"M31_CSIP_{args.mode.upper().replace('-', '_')}={status};"
        f"EVENTS={len(events)};EVIDENCE={evidence_path}"
    )
    if status != "PASS":
        print(error_text, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
