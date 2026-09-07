"""! @brief USB 명령 1개 옵션만 바꾼 bounded 진단 campaign을 exact source에서 실행합니다. """
import datetime
import hashlib
import json
import logging
from pathlib import Path
import sys
from check_pc import REPO, WORK, SDK
logging.disable(logging.CRITICAL)
sys.path.insert(0, str(REPO / 'tests/hil/nu54dk'))
import v04_pair as pair
import v04_fixture as fixture
import v04_signal_run as runner
from v04_protocol import ProbeLocks
from pyocd.core.helpers import ConnectHelper

source = '0d7f3822fe0f1b564ef629613a048b433e8fdeee'
for gate in ('host', 'contract', 'package', 'docs', 'target'):
    assert json.loads((WORK / f'pwm-usb-{gate}.json').read_text())['exit_code'] == 0
images = [pair.inspect_image(REPO, Path('C:/pwq04'), role) for role in (1, 2)]
assert all(image['core_revision'] == source for image in images)
prior = json.loads((WORK / 'pwm-hardware-054d08f/confirmation-after-reconnect.json').read_text(encoding='utf-8'))
private = json.loads((WORK / 'current-probe-uids.private.json').read_text(encoding='utf-8-sig'))
uids = [private[key].lower() for key in prior['uid_sha256']]
assert set(uids).issubset({probe.unique_id.lower() for probe in ConnectHelper.get_all_connected_probes(blocking=False)})
folder = WORK / 'pwm-hardware-0d7f382'
folder.mkdir(exist_ok=True)
confirmation = fixture.confirmation_template(images, uids, 408)
for key, value in prior.items():
    if isinstance(value, bool) or key in ('confirmed_at_unix', 'confirmed_by', 'user_reply', 'reconnection_reply', 'prompt_scope', 'reconnection_scope'):
        confirmation[key] = value
confirmation['previous_core_revision'] = prior['core_revision']
confirmation['source_change_scope'] = 'HIL USB transport option only; same fixture 408 GPIO/voltage; timestamp retained'
fixture.validate_confirmation(confirmation, images, uids, 408)
with (folder / 'confirmation.json').open('x', encoding='utf-8') as stream:
    json.dump(confirmation, stream, ensure_ascii=False, indent=2)
(folder / 'images.json').write_text(json.dumps(images, indent=2, default=str) + '\n', encoding='utf-8')
diagnostic = {'observed_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'frequency_hz': 10000000, 'cmsis_dap.limit_packets': True, 'boards': []}
with ProbeLocks(uids):
    for uid, image in zip(uids, images):
        session = ConnectHelper.session_with_chosen_probe(unique_id=uid, target_override='nrf54l',
            frequency=10000000, blocking=False, no_config=True,
            options={'auto_unlock': False, 'connect_mode': 'attach', 'resume_on_disconnect': False,
                     'cmsis_dap.limit_packets': True})
        if session is None:
            raise RuntimeError('exact probe missing')
        with session:
            target = session.target
            cpuid = target.read32(0xE000ED00)
            assert cpuid == 0x411FD210
            assert session.probe._link._packet_count == 1
            diagnostic['boards'].append({'role': image['role'], 'uid_sha256': hashlib.sha256(uid.encode()).hexdigest(),
                'cpuid': f'0x{cpuid:08x}', 'state': target.get_state().name, 'backend_packets': 1})
with (folder / 'preflight-read.json').open('x', encoding='utf-8') as stream:
    json.dump(diagnostic, stream, indent=2)
print('Exact single-packet read passed for both boards; one new 10 MHz campaign.', flush=True)
try:
    result = runner.main(['--dut', uids[0], '--peer', uids[1], '--build-root', 'C:/pwq04',
        '--pyocd', str(SDK / 'opt/bin/Scripts/pyocd.exe'), '--swd-frequency-hz', '10000000',
        '--fixture', '408', '--pwm-capture', '--cmsis-dap-limit-packets', '--execute-fixture',
        '--confirmation', str(folder / 'confirmation.json'), '--evidence', str(folder / 'attempt1.json')])
except Exception as error:
    message = f'{type(error).__name__}: {error}'
    for uid in uids:
        message = message.replace(uid, '[exact UID redacted]')
    print(message, flush=True)
    sys.exit(1)
sys.exit(result)
