#!/usr/bin/env python3
"""! @brief W06 단계의 불변 입력·중단 안전 기록·실패 분류를 공통 관리합니다. """
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
from typing import Callable, Iterator


CATEGORIES = frozenset({
    "ENVIRONMENT", "TRANSPORT", "FUNCTIONAL", "INTEGRITY", "SAFETY",
    "INTERRUPTED", "INTERNAL",
})
NAME = re.compile(r"[a-z][a-z0-9_-]*\Z")


class ExecutionFailure(ValueError):
    """! @brief 재실행 가능성을 의미 판정과 구분하는 명시적 실행 오류입니다. """

    def __init__(self, category: str, message: str):
        if category not in CATEGORIES:
            raise ValueError("unknown execution failure category")
        super().__init__(message)
        self.category = category


def require(condition: bool, message: str) -> None:
    """! @brief 불변 계약 불일치는 일반 시험 실패가 아닌 무결성 오류로 중단합니다. """

    if not condition:
        raise ExecutionFailure("INTEGRITY", message)


def digest(path: Path) -> str:
    """! @brief 큰 파일도 일정 메모리로 SHA-256을 계산합니다. """

    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def canonical(value: object) -> str:
    """! @brief 입력의 canonical JSON hash를 반환합니다. """

    raw = json.dumps(value, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def regular(path: Path, directory: bool = False) -> None:
    """! @brief checkpoint 소유 node의 symlink/junction/reparse 우회를 거부합니다. """

    info = path.lstat()
    require(not path.is_symlink() and not
            (getattr(info, "st_file_attributes", 0) & 0x400),
            "execution node must not be a link: " + path.name)
    require(stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode),
            "execution node type mismatch: " + path.name)


def read_json(path: Path) -> dict:
    """! @brief 잘린 JSON과 중복 key를 정상 checkpoint로 해석하지 않습니다. """

    def pairs(rows: list[tuple[str, object]]) -> dict:
        result = {}
        for key, value in rows:
            require(key not in result, "duplicate execution JSON key")
            result[key] = value
        return result

    regular(path)
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=pairs)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ExecutionFailure("INTEGRITY", "incomplete execution JSON") from error
    require(isinstance(value, dict), "execution JSON must be an object")
    return value


def write_new_bytes(path: Path, raw: bytes) -> None:
    """! @brief fsync 후 no-clobber link로 완성 byte만 원자 공개합니다. """

    path.parent.mkdir(parents=True, exist_ok=True)
    for parent in (path.parent, *path.parent.parents):
        regular(parent, directory=True)
    require(not os.path.lexists(path), "execution output overwrite refused")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix="." + path.name + ".pending-", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        # @note replace와 달리 경쟁 작성자가 만든 기존 결과도 덮어쓰지 않습니다.
        os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def write_new_json(path: Path, document: dict) -> None:
    """! @brief JSON 출력 전체를 한 번에 공개하며 기존 결과는 보존합니다. """

    raw = (json.dumps(document, ensure_ascii=False, sort_keys=True,
                      indent=2, allow_nan=False) + "\n").encode("utf-8")
    write_new_bytes(path, raw)


def failure_record(error: BaseException) -> dict:
    """! @brief 임의 예외 문자열의 raw UID 노출 없이 실패 종류를 보존합니다. """

    category = error.category if isinstance(error, ExecutionFailure) else (
        "INTERRUPTED" if isinstance(error, (KeyboardInterrupt, SystemExit)) else
        "ENVIRONMENT" if isinstance(error, OSError) else "INTERNAL"
    )
    return {"status": "FAIL", "category": category,
            "error_type": type(error).__name__}


def validate_stage(validate: Callable[[Path], None], attempt: Path) -> None:
    """! @brief 기존 의미 validator의 오류도 재시도 불가 무결성 실패로 분류합니다. """

    try:
        validate(attempt)
    except ExecutionFailure:
        raise
    except (ValueError, OSError) as error:
        raise ExecutionFailure("INTEGRITY", "execution output validation failed") from error


def references(root: Path, paths: list[Path]) -> list[dict]:
    """! @brief 위치와 무관한 attempt 소유 상대 경로·내용 hash를 고정합니다. """

    rows = []
    seen = set()
    for path in paths:
        relative = path.relative_to(root).as_posix()
        require(relative not in seen and ".." not in Path(relative).parts,
                "duplicate or escaping execution output")
        seen.add(relative)
        regular(path)
        for parent in path.parents:
            if parent == root:
                break
            regular(parent, directory=True)
        rows.append({"path": relative, "bytes": path.stat().st_size,
                     "sha256": digest(path)})
    return sorted(rows, key=lambda row: row["path"])


def validate_references(root: Path, rows: list[dict]) -> None:
    """! @brief 재개 전에 모든 확정 output의 경로와 byte를 다시 검증합니다. """

    require(isinstance(rows, list) and bool(rows), "execution outputs are missing")
    paths = []
    for row in rows:
        require(isinstance(row, dict) and set(row) == {"path", "bytes", "sha256"},
                "execution output reference schema mismatch")
        relative = row["path"]
        require(type(row["bytes"]) is int and row["bytes"] >= 0,
                "execution output size mismatch")
        require(isinstance(relative, str) and relative and
                not Path(relative).is_absolute() and ":" not in relative and
                "\\" not in relative and
                all(part not in {"", ".", ".."} for part in relative.split("/")),
                "execution output path escape")
        paths.append(root / relative)
    require(references(root, paths) == rows, "execution output byte/hash drift")


@contextmanager
def exclusive(root: Path) -> Iterator[None]:
    """! @brief 프로세스 종료 때 OS가 반환하는 단일 writer lock을 잡습니다. """

    root.mkdir(parents=True, exist_ok=True)
    regular(root, directory=True)
    lock_path = root / ".execution.lock"
    if os.path.lexists(lock_path):
        regular(lock_path)
    stream = lock_path.open("a+b")
    locked = False
    try:
        if lock_path.stat().st_size == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        locked = True
        yield
    except OSError as error:
        if not locked:
            raise ExecutionFailure("ENVIRONMENT", "execution root is already in use") from error
        raise
    finally:
        if locked:
            stream.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        stream.close()


class StageJournal:
    """! @brief 실행 위치와 분리된 입력 계약으로 단계별 완료·실패를 보존합니다. """

    def __init__(self, root: Path, identity: dict):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        regular(root, directory=True)
        self.identity = canonical(identity)
        session = {"schema_version": 1, "kind": "m33_execution_session",
                   "identity": identity, "identity_sha256": self.identity}
        path = root / "session.json"
        if os.path.lexists(path):
            require(read_json(path) == session, "execution session/input drift")
        else:
            require(not any(root.glob("*/attempt-*")),
                    "execution attempts exist without a session")
            write_new_json(path, session)

    def run(self, name: str, inputs: dict,
            execute: Callable[[Path], list[Path]],
            validate: Callable[[Path], None]) -> Path:
        """! @brief 완료 단계만 재사용하고 부분 실패는 다음 attempt에서 실행합니다. """

        require(NAME.fullmatch(name) is not None, "invalid execution stage name")
        stage = self.root / name
        stage.mkdir(exist_ok=True)
        regular(stage, directory=True)
        attempts = sorted(stage.glob("attempt-*"))
        expected = [f"attempt-{index:04d}" for index in range(1, len(attempts) + 1)]
        require([path.name for path in attempts] == expected,
                "execution attempt sequence mismatch")
        binding = {"session_sha256": self.identity, "stage": name,
                   "inputs_sha256": canonical(inputs)}
        completed = None
        for attempt in attempts:
            regular(attempt, directory=True)
            request = attempt / "request.json"
            # @note mkdir 직후 중단된 빈 attempt만 요청 없는 부분 상태로 허용합니다.
            if not request.exists():
                require(not any(path for path in attempt.iterdir()
                                if not path.name.startswith(".request.json.pending-")),
                        "execution data exists without request")
                continue
            require(read_json(request) == binding, "execution stage input drift")
            receipt = attempt / "complete.json"
            failure = attempt / "failure.json"
            if receipt.exists():
                require(completed is None and attempt == attempts[-1] and not failure.exists(),
                        "execution attempts follow completion")
                document = read_json(receipt)
                require(set(document) == {"binding", "status", "outputs"} and
                        document["binding"] == binding and document["status"] == "PASS",
                        "execution completion binding mismatch")
                validate_references(attempt, document["outputs"])
                validate_stage(validate, attempt)
                completed = attempt
            elif failure.exists():
                document = read_json(failure)
                require(set(document) == {"binding", "status", "category", "error_type", "outputs"} and
                        document["binding"] == binding and document["status"] == "FAIL" and
                        document["category"] in CATEGORIES,
                        "execution failure binding mismatch")
                validate_references(attempt, document["outputs"])
                require(document["category"] not in {"INTEGRITY", "SAFETY"},
                        "execution requires integrity/safety investigation")
        if completed is not None:
            return completed
        attempt = stage / f"attempt-{len(attempts) + 1:04d}"
        attempt.mkdir()
        write_new_json(attempt / "request.json", binding)
        try:
            paths = execute(attempt)
            validate_stage(validate, attempt)
            rows = references(attempt, paths)
            validate_references(attempt, rows)
            write_new_json(attempt / "complete.json",
                           {"binding": binding, "status": "PASS", "outputs": rows})
        except BaseException as error:
            if not (attempt / "complete.json").exists():
                # @note 실패의 원본 로그·입력도 seal하여 다음 attempt가 과거 실패를 숨기지 못하게 합니다.
                preserved = sorted(path for path in attempt.rglob("*")
                                   if path.is_file() and not path.is_symlink() and
                                   ".pending-" not in path.name and
                                   path.suffix not in {".o", ".obj", ".a", ".d", ".pyc"})
                write_new_json(attempt / "failure.json", {
                    "binding": binding, **failure_record(error),
                    "outputs": references(attempt, preserved),
                })
            raise
        return attempt
