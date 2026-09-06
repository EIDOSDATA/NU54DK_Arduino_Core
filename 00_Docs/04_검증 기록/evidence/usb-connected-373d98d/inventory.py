"""! @brief 재연결 뒤 exact 두 보드의 USB·COM·MSD 연결을 읽습니다. """
from runtime import *
from serial.tools import list_ports
from ble_pair_hil_common import discover_endpoint, validate_pair_identity
from m24_uarte_onboard import matching_port_names
from datetime import datetime, timezone

endpoints = [discover_endpoint(uid, None, 'auto', list_ports) for uid in UIDS]
validate_pair_identity(*endpoints)
records = []
for index, endpoint in enumerate(endpoints):
    records.append({'role': ['A/DUT/peripheral', 'B/peer/central'][index], 'probe_id_sha256': HASHES[index], 'msd_root': str(endpoint.volume.root), 'target_uart': endpoint.port_name, 'matching_vcoms': matching_port_names(list_ports.comports(), UIDS[index])})
result = {'created_at_utc': datetime.now(timezone.utc).isoformat(), 'user_confirmed': 'DAP UART connected; SWD connected; two USB; no inter-board wiring', 'boards': records, 'flash_executed': False}
write_new(WORK / 'usb-inventory.json', result)
print(json.dumps(result, ensure_ascii=False))
