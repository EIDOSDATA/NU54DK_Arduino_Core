# 점퍼 없이 수행하는 M25 실기

T14 PWM 지연 시작 취소와 관련 T12 준비용 SWD mailbox 프로그램이다. 보드 간 결선 없이
각 NU54DK의 P1.14 한 핀만 PWM 출력으로 사용한다. UART 콘솔·외부 입력은 사용하지 않는다.
부팅 후에는 mailbox 요청을 기다리며 스스로 시험을 시작하지 않는다.

Canonical build scenario는 `nucode.m25.nojumper_hil`이다. Host의
`tests/hil/nu54dk/v04_nojumper.py`는 clean source·board·build record·ELF SRAM symbol을
대조하고, nonce·요청 sequence·원본 응답을 검증한다. 실제 실행은 지정 probe의 배타 lock,
SWD 10 MHz, `auto_unlock=false`, sector flash와 controlled reset/start로 수행한다.
실패 응답은 판정 전에 기록하며 이후 명령은 차단한다. 자동 recover/mass erase는 하지 않는다.

PWM20/21/22 × decoder 4개 × TOP 1000/4000 × 단일/이중 sequence × auto/triggered step ×
finite/loop × 즉시 시작/미시작 취소/CPU START/DPPI START/DPPI 준비 취소로 **보드당 960개**다.
16-byte guard, DMA READY·SEQSTARTED·PWMPERIODEND, 정지 결과, ENABLE=0, pin/DMA/block
lease 해제와 GPIO 복원을 독립적으로 대조한다. DPPI START 구독을 유지한 stop은
ownership_conflict여야 하며, 연결 소유자가 구독을 해제한 다음 실제 stop/cancel을 수행한다.

미시작 취소는 하드웨어 STOPPED 없이 logical stopped 이벤트를 전달한다. 실제 시작이나
DMA 준비 흔적이 있으면 기존 STOP 확인·timeout 시 lease 유지 계약을 따른다. 반환받은
START 주소는 해당 active 실행 동안만 유효하며 CPU/ISR START와 stop을 동시에 호출하지 않는다.

이 결과는 출력 파형의 peer 측정, 주기·듀티 오차, 외부 회로와의 동작을 증명하지 않는다.
해당 T12 실기는 별도 GPIO 결선과 capture 판정이 필요하다.

## 내부 ADC·timer·event 확장

Protocol version 2는 다음 명령을 추가한다. 외부 AIN/GPIO 입력과 UART는 사용하지 않는다.

| op | 생성기 / 보드당 명령 | 실제 관측 |
| --- | --- | --- |
| 2 | adc_vectors / 12 | 내부 VDD/AVDD, 1/2채널·역순 scan, 1/32 sample, 100회 재시작, 보정 완료, VSS 거부 |
| 3 | timer_vectors / 352 | 44 CC × clear/stop 4조합 × 1000/10000 tick, 각 10회 compare/capture·정지·clear |
| 4 | event_vectors / 480 | EGU10 16개 × DPPI10 24개, EGU20 6개 × DPPI20 16개, 각 1000 event × 10회 |
| 5 | bridge_vectors / 44 | PPIB10↔00, 20↔01, 21↔11, 22↔30의 모든 bridge channel 및 원격 DPPI channel, 각 1000 event × 10회 |
| 6 | time_vectors / 4 | 기존 micros/millis/delay/delayMicroseconds를 TIMER20과 1/10ms·100회 대조 |

ADC는 매 반복의 READY/DONE/FINISHED, 선택한 calibration 완료, 전후 16-byte guard,
요청 길이 이후 sentinel과 자원 반환을 검사한다. Host는 마지막 반복의 96-byte RAM 원본도
별도로 읽어 guard·tail·채널 순서·장치 통계 범위를 대조한다. VDD/AVDD raw를 교정 전압으로
취급하지 않는다. calibration 완료 후의 stop/restart이며 진행 중 calibration 강제 중단은 별도다.

Event는 발생 EGU만 CPU로 trigger하고 수신 EGU event를 매번 관측한다. 100us 이상 간격과
2ms 도착 대기를 사용하며 속도·전력 모드 지연 보증은 하지 않는다. PPIB의 서로 다른 두 channel로
왕복해 되먹임을 만들지 않고 양쪽 OVERFLOW.SEND=0도 요구한다. DPPI group은 public API로
소유·구성한 다음 HAL group-enable task를 구동하여 membership과 public release의 disable을
확인한다. endpoint disconnect/채널 disable 이후의 미전달과 해제 후 publish/subscribe·lease도 검사한다.

소유권 negative는 비어 있는 자원에 시험용 system 예약을 설정하고 public acquire가 거부하는지
확인한다. 실제 OS가 소유한 GRTC channel을 재할당하는 시험이 아니다. GRTC의 기존 공개 경로는
Arduino 시간 함수이며 별도 raw GRTC channel API를 가정하지 않는다.

Busy-wait는 nrfx CPU delay와 GRTC의 서로 다른 clock을 사용하므로 V04-EVENT의 ±5%를
요청 시간과 micros 관측값에 적용한다. Sleep은 요청 시간 이상·스케줄링 여유 3ms 이내,
두 경로 모두 별도 TIMER 관측과의 차이는 요청 시간의 5% 이내를 요구한다.
millis와 micros는 양자화 차이 1ms를 허용한다. 최초 35f30b2의 995us 관측을 1000us 미만이라는
이유로 거부한 판정 오류는 95번에 실패 원본과 함께 보존한다.

확장 명령 892개와 PWM 반복 회귀 12개를 합쳐 보드당 904개를 계획한다. 실제 완료 수는
검증 기록의 source·원본 journal로 판정한다. TIMER 44 CC에 1000회 비교를 수행한 결과로
표시하지 않으며, 1000 event 조건은 EGU/DPPI/PPIB 전달 시험에 적용한다.
