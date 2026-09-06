"""! @brief 확인된 407 결선과 버튼 공유 입력 시험의 구현·재현 입력을 준비합니다. """
from pathlib import Path
import json
import re
import subprocess

repo = Path(r'C:\Users\eidos\GitHub\NU54DK_Arduino_Core')
base = Path(__file__).resolve().parent
work = base / 't12-fixture407'
work.mkdir(exist_ok=False)
baseline = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip()
checkpoint = {'fixture_id': 407, 'baseline_source': baseline,
    'user_confirmation_recorded_at_utc': '2026-09-06T13:47:49+00:00',
    'confirmation_text': 'USB 제거 후 407 결선을 한 다음, 다시 연결을 했어. 이제 진행하도록 해.',
    'preceding_wiring_instructions': 'Both USB off; move A P1.12 to P1.13/AIN6; keep B P1.14 and common GND; DAP UART disconnected/SWD connected; buttons not pressed; reconnect both USB.',
    'wiring': 'A P1.13/AIN6 P4-11 <-> B P1.14 P4-12; common GND P2-30; prior A P1.12 removed; both USB disconnected for wiring then reconnected; existing SB/PMIC unchanged',
    'signal_profile': 'B INPUT pulldown/pullup/pulldown, 25ms settling, no output driver; A button remains unpressed',
    'swd_frequency_hz': 10000000, 'pending_after_407': [408]}
(work / 'checkpoint.json').write_text(json.dumps(checkpoint, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')

def edit(name, replacements):
    path = repo / name
    content = path.read_text(encoding='utf-8')
    for old, new in replacements:
        assert old in content, (name, old)
        content = content.replace(old, new)
    path.write_text(content, encoding='utf-8', newline='\n')

path = repo / '00_Docs/TODO_v0.4.0.md'
content = path.read_text(encoding='utf-8')
rows = {
    '진행 중인 T 항목': 'T05/T10/T12 Fixture 407 AIN6/P1.13 버튼 공유 입력을 준비·실행한다. 고정 B P1.14 INPUT pull-down/up/down, 25ms 정착, 32/256 samples·single/double buffer 12 vector. 제품 core·R00~R13 완료 유지; 408도 필수 후속',
    '다음 구체적 행동': '407 allowlist와 신호원·독립 LOW/HIGH oracle·DMA/GPIO/cleanup을 Host로 검증하고 exact pair build 후 SWD 10 MHz 실기. 사용자 버튼 미누름 조건을 유지하며 결과·문서·commit·main push까지 진행',
    '다음 작업에 필요한 사용자 행동': '직전 407 결선 안내에 대해 사용자가 USB 제거·407 결선·재연결과 진행을 확인했다. 추가 407 확인 요청 없이 진행한다. 다음 408은 개별 결선 안내·확인 필요',
    '외부 결선 상태': '2026-09-06T13:47:49Z 사용자 USB 제거 후 407 결선·재연결 확인. A P1.13/AIN6(P4-11)↔B P1.14(P4-12)·공통 GND(P2-30), 이전 A P1.12 제거·DAP UART 분리/SWD 연결·버튼 미누름 안내 조건. A D/COM5·6, B E/COM7·8; 기존 SB/PMIC 설정 유지',
}
for key, value in rows.items():
    content, count = re.subn(r'^\| ' + re.escape(key) + r' \|.*$', lambda _: f'| {key} | {value} |', content, flags=re.M)
    assert count == 1, key
content = content.replace('fixture 17개(405·406 추가)', 'fixture 18개(405·406·407 추가)')
content = content.replace('AIN6/407도 필수 후속이다.', 'AIN6/407은 버튼 공유 입력 바이어스 시험으로 준비하고 실기는 별도 판정한다.')
path.write_text(content, encoding='utf-8', newline='\n')

insert = '''    {
      "id": 407,
      "family": "analog",
      "banks": [1, 1],
      "instances": [[], []],
      "links": [
        {"dut": ["P4", 11, "P1.13"], "peer": ["P4", 12, "P1.14"], "signal": "peer INPUT pull-down/up/down -> DUT SAADC AIN6"},
        {"dut": ["P2", 30, "GND"], "peer": ["P2", 30, "GND"], "signal": "GND"}
      ],
      "notes": "P1.13/AIN6은 SW1 신호(버튼 부품 SW2)와 공유하며 버튼을 누르면 GND로 연결됩니다(원본 회로도 1·8쪽). 버튼은 누르지 않습니다. B P1.14는 INPUT을 유지하고 내부 pull-down/up/down만 사용하며 출력 드라이버·PWM은 금지합니다. 25ms 정착 뒤 32/256 sample·single/double buffer 12 vector, 모든 LOW raw -256~512·HIGH raw 1024 초과~4095와 GPIO raw INPUT·DMA·cleanup을 요구합니다. controller_role=2. 버튼 자체·debounce·wake 시험이나 교정 전압 측정이 아닙니다. 기존 SB/PMIC 설정 유지.",
      "pullups": ["B P1.14 INPUT 내부 pull-down/up/down만 사용하고 종료 시 no-pull 입력으로 해제. 외부 저항·전원선 추가 없음. A P1.13 공유 버튼은 누르지 않음."]
    },
'''
edit('tests/hil/nu54dk/v04_fixtures.json', [
    ('"revision": 4,', '"revision": 5,'),
    ('406은 입력 바이어스로 별도 준비하고 407은 후속 준비·결선 확인 후 수행 대상입니다.', '406·407은 각 공유 회로에 맞춘 INPUT 바이어스 시험과 개별 결선 확인으로 수행합니다.'),
    ('    {\n      "id": 408,', insert + '    {\n      "id": 408,')])
edit('tests/zephyr/v04_pair_hil/src/shared_analog_source.h', [
    ('fixture == 405U || fixture == 406U', 'fixture == 405U || fixture == 406U || fixture == 407U'),
    ('405는 LOW/해제, 406은 입력 pull-down/up/down', '405는 LOW/해제, 406·407은 입력 pull-down/up/down'),
    ('bias_only_ = fixture == 406U;', 'bias_only_ = fixture != 405U;')])
edit('tests/zephyr/v04_pair_hil/src/fixture_gate.h', [
    ('fixture <= 406', 'fixture <= 407'), ('id <= 406', 'id <= 407'),
    ('        case 406:\n', '        case 406:\n        case 407:\n')])
edit('tests/zephyr/v04_pair_hil/src/signal_hil.cpp', [('공유 AIN4/5용', '공유 AIN4~6용')])
edit('tests/hil/nu54dk/v04_signal_run.py', [('401, 402, 403, 404, 405, 406, 408', '401, 402, 403, 404, 405, 406, 407, 408')])
edit('tests/hil/nu54dk/v04_signal.py', [
    ('SHARED_ANALOG_FIXTURES = (405, 406)', 'INPUT_BIAS_FIXTURES = (406, 407)\nSHARED_ANALOG_FIXTURES = (405,) + INPUT_BIAS_FIXTURES'),
    ('fixture_id == 406', 'fixture_id in INPUT_BIAS_FIXTURES'),
    ('selected["id"] == 406', 'selected["id"] in INPUT_BIAS_FIXTURES'),
    ('"input-bias-shared-ain5-manual-saadc"', 'f"input-bias-shared-ain{fixture_id - 401}-manual-saadc"')])
edit('tests/host/v04_fixture_gate_main.cpp', [('v04::fixtureFamily(407) == v04::FixtureFamily::invalid', 'v04::fixtureFamily(407) == v04::FixtureFamily::analog')])
edit('tests/host/v04_shared_analog_main.cpp', [
    ('{405U, 406U}', '{405U, 406U, 407U}'),
    ('!gate.arm(407,', '!gate.arm(409,'),
    ('!source.prepare(407,', '!source.prepare(408,'),
    ('fixture == 406U', 'fixture != 405U')])
edit('tests/host/test_v04_fixture.py', [
    ('self.assertEqual(catalog["revision"], 4)', 'self.assertEqual(catalog["revision"], 5)'),
    ('("P4", 10),', '("P4", 10), ("P4", 11),'),
    ('405, 406, 408,', '405, 406, 407, 408,')])
edit('tests/host/test_v04_signal.py', [
    ('self.fixture_id == 406', 'self.fixture_id in (406, 407)'),
    ('for fixture_id in (405, 406):', 'for fixture_id in (405, 406, 407):'),
    ('fixture_id == 406 else .010', 'fixture_id in (406, 407) else .010'),
    ('len(records), 48)', 'len(records), 72)'),
    ('for _, result in records), 5184)', 'for _, result in records), 7776)'),
    ('signal.shared_source_readback(source, 2, 407)', 'signal.shared_source_readback(source, 2, 408)')])

path = repo / 'tests/host/test_v04_signal.py'
content = path.read_text(encoding='utf-8')
test = '''    def test_407_button_shared_input_rejects_stuck_low_and_any_output_driver(self):
        """! @brief 버튼 공유 입력의 세 단계·DMA 경계와 눌림 LOW·출력 구성을 거부합니다. """
        vectors = list(signal.vectors("analog", 407))
        self.assertEqual(len(vectors), 12)
        self.assertEqual(len(set(vectors)), 12)
        self.assertEqual(sum(v[1] * v[5] for v in vectors), 2592)
        for vector in vectors:
            phase = vector[2]
            count = vector[1] * vector[5]
            high = phase == 1
            source = [1, phase, 46, 0, int(high), 0, 1, 0, 0xC if high else 0x4]
            status = [1, 1, 1, 1, 0, count, vector[1], 0]
            samples = [1025 if high else 512] * count
            result = signal.shared_analog_result(vector, status, samples, source, 407)
            self.assertEqual(result["scope"], "input-bias-shared-ain6-manual-saadc")
            self.assertEqual(result["phase"], ("pulldown-before", "pullup", "pulldown-after")[phase])
            for wrong in ([0 if high else 1200] * count, samples[:-1], [-32768] * count,
                          samples[:-1] + [1024 if high else 513], [4096] * count):
                with self.assertRaises(ProtocolError):
                    signal.shared_analog_result(vector, status, wrong, source, 407)
            for index, value in ((3, 1), (4, int(not high)), (8, source[8] | 1), (8, 0x80D)):
                wrong = source.copy()
                wrong[index] = value
                with self.assertRaises(ProtocolError):
                    signal.shared_analog_result(vector, status, samples, wrong, 407)

'''
marker = '    def test_shared_source_never_drives_high_and_releases_on_abort(self):'
assert marker in content
path.write_text(content.replace(marker, test + marker), encoding='utf-8', newline='\n')

edit('tests/hil/nu54dk/v04_test_plan.json', [
    ('"shared-ain6-pending-functional-test"', '"shared-ain6-input-bias-button-unpressed"'),
    ('"fixture_ids": [401, 402, 403, 404, 405, 406, 408], "pending_fixture_ids": [407]', '"fixture_ids": [401, 402, 403, 404, 405, 406, 407, 408], "pending_fixture_ids": []'),
    ('407 AIN6/P1.13 버튼도 필수 후속 기능 시험으로 별도 준비한다.', '407 AIN6/P1.13은 버튼을 누르지 않고 B INPUT 바이어스·25ms 정착·12 vector로 동일 LOW/HIGH·GPIO·DMA·cleanup을 검사한다. 버튼 자체·wake 검증은 아니다.'),
    ('405는 오픈드레인·406은 입력 바이어스 각각 12 vector. 407은 안전한 신호원 설계 및 개별 실기 대기.', '405는 오픈드레인, 406·407은 INPUT 바이어스 각각 12 vector. 407은 버튼 미누름 조건이며 각 ID의 실기는 별도 증거로 판정한다.')])
edit('tests/hil/nu54dk/README.md', [
    ('fixture 401~406/408과 420', 'fixture 401~408과 420'),
    ('| 407 | 공유 AIN6 | 별도 설계·결선 안내 대기 | 사용자 지정 필수 후속 기능 시험; 미실행 |', '| 407 | 입력 바이어스→SAADC | B P1.14 → A P1.13/AIN6, GND↔GND | 버튼 미누름; INPUT pull-down/up/down·25ms 정착·12 vector |'),
    ('AIN6 P1.13은 사용자 버튼과 공유합니다. **405→406→407→408을 모두 수행**하며 407은 개별 신호원\n설계·결선 확인·실기 대기입니다. 준비만으로 PASS 처리하지 않습니다.', 'AIN6 P1.13은 SW1 신호(버튼 부품 SW2)와 공유하며 누르면 GND로 연결됩니다(회로도 1·8쪽).\n407은 버튼을 누르지 않고 406과 같은 B P1.14 INPUT 내부 pull-down/up/down·25ms 정착 및\nLOW/HIGH 전 sample·GPIO raw INPUT·DMA·cleanup 판정을 사용합니다. 버튼 자체·debounce·wake 시험은 아닙니다.\n**405→406→407→408 모두 필수**이며 준비와 각 ID의 실제 PASS는 구분합니다.'),
    ('405·406은 각각 sample 길이', '405·406·407은 각각 sample 길이'),
    ('405는 오픈드레인, 406은 입력 바이어스 방식입니다.', '405는 오픈드레인, 406·407은 입력 바이어스 방식입니다.')])
for name in ('README.md', '05_리팩토링_진행_체크리스트.md'):
    path = repo / '00_Docs/01_아두이노 코어 설계/14_리팩토링' / name
    content = path.read_text(encoding='utf-8')
    content += '\n현재 T05/T10/T12의 407 AIN6/P1.13 버튼 공유 입력을 준비·실행한다. 사용자 USB 분리·407 결선·재연결 확인 완료. B P1.14 INPUT pull-down/up/down·25ms 정착·12 vector와 Host·exact pair build 후 SWD 10 MHz 실기·문서·commit·push를 진행한다. 408도 필수 후속이다.\n'
    path.write_text(content, encoding='utf-8', newline='\n')

for name in ('runtime.py', 'prepare.py', 'run.py', 'postflight.py', 'run_host_final.ps1', 'end_checks.ps1', 'record_software.py', 'publish_evidence.py'):
    content = (base / 't12-fixture406' / name).read_text(encoding='utf-8')
    content = content.replace('406', '407').replace('C:\\u3m', 'C:\\u3n').replace('649', '650')
    (work / name).write_text(content, encoding='utf-8', newline='\n')
audit = (base / 't12-fixture406/audit_results.py').read_text(encoding='utf-8')
audit = audit.replace('fixture406', 'fixture407').replace("== 406", "== 407").replace("'fixture_id': 406", "'fixture_id': 407")
audit = audit.replace("result['fixture_revision'] == 4", "result['fixture_revision'] == 5")
audit = audit.replace('ain5', 'ain6').replace('AIN5 VBAT_MON', 'AIN6 button-unpressed')
audit = audit.replace("'battery voltage or PMIC register behavior', 'SB4 continuity'", "'button actuation, debounce or wake behavior', 'calibrated voltage'")
audit = audit.replace('Fixture 407/408 and later T12', 'Fixture 408 and later T12')
audit = audit.replace('독립 LOW/해제/LOW', '독립 입력 pull-down/up/down')
(work / 'audit_results.py').write_text(audit, encoding='utf-8', newline='\n')
collect = (base / 't12-fixture406/collect_build.py').read_text(encoding='utf-8')
collect = collect.replace('C:\\u3m', 'C:\\u3n').replace('u3m-artifact', 'u3n-artifact').replace('t12-fixture405', 't12-fixture406')
collect = collect.replace('9fc12bfbdafbb8a4450ed6cc61ca97b9c1efd220', '96f38e9486c69cda2c76b48029bc0dc9404d9709').replace('prior_fixture405', 'prior_fixture406').replace('406 must run', '407 must run')
(work / 'collect_build.py').write_text(collect, encoding='utf-8', newline='\n')
(work / 'authoring_prepare407.py').write_bytes(Path(__file__).read_bytes())
print('FIXTURE407_PREPARED;INPUT_BIAS_ONLY;408_PENDING')
