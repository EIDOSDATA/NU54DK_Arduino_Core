"""! @brief SPI 역할 전환의 단일 변수 비교를 정식100회 자격과 분리합니다. """
from __future__ import annotations

import copy
from v04_protocol import ProtocolError

MODES = {'baseline': 1, '4mhz': 2, 'rxdelay0': 3}
MASK = 0xFFFFFFFF


def fixture(test, mode):
    """! @brief 같은 S 세 block과 GPIO를 유지하고 SPI 속도만 고정 선택으로 바꿉니다. """
    if (mode not in MODES or test['harness'] != 'S' or len(test['serial_links']) != 1 or
            any(test[key] for key in ('adc_channels', 'pwm_instance', 'pdm_instance', 'i2s'))):
        raise ProtocolError('T13 timing diagnostic requires a standalone S serial20/21/22 route')
    result = copy.deepcopy(test)
    link = result['serial_links'][0]
    for role in ('a', 'b'):
        endpoint = link[role]
        if endpoint['instance'] not in (20, 21, 22) or endpoint['kind'] not in ('uarte', 'spim', 'spis', 'twim', 'twis'):
            raise ProtocolError('T13 timing diagnostic block/kind unsupported')
    if link['a']['kind'] in ('spim', 'spis'):
        if link['rate'] != 8000000:
            raise ProtocolError('T13 timing diagnostic requires original SPI 8 MHz')
        link['rate'] = 4000000 if mode == '4mhz' else 8000000
    result['_spi_timing_mode'] = mode
    return result


def inspect(words, endpoint, rate, mode, role):
    """! @brief 실제 주파수 분주·RXDELAY·CS setup/hold가 선택한 비교 조건인지 확인합니다. """
    kind = {'spim': 2, 'spis': 3}[endpoint['kind']]
    if (len(words) != 20 or any(type(value) is not int or not 0 <= value <= MASK for value in words) or
            words[:4] != [MODES[mode], kind, endpoint['instance'], rate] or
            words[4:6] != [7 if kind == 2 else 2, 0] or words[17] == 0 or words[18:] != [role, 1]):
        raise ProtocolError('T13 SPI timing diagnostic configuration mismatch')
    expected = [16000000 // rate, 0 if mode == 'rxdelay0' else 1, 255] if kind == 2 else [MASK]*3
    if words[6:9] != expected:
        raise ProtocolError('T13 SPI timing diagnostic actual rate/RXDELAY/CSNDUR mismatch')
    return {'actual_rate_hz': 16000000 // words[6] if kind == 2 else None,
            'rxdelay': words[7] if kind == 2 else None, 'diagnostic_only': True}


def observe(devices, test, append, label):
    """! @brief 양쪽 raw를 먼저 보존한 뒤 적용된 타이밍을 판정합니다. """
    mode = test['_spi_timing_mode']
    if test['serial_links'][0]['a']['kind'] not in ('spim', 'spis'):
        return
    rows = []
    for device in devices:
        role = device.image['role']
        words = device.command(183, (0,), timeout=2)
        append(label + f'/role{role}/spi-timing', {'status': 'observation', 'words': words})
        rows.append((words, test['serial_links'][0]['a' if role == 1 else 'b'], role))
    for words, endpoint, role in rows:
        inspect(words, endpoint, test['serial_links'][0]['rate'], mode, role)
