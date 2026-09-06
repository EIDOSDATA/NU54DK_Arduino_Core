"""! @brief 실제 성공 log와 준비 중 실패를 구별하여 software 검증을 기록합니다. """
from pathlib import Path
import hashlib
import json
import re

work = Path(__file__).resolve().parent
checks = []
for name, marker in [('gate-host-final.log', 'M12_GATE_PASS=host'),
                     ('gate-contract-prebuild.log', 'M12_GATE_PASS=contract'),
                     ('gate-inventory-prebuild.log', 'M12_GATE_PASS=inventory'),
                     ('gate-docs-prebuild.log', 'M12_GATE_PASS=docs'),
                     ('style-check-verified.log', 'CPP_STYLE_FILES=358; FAILED=0; WRITE=0'),
                     ('build.log', 'M12_ZEPHYR_BUILD_PASS=2')]:
    path = work / name
    text = path.read_text(encoding='utf-8-sig')
    assert marker in text
    checks.append({'log': name, 'status': 'passed', 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
host = (work / 'gate-host-final.log').read_text(encoding='utf-8-sig')
counts = list(map(int, re.findall(r'^Ran (\d+) tests? in', host, re.M)))
payload = {'source': (work / 'source.txt').read_text(encoding='ascii').strip(),
           'host_tests': sum(counts), 'host_test_groups': len(counts), 'contract_tests': 45,
           'cpp_style_files': 358, 'pair_target_builds': 2, 'readiness_blockers': 8,
           'checks': checks,
           'preparation_failures_preserved': [
               {'log': 'gate-host.log', 'reason': 'Legacy gate test still expected fixture 405 to be invalid; updated to analog while 406/407 stay disabled until prepared.'},
               {'log': 'style-check-final.log', 'reason': 'Expanded gate assertion formatting required normalization; final full style check passed.'}],
           'physical_claim': 'None; separate fixture405-attempt1 and postflight records contain physical evidence.'}
(work / 'software-verification.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(f"SOFTWARE_PASS=Host:{sum(counts)};groups:{len(counts)};contract:45;style:358;pair:2;blockers:8")
