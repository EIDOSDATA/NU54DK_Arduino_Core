"""! @brief 완료된 canonical target 전부의 실제 application 설정과 산출물을 색인합니다. """
import hashlib,json,re,sys
from pathlib import Path
import yaml
work=Path(__file__).parent
repo=Path(r'C:\Users\eidos\GitHub\NU54DK_Arduino_Core')
root=Path(sys.argv[1] if len(sys.argv)>1 else r'C:\r13f')
expected=int(sys.argv[2]) if len(sys.argv)>2 else 60
evidence=json.loads((root/'m12-build-evidence.json').read_text(encoding='utf-8'))
assert evidence['status']=='passed' and len(evidence['scenarios'])==expected
def file_record(path):return {'path':str(path),'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
records=[]
for scenario in evidence['scenarios']:
    location=root/'nrf54l15dk_nrf54l15_cpuapp_nu54dk/zephyr_gnu'/scenario
    elfs=list(location.rglob('zephyr.elf'));assert len(elfs)==1,(scenario,elfs)
    elf=elfs[0];app=elf.parent.parent
    config=elf.with_name('.config')
    values=sorted(line for line in config.read_text(encoding='utf-8').splitlines() if line.startswith('CONFIG_') or re.match(r'# CONFIG_\w+ is not set$',line))
    assert len(values)>100,scenario
    commands_path=app/'compile_commands.json'
    commands=json.loads(commands_path.read_text(encoding='utf-8'))
    sources=sorted(str(c['file']).replace('\\','/').replace(root.as_posix(),'<BUILD>') for c in commands)
    build_log=location/'build.log'
    text=build_log.read_text(encoding='utf-8',errors='replace')
    memory={n:int(v)*{'B':1,'KB':1024,'MB':1048576}[u] for n,v,u in re.findall(r'^\s*(FLASH|RAM):\s*(\d+)\s*(B|KB|MB)',text,re.M)}
    identities=[]
    for p in app.rglob('*.yml'):
        if 'nucode_arduino_core:' in p.read_text(encoding='utf-8',errors='replace'):
            identities.append({'file':file_record(p),'identity':yaml.safe_load(p.read_text(encoding='utf-8'))['nucode_arduino_core']})
    for p in app.rglob('*.yaml'):
        if 'nucode_arduino_core:' in p.read_text(encoding='utf-8',errors='replace'):
            identities.append({'file':file_record(p),'identity':yaml.safe_load(p.read_text(encoding='utf-8'))['nucode_arduino_core']})
    core_enabled='CONFIG_NUCODE_ARDUINO_CORE=y' in values
    assert bool(identities)==core_enabled,(scenario,'build record and Core selection disagree')
    repository_sources={}
    for command in commands:
        p=Path(command['file'])
        if not p.is_absolute():p=Path(command['directory'])/p
        p=p.resolve()
        if p.is_relative_to(repo):repository_sources[p.relative_to(repo).as_posix()]=hashlib.sha256(p.read_bytes()).hexdigest()
    assert repository_sources,(scenario,'repository sources missing')
    assert memory.keys()>={'FLASH','RAM'},(scenario,memory)
    artifacts={name:file_record(elf.with_name(name)) for name in ['zephyr.elf','zephyr.hex','.config']}
    records.append({'scenario':scenario,'status':'built-not-run','artifacts':artifacts,'identity_records':identities,'core_module_enabled':core_enabled,'identity_scope':'Core build record' if core_enabled else 'standalone contract: exact clean Git source plus compiled source hashes','repository_compiled_sources_sha256':repository_sources,'config_symbols':len(values),'normalized_config_sha256':hashlib.sha256('\n'.join(values).encode()).hexdigest(),'source_count':len(sources),'source_membership_sha256':hashlib.sha256('\n'.join(sources).encode()).hexdigest(),'memory_bytes':memory,'build_log':file_record(build_log),'compile_commands':file_record(commands_path)})
output=work/(root.name+'-artifact-index.json')
output.write_text(json.dumps({'build_root':str(root),'physical_executed':False,'canonical_evidence':file_record(root/'m12-build-evidence.json'),'targets':records},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('TARGET_ARTIFACT_INDEX_PASS='+str(len(records)))
