"""! @brief 각 실행의 범위와 전체 Host 차단을 성공 결과와 분리해 기록합니다. """
from pathlib import Path
import hashlib
import json
import re
import subprocess

work = Path(__file__).resolve().parent
repo = Path(r'C:\Users\eidos\GitHub\NU54DK_Arduino_Core')
source = (work / 'source.txt').read_text().strip()
assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip() == source
assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=repo)
before = (work / 'main-before-newline-format.cpp').read_bytes()
after = (work / 'main-after-newline-format.cpp').read_bytes()
assert before != after and before.replace(b'\r\n', b'\n') == after.replace(b'\r\n', b'\n')
assert 'CPP_STYLE_FILES=362; FAILED=0; WRITE=0' in (work / 'style-final.log').read_text()
header = repo / 'tests/zephyr/v04_pair_hil/src/pdm_continuous.h'
summary = {'source': source, 'core_sdk_board_unchanged': True,
    'changes': ['PDM receiver gate HIGH prepared before generator',
                'HIL continuous 104 DMA buffers, 4 settling plus100 measured, four rotating guarded slots',
                'HIL opcode39 returns per-buffer sequence/count/sums/extrema/FNV of actual samples'],
    'target_build_passed': 2, 'style_passed_files': 362,
    'style_first_failure': 'main.cpp one mixed newline; format changed only LF to CRLF; Git blob unchanged after index refresh',
    'main_format_normalized_bytes_identical': True,
    'main_before_sha256': hashlib.sha256(before).hexdigest(), 'main_after_sha256': hashlib.sha256(after).hexdigest(),
    'pdm_header_sha256': hashlib.sha256(header.read_bytes()).hexdigest(),
    'full_host': 'NOT PASS: both canonical runs blocked during R02 native executable launch (WinError4551)',
    'host_policy_changed': False, 'new_test_initial_precommit': '4 PASS including actual native 104-buffer rotation; same helper/test code committed',
    'new_test_postcommit': '3 Python tests pass; native executable launch blocked twice with WinError4551',
    'signal_related': '17 PASS', 'r02_standalone_retry': 'PASS (full gate retries still blocked)',
    'remaining_groups': json.loads((work / 'host-remaining.json').read_text())['groups'],
    'cmake_group_failure': 'CMake could not launch existing WinLibs ninja --version; output says unknown error',
    'native_groups_blocked': ['test_v04_pdm_continuous.py', 'test_r09_spi_facade.py', 'test_r12_ble_gap.py',
        'test_r12_eeprom.py', 'test_r12_littlefs.py', 'test_v04_qdec.py', 'test_v04_serial_lifecycle.py'],
    'physical_finite': json.loads((work / 'results-audit.json').read_text()),
    'physical_continuous': json.loads((work / 'continuous-audit.json').read_text()),
    'postflight': 'Both exact roles verified; CONSTLAT/PDM20/PDM21/SPIS/GPIOTE/DPPI off and signal pins input',
    'next': 'Fresh Fixture440 confirmation, current clean exact pair, full96 continuous cases; rerun blocked Host groups only after environment issue resolved',
    'whole_pdm_complete': False, 'whole_t12_complete': False, 'remote_ci_checked': False}
(work / 'software-summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
diagnostic = json.loads((work.parent / 't12-fixture440-resume/mono-order-diagnostic.json').read_text())
captures = [row for row in diagnostic['results'] if row['id'] == 'CAPTURE']
assert len(captures) == 6
means = {str(order): [row['mean'] for row in captures if row['receiver_first'] == order] for order in (False, True)}
assert len(set(means['False'])) == 1 and means['True'][0] < means['True'][1] < means['True'][2]
(work.parent / 't12-fixture440-resume/diagnostic-audit.json').write_text(json.dumps({
    'source': '4a8dbafe74e251bbc2897775dae15688ab950823', 'captures': 6, 'raw_samples': 1536,
    'means_by_receiver_first': means, 'same_target_image': True, 'only_sequence_changed': True,
    'cleanup_pass': all(row['results'] == [[0], [0]] for row in diagnostic['results'] if row['id'] == 'CLEANUP')}, indent=2) + '\n', encoding='utf-8')
print('TWO_SOURCE_SUMMARY_PASS;FINITE224_PASS;CONTINUOUS65_PASS_31_NOT_RUN;FULL_HOST_BLOCKED')
