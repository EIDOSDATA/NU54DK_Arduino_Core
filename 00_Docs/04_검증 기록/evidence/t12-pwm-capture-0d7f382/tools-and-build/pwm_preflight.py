"""! @brief 최신 source의 두 image와 미확인 결선 초안을 하드웨어 접근 없이 만듭니다. """
import contextlib
import json
import sys
from check_pc import REPO, WORK, SDK
sys.path.insert(0, str(REPO / 'tests/hil/nu54dk'))
import v04_signal_run
import v04_pair
import v04_fixture
from pathlib import Path

private = json.loads((WORK / 'current-probe-uids.private.json').read_text(encoding='utf-8-sig'))
keys = ('32f71533ff6ba27fd38ed32a17bf6d80a90d4f4980221051ed5c5a2e7fdb63a9',
        '4574ee31f25fe05f154395ea4d8c6aa0583b04a4f7a0ea97fe3d13b05eea8ca0')
uids = [private[key].lower() for key in keys]
root = Path('C:/pwh04')
images = [v04_pair.inspect_image(REPO, root, role) for role in (1, 2)]
(WORK / 'pwm-ready-images.json').write_text(json.dumps(images, indent=2, default=str) + '\n', encoding='utf-8')
template = v04_fixture.confirmation_template(images, uids, 408)
(WORK / 'pwm-ready-confirmation-draft.json').write_text(json.dumps(template, indent=2) + '\n', encoding='utf-8')
with (WORK / 'pwm-ready-preflight.log').open('w', encoding='utf-8') as stream, contextlib.redirect_stdout(stream):
    result = v04_signal_run.main(['--dut', uids[0], '--peer', uids[1], '--build-root', str(root),
        '--pyocd', str(SDK / 'opt/bin/Scripts/pyocd.exe'), '--fixture', '408', '--pwm-capture',
        '--swd-frequency-hz', '10000000'])
assert result == 0
print(json.dumps({'status': 'preflight-only PASS', 'core_revision': images[0]['core_revision'],
                  'roles': len(images), 'confirmation': 'draft: all physical conditions false',
                  'probe_access': False, 'flash': False, 'external_wiring_executed': False}))
