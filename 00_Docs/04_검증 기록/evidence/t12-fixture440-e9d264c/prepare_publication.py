"""! @brief 재결선·부분 실기·CONSTLAT 빌드 증거와 source별 software 범위를 정리합니다. """
from pathlib import Path
import hashlib
import json
import re
import shutil
import subprocess

work = Path(__file__).resolve().parent
repo = Path(r'C:\Users\eidos\GitHub\NU54DK_Arduino_Core')
source = (work / 'source.txt').read_text().strip()
assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip() == source
assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=repo)
stages = []
for name, status in (
    ('t12-fixture440-rewired', 'independent-nets-pass96;mono-pass4;stereo-polarity-fail1;remaining187'),
    ('t12-fixture440-phase', 'functional-pass76;stereo-polarity-fail1;remaining115'),
    ('t12-fixture440-constlat', 'host-pass;pair-link-build-failed2;physical-not-run'),
    ('t12-fixture440-constlat-link', 'pair-build-pass2;physical-not-run;confirmation-expired')):
    origin = work.parent / name
    stage_source = (origin / 'source.txt').read_text().strip()
    summary = {'source': stage_source, 'status': status, 'public_core_sdk_board_changed': False,
        'swd_frequency_hz': 10000000, 'whole_pdm_pass': False, 'whole_t12_pass': False,
        'continuous_4_settling_100_measured_buffers': 'not implemented or executed',
        'software': {}, 'physical': {}}
    full = origin / 'gate-host-final.json'
    if full.exists():
        record = json.loads(full.read_text())
        log = (origin / 'gate-host-final.log').read_text(encoding='utf-8')
        groups = re.findall(r'Ran (\d+) tests? in', log)
        skips = sum(int(count) for count in re.findall(r'OK \(skipped=(\d+)\)', log))
        total = sum(map(int, groups))
        assert record['returncode'] == 0 and record['source'] == stage_source and not record['dirty']
        assert total == 661 and skips == 1 and len(groups) == 82
        assert "native compiler unavailable" not in log
        summary['software']['full_host'] = {'total': total, 'passed': total - skips, 'conditional_skips': skips, 'groups': len(groups), 'source': stage_source}
    subset = origin / 'signal-host-final.json'
    if subset.exists():
        record = json.loads(subset.read_text())
        assert record['returncode'] == 0 and record['source'] == stage_source and not record['dirty']
        summary['software']['signal_host'] = {'passed': 17, 'source': stage_source}
        summary['software']['prior_full_host_source'] = '5273b30c05e1cdf2b7043f39c1f2536f1699bb59'
        diff = subprocess.check_output(['git', 'diff', '--name-only', '5273b30', stage_source], cwd=repo, text=True).splitlines()
        assert diff == ['tests/zephyr/v04_pair_hil/src/signal_hil.cpp']
        summary['software']['only_change_since_full_host'] = 'C linkage wrapper around SDK C-only header; target link and signal Host rechecked'
    if (origin / 'style.log').exists():
        assert 'CPP_STYLE_FILES=361; FAILED=0; WRITE=0' in (origin / 'style.log').read_text()
        summary['software']['style_files_passed'] = 361
    if (origin / 'target-artifact-index.json').exists():
        index = json.loads((origin / 'target-artifact-index.json').read_text())
        assert len(index['targets']) == 2
        for role, target in enumerate(index['targets'], 1):
            assert target['status'] == 'built-not-run'
            assert target['identity_records'][0]['identity']['core_revision'] == stage_source[:12]
            for artifact in target['artifacts'].values():
                raw = Path(artifact['path']).read_bytes()
                assert len(raw) == artifact['bytes'] and hashlib.sha256(raw).hexdigest() == artifact['sha256']
            dt = Path(target['artifacts']['zephyr.elf']['path']).with_name('zephyr.dts')
            destination = origin / f'role{role}-zephyr.dts'
            if not destination.exists():
                shutil.copyfile(dt, destination)
        summary['software']['target_builds_passed'] = 2
    audit = origin / 'results-audit.json'
    if audit.exists():
        result = json.loads(audit.read_text())
        summary['physical'] = {key: result[key] for key in ('campaign_status', 'functional_pass', 'density_pass', 'cleanup_pass', 'raw_captures', 'audited_functional_samples', 'failed_cases', 'unexecuted_vectors', 'error')}
        postflight = json.loads((origin / 'postflight.json').read_text())
        assert postflight['source'] == stage_source and len(postflight['devices']) == 2
        assert all(v == 0 for device in postflight['devices'] for v in device['peripheral_enable'].values())
        summary['physical']['postflight_roles_passed'] = 2
    if name == 't12-fixture440-rewired':
        net = json.loads((origin / 'net-flushed-audit.json').read_text())
        assert net['wiring_matches_fixture440'] and net['observations'] == 96 and not net['mismatches']
        summary['physical']['independent_clock_gate_observations_passed'] = 96
        old = json.loads((work.parent / 't12-fixture440-final/target-artifact-index.json').read_text())
        for role, target in enumerate(index['targets']):
            for key in ('repository_compiled_sources_sha256', 'normalized_config_sha256', 'source_membership_sha256'):
                assert target[key] == old['targets'][role][key]
        summary['software']['same_compiled_input_as_source'] = 'ea4e25a035dbc9219e417bf2a2056ce6f9a2e09c'
    with (origin / 'software-summary.json').open('x', encoding='utf-8', newline='\n') as output:
        output.write(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    stages.append((name, stage_source, status))
tail = (work.parent / 't12-fixture440-final/publish_evidence.py').read_text(encoding='utf-8')
tail = tail[tail.index('published = []'):]
(work / 'publish_evidence.py').write_text('from runtime import *\nimport gzip\nstages = ' + repr(stages) + '\n' + tail, encoding='utf-8', newline='\n')
print('FOUR_SOURCE_EVIDENCE_PREPARED;LATEST_PHYSICAL_NOT_RUN')
