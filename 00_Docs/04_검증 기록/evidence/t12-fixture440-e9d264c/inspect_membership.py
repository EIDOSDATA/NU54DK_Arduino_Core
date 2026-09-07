"""! @brief compile command의 중복을 포함한 source 소속 차이를 계산합니다. """
from pathlib import Path
from collections import Counter
import json

work = Path(__file__).resolve().parent
cur = json.loads((work / 'target-artifact-index.json').read_text())
old = json.loads((work.parent / 't12-fixture440-phase/target-artifact-index.json').read_text())
rows = []
for role in range(2):
    counters = []
    for index, root in ((cur, 'C:/u4j'), (old, 'C:/u4h')):
        commands = json.loads(Path(index['targets'][role]['compile_commands']['path']).read_text())
        counters.append(Counter(row['file'].replace('\\', '/').replace(root, '<BUILD>') for row in commands))
    rows.append({'role': role + 1, 'added': dict(counters[0] - counters[1]), 'removed': dict(counters[1] - counters[0])})
(work / 'membership-differences.json').write_text(json.dumps(rows, indent=2) + '\n', encoding='utf-8', newline='\n')
print(json.dumps(rows))
