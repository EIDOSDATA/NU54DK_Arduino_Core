"""! @brief 내부 ADC·timer·event의 관측 누락과 잘못된 PASS를 거부합니다. """
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'hil' / 'nu54dk'))
import v04_nojumper as hil


def reply_for(vector):
    request = [1, 123, *vector]
    reply = [0] * 32
    reply[:8] = request
    reply[2] = 0
    return request, reply


class InternalNojumperTests(unittest.TestCase):
    def test_vectors_cover_channel_boundaries_and_repetitions(self):
        adc = list(hil.adc_vectors())
        timer = list(hil.timer_vectors())
        event = list(hil.event_vectors())
        bridge = list(hil.bridge_vectors())
        self.assertEqual([len(adc), len(timer), len(event), len(bridge)], [12, 352, 480, 44])
        for vectors in (adc, timer, event, bridge):
            self.assertEqual(len(vectors), len(set(vectors)))
        self.assertEqual({v[1:3] for v in timer}, {(i, c) for i, n in hil.TIMER_CHANNELS.items() for c in range(n)})
        self.assertEqual({v[2] for v in bridge if v[1] == 2}, set(range(16)))
        self.assertEqual({v[3] for v in bridge if v[1] == 2}, set(range(24)))

    def test_grtc_public_time_requires_elapsed_and_timer_agreement(self):
        self.assertEqual(len(list(hil.time_vectors())), 4)
        for vector in hil.time_vectors():
            request, reply = reply_for(vector)
            duration = request[3]
            reply[12:17] = [duration, duration + 10, duration // 1000, duration // 1000, 10]
            reply[20:22] = [1, 100]
            hil.validate_reply(request, reply)
            for index, value in ((12, 0), (15, 100), (16, 1000), (20, 0), (21, 99)):
                altered = reply.copy()
                altered[index] = value
                with self.assertRaises(hil.ProtocolError):
                    hil.validate_reply(request, altered)

    def adc(self, reverse=0, count=32, channels=2):
        request, reply = reply_for((2, channels, reverse | 2, count, 100, 1))
        reply[11] = 1
        reply[12:16] = [2000, 2010, 3700, 3710] if reverse else [3700, 3710, 2000, 2010]
        reply[16] = count * 100
        reply[19:22] = [1, 1, 100]
        reply[23] = 100
        reply[26] = 2
        return request, reply

    def test_busy_wait_uses_existing_five_percent_clock_tolerance(self):
        """! @brief clock 차이 995us는 허용하고 5% 바깥과 누락된 반복은 거부합니다. """
        request, reply = reply_for((6, 1000, 0, 100, 0, 1))
        reply[12:17] = [995, 995, 1, 1, 16]
        reply[20:22] = [1, 100]
        hil.validate_reply(request, reply)
        for minimum, maximum in ((949, 995), (995, 1051)):
            altered = reply.copy()
            altered[12:14] = [minimum, maximum]
            with self.assertRaises(hil.ProtocolError):
                hil.validate_reply(request, altered)
        reply[21] = 0
        with self.assertRaises(hil.ProtocolError):
            hil.validate_reply(request, reply)

    def test_adc_scan_reverse_and_calibration_count(self):
        for reverse in (0, 1):
            request, reply = self.adc(reverse)
            hil.validate_reply(request, reply)
            for index, value in ((11, 2), (16, 3199), (19, 0), (20, 0), (21, 99), (23, 99)):
                altered = reply.copy()
                altered[index] = value
                with self.assertRaises(hil.ProtocolError):
                    hil.validate_reply(request, altered)
            altered = reply.copy()
            altered[12:14], altered[14:16] = altered[14:16], altered[12:14]
            with self.assertRaises(hil.ProtocolError):
                hil.validate_reply(request, altered)

    def test_adc_independent_raw_guards_tail_and_channel_order(self):
        request, reply = self.adc(count=1, channels=1)
        samples = [3705] + [0x5555] * 31
        raw = struct.pack('<4I32h4I', *([0xD65A91C3] * 4 + samples + [0xD65A91C3] * 4))
        hil.validate_adc_snapshot(request, reply, raw)
        for byte in (0, 18, 80):
            altered = bytearray(raw)
            altered[byte] ^= 1
            with self.assertRaises(hil.ProtocolError):
                hil.validate_adc_snapshot(request, reply, altered)
        request, reply = self.adc()
        raw = struct.pack('<4I32h4I', *([0xD65A91C3] * 4 + [3705, 2005] * 16 + [0xD65A91C3] * 4))
        hil.validate_adc_snapshot(request, reply, raw)
        with self.assertRaises(hil.ProtocolError):
            hil.validate_adc_snapshot(request, reply, raw[:16] + raw[18:20] + raw[16:18] + raw[20:])

    def test_timer_shortcuts_and_independent_elapsed_tolerance(self):
        for flags in range(4):
            request, reply = reply_for((3, 10, 7, flags, 1000, 10))
            value = (0 if flags & 1 else 1000) if flags & 2 else (500 if flags & 1 else 1500)
            reply[12:15] = [value, value, 0]
            reply[15] = 1
            reply[18:22] = [1, 1, 1, 10]
            reply[25:27] = [1500, value]
            reply[27] = 10
            hil.validate_reply(request, reply)
            for index, value in ((10, 9), (14, 51), (15, 0), (17, 1), (18, 0), (19, 0), (20, 0), (21, 9), (26, 5000)):
                altered = reply.copy()
                altered[index] = value
                with self.assertRaises(hil.ProtocolError):
                    hil.validate_reply(request, altered)

    def test_event_and_bridge_require_disable_group_and_overflow_checks(self):
        for op in (4, 5):
            request, reply = reply_for((op, 10 if op == 4 else 2, 0, 0, 1000, 10))
            reply[12:15] = [10000, 10, 10]
            reply[20:27] = [1, 10, 60, 6, 10, 10, 60]
            hil.validate_reply(request, reply)
            for index, value in ((12, 9999), (13, 9), (17, 1), (18, 1), (19, 1), (20, 0), (21, 9)):
                altered = reply.copy()
                altered[index] = value
                with self.assertRaises(hil.ProtocolError):
                    hil.validate_reply(request, altered)
            if op == 4:
                reply[22] = 59
                with self.assertRaises(hil.ProtocolError):
                    hil.validate_reply(request, reply)


if __name__ == '__main__':
    unittest.main()
