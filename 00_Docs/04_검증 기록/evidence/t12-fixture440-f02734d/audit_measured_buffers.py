"""! @brief 평균 합계뿐 아니라 측정 버퍼 100개 각각의 밀도 순서·채널 부호를 대조합니다. """
from pathlib import Path
import ast
import json

work = Path(__file__).resolve().parent
result = json.loads((work / 'fixture440-continuous.json').read_text())
assert result['status'] == 'passed'
rows = [row for row in result['results'] if row['id'].startswith('V04-PDM-CONTINUOUS/440/')]
assert len(rows) == 96
mono = {}
stereo_checks = 0
for row in rows:
    fields = row['id'].split('/')
    role = int(fields[2])
    instance, samples, density, stereo, edge = ast.literal_eval(fields[3])
    assert len(row['buffer_statistics']) == 104
    means = []
    for words in row['buffer_statistics'][4:]:
        values = [word if word < 0x80000000 else word - 0x100000000 for word in words[3:5]]
        channels = [value / (samples // (2 if stereo else 1)) for value in values]
        if stereo:
            sign = 1 if ((edge == 0) != (density == 75)) else -1
            assert channels[0] * sign > 0 and channels[1] * -sign > 0
            stereo_checks += 1
        else:
            means.append(channels[0])
    if not stereo:
        mono.setdefault((role, instance, samples, edge), {})[density] = means
assert len(mono) == 16 and stereo_checks == 4800
density_checks = 0
for series in mono.values():
    assert set(series) == {25, 50, 75}
    for index in range(100):
        assert series[25][index] < series[50][index] < series[75][index]
        density_checks += 1
assert density_checks == 1600
audit = {'source': result['core_revision'], 'status': 'passed', 'measured_buffers_per_case': 100,
    'mono_per_buffer_density_order_checks': density_checks,
    'stereo_per_buffer_polarity_checks': stereo_checks,
    'scope': 'Every measured buffer after the four settling buffers; no absolute PCM calibration or constant-amplitude claim'}
(work / 'measured-buffers-audit.json').write_text(json.dumps(audit, indent=2) + '\n', encoding='utf-8')
print(json.dumps(audit))
