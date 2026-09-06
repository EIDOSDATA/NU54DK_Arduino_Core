"""두 NU54DK만 사용하는 analog/stream 합성 신호 시험 준비입니다."""
from __future__ import annotations
import hashlib
import itertools
import statistics
import struct
import time

import v04_fixture as fixture
from v04_protocol import ProtocolError

INPUT_BIAS_FIXTURES = (406, 407)
SHARED_ANALOG_FIXTURES = (405,) + INPUT_BIAS_FIXTURES

def vectors(family, fixture_id=None):
    """기능 sweep와 buffer 경계를 한 번씩 바꾸는 실행 vector를 생성합니다."""
    if family == "analog":
        if fixture_id in SHARED_ANALOG_FIXTURES:
            for samples, buffers, phase in itertools.product((32, 256), (1, 2), range(3)):
                yield (0, samples, phase, 0, 0, buffers)
            return
        yield from itertools.product((20, 21, 22), (32, 256), (1021,), (512,),
                                     range(4), (1, 2))
        return
    if family == "qdec":
        yield from itertools.product((20, 21, 22), (20, 21), (1, 100),
                                     (2000,), range(2), range(2))
        return
    if family == "i2s":
        yield from itertools.product((16000, 48000), (8, 16, 24, 32), range(3),
                                     (32, 256), (1, 2), (0x13579BDF,))
        return
    if family == "pdm":
        yield from itertools.product((20, 21), (256, 1024), (25, 50, 75),
                                     range(2), range(2), (1, 2))
        return
    raise ProtocolError("unknown signal family")


def arguments_for(family, vector):
    """8-word firmware 인자로 확장하며 남은 word는 반드시 0으로 고정합니다."""
    values = list(vector)
    if len(values) > 8:
        raise ProtocolError("signal vector exceeds mailbox")
    return tuple(values + [0] * (8 - len(values)))


def wait_status(device, predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    words = []
    while time.monotonic() < deadline:
        words = device.command(36)
        if len(words) != 8 or words[4]:
            raise ProtocolError(f"signal firmware error role={device.image['role']}: {words}")
        if predicate(words):
            return words
        time.sleep(.005)
    raise ProtocolError(f"signal timeout role={device.image['role']}: {words}")


def read_u16(device, samples):
    output = []
    for offset in range(0, samples, 16):
        count = min(16, samples - offset)
        words = device.command(37, (offset, count))
        raw = struct.pack(f"<{len(words)}I", *words)
        output.extend(struct.unpack(f"<{count}h", raw[:count * 2]))
    return output


def read_u32(device, words):
    output = []
    for offset in range(0, words, 16):
        count = min(16, words - offset)
        output.extend(device.command(37, (offset, count)))
    return output


def pattern(seed, index):
    return ((seed + 0x9E3779B9 * (index + 1)) & 0xFFFFFFFF) ^ \
           (((index << 16) | (index >> 16)) & 0xFFFFFFFF)


def i2s_expected(seed, words, width, channels):
    """NRF I2S memory word에서 활성 sample bit만 비교할 mask를 함께 반환합니다."""
    mask = 0xFFFFFF if width == 24 else 0xFFFFFFFF
    return [pattern(seed, index) & mask for index in range(words)], mask


def i2s_received(raw, seed, words, width, channels):
    """시작 시 최대 8개의 zero frame 뒤 요청 payload 전체를 sample 단위로 검증합니다."""
    if len(raw) != words + 16:
        raise ProtocolError("I2S capture word count mismatch")
    expected, _ = i2s_expected(seed, words, width, channels)
    sample_mask = (1 << width) - 1
    shifts = range(0, 32, width) if width <= 16 else (0,)
    unpack = lambda data: [(word >> shift) & sample_mask
                           for word in data for shift in shifts]
    actual_samples, expected_samples = unpack(raw), unpack(expected)
    padding = next((index for index, value in enumerate(actual_samples) if value), len(actual_samples))
    frame_samples = 2 if channels == 0 else 1
    if padding > 8 * frame_samples or padding % frame_samples:
        raise ProtocolError("I2S startup zero-frame bound/alignment mismatch")
    if actual_samples[padding:padding + len(expected_samples)] != expected_samples:
        raise ProtocolError("I2S payload/packing mismatch")
    return {"startup_zero_samples": padding, "payload_samples": len(expected_samples),
            "capture_words": len(raw),
            "raw_sha256": hashlib.sha256(b"".join(word.to_bytes(4, "little") for word in raw)).hexdigest()}


def shared_source_readback(source, phase, fixture_id=405):
    """! @brief nRF54L15 PIN_CNF의 DIR/INPUT/PULL/DRIVE0/DRIVE1도 독립 해석합니다. """
    level = int(phase == 1)
    if fixture_id == 405:
        expected, raw = [1, phase, 46, 1, 1, 1, level], 0x80D
    elif fixture_id in INPUT_BIAS_FIXTURES:
        expected, raw = [1, phase, 46, 0, level, 0, 1], 0xC if level else 0x4
    else:
        raise ProtocolError("unknown shared analog fixture")
    if len(source) != 9 or source[:7] != expected or source[8] & 0xF0F != raw:
        raise ProtocolError(f"shared analog source configuration mismatch: {source}")


def shared_analog_result(vector, status, samples, source, fixture_id=405):
    """! @brief 공유 입력별 LOW/HIGH 경계와 DMA 완료를 독립 판정합니다. """
    phase = vector[2]
    expected = vector[1] * vector[5]
    level = int(phase == 1)
    shared_source_readback(source, phase, fixture_id)
    if (len(status) != 8 or status[:5] != [1, 1, 1, 1, 0] or
            status[5:7] != [expected, vector[1]] or len(samples) != expected):
        raise ProtocolError(f"shared analog DMA completion mismatch: {status}")
    high_threshold = 1024 if fixture_id in INPUT_BIAS_FIXTURES else 256
    low_limit = 512 if fixture_id in INPUT_BIAS_FIXTURES else 256
    high = sum(sample > high_threshold for sample in samples)
    median = statistics.median(samples)
    if min(samples) < -256 or max(samples) > 4095:
        raise ProtocolError("shared analog raw samples are outside functional bounds")
    if level:
        required_percent = 100 if fixture_id in INPUT_BIAS_FIXTURES else 95
        if high * 100 < expected * required_percent or median <= high_threshold:
            raise ProtocolError("shared analog HIGH phase did not rise")
    elif max(samples) > low_limit:
        raise ProtocolError("shared analog input did not return LOW")
    return {"receiver_status": status, "source_readback": source,
            "phase": (("pulldown-before", "pullup", "pulldown-after") if fixture_id in INPUT_BIAS_FIXTURES else
                      ("low-before", "released", "low-after"))[phase],
            "minimum": min(samples), "maximum": max(samples), "median": median,
            "high_samples": high, "samples": samples,
            "sha256": hashlib.sha256(struct.pack(f"<{len(samples)}h", *samples)).hexdigest(),
            "scope": (f"input-bias-shared-ain{fixture_id - 401}-manual-saadc" if fixture_id in INPUT_BIAS_FIXTURES else
                      "open-drain-shared-ain4-manual-saadc")}


def run_case(devices, selected, controller_role, vector, append):
    family = selected["family"]
    controller = devices[controller_role - 1]
    receiver = devices[2 - controller_role]
    args = arguments_for(family, vector)
    try:
        for device in devices:
            reply = device.command(32, (selected["id"], 1, fixture.CONSENT,
                                        controller_role))
            if reply != [selected["id"], 10000]:
                raise ProtocolError(f"signal fixture arm failed: {reply}")
        if controller.command(34, args) != [0]:
            raise ProtocolError("signal generator prepare failed")
        if family == "pdm":
            wait_status(controller, lambda words: words[2] == 1)
        if receiver.command(34, args) != [0]:
            raise ProtocolError("signal receiver prepare failed")
        wait_status(receiver, lambda words: words[2] == 1)

        if family == "i2s":
            if receiver.command(35) != [0] or controller.command(35) != [0]:
                raise ProtocolError("I2S slave/master start failed")
            target = vector[3] * vector[4]
            statuses = [wait_status(device, lambda words: words[3] == 1)
                        for device in devices]
            if any(status[5] != target for status in statuses):
                raise ProtocolError(f"I2S DMA word count mismatch: {statuses}")
            payloads = []
            for device in devices:
                peer_role = 3 - device.image["role"]
                peer_seed = vector[5] ^ (0 if peer_role == 1 else 0x5A5A5A5A)
                payloads.append({"receiver_role": device.image["role"], **i2s_received(
                    read_u32(device, target + 16), peer_seed, target, vector[1], vector[2])})
            result = {"statuses": statuses, "payloads": payloads, "scope": "i2s-full-duplex-dma"}
        elif family == "pdm":
            if receiver.command(35) != [0]:
                raise ProtocolError("PDM receiver start failed")
            receiver_status = wait_status(receiver, lambda words: words[3] == 1,
                                          timeout=10.0)
            sample_count = vector[1] * vector[5]
            if receiver_status[5] != sample_count:
                raise ProtocolError(f"PDM DMA sample count mismatch: {receiver_status}")
            samples = read_u16(receiver, sample_count)
            mean = sum(samples) / len(samples)
            channel_means = None
            if vector[3]:
                channel_means = [sum(samples[channel::2]) / len(samples[channel::2])
                                 for channel in range(2)]
                if abs(channel_means[0] - channel_means[1]) < 512:
                    raise ProtocolError(
                        f"PDM stereo channels are not independently distinguishable: {channel_means}")
            result = {"receiver_status": receiver_status, "mean": mean,
                      "minimum": min(samples), "maximum": max(samples),
                      "channel_means": channel_means,
                      "scope": "pdm-clock-synchronous-spis-bitstream"}
        elif family == "analog":
            if controller.command(35) != [0]:
                raise ProtocolError("analog generator start failed")
            source = controller.command(38) if selected["id"] in SHARED_ANALOG_FIXTURES else None
            if source is not None:
                shared_source_readback(source, vector[2], selected["id"])
                time.sleep(.025 if selected["id"] in INPUT_BIAS_FIXTURES else .010)
            if receiver.command(35) != [0]:
                raise ProtocolError("SAADC sampling start failed")
            receiver_status = wait_status(receiver, lambda words: words[3] == 1)
            sample_count = vector[1] * vector[5]
            samples = read_u16(receiver, sample_count)
            if selected["id"] in SHARED_ANALOG_FIXTURES:
                result = shared_analog_result(vector, receiver_status, samples, source, selected["id"])
                final_source = controller.command(38)
                shared_source_readback(final_source, vector[2], selected["id"])
                if len(final_source) != 9 or final_source[:7] != source[:7]:
                    raise ProtocolError(f"shared source changed during sampling: {final_source}")
                result["source_readback_after"] = final_source
            else:
                if receiver_status[5] != sample_count or max(samples) <= 256:
                    raise ProtocolError("PWM-triggered SAADC did not capture a valid HIGH level")
                result = {"receiver_status": receiver_status,
                          "minimum": min(samples), "maximum": max(samples),
                          "sha256": hashlib.sha256(struct.pack(f"<{len(samples)}h", *samples)).hexdigest(),
                          "scope": "pwm-manual-saadc"}
        else:
            if controller.command(35) != [0]:
                raise ProtocolError("quadrature generator start failed")
            wait_status(controller, lambda words: words[3] == 1,
                        timeout=max(5.0, vector[2] * vector[3] * 4 / 1_000_000 + 2.0))
            time.sleep(vector[3] * 2 / 1_000_000)
            report = receiver.command(37)
            if len(report) != 3 or report[0] != 0 or report[2] != 0:
                raise ProtocolError(f"QDEC accumulator error: {report}")
            signed = report[1] if report[1] < 0x80000000 else report[1] - 0x100000000
            expected = (-1 if vector[4] else 1) * vector[2] * 4
            if signed != expected:
                raise ProtocolError(f"QDEC count mismatch: actual={signed}, expected={expected}")
            result = {"accumulated": signed, "double_transitions": report[2],
                      "scope": "pwm-quadrature-qdec"}
        append(f"V04-{family.upper()}-SIGNAL/{selected['id']}/{controller_role}/{vector}",
               result)
    finally:
        original_error = __import__("sys").exception()
        cleanup = []
        cleanup_devices = (controller, receiver) if selected["id"] in SHARED_ANALOG_FIXTURES else devices
        for device in cleanup_devices:
            try:
                item = {"role": device.image["role"], "result": device.command(33)}
                if selected["id"] in SHARED_ANALOG_FIXTURES and device is controller:
                    state = device.command(38)
                    item["source_readback"] = state
                    if (len(state) != 9 or state[:7] != [0, 0xFFFFFFFF, 46, 0, 0, 0, 1] or
                            state[8] & 0xF0F != 0):
                        item["error"] = "shared source input release not proven"
                cleanup.append(item)
            except BaseException as cleanup_error:
                cleanup.append({"role": device.image["role"], "error": str(cleanup_error)})
        append("V04-SIGNAL-CLEANUP", {"status": "cleanup", "cleanup_only": True,
                                      "results": cleanup})
        if any(item.get("result") != [0] or "error" in item for item in cleanup):
            if original_error is not None:
                original_error.add_note(f"signal cleanup not proven: {cleanup}")
            else:
                raise ProtocolError(f"signal cleanup not proven: {cleanup}")


def run_confirmed(devices, images, uids, confirmation, fixture_id, append,
                  repetitions=1):
    selected = fixture.validate_confirmation(confirmation, images, uids, fixture_id)
    if selected["family"] not in {"analog", "qdec", "i2s", "pdm"}:
        raise ProtocolError("not a signal fixture")
    if type(repetitions) is not int or not 1 <= repetitions <= 100:
        raise ProtocolError("repetitions out of range")
    for repetition in range(repetitions):
        controller_roles = (2,) if selected["family"] in {"analog", "qdec"} else (1, 2)
        for controller_role in controller_roles:
            pdm_means = {}
            for vector in vectors(selected["family"], fixture_id):
                def record(case_id, result):
                    append(f"{case_id}/repeat-{repetition + 1}", result)
                    if (selected["family"] == "pdm" and not vector[3] and
                            "mean" in result):
                        key = (vector[0], vector[1], vector[4], vector[5])
                        pdm_means.setdefault(key, {})[vector[2]] = result["mean"]

                run_case(devices, selected, controller_role, vector, record)
            for key, means in pdm_means.items():
                if set(means) != {25, 50, 75} or not means[25] < means[50] < means[75]:
                    raise ProtocolError(f"PDM density ordering mismatch {key}: {means}")
                append(
                    f"V04-PDM-DENSITY/{selected['id']}/{controller_role}/{key}"
                    f"/repeat-{repetition + 1}",
                    {"means": means, "scope": "pdm-mono-density-order"})
