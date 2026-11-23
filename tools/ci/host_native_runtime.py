#!/usr/bin/env python3
"""! @brief 설치된 exact Core backend로 SDK 환경과 CI 전용 서명 fixture를 준비합니다. """
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys


def main() -> int:
    """! @brief 초기 Python이 SDK 자체 Python을 선택하고 private key 원문을 출력하지 않습니다. """
    parser = argparse.ArgumentParser()
    parser.add_argument('--platform', type=Path, required=True)
    parser.add_argument('--signing-key', type=Path, required=True)
    parser.add_argument('--verify-image', type=Path)
    args = parser.parse_args()
    platform = args.platform.resolve()
    key = args.signing_key.resolve()
    valid_key = key.is_file() if args.verify_image is not None else not key.exists()
    if not args.signing_key.is_absolute() or not valid_key or not (platform / 'release-manifest.json').is_file():
        raise ValueError('exact 설치 Core와 새 CI signing fixture 경로가 필요합니다.')
    source = platform / 'tools/nu54-builder/src/nu54_builder.py'
    spec = importlib.util.spec_from_file_location('installed_native_sdk_environment', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    tool = module.tool_environment(platform)
    python = module.implementation.host.resolve_toolchain_executable(tool['toolchain_root'], 'python')
    key.parent.mkdir(parents=True, exist_ok=True)
    program = '''import hashlib, json, os, pathlib, sys
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
key = ec.generate_private_key(ec.SECP256R1())
private = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption())
public = key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
descriptor = os.open(sys.argv[1], os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(descriptor, 'wb') as stream:
    stream.write(private)
print(json.dumps({'curve':'secp256r1','public_key_sha256':hashlib.sha256(public).hexdigest(),'public_key_der_hex':public.hex(),'CI_fixture_only':True}))
'''
    arguments = [str(key)]
    if args.verify_image is not None:
        if not args.verify_image.is_absolute() or not args.verify_image.is_file():
            raise ValueError('검증할 실제 signed image가 없습니다.')
        program = '''import hashlib,json,sys
sys.path.insert(0, sys.argv[3])
from imgtool import keys
from imgtool.image import Image, VerifyResult
key = keys.load(sys.argv[1])
ret, version, digest, signature = Image.verify(sys.argv[2], key)
assert ret == VerifyResult.OK and digest is not None
public = key.get_public_bytes()
print(json.dumps({'status':'PASS','image_version':list(version),'image_digest_sha256':digest.hex(),
    'public_key_sha256':hashlib.sha256(public).hexdigest(),'CI_fixture_only':True}))
'''
        arguments += [str(args.verify_image), str(tool['ncs_root'] / 'bootloader/mcuboot/scripts')]
    result = subprocess.run([str(python), '-I', '-B', '-c', program, *arguments], env=tool['environment'],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60, check=False)
    if result.returncode != 0:
        sys.stderr.buffer.write(result.stderr)
        raise RuntimeError('SDK Python의 CI 서명 fixture 생성 또는 실제 image 검증이 실패했습니다.')
    public = json.loads(result.stdout)
    manifest = json.loads((platform / 'release-manifest.json').read_text(encoding='utf-8'))
    public.update(source_revision=manifest['core_revision'], sdk_bundle=tool['toolchain_root'].name,
        bootstrap_python=sys.version.split()[0], SDK_environment_verified=True)
    print(json.dumps(public, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='backslashreplace')
    raise SystemExit(main())
