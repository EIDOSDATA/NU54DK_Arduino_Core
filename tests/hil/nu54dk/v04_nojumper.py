"""! @brief 무점퍼 PWM·ADC·event의 exact image·SWD 명령·독립 판정과 실패 원본을 관리합니다. """
from __future__ import annotations

from itertools import product
from pathlib import Path
import secrets
import struct
import time

from m24_uarte_onboard import git_output, parse_build_record, sha256_file
from v04_protocol import ProtocolError

MAGIC = 0x4E4A5031
SIZES = {'nojumper_request': 32, 'nojumper_response': 128, 'nojumper_ready': 16,
         'nojumper_revision': 41, 'nojumper_adc_buffer': 96}


def pwm_vectors():
    """! @brief 시작 방식 5개와 PWM 모드 조합 960개를 생성합니다. 외부 파형 판정은 아닙니다. """
    for instance, load, top, complex_sequence, triggered, loop, start in product(
            (20, 21, 22), range(4), (1000, 4000), (0, 4), (0, 8), (0, 16), (0, 1, 3, 33, 35)):
        flags = complex_sequence | triggered | loop | start
        yield (1, instance, flags, load, top, 1)


def validate_reply(request, reply):
    """! @brief nonce·요청 identity·DMA/주기 흔적·반복·guard·자원 반환을 각각 검사합니다. """
    if len(request) != 8 or len(reply) != 32 or reply[:2] != request[:2]:
        raise ProtocolError('nojumper response identity/size mismatch')
    if reply[2] or reply[3:8] != request[3:8]:
        raise ProtocolError(f'nojumper firmware failure or request mismatch: {reply}')
    operation = request[2]
    if operation == 2:
        return validate_adc(request, reply)
    if operation == 3:
        return validate_timer(request, reply)
    if operation in (4, 5):
        return validate_event(request, reply)
    if operation == 6:
        return validate_time(request, reply)
    if operation != 1:
        raise ProtocolError('unknown nojumper operation')
    flags = request[4]
    started = not flags & 1 or bool(flags & 2)
    if any(reply[index] for index in (8, 9, 10, 17)):
        raise ProtocolError(f'PWM configure/play/stop/disable failed: {reply}')
    if reply[11] != 1 or reply[19:21] != [1, 1] or reply[21] != request[7]:
        raise ProtocolError(f'PWM state/guard/lease/repetitions mismatch: {reply}')
    if reply[18] != reply[24]:
        raise ProtocolError('PWM pin restoration mismatch')
    if started:
        if not (reply[12] | reply[13]) or not (reply[14] | reply[15]):
            raise ProtocolError('PWM START did not reach DMA/wave counter')
    elif any(reply[12:17]):
        raise ProtocolError('cancelled preparation unexpectedly started DMA/PWM')
    if flags & 32 and reply[22] != 7:
        raise ProtocolError('active START subscription was not rejected')


def inspect_image(repository: Path, build_root: Path):
    """! @brief clean source·board gitlink·build record·ELF의 SRAM 범위를 고정합니다. """
    from elftools.elf.elffile import ELFFile
    source = git_output(repository, 'rev-parse', 'HEAD')
    if git_output(repository, 'status', '--porcelain'):
        raise ProtocolError('clean source required before nojumper hardware access')
    board = git_output(repository, 'rev-parse', 'HEAD:board_package/NU54DK_Zephyr_DTS')
    if git_output(repository / 'board_package/NU54DK_Zephyr_DTS', 'rev-parse', 'HEAD') != board:
        raise ProtocolError('nojumper board gitlink mismatch')
    images = list(build_root.glob('**/nucode.m25.nojumper_hil/m25_nojumper_hil/zephyr/zephyr.hex'))
    if len(images) != 1:
        raise ProtocolError('exactly one canonical nojumper image required')
    image = images[0]
    record = parse_build_record(image.parent.parent / 'nucode_arduino_core_build.yml')
    expected = {'core_revision': source[:12], 'board_revision': board[:12],
                'board': 'nrf54l15dk', 'board_qualifiers': 'nrf54l15/cpuapp/nu54dk'}
    if any(record.get(key) != value for key, value in expected.items()):
        raise ProtocolError('nojumper image provenance mismatch')
    config = (image.parent / '.config').read_text(encoding='utf-8')
    for forbidden in ('CONFIG_SERIAL=y', 'CONFIG_CONSOLE=y', 'CONFIG_NUCODE_ARDUINO_SERIAL_FABRIC=y'):
        if forbidden in config:
            raise ProtocolError('nojumper image must not own DAP UART')
    symbols = {}
    with image.with_suffix('.elf').open('rb') as stream:
        table = ELFFile(stream).get_section_by_name('.symtab')
        for name, size in SIZES.items():
            entries = table.get_symbol_by_name(name) or []
            if len(entries) != 1 or entries[0]['st_size'] != size:
                raise ProtocolError(f'invalid nojumper symbol: {name}')
            address = int(entries[0]['st_value'])
            if not 0x20000000 <= address <= 0x20040000 - size or address % 4:
                raise ProtocolError('nojumper mailbox outside aligned SRAM')
            symbols[name] = address
    spans = sorted((address, address + SIZES[name]) for name, address in symbols.items())
    if any(a[1] > b[0] for a, b in zip(spans, spans[1:])):
        raise ProtocolError('overlapping nojumper mailbox symbols')
    return {'path': image, 'elf': image.with_suffix('.elf'), 'source': source, 'board': board,
            'hex_sha256': sha256_file(image), 'elf_sha256': sha256_file(image.with_suffix('.elf')),
            'symbols': symbols}


class Device:
    """! @brief exact identity와 응답이 실패하면 후속 명령을 차단합니다. """
    def __init__(self, target, image):
        self.target, self.image = target, image
        self.sequence = 0
        self.nonce = secrets.randbits(32) or 1
        self.poisoned = False

    def identity(self):
        symbols = self.image['symbols']
        ready = self.target.read_memory_block32(symbols['nojumper_ready'], 4)
        revision = bytes(self.target.read_memory_block8(symbols['nojumper_revision'], 41))
        if ready[:2] != [MAGIC, 2] or revision != self.image['source'].encode('ascii') + b'\0':
            raise ProtocolError('nojumper runtime identity mismatch')
        return ready

    def command(self, vector, append):
        if self.poisoned or len(vector) != 6:
            raise ProtocolError('invalid vector or poisoned nojumper session')
        self.sequence += 1
        request = [self.sequence, self.nonce, *vector]
        symbols = self.image['symbols']
        try:
            self.target.write32(symbols['nojumper_request'], 0)
            self.target.write32(symbols['nojumper_response'], 0)
            self.target.write_memory_block32(symbols['nojumper_request'] + 4, request[1:])
            self.target.flush()
            self.target.write32(symbols['nojumper_request'], self.sequence)
            self.target.flush()
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                if self.target.read32(symbols['nojumper_response']) != 0:
                    reply = self.target.read_memory_block32(symbols['nojumper_response'], 32)
                    record = {'request': request, 'reply': reply}
                    if request[2] == 2:
                        try:
                            raw = bytes(self.target.read_memory_block8(symbols['nojumper_adc_buffer'], 96))
                            record['adc_snapshot_hex'] = raw.hex()
                        except BaseException as error:
                            record['adc_snapshot_error'] = str(error)
                            append(record)
                            raise
                    append(record)
                    validate_reply(request, reply)
                    if request[2] == 2:
                        validate_adc_snapshot(request, reply, raw)
                    return request, reply
                time.sleep(0.002)
            raise ProtocolError('nojumper command timeout')
        except BaseException:
            self.poisoned = True
            raise


def read_postflight(device):
    """! @brief reset 없이 세 PWM과 한 출력 핀 및 DPPI 채널 해제를 읽습니다. """
    target = device.target
    return {'ready': device.identity(), 'pwm_enable': [target.read32(base + 0x500)
            for base in (0x500D2000, 0x500D3000, 0x500D4000)],
            'p1_14_pin_cnf': target.read32(0x500D8280 + 14 * 4),
            'dppi20_channel0': target.read32(0x500C2500) & 1,
            'dppi_channels': [target.read32(base + 0x500) for base in (0x50042000, 0x50082000, 0x500C2000, 0x50102000)],
            'saadc_enable': target.read32(0x500D5500)}


TIMER_CHANNELS = {0: 6, 10: 8, 20: 6, 21: 6, 22: 6, 23: 6, 24: 6}


def adc_vectors():
    """! @brief 내부 입력 단독/역순 scan과 짧은/전체 buffer 및 보정 반복을 생성합니다. """
    for channels, flags, count in product((1, 2), range(4), (1, 32)):
        if count % channels == 0:
            yield (2, channels, flags, count, 100, 1)


def timer_vectors():
    """! @brief 44개 CC와 shortcut 네 조합 및 두 시간을 각각 10회 검증합니다. """
    for instance, channels in TIMER_CHANNELS.items():
        for channel, flags, top in product(range(channels), range(4), (1000, 10000)):
            yield (3, instance, channel, flags, top, 10)


def event_vectors():
    """! @brief 두 EGU의 모든 source channel과 같은 domain의 모든 DPPI channel을 조합합니다. """
    for domain, channels, egu_channels in ((10, 24, 16), (20, 16, 6)):
        for channel, source in product(range(channels), range(egu_channels)):
            yield (4, domain, channel, source, 1000, 10)


def bridge_vectors():
    """! @brief 8/8/16/4 bridge channel을 양방향으로 통과하며 모든 원격 DPPI channel을 사용합니다. """
    for pair, bridge_channels, remote_channels in ((0, 8, 8), (1, 8, 8), (2, 16, 24), (3, 4, 4)):
        for index in range(max(bridge_channels, remote_channels)):
            yield (5, pair, index % bridge_channels, index % remote_channels, 1000, 10)


def validate_adc(request, reply):
    channels, flags, count, repetitions = request[3:7]
    if any(reply[index] for index in (8, 9, 10, 17, 22)) or reply[11] != 1:
        raise ProtocolError('SAADC lifecycle failure')
    if reply[19:22] != [1, 1, repetitions] or reply[16] != count * repetitions:
        raise ProtocolError('SAADC guard/lease/count failure')
    if reply[26] != 2:
        raise ProtocolError('SAADC unsupported VSS input was not rejected')
    if reply[23] != (repetitions if flags & 2 else 0):
        raise ProtocolError('SAADC calibration completion count failure')
    for channel in range(channels):
        minimum, maximum = reply[12 + channel * 2:14 + channel * 2]
        if not 100 < minimum <= maximum < 4095:
            raise ProtocolError('SAADC internal source clipped/missing')
    if channels == 2:
        vdd, avdd = (1, 0) if flags & 1 else (0, 1)
        if reply[12 + 2 * vdd] <= reply[13 + 2 * avdd]:
            raise ProtocolError('SAADC VDD/AVDD scan order mismatch')


def validate_adc_snapshot(request, reply, raw):
    """! @brief SWD 원본을 별도로 해석해 DMA tail/guard와 마지막 scan 순서를 대조합니다. """
    if len(raw) != 96:
        raise ProtocolError('SAADC raw size mismatch')
    before = struct.unpack('<4I', raw[:16])
    samples = struct.unpack('<32h', raw[16:80])
    after = struct.unpack('<4I', raw[80:])
    if before != (0xD65A91C3,) * 4 or after != before:
        raise ProtocolError('SAADC raw guard damage')
    channels, flags, count = request[3:6]
    if any(value != 0x5555 for value in samples[count:]):
        raise ProtocolError('SAADC wrote beyond requested DMA length')
    for index, value in enumerate(samples[:count]):
        channel = index % channels
        if not reply[12 + channel * 2] <= value <= reply[13 + channel * 2]:
            raise ProtocolError('SAADC raw sample outside device statistics')
    if channels == 2:
        vdd, avdd = (1, 0) if flags & 1 else (0, 1)
        if min(samples[vdd:count:2]) <= max(samples[avdd:count:2]):
            raise ProtocolError('SAADC raw scan order mismatch')


def validate_timer(request, reply):
    flags, top, repetitions = request[5:8]
    if any(reply[index] for index in (8, 9, 10, 11, 17, 22, 23, 24)):
        raise ProtocolError('TIMER lifecycle/shortcut cleanup failure')
    if reply[27] != repetitions:
        raise ProtocolError('TIMER reserved block was not rejected')
    if reply[15] != 1 or reply[18:22] != [1, 1, 1, repetitions]:
        raise ProtocolError('TIMER compare/capture/stop/clear/lease failure')
    if flags & 2:
        expected = 0 if flags & 1 else top
        if reply[12:15] != [expected, expected, 0] or reply[26] != expected:
            raise ProtocolError('TIMER automatic clear/stop mismatch')
    else:
        expected = reply[25] % top if flags & 1 else reply[25]
        if reply[14] > top // 20 or abs(reply[26] - expected) > top // 20:
            raise ProtocolError('TIMER capture differs from elapsed time by more than 5% of TOP')
        if not reply[12] <= reply[26] <= reply[13] or reply[25] < top:
            raise ProtocolError('TIMER raw observation statistics mismatch')


def validate_event(request, reply):
    events, repetitions = request[6:8]
    if any(reply[index] for index in (8, 9, 10, 11, 17, 18, 19)) or reply[20:22] != [1, repetitions]:
        raise ProtocolError('EGU/DPPI/PPIB lifecycle/overflow/lease failure')
    if reply[12:14] != [events * repetitions, repetitions]:
        raise ProtocolError('EGU/DPPI/PPIB event or disable count mismatch')
    if reply[24] != repetitions or reply[26] != reply[22] or (request[2] == 4 and reply[25] != repetitions):
        raise ProtocolError('EGU/DPPI/PPIB reservation conflict was not rejected')
    if reply[23] == 0 or reply[22] != reply[23] * repetitions or (request[2] == 4 and reply[14] != repetitions):
        raise ProtocolError('DPPI disconnect/group release count mismatch')



def time_vectors():
    for duration, sleep in product((1000, 10000), (0, 1)):
        yield (6, duration, sleep, 100, 0, 1)


def validate_time(request, reply):
    duration, sleep_ms, repetitions = request[3:6]
    minimum = duration if sleep_ms else duration - duration // 20
    maximum = duration + 3000 if sleep_ms else duration + duration // 20
    if any(reply[index] for index in (8, 9, 10)) or reply[20:22] != [1, repetitions]:
        raise ProtocolError('GRTC/TIMER lifecycle failure')
    if not minimum <= reply[12] <= reply[13] <= maximum or reply[16] > duration // 20:
        raise ProtocolError('GRTC micros/delay differs from TIMER capture')
    if not reply[12] // 1000 - 1 <= reply[14] <= reply[15] <= reply[13] // 1000 + 1:
        raise ProtocolError('GRTC millis differs from micros')
