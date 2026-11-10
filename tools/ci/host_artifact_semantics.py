"""! @brief Host별 debug 경로와 분리해 실제 ARM ELF load image·HEX 주소 byte를 비교합니다. """
from __future__ import annotations

import hashlib
from pathlib import Path
import struct


class ArtifactFormatError(ValueError):
    """! @brief 손상되거나 지원 범위를 벗어난 target artifact를 나타냅니다. """


def bounded(data: bytes, offset: int, size: int) -> bytes:
    """! @brief 파일 경계를 넘는 ELF table·payload 참조를 거부합니다. """
    if offset < 0 or size < 0 or offset > len(data) or size > len(data) - offset:
        raise ArtifactFormatError('ELF table 또는 payload가 파일 경계를 벗어났습니다.')
    return data[offset:offset + size]


def elf_semantics(path: Path) -> dict:
    """! @brief ELF32 little-endian ARM의 PT_LOAD byte와 실제 할당 section을 추출합니다. """
    data = path.read_bytes()
    if len(data) < 52 or data[:7] != b'\x7fELF\x01\x01\x01':
        raise ArtifactFormatError('ELF32 little-endian target image가 아닙니다.')
    header = struct.unpack('<16sHHIIIIIHHHHHH', bounded(data, 0, 52))
    _, kind, machine, version, entry, phoff, shoff, flags, ehsize, phsize, phcount, shsize, shcount, names_index = header
    if (kind != 2 or machine != 40 or version != 1 or ehsize != 52 or phsize != 32 or shsize != 40
            or not phcount or not shcount or names_index >= shcount):
        raise ArtifactFormatError('ARM 실행 image의 ELF header·table 크기가 다릅니다.')
    bounded(data, phoff, phsize * phcount)
    bounded(data, shoff, shsize * shcount)
    segments = []
    digest = hashlib.sha256(struct.pack('<II', entry, flags))
    for index in range(phcount):
        row = struct.unpack('<IIIIIIII', bounded(data, phoff + index * phsize, phsize))
        item_type, offset, virtual, physical, file_size, memory_size, item_flags, alignment = row
        if item_type != 1:
            continue
        if file_size > memory_size or virtual + memory_size > 1 << 32 or physical + file_size > 1 << 32:
            raise ArtifactFormatError('ARM load segment의 주소·파일·메모리 크기가 다릅니다.')
        body = bounded(data, offset, file_size)
        segments.append({'virtual_address': virtual, 'physical_address': physical, 'file_size': file_size,
            'memory_size': memory_size, 'flags': item_flags, 'alignment': alignment,
            'data_sha256': hashlib.sha256(body).hexdigest()})
    if not segments:
        raise ArtifactFormatError('ARM ELF에 실제 load segment가 없습니다.')
    segments.sort(key=lambda row: (row['physical_address'], row['virtual_address'], row['flags']))
    for row in segments:
        digest.update(struct.pack('<IIIIII', *(row[key] for key in ('virtual_address', 'physical_address',
            'file_size', 'memory_size', 'flags', 'alignment'))))
        digest.update(bytes.fromhex(row['data_sha256']))
    headers = [struct.unpack('<IIIIIIIIII', bounded(data, shoff + index * shsize, shsize)) for index in range(shcount)]
    string_header = headers[names_index]
    names = bounded(data, string_header[4], string_header[5])
    sections = []
    for row in headers:
        name_index, item_type, item_flags, address, offset, size, _link, _info, alignment, _entry_size = row
        if not item_flags & 2:
            continue
        if name_index >= len(names) or b'\0' not in names[name_index:]:
            raise ArtifactFormatError('ARM section 이름 table이 잘못되었습니다.')
        try:
            name = names[name_index:].split(b'\0', 1)[0].decode('utf-8')
        except UnicodeDecodeError as error:
            raise ArtifactFormatError('ARM section 이름이 UTF-8이 아닙니다.') from error
        body_hash = None if item_type == 8 else hashlib.sha256(bounded(data, offset, size)).hexdigest()
        sections.append({'name': name, 'type': item_type, 'flags': item_flags, 'address': address,
            'size': size, 'alignment': alignment, 'data_sha256': body_hash})
    if not sections:
        raise ArtifactFormatError('ARM ELF에 할당 section이 없습니다.')
    sections.sort(key=lambda row: (row['address'], row['name'], row['type']))
    return {'file_sha256': hashlib.sha256(data).hexdigest(), 'machine': 'ARM_ELF32_LE', 'entry': entry,
        'flags': flags, 'load_sha256': digest.hexdigest(), 'load_segments': segments, 'allocated_sections': sections}


def hex_semantics(path: Path, fixture_public_key: bytes | None = None) -> dict:
    """! @brief HEX 줄 분할·기록 순서를 제거하고 실제 flash 주소와 byte를 정규화합니다. """
    blocks = []
    base = 0
    finished = False
    total = 0
    starts = {}
    for line in path.read_text(encoding='ascii').splitlines():
        line = line.strip()
        if not line:
            continue
        if finished or not line.startswith(':'):
            raise ArtifactFormatError('HEX 종료 뒤 record 또는 잘못된 줄이 있습니다.')
        try:
            record = bytes.fromhex(line[1:])
        except ValueError as error:
            raise ArtifactFormatError('HEX record에 16진수가 아닌 값이 있습니다.') from error
        if len(record) < 5 or len(record) != record[0] + 5 or sum(record) & 255:
            raise ArtifactFormatError('HEX record 길이 또는 checksum이 다릅니다.')
        size, address, kind = record[0], int.from_bytes(record[1:3], 'big'), record[3]
        body = record[4:-1]
        if kind == 0:
            total += size
            if total > 16 * 1024 * 1024 or address + size > 65536 or base + address + size > 1 << 32:
                raise ArtifactFormatError('HEX 데이터가 target 주소·분석 크기 범위를 벗어났습니다.')
            if body:
                blocks.append((base + address, body))
        elif kind == 1 and size == 0 and address == 0:
            finished = True
        elif kind in (2, 4) and size == 2 and address == 0:
            base = int.from_bytes(body, 'big') << (4 if kind == 2 else 16)
        elif kind in (3, 5) and size == 4 and address == 0:
            value = body.hex()
            if kind in starts and starts[kind] != value:
                raise ArtifactFormatError('HEX 시작 주소 record가 충돌합니다.')
            starts[kind] = value
        else:
            raise ArtifactFormatError('지원하지 않거나 잘못된 HEX record입니다.')
    if not finished or not blocks:
        raise ArtifactFormatError('HEX의 데이터 또는 종료 record가 없습니다.')
    merged = []
    for address, body in sorted(blocks):
        if not merged or address > merged[-1][0] + len(merged[-1][1]):
            merged.append((address, bytearray(body)))
            continue
        previous_address, previous = merged[-1]
        offset = address - previous_address
        overlap = min(len(previous) - offset, len(body))
        if previous[offset:offset + overlap] != body[:overlap]:
            raise ArtifactFormatError('HEX의 겹치는 주소에서 서로 다른 byte가 발견됐습니다.')
        previous.extend(body[overlap:])
    digest = hashlib.sha256()
    fixture_digest = hashlib.sha256()
    replacements = []
    if fixture_public_key is not None and not 32 <= len(fixture_public_key) <= 512:
        raise ArtifactFormatError('CI public key fixture 길이가 잘못되었습니다.')
    ranges = []
    for address, body in merged:
        digest.update(struct.pack('<II', address, len(body)))
        digest.update(body)
        normalized = bytearray(body)
        if fixture_public_key is not None:
            offset = normalized.find(fixture_public_key)
            while offset >= 0:
                replacements.append({'address': address + offset, 'size': len(fixture_public_key)})
                normalized[offset:offset + len(fixture_public_key)] = b'\0' * len(fixture_public_key)
                offset = normalized.find(fixture_public_key, offset + len(fixture_public_key))
        fixture_digest.update(struct.pack('<II', address, len(normalized)))
        fixture_digest.update(normalized)
        ranges.append({'address': address, 'size': len(body), 'data_sha256': hashlib.sha256(body).hexdigest()})
    result = {'file_sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'data_sha256': digest.hexdigest(),
        'ranges': ranges, 'data_bytes': sum(row['size'] for row in ranges),
        'start_records': {str(key): value for key, value in sorted(starts.items())}}
    if fixture_public_key is not None:
        if len(replacements) != 1:
            raise ArtifactFormatError('실제 boot image에 해당 CI public key가 정확히 한 번 있어야 합니다.')
        result.update(normalized_fixture_sha256=fixture_digest.hexdigest(), fixture_masked_ranges=replacements,
            fixture_public_key_sha256=hashlib.sha256(fixture_public_key).hexdigest())
    return result
