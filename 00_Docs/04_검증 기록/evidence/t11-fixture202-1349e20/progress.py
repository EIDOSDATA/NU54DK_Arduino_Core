"""! @brief 실행 중 append-only journal을 장치 접근 없이 요약합니다. """
from pathlib import Path
from datetime import datetime, timezone
import json
import time

work = Path(__file__).resolve().parent
path = work / 'fixture202-attempt1.json.jsonl'
rows = []
if path.exists():
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            pass
functional = [r for r in rows if r.get('id', '').startswith('V04-SPI-')]
value = {'utc': datetime.now(timezone.utc).isoformat(), 'functional_records': len(functional), 'expected': 9084, 'percent': round(len(functional) / 9084 * 100, 1), 'last_id': functional[-1]['id'] if functional else None}
if path.exists():
    elapsed = time.time() - path.stat().st_ctime
    value.update(elapsed_seconds=round(elapsed, 1), stale_seconds=round(time.time() - path.stat().st_mtime, 1))
    if functional:
        value['linear_remaining_minutes'] = round(elapsed / len(functional) * (9084 - len(functional)) / 60, 1)
final = work / 'fixture202-attempt1.json'
if final.exists():
    value['final_status'] = json.loads(final.read_text(encoding='utf-8-sig'))['status']
print(json.dumps(value, ensure_ascii=False))
