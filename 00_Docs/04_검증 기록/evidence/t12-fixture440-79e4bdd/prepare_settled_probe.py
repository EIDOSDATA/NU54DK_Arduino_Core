"""! @brief 최초 GPIO 입력 관측의 안정화를 10 ms 간격 3회 측정으로 독립 재검사합니다. """
from pathlib import Path

work = Path(__file__).resolve().parent
text = (work / 'net_isolation_probe.py').read_text(encoding='utf-8')
text = text.replace('from runtime import *', 'from runtime import *\nimport time')
text = text.replace('net-isolation-probe.json', 'net-isolation-settled.json')
text = text.replace("'functional_pass_claimed': False}", "'functional_pass_claimed': False, 'settling_seconds': 0.01, 'samples_per_level': 3}")
text = text.replace("        originals =", "        write_new(WORK / 'net-startup-pins.json', {'source': SOURCE, 'devices': [{'role': device.image['role'], 'pin_cnf': {str(pin): device.target.read32(0x500D8280 + pin * 4) for pin in (4, 5, 6, 7)}} for device in devices], 'capture': 'passive read after settled diagnostic canonical boot'})\n        originals =")
start = text.index('                        observed = []')
end = text.index('                    source.target.write32(0x500D8280', start)
block = text[start:end]
block = block.replace("'driver_pin': pin, 'level': level,", "'driver_pin': pin, 'level': level, 'sample': sample,")
text = text[:start] + '                        for sample in range(3):\n                            time.sleep(0.01)\n' + ''.join('    ' + line + '\n' for line in block.splitlines()) + text[end:]
(work / 'net_isolation_settled.py').write_text(text, encoding='utf-8', newline='\n')
audit = (work / 'audit_net.py').read_text(encoding='utf-8')
audit = audit.replace('net-isolation-probe.json', 'net-isolation-settled.json').replace('net-audit.json', 'net-settled-audit.json')
audit = audit.replace('len(rows) == 9', 'len(rows) == 25').replace('rows[:8]', 'rows[:24]').replace("'observations': 32", "'observations': 96").replace('_PASS=32', '_PASS=96')
(work / 'audit_net_settled.py').write_text(audit, encoding='utf-8', newline='\n')
print('SETTLED_PROBE_READY;FIRST_FAILURE_PRESERVED')
