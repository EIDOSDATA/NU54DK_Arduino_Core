"""! @brief 같은 채널의 실제 sample 일치 여부를 추가 측정 없이 분석합니다. """
from pathlib import Path
import json

work = Path(__file__).resolve().parent
rows = [json.loads(line) for line in (work / 'pdm-samples.jsonl').read_text().splitlines()]
assert len(rows) == 5
samples = rows[-1]['samples']
left, right = samples[0::2], samples[1::2]
assert len(left) == len(right) == 128
result = {'source': (work / 'source.txt').read_text().strip(), 'hardware_executed': False,
    'input': 'pdm-samples.jsonl read_index 4; failed first stereo vector',
    'channel_samples': 128, 'identical_sample_pairs': sum(a == b for a, b in zip(left, right)),
    'channel_means': [sum(left) / len(left), sum(right) / len(right)],
    'channel_ranges': [[min(left), max(left)], [min(right), max(right)]],
    'mono_means': [sum(row['samples']) / len(row['samples']) for row in rows[:4]],
    'root_cause': 'unresolved; source routing/physical transfer and receiver settings require active readback',
    'not_proven': ['wiring fault', 'public core PDM defect', 'mono density ordering', 'independent stereo source waveform']}
with (work / 'sample-analysis.json').open('x', encoding='utf-8', newline='\n') as output:
    output.write(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
print(json.dumps(result))
