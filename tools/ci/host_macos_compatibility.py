#!/usr/bin/env python3
"""! @brief 새 source의 비공개 kit와 macOS 실제 버전 증거만 준비하며 장치를 열지 않습니다. """
import argparse
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def main():
    """! @brief OS label 추정 대신 실제 major·architecture를 확인하고 새 증거를 만듭니다. """
    parser = argparse.ArgumentParser()
    parser.add_argument('operation', choices=('kit', 'identity'))
    parser.add_argument('--source', required=True)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--major', choices=('26', '27'))
    args = parser.parse_args()
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip()
    if head != args.source or not args.root.is_absolute() or args.root.resolve().is_relative_to(ROOT):
        raise ValueError('exact source와 저장소 밖 절대 출력이 필요합니다.')
    args.root.mkdir(parents=True, exist_ok=True)
    if args.operation == 'identity':
        observed = dict(source_revision=head, system=platform.system(), release=platform.release(),
            version=platform.mac_ver()[0], architecture=platform.machine(),
            image_os=os.environ.get('ImageOS'), image_version=os.environ.get('ImageVersion'),
            run_id=os.environ.get('GITHUB_RUN_ID'), run_attempt=os.environ.get('GITHUB_RUN_ATTEMPT'),
            requested_major=args.major, hardware_operations=0, physical_OS_gate='NOT_RUN')
        accepted = (observed['system'] == 'Darwin' and observed['architecture'] == 'arm64'
            and observed['version'].split('.')[0] == args.major)
        observed['status'] = 'PASS' if accepted else 'FAIL'
        with (args.root/'identity.json').open('x', encoding='utf-8') as stream:
            json.dump(observed, stream, ensure_ascii=False, indent=2)
        if not accepted:
            raise ValueError('실제 macOS major 또는 architecture가 요청과 다릅니다.')
        print(json.dumps(observed))
        return
    spec = importlib.util.spec_from_file_location('macos_compat_consumer', ROOT/'tools/ci/host_native_package_consumer.py')
    consumer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(consumer)
    pins = json.loads((ROOT/'tools/nu54-prerequisites/platform-pins.json').read_text(encoding='utf-8'))
    assets = args.root/'cli-assets'
    assets.mkdir()
    for key, item in pins['platforms'].items():
        asset = consumer.download(item['arduino_cli']['archive'], args.root/('download-'+key))
        shutil.copyfile(asset, assets/asset.name)
    subprocess.run([sys.executable, '-I', '-B', str(ROOT/'tools/release/host_rc_kit.py'),
        '--source', head, '--producer', str(args.root/'current'), '--previous-source', head,
        '--previous-producer', str(args.root/'previous'), '--cli-assets', str(assets),
        '--output', str(args.root/'kit')], cwd=ROOT, check=True, timeout=180)


if __name__ == '__main__':
    main()
