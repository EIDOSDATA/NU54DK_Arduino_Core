"""! @brief 결선 해제 보고 이후 지정한 두 보드의 USB/SWD와 PWM 유휴 상태를 읽습니다. """
from runtime import *
from datetime import datetime, timezone
from v04_protocol import ProbeLocks

rows=[]
with ProbeLocks(UIDS):
    for uid,digest in zip(UIDS,HASHES):
        session=ConnectHelper.session_with_chosen_probe(unique_id=uid,target_override='nrf54l',
            frequency=10000000,blocking=False,no_config=True,
            options={'auto_unlock':False,'connect_mode':'attach','resume_on_disconnect':False})
        assert session is not None
        with session:
            target=session.target
            cpuid=target.read32(0xE000ED00)
            assert cpuid==0x411FD210
            row={'uid_sha256':digest,'cpuid':hex(cpuid),'state':target.get_state().name,
                'pwm_enable':[target.read32(base+0x500) for base in (0x500D2000,0x500D3000,0x500D4000)],
                'p1_14_pin_cnf':target.read32(0x500D8280+14*4)}
            rows.append(row)
write_new(WORK/'preflight.json',{'at':datetime.now(timezone.utc).isoformat(),'flash':False,
    'reset':False,'frequency_hz':10000000,'devices':rows})
assert all(row['pwm_enable']==[0,0,0] for row in rows)
print('TWO_BOARDS_READ_ONLY_PREFLIGHT_PASS')
