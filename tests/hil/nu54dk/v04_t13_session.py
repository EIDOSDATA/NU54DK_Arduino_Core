"""! @brief S 전용 현재 확인·고정 만료·exact 두 image의 실행 경계를 검증합니다. """
from __future__ import annotations

import hashlib
import json
import math
import struct
import time

import v04_t13_cases as catalog
import v04_t13_plan as plan
from v04_protocol import ProtocolError


def catalog_hash():
    """! @brief GPIO·시간·실행 ID 전체를 포함하는 펌웨어와 같은 digest입니다. """
    return hashlib.sha256(json.dumps(catalog.definition(), sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def validate(grant, images, uids, *, now=None):
    """! @brief 과거 C 확인·다른 UID·소스 혼합·미래 확인·12시간 초과를 거부합니다. """
    now = time.time() if now is None else now
    if len(images) != 2 or len(uids) != 2 or uids[0].lower() == uids[1].lower():
        raise ProtocolError('T13 requires two distinct exact roles')
    expected = {
        'type': 'v04-t13-s-session', 'harness': 'S', 'catalog_sha256': catalog_hash(),
        'uid_sha256': [hashlib.sha256(uid.lower().encode()).hexdigest() for uid in uids],
        'maintain_harness_until_end': True, 'notify_before_usb_wiring_switch_changes': True,
        'dap_uart_disconnected_both': True, 'swd_connected_both': True,
        'equal_io_voltage_confirmed': True, 'power_rails_not_joined': True,
        'common_ground_confirmed': True, 'links_match_catalog': True,
        'external_pullups_disconnected': True, 'extra_outputs_disconnected': True,
    }
    if any(type(grant.get(key)) is not type(value) or grant.get(key) != value for key, value in expected.items()):
        raise ProtocolError('T13 S current wiring or target report mismatch')
    start, end = grant.get('confirmed_at_unix'), grant.get('expires_at_unix')
    if (type(start) not in (int, float) or type(end) not in (int, float) or
            not all(math.isfinite(value) for value in (start, end, now)) or
            not start <= now < end or not 0 < end - start <= 43200):
        raise ProtocolError('T13 S confirmation expired or invalid')
    for key in ('user_wiring_report', 'user_maintain_reply'):
        if not isinstance(grant.get(key), str) or not grant[key].strip():
            raise ProtocolError('T13 explicit current user report missing')
    for role, image in enumerate(images, 1):
        if (image['role'] != role or image['board_revision'] != plan.plan()['board_revision'] or
                image['core_revision'] != images[0]['core_revision']):
            raise ProtocolError('T13 exact source or board mismatch')


def verify_profile(device):
    """! @brief 구 C image나 다른 계획으로 출력 명령을 실행하지 않습니다. """
    expected = [0x54313302, *struct.unpack('<8I', bytes.fromhex(catalog_hash()))]
    words = device.command(96, timeout=2)
    if len(words) != 10 or words[:9] != expected:
        raise ProtocolError('T13 compiled S wiring/catalog identity mismatch')
    return words[9]


class Continuity:
    """! @brief 한 연결에서만 유효하며 만료·단절·reset 뒤 자동 재접속하지 않습니다. """
    def __init__(self, grant, images, uids, devices, enumerate_uids, verify_identity):
        self.grant, self.images, self.uids, self.devices = grant, images, uids, devices
        self.enumerate_uids, self.verify_identity = enumerate_uids, verify_identity
        self.deadline = time.monotonic() + grant['expires_at_unix'] - time.time()
        self.faulted = False

    def check(self):
        """! @brief 실제 출력 전 현재 대상·runtime source와 고정 만료를 재검사합니다. """
        try:
            if self.faulted or time.monotonic() >= self.deadline:
                raise ProtocolError('T13 S session faulted or expired')
            validate(self.grant, self.images, self.uids)
            if not set(self.uids).issubset(self.enumerate_uids()):
                raise ProtocolError('T13 exact probe disconnected')
            for device, image in zip(self.devices, self.images):
                raw = bytes(device.target.read_memory_block8(image['symbols']['v04_identity'], 64))
                self.verify_identity(raw, image['role'], image['core_revision'])
                if struct.unpack('<I', raw[12:16])[0] != 0x54313302:
                    raise ProtocolError('T13 S runtime profile changed')
        except BaseException:
            self.faulted = True
            raise
