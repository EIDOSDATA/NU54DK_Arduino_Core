"""! @brief canonical 온보드·BLE 판정을 유지하며 실행과 실패 기록을 보존합니다. """
from runtime import *
import importlib
from datetime import datetime, timezone

kind = sys.argv[1]
modules = {'uart': 'm24_uarte_onboard', 'twim': 'm24_twim_onboard', 'm25': 'm25_onboard', 'm26': 'm26_onboard', 'm19': 'm19_ble_gap', 'm20': 'm20_ble_gatt', 'm21': 'm21_ble_security'}
module = importlib.import_module(modules[kind])
for function_name in ('choose_exact_port', 'choose_unique_response'):
    if hasattr(module, function_name):
        original = getattr(module, function_name)
        def observed_frame(transcripts, expected, _original=original):
            print('FRAME_OBSERVATION=' + json.dumps({'expected_hex': expected.hex(), 'received_hex': {port: data.hex() for port, data in transcripts.items()}}), flush=True)
            return _original(transcripts, expected)
        setattr(module, function_name, observed_frame)
case = kind + ('-' + sys.argv[2] if kind in ('uart', 'twim', 'm25', 'm26') else '-pair')
evidence = WORK / (case + '-18a7cbe.json')
assert not evidence.exists(), 'Evidence is append-only; choose a new qualified attempt'
if kind in ('uart', 'twim', 'm25', 'm26'):
    index = {'a': 0, 'b': 1}[sys.argv[2]]
    arguments = ['--repository', str(REPO), '--build-root', str(BUILD), '--probe-id', UIDS[index], '--pyocd', str(BUNDLE / 'opt/bin/Scripts/pyocd.exe'), '--evidence', str(evidence)]
    if kind == 'uart':
        arguments += ['--swd-frequency-hz', '10000000']
else:
    suite = {'m19': 'm19.ble_gap_hil', 'm20': 'm20.ble_gatt_hil', 'm21': 'm21.ble_security_hil'}[kind]
    images = []
    for role in ('peripheral', 'central'):
        matches = list((BUILD / 'nrf54l15dk_nrf54l15_cpuapp_nu54dk/zephyr_gnu' / ('nucode.' + suite + '_' + role)).rglob('zephyr.hex'))
        assert len(matches) == 1, (suite, role, len(matches))
        images.append(matches[0])
    arguments = ['--peripheral-hex', str(images[0]), '--central-hex', str(images[1]), '--peripheral-board-id', UIDS[0], '--central-board-id', UIDS[1], '--expected-core-revision', SOURCE, '--evidence', str(evidence)]
start = datetime.now(timezone.utc).isoformat()
print('CASE_START=' + case, flush=True)
try:
    code = module.main(arguments)
    assert code == 0, 'Canonical runner returned ' + str(code)
except Exception as error:
    failure = {'case': case, 'status': 'failed', 'core_revision': SOURCE, 'started_at_utc': start, 'completed_at_utc': datetime.now(timezone.utc).isoformat(), 'error_type': type(error).__name__, 'error': str(error), 'canonical_arguments_redacted': arguments, 'automatic_retry': False}
    write_new(WORK / (case + '-18a7cbe-failure.json'), failure)
    print('CASE_FAIL=' + json.dumps(failure, ensure_ascii=False), file=sys.stderr, flush=True)
    raise SystemExit(1)
print('CASE_PASS=' + case, flush=True)
