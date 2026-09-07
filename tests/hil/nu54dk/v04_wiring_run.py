"""! @brief 현재 확인서와 exact image가 있어야 실행되는 17신호 결선 checker CLI입니다. """
from __future__ import annotations

import argparse
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import sys

import v04_fixture as fixture
from v04_fixture_run import unique_fields
import v04_pair as pair
import v04_wiring as wiring
from v04_protocol import ProbeLocks, ProtocolError, validate_pair


def arguments(argv=None):
    """! @brief 실행 옵션이 없으면 probe 접근 없는 준비만 허용합니다. """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dut', required=True)
    parser.add_argument('--peer', required=True)
    parser.add_argument('--build-root', required=True, type=Path)
    parser.add_argument('--pyocd', required=True, type=Path)
    parser.add_argument('--swd-frequency-hz', type=int, default=10_000_000)
    parser.add_argument('--cmsis-dap-limit-packets', action='store_true')
    parser.add_argument('--confirmation', type=Path)
    parser.add_argument('--evidence', type=Path)
    parser.add_argument('--execute-fixture', action='store_true')
    args = parser.parse_args(argv)
    if args.swd_frequency_hz != 10_000_000:
        raise ProtocolError('wiring check requires SWD 10 MHz')
    if args.execute_fixture and (args.confirmation is None or args.evidence is None):
        raise ProtocolError('wiring check requires current confirmation and new evidence')
    return args


def main(argv=None):
    """! @brief 이전 fixture 승인이나 임의 GPIO 명령을 재사용하지 않습니다. """
    args = arguments(argv)
    uids = validate_pair(args.dut, args.peer)
    if not args.pyocd.is_file():
        raise ProtocolError('pyOCD executable missing')
    images = [pair.inspect_image(pair.ROOT, args.build_root.resolve(), role) for role in (1, 2)]
    catalog, selected = fixture.fixture_contract(501, catalog_path=wiring.CATALOG)
    evidence = {
        'schema_version': 1, 'type': 'v04-common-wiring-check', 'status': 'preflight',
        'fixture_id': 501, 'fixture_revision': catalog['revision'],
        'catalog_sha256': pair.sha256_file(wiring.CATALOG),
        'core_revision': images[0]['core_revision'], 'board_revision': images[0]['board_revision'],
        'scope': '17-signal-connectivity-not-gpio-api-or-t12-completion',
        'swd_frequency_hz': args.swd_frequency_hz,
        'cmsis_dap_limit_packets': args.cmsis_dap_limit_packets,
        'external_wiring_executed': False,
        'devices': [{'role': image['role'], 'uid_sha256': hashlib.sha256(uid.encode()).hexdigest(),
                     'hex_sha256': image['sha256'], 'elf_sha256': image['elf_sha256'],
                     'record_sha256': image['record_sha256']} for uid, image in zip(uids, images)],
        'results': [],
    }
    if not args.execute_fixture:
        print(json.dumps({**evidence, 'fixture': selected,
                          'confirmation_template': fixture.confirmation_template(
                              images, uids, 501, catalog_path=wiring.CATALOG)}, ensure_ascii=False, indent=2))
        print('V04_WIRING_PREFLIGHT_ONLY; no probe access, flash, reset or external output')
        return 0
    confirmation_bytes = args.confirmation.read_bytes()
    confirmation = json.loads(confirmation_bytes, object_pairs_hook=unique_fields)
    fixture.validate_confirmation(confirmation, images, uids, 501, catalog_path=wiring.CATALOG)
    evidence['confirmation_sha256'] = hashlib.sha256(confirmation_bytes).hexdigest()
    with pair.evidence_session(args.evidence, evidence) as journal:
        from pyocd.core.helpers import ConnectHelper
        with ProbeLocks(uids), ExitStack() as stack:
            available = {probe.unique_id.lower() for probe in ConnectHelper.get_all_connected_probes(blocking=False)}
            if not set(uids).issubset(available):
                raise ProtocolError('both confirmed probes required; no automatic substitution')
            devices = []
            for uid, image in zip(uids, images):
                device, flash = pair.boot_exact(stack, ConnectHelper, args.pyocd, uid, image,
                    args.swd_frequency_hz, cmsis_dap_limit_packets=args.cmsis_dap_limit_packets)
                devices.append(device)
                evidence['devices'][image['role'] - 1]['flash'] = flash

            def append(case_id, result):
                """! @brief 관측·기능 판정·cleanup을 원래 상태로 구분하여 보존합니다. """
                entry = {'id': case_id, **result}
                evidence['results'].append(entry)
                journal.write(json.dumps(entry, ensure_ascii=False) + '\n')
                journal.flush()

            evidence['external_wiring_executed'] = True
            wiring.run_confirmed(devices, images, uids, confirmation, append)
            for device, image in zip(devices, images):
                pair.verify_identity(bytes(device.target.read_memory_block8(
                    image['symbols']['v04_identity'], 64)), image['role'], image['core_revision'])
    print('V04_WIRING_PASS=102 net-rounds;2 pulse-timeouts;1 dual-lease-timeout')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ProtocolError, OSError, ValueError) as error:
        print(f'V04_WIRING_FAIL: {error}', file=sys.stderr)
        raise SystemExit(1)
