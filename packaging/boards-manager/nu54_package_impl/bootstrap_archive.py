"""! @brief upstream 실행 파일 byte를 보존하며 Arduino용 부모 디렉터리 우선 archive를 생성합니다. """
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import posixpath
import tarfile

LAYOUT = 'USTAR_PARENTS_FIRST_BZIP2_9_V1'


def digest(path: Path) -> str:
    """! @brief 실제 archive byte를 hash합니다. """
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def safe_name(name: str) -> PurePosixPath:
    """! @brief 단일 python root 안의 정규 상대 경로만 허용합니다. """
    path = PurePosixPath(name)
    if (path.is_absolute() or '..' in path.parts or not path.parts or path.parts[0] != 'python'
            or '\\' in name or ':' in name or path.as_posix() != name.rstrip('/')):
        raise ValueError('초기 runtime archive 경로가 안전하지 않습니다: ' + name)
    return path


def inventory(archive: Path) -> dict[str, dict]:
    """! @brief 파일 byte·실행 mode와 link 의미를 추출 없이 기록합니다. """
    result = {}
    with tarfile.open(archive) as stream:
        for item in stream.getmembers():
            safe_name(item.name)
            if item.isdir():
                continue
            if item.name in result or not (item.isfile() or item.issym()) or item.mode & 0o7000:
                raise ValueError('중복·특수·고권한 runtime member를 허용하지 않습니다.')
            row = {'type': 'file' if item.isfile() else 'symlink', 'mode': item.mode & 0o777}
            if item.isfile():
                row.update(size=item.size, sha256=hashlib.file_digest(stream.extractfile(item), 'sha256').hexdigest())
            else:
                if not item.linkname or PurePosixPath(item.linkname).is_absolute() or '\\' in item.linkname or ':' in item.linkname:
                    raise ValueError('runtime symlink가 상대 경로가 아닙니다.')
                target = posixpath.normpath(posixpath.join(posixpath.dirname(item.name), item.linkname))
                safe_name(target)
                row.update(target=item.linkname, resolved_target=target)
            result[item.name] = row
    for name, row in result.items():
        if row['type'] != 'symlink':
            continue
        target, seen = row['resolved_target'], {name}
        while target in result and result[target]['type'] == 'symlink':
            if target in seen:
                raise ValueError('runtime symlink가 순환합니다.')
            seen.add(target)
            target = result[target]['resolved_target']
        if target not in result:
            raise ValueError('runtime symlink 대상 파일이 없습니다: ' + name)
        if any(parent.as_posix() in result for parent in PurePosixPath(name).parents if parent.as_posix() != '.'):
            raise ValueError('runtime 파일/link를 상위 디렉터리로 사용할 수 없습니다.')
    return result


def normalize(upstream: Path, output: Path, notices: dict[str, bytes], expected_upstream: dict) -> dict:
    """! @brief 고정 upstream 검증 후 directory 순서·고지·provenance만 추가하고 모든 원형 파일을 대조합니다. """
    if (output.exists() or upstream.stat().st_size != expected_upstream['size']
            or digest(upstream) != expected_upstream['sha256']):
        raise ValueError('새 출력과 실제 size·SHA-256이 일치하는 upstream archive가 필요합니다.')
    original = inventory(upstream)
    provenance = {'schema_version': 1, 'layout': LAYOUT, 'upstream': expected_upstream,
        'upstream_file_and_link_count': len(original), 'executable_bytes_modified': False,
        'notice_sha256': {name: hashlib.sha256(data).hexdigest() for name, data in sorted(notices.items())}}
    additions = {'python/NU54_PROVENANCE.json': (json.dumps(provenance, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf-8')}
    for name, data in notices.items():
        if PurePosixPath(name).name != name or not name or name in ('.', '..'):
            raise ValueError('고지 파일 이름이 단일 basename이 아닙니다.')
        additions['python/NU54_LICENSES/' + name] = data
    if set(original) & set(additions):
        raise ValueError('새 provenance·고지가 upstream 파일을 덮어쓸 수 없습니다.')
    directories = {parent.as_posix() for name in original.keys() | additions.keys()
        for parent in PurePosixPath(name).parents if parent.as_posix() != '.'}
    if any(name in original for name in directories):
        raise ValueError('파일·link가 다른 member의 부모가 될 수 없습니다.')
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('xb') as destination, tarfile.open(upstream) as source, tarfile.open(
            fileobj=destination, mode='w:bz2', format=tarfile.USTAR_FORMAT, compresslevel=9) as target:
        for name in sorted(directories, key=lambda name: (len(PurePosixPath(name).parts), name)):
            item = tarfile.TarInfo(name)
            item.type, item.mode = tarfile.DIRTYPE, 0o755
            target.addfile(item)
        for name in sorted(original):
            old = source.getmember(name)
            item = tarfile.TarInfo(name)
            item.type, item.mode, item.size = old.type, old.mode & 0o777, old.size
            item.linkname = old.linkname
            target.addfile(item, source.extractfile(old) if old.isfile() else None)
        for name, data in sorted(additions.items()):
            item = tarfile.TarInfo(name)
            item.mode, item.size = 0o644, len(data)
            target.addfile(item, io.BytesIO(data))
    observed = inventory(output)
    if any(observed.get(name) != row for name, row in original.items()) or set(observed) != original.keys() | additions.keys():
        raise ValueError('정규화 뒤 upstream 파일 byte·mode·link 의미가 바뀌었습니다.')
    return {'filename': output.name, 'size': output.stat().st_size, 'sha256': digest(output),
        'layout': LAYOUT, 'upstream_members_unchanged': len(original), 'added_notice_files': len(notices),
        'executable_bytes_modified': False}
