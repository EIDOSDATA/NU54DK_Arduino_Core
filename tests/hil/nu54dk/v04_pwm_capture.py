"""! @brief Fixture 408의 첫 PWM peer capture를 raw TIMER 시각으로 독립 판정합니다. """
from __future__ import annotations

import itertools
import sys

import v04_fixture as fixture
from v04_protocol import ProtocolError

PERIODS = 100
EDGE_COUNT = PERIODS * 2 + 1


def vectors():
    """! @brief 12 slot·두 TOP·다섯 듀티·두 DMA word 극성의 240조건입니다. """
    yield from itertools.product((20, 21, 22), range(4), (1000, 4000),
                                 (0, 25, 50, 75, 100), (0, 1))


def received(vector, status, edges):
    """! @brief 평균으로 실패를 숨기지 않고 각 100주기·HIGH 폭을 ±5%로 판정합니다. """
    if vector not in vectors():
        raise ProtocolError("unsupported PWM capture vector")
    if (len(status) != 12 or any(type(value) is not int or not 0 <= value <= 0xFFFFFFFF
                                 for value in status) or
            status[:4] != [1, 1, 1, 0] or status[11] != 1 or
            status[5] not in (0, 1) or status[6] not in (0, 1)):
        raise ProtocolError("PWM capture incomplete/error/guard/status")
    top, duty = vector[2:4]
    if status[4] != len(edges):
        raise ProtocolError("PWM raw edge count mismatch")
    if duty in (0, 100):
        if edges or status[5:7] != [int(duty == 100)] * 2 or not top * PERIODS <= status[7] <= top * 125:
            raise ProtocolError("PWM static level changed, incorrect or too short")
        return {"static_level": int(duty == 100), "observed_us": status[7],
                "equivalent_periods": PERIODS, "measured_edges": 0}
    if len(edges) != EDGE_COUNT or not 0 < status[7] <= top * 125:
        raise ProtocolError("PWM capture requires exactly 100 complete periods")
    for index, row in enumerate(edges):
        if (len(row) != 2 or any(type(value) is not int for value in row) or
                not 0 <= row[0] <= 0xFFFFFFFF or row[1] not in (0, 1)):
            raise ProtocolError("PWM malformed raw capture")
        if index and (row[0] <= edges[index - 1][0] or row[1] == edges[index - 1][1]):
            raise ProtocolError("PWM missing/reordered/duplicate edge")
    periods, high_times = [], []
    for index in range(0, PERIODS * 2, 2):
        first, middle, last = edges[index:index + 3]
        period = last[0] - first[0]
        high = (middle[0] - first[0]) if first[1] else (last[0] - middle[0])
        if abs(period - top) * 100 > top * 5:
            raise ProtocolError("PWM individual period outside 5 percent")
        ## @brief duty 목표 비율의 상대 ±5%이며 ±5 percentage point로 넓히지 않습니다.
        if abs(high * 100 - period * duty) * 100 > period * duty * 5:
            raise ProtocolError("PWM individual duty outside 5 percent")
        periods.append(period)
        high_times.append(high)
    return {"periods": PERIODS, "period_us_range": [min(periods), max(periods)],
            "high_us_range": [min(high_times), max(high_times)],
            "tolerance_percent": 5, "measured_edges": EDGE_COUNT}


def run_case(devices, vector, append):
    """! @brief B 출력→A capture→원본 보존→B 우선 STOP을 한 case로 묶습니다. """
    receiver, generator = devices
    label = "V04-PWM-CAPTURE/408/" + "/".join(map(str, vector))
    try:
        for device in devices:
            if device.command(40, (408, 1, fixture.CONSENT, 2)) != [408, 10000]:
                raise ProtocolError("PWM fixture arm failed")
            if device.command(41, vector) != [0]:
                raise ProtocolError("PWM fixture prepare failed")
        if generator.command(42) != [0]:
            raise ProtocolError("PWM generator start failed")
        capture_reply = receiver.command(43, timeout=2)
        statuses = [device.command(46) for device in devices]
        raw = []
        if len(statuses[0]) != 12 or not 0 <= statuses[0][4] <= EDGE_COUNT:
            raise ProtocolError("PWM capture status length/count invalid")
        for offset in range(0, statuses[0][4], 8):
            count = min(8, statuses[0][4] - offset)
            values = receiver.command(44, (offset, count))
            if len(values) != count * 2:
                raise ProtocolError("PWM capture raw response truncated")
            raw.extend([values[index:index + 2] for index in range(0, len(values), 2)])
        append(label + "/raw", {"status": "observation", "vector": list(vector),
                                "capture_reply": capture_reply, "statuses": statuses, "edges": raw})
        if capture_reply != [0]:
            raise ProtocolError("PWM receiver capture failed; partial raw preserved")
        if (len(statuses[1]) != 12 or statuses[1][:4] != [1, 1, 0, 0] or
                statuses[1][11] != 1 or statuses[1][8] + statuses[1][9] == 0):
            raise ProtocolError("PWM generator error/guard/no sequence progress")
        result = received(vector, statuses[0], raw)
        append(label, {"vector": list(vector), "scope": "individual-single-buffer-loop-peer-capture",
                       **result})
    finally:
        original = sys.exception()
        cleanup = []
        for device in (generator, receiver):
            try:
                cleanup.append({"role": device.image["role"], "result": device.command(45)})
            except BaseException as error:
                cleanup.append({"role": device.image["role"], "error": str(error)})
        append(label + "/cleanup", {"status": "cleanup", "cleanup_only": True, "results": cleanup})
        if any(row.get("result") != [0, 1, 1] for row in cleanup):
            if original is not None:
                original.add_note(f"PWM cleanup unproven: {cleanup}")
            else:
                raise ProtocolError(f"PWM cleanup unproven: {cleanup}")


def run_confirmed(devices, images, uids, confirmation, fixture_id, append, repetitions=1):
    """! @brief 현재 source·UID·image·408 결선을 매 case 전에 다시 확인합니다. """
    if fixture_id != 408 or type(repetitions) is not int or not 1 <= repetitions <= 100:
        raise ProtocolError("PWM capture requires fixture 408 and bounded repetitions")
    for repetition in range(repetitions):
        for vector in vectors():
            fixture.validate_confirmation(confirmation, images, uids, 408)
            run_case(devices, vector,
                     lambda case_id, result: append(f"{case_id}/repeat-{repetition + 1}", result))
