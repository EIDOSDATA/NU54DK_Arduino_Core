"""! @brief T13의 계획만 생성하며 probe·flash·실기 실행 기능은 제공하지 않습니다. """
from __future__ import annotations

import argparse
import json
from pathlib import Path

OUTPUT = Path(__file__).with_name('v04_t13_topologies.json')


def harness(profile):
    """! @brief 현재 C와 후속 S/U의 실제 point-to-point GPIO 대응입니다. """
    pins = ['P1.14', 'P1.10', *[f'P1.{pin:02}' for pin in range(4, 8)],
            *[f'P0.{pin:02}' for pin in range(4)], *[f'P2.{pin:02}' for pin in range(7)]]
    mapping = dict(zip(pins, pins))
    mapping['P1.06'], mapping['P1.07'] = 'P1.07', 'P1.06'
    if profile in ('S', 'U'):
        mapping['P1.04'], mapping['P1.05'] = 'P1.05', 'P1.04'
    if profile == 'S':
        mapping['P2.02'], mapping['P2.04'] = 'P2.04', 'P2.02'
    elif profile == 'U':
        mapping['P2.00'], mapping['P2.02'] = 'P2.02', 'P2.00'
        mapping['P2.04'], mapping['P2.05'] = 'P2.05', 'P2.04'
    elif profile != 'C':
        raise ValueError('unknown harness')
    return mapping


def endpoint(kind, instance, pins):
    """! @brief 생산 route validator에 전달할 bank/profile과 GPIO 신호를 고정합니다. """
    port = next(iter(pins.values()))[1]
    return {'kind': kind, 'instance': instance, 'bank': {'0': 'p0_flexible', '1': 'p1_flexible',
            '2': 'p2_dedicated20'}[port], 'profile': 'connector_fixture' if port == '2' or
            all(pin in ('P1.10', 'P1.14') for pin in pins.values()) else 'dap_uart_disabled', 'pins': pins}


def serial_link(profile, kind, instance, pins, peer_instance=None):
    """! @brief UART만 신호명을 반대로 대응하고 SPI/TWI는 같은 신호끼리 묶습니다. """
    mapping = harness(profile)
    opposite = {'txd': 'rxd', 'rxd': 'txd', 'rts': 'cts', 'cts': 'rts'} if kind == 'uarte' else {}
    peer_kind = {'uarte': 'uarte', 'spim': 'spis', 'twim': 'twis'}[kind]
    return {'a': endpoint(kind, instance, pins), 'b': endpoint(peer_kind, instance if peer_instance is None else peer_instance,
            {opposite.get(signal, signal): mapping[pin] for signal, pin in pins.items()}),
            'rate': 1000000 if kind == 'uarte' else 8000000 if kind == 'spim' else 400000,
            'buffer_bytes': 1024 if kind != 'twim' else 256,
            'buffers_per_direction': 2, 'guard_bytes_per_end': 16,
            'mode': '8N1/full-duplex' if kind == 'uarte' else 'mode0/msb/full-duplex' if kind == 'spim' else 'write-read/repeated-start/0x42'}


def uart(profile, instance, tx, rx, flow=None):
    """! @brief 2선 또는 명시한 RTS/CTS 4선 UART입니다. """
    pins = {'txd': tx, 'rxd': rx}
    if flow:
        pins.update(rts=flow[0], cts=flow[1])
    return serial_link(profile, 'uarte', instance, pins)


def spi(profile, instance, sck, mosi, miso, csn):
    """! @brief 물리 CS를 포함한 SPI pair입니다. """
    return serial_link(profile, 'spim', instance, dict(sck=sck, mosi=mosi, miso=miso, csn=csn))


def twi(profile, instance, sda='P1.10', scl='P1.14'):
    """! @brief PMIC와 분리한 0x42 전용 bus이며 외부 pull-up은 추가하지 않습니다. """
    return serial_link(profile, 'twim', instance, dict(sda=sda, scl=scl))


def plan():
    """! @brief 8개 동시 조합·두 후속 결선·단독 대상과 복구 경계를 확정합니다. """
    profile = 'S'
    u20 = lambda: uart(profile, 20, 'P1.04', 'P1.05')
    u21 = lambda: uart(profile, 21, 'P1.06', 'P1.07')
    u30 = lambda: uart(profile, 30, 'P0.00', 'P0.01', ('P0.02', 'P0.03'))
    spi20 = lambda: spi(profile, 20, 'P1.04', 'P1.06', 'P1.07', 'P1.05')
    entries = [
        ('C01', 'UART20+UART21+TWI22+UART30', [u20(), u21(), twi(profile, 22), u30()], []),
        ('C02', 'SPI20+UART21+UART30', [spi20(), uart(profile, 21, 'P1.14', 'P1.10'), u30()], []),
        ('C03', 'UART20+SPI30+TWI22', [u20(), spi(profile, 30, 'P0.00', 'P0.01', 'P0.02', 'P0.03'), twi(profile, 22)], []),
        ('C04', 'SPI20+TWI21+TWI30', [spi20(), twi(profile, 21), twi(profile, 30, 'P0.00', 'P0.01')], []),
        ('C05', 'SPI00+UART20+UART21+TWI22+UART30', [spi(profile, 0, 'P2.01', 'P2.02', 'P2.04', 'P2.05'),
                                                            u20(), u21(), twi(profile, 22), u30()], []),
        ('C06', 'I2S20+PWM20+SAADC+UART30', [u30()], [
            {'name': 'I2S20', 'a_pins': ['P1.04', 'P1.05', 'P1.06', 'P1.07'],
             'b_pins': ['P1.05', 'P1.04', 'P1.07', 'P1.06'],
             'a_resources': ['i2s20'], 'b_resources': ['i2s20'],
             'configuration': 'A master SCK=P1.04 LRCK=P1.05 TX=P1.06 RX=P1.07; B slave SCK=P1.05 LRCK=P1.04 TX=P1.06 RX=P1.07; 48kHz/32bit/stereo/256word/3slot'},
            {'name': 'PWM20 peer capture', 'a_pins': ['P1.14'], 'b_pins': ['P1.14'],
             'a_resources': ['gpiote20:0', 'dppi20:0', 'timer22'], 'b_resources': ['pwm20'],
             'configuration': 'B TOP1000/duty50/individual/32values/loop; A continuous edge count+timestamp'},
            {'name': 'SAADC', 'a_pins': [], 'b_pins': [], 'a_resources': ['saadc'], 'b_resources': [],
             'configuration': 'A internal VDD/AVDD scan 12bit 32samples x2 buffers; 2ms SAMPLE'}]),
        ('C07', 'QDEC20+UART20+UART21+UART30+SAADC', [u20(), u21(), u30()], [
            {'name': 'QDEC20', 'a_pins': ['P1.14', 'P1.10'], 'b_pins': ['P1.14', 'P1.10'],
             'a_resources': ['qdec20'], 'b_resources': ['cpu-phase-source'],
             'configuration': 'B 2ms/step continuously forward/reverse 100cycles; A 256us sample, 5ms hardware read'},
            {'name': 'SAADC', 'a_pins': [], 'b_pins': [], 'a_resources': ['saadc'], 'b_resources': [],
             'configuration': 'A internal VDD 12bit/32samples x2; 2ms SAMPLE'}]),
        ('C08', 'PDM20+PWM21+SAADC+UART30', [u30()], [
            {'name': 'PDM20 mono source', 'a_pins': ['P1.04', 'P1.05', 'P1.06'],
             'b_pins': ['P1.05', 'P1.04', 'P1.07', 'P1.06'],
             'a_resources': ['pdm20', 'gpio-cs'], 'b_resources': ['serial21'],
             'configuration': 'A PDM CLK=P1.04 DATA=P1.06 CS=P1.05; B SPIS21 SCK=P1.05 MISO=P1.07 CS=P1.04 MOSI=P1.06 input;16kHz/mono/1024samples x4/50percent source'},
            {'name': 'PWM21 peer capture', 'a_pins': ['P1.14'], 'b_pins': ['P1.14'],
             'a_resources': ['gpiote20:0', 'dppi20:0', 'timer22'], 'b_resources': ['pwm21'],
             'configuration': 'B TOP1000/duty25/individual/32values/loop; A continuous edge count+timestamp'},
            {'name': 'SAADC', 'a_pins': [], 'b_pins': [], 'a_resources': ['saadc'], 'b_resources': [],
             'configuration': 'A internal VDD 12bit/32samples x2; 2ms SAMPLE'}]),
    ]
    topologies = [{'id': identifier, 'name': name, 'harness': profile,
                   'duration_seconds': 3600 if identifier == 'C05' else 900,
                   'serial_links': links, 'other_components': components,
                   'execution_status': 'not-run', 'runner_status': 'implementation-required'}
                  for identifier, name, links, components in entries]
    standalone = []
    for kind, instances in (('uarte', (0, 20, 21, 22, 30)), ('spim', (0, 20, 21, 22, 30)),
                             ('spis', (0, 20, 21, 22, 30)), ('twim', (20, 21, 22, 30)), ('twis', (20, 21, 22, 30)),
                             ('saadc', (0,)), ('pwm', (20, 21, 22)), ('pdm', (20, 21)), ('i2s', (20,)), ('qdec', (20, 21))):
        for instance in instances:
            selected = 'U' if kind == 'uarte' and instance == 0 else 'S'
            row = {'kind': kind, 'instance': instance, 'duration_seconds': 180,
                   'harness': selected, 'execution_status': 'not-run'}
            if kind == 'uarte':
                if instance == 0:
                    link = uart(selected, 0, 'P2.02', 'P2.00', ('P2.05', 'P2.04'))
                elif instance == 30:
                    link = uart(selected, 30, 'P0.00', 'P0.01', ('P0.02', 'P0.03'))
                else:
                    link = uart(selected, instance, 'P1.04', 'P1.05', ('P1.06', 'P1.07'))
                row['serial_link'] = link
                row['measured_role'] = 'a'
            elif kind in ('spim', 'spis'):
                pins = ('P2.01', 'P2.02', 'P2.04', 'P2.05') if instance == 0 else (
                    ('P0.00', 'P0.01', 'P0.02', 'P0.03') if instance == 30 else ('P1.04', 'P1.06', 'P1.07', 'P1.05'))
                row['serial_link'] = spi(selected, instance, *pins)
                row['measured_role'] = 'a' if kind == 'spim' else 'b'
            elif kind in ('twim', 'twis'):
                row['serial_link'] = twi(selected, instance, *('P0.00', 'P0.01')) if instance == 30 else twi(selected, instance)
                row['measured_role'] = 'a' if kind == 'twim' else 'b'
            else:
                row['configuration'] = {'saadc': 'A internal VDD/AVDD 12bit scan/32samples x2/2ms',
                    'pwm': 'B P1.14→A P1.14; slot0/TOP1000/duty50/individual/32values/loop; A TIMER22 capture',
                    'pdm': 'A P1.04 clock/P1.06 data/P1.05 CS; B P1.05 clock/P1.07 data/P1.04 CS;16k/mono/1024samples x4',
                    'i2s': 'A master P1.04 SCK/P1.05 LRCK; B slave P1.05 SCK/P1.04 LRCK; TX P1.06/RX P1.07 both;48k/32bit/stereo/256word x3',
                    'qdec': 'B P1.14/P1.10 phases→A same pins;256us sample/2ms step/5ms read/100cycle direction change'}[kind]
            standalone.append(row)
    return {'schema_version': 1, 'status': 'planning-only', 'physical_executed': False,
            'board_revision': 'fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3',
            'harnesses': {key: harness(key) for key in ('C', 'S', 'U')}, 'common_ground': 'GND P2-30 ↔ P2-30',
            'current_harness': 'C', 'future_order': ['S', 'U'], 'standalone': standalone,
            'topologies': topologies, 'recovery_repetitions': 100, 'handover_repetitions': 100,
            'unexpected_loss_allowed': 0, 'unexpected_reset_allowed': 0, 'guard_bytes': 16,
            'continuous_measurement_minutes_sequential': 261,
            'manual_boundaries': ['C→S with both USB disconnected; confirm exact GPIO and DAP switches anew',
                                  'S→U with both USB disconnected; fresh wiring check',
                                  'System OFF fixture isolation/reconnect remains separate'],
            'not_covered': ['all pairwise resource/peripheral combinations', 'all UART ports with simultaneous hardware flow control',
                            'unsupported P2 dedicated21 bank', 'T13 physical execution', 'RC or release']}


def validate(data):
    """! @brief 두 보드의 중복 block/pin과 UART/SPI 출력 충돌을 사전 거부합니다. """
    assert data == plan(), 'canonical topology document mismatch'
    assert len(data['standalone']) == 32
    assert (sum(row['duration_seconds'] for row in data['standalone']) +
            sum(row['duration_seconds'] for row in data['topologies'])) // 60 == 261
    for topology in data['topologies']:
        for role in ('a', 'b'):
            pins, resources = set(), set()
            for link in topology['serial_links']:
                end = link[role]
                assert not pins.intersection(end['pins'].values()), 'duplicate physical GPIO'
                pins.update(end['pins'].values())
                block = 'serial' + str(end['instance'])
                assert block not in resources, 'duplicate serial block'
                resources.add(block)
            for component in topology['other_components']:
                assert not pins.intersection(component[role + '_pins']), 'stream/serial GPIO conflict'
                pins.update(component[role + '_pins'])
                assert not resources.intersection(component[role + '_resources']), 'stream/serial resource conflict'
                resources.update(component[role + '_resources'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    if args.write:
        OUTPUT.write_text(json.dumps(plan(), ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    validate(json.loads(OUTPUT.read_text(encoding='utf-8')))
    print('T13_PLAN_STATIC_PASS; 32 standalone; 8 combinations; physical_executed=0')
