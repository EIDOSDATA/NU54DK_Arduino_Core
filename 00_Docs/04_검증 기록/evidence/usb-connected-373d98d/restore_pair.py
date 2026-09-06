"""! @brief 마지막 exact DUT/peer image를 준비하고 외부 명령 없이 identity와 ping만 확인합니다. """
from runtime import *
from contextlib import ExitStack
from datetime import datetime, timezone
import secrets
import struct
from v04_pair import inspect_image, boot_exact, verify_identity, evidence_session
from v04_protocol import ProbeLocks, ProtocolError

images = [inspect_image(REPO, BUILD, role) for role in (1, 2)]
evidence = {'type': 'exact-pair-handoff-identity-and-ping-only', 'core_revision': SOURCE, 'created_at_utc': datetime.now(timezone.utc).isoformat(), 'external_fixture_commands_executed': False, 'onboard_full_suite_executed': False, 'swd_frequency_hz': 10000000, 'devices': []}
with evidence_session(WORK / ('pair-handoff-' + SOURCE[:7] + '.json'), evidence) as log:
    with ProbeLocks(UIDS), ExitStack() as stack:
        for uid, digest, image in zip(UIDS, HASHES, images):
            device, flash = boot_exact(stack, ConnectHelper, BUNDLE / 'opt/bin/Scripts/pyocd.exe', uid, image, 10000000)
            challenge = list(struct.unpack('<4I', secrets.token_bytes(16)))
            reply = device.command(1, challenge)
            if reply != [value ^ (0xA5000000 | image['role']) for value in challenge]:
                raise ProtocolError('independent ping oracle failed')
            identity = bytes(device.target.read_memory_block8(image['symbols']['v04_identity'], 64))
            verify_identity(identity, image['role'], SOURCE)
            row = {'role': image['role'], 'probe_id_sha256': digest, 'hex_sha256': image['sha256'], 'elf_sha256': image['elf_sha256'], 'record_sha256': image['record_sha256'], 'flash': flash, 'cpuid': hex(device.target.read32(0xE000ED00)), 'runtime_identity_hex': identity.hex(), 'challenge': challenge, 'response': reply, 'state': device.target.get_state().name, 'status': 'passed'}
            evidence['devices'].append(row)
            log.write(json.dumps(row) + '\n')
            log.flush()
            print('HANDOFF_ROLE_PASS=' + str(image['role']), flush=True)
print('PAIR_HANDOFF_IDENTITY_AND_PING_PASS=2;EXTERNAL_T11_NOT_RUN', flush=True)
