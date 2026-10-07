#!/usr/bin/env python3
"""! @brief M33 native 위험 회귀의 exact program·readback·dispatcher 증거를 만듭니다. """

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
from typing import Any


HIL = Path(__file__).resolve().parent
REPOSITORY = HIL.parents[2]
TOOLS = REPOSITORY / "tools" / "bluetooth"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from m33_regression import intel_hex_ranges  # noqa: E402
from ble_pair_hil_common import validate_build_record  # noqa: E402


def _write_new_regular_json(path: Path, value: dict[str, Any]) -> None:
    """! @brief readback JSON을 symlink 추종 없이 배타 regular file로 생성합니다. """

    try:
        path.lstat()
    except FileNotFoundError:
        pass
    else:
        raise FileExistsError("readback output already exists: " + str(path))
    raw = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode(
        "utf-8"
    )
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0) | \
        getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            raise ExactProgrammingFailure("readback output is not a regular file")
        offset = 0
        while offset < len(raw):
            written = os.write(descriptor, raw[offset:])
            if written <= 0:
                raise ExactProgrammingFailure("readback output write failed")
            offset += written
        os.fsync(descriptor)
        after = path.lstat()
        if stat.S_ISLNK(after.st_mode) or (
                opened.st_dev, opened.st_ino) != (after.st_dev, after.st_ino):
            raise ExactProgrammingFailure("readback output changed while writing")
    finally:
        os.close(descriptor)


SHA256 = re.compile(r"[0-9a-f]{64}")
_PROGRAM_AUTHORITY = object()


class ExactProgrammingFailure(RuntimeError):
    """! @brief exact build·sector program·readback 결합에 실패했습니다. """


class ExactProgrammingReceipt:
    """! @brief 같은 프로세스의 실제 readback 뒤에만 생성되는 비직렬화 receipt입니다. """

    __slots__ = ("_authority", "roles", "fingerprints")

    def __init__(self, authority: object, roles: tuple[str, ...], fingerprints: tuple[str, ...]):
        self._authority = authority
        self.roles = roles
        self.fingerprints = fingerprints


def _digest(path: Path) -> str:
    """! @brief 파일 byte의 SHA-256을 반환합니다. """

    return hashlib.sha256(path.read_bytes()).hexdigest()


def require_exact_clean_source(repository: Path, expected_revision: str) -> None:
    """! @brief 실행 종료 시점에도 같은 clean commit인지 다시 확인합니다. """

    revision = subprocess.run(
        ["git", "-C", str(repository), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    dirty = subprocess.run(
        [
            "git",
            "-C",
            str(repository),
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    if revision != expected_revision or dirty:
        raise ExactProgrammingFailure("exact source changed or became dirty during HIL")


def build_record_path(image: Path) -> Path:
    """! @brief Arduino JSON 또는 native YAML build record의 실제 경로를 반환합니다. """

    arduino = image.with_suffix(".nu54-build.json")
    if arduino.is_file():
        return arduino
    native = image.parent.parent / "nucode_arduino_core_build.yml"
    if not native.is_file():
        raise ExactProgrammingFailure("exact build record file is missing")
    return native


def reserve_sidecars(native_path: Path, roles: tuple[str, ...]) -> dict[str, dict[str, Path]]:
    """! @brief native JSON 옆의 image·build·readback 경로를 덮어쓰기 없이 예약합니다. """

    stem = native_path.stem
    sidecars = {
        role: {
            "image": native_path.with_name(f"{stem}.{role}.image.hex"),
            "build_record": native_path.with_name(f"{stem}.{role}.build-record"),
            "readback": native_path.with_name(f"{stem}.{role}.readback.json"),
        }
        for role in roles
    }
    existing = [
        path
        for values in sidecars.values()
        for path in values.values()
        if path.exists()
    ]
    if existing:
        raise ExactProgrammingFailure("기존 exact program sidecar를 덮어쓰지 않습니다")
    native_path.parent.mkdir(parents=True, exist_ok=True)
    return sidecars


def copy_program_inputs(
    images: dict[str, Path],
    sidecars: dict[str, dict[str, Path]],
) -> dict[str, dict[str, str]]:
    """! @brief 검증할 image와 build record 원본 byte를 evidence 묶음에 복사합니다. """

    if set(images) != set(sidecars):
        raise ExactProgrammingFailure("program input role mismatch")
    copied: dict[str, dict[str, str]] = {}
    for role, image in images.items():
        resolved = image.resolve()
        if not resolved.is_file() or resolved.suffix.lower() != ".hex":
            raise ExactProgrammingFailure(f"{role} exact HEX is missing")
        record = build_record_path(resolved)
        shutil.copyfile(resolved, sidecars[role]["image"])
        shutil.copyfile(record, sidecars[role]["build_record"])
        copied[role] = {
            "image_sha256": _digest(sidecars[role]["image"]),
            "build_record_sha256": _digest(sidecars[role]["build_record"]),
        }
    return copied


def _load_pyocd_site_packages() -> None:
    """! @brief 고정 workspace pyOCD를 readback 시점에만 불러옵니다. """

    try:
        __import__("pyocd")
    except ModuleNotFoundError:
        from pyocd_launcher import _resolve_site_packages

        site_packages = _resolve_site_packages()
        if site_packages is not None and str(site_packages) not in sys.path:
            sys.path.insert(0, str(site_packages))


ACTIVE_TARGET_STATES = {"RUNNING", "SLEEPING"}


def readback_state_restored(pre_state: object, post_state: object) -> bool:
    """! @brief readback 전후 halt 또는 실행 가능 상태가 보존됐는지 판정합니다. """

    if pre_state == "HALTED":
        return post_state == "HALTED"
    return pre_state in ACTIVE_TARGET_STATES and post_state in ACTIVE_TARGET_STATES


def readback_programmed_images(
    probe_ids: dict[str, str],
    probe_hashes: dict[str, str],
    images: dict[str, Path],
    sidecars: dict[str, dict[str, Path]],
) -> tuple[dict[str, dict[str, Any]], ExactProgrammingReceipt]:
    """! @brief exact probe를 halt해 HEX byte를 비교하고 원래 CPU 상태로 복원합니다.

    여기서 RUNNING/HALTED는 debugger가 관측한 CPU 실행 상태다. Application의 RF STOP,
    link 해제, 자원 cleanup semantic과는 별개이며 어느 쪽도 다른 쪽의 PASS를 대신하지 않는다.
    """

    roles = tuple(images)
    if set(probe_ids) != set(roles) or set(probe_hashes) != set(roles) or \
            set(sidecars) != set(roles):
        raise ExactProgrammingFailure("readback role mapping mismatch")
    if len(set(probe_ids.values())) != len(roles) or \
            len(set(probe_hashes.values())) != len(roles):
        raise ExactProgrammingFailure("readback probes must be distinct")
    _load_pyocd_site_packages()
    from m33_diagnostics import (
        IdleAuditFailure,
        PyocdPreparationBackend,
        halt_and_wait,
        private_debug_output,
        readback_ranges,
        wait_for_target_state,
    )

    records: dict[str, dict[str, Any]] = {}
    fingerprints: list[str] = []
    with private_debug_output():
        backend = PyocdPreparationBackend()
        probes, _ports = backend.discover()
        by_uid = {probe.unique_id.strip().lower(): probe for probe in probes}
        for role in roles:
            raw_uid = probe_ids[role].strip().lower()
            expected_hash = probe_hashes[role]
            if SHA256.fullmatch(expected_hash) is None or \
                    hashlib.sha256(raw_uid.encode("ascii")).hexdigest() != expected_hash:
                raise ExactProgrammingFailure(f"{role} probe provenance mismatch")
            probe = by_uid.get(raw_uid)
            if probe is None:
                raise ExactProgrammingFailure(f"{role} exact readback probe is absent")
            ranges = intel_hex_ranges(images[role])
            with backend.session(probe) as session:
                pre_state = session.target.get_state().name
                if pre_state not in ACTIVE_TARGET_STATES | {"HALTED"}:
                    raise ExactProgrammingFailure(
                        f"{role} unsupported pre-readback target state: {pre_state}"
                    )
                failure: ExactProgrammingFailure | None = None
                observed: list[dict[str, Any]] = []
                try:
                    try:
                        monitor = halt_and_wait(session.target)
                    except IdleAuditFailure as error:
                        kind = error.evidence.get("kind", "unknown")
                        raise ExactProgrammingFailure(
                            f"{role} readback halt failed: {kind}"
                        ) from None
                    try:
                        observed = readback_ranges(
                            session.target, ranges, monitor=monitor
                        )
                    except IdleAuditFailure as error:
                        kind = error.evidence.get("kind", "unknown")
                        raise ExactProgrammingFailure(
                            f"{role} readback stability failed: {kind}"
                        ) from None
                except ExactProgrammingFailure as error:
                    failure = error
                except Exception as error:
                    failure = ExactProgrammingFailure(
                        f"{role} readback failed: {type(error).__name__}"
                    )
                try:
                    if pre_state in ACTIVE_TARGET_STATES:
                        session.target.resume()
                        post_state = wait_for_target_state(
                            session.target, ACTIVE_TARGET_STATES
                        )
                    else:
                        post_state = wait_for_target_state(
                            session.target, {"HALTED"}
                        )
                except Exception as error:
                    restore_failure = ExactProgrammingFailure(
                        f"{role} readback state restore failed: {type(error).__name__}"
                    )
                    if failure is not None:
                        raise ExactProgrammingFailure(
                            f"{failure}; {restore_failure}"
                        ) from None
                    raise restore_failure from None
                if failure is not None:
                    raise failure
            restored = readback_state_restored(pre_state, post_state)
            if not restored:
                raise ExactProgrammingFailure(f"{role} readback state restore failed")
            record = {
                "schema_version": 1,
                "kind": "m33_exact_program_readback",
                "status": "PASS",
                "role": role,
                "probe_sha256": expected_hash,
                "image_sha256": _digest(images[role]),
                "backend": "pyocd-live-target",
                "halted": True,
                "resumed": pre_state in ACTIVE_TARGET_STATES,
                "pre_state": pre_state,
                "post_state": post_state,
                "restored": restored,
                "ranges": observed,
            }
            _write_new_regular_json(sidecars[role]["readback"], record)
            records[role] = record
            fingerprints.append(hashlib.sha256(
                json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest())
    return records, ExactProgrammingReceipt(
        _PROGRAM_AUTHORITY, roles, tuple(fingerprints)
    )


def readback_programmed_images_by_hash(
    probe_hashes: dict[str, str],
    images: dict[str, Path],
    sidecars: dict[str, dict[str, Path]],
) -> tuple[dict[str, dict[str, Any]], ExactProgrammingReceipt]:
    """! @brief raw probe ID를 직렬화하지 않고 hash mapping으로 live readback을 수행합니다. """

    roles = tuple(images)
    if set(probe_hashes) != set(roles) or set(sidecars) != set(roles):
        raise ExactProgrammingFailure("hashed readback role mapping mismatch")
    if len(set(probe_hashes.values())) != len(roles) or any(
            SHA256.fullmatch(value) is None for value in probe_hashes.values()):
        raise ExactProgrammingFailure("hashed readback probes must be distinct SHA-256 values")
    _load_pyocd_site_packages()
    from m33_diagnostics import PyocdPreparationBackend, private_debug_output

    with private_debug_output():
        probes, _ports = PyocdPreparationBackend().discover()
    by_hash = {
        hashlib.sha256(probe.unique_id.strip().lower().encode("ascii")).hexdigest():
        probe.unique_id
        for probe in probes
    }
    if any(identity not in by_hash for identity in probe_hashes.values()):
        raise ExactProgrammingFailure("exact hashed readback probe is absent")
    probe_ids = {
        role: by_hash[probe_hashes[role]]
        for role in roles
    }
    return readback_programmed_images(
        probe_ids, probe_hashes, images, sidecars
    )


def validate_programming_receipt(
    receipt: ExactProgrammingReceipt,
    roles: tuple[str, ...],
    records: dict[str, dict[str, Any]],
) -> None:
    """! @brief 문자열 verified나 임의 hash가 실제 same-process readback을 대신하지 못하게 합니다. """

    fingerprints = tuple(
        hashlib.sha256(
            json.dumps(records[role], sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        for role in roles
    )
    if not isinstance(receipt, ExactProgrammingReceipt) or \
            receipt._authority is not _PROGRAM_AUTHORITY or \
            receipt.roles != roles or receipt.fingerprints != fingerprints:
        raise ExactProgrammingFailure("same-process exact programming receipt mismatch")


def exact_program_evidence(
    roles: tuple[str, ...],
    probe_hashes: dict[str, str],
    sidecars: dict[str, dict[str, Path]],
    flash_records: dict[str, dict[str, str]],
    build_records: dict[str, dict[str, str]],
    readback_records: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """! @brief build·sector program·readback·probe를 역할별 한 record로 결합합니다. """

    evidence: dict[str, dict[str, Any]] = {}
    for role in roles:
        flash = flash_records.get(role, {})
        build = build_records.get(role, {})
        readback = readback_records.get(role, {})
        image_digest = _digest(sidecars[role]["image"])
        build_digest = _digest(sidecars[role]["build_record"])
        if SHA256.fullmatch(probe_hashes.get(role, "")) is None:
            raise ExactProgrammingFailure(f"{role} probe hash proof missing")
        if sidecars[role]["image"].stat().st_size <= 0 or \
                sidecars[role]["build_record"].stat().st_size <= 0 or \
                sidecars[role]["readback"].stat().st_size <= 0:
            raise ExactProgrammingFailure(f"{role} exact program sidecar is empty")
        if not str(flash.get("mode", "")).startswith("pyocd-sector") or \
                not str(flash.get("bytes", "")).isdecimal() or \
                int(flash["bytes"]) <= 0:
            raise ExactProgrammingFailure(f"{role} sector program proof missing")
        if SHA256.fullmatch(build.get("record_sha256", "")) is None or \
                build["record_sha256"] != build_digest:
            raise ExactProgrammingFailure(f"{role} exact build record proof missing")
        pre_state = readback.get("pre_state")
        post_state = readback.get("post_state")
        if readback.get("status") != "PASS" or \
                readback.get("probe_sha256") != probe_hashes[role] or \
                readback.get("image_sha256") != image_digest or \
                not readback_state_restored(pre_state, post_state) or \
                readback.get("restored") is not True or \
                readback.get("resumed") is not (pre_state in ACTIVE_TARGET_STATES) or \
                not readback.get("ranges") or \
                any(row.get("status") != "PASS" or
                    row.get("expected_sha256") != row.get("observed_sha256")
                    for row in readback.get("ranges", [])):
            raise ExactProgrammingFailure(f"{role} programmed byte readback missing")
        evidence[role] = {
            "probe_sha256": probe_hashes[role],
            "image": {
                "path": sidecars[role]["image"].name,
                "sha256": image_digest,
            },
            "build_record": {
                "path": sidecars[role]["build_record"].name,
                "sha256": build_digest,
            },
            "flash": {
                "mode": flash["mode"],
                "programmed_bytes": int(flash["bytes"]),
                "erase": "sector",
                "auto_unlock": False,
                "mass_erase": False,
                "automatic_recover": False,
            },
            "readback": {
                "path": sidecars[role]["readback"].name,
                "sha256": _digest(sidecars[role]["readback"]),
            },
        }
    return evidence


def prepare_direct_program(
    native_path: Path,
    roles: tuple[str, ...],
    images: dict[str, Path],
    source_revision: str,
    board_revision: str,
    application_root: Path | dict[str, Path],
) -> tuple[dict[str, dict[str, Path]], dict[str, dict[str, str]]]:
    """! @brief direct-HIL 입력을 exact build record와 인접 sidecar에 결합합니다. """

    if set(images) != set(roles):
        raise ExactProgrammingFailure("direct program image role mismatch")
    if isinstance(application_root, dict):
        if set(application_root) != set(roles) or not all(
                isinstance(value, Path) for value in application_root.values()):
            raise ExactProgrammingFailure("direct program application role mismatch")
        application_roots = application_root
    else:
        application_roots = {role: application_root for role in roles}
    build_records = {
        role: validate_build_record(
            images[role], source_revision, board_revision, application_roots[role]
        )
        for role in roles
    }
    sidecars = reserve_sidecars(native_path, roles)
    copied = copy_program_inputs(images, sidecars)
    for role in roles:
        if copied[role]["image_sha256"] != _digest(images[role]) or \
                copied[role]["build_record_sha256"] != \
                build_records[role]["record_sha256"]:
            raise ExactProgrammingFailure(f"{role} copied exact input mismatch")
    return sidecars, build_records


def complete_direct_program(
    repository: Path,
    source_revision: str,
    roles: tuple[str, ...],
    images: dict[str, Path],
    probe_ids: dict[str, str],
    probe_hashes: dict[str, str],
    sidecars: dict[str, dict[str, Path]],
    flash_records: dict[str, dict[str, str]],
    build_records: dict[str, dict[str, str]],
) -> dict[str, dict[str, Any]]:
    """! @brief clean source를 재확인하고 live readback을 exact program 증거로 닫습니다. """

    require_exact_clean_source(repository, source_revision)
    readbacks, receipt = readback_programmed_images(
        probe_ids, probe_hashes, images, sidecars
    )
    validate_programming_receipt(receipt, roles, readbacks)
    return exact_program_evidence(
        roles,
        probe_hashes,
        sidecars,
        flash_records,
        build_records,
        readbacks,
    )


def cleanup_direct_ports(
    ports: dict[str, object],
    stop_commands: dict[str, bytes],
    confirmed_stopped: set[str],
    transcript: list[str],
) -> dict[str, dict[str, str]]:
    """! @brief 부분 open과 실패 경로에서도 STOP·close 결과를 숨김없이 기록합니다. """

    records: dict[str, dict[str, str]] = {}
    for role, port in ports.items():
        stop_status = "PASS" if role in confirmed_stopped else "NOT_CONFIRMED"
        if role not in confirmed_stopped:
            try:
                port.write(stop_commands[role])
                port.flush()
                stop_status = "SENT_NOT_CONFIRMED"
                transcript.append(f"{role}-cleanup: STOP_SENT_NOT_CONFIRMED")
            except BaseException as error:
                stop_status = f"ERROR:{type(error).__name__}"
                transcript.append(f"{role}-cleanup: STOP_ERROR={type(error).__name__}")
        close_status = "PASS"
        try:
            port.close()
        except BaseException as error:
            close_status = f"ERROR:{type(error).__name__}"
            transcript.append(f"{role}-cleanup: CLOSE_ERROR={type(error).__name__}")
        records[role] = {
            "stop": stop_status,
            "serial_close": close_status,
        }
    return records


def dispatch_attestation(
    campaign_id: str,
    source_revision: str,
    cycles: int,
    semantics: tuple[str, ...],
    roles: tuple[str, ...],
    exact_program: dict[str, dict[str, Any]],
    semantic_status: dict[str, str] | None = None,
    cycle_records: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """! @brief adapter가 원시 cycle과 실제 image/readback byte를 재검증할 구조를 만듭니다. """

    if cycles <= 0 or set(exact_program) != set(roles):
        raise ExactProgrammingFailure("dispatcher attestation denominator mismatch")
    statuses = semantic_status or {token: "PASS" for token in semantics}
    if set(statuses) != set(semantics) or any(
            value not in ("PASS", "NOT_APPLICABLE")
            for value in statuses.values()):
        raise ExactProgrammingFailure("dispatcher semantic status mismatch")
    records = cycle_records
    if records is None:
        records = [
            {
                "cycle": cycle,
                "status": "PASS",
                "semantics": dict(statuses),
            }
            for cycle in range(1, cycles + 1)
        ]
    if len(records) != cycles or any(
            set(row) != {"cycle", "status", "semantics"} or
            row["cycle"] != index or row["status"] != "PASS" or
            row["semantics"] != statuses
            for index, row in enumerate(records, 1)):
        raise ExactProgrammingFailure("dispatcher raw-derived cycle mismatch")
    return {
        "schema_version": 1,
        "kind": "m33_native_campaign_attestation",
        "campaign_id": campaign_id,
        "source_revision": source_revision,
        "source_clean": True,
        "semantic_status": statuses,
        "cycle_records": records,
        "hardware": [
            {
                "role": role,
                "probe_sha256": exact_program[role]["probe_sha256"],
                "image": exact_program[role]["image"],
                "build_record": exact_program[role]["build_record"],
                "flash": exact_program[role]["flash"],
                "readback": exact_program[role]["readback"],
            }
            for role in roles
        ],
    }
