"""! @brief S/U별 유지 결선·exact 두 image의 실행 경계를 검증합니다. """
from __future__ import annotations

import hashlib
import json
import struct

import v04_t13_cases as catalog
import v04_t13_plan as plan
from v04_protocol import ProtocolError


def catalog_hash():
    """! @brief GPIO·시간·실행 ID 전체를 포함하는 펌웨어와 같은 digest입니다. """
    return hashlib.sha256(json.dumps(catalog.definition(), sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def harness_code(harness):
    """! @brief 실행기가 요청한 S/U만 firmware identity 값으로 변환합니다. """
    if harness not in ('S', 'U'):
        raise ProtocolError('T13 unknown harness')
    return 2 if harness == 'S' else 3


def validate(grant, images, uids, *, harness='S'):
    """! @brief 과거 C 확인·다른 UID·소스 혼합과 유지되지 않은 결선을 거부합니다. """
    if len(images) != 2 or len(uids) != 2 or uids[0].lower() == uids[1].lower():
        raise ProtocolError('T13 requires two distinct exact roles')
    harness_code(harness)
    expected = {
        'type': f'v04-t13-{harness.lower()}-session', 'harness': harness,
        'catalog_sha256': catalog_hash(),
        'uid_sha256': [hashlib.sha256(uid.lower().encode()).hexdigest() for uid in uids],
        'maintain_harness_until_end': True, 'notify_before_usb_wiring_switch_changes': True,
        'dap_uart_disconnected_both': True, 'swd_connected_both': True,
        'equal_io_voltage_confirmed': True, 'power_rails_not_joined': True,
        'common_ground_confirmed': True, 'links_match_catalog': True,
        'external_pullups_disconnected': True, 'extra_outputs_disconnected': True,
    }
    if any(type(grant.get(key)) is not type(value) or grant.get(key) != value for key, value in expected.items()):
        raise ProtocolError(f'T13 {harness} current wiring or target report mismatch')
    for key in ('user_wiring_report', 'user_maintain_reply'):
        if not isinstance(grant.get(key), str) or not grant[key].strip():
            raise ProtocolError('T13 explicit current user report missing')
    for role, image in enumerate(images, 1):
        if (image['role'] != role or image['board_revision'] != plan.plan()['board_revision'] or
                image['core_revision'] != images[0]['core_revision']):
            raise ProtocolError('T13 exact source or board mismatch')


def verify_profile(device, harness='S'):
    """! @brief 구 C image나 다른 계획으로 출력 명령을 실행하지 않습니다. """
    expected = [0x54313300 | harness_code(harness),
                *struct.unpack('<8I', bytes.fromhex(catalog_hash()))]
    words = device.command(96, timeout=2)
    if len(words) != 10 or words[:9] != expected:
        raise ProtocolError(f'T13 compiled {harness} wiring/catalog identity mismatch')
    return words[9]


class Continuity:
    """! @brief 한 연결에서만 유효하며 단절·reset 뒤 자동 재접속하지 않습니다. """
    def __init__(self, grant, images, uids, devices, enumerate_uids, verify_identity, *,
                 harness='S'):
        self.grant, self.images, self.uids, self.devices = grant, images, uids, devices
        self.enumerate_uids, self.verify_identity = enumerate_uids, verify_identity
        self.harness = harness
        harness_code(harness)
        self.faulted = False

    def check(self):
        """! @brief 실제 출력 전 현재 대상·runtime source와 유지 결선을 재검사합니다. """
        try:
            if self.faulted:
                raise ProtocolError(f'T13 {self.harness} session faulted')
            validate(self.grant, self.images, self.uids, harness=self.harness)
            if not set(self.uids).issubset(self.enumerate_uids()):
                raise ProtocolError('T13 exact probe disconnected')
            for device, image in zip(self.devices, self.images):
                raw = bytes(device.target.read_memory_block8(image['symbols']['v04_identity'], 64))
                self.verify_identity(raw, image['role'], image['core_revision'])
                if struct.unpack('<I', raw[12:16])[0] != (0x54313300 | harness_code(self.harness)):
                    raise ProtocolError(f'T13 {self.harness} runtime profile changed')
        except BaseException:
            self.faulted = True
            raise
