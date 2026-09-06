"""! @brief 패키저의 Git 입력 선택과 byte 변환 책임입니다. """
from __future__ import annotations
from . import model
from pathlib import Path, PurePosixPath
import datetime as dt
import re
import subprocess
from .model import (
    PackageError,
    SourceFile,
)


## @brief 외부 명령을 실행하고 실패를 패키징 오류로 변환합니다.
def run_checked(arguments: list[str], *, cwd: Path, binary: bool = False) -> bytes | str:
    try:
        result = subprocess.run(
            arguments,
            cwd=cwd,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=not binary,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        detail = ""
        if isinstance(error, subprocess.CalledProcessError):
            stderr = error.stderr
            detail = stderr.decode("utf-8", "replace") if isinstance(stderr, bytes) else (stderr or "")
        raise PackageError(f"명령 실행 실패: {' '.join(arguments)}\n{detail.strip()}") from error
    return result.stdout


## @brief Git ref를 full commit SHA로 고정합니다.
def resolve_commit(repo_root: Path, revision: str) -> str:
    output = run_checked(
        ["git", "rev-parse", "--verify", f"{revision}^{{commit}}"], cwd=repo_root
    )
    commit = str(output).strip()
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise PackageError(f"full Git commit SHA를 얻지 못했습니다: {commit}")
    return commit


## @brief Git commit 시간을 SPDX UTC timestamp로 정규화합니다.
def commit_timestamp(repo_root: Path, commit: str) -> str:
    output = str(
        run_checked(["git", "show", "-s", "--format=%cI", commit], cwd=repo_root)
    ).strip()
    try:
        parsed = dt.datetime.fromisoformat(output).astimezone(dt.timezone.utc)
    except ValueError as error:
        raise PackageError(f"Git commit 시간을 해석하지 못했습니다: {output}") from error
    return parsed.replace(microsecond=0).isoformat().replace("+00:00", "Z")


## @brief Git tree의 blob 및 gitlink를 byte 안전하게 열거합니다.
def git_tree_entries(repo_root: Path, revision: str) -> list[tuple[str, str, str, str]]:
    raw = run_checked(
        ["git", "ls-tree", "-r", "-z", "--full-tree", revision], cwd=repo_root, binary=True
    )
    assert isinstance(raw, bytes)
    entries: list[tuple[str, str, str, str]] = []
    for record in raw.split(b"\0"):
        if not record:
            continue
        try:
            metadata, encoded_path = record.split(b"\t", 1)
            mode, object_type, object_id = metadata.decode("ascii").split(" ", 2)
            path = encoded_path.decode("utf-8")
        except (ValueError, UnicodeDecodeError) as error:
            raise PackageError("Git tree record를 안전하게 해석하지 못했습니다.") from error
        entries.append((mode, object_type, object_id, path))
    return entries


## @brief Git blob 원문을 읽습니다.
def git_blob(repo_root: Path, object_id: str) -> bytes:
    output = run_checked(["git", "cat-file", "blob", object_id], cwd=repo_root, binary=True)
    assert isinstance(output, bytes)
    return output


## @brief Windows 추출 환경에서 위험하거나 비밀일 수 있는 경로를 거부합니다.
def ensure_safe_relative_path(path: str) -> None:
    if not path or "\\" in path or "\0" in path:
        raise PackageError(f"안전하지 않은 경로입니다: {path!r}")
    pure = PurePosixPath(path)
    if pure.is_absolute() or any(part in ("", ".", "..") for part in pure.parts):
        raise PackageError(f"안전하지 않은 상대 경로입니다: {path}")
    if re.match(r"^[A-Za-z]:", path):
        raise PackageError(f"드라이브 경로는 허용하지 않습니다: {path}")
    for part in pure.parts:
        lowered = part.casefold()
        if lowered in {".git", ".svn", ".hg", "__pycache__", "build", "out", ".cache"}:
            raise PackageError(f"배포 금지 경로가 포함되었습니다: {path}")
        if lowered in {"id_rsa", "id_ed25519", "authorized_keys", ".env", "secrets.json"}:
            raise PackageError(f"비밀정보 후보 파일은 배포할 수 없습니다: {path}")
        if lowered.endswith((".pem", ".pfx", ".p12", ".jks", ".keystore", ".key")):
            raise PackageError(f"개인키 후보 파일은 배포할 수 없습니다: {path}")


## @brief Arduino platform runtime에 필요한 상위 저장소 파일만 선택합니다.
def include_core_path(path: str) -> bool:
    ensure_safe_relative_path(path)
    pure = PurePosixPath(path)
    if path.endswith("/.gitkeep") or pure.name == ".gitkeep" or pure.suffix.casefold() == ".pdf":
        return False
    if len(pure.parts) == 1:
        return pure.name in {
            "LICENSE",
            "boards.txt",
            "platform.txt",
            "programmers.txt",
            "post_install.bat",
            "post_install.sh",
        }
    root = pure.parts[0]
    if root in {"cores", "dts", "libraries", "third_party", "variants", "zephyr"}:
        return True
    if root == "tools":
        return len(pure.parts) >= 2 and pure.parts[1] in {"nu54-builder", "nu54-prerequisites"}
    return False


## @brief 보드 저장소에서 DTS runtime과 라이선스만 선택합니다.
def include_board_path(path: str) -> bool:
    ensure_safe_relative_path(path)
    pure = PurePosixPath(path)
    if pure.suffix.casefold() == ".pdf" or pure.name == ".gitkeep":
        return False
    if pure.parts[0] == "boards":
        return True
    if len(pure.parts) == 1 and pure.name in {"LICENSE", "NOTICE"}:
        return True
    return pure.parts[0] == "LICENSES"


## @brief platform.txt의 version만 배포 버전으로 교체합니다.
def rewrite_platform_version(data: bytes, version: str) -> bytes:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise PackageError("platform.txt가 UTF-8이 아닙니다.") from error
    lines = text.splitlines(keepends=True)
    matches = [index for index, line in enumerate(lines) if line.startswith("version=")]
    if matches != [1] and len(matches) != 1:
        raise PackageError("platform.txt에는 version= 항목이 정확히 하나 있어야 합니다.")
    index = matches[0]
    ending = "\r\n" if lines[index].endswith("\r\n") else "\n"
    lines[index] = f"version={version}{ending}"
    return "".join(lines).encode("utf-8")


## @brief cmd.exe가 안정적으로 해석하도록 Windows command script를 CRLF로 고정합니다.
def rewrite_windows_command_line_endings(data: bytes, path: str) -> bytes:
    try:
        text = data.decode("ascii")
    except UnicodeDecodeError as error:
        raise PackageError(f"Windows command script가 ASCII-only가 아닙니다: {path}") from error
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return normalized.replace("\n", "\r\n").encode("ascii")


## @brief 상위 commit과 gitlink commit을 깨끗한 패키지 입력으로 materialize합니다.
def collect_source_files(repo_root: Path, commit: str, version: str) -> tuple[list[SourceFile], str]:
    board_path = "board_package/NU54DK_Zephyr_DTS"
    board_entry: tuple[str, str, str, str] | None = None
    files: list[SourceFile] = []
    for mode, object_type, object_id, path in git_tree_entries(repo_root, commit):
        if path == board_path:
            board_entry = (mode, object_type, object_id, path)
            continue
        if path.startswith(f"{board_path}/"):
            raise PackageError("보드 패키지가 gitlink가 아닌 중첩 파일로 저장되어 있습니다.")
        if not include_core_path(path):
            continue
        if object_type != "blob" or mode not in {"100644", "100755"}:
            raise PackageError(f"지원하지 않는 Git object입니다: {mode} {object_type} {path}")
        data = git_blob(repo_root, object_id)
        transformation = None
        if path == "platform.txt":
            data = rewrite_platform_version(data, version)
            transformation = "platform-version"
        elif (
            version in model.WINDOWS_SAFE_VERSIONS
            and PurePosixPath(path).suffix.casefold() in {".bat", ".cmd"}
        ):
            data = rewrite_windows_command_line_endings(data, path)
            transformation = "windows-crlf"
        files.append(
            SourceFile(
                path=path,
                data=data,
                mode=0o755 if mode == "100755" else 0o644,
                origin="core",
                git_object=object_id,
                transformation=transformation,
            )
        )

    if board_entry is None:
        raise PackageError(f"{commit}에 {board_path} gitlink가 없습니다.")
    mode, object_type, board_revision, _ = board_entry
    if mode != "160000" or object_type != "commit" or not re.fullmatch(r"[0-9a-f]{40}", board_revision):
        raise PackageError("보드 패키지 항목이 유효한 gitlink가 아닙니다.")
    submodule_root = repo_root / board_path
    if not submodule_root.is_dir():
        raise PackageError("보드 서브모듈이 초기화되지 않았습니다. git submodule update --init을 실행하십시오.")
    try:
        run_checked(["git", "cat-file", "-e", f"{board_revision}^{{commit}}"], cwd=submodule_root)
    except PackageError as error:
        raise PackageError(f"보드 서브모듈에 고정 revision이 없습니다: {board_revision}") from error

    for sub_mode, sub_type, object_id, sub_path in git_tree_entries(submodule_root, board_revision):
        if not include_board_path(sub_path):
            continue
        if sub_type != "blob" or sub_mode not in {"100644", "100755"}:
            raise PackageError(f"지원하지 않는 보드 Git object입니다: {sub_path}")
        package_path = f"{board_path}/{sub_path}"
        files.append(
            SourceFile(
                path=package_path,
                data=git_blob(submodule_root, object_id),
                mode=0o755 if sub_mode == "100755" else 0o644,
                origin="board",
                git_object=object_id,
            )
        )

    files.sort(key=lambda item: item.path.encode("utf-8"))
    paths = [item.path for item in files]
    if len(paths) != len(set(paths)) or len({path.casefold() for path in paths}) != len(paths):
        raise PackageError("대소문자 비구분 환경에서 충돌하는 패키지 경로가 있습니다.")
    required = {
        "LICENSE",
        "boards.txt",
        "platform.txt",
        "tools/nu54-prerequisites/pins.json",
        f"{board_path}/LICENSE",
        f"{board_path}/NOTICE",
    }
    missing = sorted(required.difference(paths))
    if missing:
        raise PackageError(f"필수 패키지 파일이 없습니다: {', '.join(missing)}")
    return files, board_revision
