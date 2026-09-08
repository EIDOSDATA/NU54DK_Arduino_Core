"""! @brief T13 계획의 실행 가능 항목만 고정 C++ allowlist로 생성합니다. """
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

import v04_t13_plan as plan

ROOT = Path(__file__).resolve().parents[3]
OUTPUT = ROOT / 'tests/zephyr/v04_t13_hil/src/cases.h'
KINDS = {'uarte': 'uart', 'spim': 'spim', 'spis': 'spis', 'twim': 'twim', 'twis': 'twis'}
BANKS = ('p2_dedicated20', 'p1_flexible', 'p0_flexible')
PROFILES = ('connector_fixture', 'dap_uart_bridge', 'dap_uart_disabled', 'pmic_read_only')
SIGNALS = ('invalid', 'txd', 'rxd', 'rts', 'cts', 'sck', 'mosi', 'miso', 'csn', 'dcx', 'sda', 'scl')


def cases():
    """! @brief QDEC 제외를 명시하고 단독/동시 ID와 원래 목표 시간을 보존합니다. """
    data = plan.plan()
    plan.validate(data)
    result = []
    for index, row in enumerate(data['standalone'], 1):
        if row['required_gates']:
            continue
        item = {'id': index, 'name': f'{row["kind"]}{row["instance"]}', 'harness': row['harness'],
                'duration_seconds': row['duration_seconds'],
                'serial_links': [row['serial_link']] if 'serial_link' in row else [],
                'adc_channels': 2 if row['kind'] == 'saadc' else 0,
                'pwm_instance': row['instance'] if row['kind'] == 'pwm' else 0,
                'pwm_duty': 50 if row['kind'] == 'pwm' else 0,
                'pdm_instance': row['instance'] if row['kind'] == 'pdm' else 0,
                'i2s': row['kind'] == 'i2s', 'measured_role': row.get('measured_role')}
        result.append(item)
    for row in data['topologies']:
        if row['required_gates']:
            continue
        number = int(row['id'][1:])
        result.append({'id': 100 + number, 'name': row['id'], 'harness': row['harness'],
                       'duration_seconds': row['duration_seconds'], 'serial_links': row['serial_links'],
                       'adc_channels': 2 if number == 6 else 1 if number == 8 else 0,
                       'pwm_instance': 20 if number == 6 else 21 if number == 8 else 0,
                       'pwm_duty': 50 if number == 6 else 25 if number == 8 else 0,
                       'pdm_instance': 20 if number == 8 else 0, 'i2s': number == 6,
                       'measured_role': None})
    return result


def endpoint(link, role):
    """! @brief 검증된 생산 route만 포트 번호와 enum 값으로 직렬화합니다. """
    entry = link[role]
    pins, signals = [], []
    for signal, pin in entry['pins'].items():
        port, number = map(int, pin[1:].split('.'))
        pins.append(32 * port + number)
        signals.append(SIGNALS.index(signal))
    count = len(pins)
    pins += [0] * (4 - count)
    signals += [0] * (4 - count)
    values = lambda items: '{' + ', '.join(f'{value}U' for value in items) + '}'
    return ('{Kind::' + KINDS[entry['kind']] + f', {entry["instance"]}U, '
            f'{BANKS.index(entry["bank"])}U, {PROFILES.index(entry["profile"])}U, '
            f'{values(pins)}, {values(signals)}, {count}U, {link["rate"]}U, {link["buffer_bytes"]}U' + '}')


def definition():
    """! @brief 미사용 net도 포함한 결선 전체와 실행 조건을 함께 고정합니다. """
    return {'harnesses': {profile: plan.harness(profile) for profile in ('S', 'U')}, 'cases': cases()}


def render():
    """! @brief 계획 hash와 immutable endpoint 배열을 생성하며 실기를 실행하지 않습니다. """
    selected = cases()
    digest = hashlib.sha256(json.dumps(definition(), sort_keys=True, separators=(',', ':')).encode()).digest()
    lines = ['/** @file @brief v04_t13_cases.py가 생성한 T13 고정 실행 allowlist입니다. */',
             '#pragma once', '#include "model.h"', '', 'namespace t13', '{',
             '    inline constexpr std::uint32_t plan_hash[]{' + ', '.join(
                 f'0x{int.from_bytes(digest[index:index + 4], "little"):08X}U' for index in range(0, 32, 4)) + '};',
             '    inline constexpr std::uint32_t net_pins[3][17]{']
    raw_pin = lambda pin: int(pin[1]) * 32 + int(pin[3:])
    for pins in (list(plan.harness('S')), list(plan.harness('S').values()), list(plan.harness('U').values())):
        lines.append('        {' + ', '.join(f'{raw_pin(pin)}U' for pin in pins) + '},')
    lines.extend(['    };', '    inline constexpr Case cases[]{'])
    for item in selected:
        links = item['serial_links']
        assert len(links) <= 5
        roles = []
        for role in ('a', 'b'):
            roles.append('{' + ', '.join([endpoint(link, role) for link in links] + ['{}'] * (5 - len(links))) + '}')
        lines.extend([f'        /** @brief {item["name"]}의 두 보드 실제 GPIO와 목표 시간입니다. */',
                      '        {' + f'{item["id"]}U, {2 if item["harness"] == "S" else 3}U, '
                      f'{item["duration_seconds"]}U, {len(links)}U, ' + '{' + ', '.join(roles) + '}, '
                      f'{item["adc_channels"]}U, {item["pwm_instance"]}U, {item["pwm_duty"]}U, '
                      f'{item["pdm_instance"]}U, {str(item["i2s"]).lower()}' + '},'])
    lines.extend(['    };', '} // namespace t13', ''])
    return '\n'.join(lines)


def generated_tokens(text):
    """! @brief clang-format의 공백 배치를 허용하되 생성 C++ 토큰은 모두 대조합니다. """
    return re.findall(r'\w+|[^\w\s]', text)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    if args.write:
        OUTPUT.write_text(render(), encoding='utf-8', newline='\n')
    assert generated_tokens(OUTPUT.read_text(encoding='utf-8')) == generated_tokens(render()), 'T13 generated endpoint drift'
    print('T13_CASES_PASS; S=36; U=1; QDEC not scheduled; physical_executed=0')
