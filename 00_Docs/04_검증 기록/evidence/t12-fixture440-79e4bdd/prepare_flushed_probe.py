"""! @brief 보드별 SWD 쓰기를 모두 완료한 뒤 입력을 읽도록 진단 순서를 교정합니다. """
from pathlib import Path

work = Path(__file__).resolve().parent
source = (work / 'net_isolation_settled_retry.py').read_text(encoding='utf-8')
source = source.replace('net-isolation-settled-retry.json', 'net-isolation-flushed.json')
source = source.replace('net-startup-pins.json', 'net-flushed-startup-pins.json')
source = source.replace('            for source in devices:', '                device.target.flush()\n                assert all(device.target.read32(0x500D8280 + 4 * pin) == 4 for pin in (4, 5))\n            for source in devices:')
source = source.replace('                    source.target.write32(0x500D8280 + 4 * pin, 4)', '                    source.target.write32(0x500D8280 + 4 * pin, 4)\n                    source.target.flush()\n                    assert source.target.read32(0x500D8280 + 4 * pin) == 4')
source = source.replace('            cleanup = []', '                device.target.flush()\n            cleanup = []')
(work / 'net_isolation_flushed.py').write_text(source, encoding='utf-8', newline='\n')
audit = (work / 'audit_net_settled_retry.py').read_text(encoding='utf-8')
audit = audit.replace('net-isolation-settled-retry.json', 'net-isolation-flushed.json').replace('net-settled-audit.json', 'net-flushed-audit.json')
(work / 'audit_net_flushed.py').write_text(audit, encoding='utf-8', newline='\n')
print('EXPLICIT_PER_TARGET_WRITE_COMPLETION_READY;EARLIER_FAILURES_PRESERVED')
