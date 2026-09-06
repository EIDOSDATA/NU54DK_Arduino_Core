"""! @brief source별 부분 결과와 실제 software 로그를 대조하고 보존 입력을 만듭니다. """
from pathlib import Path
import hashlib
import json
import re
import shutil
import subprocess

WORK = Path(__file__).resolve().parent
REPO = Path(r'C:\Users\eidos\GitHub\NU54DK_Arduino_Core')
SOURCE = (WORK / 'source.txt').read_text().strip()
assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip() == SOURCE
assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=REPO)
stages = []
for name, total, passes, cleanup in [
    ('t12-fixture440', 660, 0, 1),
    ('t12-fixture440-fixed', 660, 4, 5),
    ('t12-fixture440-stereo', 661, 4, 4),
    ('t12-fixture440-final', 661, 4, 5),
]:
    folder = WORK.parent / name
    revision = (folder / 'source.txt').read_text().strip()
    host = json.loads((folder / 'gate-host-final.json').read_text())
    log = (folder / 'gate-host-final.log').read_text(encoding='utf-8')
    assert host['source'] == revision and not host['dirty'] and host['returncode'] == 0
    counts = list(map(int, re.findall(r'^Ran (\d+) tests? in', log, re.M)))
    skips = [line for line in log.splitlines() if '... skipped ' in line]
    assert sum(counts) == total and len(counts) == 82 and len(skips) == 1
    assert 'NUCODE_M13_CLI_DISCOVERY' in skips[0]
    assert 'CPP_STYLE_FILES=361; FAILED=0; WRITE=0' in (folder / 'style.log').read_text()
    result = json.loads((folder / 'results-audit.json').read_text())
    assert result['source'] == revision and result['campaign_status'] == 'failed'
    assert result['functional_pass'] == passes and result['cleanup_pass'] == cleanup
    assert result['failed_cases'] == 1 and not result['whole_fixture_pass']
    index = json.loads((folder / 'target-artifact-index.json').read_text())
    assert len(index['targets']) == 2 and not index['physical_executed']
    dt_rows = []
    for role, target in enumerate(index['targets'], 1):
        assert target['status'] == 'built-not-run'
        for artifact in target['artifacts'].values():
            raw = Path(artifact['path']).read_bytes()
            assert len(raw) == artifact['bytes'] and hashlib.sha256(raw).hexdigest() == artifact['sha256']
        dts = Path(target['artifacts']['zephyr.elf']['path']).with_name('zephyr.dts')
        content = dts.read_text(encoding='utf-8')
        pins = {}
        for pin in (4, 5, 6, 7):
            block = re.search(r'arduino_p1_0' + str(pin) + r':[^\{]+\{([^}]+)\}', content).group(1)
            pins[str(pin)] = {key: int(re.search(r'nucode,' + key + r'\s*=\s*<\s*(0x[0-9a-f]+|\d+)\s*>', block).group(1), 0)
                             for key in ('capability-mask', 'policy', 'ownership')}
        if folder == WORK:
            assert all(row == {'capability-mask': 19, 'policy': 4, 'ownership': 9} for row in pins.values())
        shutil.copyfile(dts, folder / f'role{role}-zephyr.dts')
        dt_rows.append({'role': role, 'sha256': hashlib.sha256(dts.read_bytes()).hexdigest(), 'pins': pins})
    post = json.loads((folder / 'postflight.json').read_text())
    assert post['source'] == revision and len(post['devices']) == 2
    assert all(v == 0 for device in post['devices'] for v in device['peripheral_enable'].values())
    for device in post['devices']:
        assert device['identity_status'] == 'passed'
        assert all((v & 1) == 0 for v in device['signal_pin_cnf'].values())
    summary = {'source': revision, 'host': {'total': total, 'passed': total - 1, 'skipped': 1,
        'groups': 82, 'skip_reason': skips[0], 'native_compiler_skips': 0},
        'style_files': 361, 'style_failed': 0, 'pair_builds': 2,
        'fixture440_status': 'failed', 'functional_pass': passes, 'cleanup_pass': cleanup,
        'unexecuted_vectors': 192 - passes - 1, 'postflight_peripherals_off_roles': 2,
        'postflight_original_assertion': 'failed: original P1.04 input pullup was assumed to be default input' if passes == 0 else 'passed',
        'prepared_failure_cleanup_unproven': 1 if name.endswith('stereo') else 0,
        'raw_samples_scope': 'Only the four completed mono DMA vectors are counted; density ordering was not reached',
        'resolved_devicetree': dt_rows, 'public_core_sdk_board_changed': False,
        'not_reexecuted': ['contract', 'inventory', 'package', 'full product target matrix', 'examples', 'remote CI'],
        't12_whole_completed': False}
    with (folder / 'software-summary.json').open('x', encoding='utf-8', newline='\n') as output:
        output.write(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    stages.append((name, revision, f'campaign-failed-{passes}-mono-dma-pass-1-failed-{191-passes}-not-run'))

completion = {'source': SOURCE, 'fixture440_status': 'failed', 'functional_pass': 4,
    'functional_scope': 'mono DMA completion, length, ordering, sample readout only; density ordering not reached',
    'cleanup_pass': 5, 'postflight_roles_pass': 2, 'failed_cases': 1, 'unexecuted_vectors': 187,
    'whole_fixture_pass': False, 't12_whole_completed': False,
    'last_uploaded_source': SOURCE, 'background_hardware_tests_running': False,
    'confirmation_utc': '2026-09-06T19:45:39Z', 'confirmation_expiry_utc': '2026-09-06T20:15:39Z',
    'next_action': 'Obtain current Fixture440 wiring-isolation confirmation; rebuild clean HEAD pair, read generator/receiver setup, diagnose identical stereo channels before the full sweep',
    'remaining': ['PDM20/21 role/mode/buffer sweep and mono density ordering',
        'PDM four settling plus 100 measured continuous buffers', 'T12 PWM period/duty capture',
        'T12 ADC calibration and multichannel sequence', 'T12 timer/event requirements', 'T13 and later gates']}
with (WORK / 'completion-status.json').open('x', encoding='utf-8', newline='\n') as output:
    output.write(json.dumps(completion, ensure_ascii=False, indent=2) + '\n')
old = (WORK.parent / 't12-fixture430-compact/publish_evidence.py').read_text(encoding='utf-8')
tail = old[old.index('published = []'):].replace('t12-fixture430-', 't12-fixture440-')
tail = tail.replace("'.txt', '.yml'", "'.txt', '.yml', '.dts'")
(WORK / 'publish_evidence.py').write_text('from runtime import *\nimport gzip\nstages = ' + repr(stages) + '\n' + tail,
    encoding='utf-8', newline='\n')
print('FOUR_SOURCE_FAILURES_SOFTWARE_AND_POSTFLIGHT_CHECKED;LATEST_HOST_660PASS_1SKIP')
