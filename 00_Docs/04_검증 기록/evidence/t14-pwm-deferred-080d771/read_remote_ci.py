"""! @brief push source의 실제 두 자동 workflow 상태를 공개 API에서 한 번 읽습니다. """
from pathlib import Path
import datetime
import json
import re
import sys
import urllib.request

work = Path(__file__).parent
source = sys.argv[1]
assert re.fullmatch('[0-9a-f]{40}', source)
url = 'https://api.github.com/repos/EIDOSDATA/NU54DK_Arduino_Core/actions/runs?head_sha=' + source + '&per_page=100'
request = urllib.request.Request(url, headers={'Accept': 'application/vnd.github+json', 'User-Agent': 'NU54DK-verification'})
with urllib.request.urlopen(request, timeout=30) as response:
    data = json.load(response)
runs = [{'id': row['id'], 'name': row['name'], 'head_sha': row['head_sha'],
         'event': row['event'], 'status': row['status'], 'conclusion': row['conclusion'],
         'url': row['html_url'], 'created_at': row['created_at'], 'updated_at': row['updated_at']}
        for row in data['workflow_runs'] if row['head_sha'] == source and row['event'] == 'push']
result = {'source': source, 'at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
          'runs': runs, 'all_observed_runs_successful': len(runs) >= 2 and all(row['status'] == 'completed' and row['conclusion'] == 'success' for row in runs)}
(work / ('remote-final-' + source[:7] + '.json')).write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(result, ensure_ascii=False))
