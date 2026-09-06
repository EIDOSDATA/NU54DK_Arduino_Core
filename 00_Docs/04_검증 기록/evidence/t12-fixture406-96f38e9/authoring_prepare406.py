"""! @brief 406 입력 바이어스 계약·실행 재현 입력과 확인된 GPIO 결선을 기록합니다. """
from pathlib import Path
import json
import subprocess

repo = Path(r'C:\Users\eidos\GitHub\NU54DK_Arduino_Core')
base = Path(__file__).resolve().parent
work = base / 't12-fixture406'
work.mkdir(exist_ok=False)
baseline = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip()
checkpoint = {'fixture_id': 406, 'baseline_source': baseline,
    'user_confirmation_recorded_at_utc': '2026-09-06T13:25:22+00:00',
    'confirmation_text': '어. 그리 했어.',
    'wiring': 'A P1.12/AIN5 <-> B P1.14; common GND; prior A P1.11 removed; both USB disconnected for wiring then reconnected; DAP UART disconnected; SWD connected; SB4/PMIC unchanged',
    'signal_profile': 'B remains INPUT with pulldown/pullup/pulldown, 25ms settling, no output driver',
    'swd_frequency_hz': 10000000, 'pending_after_406': [407, 408]}
(work / 'checkpoint.json').write_text(json.dumps(checkpoint, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')

path = repo / 'tests/hil/nu54dk/v04_fixtures.json'
text = path.read_text(encoding='utf-8').replace('"revision": 3,', '"revision": 4,', 1)
text = text.replace('406·407은 별도 준비·결선 확인 후 수행 대상입니다.', '406은 입력 바이어스로 별도 준비하고 407은 후속 준비·결선 확인 후 수행 대상입니다.')
insert = '''    {
      "id": 406,
      "family": "analog",
      "banks": [1, 1],
      "instances": [[], []],
      "links": [
        {"dut": ["P4", 10, "P1.12"], "peer": ["P4", 12, "P1.14"], "signal": "peer INPUT pull-down/up/down -> DUT SAADC AIN5"},
        {"dut": ["P2", 30, "GND"], "peer": ["P2", 30, "GND"], "signal": "GND"}
      ],
      "notes": "P1.12/AIN5는 SB4/VBAT_MON을 통해 VBAT 분압기 R8 470kΩ·R11 1MΩ·C12 100nF와 공유합니다(원본 회로도 1·3쪽). B P1.14는 INPUT을 유지하고 내부 pull-down/up/down으로만 신호를 만듭니다. 출력 드라이버·PWM 사용 금지. 각 단계 25ms 정착 뒤 32/256 sample·single/double buffer 12 vector, LOW raw -256~512·HIGH raw 1024 초과~4095의 모든 samples를 요구합니다. controller_role=2. SB4/PMIC 설정 변경 없음; 실제 SB4 상태·배터리 전압 측정이 아닙니다.",
      "pullups": ["B P1.14 INPUT 내부 pull-down/up/down만 사용하고 종료 시 no-pull 입력으로 해제. 외부 저항·전원선 추가 없음."]
    },
'''
assert text.count('    {\n      "id": 408,') == 1
path.write_text(text.replace('    {\n      "id": 408,', insert + '    {\n      "id": 408,'), encoding='utf-8', newline='\n')

path = repo / 'tests/hil/nu54dk/v04_test_plan.json'
text = path.read_text(encoding='utf-8')
text = text.replace('"shared-ain5-ain6-pending-functional-test"', '"shared-ain5-input-bias", "shared-ain6-pending-functional-test"')
text = text.replace('"fixture_ids": [401, 402, 403, 404, 405, 408], "pending_fixture_ids": [406, 407]',
    '"fixture_ids": [401, 402, 403, 404, 405, 406, 408], "pending_fixture_ids": [407]')
text = text.replace('406 AIN5/P1.12 VBAT 분압기와 407 AIN6/P1.13 버튼도 필수 후속 기능 시험으로 별도 준비한다.',
    '406 AIN5/P1.12 VBAT 분압기/SB4·100nF 필터는 B P1.14 INPUT pull-down/up/down·25ms 정착으로 12 vector를 검사한다. 모든 LOW raw -256~512·HIGH raw 1024 초과~4095와 입력 모드 GPIO raw readback·DMA·cleanup을 요구한다. 407 AIN6/P1.13 버튼도 필수 후속 기능 시험으로 별도 준비한다.')
text = text.replace('405는 전용 오픈드레인 12 vector, 406·407은 안전한 신호원 설계 및 개별 실기 대기.',
    '405는 오픈드레인·406은 입력 바이어스 각각 12 vector. 407은 안전한 신호원 설계 및 개별 실기 대기.')
path.write_text(text, encoding='utf-8', newline='\n')

path = repo / 'tests/host/test_v04_fixture.py'
text = path.read_text(encoding='utf-8').replace('self.assertEqual(catalog["revision"], 3)', 'self.assertEqual(catalog["revision"], 4)')
text = text.replace('("P4", 8), ("P4", 9),', '("P4", 8), ("P4", 9), ("P4", 10),')
text = text.replace('401, 402, 403, 404, 405, 408, 420, 430, 440}', '401, 402, 403, 404, 405, 406, 408, 420, 430, 440}')
path.write_text(text, encoding='utf-8', newline='\n')

path = repo / 'tests/hil/nu54dk/README.md'
text = path.read_text(encoding='utf-8').replace('fixture 401~405/408과 420', 'fixture 401~406/408과 420')
text = text.replace('| 406·407 | 공유 AIN5·AIN6 | 별도 설계·결선 안내 대기 | 사용자 지정 필수 후속 기능 시험; 미실행 |',
    '| 406 | 입력 바이어스→SAADC | B P1.14 → A P1.12/AIN5, GND↔GND | VBAT_MON/SB4·100nF 공유 입력; INPUT pull-down/up/down·25ms 정착·12 vector |\n| 407 | 공유 AIN6 | 별도 설계·결선 안내 대기 | 사용자 지정 필수 후속 기능 시험; 미실행 |')
text = text.replace('AIN5 P1.12는 VBAT 분압기/SB4, AIN6 P1.13은 사용자 버튼과 공유합니다. **405→406→407→408을 모두\n수행**하며 406·407은 개별 신호원 설계·결선 확인·실기 대기 상태입니다. 준비만으로 PASS 처리하지 않습니다.',
'''AIN5 P1.12는 SB4→VBAT_MON→R8 470kΩ/VBAT·R11 1MΩ/GND·C12 100nF와 공유합니다.
406은 B P1.14의 **INPUT 내부 pull-down/up/down**으로 필터를 충방전하며 출력 드라이버는 활성화하지 않습니다.
25ms 정착 후 모든 LOW sample이 -256~512, 모든 HIGH sample이 1024 초과~4095여야 PASS입니다.
GPIO raw PIN_CNF mask 0xF0F는 LOW 0x4/HIGH 0xC, 종료 no-pull 입력은 0이어야 합니다.
SB4·PMIC 설정을 변경하지 않으며 실제 배터리 전압이나 SB4 연결 상태를 측정한 것으로 취급하지 않습니다.
AIN6 P1.13은 사용자 버튼과 공유합니다. **405→406→407→408을 모두 수행**하며 407은 개별 신호원
설계·결선 확인·실기 대기입니다. 준비만으로 PASS 처리하지 않습니다.''')
text = text.replace('405는 sample 길이 2 × 단일/이중 buffer 2 × LOW/해제/LOW 3의 **12 vector·2,592 samples**입니다.',
    '405·406은 각각 sample 길이 2 × 단일/이중 buffer 2 × LOW/HIGH/LOW 3의 **12 vector·2,592 samples**입니다. 405는 오픈드레인, 406은 입력 바이어스 방식입니다.')
path.write_text(text, encoding='utf-8', newline='\n')

path = repo / '00_Docs/TODO_v0.4.0.md'
text = path.read_text(encoding='utf-8').replace('AIN4~6은 보드 공유 제한으로 contract-only.',
    'AIN4는 405 오픈드레인, AIN5는 406 입력 바이어스로 추가 기능 시험하며 AIN6/407도 필수 후속이다.')
text = text.replace('회로도 connector mapping, fixture 15개,', '회로도 connector mapping, fixture 17개(405·406 추가),')
text = text.replace('2026-09-06T12:52:24Z 사용자 답변 기록: “ㅇㅇ 했다. P1.11 했다”. 전원 OFF 변경 안내에 따라 A P1.11/P4-9↔B P1.14/P4-12와 공통 GND/P2-30, DAP UART 분리·SWD 연결·각자 USB 재연결 확인. A D/COM5·6, B E/COM7·8. P1.11은 SB1을 통해 PMIC_INT/BQ25186 /INT와 공유하며 DAP 전원 감지 핀이 아니다',
    '2026-09-06T13:25:22Z 사용자 “어. 그리 했어.” 답변 기록. A P1.12/P4-10↔B P1.14/P4-12·공통 GND/P2-30, 이전 A P1.11 제거·전원 OFF 변경/USB 재연결·DAP UART 분리/SWD 연결·SB4/PMIC 유지 확인. A D/COM5·6, B E/COM7·8')
path.write_text(text, encoding='utf-8', newline='\n')

for name in ('README.md', '05_리팩토링_진행_체크리스트.md'):
    path = repo / '00_Docs/01_아두이노 코어 설계/14_리팩토링' / name
    text = path.read_text(encoding='utf-8')
    text += '\n현재 T05/T10/T12의 Fixture 406 AIN5/P1.12를 준비한다. VBAT 분압기·100nF 필터 공유 회로를 확인했고, B P1.14 INPUT pull-down/up/down의 전용 12 vector·25ms 정착·DMA/GPIO/cleanup 검증 후 10 MHz 실기를 수행한다. 사용자 결선 확인 완료. 제품 core·R00~R13 완료는 유지하며 407→408도 필수 후속이다.\n'
    path.write_text(text, encoding='utf-8', newline='\n')

for name in ('runtime.py', 'prepare.py', 'run.py', 'postflight.py', 'run_host_final.ps1', 'end_checks.ps1'):
    text = (base / 't12-fixture405' / name).read_text(encoding='utf-8')
    text = text.replace('405', '406').replace('C:\\u3l', 'C:\\u3m')
    if name == 'run_host_final.ps1':
        text = text.replace('gate-host-final.log', 'gate-host.log')
    (work / name).write_text(text, encoding='utf-8', newline='\n')
print('FIXTURE406_CONTRACT_AND_WRAPPERS_PREPARED;CONFIRMATION_RECORDED;407_408_PENDING')
