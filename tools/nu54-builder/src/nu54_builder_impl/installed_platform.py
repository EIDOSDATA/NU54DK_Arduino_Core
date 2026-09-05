"""! @brief 고정 Windows SDK에 전달할 설치 package의 경로와 byte 복사본을 소유합니다. """
from pathlib import Path
import os
from typing import Any

from .common import AdapterError, atomic_write_bytes_if_changed, is_within, tree_content_sha256


## @brief 고정 SDK가 직접 처리하지 못하는 설치 root만 build 복사 대상으로 선택합니다.
def requires_platform_copy(platform_root: Path) -> bool:
    return (os.name == 'nt' and (not str(platform_root).isascii() or ' ' in str(platform_root))
            and not (platform_root / '.git').exists()
            and (platform_root / 'release-manifest.json').is_file())


## @brief 외부 metadata는 원본 root를 유지하고 CMake/compile 경로만 복사본으로 반환합니다.
def platform_build_root(paths: dict[str, Path]) -> Path:
    original = paths['platform_root']
    if not requires_platform_copy(original):
        return original
    workspace = paths['workspace']
    if not str(workspace).isascii() or ' ' in str(workspace):
        raise AdapterError('[NU54:E_SDK_BUILD_PATH] 고정 Windows SDK의 build cache에는 ASCII 공백 없는 경로가 필요합니다. NUCODE_BUILD_CACHE_ROOT를 설정하십시오.')
    return workspace / 'platform'


## @brief 원본 설치 파일만 mapping하며 외부 sketch/library 경로는 보존합니다.
def platform_compiled_path(path: Path, paths: dict[str, Path]) -> Path:
    original = paths['platform_root']
    target = platform_build_root(paths)
    if target != original and is_within(path, original):
        return target / path.resolve().relative_to(original.resolve())
    return path


## @brief 설치 bytes를 cache lock 안에서 동기화하고 누락/손상/부분 복사를 회복합니다.
def materialize_installed_platform(paths: dict[str, Path]) -> None:
    original = paths['platform_root']
    target = platform_build_root(paths)
    if target == original:
        return
    workspace = paths['workspace'].resolve()
    if not is_within(target, workspace) or target.resolve() == workspace:
        raise AdapterError('[NU54:E_PLATFORM_COPY_PATH] 설치 build 복사본이 cache 밖을 가리킵니다.')
    expected = set()
    for source in sorted(original.rglob('*')):
        if source.is_symlink() or (hasattr(source, 'is_junction') and source.is_junction()):
            raise AdapterError('[NU54:E_PLATFORM_COPY_PATH] 설치 package에 link 경로가 있습니다.')
        if not source.is_file() or '__pycache__' in source.parts or source.suffix == '.pyc':
            continue
        relative = source.relative_to(original)
        destination = target / relative
        if not is_within(destination, target) or not is_within(destination, workspace):
            raise AdapterError('[NU54:E_PLATFORM_COPY_PATH] 설치 build 파일이 cache 밖을 가리킵니다.')
        expected.add(relative.as_posix())
        atomic_write_bytes_if_changed(destination, source.read_bytes())
    actual = {p.relative_to(target).as_posix() for p in target.rglob('*')
              if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc'}
    if actual != expected or tree_content_sha256(original, ('.',)) != tree_content_sha256(target, ('.',)):
        raise AdapterError('[NU54:E_PLATFORM_COPY_INTEGRITY] 설치 build 복사본의 파일 집합 또는 bytes가 다릅니다.')


## @brief key 계산 뒤 원본이 바뀌어 이전 identity로 다른 bytes를 빌드하지 않도록 거부합니다.
def validate_platform_copy(paths: dict[str, Path], input_manifest: dict[str, Any]) -> None:
    if not requires_platform_copy(paths['platform_root']):
        return
    expected = input_manifest.get('platform_build_copy', {}).get('content')
    if (not expected or tree_content_sha256(paths['platform_root'], ('.',)) != expected
            or tree_content_sha256(platform_build_root(paths), ('.',)) != expected):
        raise AdapterError('[NU54:E_PLATFORM_COPY_STALE] 설치 package bytes가 cache key 계산 이후 변경되었습니다. 다시 compile하십시오.')
