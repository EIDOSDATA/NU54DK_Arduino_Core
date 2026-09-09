"""! @brief I2S SDIN 패드 전이와 DMA 수신을 같은 버퍼 경계에서 진단합니다. """
from __future__ import annotations

import copy

from v04_protocol import ProtocolError

MASK = 0xFFFFFFFF
EDGE_FAILURE_NOISE_BUDGET = 8


def fixture(test, mode=1):
    """! @brief 고정 S의 단독 i2s20을 원래/교환 data route 진단 case로 복사합니다. """
    if (test['harness'] != 'S' or test['id'] != 30 or test['name'] != 'i2s20' or
            test['serial_links'] or test['adc_channels'] or test['pwm_instance'] or
            test['pdm_instance'] or not test['i2s'] or type(mode) is not int or mode not in (1, 2)):
        raise ProtocolError('T13 I2S edge diagnostic requires standalone i2s20')
    selected = copy.deepcopy(test)
    selected['_i2s_edge_diagnostic'] = mode
    return selected


def inspect(pages, role, mode=1):
    """! @brief 정상 반복 뒤 계수 일치와 endpoint·자원 정리를 모두 요구합니다. """
    if (role not in (1, 2) or mode not in (1, 2) or len(pages) != 3 or
            any(len(page) != 20 for page in pages) or
            any(type(value) is not int or not 0 <= value <= MASK
                for page in pages for value in page)):
        raise ProtocolError('T13 I2S edge diagnostic snapshot shape mismatch')
    summary, first, trace = pages
    if (summary[:5] != [0x49324530, role, mode, 0, 0] or summary[13] != 0 or
            summary[17] != 0 or summary[18] != summary[19] or
            first[:3] != [0x49324531, role, 0] or first[12:15] != [0, 0, 0] or
            first[18:20] != [0, 1]):
        raise ProtocolError('T13 I2S edge diagnostic cleanup or first-failure state mismatch')
    if role == 1:
        if (summary[5] == 0 or summary[6] != 4 or summary[7] > summary[6] or
                summary[8] > summary[6] or
                first[10] != summary[5] or first[11] != summary[5] or
                trace[:4] != [0x49324554, 1, summary[6], summary[5]]):
            raise ProtocolError('T13 I2S physical edge count did not match normal DMA data')
        traces = []
        for index in range(trace[2]):
            base = 4 + index * 4
            boundary, observed, expected, received = trace[base:base + 4]
            if ((index > 0 and boundary - traces[-1]['boundary'] != observed) or
                    expected != received):
                raise ProtocolError('T13 I2S physical edge trace linkage mismatch')
            traces.append({'boundary': boundary, 'observed': observed, 'expected': expected,
                           'received': received})
        observed_total = sum(row['observed'] for row in traces)
        expected_internal = sum(row['expected'] for row in traces)
        received_internal = sum(row['received'] for row in traces)
        if (summary[14] != observed_total or
                not expected_internal <= summary[15] <= expected_internal + 3 or
                not received_internal <= summary[16] <= received_internal + 3 or
                summary[15] != summary[16] or
                abs(summary[14] - summary[16]) > EDGE_FAILURE_NOISE_BUDGET):
            raise ProtocolError('T13 I2S continuous physical edge total mismatch')
    elif (any(summary[index] != 0 for index in range(5, 17)) or first[10] != 0 or
          first[11] == 0 or any(trace)):
        raise ProtocolError('T13 I2S peer unexpectedly owned the receive edge observer')
    return {'role': role, 'buffers': summary[5], 'comparisons': summary[6],
            'physical_matches_expected': summary[7], 'physical_matches_received': summary[8],
            'cleanup_failures': summary[17], 'traces': traces if role == 1 else [],
            'observed_total': summary[14] if role == 1 else 0,
            'expected_total': summary[15] if role == 1 else 0,
            'received_total': summary[16] if role == 1 else 0,
            'diagnostic_only': True}


def classify_failure(pages, mode=1):
    """! @brief 최초 오류에서 패드 경로와 I2S 내부 경로를 전이 수로 구분합니다. """
    if (mode not in (1, 2) or len(pages) != 3 or any(len(page) != 20 for page in pages) or
            any(type(value) is not int or not 0 <= value <= MASK
                for page in pages for value in page)):
        raise ProtocolError('T13 I2S edge failure snapshot shape mismatch')
    summary, first, registers = pages
    if (summary[:3] != [0x49324530, 1, mode] or summary[13] != 1 or
            first[:3] != [0x49324531, 1, 1] or registers[:2] != [0x49324552, 1] or
            first[5:8] != summary[14:17] or first[8] != abs(first[5] - first[6]) or
            first[9] != abs(first[5] - first[7])):
        raise ProtocolError('T13 I2S edge first-failure linkage mismatch')
    expected_match = first[8] <= EDGE_FAILURE_NOISE_BUDGET
    received_match = first[9] <= EDGE_FAILURE_NOISE_BUDGET
    if received_match and not expected_match:
        cause = 'physical-pad-or-peer-output'
    elif expected_match and not received_match:
        cause = 'i2s-sampling-or-dma-internal'
    else:
        cause = 'ambiguous-transition-count'
    return {'cause': cause, 'route': 'swapped' if mode == 2 else 'original',
            'observed_edges': first[5], 'expected_edges': first[6],
            'received_edges': first[7], 'expected_difference': first[8],
            'received_difference': first[9], 'diagnostic_only': True}


def execute(devices, test, repetitions, continuity, append):
    """! @brief B 공급 생략 뒤 정상 재시작을 반복하고 첫 오류 raw를 보존합니다. """
    import v04_t13_stream_fault as stream_faults
    mode = test.get('_i2s_edge_diagnostic', 1)
    selected = fixture(test, mode)
    if not isinstance(repetitions, int) or not 1 <= repetitions <= 1000:
        raise ProtocolError('T13 I2S edge diagnostic repetition count is invalid')
    for repetition in range(1, repetitions + 1):
        label = f'T13-S/i2s-edge-diagnostic/i2s20/repeat{repetition:04}'
        captured = {}

        def record(identifier, row):
            append(label + '/' + identifier, row)
            marker = '/failure/role1/i2s-edge-page'
            if marker in identifier and isinstance(row.get('words'), list):
                captured[int(identifier.rsplit('page', 1)[1])] = row['words']

        try:
            stream_faults.execute(devices, test, 2, 1, continuity, record, preflight=True,
                                  restart_test=selected)
        except BaseException:
            if set(captured) == {0, 1, 2}:
                try:
                    analysis = classify_failure([captured[page] for page in range(3)], mode)
                except ProtocolError as error:
                    append(label + '/edge/failure-analysis',
                           {'status': 'unproven', 'error': str(error)})
                else:
                    append(label + '/edge/failure-analysis',
                           {'status': 'diagnostic', **analysis})
            raise
        measured = []
        for device in devices:
            role = device.image['role']
            pages = []
            for page in range(3):
                words = device.command(186, (page,), timeout=2)
                pages.append(words)
                append(label + f'/edge/role{role}/page{page}',
                       {'status': 'observation', 'words': words})
            measured.append(inspect(pages, role, mode))
        append(label + '/result', {'status': 'observation-complete',
                                   'diagnostic_only': True, 'roles': measured})
        print(f'T13_I2S_EDGE_PROGRESS completed={repetition}/{repetitions}', flush=True)
