"""! @brief 공통 결선의 exact flash·연속성 확인·GPIO/PWM/QDEC/I2S 실기를 수행합니다. """
from __future__ import annotations

import argparse
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import sys

import v04_common_gpio as gpio
import v04_common_qdec as qdec
import v04_qdec_read_diagnostic as qdec_diagnostic
import v04_qdec_clear_diagnostic as clear_diagnostic
import v04_common_i2s as i2s
import v04_common_pwm_modes as pwm_modes
import v04_pwm_capture as pwm
import v04_common_session as common
import v04_pair as pair
import v04_wiring as wiring
from v04_fixture_run import unique_fields
from v04_protocol import ProbeLocks, ProtocolError, validate_pair


def arguments(argv=None):
    """! @brief 실행 옵션 없이는 probe에 접근하지 않습니다. """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dut', required=True)
    parser.add_argument('--peer', required=True)
    parser.add_argument('--build-root', required=True, type=Path)
    parser.add_argument('--pyocd', required=True, type=Path)
    parser.add_argument('--session-grant', required=True, type=Path)
    parser.add_argument('--evidence', type=Path)
    parser.add_argument('--section', choices=('all', 'gpio', 'task', 'edge', 'qdec', 'qdec-read-diagnostic', 'qdec-clear-diagnostic', 'pwm', 'pwm-modes', 'i2s', 'signals', 'additional-signals', 'qdec-i2s'), default='all')
    parser.add_argument('--execute-fixture', action='store_true')
    parser.add_argument('--cmsis-dap-limit-packets', action='store_true')
    parser.add_argument('--swd-frequency-hz', type=int, default=10000000)
    args = parser.parse_args(argv)
    if args.swd_frequency_hz != 10000000 or (args.execute_fixture and args.evidence is None):
        raise ProtocolError('common run requires 10 MHz and exclusive evidence path')
    return args


def main(argv=None):
    """! @brief 각 새 image는 결선 checker를 통과해야 기능 출력으로 전환합니다. """
    args = arguments(argv)
    uids = validate_pair(args.dut, args.peer)
    images = [pair.inspect_image(pair.ROOT, args.build_root.resolve(), role) for role in (1, 2)]
    grant_bytes = args.session_grant.read_bytes()
    grant = json.loads(grant_bytes, object_pairs_hook=unique_fields)
    common.validate(grant, images, uids, 502)
    evidence = {'schema_version': 1, 'type': 'v04-common-functional-campaign', 'status': 'preflight',
                'core_revision': images[0]['core_revision'], 'board_revision': images[0]['board_revision'],
                'catalog_sha256': pair.sha256_file(common.CATALOG),
                'session_grant_sha256': hashlib.sha256(grant_bytes).hexdigest(),
                'section': args.section, 'swd_frequency_hz': 10000000,
                'external_wiring_executed': False,
                'devices': [{'role': image['role'], 'uid_sha256': hashlib.sha256(uid.encode()).hexdigest(),
                             'hex_sha256': image['sha256'], 'elf_sha256': image['elf_sha256'],
                             'record_sha256': image['record_sha256']} for uid, image in zip(uids, images)],
                'results': []}
    if args.section in ('qdec-read-diagnostic', 'qdec-clear-diagnostic'):
        evidence['type'] = 'v04-common-' + args.section
        evidence['functional_regression'] = False
    if not args.execute_fixture:
        print(json.dumps(evidence, ensure_ascii=False, indent=2))
        print('V04_COMMON_PREFLIGHT_ONLY; no probe access, flash, reset or external output')
        return 0
    with pair.evidence_session(args.evidence, evidence) as journal:
        from pyocd.core.helpers import ConnectHelper
        with ProbeLocks(uids), ExitStack() as stack:
            def available():
                """! @brief 이전 COM 번호에 의존하지 않고 exact probe를 새로 열거합니다. """
                return {probe.unique_id.lower() for probe in ConnectHelper.get_all_connected_probes(blocking=False)}
            if not set(uids).issubset(available()):
                raise ProtocolError('both exact probes required before flash')
            devices = []
            for uid, image in zip(uids, images):
                common.validate(grant, images, uids, 502)
                device, flash = pair.boot_exact(stack, ConnectHelper, args.pyocd, uid, image,
                    10000000, cmsis_dap_limit_packets=args.cmsis_dap_limit_packets)
                devices.append(device)
                evidence['devices'][image['role'] - 1]['flash'] = flash
            continuity = common.Continuity(grant, images, uids, devices, available, pair.verify_identity)
            completed = 0
            def append(case_id, result):
                """! @brief 첫 실패 원본·cleanup·개별 기능을 구분해 즉시 저장합니다. """
                nonlocal completed
                entry = {'id': case_id, **result}
                evidence['results'].append(entry)
                journal.write(json.dumps(entry, ensure_ascii=False) + '\n')
                journal.flush()
                if result.get('status') == 'passed' and 'WIRING' not in case_id:
                    completed += 1
                    if completed % 10 == 0:
                        print(f'COMMON_PHYSICAL_PASSED={completed};SECTION={args.section}', flush=True)
            evidence['external_wiring_executed'] = True
            wiring.run_checks(devices, append, lambda: continuity.check(501))
            if args.section in ('signals', 'additional-signals', 'qdec-i2s'):
                for name, execute in (('pwm', pwm.run_common), ('pwm-modes', pwm_modes.run),
                                      ('qdec', qdec.run), ('i2s', i2s.run)):
                    if args.section == 'additional-signals' and name == 'pwm':
                        continue
                    if args.section == 'qdec-i2s' and name in ('pwm', 'pwm-modes'):
                        continue
                    print(f'COMMON_SECTION_START={name}', flush=True)
                    execute(devices, continuity.check, append)
                    print(f'COMMON_SECTION_PASS={name}', flush=True)
            elif args.section == 'qdec':
                qdec.run(devices, continuity.check, append)
            elif args.section == 'qdec-read-diagnostic':
                qdec_diagnostic.run(devices, continuity.check, append)
            elif args.section == 'qdec-clear-diagnostic':
                clear_diagnostic.run(devices, continuity.check, append)
            elif args.section == 'pwm':
                pwm.run_common(devices, continuity.check, append)
            elif args.section == 'i2s':
                i2s.run(devices, continuity.check, append)
            elif args.section == 'pwm-modes':
                pwm_modes.run(devices, continuity.check, append)
            else:
                gpio.run(devices, continuity.check, append, section=args.section)
            continuity.check(502)
    print('V04_COMMON_CAMPAIGN_PASS', flush=True)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ProtocolError, OSError, ValueError) as error:
        print(f'V04_COMMON_FAIL: {error}', file=sys.stderr)
        raise SystemExit(1)
