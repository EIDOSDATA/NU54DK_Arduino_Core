"""! @brief clock/gate 네 핀을 하나씩만 구동하고 나머지 입력 pull-down으로 net 분리를 진단합니다. """
from runtime import *
import time
from contextlib import ExitStack
import v04_fixture as fixture
import v04_pair as pair
from v04_protocol import ProbeLocks

images = [pair.inspect_image(REPO, BUILD, role) for role in (1, 2)]
confirmation = json.loads((WORK / 'confirmation.json').read_text())
fixture.validate_confirmation(confirmation, images, UIDS, 440)
evidence = {'status': 'preflight', 'source': SOURCE, 'fixture_id': 440,
    'scope': 'One clock/gate output at a time; all other clock/gate pins input pull-down; PDM disabled',
    'confirmation_sha256': hashlib.sha256((WORK / 'confirmation.json').read_bytes()).hexdigest(),
    'swd_frequency_hz': 10000000, 'devices': [], 'results': [], 'functional_pass_claimed': False, 'settling_seconds': 0.01, 'samples_per_level': 3}
with pair.evidence_session(WORK / 'net-isolation-settled.json', evidence) as journal:
    with ProbeLocks(UIDS), ExitStack() as stack:
        devices = []
        for uid, digest, image in zip(UIDS, HASHES, images):
            device, flash = pair.boot_exact(stack, ConnectHelper, BUNDLE / 'opt/bin/Scripts/pyocd.exe', uid, image, 10000000)
            devices.append(device)
            evidence['devices'].append({'role': image['role'], 'uid_sha256': digest, 'hex_sha256': image['sha256'], 'flash': flash})
        write_new(WORK / 'net-startup-pins.json', {'source': SOURCE, 'devices': [{'role': device.image['role'], 'pin_cnf': {str(pin): device.target.read32(0x500D8280 + pin * 4) for pin in (4, 5, 6, 7)}} for device in devices], 'capture': 'passive read after settled diagnostic canonical boot'})
        originals = [{pin: device.target.read32(0x500D8280 + 4 * pin) for pin in (4, 5)} for device in devices]
        outputs = [device.target.read32(0x500D8200) for device in devices]
        assert all(value & 1 == 0 for original in originals for value in original.values())
        assert all(device.target.read32(address) == 0 for device in devices for address in (0x500D0500, 0x500D1500, 0x500C7500, 0x500DA510, 0x500DA514))

        def append(row):
            evidence['results'].append(row)
            journal.write(json.dumps(row) + '\n')
            journal.flush()

        try:
            for device in devices:
                assert device.command(32, (440, 1, fixture.CONSENT, 1)) == [440, 10000]
                for pin in (4, 5):
                    device.target.write32(0x500D8280 + 4 * pin, 4)
            for source in devices:
                for pin in (4, 5):
                    source.target.write32(0x500D8208, 1 << pin)
                    source.target.write32(0x500D8280 + 4 * pin, 1)
                    for level in (0, 1):
                        source.target.write32(0x500D8204 if level else 0x500D8208, 1 << pin)
                        source.target.flush()
                        for sample in range(3):
                            time.sleep(0.01)
                            observed = []
                            for device in devices:
                                raw = device.target.read32(0x500D820C)
                                observed.append({'role': device.image['role'], 'p1_04': (raw >> 4) & 1, 'p1_05': (raw >> 5) & 1,
                                    'pin_cnf': {str(p): device.target.read32(0x500D8280 + 4 * p) for p in (4, 5)}})
                            append({'id': f'NET/{source.image["role"]}/{pin}/{level}', 'driver_role': source.image['role'],
                                'driver_pin': pin, 'level': level, 'sample': sample, 'observed': observed})
                    source.target.write32(0x500D8280 + 4 * pin, 4)
        finally:
            for device in devices:
                for pin in (4, 5):
                    device.target.write32(0x500D8280 + 4 * pin, 4)
            cleanup = []
            for device, original, output in zip(devices, originals, outputs):
                for pin in (4, 5):
                    device.target.write32(0x500D8204 if output & (1 << pin) else 0x500D8208, 1 << pin)
                    device.target.write32(0x500D8280 + 4 * pin, original[pin])
                device.target.flush()
                cleanup.append({'role': device.image['role'], 'result': device.command(33),
                    'pins_restored': {str(pin): device.target.read32(0x500D8280 + 4 * pin) for pin in (4, 5)}})
            append({'id': 'NET-CLEANUP', 'results': cleanup})
            assert all(row['result'] == [0] for row in cleanup)
            assert [row['pins_restored'] for row in cleanup] == [{str(pin): value for pin, value in original.items()} for original in originals]
        evidence['diagnostic_completed'] = True
print('CLOCK_GATE_NET_ISOLATION_CAPTURED;PINS_RESTORED;PDM_DISABLED')
