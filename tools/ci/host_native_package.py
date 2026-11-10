#!/usr/bin/env python3
"""! @brief 공개 allowlist를 바꾸지 않고 exact source의 native 시험 package·index를 생성합니다. """
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
from typing import Sequence

ROOT = Path(__file__).resolve().parents[2]
PRIVATE_VERSIONS = ('0.6.0-host.1', '0.6.0-rc.1')


def load_package(root: Path = ROOT):
    """! @brief CWD·PYTHONPATH와 분리해 같은 checkout의 package backend를 읽습니다. """
    spec = importlib.util.spec_from_file_location('host_native_package_producer', root / 'packaging/boards-manager/nu54_package.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha(path: Path) -> str:
    """! @brief 실제 파일 byte의 SHA-256을 계산합니다. """
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def git(root: Path, *arguments: str) -> str:
    """! @brief shell 재해석 없이 exact Git identity와 clean 상태만 확인합니다. """
    return subprocess.check_output(['git', *arguments], cwd=root, text=True, encoding='utf-8').strip()


def build(root: Path, source: str, output: Path, version: str) -> dict:
    """! @brief 두 번 독립 생성한 모든 sidecar·archive를 대조하고 official URL index를 기록합니다. """
    root, output = root.resolve(), output.resolve()
    if (version not in PRIVATE_VERSIONS or not re.fullmatch(r'[0-9a-f]{40}', source)
            or git(root, 'rev-parse', 'HEAD') != source or git(root, 'status', '--porcelain=v1', '--untracked-files=all')):
        raise ValueError('native package 생성은 허용한 private version과 exact clean HEAD를 요구합니다.')
    if output.exists() or output.is_relative_to(root):
        raise ValueError('기존 출력이나 source 내부에는 native package를 생성하지 않습니다.')
    package = load_package(root)
    if version in package.PACKAGE_VERSIONS:
        raise ValueError('native 시험 version이 이미 공개 allowlist에 있습니다.')
    package.configure_release_candidates(package.RELEASE_CANDIDATE_VERSIONS + (version,))
    output.mkdir(parents=True)
    first = package.build_package(root, output / 'package', version, source)
    second = package.build_package(root, output / 'repeated', version, source)
    first_files = {path.name: sha(path) for path in (output / 'package').iterdir() if path.is_file()}
    second_files = {path.name: sha(path) for path in (output / 'repeated').iterdir() if path.is_file()}
    if not first_files or first_files != second_files:
        raise ValueError('native archive 또는 sidecar의 독립 재생성 byte가 다릅니다.')
    manifest = package.validate_archive(first['archive'], expected_version=version, expected_commit=source)
    index = package.generate_index(output / 'package', [version])
    package.validate_index(index, artifact_dir=output / 'package')
    record = {'schema_version': 1, 'kind': 'HOST_NATIVE_PRIVATE_PACKAGE_PRODUCER', 'source_revision': source,
        'version': version, 'board_revision': manifest['board_revision'], 'reproducible_bytes': True,
        'source_date_epoch': int(git(root, 'show', '-s', '--format=%ct', source)),
        'archive': {'filename': first['archive'].name, 'sha256': sha(first['archive']), 'size': first['archive'].stat().st_size},
        'index': {'filename': index.name, 'sha256': sha(index)}, 'sidecar_sha256': first_files,
        'platform_prerequisites_sha256': manifest['platform_prerequisites_sha256'],
        'bootstrap_pins_sha256': manifest['bootstrap_pins_sha256'],
        'runtime_payload_sha256': manifest['runtime_payload_sha256'], 'toolchain_bundle_ids': manifest['toolchain_bundle_ids'],
        'public_release_or_tag_created': False, 'user_physical_OS_gate': 'NOT_RUN',
        'observed_utc': datetime.now(timezone.utc).isoformat()}
    (output / 'producer.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return record


def main(arguments: Sequence[str] | None = None) -> int:
    """! @brief 생성·검증만 수행하며 publish·root index 갱신 명령을 제공하지 않습니다. """
    parser = argparse.ArgumentParser()
    parser.add_argument('--repository', type=Path, default=ROOT)
    parser.add_argument('--source', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--version', choices=PRIVATE_VERSIONS, default=PRIVATE_VERSIONS[0])
    args = parser.parse_args(arguments)
    result = build(args.repository, args.source, args.output, args.version)
    print(json.dumps({'status': 'HOST_NATIVE_PACKAGE_PRODUCER_PASS', 'source_revision': result['source_revision'],
        'archive_sha256': result['archive']['sha256'], 'reproducible_bytes': True}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
