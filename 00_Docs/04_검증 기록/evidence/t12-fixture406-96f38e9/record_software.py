"""! @brief 성공 log와 exact source를 결합한 software 검증을 기록합니다. """
from pathlib import Path
import hashlib
import json
import re

work = Path(__file__).resolve().parent
checks = []
for name, marker in [('gate-host.log', 'M12_GATE_PASS=host'),
                     ('gate-contract-prebuild.log', 'M12_GATE_PASS=contract'),
                     ('gate-inventory-prebuild.log', 'M12_GATE_PASS=inventory'),
                     ('gate-docs-prebuild.log', 'M12_GATE_PASS=docs'),
                     ('style-check.log', 'CPP_STYLE_FILES=358; FAILED=0; WRITE=0'),
                     ('build.log', 'M12_ZEPHYR_BUILD_PASS=2')]:
    path = work / name
    text = path.read_text(encoding='utf-8-sig')
    assert marker in text
    checks.append({'log': name, 'status': 'passed', 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                   'sha256_basis': 'original bytes preserved in .raw.gz'})
host = (work / 'gate-host.log').read_text(encoding='utf-8-sig')
counts = list(map(int, re.findall(r'^Ran (\d+) tests? in', host, re.M)))
assert sum(counts) == 649
build = (work / 'build.log').read_text(encoding='utf-8-sig')
seconds = float(re.search(r'with no warnings in ([\d.]+) seconds', build).group(1))
payload = {'source': (work / 'source.txt').read_text(encoding='ascii').strip(),
           'host_tests': sum(counts), 'host_test_groups': len(counts), 'contract_tests': 45,
           'cpp_style_files': 358, 'pair_target_builds': 2, 'pair_build_seconds': seconds,
           'readiness_blockers': 8, 'checks': checks, 'preparation_failures': [],
           'physical_claim': 'None; fixture406-attempt1 and postflight contain physical evidence.'}
(work / 'software-verification.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
print(f'SOFTWARE_PASS=Host:649;groups:{len(counts)};contract:45;style:358;pair:2;build_seconds:{seconds};blockers:8')
