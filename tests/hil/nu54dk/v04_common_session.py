"""! @brief 사용자가 유지하기로 확인한 공통 결선 실행의 고정 만료·대상 계약입니다. """
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import time

from v04_protocol import ProtocolError

CATALOG = Path(__file__).with_name('v04_common_bundle.json')
ALLOWED = (501, 502, 508, 520, 530)
MAX_SECONDS = 12 * 3600


def validate(grant, images, uids, fixture_id, *, now=None):
    """! @brief 단순한 과거 확인서·다른 결선·무기한/미래 확인을 거부합니다. """
    now = time.time() if now is None else now
    catalog = json.loads(CATALOG.read_text(encoding='utf-8'))
    expected = {
        'type': 'v04-fixed-common-harness-session',
        'catalog_sha256': hashlib.sha256(CATALOG.read_bytes()).hexdigest(),
        'board_revision': catalog['board_revision'],
        'uid_sha256': [hashlib.sha256(uid.lower().encode()).hexdigest() for uid in uids],
        'allowed_fixture_ids': list(ALLOWED),
        'maintain_harness_until_end': True,
        'notify_before_usb_wiring_switch_changes': True,
        'dap_uart_disconnected_both': True,
        'swd_connected_both': True,
        'power_rails_not_joined': True,
        'equal_io_voltage_confirmed': True,
        'common_ground_confirmed': True,
        'links_match_catalog': True,
        'pullups_match_catalog': True,
        'extra_outputs_disconnected': True,
    }
    if fixture_id not in ALLOWED or len(images) != 2 or len(uids) != 2 or uids[0].lower() == uids[1].lower():
        raise ProtocolError('fixed common session target mismatch')
    if any(type(grant.get(key)) is not type(value) or grant.get(key) != value for key, value in expected.items()):
        raise ProtocolError('fixed common session conditions missing or foreign')
    start, end = grant.get('confirmed_at_unix'), grant.get('expires_at_unix')
    if (type(start) not in (int, float) or type(end) not in (int, float) or
            not all(math.isfinite(value) for value in (start, end, now)) or
            not start <= now < end or not 0 < end - start <= MAX_SECONDS):
        raise ProtocolError('fixed common session expired or invalid deadline')
    for key in ('confirmed_by', 'user_condition_reply', 'user_maintain_reply', 'session_id'):
        if not isinstance(grant.get(key), str) or not grant[key].strip():
            raise ProtocolError('explicit current session report missing')
    if any(image['role'] != role or image['board_revision'] != catalog['board_revision'] or
           image['core_revision'] != images[0]['core_revision'] for role, image in enumerate(images, 1)):
        raise ProtocolError('fixed common image identity mismatch')


class Continuity:
    """! @brief 한 probe 연결 수명에만 유효하며 예외 뒤 재사용하지 않는 세션 감시입니다. """
    def __init__(self, grant, images, uids, devices, enumerate_uids, verify_identity, *, monotonic=time.monotonic):
        self.grant, self.images, self.uids, self.devices = grant, images, uids, devices
        self.enumerate_uids, self.verify_identity = enumerate_uids, verify_identity
        self.monotonic = monotonic
        self.origin = monotonic()
        self.wall_origin = time.time()
        self.deadline = self.origin + max(0, grant['expires_at_unix'] - self.wall_origin)
        self.faulted = False

    def check(self, fixture_id):
        """! @brief 단절·identity 변경·시간 변경·만료에서 다음 출력을 차단합니다. """
        try:
            if self.faulted or self.monotonic() >= self.deadline:
                raise ProtocolError('common session faulted or expired')
            validate(self.grant, self.images, self.uids, fixture_id)
            if not set(self.uids).issubset(self.enumerate_uids()):
                raise ProtocolError('common session probe disconnected; no substitution or retry')
            for device, image in zip(self.devices, self.images):
                raw = bytes(device.target.read_memory_block8(image['symbols']['v04_identity'], 64))
                self.verify_identity(raw, image['role'], image['core_revision'])
        except BaseException:
            self.faulted = True
            raise
