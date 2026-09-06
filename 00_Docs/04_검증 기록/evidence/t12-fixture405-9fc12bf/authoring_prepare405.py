"""! @brief 405 실행 계약과 사용자 지정 406~408 후속 범위를 기록합니다. """
from pathlib import Path
import json

repo = Path(r'C:\Users\eidos\GitHub\NU54DK_Arduino_Core')
work = Path(__file__).resolve().parent / 't12-fixture405'
work.mkdir(exist_ok=False)
checkpoint = {'fixture_id': 405, 'baseline_source': 'b6611d7f4de9f40673583f36a4c1ee9fb20b2a43',
              'user_confirmation_recorded_at_utc': '2026-09-06T12:52:24+00:00',
              'confirmation_text': 'ㅇㅇ 했다. P1.11 했다',
              'wiring': 'A P1.11/AIN4 <-> B P1.14 open-drain; common GND; separate USB; DAP UART disconnected; SWD connected; SB1 and PMIC unchanged',
              'swd_frequency_hz': 10000000, 'pending_after_405': [406, 407, 408]}
(work / 'checkpoint.json').write_text(json.dumps(checkpoint, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

path = repo / 'tests/hil/nu54dk/v04_fixtures.json'
text = path.read_text(encoding='utf-8')
text = text.replace('"revision": 2,', '"revision": 3,', 1).replace(
    '외부 장치·배터리·점퍼의 다른 출력이 시험 선을 구동하지 않음',
    'fixture에 명시된 공유 회로 외 외부 장치·배터리·점퍼의 다른 출력이 시험 선을 구동하지 않음')
insert = '''    {
      "id": 405,
      "family": "analog",
      "banks": [1, 1],
      "instances": [[], []],
      "links": [
        {"dut": ["P4", 9, "P1.11"], "peer": ["P4", 12, "P1.14"], "signal": "peer open-drain LOW/release -> DUT SAADC AIN4"},
        {"dut": ["P2", 30, "GND"], "peer": ["P2", 30, "GND"], "signal": "GND"}
      ],
      "notes": "P1.11/AIN4는 SB1을 통해 PMIC_INT/BQ25186 /INT와 공유합니다(원본 회로도 1·3쪽). B P1.14만 S0D1 LOW/해제로 구동하며 강한 HIGH/PWM 출력은 금지합니다. SB1 및 PMIC 설정 변경 없음. controller_role=2, 32/256 sample·single/double buffer마다 LOW→해제→LOW 12 vector. 406·407은 별도 준비·결선 확인 후 수행 대상입니다.",
      "pullups": ["B P1.14 내부 pull-up 사용. SB1 연결 시 보드 R3 10kΩ/VDD_MOD와 병렬. 외부 저항 없음. 실제 SB1 개폐와 무관하게 해제 시 HIGH가 관측되어야 PASS."]
    },
'''
assert text.count('    {\n      "id": 408,') == 1
path.write_text(text.replace('    {\n      "id": 408,', insert + '    {\n      "id": 408,'), encoding='utf-8', newline='\n')

path = repo / 'tests/hil/nu54dk/v04_test_plan.json'
text = path.read_text(encoding='utf-8')
payload = json.loads(text)
old = '"modes": ["ain0-ain1-ain2-ain3-ain7", "board-shared-ain4-ain5-ain6-contract-only", "manual-sample", "single-buffer", "double-buffer"]'
text = text.replace(old, '"modes": ["ain0-ain1-ain2-ain3-ain7", "shared-ain4-open-drain", "shared-ain5-ain6-pending-functional-test", "manual-sample", "single-buffer", "double-buffer"]')
text = text.replace('"fixture_ids": [401, 402, 403, 404, 408]', '"fixture_ids": [401, 402, 403, 404, 405, 408], "pending_fixture_ids": [406, 407], "required_analog_fixture_ids": [401, 402, 403, 404, 405, 406, 407, 408]')
text = text.replace('같은 3.3V domain의 peer PWM을 안전한 AIN0~3/AIN7에 묶음별로 연결한다. DMA 완료 길이·buffer 반환·guard와 HIGH code를 검사한다. 정밀 전압 정확도 시험이 아니며 AIN4 DAP 감지, AIN5 VBAT 분압기, AIN6 버튼에는 peer 출력을 연결하지 않는다.',
    '동일 I/O 전압의 peer PWM을 AIN0~3/AIN7에 묶음별로 연결해 HIGH와 DMA 길이를 검사한다. 405 AIN4/P1.11은 SB1/PMIC_INT/BQ25186 /INT 공유이므로 B P1.14 S0D1·내부 pull-up의 LOW/해제/LOW만 사용한다. LOW raw -256~256, 해제 raw -256~4095 중 95% 이상 >256 및 median >256, 실제 GPIO readback·DMA 길이·cleanup을 확인한다. PMIC 128µs interrupt LOW를 허용하는 기능 oracle이며 정밀 전압 검증은 아니다. 406 AIN5/P1.12 VBAT 분압기와 407 AIN6/P1.13 버튼도 필수 후속 기능 시험으로 별도 준비한다.')
text = text.replace('T05/T08: fixture 401~404/408을 전원 분리 상태에서 하나씩 재결선. AIN4~6은 board-shared 제한을 문서화하고 실기 PASS로 승격하지 않음.',
    'T05/T10/T12: fixture 401~408을 전원 분리 상태에서 하나씩 재결선하고 사용자 확인 후 실행. 405는 전용 오픈드레인 12 vector, 406·407은 안전한 신호원 설계 및 개별 실기 대기. 공유 회로를 이유로 생략하거나 준비만으로 PASS 처리하지 않음.')
assert json.loads(text) != payload
path.write_text(text, encoding='utf-8', newline='\n')

path = repo / 'tests/host/test_v04_fixture.py'
text = path.read_text(encoding='utf-8').replace('self.assertEqual(catalog["revision"], 2)', 'self.assertEqual(catalog["revision"], 3)')
text = text.replace('("P4", 5), ("P4", 8),', '("P4", 5), ("P4", 8), ("P4", 9),')
text = text.replace('401, 402, 403, 404, 408, 420, 430, 440}', '401, 402, 403, 404, 405, 408, 420, 430, 440}')
path.write_text(text, encoding='utf-8', newline='\n')

path = repo / 'tests/hil/nu54dk/README.md'
text = path.read_text(encoding='utf-8').replace('fixture 401~404/408과 420', 'fixture 401~405/408과 420')
text = text.replace('| 408 | PWM→SAADC', '| 405 | 오픈드레인→SAADC | B P1.14 → A P1.11/AIN4, GND↔GND | PMIC_INT 공유 입력의 LOW/해제/LOW·32/256 sample·단일/이중 DMA·GPIO readback |\n| 406·407 | 공유 AIN5·AIN6 | 별도 설계·결선 안내 대기 | 사용자 지정 필수 후속 기능 시험; 미실행 |\n| 408 | PWM→SAADC', 1)
text = text.replace('fixture를 바꿀 때 두 USB 전원을 먼저 분리하고, 표에 없는 전원·신호선은 연결하지 않습니다. AIN4\nP1.11은 DAP 전원 감지, AIN5 P1.12는 VBAT 분압기/SB4, AIN6 P1.13은 사용자 버튼과 공유하므로\n이번 무개조 peer 출력 fixture에서 제외하고 source/build 경계만 검사합니다. 이를 실기 PASS로 표시하지 않습니다.',
'''fixture를 바꿀 때 두 USB 전원을 먼저 분리하고, 표에 없는 전원·신호선은 연결하지 않습니다.
AIN4 P1.11은 **SB1→PMIC_INT→BQ25186 /INT**와 공유합니다(원본 회로도 1·3쪽). 405는 B P1.14를
S0D1·내부 pull-up으로 구성해 LOW 또는 해제만 출력합니다. SB1·PMIC 설정 변경과 강한 HIGH 출력은 없습니다.
SB1 연결 시 R3 10kΩ도 pull-up에 참여하나 실제 SB1 상태를 추정하지 않습니다. LOW raw는 -256~256,
해제 raw는 -256~4095 안에서 95% 이상 >256 및 median >256이어야 합니다. 해제 단계에는 PMIC의 짧은
interrupt LOW를 허용하며 정확한 전압·PMIC 동작 검증으로 확대하지 않습니다. 시작 전 10ms 정착,
명령 38의 실제 GPIO 설정과 전체 ADC sample·hash를 보존하고 양쪽 cleanup 시 B를 먼저 입력으로 해제합니다.
AIN5 P1.12는 VBAT 분압기/SB4, AIN6 P1.13은 사용자 버튼과 공유합니다. **405→406→407→408을 모두
수행**하며 406·407은 개별 신호원 설계·결선 확인·실기 대기 상태입니다. 준비만으로 PASS 처리하지 않습니다.''')
text = text.replace('Analog fixture는 각 ID마다 PWM', '405는 sample 길이 2 × 단일/이중 buffer 2 × LOW/해제/LOW 3의 **12 vector·2,592 samples**입니다.\n401~404/408 Analog fixture는 각 ID마다 PWM')
path.write_text(text, encoding='utf-8', newline='\n')

path = repo / '00_Docs/TODO_v0.4.0.md'
text = path.read_text(encoding='utf-8').replace('다음은 Fixture 408이다.', '다음은 사용자 지정 Fixture 405→406→407→408이다.').replace('다음은 408.', '다음은 405→406→407→408이며 공유 AIN4~6도 개별 기능 시험한다.')
path.write_text(text, encoding='utf-8', newline='\n')
print('FIXTURE405_CONTRACT_PREPARED;406_407_408_REQUIRED_PENDING')
