#!/usr/bin/env python3
"""! @brief ANCS/AMS 합성 peer image build 및 사전 검증된 두 보드의 유한 HIL입니다. """
from __future__ import annotations

import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
APPLICATION = ROOT / "tests/zephyr/m33_ecosystem_hil"
BOARD = "nrf54l15dk/nrf54l15/cpuapp/nu54dk"
ROLES = ("client", "peer")
CASES = ("access_denied", "ancs", "ams", "ancs_bad", "ams_bad")
POSITIVE_RECONNECT_CYCLES = 20
MALFORMED_CYCLES = 2
LOCK = json.loads((ROOT / "tools/ci/ncs-3.4.0.lock.json").read_text(encoding="utf-8"))
FIELDS = {
    "role", "nonce", "case", "revision", "identity", "packets", "attributes", "writes",
    "negative", "links", "security", "pairings", "bonded", "reconnects",
    "security_rejects", "test_bond",
}
COUNTERS = {
    ("access_denied", "client"): (0, 0, 0, 1),
    ("access_denied", "peer"): (0, 0, 0, 1),
    ("ancs", "client"): (1, 1, 2, 1), ("ancs", "peer"): (1, 1, 2, 0),
    ("ams", "client"): (1, 1, 2, 1), ("ams", "peer"): (1, 0, 3, 0),
    ("ancs_bad", "client"): (0, 0, 0, 2), ("ancs_bad", "peer"): (1, 0, 0, 1),
    ("ams_bad", "client"): (0, 0, 1, 2), ("ams_bad", "peer"): (1, 0, 1, 1),
}


def regression_schedule() -> list[tuple[int, str, str]]:
    """! @brief ANCS·AMS를 각각 20회 반복하고 malformed 회귀를 분리합니다. """
    schedule: list[tuple[int, str, str]] = []
    for cycle in range(1, POSITIVE_RECONNECT_CYCLES + 1):
        schedule.append((cycle, "ancs", "fresh" if cycle == 1 else "reconnect"))
        schedule.append((cycle, "ams", "reconnect"))
        if cycle <= MALFORMED_CYCLES:
            schedule.append((cycle, "ancs_bad", "reconnect"))
            schedule.append((cycle, "ams_bad", "reconnect"))
    return schedule


def validate_case_denominators(cases: list[dict]) -> dict[str, int]:
    """! @brief 실행된 case가 고정 회수와 중복 없는 cycle을 만족하는지 검사합니다. """
    expected = {
        "access_denied": 1,
        "ancs": POSITIVE_RECONNECT_CYCLES,
        "ams": POSITIVE_RECONNECT_CYCLES,
        "ancs_bad": MALFORMED_CYCLES,
        "ams_bad": MALFORMED_CYCLES,
    }
    observed = {case: 0 for case in expected}
    cycles = {case: set() for case in expected}
    for entry in cases:
        case = entry.get("case")
        cycle = entry.get("cycle")
        if case not in observed or not isinstance(cycle, int) or entry.get("status") != "PASS":
            raise ValueError("invalid regression case evidence")
        if cycle in cycles[case]:
            raise ValueError("duplicate regression case cycle")
        cycles[case].add(cycle)
        observed[case] += 1
    if observed != expected:
        raise ValueError("ANCS/AMS regression denominator mismatch")
    if cycles["access_denied"] != {0}:
        raise ValueError("access-denied cycle mismatch")
    positive_cycles = set(range(1, POSITIVE_RECONNECT_CYCLES + 1))
    malformed_cycles = set(range(1, MALFORMED_CYCLES + 1))
    if cycles["ancs"] != positive_cycles or cycles["ams"] != positive_cycles:
        raise ValueError("ANCS/AMS cycle sequence mismatch")
    if cycles["ancs_bad"] != malformed_cycles or cycles["ams_bad"] != malformed_cycles:
        raise ValueError("malformed cycle sequence mismatch")
    return observed


def digest(path: Path) -> str:
    """! @brief 파일 byte의 SHA-256을 계산합니다. """
    return hashlib.sha256(path.read_bytes()).hexdigest()


def revision(path: Path) -> str:
    """! @brief 지정된 checkout의 실제 revision을 조회합니다. """
    return subprocess.check_output(
        ["git", "-C", str(path), "rev-parse", "HEAD"], text=True,
        timeout=30,
    ).strip()


def source_clean(path: Path) -> bool:
    """! @brief build 시점 checkout에 추적·미추적 변경이 없는지 확인합니다. """

    return not subprocess.check_output(
        ["git", "-C", str(path), "status", "--porcelain", "--untracked-files=all"],
        text=True,
        timeout=30,
    ).strip()


def validate_locked_sources(sdk: Path) -> dict[str, str]:
    """! @brief NCS 3.4.0·Zephyr·board checkout의 revision과 clean 상태를 함께 고정합니다. """

    paths = {
        "ncs": sdk / "nrf",
        "zephyr": sdk / "zephyr",
        "board": ROOT / "board_package/NU54DK_Zephyr_DTS",
    }
    revisions = {name: revision(path) for name, path in paths.items()}
    if any(revisions[name] != LOCK[name]["revision"] for name in paths):
        raise ValueError("fixed NCS 3.4.0 / Zephyr / board revision mismatch")
    if any(not source_clean(path) for path in paths.values()):
        raise ValueError("NCS 3.4.0 / Zephyr / board checkout must be clean")
    return revisions


def source_identity() -> str:
    """! @brief CMake와 동일한 source 목록을 hash하여 dirty 개발 image도 구분합니다. """
    files = [p for p in APPLICATION.rglob("*") if p.is_file() and
             (p.suffix in (".cpp", ".conf", ".overlay") or p.name == "CMakeLists.txt")]
    for library in ("NUCODE_BLE", "NUCODE_BLE_Companion", "NUCODE_BLE_Security"):
        files.extend(p for p in (ROOT / "libraries" / library / "src").rglob("*")
                     if p.is_file() and p.suffix in (".c", ".cpp", ".h"))
    text = "".join(f"{p.relative_to(ROOT).as_posix()}:{digest(p)}\n"
                   for p in sorted(files, key=lambda p: p.relative_to(ROOT).as_posix()))
    return revision(ROOT) + hashlib.sha256(text.encode()).hexdigest()


def build(args: argparse.Namespace) -> None:
    """! @brief 고정 SDK·board identity에서 image를 build하며 flash를 하지 않습니다. """
    locked = validate_locked_sources(args.sdk)
    if args.toolchain.name != LOCK["windows_toolchain"]["bundle_id"]:
        raise ValueError("fixed toolchain required")
    if args.output.exists():
        previous = args.output / "build-manifest.json"
        if not args.retry or not previous.is_file() or json.loads(previous.read_text(encoding="utf-8"))["role"] != args.role:
            raise ValueError("unused output required, or --retry with the same role's completed manifest")
        history = args.output / "history" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        history.mkdir(parents=True)
        for name in ("build.log", "build-manifest.json"):
            shutil.copyfile(args.output / name, history / name)
    else:
        args.output.mkdir(parents=True)
    sys.path.insert(0, str(ROOT / "tools/nu54-builder/src"))
    from nu54_builder_impl.environment import apply_toolchain_environment
    environment = apply_toolchain_environment(args.toolchain.resolve())
    environment["ZEPHYR_BASE"] = str(args.sdk.resolve() / "zephyr")
    environment["CMAKE_BUILD_PARALLEL_LEVEL"] = "2"
    command = [str(args.toolchain / "opt/bin/python.exe"), "-B", "-I", "-m", "west", "build", "--no-sysbuild",
               "-b", BOARD, "-d", str(args.output / "build"), str(APPLICATION), "--",
               f"-DBOARD_ROOT={(ROOT / 'board_package/NU54DK_Zephyr_DTS').as_posix()}",
               f"-DZEPHYR_EXTRA_MODULES={ROOT.as_posix()}", f"-DCOMPANION_ROLE={args.role}", "-DUSE_CCACHE=0",
               f"-DUSER_CACHE_DIR={(args.output / 'cache').as_posix()}"]
    if args.retry:
        # 이전 configure가 만든 raw CONFIG_* cache를 사용자 CLI Kconfig로 재해석하지 않습니다.
        command.extend(("-UCONFIG_*", "-UCLI_CONFIG_*"))
    identity = source_identity()
    build_source_clean = source_clean(ROOT)
    # @note 고정 west는 source와 cwd의 상대 경로를 구하므로 SDK와 다른 drive의 app에서 실행합니다.
    result = subprocess.run(command, cwd=ROOT, env=environment, capture_output=True, timeout=1800)
    log = args.output / "build.log"
    log.write_bytes(result.stdout + result.stderr)
    image = args.output / "build/zephyr/zephyr.hex"
    elf = args.output / "build/zephyr/zephyr.elf"
    config = args.output / "build/zephyr/.config"
    stable = identity == source_identity()
    end_locked = validate_locked_sources(args.sdk)
    valid = (result.returncode == 0 and stable and locked == end_locked and
             image.is_file() and elf.is_file() and config.is_file())
    manifest = {"schema_version": 1, "role": args.role, "identity": identity,
                "identity_stable": stable, "source_revision": revision(ROOT),
                "source_clean": build_source_clean and source_clean(ROOT),
                "ncs_revision": locked["ncs"],
                "zephyr_revision": locked["zephyr"],
                "board_revision": locked["board"],
                "command": command,
                "command_sha256": hashlib.sha256(json.dumps(
                    command, separators=(",", ":")
                ).encode("utf-8")).hexdigest(),
                "exit_code": result.returncode, "log_sha256": digest(log),
                "image": str(image), "image_sha256": digest(image) if valid and image.is_file() else None,
                "elf": str(elf),
                "elf_sha256": digest(elf) if valid and elf.is_file() else None,
                "config": str(config),
                "config_sha256": digest(config) if valid and config.is_file() else None,
                "runtime": "NOT_RUN", "apple_interoperability": "NOT_RUN"}
    (args.output / "build-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest))
    if not valid or not manifest["source_clean"]:
        raise ValueError("build failed or source changed; original log preserved")


def parse(line: str, role: str, identity: str) -> dict:
    """! @brief 중복·누락·다른 image·잘못된 역할을 거부하는 엄격한 protocol decoder입니다. """
    pieces = line.split("|")
    if len(line) > 640 or pieces[:2] != ["M33ECO", "2"] or len(pieces) != 3 + len(FIELDS):
        raise ValueError("malformed protocol record")
    if pieces[2] not in ("READY", "STARTED", "CLIENT_READY", "GO_ACK", "REJECT", "PASS",
                         "FAIL", "STOPPED", "CLEANED"):
        raise ValueError("unknown event")
    values = {}
    for part in pieces[3:]:
        key, separator, value = part.partition("=")
        if separator != "=" or key in values:
            raise ValueError("duplicate or malformed field")
        values[key] = value
    if set(values) != FIELDS or values["role"] != role or values["identity"] != identity or values["revision"] != identity[:40]:
        raise ValueError("role/image/revision/field mismatch")
    if not re.fullmatch(r"[0-9a-f]{104}", identity):
        raise ValueError("invalid image identity")
    if values["nonce"] and not re.fullmatch(r"[0-9a-f]{32}", values["nonce"]):
        raise ValueError("invalid nonce")
    if values["case"] not in ("", *CASES):
        raise ValueError("invalid case")
    for key in ("packets", "attributes", "writes", "negative", "links", "security", "pairings",
                "bonded", "reconnects", "security_rejects", "test_bond"):
        if not re.fullmatch(r"[0-9]{1,6}", values[key]):
            raise ValueError("invalid counter")
        values[key] = int(values[key])
    values["event"] = pieces[2]
    return values


def validate_pass(record: dict, case: str, role: str, nonce: str, security_mode: str) -> None:
    """! @brief 데이터·보안·bond 재사용의 정확한 분모와 현재 session을 검사합니다. """
    actual = tuple(record[key] for key in ("packets", "attributes", "writes", "negative"))
    links_valid = record["links"] in (0, 1) if case == "access_denied" or case.endswith("_bad") else record["links"] == 1
    expected_security = {
        "denied": (0, 0, 0, 0, 1 if role == "peer" else 0, 0),
        "fresh": (1, 1, 1, 0, 0, 1),
        "reconnect": (1, 0, 1, 1, 0, 1),
    }
    security = tuple(record[key] for key in
                     ("security", "pairings", "bonded", "reconnects", "security_rejects", "test_bond"))
    if (record["event"] != "PASS" or record["role"] != role or record["nonce"] != nonce or
            record["case"] != case or actual != COUNTERS[(case, role)] or
            security != expected_security[security_mode] or not links_valid):
        raise ValueError("result denominator/session mismatch")


def validate_cleanup(record: dict, role: str, nonce: str) -> None:
    """! @brief exact test bond만 지운 뒤 기존 bond와 link가 남지 않은 상태를 검사합니다. """
    if (record["event"] != "CLEANED" or record["role"] != role or record["nonce"] != nonce or
            record["links"] != 0 or record["test_bond"] != 0 or record["bonded"] != 0 or
            any(record[key] for key in ("security", "pairings", "reconnects", "security_rejects"))):
        raise ValueError("test-owned bond cleanup mismatch")


def validate_fixture(data: dict) -> None:
    """! @brief 실행 직전 debugger mapping·image readback·다른 radio 격리 증거를 요구합니다. """
    if (data.get("schema_version") != 1 or data.get("other_radios") != "isolated_verified" or
            data.get("test_owned_bond_cleanup") is not True):
        raise ValueError("other connected boards must be explicitly isolated")
    if not re.fullmatch(r"[0-9a-f]{104}", data.get("identity", "")):
        raise ValueError("exact image identity required")
    evidence = Path(data.get("preflight_evidence", ""))
    if not evidence.is_file() or digest(evidence) != data.get("preflight_sha256"):
        raise ValueError("verified preflight evidence file/hash required")
    boards = data.get("boards", [])
    if len(boards) != 2 or {b.get("role") for b in boards} != set(ROLES):
        raise ValueError("one client and one peer required")
    if len({b.get("probe_sha256") for b in boards}) != 2 or len({b.get("port") for b in boards}) != 2:
        raise ValueError("roles must use different probes and ports")
    for board in boards:
        if (not re.fullmatch(r"[0-9a-f]{64}", board.get("probe_sha256", "")) or
                board.get("readback") != "verified" or not board.get("port")):
            raise ValueError("hashed probe, port and image readback required")
        image = Path(board.get("image", ""))
        if not image.is_file() or digest(image) != board.get("image_sha256"):
            raise ValueError("exact image file/hash required")
        build_record = Path(board.get("build_record", ""))
        if (not build_record.is_file() or
                digest(build_record) != board.get("build_record_sha256")):
            raise ValueError("exact build record file/hash required")
        record = json.loads(build_record.read_text(encoding="utf-8"))
        config = Path(record.get("config", ""))
        elf = Path(record.get("elf", ""))
        command = record.get("command")
        if (record.get("schema_version") != 1 or
                record.get("role") != board["role"] or
                record.get("identity") != data["identity"] or
                record.get("identity_stable") is not True or
                record.get("source_revision") != data["identity"][:40] or
                record.get("source_clean") is not True or
                record.get("ncs_revision") != LOCK["ncs"]["revision"] or
                record.get("zephyr_revision") != LOCK["zephyr"]["revision"] or
                record.get("board_revision") != LOCK["board"]["revision"] or
                record.get("image_sha256") != board["image_sha256"] or
                not config.is_file() or digest(config) != record.get("config_sha256") or
                not elf.is_file() or digest(elf) != record.get("elf_sha256") or
                not isinstance(command, list) or "west" not in command or
                "build" not in command or BOARD not in command or
                str(APPLICATION) not in command or
                f"-DCOMPANION_ROLE={board['role']}" not in command or
                hashlib.sha256(json.dumps(
                    command, separators=(",", ":")
                ).encode("utf-8")).hexdigest() != record.get("command_sha256") or
                record.get("exit_code") != 0 or
                record.get("runtime") != "NOT_RUN"):
            raise ValueError("build record identity mismatch")
        flash = board.get("flash")
        if (not isinstance(flash, dict) or
                set(flash) != {"mode", "programmed_bytes", "erase", "auto_unlock",
                              "mass_erase", "automatic_recover"} or
                not str(flash["mode"]).startswith("pyocd-sector") or
                not isinstance(flash["programmed_bytes"], int) or
                flash["programmed_bytes"] <= 0 or flash["erase"] != "sector" or
                flash["auto_unlock"] is not False or flash["mass_erase"] is not False or
                flash["automatic_recover"] is not False):
            raise ValueError("sector program safety receipt required")
    for identity in data.get("isolated_probe_sha256", []):
        if not re.fullmatch(r"[0-9a-f]{64}", identity):
            raise ValueError("isolated probe identity must be SHA-256")


class ProbeLocks:
    """! @brief 기존 HIL과 동일한 SHA-256 lock 경로를 사용합니다. """
    def __init__(self, identities):
        self.identities = sorted(set(identities))
        self.streams = []

    def __enter__(self):
        path = Path(tempfile.gettempdir()) / "nu54dk-hil-locks"
        path.mkdir(parents=True, exist_ok=True)
        try:
            for identity in self.identities:
                stream = (path / (identity + ".lock")).open("a+b")
                self.streams.append(stream)
                if stream.seek(0, os.SEEK_END) == 0:
                    stream.write(b"0")
                    stream.flush()
                stream.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except Exception:
            self.__exit__()
            raise RuntimeError("another HIL owns a probe lock") from None
        return self

    def __exit__(self, *_):
        for stream in reversed(self.streams):
            stream.close()
        self.streams.clear()


class Endpoint:
    """! @brief 유한 serial timeout과 모든 protocol 원본을 보존합니다. """
    def __init__(self, port, role: str, identity: str, transcript: list):
        self.port, self.role, self.identity, self.transcript = port, role, identity, transcript

    def send(self, command: str):
        self.transcript.append(f"{self.role}> {command}")
        self.port.write((command + "\n").encode("ascii"))
        self.port.flush()

    def receive(self, event: str, timeout: float = 10.0, nonce: str | None = None):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            raw = self.port.readline(641)
            if not raw:
                continue
            line = raw.decode("ascii", errors="strict").strip()
            if line:
                self.transcript.append(f"{self.role}< {line}")
            if not line.startswith("M33ECO|"):
                continue
            record = parse(line, self.role, self.identity)
            if record["event"] == "FAIL":
                raise ValueError(f"{self.role} firmware failed")
            if nonce is not None and record["nonce"] != nonce:
                raise ValueError("stale nonce from firmware")
            if record["event"] == event:
                return record
            raise ValueError(f"expected {event}, received {record['event']}")
        raise TimeoutError(f"{self.role} {event} timeout")


def _consume_line(lines: list[str], cursor: int, expected: str,
                  consumed: set[int] | None = None) -> int:
    """! @brief global transcript에서 다음 exact host 명령을 순서대로 소비합니다. """

    for index in range(cursor, len(lines)):
        if lines[index] == expected:
            if consumed is not None:
                consumed.add(index)
            return index + 1
    raise ValueError(f"ecosystem transcript command missing: {expected[:80]}")


def _consume_event(lines: list[str], cursor: int, role: str, event: str,
                   identity: str, nonce: str | None = None,
                   case: str | None = None,
                   consumed: set[int] | None = None) -> int:
    """! @brief global transcript의 다음 firmware event를 strict parser로 소비합니다. """

    prefix = role + "< M33ECO|"
    for index in range(cursor, len(lines)):
        if not lines[index].startswith(prefix):
            continue
        parsed = parse(lines[index].partition("< ")[2], role, identity)
        if parsed["event"] != event:
            raise ValueError(f"ecosystem transcript expected {event}, got {parsed['event']}")
        if nonce is not None and parsed["nonce"] != nonce:
            raise ValueError("ecosystem transcript nonce order mismatch")
        if case is not None and parsed["case"] != case:
            raise ValueError("ecosystem transcript case order mismatch")
        if consumed is not None:
            consumed.add(index)
        return index + 1
    raise ValueError(f"ecosystem transcript event missing: {role}/{event}")


def validate_transcript_evidence(report: dict, lines: list[str]) -> None:
    """! @brief START·GO·PASS·STOP·CLEANUP의 global 실행 순서를 raw 행에서 재생합니다. """

    if not isinstance(lines, list) or not lines:
        raise ValueError("ecosystem transcript is empty")
    cursor = 0
    consumed: set[int] = set()
    for role in ROLES:
        cursor = _consume_line(lines, cursor, role + "> STATUS", consumed)
        cursor = _consume_event(lines, cursor, role, "READY", report["identity"],
                                consumed=consumed)
        for command in ("START " + "0" * 32 + " ancs", "START invalid ancs", "X" * 120):
            cursor = _consume_line(lines, cursor, role + "> " + command, consumed)
            cursor = _consume_event(lines, cursor, role, "REJECT", report["identity"],
                                    consumed=consumed)

    negative = report.get("negative")
    if (not isinstance(negative, list) or len(negative) != 1 or
            not isinstance(negative[0].get("wrong_peer_nonces"), dict) or
            set(negative[0]["wrong_peer_nonces"]) != set(ROLES)):
        raise ValueError("ecosystem negative nonce evidence mismatch")
    for role in ROLES:
        nonce = negative[0]["wrong_peer_nonces"][role]
        cursor = _consume_line(lines, cursor, f"{role}> START {nonce} ancs", consumed)
        cursor = _consume_event(lines, cursor, role, "STARTED", report["identity"], nonce,
                                "ancs", consumed)
    for role in ROLES:
        nonce = negative[0]["wrong_peer_nonces"][role]
        cursor = _consume_line(lines, cursor, role + "> STATUS", consumed)
        cursor = _consume_event(lines, cursor, role, "READY", report["identity"], nonce,
                                "ancs", consumed)
        cursor = _consume_line(lines, cursor, f"{role}> STOP {nonce}", consumed)
        cursor = _consume_event(lines, cursor, role, "STOPPED", report["identity"], nonce,
                                "ancs", consumed)

    for case_row in report.get("cases", []):
        nonce = case_row["nonce"]
        case = case_row["case"]
        for role in ROLES:
            cursor = _consume_line(lines, cursor, f"{role}> START {nonce} {case}", consumed)
            cursor = _consume_event(lines, cursor, role, "STARTED", report["identity"], nonce,
                                    case, consumed)
        if case != "access_denied":
            cursor = _consume_event(lines, cursor, "client", "CLIENT_READY",
                                    report["identity"], nonce, case, consumed)
            cursor = _consume_line(lines, cursor, f"peer> GO {nonce}", consumed)
            cursor = _consume_event(lines, cursor, "peer", "GO_ACK",
                                    report["identity"], nonce, case, consumed)
        for role in ROLES:
            cursor = _consume_event(lines, cursor, role, "PASS",
                                    report["identity"], nonce, case, consumed)
        if case != "access_denied":
            for role in ROLES:
                cursor = _consume_line(lines, cursor, role + "> STOP " + "f" * 32,
                                       consumed)
                cursor = _consume_event(lines, cursor, role, "REJECT",
                                        report["identity"], nonce, case, consumed)
                cursor = _consume_line(lines, cursor, f"{role}> STOP {nonce}", consumed)
        else:
            for role in ROLES:
                cursor = _consume_line(lines, cursor, f"{role}> STOP {nonce}", consumed)
        for role in ROLES:
            cursor = _consume_event(lines, cursor, role, "STOPPED",
                                    report["identity"], nonce, case, consumed)

    bond_nonce = next(row["nonce"] for row in report["cases"]
                      if row["case"] == "ancs" and row["cycle"] == 1)
    for role in ROLES:
        cursor = _consume_line(lines, cursor, f"{role}> CLEANUP {bond_nonce}", consumed)
    for role in ROLES:
        cursor = _consume_event(lines, cursor, role, "CLEANED",
                                report["identity"], bond_nonce, consumed=consumed)
    for role in ROLES:
        cursor = _consume_line(lines, cursor, role + "> STATUS", consumed)
        cursor = _consume_event(lines, cursor, role, "READY", report["identity"],
                                consumed=consumed)
    cleanup = report.get("cleanup")
    expected_cleanup = [
        {"role": role, "status": "PASS", "stop": "PASS",
         "serial_close": "PASS"}
        for role in ROLES
    ]
    if cleanup != expected_cleanup:
        raise ValueError("ecosystem final cleanup evidence mismatch")
    for index, line in enumerate(lines):
        is_host_command = any(line.startswith(role + "> ") for role in ROLES)
        is_protocol_event = any(
            line.startswith(role + "< M33ECO|") for role in ROLES
        )
        if (is_host_command or is_protocol_event) and index not in consumed:
            raise ValueError("ecosystem transcript contains unconsumed command/event")


def execute(args: argparse.Namespace) -> None:
    """! @brief flash 없이 잘못된 peer·재연결·malformed·STOP을 자동 검증합니다. """
    import serial
    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    validate_fixture(fixture)
    if args.output.exists():
        raise ValueError("existing evidence is never overwritten")
    args.output.mkdir(parents=True)
    fixture_copy = args.output / "fixture.json"
    preflight_copy = args.output / "preflight.json"
    shutil.copyfile(args.fixture, fixture_copy)
    shutil.copyfile(Path(fixture["preflight_evidence"]), preflight_copy)
    build_provenance = {}
    for board in fixture["boards"]:
        role = board["role"]
        source_record = Path(board["build_record"])
        record = json.loads(source_record.read_text(encoding="utf-8"))
        copies = {
            "build_record": (source_record, args.output / f"{role}.build-record.json"),
            "config": (Path(record["config"]), args.output / f"{role}.config"),
            "elf": (Path(record["elf"]), args.output / f"{role}.elf"),
        }
        build_provenance[role] = {}
        for kind, (source, target) in copies.items():
            shutil.copyfile(source, target)
            build_provenance[role][kind] = {
                "path": target.name,
                "sha256": digest(target),
            }
    report = {"schema_version": 2, "status": "FAIL", "fixture_sha256": digest(args.fixture),
              "identity": fixture["identity"], "cases": [], "negative": [], "cleanup": [],
              "bond_cleanup": [],
              "case_denominators": {},
              "build_provenance": build_provenance,
              "fixture": {"path": fixture_copy.name,
                          "sha256": digest(fixture_copy)},
              "preflight": {"path": preflight_copy.name,
                            "sha256": digest(preflight_copy)},
              "apple_interoperability": "NOT_RUN", "google_interoperability": "NOT_RUN"}
    transcript, endpoints, active = [], {}, {}
    stop_status = {role: "NOT_RUN" for role in ROLES}
    try:
        with ExitStack() as resources:
            hashes = [b["probe_sha256"] for b in fixture["boards"]] + fixture.get("isolated_probe_sha256", [])
            resources.enter_context(ProbeLocks(hashes))
            for board in sorted(fixture["boards"], key=lambda row: ROLES.index(row["role"])):
                port = resources.enter_context(serial.Serial(board["port"], 115200, timeout=0.1, write_timeout=1.0))
                port.reset_input_buffer()
                endpoint = Endpoint(port, board["role"], fixture["identity"], transcript)
                endpoints[board["role"]] = endpoint
                endpoint.send("STATUS")
                if endpoint.receive("READY")["links"] != 0:
                    raise ValueError("firmware must start disconnected")
                for command in ("START " + "0" * 32 + " ancs", "START invalid ancs", "X" * 120):
                    endpoint.send(command)
                    endpoint.receive("REJECT")
            bond_nonce = None
            try:
                for role in ROLES:
                    nonce = secrets.token_hex(16)
                    active[role] = nonce
                    endpoints[role].send(f"START {nonce} ancs")
                    endpoints[role].receive("STARTED", nonce=nonce)
                wrong_peer_nonces = dict(active)
                time.sleep(2.0)
                for role in ROLES:
                    endpoints[role].send("STATUS")
                    record = endpoints[role].receive("READY", nonce=active[role])
                    if any(record[k] for k in ("links", "packets", "attributes", "writes")):
                        raise ValueError("wrong nonce peer was accepted")
                    endpoints[role].send("STOP " + active[role])
                    if endpoints[role].receive("STOPPED", nonce=active[role])["links"] != 0:
                        raise ValueError("wrong-peer cleanup left a link")
                    stop_status[role] = "PASS"
                    del active[role]
                report["negative"].append({
                    "wrong_peer_nonce": "PASS",
                    "malformed_commands": "PASS",
                    "wrong_peer_nonces": wrong_peer_nonces,
                })
                denied_nonce = secrets.token_hex(16)
                for role in ROLES:
                    active[role] = denied_nonce
                    endpoints[role].send(f"START {denied_nonce} access_denied")
                    endpoints[role].receive("STARTED", nonce=denied_nonce)
                denied_records = {}
                for role in ROLES:
                    record = endpoints[role].receive("PASS", timeout=25.0, nonce=denied_nonce)
                    validate_pass(record, "access_denied", role, denied_nonce, "denied")
                    denied_records[role] = record
                for role in ROLES:
                    endpoints[role].send("STOP " + denied_nonce)
                for role in ROLES:
                    stopped = endpoints[role].receive("STOPPED", nonce=denied_nonce)
                    if stopped["links"] != 0:
                        raise ValueError("denied STOP left a link")
                    stop_status[role] = "PASS"
                    del active[role]
                report["cases"].append({"cycle": 0, "case": "access_denied", "nonce": denied_nonce,
                                        "status": "PASS", "roles": denied_records, "cleanup": "PASS"})

                for cycle, case, security_mode in regression_schedule():
                    nonce = secrets.token_hex(16)
                    if security_mode == "fresh":
                        bond_nonce = nonce
                    for role in ROLES:
                        active[role] = nonce
                        endpoints[role].send(f"START {nonce} {case}")
                        endpoints[role].receive("STARTED", nonce=nonce)
                    endpoints["client"].receive("CLIENT_READY", timeout=25.0, nonce=nonce)
                    endpoints["peer"].send(f"GO {nonce}")
                    endpoints["peer"].receive("GO_ACK", nonce=nonce)
                    records = {}
                    for role in ROLES:
                        record = endpoints[role].receive("PASS", timeout=25.0, nonce=nonce)
                        validate_pass(record, case, role, nonce, security_mode)
                        records[role] = record
                    for role in ROLES:
                        endpoints[role].send("STOP " + "f" * 32)
                        endpoints[role].receive("REJECT", nonce=nonce)
                        endpoints[role].send("STOP " + nonce)
                    for role in ROLES:
                        stopped = endpoints[role].receive("STOPPED", nonce=nonce)
                        if stopped["links"] != 0:
                            raise ValueError("STOP did not close every link")
                        stop_status[role] = "PASS"
                        del active[role]
                    report["cases"].append({"cycle": cycle, "case": case, "nonce": nonce,
                                            "status": "PASS", "roles": records, "cleanup": "PASS"})
                report["case_denominators"] = validate_case_denominators(report["cases"])
                for role in ROLES:
                    endpoints[role].send("CLEANUP " + bond_nonce)
                for role in ROLES:
                    cleaned = endpoints[role].receive("CLEANED", timeout=15.0, nonce=bond_nonce)
                    validate_cleanup(cleaned, role, bond_nonce)
                    report["bond_cleanup"].append(
                        {"role": role, "status": "PASS", "exact_deleted": 1, "existing_unchanged": True})
                for role in ROLES:
                    endpoints[role].send("STATUS")
                    ready = endpoints[role].receive("READY")
                    if ready["links"] != 0 or ready["test_bond"] != 0:
                        raise ValueError("final ecosystem state is not link/bond clean")
                report["status"] = "PASS"
            finally:
                for role, nonce in tuple(active.items()):
                    try:
                        endpoints[role].send("STOP " + nonce)
                        record = endpoints[role].receive("STOPPED", nonce=nonce)
                        if record["links"] != 0:
                            raise ValueError("remaining link")
                        stop_status[role] = "PASS"
                    except Exception as error:
                        report["status"] = "FAIL"
                        report["cleanup"].append({"role": role, "status": "FAIL", "error": type(error).__name__})
                if bond_nonce is not None:
                    for role in ROLES:
                        if not any(entry.get("role") == role for entry in report["bond_cleanup"]):
                            try:
                                endpoints[role].send("CLEANUP " + bond_nonce)
                                cleaned = endpoints[role].receive("CLEANED", timeout=15.0,
                                                                  nonce=bond_nonce)
                                validate_cleanup(cleaned, role, bond_nonce)
                                report["bond_cleanup"].append(
                                    {"role": role, "status": "PASS", "exact_deleted": 1,
                                     "existing_unchanged": True})
                            except Exception as error:
                                report["status"] = "FAIL"
                                report["bond_cleanup"].append(
                                    {"role": role, "status": "FAIL", "error": type(error).__name__})
    except Exception as error:
        report["status"] = "FAIL"
        report["error"] = type(error).__name__ + ": " + str(error)
    report["cleanup"] = [
        {
            "role": role,
            "status": ("PASS" if stop_status[role] == "PASS" and
                       role in endpoints and not endpoints[role].port.is_open else "FAIL"),
            "stop": stop_status[role],
            "serial_close": ("PASS" if role in endpoints and
                             not endpoints[role].port.is_open else "FAIL"),
        }
        for role in ROLES
    ]
    if any(row["status"] != "PASS" for row in report["cleanup"]):
        report["status"] = "FAIL"
    if report["status"] == "PASS":
        try:
            validate_transcript_evidence(report, transcript)
        except Exception as error:
            report["status"] = "FAIL"
            report["error"] = type(error).__name__ + ": " + str(error)
    raw = ("\n".join(transcript) + "\n").encode("ascii")
    (args.output / "transcript.log").write_bytes(raw)
    report["transcript_sha256"] = hashlib.sha256(raw).hexdigest()
    (args.output / "result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "cases": len(report["cases"]), "result": str(args.output / "result.json")}))
    if report["status"] != "PASS":
        raise ValueError("HIL did not pass; original evidence preserved")


def main() -> int:
    """! @brief build와 사전 flash 완료 후 run만 제공하며 복구·erase는 제공하지 않습니다. """
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    build_parser = commands.add_parser("build")
    build_parser.add_argument("--role", choices=ROLES, required=True)
    build_parser.add_argument("--sdk", type=Path, required=True)
    build_parser.add_argument("--toolchain", type=Path, required=True)
    build_parser.add_argument("--output", type=Path, required=True)
    build_parser.add_argument("--retry", action="store_true", help="preserve a completed attempt and reconfigure the same role")
    run_parser = commands.add_parser("run")
    run_parser.add_argument("--fixture", type=Path, required=True)
    run_parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        (build if args.command == "build" else execute)(args)
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(f"ecosystem HIL: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
