from runtime import *
from v04_protocol import ProbeLocks
records=[]
with ProbeLocks(UIDS):
    for uid,digest in zip(UIDS,HASHES):
        session=ConnectHelper.session_with_chosen_probe(unique_id=uid,target_override='nrf54l',frequency=10000000,blocking=False,no_config=True,options={'auto_unlock':False,'connect_mode':'attach','resume_on_disconnect':False})
        with session:
            target=session.target
            records.append({'uid_sha256':digest,'state':target.get_state().name,'dppi_channels':[target.read32(base+0x500) for base in (0x50042000,0x50082000,0x500C2000,0x50102000)],'egu_inten':[target.read32(base+0x300) for base in (0x50087000,0x500C9000)]})
write_new(WORK/'internal-resource-preflight2.json',{'source':SOURCE,'reset':False,'flash':False,'swd_hz':10000000,'records':records})
print(json.dumps(records))
