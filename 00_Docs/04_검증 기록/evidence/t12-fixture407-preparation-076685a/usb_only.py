"""! @brief Host 차단 중 두 보드 USB만 열거하며 flash/reset/SWD 명령은 실행하지 않습니다. """
from runtime import *
from datetime import datetime, timezone
from serial.tools import list_ports
from ble_pair_hil_common import discover_endpoint, validate_pair_identity
from m24_uarte_onboard import matching_port_names

endpoints = [discover_endpoint(uid, None, 'auto', list_ports) for uid in UIDS]
validate_pair_identity(*endpoints)
evidence = {'checked_at_utc': datetime.now(timezone.utc).isoformat(), 'fixture_id': 407,
    'flash_executed': False, 'reset_executed': False, 'swd_target_commands_executed': False, 'boards': []}
for role, endpoint, uid, digest in zip((1, 2), endpoints, UIDS, HASHES):
    evidence['boards'].append({'role': role, 'uid_sha256': digest, 'msd_root': str(endpoint.volume.root),
        'target_uart': endpoint.port_name, 'matching_vcoms': matching_port_names(list_ports.comports(), uid)})
write_new(WORK / 'usb-only-inventory.json', evidence)
print('USB_PAIR_INVENTORY_PASS=2;NO_FLASH_RESET_OR_TARGET_COMMAND')
