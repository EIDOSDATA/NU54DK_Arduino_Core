"""! @brief 같은 exact image에서 PDM gate 준비 순서와 SPIS 상태를 비교합니다. """
from runtime import *
from contextlib import ExitStack
import v04_pair as pair
import v04_fixture as fixture
import v04_signal as signal
from v04_protocol import ProbeLocks

images = [pair.inspect_image(REPO, BUILD, role) for role in (1, 2)]
confirmation = json.loads((WORK / 'confirmation.json').read_text())
fixture.validate_confirmation(confirmation, images, UIDS, 440)
evidence = {'status': 'preflight', 'source': SOURCE, 'fixture_id': 440,
    'scope': 'Diagnostic prepare order comparison; canonical commands and unchanged PCM capture',
    'swd_frequency_hz': 10000000, 'results': [], 'devices': []}
with pair.evidence_session(WORK / 'mono-order-diagnostic.json', evidence) as journal:
    with ProbeLocks(UIDS), ExitStack() as stack:
        devices = []
        for uid, image in zip(UIDS, images):
            device, flash = pair.boot_exact(stack, ConnectHelper, BUNDLE / 'opt/bin/Scripts/pyocd.exe', uid, image, 10000000)
            devices.append(device)
            evidence['devices'].append({'role': image['role'], 'flash': flash, 'hex_sha256': image['sha256']})
        def append(row):
            evidence['results'].append(row)
            journal.write(json.dumps(row) + '\n')
            journal.flush()
        def snapshot(label):
            append({'id': label, 'registers': [{str(hex(a)): d.target.read32(a) for a in
                (0x500C7400, 0x500C7440, 0x500C7500, 0x500C7554, 0x500C755C,
                 0x500C75C0, 0x500C7600, 0x500C7604, 0x500C7608, 0x500C760C,
                 0x500D820C, 0x500D8290, 0x500D8294)} for d in devices]})
        for receiver_first in (False, True):
            for density in (25, 50, 75):
                fixture.validate_confirmation(confirmation, images, UIDS, 440)
                vector = (20, 256, density, 0, 0, 1)
                args = signal.arguments_for('pdm', vector)
                try:
                    for d in devices:
                        assert d.command(32, (440, 1, fixture.CONSENT, 2)) == [440, 10000]
                    order = devices if receiver_first else devices[::-1]
                    for d in order:
                        assert d.command(34, args) == [0]
                        signal.wait_status(d, lambda words: words[2] == 1)
                        snapshot(f'PREPARE/{receiver_first}/{density}/{d.image["role"]}')
                    assert devices[0].command(35) == [0]
                    status = signal.wait_status(devices[0], lambda words: words[3] == 1)
                    samples = signal.read_u16(devices[0], 256)
                    snapshot(f'COMPLETE/{receiver_first}/{density}')
                    append({'id': 'CAPTURE', 'receiver_first': receiver_first, 'density': density,
                        'status_words': status, 'samples': samples, 'mean': sum(samples) / len(samples)})
                finally:
                    append({'id': 'CLEANUP', 'results': [d.command(33) for d in devices]})
print('MONO_PREPARE_ORDER_DIAGNOSTIC_CAPTURED')
