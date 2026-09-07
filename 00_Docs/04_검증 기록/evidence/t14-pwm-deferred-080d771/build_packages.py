from pathlib import Path
import hashlib,json,subprocess,sys
repo=Path(r'C:\Users\eidos\GitHub\NU54DK_Arduino_Core');work=Path(__file__).parent
commit=sys.argv[1];prefix=sys.argv[2] if len(sys.argv)>2 else 'final-package'
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()==commit
assert not subprocess.check_output(['git','status','--porcelain'],cwd=repo,text=True).strip()
outputs=[]
for suffix in ['a','b']:
    output=work/(prefix+'-'+suffix);assert not output.exists(),output
    result=subprocess.run([sys.executable,str(repo/'packaging/boards-manager/nu54_package.py'),'build','--repo-root',str(repo),'--output-dir',str(output),'--version','0.0.90','--commit',commit,'--update-index'],cwd=repo)
    assert result.returncode==0
    outputs.append(output)
assert {p.name for p in outputs[0].iterdir()}=={p.name for p in outputs[1].iterdir()}
records={}
for path in outputs[0].iterdir():
    assert path.read_bytes()==(outputs[1]/path.name).read_bytes(),path
    records[path.name]={'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size}
manifest=json.loads(next(outputs[0].glob('*.release-manifest.json')).read_text(encoding='utf-8'))
assert manifest['core_revision']==commit
(work/(prefix+'-reproducibility.json')).write_text(json.dumps({'source_commit':commit,'board_revision':manifest['board_revision'],'package_version':'0.0.90','independent_outputs':[str(p) for p in outputs],'byte_identical':True,'files':records,'physical_executed':False,'published':False},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('FINAL_PACKAGE_REPRODUCIBILITY_PASS='+str(len(records)),flush=True)
