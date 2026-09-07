"""! @brief PDM을 켜지 않고 확인된 clock 선의 LOW/HIGH 전달 위치를 진단합니다. """
from runtime import *
from contextlib import ExitStack
import v04_fixture as fixture
import v04_pair as pair
import v04_signal as signal
from v04_protocol import ProbeLocks

images = [pair.inspect_image(REPO, BUILD, role) for role in (1, 2)]
confirmation = json.loads((WORK / 'confirmation.json').read_text())
fixture.validate_confirmation(confirmation, images, UIDS, 440)
evidence = {'status': 'preflight', 'source': SOURCE, 'fixture_id': 440,
    'scope': 'Static confirmed clock GPIO LOW/HIGH mapping; PDM never started; no MHz functional claim',
    'confirmation_sha256': hashlib.sha256((WORK / 'confirmation.json').read_bytes()).hexdigest(),
    'swd_frequency_hz': 10000000, 'devices': [], 'results': []}
with pair.evidence_session(WORK / 'clock-path-probe.json', evidence) as journal:
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
            generator, receiver = devices[generator_role - 1], devices[2 - generator_role]
            clk_pin = 5 if generator_role == 1 else 4
            observed_clock_pin = 4 if generator_role == 1 else 5
            rx_data_pin = 7 if generator_role == 1 else 6
            snapshots = [{pin: device.target.read32(0x500D8280 + pin * 4) for pin in (4, 5, 6, 7)} for device in devices]
            out = receiver.target.read32(0x500D8200)
            assert all((value & 1) == 0 for snapshot in snapshots for value in snapshot.values())
            assert all(device.target.read32(address) == 0 for device in devices for address in (0x500D0500, 0x500D1500, 0x500C7500, 0x500DA510, 0x500DA514))
            try:
                for device in devices:
                    assert device.command(32, (440, 1, fixture.CONSENT, generator_role)) == [440, 10000]
                receiver.target.write32(0x500D8208, 1 << clk_pin)
                receiver.target.write32(0x500D8280 + 4 * clk_pin, 1)
                receiver.target.write32(0x500D8280 + 4 * rx_data_pin, snapshots[receiver.image['role'] - 1][rx_data_pin] & ~2)
                assert generator.command(34, signal.arguments_for('pdm', (20, 256, 25, 1, 0, 1))) == [0]
                for pin in (4, 5):
                    address = 0x500D8280 + 4 * pin
                    generator.target.write32(address, generator.target.read32(address) & ~2)
                for level in (0, 1, 0, 1):
                    receiver.target.write32(0x500D8204 if level else 0x500D8208, 1 << clk_pin)
                    receiver.target.flush()
                    rx_input = receiver.target.read32(0x500D820C)
                    gen_input = generator.target.read32(0x500D820C)
                    append({'id': f'CLOCK-LEVEL/{generator_role}/{len(evidence["results"])}',
                        'clock_output_role': receiver.image['role'], 'clock_output_pin': clk_pin,
                        'level_requested': level, 'driver_readback_level': (rx_input >> clk_pin) & 1,
                        'generator_role': generator_role, 'expected_generator_clock_pin': observed_clock_pin,
                        'generator_p1_04': (gen_input >> 4) & 1, 'generator_p1_05': (gen_input >> 5) & 1,
                        'generator_data_out': (generator.target.read32(0x500D8200) >> (6 if generator_role == 1 else 7)) & 1,
                        'receiver_data_level': (rx_input >> rx_data_pin) & 1,
                        'generator_clock_event': generator.target.read32(0x500DA100)})
            finally:
                receiver.target.write32(0x500D8280 + 4 * clk_pin, snapshots[receiver.image['role'] - 1][clk_pin])
                receiver.target.write32(0x500D8204 if out & (1 << clk_pin) else 0x500D8208, 1 << clk_pin)
                cleanup = []
                for device in devices:
                    try:
                        cleanup.append({'role': device.image['role'], 'result': device.command(33)})
                    except Exception as error:
                        cleanup.append({'role': device.image['role'], 'error': str(error)})
                restored = []
                for device, snapshot in zip(devices, snapshots):
                    for pin, value in snapshot.items():
                        device.target.write32(0x500D8280 + pin * 4, value)
                    device.target.flush()
                    restored.append({str(pin): device.target.read32(0x500D8280 + pin * 4) for pin in snapshot})
                append({'id': 'CLOCK-PROBE-CLEANUP', 'results': cleanup, 'pins_restored': restored})
                assert all(row.get('result') == [0] for row in cleanup)
                assert restored == [{str(pin): value for pin, value in snapshot.items()} for snapshot in snapshots]
        evidence['diagnostic_completed'] = True
        evidence['functional_pass_claimed'] = False
print('CLOCK_PATH_DIAGNOSTIC_CAPTURED;ALL_PINS_RESTORED;PDM_NOT_STARTED')
