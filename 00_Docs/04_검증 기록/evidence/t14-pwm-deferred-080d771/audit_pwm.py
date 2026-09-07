from pathlib import Path
import hashlib,json,sys
work=Path(__file__).resolve().parent
sys.path.insert(0,'C:/Users/eidos/GitHub/NU54DK_Arduino_Core/tests/hil/nu54dk')
import v04_nojumper as hil
summary=json.loads((work/'hardware-attempt1.json').read_text(encoding='utf-8'))
records=[json.loads(line) for line in (work/'hardware-attempt1.json.jsonl').read_text(encoding='utf-8').splitlines()]
assert len(records)==1944
for record in records:
    hil.validate_reply(record['request'],record['reply'])
boards=[]
for device in summary['devices']:
    rows=[row for row in records if row['uid_sha256']==device['uid_sha256']]
    vectors=list(hil.pwm_vectors())+[(1,i,f,2,1000,100) for i in (20,21,22) for f in (1,3,33,35)]
    assert [row['request'][2:] for row in rows]==[list(v) for v in vectors]
    assert [row['request'][0] for row in rows]==list(range(1,973))
    assert len({row['request'][1] for row in rows})==1
    assert device['postflight']['pwm_enable']==[0,0,0] and device['postflight']['ready'][2:]==[972,0]
    assert device['postflight']['p1_14_pin_cnf']==device['initial_pin']==2
    assert device['postflight']['dppi20_channel0']==0
    cancelled=[r for r in rows if r['request'][4]&1 and not r['request'][4]&2]
    boards.append({'uid_sha256':device['uid_sha256'],'commands':len(rows),'configure_play_stop_cycles':sum(r['request'][7] for r in rows),'cancelled_without_dma_cycles':sum(r['request'][7] for r in cancelled),'reported_stop_us_range':[min(r['reply'][23] for r in rows),max(r['reply'][23] for r in rows)],'cancel_reported_stop_us_range':[min(r['reply'][23] for r in cancelled),max(r['reply'][23] for r in cancelled)]})
data={'source':summary['source'],'status':'passed','swd_hz':10000000,'commands':len(records),'boards':boards,'external_waveform_observed':False,'repeat_statistics_note':'every cycle is checked on device; SWD record reports final cycle latch and stop duration within each command','journal_sha256':hashlib.sha256((work/'hardware-attempt1.json.jsonl').read_bytes()).hexdigest()}
(work/'hardware-pwm-audit.json').write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')
print(json.dumps(data))
