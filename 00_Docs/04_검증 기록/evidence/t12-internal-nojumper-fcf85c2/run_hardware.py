"""! @brief 결선 해제 승인 범위에서 두 exact 보드의 PWM 무점퍼 회귀를 실행합니다. """
from runtime import *
from datetime import datetime, timezone
import time
import v04_nojumper as hil
from v04_pair import evidence_session
from v04_protocol import ProbeLocks
from m24_uarte_onboard import flash_image, sha256_file

image=hil.inspect_image(REPO,BUILD)
assert image['source']==SOURCE
vectors=list(hil.time_vectors()) + list(hil.adc_vectors()) + list(hil.timer_vectors()) + list(hil.event_vectors()) + list(hil.bridge_vectors())
vectors += [(1, instance, flags, 2, 1000, 100)
            for instance in (20,21,22) for flags in (1,3,33,35)]

evidence={'source':SOURCE,'at':datetime.now(timezone.utc).isoformat(),'swd_frequency_hz':10000000,
          'wiring':'user-confirmed no inter-board jumpers','vectors_per_board':len(vectors),'plan':[list(v) for v in vectors],
          'image':{key:str(value) if isinstance(value,Path) else value for key,value in image.items()},
          'devices':[]}
with evidence_session(WORK/'hardware-attempt1.json',evidence) as journal, ProbeLocks(UIDS):
    for uid,digest in zip(UIDS,HASHES):
        assert sha256_file(image['path'])==image['hex_sha256']
        row={'uid_sha256':digest,'passed':0,'flash':None}
        evidence['devices'].append(row)
        row['flash']=flash_image(BUNDLE/'opt/bin/Scripts/pyocd.exe',uid,image['path'],120,10000000)
        session=ConnectHelper.session_with_chosen_probe(unique_id=uid,target_override='nrf54l',
            frequency=10000000,blocking=False,no_config=True,
            options={'auto_unlock':False,'connect_mode':'attach','resume_on_disconnect':False})
        assert session is not None
        with session:
            target=session.target
            target.reset_and_halt()
            assert target.get_state().name=='HALTED' and target.read32(0xE000ED00)==0x411FD210
            for name in ('nojumper_request','nojumper_response','nojumper_ready'):
                target.write32(image['symbols'][name],0)
            target.flush()
            target.resume()
            deadline=time.monotonic()+5
            while target.read32(image['symbols']['nojumper_ready'])!=hil.MAGIC:
                assert time.monotonic()<deadline, 'nojumper boot timeout'
                time.sleep(0.01)
            device=hil.Device(target,image)
            row['initial_identity']=device.identity()
            row['initial_pin']=target.read32(0x500D8280+14*4)
            row['initial_resources']=hil.read_postflight(device)
            assert row['initial_resources']['dppi_channels']==[0,0,0,0]
            assert row['initial_resources']['saadc_enable']==0
            row['initial_egu_inten']=[target.read32(base+0x300) for base in (0x50087000,0x500C9000)]
            assert row['initial_egu_inten']==[0,0]
            def append(record):
                record.update(uid_sha256=digest,at=datetime.now(timezone.utc).isoformat())
                journal.write(json.dumps(record)+'\n')
                journal.flush()
            try:
                for vector in vectors:
                    row['pending_vector']=list(vector)
                    device.command(vector,append)
                    row.pop('pending_vector')
                    row['passed']+=1
                    if row['passed']%20==0:
                        print('INTERNAL_HIL_PROGRESS',digest[:12],row['passed'],flush=True)
                row['postflight']=hil.read_postflight(device)
                assert row['postflight']['pwm_enable']==[0,0,0]
                assert row['postflight']['dppi_channels']==[0,0,0,0]
                assert row['postflight']['saadc_enable']==0
                assert row['postflight']['p1_14_pin_cnf']==row['initial_pin']
                assert row['postflight']['ready'][3]==0
            except BaseException:
                try:
                    row['failure_snapshot']=hil.read_postflight(device)
                    target.reset_and_halt()
                    row['controlled_failure_cleanup']={'method':'reset-and-halt after recorded failure',
                        'pwm_enable':[target.read32(base+0x500) for base in (0x500D2000,0x500D3000,0x500D4000)],
                        'state':target.get_state().name,'saadc_enable':target.read32(0x500D5500),'dppi_channels':[target.read32(base+0x500) for base in (0x50042000,0x50082000,0x500C2000,0x50102000)]}
                except BaseException as cleanup_error:
                    row['cleanup_error']=str(cleanup_error)
                raise
print('TWO_BOARD_INTERNAL_NOJUMPER_PASS',sum(row['passed'] for row in evidence['devices']))
