"""! @brief 수정 package의 실제 설치 build마다 configure/live revision과 보존 artifact를 검증합니다. """
from pathlib import Path
import hashlib,importlib.util,json,os,shutil,subprocess,sys,zipfile
import yaml

repo=Path(r'C:\Users\eidos\GitHub\NU54DK_Arduino_Core');work=Path(__file__).parent
mode=sys.argv[1];root=Path(sys.argv[2]);prefix='verified-package'
proof=json.loads((work/(prefix+'-reproducibility.json')).read_text(encoding='utf-8'))
archive=work/(prefix+'-a')/'nucode-nu54dk-zephyr-0.0.90.zip'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def save(path,data):path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module);return module
assert sha(archive)==proof['files'][archive.name]['sha256']
assert not root.exists();root.mkdir()
smoke=load('r13_verified_smoke',repo/'tests/arduino-cli/run_smoke.py')
with zipfile.ZipFile(archive) as z:z.extractall(root/'archive')
extracted=next((root/'archive').glob('*/release-manifest.json')).parent
platform=smoke.stage_packaged_platform(extracted,root/'검증 설치')
config=root/'arduino-cli.yaml';smoke.write_cli_config(config,root/'검증 설치',root/'data',root/'downloads')
cli=Path(r'C:\NU54DEV\tools\arduino-cli-1.5.1\arduino-cli.exe')
save(root/'installation.json',{'source_commit':proof['source_commit'],'archive_sha256':sha(archive),'platform_root':str(platform),'extracted_root':str(extracted),'config':str(config),'physical_executed':False})
if mode=='examples':
    env={**os.environ,'PATH':str(cli.parent)+os.pathsep+os.environ['PATH'],'PYTHONUTF8':'1','NUCODE_M13_CLI_DISCOVERY':'1','ARDUINO_DIRECTORIES_USER':str(root/'검증 설치'),'ARDUINO_DIRECTORIES_DATA':str(root/'data'),'ARDUINO_DIRECTORIES_DOWNLOADS':str(root/'downloads')}
    with (root/'m13-discovery.log').open('w',encoding='utf-8') as stream:
        result=subprocess.run([sys.executable,str(repo/'tests/host/test_m13_profiles.py'),'-v'],cwd=root,env=env,stdout=stream,stderr=subprocess.STDOUT)
    assert result.returncode==0,('M13 installed discovery',result.returncode)

builder=load('r13_verified_builder',platform/'tools/nu54-builder/src/nu54_builder.py')
bundle=Path(r'C:\Users\eidos\ncs\toolchains\dcbdc366a1');ncs=Path(r'C:\Users\eidos\ncs\v3.4.0')
os.environ['PATH']=os.pathsep.join([str(Path(os.environ['SystemRoot'])/'System32'),os.environ['SystemRoot'],r'C:\Program Files\Git\cmd'])
os.environ.update(builder.apply_toolchain_environment(bundle))
os.environ['PATH']=str(work.parent/'r00/bin')+os.pathsep+os.environ['PATH']
os.environ.update({'PYTHONUTF8':'1','NUCODE_NCS_ROOT':str(ncs),'NUCODE_TOOLCHAIN_ROOT':str(bundle),'NUCODE_PYTHON':str(bundle/'opt/bin/python.exe'),'NUCODE_BUILD_CACHE_ROOT':str(root/'cache')})
for key in ['CC','CXX']:os.environ.pop(key,None)
(root/'tmp').mkdir();os.environ['TEMP']=os.environ['TMP']=str(root/'tmp')
builder.tool_environment(platform);os.chdir(root)

def verify_identity(path):
    data=json.loads(path.read_text(encoding='utf-8'))
    assert data['product_identity']=={'source_version':'0.4.0-dev','package_version':'0.0.90'}
    for item in data['artifacts'].values():
        p=Path(item['path']);assert p.is_file() and sha(p)==item['sha256'] and p.stat().st_size==item['size'],p
    for item in data['source_inputs']['sources']:
        p=Path(item['source_path']);assert p.is_file() and sha(p)==item['sha256'],p
    live_ref=data['source_inputs']['live_build_record'];live_path=Path(live_ref['path'])
    assert sha(live_path)==live_ref['sha256']
    live=yaml.safe_load(live_path.read_text(encoding='utf-8'))['nucode_arduino_core']
    configured_path=Path(data['context']['zephyr_build_dir'])/'build_info.yml'
    configured=yaml.safe_load(configured_path.read_text(encoding='utf-8'))['cmake']['vendor-specific']['nucode-arduino-core']
    assert live['core_revision']==configured['core-revision']==proof['source_commit'],(path,live,configured)
    assert live['board_revision']==configured['board-package-revision']==proof['board_revision'],path
    assert live['core_source_sha256']==configured['core-source-sha256'],path
    destination=root/'identity-records'/path.parent.name;destination.mkdir(parents=True)
    shutil.copyfile(path,destination/path.name)
    shutil.copyfile(live_path,destination/'nucode_arduino_core_build.yml')
    shutil.copyfile(configured_path,destination/'build_info.yml')
    save(destination/'verified.json',{'manifest_path':str(path),'manifest_sha256':sha(path),'artifacts':data['artifacts'],'source_inputs':data['source_inputs'],'live_record':{'path':str(destination/'nucode_arduino_core_build.yml'),'sha256':sha(live_path),'identity':live},'configure_record':{'path':str(destination/'build_info.yml'),'sha256':sha(configured_path),'identity':configured},'physical_executed':False})

if mode=='examples':
    runner=load('r13_verified_examples',repo/'tools/release/run_m27_package_examples.py')
    validate=runner.BASE.validate_build_manifest
    def validate_and_preserve(path,**kwargs):
        result=validate(path,**kwargs);verify_identity(path);return result
    runner.BASE.validate_build_manifest=validate_and_preserve
    result=runner.main(['--arduino-cli',str(cli),'--config',str(config),'--platform-root',str(platform),'--build-root',str(root/'examples'),'--ncs-root',str(ncs),'--toolchain-root',str(bundle),'--cache-root',str(root/'cache'),'--forbid-root',str(repo),'--evidence',str(root/'examples.json'),'--package-version','0.0.90','--workers','4'])
    assert result==0
    expected=29
elif mode=='provenance-smoke':
    original_assert=smoke.assert_build
    def assert_and_preserve(build,project):
        result=original_assert(build,project);verify_identity(build/(project+'.nu54-build.json'));return result
    smoke.assert_build=assert_and_preserve
    assert smoke.main(['--cli',str(cli),'--platform-root',str(extracted),'--tests','m7'])==0
    selections=[]
    for selection in ['pyocd','pyocd_uid']:
        build=root/('m8-compile-'+selection);sketch=repo/'tests/arduino-cli/m8_upload'
        command=smoke.compile_command(cli,config,build,sketch);command[-1:-1]=('--board-options','upload_probe='+selection)
        smoke.run(command);context=smoke.assert_build(build,'m8_upload.ino')
        manifest=build/'m8_upload.ino.nu54-build.json';data=json.loads(manifest.read_text(encoding='utf-8'))
        assert data['fqbn']==smoke.FQBN+':upload_probe='+selection and data['sysbuild'] is False
        runners=(Path(context['zephyr_build_dir'])/'zephyr/runners.yaml').read_text(encoding='utf-8')
        for token in ['- pyocd','- jlink','--target=nrf54l','--device=nRF54L15_M33']:assert token in runners
        selections.append(selection)
    save(root/'provenance-smoke.json',{'source_commit':proof['source_commit'],'m7':'4 actual compile/config checks plus actual live scope PASS','m8_compile_only':selections,'physical_executed':False,'upload_sentinel':'NOT RUN: would enumerate probes'})
    expected=6
else:raise RuntimeError('unknown mode')
records=[json.loads(p.read_text(encoding='utf-8')) for p in sorted((root/'identity-records').glob('*/verified.json'))]
assert len(records)==expected,(len(records),expected)
save(root/'verified-identities.json',{'source_commit':proof['source_commit'],'board_revision':proof['board_revision'],'live_and_configure_records_preserved':len(records),'records':records,'physical_executed':False})
print(f'INSTALLED_CONFIGURE_AND_LIVE_IDENTITY_PASS={len(records)};MODE={mode}',flush=True)
