"""! @brief 확인된 440 data 선의 정적 LOW/HIGH 전달을 두 역할에서 진단합니다. """
from runtime import *
from contextlib import ExitStack
from datetime import datetime, timezone
import v04_fixture as fixture
import v04_pair as pair
import v04_signal as signal
from v04_protocol import ProbeLocks

images = [pair.inspect_image(REPO, BUILD, role) for role in (1, 2)]
confirmation = json.loads((WORK / 'confirmation.json').read_text())
fixture.validate_confirmation(confirmation, images, UIDS, 440)
evidence = {'status': 'preflight', 'core_revision': SOURCE, 'fixture_id': 440,
    'scope': 'Static data wire LOW/HIGH diagnostic only; no PDM clock/start or functional sweep',
    'confirmation_sha256': hashlib.sha256((WORK / 'confirmation.json').read_bytes()).hexdigest(),
    'swd_frequency_hz': 10000000, 'devices': [], 'results': []}
with pair.evidence_session(WORK / 'static-probe.json', evidence) as journal:
    with ProbeLocks(UIDS), ExitStack() as stack:
        devices = []
        for uid, digest, image in zip(UIDS, HASHES, images):
            device, flash = pair.boot_exact(stack, ConnectHelper, BUNDLE / 'opt/bin/Scripts/pyocd.exe', uid, image, 10000000)
            devices.append(device)
            evidence['devices'].append({'role': image['role'], 'uid_sha256': digest,
                'hex_sha256': image['sha256'], 'elf_sha256': image['elf_sha256'], 'flash': flash})

        def append(row):
            evidence['results'].append(row)
            journal.write(json.dumps(row) + '\n')
            journal.flush()

        for generator_role in (1, 2):
            generator = devices[generator_role - 1]
            receiver = devices[2 - generator_role]
            rx_pin = 7 if generator_role == 1 else 6
            rx_cnf = 0x500D8280 + 4 * rx_pin
            for density, expected in ((25, 0), (75, 1)):
                original = receiver.target.read32(rx_cnf)
                assert original & 1 == 0
                try:
                    for device in devices:
                        assert device.command(32, (440, 1, fixture.CONSENT, generator_role)) == [440, 10000]
                    assert generator.command(34, signal.arguments_for('pdm', (20, 256, density, 1, 0, 1))) == [0]
                    signal.wait_status(generator, lambda words: words[2] == 1)
                    # Input buffer alone is enabled on the confirmed receiver data pin; DIR remains input.
                    receiver.target.write32(rx_cnf, original & ~2)
                    receiver.target.flush()
                    setup = {name: generator.target.read32(address) for name, address in
                        [('CONFIG0', 0x500DA510), ('CONFIG1', 0x500DA514), ('PUBLISH_IN0', 0x500DA180),
                         ('SUBSCRIBE_OUT1', 0x500DA084), ('DPPI20_CHEN', 0x500C2500),
                         ('GPIO1_IN', 0x500D820C), ('GPIO1_OUT', 0x500D8200)]}
                    levels = [(receiver.target.read32(0x500D820C) >> rx_pin) & 1 for _ in range(8)]
                    append({'id': f'STATIC-DATA/{generator_role}/{density}', 'status': 'passed' if levels == [expected] * 8 else 'failed',
                        'generator_role': generator_role, 'receiver_role': receiver.image['role'], 'receiver_pin': rx_pin,
                        'expected': expected, 'levels': levels, 'generator_setup': setup,
                        'receiver_original_pin_cnf': original, 'receiver_read_pin_cnf': receiver.target.read32(rx_cnf),
                        'pdm_start_executed': False})
                finally:
                    cleanup = []
                    for device in devices:
                        try:
                            cleanup.append({'role': device.image['role'], 'result': device.command(33)})
                        except Exception as error:
                            cleanup.append({'role': device.image['role'], 'error': str(error)})
                    receiver.target.write32(rx_cnf, original)
                    receiver.target.flush()
                    append({'id': 'STATIC-CLEANUP', 'results': cleanup,
                        'receiver_restored_pin_cnf': receiver.target.read32(rx_cnf)})
                    assert all(item.get('result') == [0] for item in cleanup)
                    assert receiver.target.read32(rx_cnf) == original
        assert all(row['status'] == 'passed' for row in evidence['results'] if row['id'].startswith('STATIC-DATA/'))
print('STATIC_DATA_LOW_HIGH_BOTH_ROLES_PASS=4;PDM_FUNCTIONAL_PASS_NOT_CLAIMED')
