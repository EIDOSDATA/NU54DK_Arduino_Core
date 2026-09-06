"""! @brief 사용자 결선 확인을 exact image 확인서와 읽기 전용 USB 증거에 연결합니다. """
from runtime import *
from datetime import datetime, timezone
from serial.tools import list_ports
from ble_pair_hil_common import discover_endpoint, validate_pair_identity
from m24_uarte_onboard import matching_port_names
import v04_fixture as fixture
import v04_pair as pair
import v04_fixture_run as runner

images = [pair.inspect_image(REPO, BUILD, role) for role in (1, 2)]
assert all(image['core_revision'] == SOURCE for image in images)
endpoints = [discover_endpoint(uid, None, 'auto', list_ports) for uid in UIDS]
validate_pair_identity(*endpoints)
inventory = {'created_at_utc': datetime.now(timezone.utc).isoformat(), 'flash_executed': False, 'boards': []}
for role, endpoint, uid, digest in zip((1, 2), endpoints, UIDS, HASHES):
    inventory['boards'].append({'role': role, 'uid_sha256': digest, 'msd_root': str(endpoint.volume.root), 'target_uart': endpoint.port_name, 'matching_vcoms': matching_port_names(list_ports.comports(), uid)})
write_new(WORK / 'usb-inventory.json', inventory)
checkpoint = json.loads((WORK / 'checkpoint.json').read_text(encoding='utf-8'))
confirmation = fixture.confirmation_template(images, UIDS, 301)
for key, value in list(confirmation.items()):
    if type(value) is bool:
        confirmation[key] = True
confirmation['confirmed_at_unix'] = datetime.fromisoformat(checkpoint['user_confirmation_recorded_at_utc']).timestamp()
confirmation['confirmed_by'] = 'Project owner (user confirmation in this task)'
fixture.validate_confirmation(confirmation, images, UIDS, 301)
write_new(WORK / 'confirmation.json', confirmation)
write_new(WORK / 'exact-images.json', [{key: str(value) if isinstance(value, Path) else value for key, value in image.items()} for image in images])
raise SystemExit(runner.main(['--dut', UIDS[0], '--peer', UIDS[1], '--build-root', str(BUILD), '--pyocd', str(BUNDLE / 'opt/bin/Scripts/pyocd.exe'), '--fixture', '301', '--swd-frequency-hz', '10000000']))
