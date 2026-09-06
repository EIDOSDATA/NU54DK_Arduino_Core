"""! @brief 활성 안내의 오래된 408 직행 문장을 사용자 지정 405~408 순서로 교정합니다. """
from pathlib import Path
repo = Path(r'C:\Users\eidos\GitHub\NU54DK_Arduino_Core')
paths = [repo / p for p in ('README.md', '00_Docs/README.md',
    '00_Docs/01_아두이노 코어 설계/02_구현_로드맵.md',
    '00_Docs/01_아두이노 코어 설계/14_리팩토링/README.md',
    '00_Docs/01_아두이노 코어 설계/14_리팩토링/05_리팩토링_진행_체크리스트.md',
    '00_Docs/04_검증 기록/README.md', 'tests/hil/nu54dk/README.md')]
for path in paths:
    text = path.read_text(encoding='utf-8')
    for old in ('다음은 Fixture 408 PWM→AIN7 결선 변경이다.', '다음은 Fixture 408 PWM→AIN7이다.',
                '다음은 전원 OFF·A P1.07→P1.14/AIN7 변경 후 Fixture 408이다.',
                '다음은 Fixture 408 PWM→AIN7 결선입니다.'):
        text = text.replace(old, '다음 순서는 사용자 지정 405→406→407→408이며 현재 405 AIN4/P1.11 오픈드레인 시험을 준비한다.')
    text = text.replace('다음은 Fixture 408이고', '다음은 Fixture 405→406→407→408이고')
    path.write_text(text, encoding='utf-8', newline='\n')
print('ACTIVE_ANALOG_ORDER_UPDATED')
