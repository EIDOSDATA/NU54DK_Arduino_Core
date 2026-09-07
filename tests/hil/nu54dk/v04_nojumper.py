"""! @brief 무점퍼 PWM의 exact image·SWD 명령·독립 판정과 실패 원본을 관리합니다. """
from __future__ import annotations

from itertools import product
from pathlib import Path
import secrets
import time

from m24_uarte_onboard import git_output, parse_build_record, sha256_file
from v04_protocol import ProtocolError

MAGIC = 0x4E4A5031
SIZES = {'nojumper_request': 32, 'nojumper_response': 128, 'nojumper_ready': 16,
         'nojumper_revision': 41}


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
        if ready[:2] != [MAGIC, 1] or revision != self.image['source'].encode('ascii') + b'\0':
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
                    append({'request': request, 'reply': reply})
                    validate_reply(request, reply)
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
            'dppi20_channel0': target.read32(0x500C2500) & 1}
