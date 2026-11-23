#!/usr/bin/env python3
"""! @brief GitHub native runner에서 OS별 prerequisite를 설치하고 실제 실행 범위를 기록합니다. """
from __future__ import annotations

import argparse
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def capture_layout(toolchain: Path, source: str, reports: Path):
    """! @brief 부가 경로 진단 오류가 원래 설치 FAIL을 덮어쓰지 않도록 보존합니다. """
    try:
        layout = {'source_revision': source, 'toolchain_root': str(toolchain), 'metadata': {}, 'declared_programs': []}
        for name in ('environment.json', 'manifest.json'):
            path = toolchain / name
            if path.is_file():
                layout['metadata'][name] = json.loads(path.read_text(encoding='utf-8-sig'))
        for entry in layout['metadata'].get('environment.json', {}).get('env_vars', []):
            if entry.get('key') != 'PATH' or entry.get('type') != 'relative_paths':
                continue
            for relative in entry['values']:
                directory = toolchain / relative
                if not directory.is_dir():
                    continue
                for path in directory.iterdir():
                    if path.name.startswith(('python', 'west', 'git', 'arm-zephyr-eabi')):
                        layout['declared_programs'].append({'path': str(path.relative_to(toolchain)),
                            'is_file': path.is_file(), 'is_symlink': path.is_symlink()})
        (reports / 'toolchain-layout.json').write_text(json.dumps(layout, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    except Exception as error:
        print('HOST_LAYOUT_DIAGNOSTIC_ERROR=' + type(error).__name__, flush=True)


def main():
    """! @brief 사용자 PC 설치와 구분된 CI 전용 실행·증거 경로를 구성합니다. """
    parser = argparse.ArgumentParser()
    parser.add_argument('--bootstrap-only', action='store_true')
    args = parser.parse_args()
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise RuntimeError('이 진입점은 GitHub native runner 전용입니다. 사용자 PC에서는 nordic.py를 사용하십시오.')
    source = ROOT / 'tools/nu54-builder/src/nu54_builder.py'
    spec = importlib.util.spec_from_file_location('host_native_ci', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    from importlib import import_module
    backend = import_module(module.implementation.__name__ + '.prerequisites')
    descriptor = backend.describe_host()
    module.require_supported_host(descriptor)
    base = Path(os.environ['RUNNER_TEMP']).resolve() / 'nu54-host'
    reports = base / 'reports'
    reports.mkdir(parents=True, exist_ok=True)
    state = base / 'state'
    cache = base / 'downloads'
    if descriptor['os'] == 'macos':
        install = Path('/opt/nordic/ncs')
    elif descriptor['os'] == 'windows':
        install = Path('D:/ncs')
    else:
        install = Path.home() / 'ncs'
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip()
    if head != os.environ['GITHUB_SHA']:
        raise RuntimeError('현재 checkout과 CI source SHA가 다릅니다.')
    context = {'schema_version': 1, 'kind': 'host_native_prerequisite_CI',
        'source_revision': head, 'host': descriptor, 'runner_name': os.environ.get('RUNNER_NAME'),
        'observed_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'operation': 'bootstrap' if args.bootstrap_only else 'install',
        'state_root': str(state), 'install_root': str(install),
        'manifest_sha256': hashlib.sha256(backend.MANIFEST_PATH.read_bytes()).hexdigest(),
        'hardware_operations': 0, 'user_physical_OS_gate': 'NOT_RUN',
        'free_bytes': shutil.disk_usage(base).free}
    (reports / 'context.json').write_text(json.dumps(context, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(context, ensure_ascii=False), flush=True)
    command = [context['operation'], '--state-root', str(state), '--install-root', str(install),
        '--cache-root', str(cache), '--evidence', str(reports / 'prerequisites.json')]
    try:
        backend.main(command)
    finally:
        toolchain = install / 'toolchains' / backend.BUNDLES[context['host']['os'] + '-' + context['host']['architecture']]
        capture_layout(toolchain, head, reports)
    if not args.bootstrap_only:
        backend.main(['verify', '--state-root', str(state), '--install-root', str(install),
            '--evidence', str(reports / 'stored-verification.json')])
    return 0


if __name__ == '__main__':
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='backslashreplace')
    raise SystemExit(main())
