"""! @brief 보존된 시작 진단을 byte/sample 경계에서 분석하며 실행 판정은 바꾸지 않습니다. """
from pathlib import Path
import json
import struct

WORK = Path(__file__).resolve().parent
result = json.loads((WORK / 'startup-diagnostic.json').read_text())
for case in result['cases'][:12]:
    width, channels = case['vector'][1:3]
    outputs = []
    for received in case['receivers']:
        seed = 0x13579BDF ^ (0x5A5A5A5A if received['role'] == 1 else 0)
        expected = [((seed + 0x9E3779B9 * (index + 1)) ^ ((index << 16) | (index >> 16))) & 0xFFFFFFFF for index in range(32)]
        raw = struct.pack('<40I', *(received['raw_words'] + received['tail']))
        mask = 0xFFFFFF if width == 24 else 0xFFFFFFFF
        candidates = []
        for offset in range(0, 17):
            actual = struct.unpack('<32I', raw[offset:offset + 128])
            prefix = next((i for i in range(32) if actual[i] & mask != expected[i] & mask), 32)
            if prefix >= 28:
                candidates.append((offset, prefix, hex(actual[-1]), hex(expected[-1])))
        outputs.append({'role': received['role'], 'candidate_byte_offset_prefix': candidates,
            'head': [hex(word) for word in received['raw_words'][:3]], 'tail': [hex(word) for word in received['tail'][:3]]})
    print(json.dumps({'width': width, 'channels': channels, 'receivers': outputs}))
