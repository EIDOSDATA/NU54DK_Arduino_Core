#!/usr/bin/env python3
"""! @brief 공개하지 않은 exact RC1과 고정 초기 runtime·CLI를 사용자 실기 kit로 묶습니다. """
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[2]


def sha(path):
    """! @brief 원형 파일의 SHA-256을 계산합니다. """
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):
            digest.update(block)
    return digest.hexdigest()


def main():
    """! @brief Git·source·입력 원형을 고정하고 새 kit만 생성합니다. """
    parser = argparse.ArgumentParser()
    parser.add_argument('--source',required=True)
    parser.add_argument('--producer',type=Path,required=True)
    parser.add_argument('--previous-producer',type=Path,required=True)
    parser.add_argument('--previous-source',required=True)
    parser.add_argument('--cli-assets',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    def git(*values):
        """! @brief 현재 Git source만 읽고 branch·tag를 만들지 않습니다. """
        return subprocess.check_output(['git',*values],cwd=ROOT).decode('utf-8').strip()
    if git('rev-parse','HEAD') != args.source or git('status','--porcelain=v1','--untracked-files=all'):
        raise ValueError('kit는 exact clean source에서만 생성합니다.')
    if not args.output.is_absolute() or args.output.exists() or args.output.resolve().is_relative_to(ROOT):
        raise ValueError('저장소 밖의 새 절대 output이 필요합니다.')
    specification = importlib.util.spec_from_file_location('host_kit_lifecycle',ROOT/'tools/release/host_native_lifecycle.py')
    lifecycle = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(lifecycle)
    current = lifecycle.verified_producer(args.producer,args.source,'0.6.0-rc.1')
    previous = lifecycle.verified_producer(args.previous_producer,args.previous_source,'0.6.0-host.1')
    pins = json.loads((ROOT/'tools/nu54-prerequisites/platform-pins.json').read_text(encoding='utf-8'))
    bootstrap = json.loads((ROOT/'tools/nu54-prerequisites/bootstrap-pins.json').read_text(encoding='utf-8'))
    args.output.mkdir(parents=True)
    for name,directory,record in (('current',args.producer,current[0]),('previous',args.previous_producer,previous[0])):
        destination = args.output/'payload'/name
        (destination/'package').mkdir(parents=True)
        shutil.copyfile(directory/'producer.json',destination/'producer.json')
        for path in sorted((directory/'package').iterdir()):
            if path.is_file():
                shutil.copyfile(path,destination/'package'/path.name)
        (destination/'bootstrap-tools').mkdir()
        for platform in bootstrap['platforms'].values():
            pin = platform['arduino_archive']
            path = args.producer/'bootstrap-tools'/pin['filename']
            if path.stat().st_size != pin['size'] or sha(path) != pin['sha256']:
                raise ValueError('bootstrap tool archive pin이 다릅니다.')
            shutil.copyfile(path,destination/'bootstrap-tools'/path.name)
    assets = args.output/'payload/cli'
    assets.mkdir()
    cli_files = {}
    for key,pin in pins['platforms'].items():
        asset = pin['arduino_cli']['archive']
        filename = asset['url'].split('/')[-1]
        path = args.cli_assets/filename
        if path.stat().st_size != asset['size'] or sha(path) != asset['sha256']:
            raise ValueError('고정 CLI archive pin이 다릅니다: '+key)
        shutil.copyfile(path,assets/filename)
        cli_files[key] = 'payload/cli/'+filename
    archive = args.output/'source.tar'
    tooling = ['tools/ci','tools/nu54-builder','tools/nu54-prerequisites','tools/release',
        'packaging/boards-manager','LICENSE','00_Docs/02_빌드 설계/15_Host_RC1_실기_도구와_증거_절차.md']
    subprocess.run(['git','archive','--format=tar','--prefix=source/','-o',str(archive),args.source,*tooling],cwd=ROOT,check=True)
    with tarfile.open(archive) as stream:
        for item in stream.getmembers():
            relative = PurePosixPath(item.name)
            if relative.is_absolute() or '..' in relative.parts or not (item.isdir() or item.isfile()):
                raise ValueError('source archive에 예상하지 않은 경로·link가 있습니다.')
        stream.extractall(args.output,filter='data')
    ## @brief 첫 Python 실행 전 OS 기본 hash 도구로 고정 초기 archive를 검사합니다.
    win = bootstrap['platforms']['windows-x86_64']['arduino_archive']
    win_rel = 'payload/current/bootstrap-tools/'+win['filename']
    entry_rel = 'source/tools/release/host_rc_entry.py'
    entry_sha = sha(args.output/entry_rel)
    starter = '@echo off\r\nsetlocal EnableExtensions\r\nset "KIT=%~dp0"\r\n'
    starter += 'if /i not "%PROCESSOR_ARCHITECTURE%"=="AMD64" exit /b 2\r\n'
    starter += 'powershell.exe -NoLogo -NoProfile -NonInteractive -Command "$ErrorActionPreference=\'Stop\'; if ((Get-FileHash -LiteralPath ($env:KIT+\''+win_rel+'\') -Algorithm SHA256).Hash.ToLower() -ne \''+win['sha256']+'\') { exit 2 }; if ((Get-FileHash -LiteralPath ($env:KIT+\''+entry_rel+'\') -Algorithm SHA256).Hash.ToLower() -ne \''+entry_sha+'\') { exit 2 }"\r\nif errorlevel 1 exit /b 2\r\n'
    starter += 'if not exist "%KIT%runtime-windows\\python\\python.exe" (\r\n  mkdir "%KIT%runtime-windows"\r\n  "%SystemRoot%\\System32\\tar.exe" -xf "%KIT%'+win_rel.replace('/','\\')+'" -C "%KIT%runtime-windows"\r\n  if errorlevel 1 exit /b 2\r\n)\r\n'
    starter += '"%KIT%runtime-windows\\python\\python.exe" -I -X utf8 -B "%KIT%source\\tools\\release\\host_rc_entry.py" --kit "%KIT%." %*\r\nexit /b %ERRORLEVEL%\r\n'
    (args.output/'START.cmd').write_bytes(starter.encode('utf-8'))
    shell = '#!/bin/sh\n# @brief OS 기본 도구로 초기 archive를 검사하고 관리 Python을 실행합니다.\nset -eu\nkit=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)\n'
    shell += 'case "$(uname -s):$(uname -m)" in\n'
    for key,pattern,hasher in [('linux-x86_64','Linux:x86_64','sha256sum'),('macos-arm64','Darwin:arm64','/usr/bin/shasum -a 256')]:
        pin = bootstrap['platforms'][key]['arduino_archive']
        executable = bootstrap['platforms'][key]['executable']
        shell += f'  {pattern}) archive="{pin["filename"]}"; expected="{pin["sha256"]}"; runtime="runtime-{key}"; executable="{executable}"; hasher="{hasher}" ;;\n'
    shell += '  *) echo "Unsupported native OS/architecture" >&2; exit 2 ;;\nesac\n'
    shell += 'actual=$($hasher "$kit/payload/current/bootstrap-tools/$archive" | cut -d " " -f 1)\n[ "$actual" = "$expected" ] || exit 2\n'
    shell += 'entry_sha=$($hasher "$kit/'+entry_rel+'" | cut -d " " -f 1)\n[ "$entry_sha" = "'+entry_sha+'" ] || exit 2\n'
    shell += 'if [ ! -x "$kit/$runtime/$executable" ]; then\n  mkdir "$kit/$runtime"\n  /usr/bin/tar -xf "$kit/payload/current/bootstrap-tools/$archive" -C "$kit/$runtime"\nfi\n'
    shell += 'exec "$kit/$runtime/$executable" -I -X utf8 -B "$kit/source/tools/release/host_rc_entry.py" --kit "$kit" "$@"\n'
    path = args.output/'START.sh'
    path.write_text(shell,encoding='utf-8',newline='\n')
    path.chmod(0o755)
    manifest = dict(schema_version=1,kind='UNPUBLISHED_PRIVATE_HOST_RC1_KIT',source_revision=args.source,
        version='0.6.0-rc.1',previous_source_revision=args.previous_source,previous_version='0.6.0-host.1',
        cli_files=cli_files,publication='NOT_PUBLISHED',physical_OS_gate='NOT_RUN',
        expected_technical_source=args.source,source_scope='TOOLING_AND_CURRENT_GUIDE_FROM_EXACT_GIT_SOURCE',files=[])
    for path in sorted(args.output.rglob('*')):
        if path.is_file():
            manifest['files'].append(dict(path=path.relative_to(args.output).as_posix(),size=path.stat().st_size,sha256=sha(path)))
    (args.output/'kit-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(status='KIT_CREATED_NOT_PHYSICAL_PASS',source_revision=args.source,files=len(manifest['files']),
        kit_manifest_sha256=sha(args.output/'kit-manifest.json'),path=str(args.output))))


if __name__ == '__main__':
    main()
