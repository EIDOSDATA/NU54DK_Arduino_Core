"""! @brief 430 계획·DMA 완료·수신 원본·cleanup과 exact image를 독립 대조합니다. """
from pathlib import Path
import hashlib
import itertools
import json
import struct

WORK = Path(__file__).resolve().parent
SOURCE = (WORK / 'source.txt').read_text().strip()
path = WORK / 'fixture430-attempt1.json'
result = json.loads(path.read_text(encoding='utf-8'))
journal_path = path.with_suffix('.json.jsonl')
entries = [json.loads(line) for line in journal_path.read_text(encoding='utf-8').splitlines()]
payload_path = WORK / 'i2s-payloads.jsonl'
payloads = [json.loads(line) for line in payload_path.read_text(encoding='utf-8').splitlines()]
assert result['status'] == 'passed' and result['external_wiring_executed'] is True
assert result['fixture_id'] == 430 and result['fixture_revision'] == 5 and result['core_revision'] == SOURCE
assert result['swd_frequency_hz'] == 10000000 and result['results'] == entries
assert result['campaign']['completed_cycles'] == 1 and not result['campaign']['interrupted_duration_reused']
vectors = list(itertools.product((16000, 48000), (8, 16, 24, 32), (0, 1, 2), (32, 256), (1, 2), (0x13579BDF,)))
plan = list(itertools.product((1, 2), vectors))
functional = [row for row in entries if row['id'].startswith('V04-I2S-SIGNAL/')]
assert len(functional) == len({row['id'] for row in functional}) == len(plan) == 192
assert len(payloads) == 384
counts = []
for index, (controller, vector) in enumerate(plan):
    row, cleanup = entries[index * 2:index * 2 + 2]
    assert row['id'] == f'V04-I2S-SIGNAL/430/{controller}/{vector}/repeat-1'
    assert row['status'] == 'passed' and row['scope'] == 'i2s-full-duplex-dma'
    words = vector[3] * vector[4]
    assert row['statuses'] == [[1, 1, 1, 1, 0, words, vector[3], (1 << vector[4]) - 1]] * 2
    payload_hashes = []
    for role in (1, 2):
        capture = payloads[index * 2 + role - 1]
        assert capture['read_index'] == index * 2 + role - 1 and capture['receiver_role'] == role
        assert capture['requested_words'] == len(capture['raw_words']) == words + 16
        seed = vector[5] ^ (0x5A5A5A5A if role == 1 else 0)
        width = vector[1]
        mask = (1 << width) - 1
        expected = [((seed + 0x9E3779B9 * (offset + 1)) ^ ((offset << 16) | (offset >> 16))) & 0xFFFFFFFF for offset in range(words)]
        offsets = list(range(0, 32, width)) if width <= 16 else [0]
        expected_samples = [(value >> shift) & mask for value in expected for shift in offsets]
        actual_samples = [(value >> shift) & mask for value in capture['raw_words'] for shift in offsets]
        start = 0
        while start < len(actual_samples) and actual_samples[start] == 0:
            start += 1
        channels = 2 if vector[2] == 0 else 1
        assert start <= 8 * channels and start % channels == 0
        assert actual_samples[start:start + len(expected_samples)] == expected_samples
        digest = hashlib.sha256(struct.pack(f'<{words + 16}I', *capture['raw_words'])).hexdigest()
        assert row['payloads'][role - 1] == {'receiver_role': role, 'startup_zero_samples': start,
            'payload_samples': len(expected_samples), 'capture_words': words + 16, 'raw_sha256': digest}
        payload_hashes.append(digest)
    counts.append({'controller_role': controller, 'sample_rate_hz_requested': vector[0], 'width_bits': vector[1],
        'channels': vector[2], 'words_per_buffer': vector[3], 'buffers': vector[4], 'received_words_per_role': words,
        'raw_payload_sha256_by_receiver_role': payload_hashes})
    assert cleanup['id'] == 'V04-SIGNAL-CLEANUP/repeat-1' and cleanup['status'] == 'cleanup'
    assert cleanup['cleanup_only'] is True
    assert cleanup['results'] == [{'role': 1, 'result': [0]}, {'role': 2, 'result': [0]}]
assert [row['id'] for row in entries[384:]] == ['V04-CAMPAIGN-PROGRESS', 'V04-CAMPAIGN-COMPLETE']
images = json.loads((WORK / 'exact-images.json').read_text(encoding='utf-8'))
confirmation = json.loads((WORK / 'confirmation.json').read_text(encoding='utf-8'))
assert result['confirmation_sha256'] == hashlib.sha256((WORK / 'confirmation.json').read_bytes()).hexdigest()
for role, device, image in zip((1, 2), result['devices'], images):
    assert device['role'] == image['role'] == role and image['core_revision'] == SOURCE
    assert device['hex_sha256'] == image['sha256'] == confirmation['hex_sha256'][role - 1]
    assert device['elf_sha256'] == image['elf_sha256'] and device['uid_sha256'] == confirmation['uid_sha256'][role - 1]
    assert device['flash']['frequency_hz'] == 10000000
    assert not device['flash']['mass_erase_requested'] and not device['flash']['recover_requested']
audit = {'status': 'passed', 'fixture_id': 430, 'source': SOURCE, 'attempt': 1,
    'functional_records': 192, 'cleanup_records': 192, 'campaign_records': 2, 'total_journal_records': len(entries),
    'journal_matches_final_json': True, 'independent_plan_order_and_unique_functional_ids': 'passed',
    'raw_payload_records': len(payloads), 'received_words_both_roles': sum(2 * row['received_words_per_role'] for row in counts),
    'counts': counts, 'continuous_elapsed_seconds': result['campaign']['continuous_elapsed_seconds'],
    'swd_frequency_hz': 10000000,
    'capture_note': 'Canonical read_u32 return values copied without extra mailbox or target commands',
    'not_measured': ['calibrated sample rate or jitter', 'external codec compatibility or audio quality',
                     'injected underrun/overrun recovery', 'T13 concurrency/soak'],
    'hashes': {item.name: hashlib.sha256(item.read_bytes()).hexdigest() for item in (path, journal_path, payload_path)}}
assert audit['received_words_both_roles'] == 82944
(WORK / 'results-audit.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
print(json.dumps({key: value for key, value in audit.items() if key != 'counts'}))
