"""! @brief 전체 SPI RAM·실제512byte 경계·미준비 semaphore와 STOP 누락을 검사합니다. """
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'tests/hil/nu54dk'))
import v04_t13_cases as cases
import v04_t13_spi_boundary as boundary
import v04_t13_run as runner
from v04_protocol import ProtocolError


class SpiBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.test = next(row for row in cases.cases() if row['id'] == 7)
        self.seed = 0x12345678

    def vector(self, role, mode):
        policy = role if mode == 'short' else role+2
        terminal = policy != 4
        endpoint = self.test['serial_links'][0]['a' if role == 1 else 'b']
        instance = endpoint['instance']
        pointers = [0x20001010, 0x20001810]
        amount = 1024 if role == 1 else 512
        hardware = [amount]*2 if terminal else [77, 88]
        status = boundary.MASK if role == 1 else 3 if mode == 'short' else 0
        semaphore = boundary.MASK if role == 1 else 1
        raw = [policy, instance, 1, 1 if terminal else 2, int(terminal), 0 if terminal else boundary.MASK,
               amount if terminal else 0, amount if terminal else 0, 3 if terminal else 0, 1, 1,
               *hardware, status, semaphore, 101010 if terminal else 0, 1000,
               101000 if role == 1 else 0, 1000000, 1]
        pins = [boundary.physical(endpoint['pins'][name]) for name in ('sck', 'mosi', 'miso', 'csn')]
        before = [policy, 2 if role == 1 else 3, instance, 7 if role == 1 else 2,
                  255, boundary.MASK if role == 1 else 255, 1024, 1024, *pointers,
                  *pins, boundary.MASK if role == 1 else 0, semaphore, 1, 1, 1000, 1000000]
        after = before[:]
        if terminal:
            after[6:8] = [amount, amount]
            after[14] = status
        after[18] = 101010
        baseline = [77, 88, *pointers, 1024]+[0]*15
        tx = bytes(boundary.oracle.pattern(boundary.oracle.lane_seed(self.seed, 0, role), i) for i in range(1024))
        peer = bytes(boundary.oracle.pattern(boundary.oracle.lane_seed(self.seed, 0, 3-role), i) for i in range(1024))
        rx = (peer[:512]+bytes([255 if role == 1 else 204])*512) if mode == 'short' else bytes([255 if role == 1 else 204])*1024
        lane = ([82, 0, 0] if terminal else [0, 0, 1])+[0]*16+[20]
        return [raw, before, after, baseline, tx, rx, self.test, role, mode, self.seed, lane]

    def test_scope_includes_only_fixed_spi_pairs(self):
        for test in cases.cases():
            if 6 <= test['id'] <= 10:
                boundary.validate_selection(test, 'short')
            else:
                with self.assertRaises(ProtocolError):
                    boundary.validate_selection(test, 'short')

    def test_wrong_event_amount_guard_state_and_full_ram_cannot_pass(self):
        for mode in ('short', 'unready'):
            for role in (1, 2):
                args = self.vector(role, mode)
                boundary.inspect(*args)
                mutations = [(0, 2, 0), (0, 3, 0), (0, 9, 0), (0, 10, 0), (0, 19, 0),
                             (1, 10, 46), (2, 16, 0), (3, 2, 0), (10, 0, 71)]
                mutations += [(0, 5, 1), (0, 6, 0), (0, 11, 0)] if not (mode == 'unready' and role == 2) else [(0, 4, 1), (0, 11, 0), (2, 15, 0)]
                for which, index, value in mutations:
                    broken = self.vector(role, mode)
                    broken[which][index] = value
                    with self.subTest(mode=mode, role=role, which=which, index=index), self.assertRaises(ProtocolError):
                        boundary.inspect(*broken)
                for direction in (4, 5):
                    for offset in (0, 511, 512, 1023):
                        broken = self.vector(role, mode)
                        data = bytearray(broken[direction])
                        data[offset] ^= 1
                        broken[direction] = bytes(data)
                        with self.assertRaises(ProtocolError):
                            boundary.inspect(*broken)

    def test_previous_amount_is_not_counted_as_unready_rx(self):
        result = boundary.inspect(*self.vector(2, 'unready'))
        self.assertEqual(result['hardware_rx_amount_raw'], 88)
        self.assertTrue(result['rx_amount_is_previous'])
        self.assertFalse(result['normal_soak_pass'])

    def test_hil_refreshes_csn_after_event_before_deactivate(self):
        source = (ROOT/'tests/zephyr/v04_t13_hil/src/serial.cpp').read_text(encoding='utf-8')
        stop = source[source.index('bool t13::serialStop()'):source.index('bool t13::serialSpiBoundaryPolicy')]
        self.assertIn('const auto csn = spi_boundary.after[13];', stop)
        self.assertIn('spi_boundary.after[16] = csn < 96U ? nrf_gpio_pin_read(csn)', stop)
        self.assertLess(stop.index('spi_boundary.after[16] ='), stop.index('lane.handle->deactivate'))

    def test_full_capture_precedes_inspection_and_reacquire_needs_cleanup(self):
        devices = [mock.Mock(), mock.Mock()]
        for role, device in enumerate(devices, 1):
            device.image = {'role': role}
            def command(opcode, args=(), role=role, **kwargs):
                vector = self.vector(role, 'short')
                if opcode == 152:
                    return vector[args[0]]
                if opcode == 153:
                    data = vector[4+args[0]][args[1]*64:(args[1]+1)*64]
                    return [int.from_bytes(data[i:i+4], 'little') for i in range(0, 64, 4)]
                if opcode == 99:
                    return [7, 0, 0, 0, 0, 0]+[0]*10
                if opcode == 100:
                    return vector[-1]
                if opcode == 107:
                    return [1, 1, 1]
                return [1]
            device.command.side_effect = command
        for cleanup in (True, False):
            rows = []
            with mock.patch.object(runner, 'execute_group') as group, \
                 mock.patch.object(runner, 'prepared_bus_pins'), \
                 mock.patch.object(runner, 'stop_pair', return_value=cleanup), \
                 mock.patch.object(runner, 'idle_pins', return_value=True), \
                 mock.patch.object(boundary.secrets, 'randbits', return_value=self.seed), \
                 mock.patch.object(boundary.time, 'sleep'):
                if cleanup:
                    boundary.execute(devices, self.test, 'short', mock.Mock(), lambda name, row: rows.append((name, row)), preflight=True)
                    self.assertEqual(group.call_count, 2)
                    first_observed = next(i for i, (_, row) in enumerate(rows) if row['status'] == 'expected-boundary-observed')
                    memory = [i for i, (name, _) in enumerate(rows) if '/stopped/' in name and ('/tx' in name or '/rx' in name)]
                    self.assertEqual(len(memory), 64)
                    self.assertLess(max(memory), first_observed)
                    self.assertFalse(rows[-1][1]['planned_spi_boundary_pass'])
                    first, restart = group.call_args_list
                    self.assertEqual(first.kwargs['seed'] ^ 0x9E3779B9, restart.kwargs['seed'])
                    self.assertTrue(first.kwargs['serial_start_barrier'])
                    self.assertTrue(restart.kwargs['serial_start_barrier'])
                else:
                    with self.assertRaises(ProtocolError):
                        boundary.execute(devices, self.test, 'short', mock.Mock(), lambda name, row: rows.append((name, row)), preflight=True)
                    self.assertEqual(group.call_count, 1)


if __name__ == '__main__':
    unittest.main()
