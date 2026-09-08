# T13 S 오류 복구 실행 항목과 판정

현재 완료 수는 [107번 자동 진행 기록](../../../00_Docs/04_검증%20기록/107_T13_S_자동_진행과_System_OFF_계획.md)을
따른다. 아래 날짜/source별 수치는 당시 체크포인트이며 현재 완료 수와 합산하지 않는다.

자원 충돌 경로 정정: 현재 단독 UART30은 P0이며 같은 block SPI 활성화 거부만 시험한다.
UART21/22에는 세 mode를 모두 적용한다. 다른 P1 UART의 P0 route를 잘못 요청해 발생한
route 오류를 GPIO/DMA 소유권 거부로 세지 않는다. 총14개 role/mode 조건이며 실기 전이다.

2026-09-08 f591571의26개와43bc032의 I2S/PWM21/PWM22 세 항목으로 정상 안정성 근거29/36을 확보했다.
단독29/29·동시0/7이며 source별 증거다. 고정 serial 복구21항목 중 UART20/21/22/30 TX100회4항목을 완료했다. 이전 실패 원인은 미확정이다.
원본과 source별 결과는 [104번](<../../../00_Docs/04_검증 기록/104_T13_S_복구_동시_안정성_검증.md>),
전체 범위와 결선은 [T13 계획](T13_PLAN.md)을 따른다. T12 완료와 QDEC 문제 보고 후 종료 결정은 유지한다.

## 먼저 구현한 고정 serial 오류

| mode | S 대상·주입 역할 | 고정 주입 | 필요한 관측 |
| --- | --- | --- | --- |
| 1 | UART20/21/22/30, 선택한 물리 role | 첫 TX 제출50µs 뒤 cancelTransmit | tx_cancelled·실제0보다 크고1024보다 작은 길이·정확한 buffer 주소·가드 |
| 2 | UART20/21/22/30, 선택한 물리 role | START 전 RXDRDY 초기화, 첫 실제 RXDRDY 관측50µs 뒤 cancelReceive | rx_cancelled·실제 부분 RX 길이·정확한 buffer 주소·가드 |
| 3 | SPIM00/20/21/22/30, A controller | 첫 transfer 제출50µs 뒤 cancelTransfer | transfer_cancelled·SPI DMA AMOUNT의 부분 전송·peer 원본·가드 |
| 4 | TWIM20/21/22/30, A controller | peer0x42의 첫 transfer 제출50µs 뒤 cancelTransfer | transfer_cancelled·TWI DMA AMOUNT의 부분 전송·주소0x42·가드 |
| 5 | TWIM20/21/22/30, A controller | peer 전용 미할당0x44에 쓰기만 요청 | address_nack·주소0x44·TX DMA AMOUNT0·RX 미요청·가드 |

한 role의 UART를 기준으로 mode/instance21항목이며 각100회다. 다른 role을 실행하면 그 role의
별도 결과로 기록한다. 같은 SPI/TWI pair의 peer 관측을 반대 controller 역할의 주입으로 세지 않는다.
UART00은 U 결선 전에는 실행하지 않는다. PMIC0x6A와 P1.02/03에는 주입하지 않는다.

단독 serial·허용 kind/role만 선택할 수 있고 임의 주소·GPIO·취소 지연 입력은 받지 않는다.
`--phase fault-preflight`는 선택한 각 항목1회, `--phase serial-fault`는 각100회다.
`--fault-mode 1..5`, `--fault-role 1|2`, 기존 고정 `--cases`를 명시한다.
명시적 execute 전에는 image·계획만 검사하며 source/UID/S 확인서/10MHz/controlled flash 규칙은 같다.

## 한 회의 완료 조건

1. 새 seed로 양쪽을 PREPARE하고 HFXO 참조 및 UART 실제 PSEL을 확인한다.
2. 선택한 보드만 고정 오류를 ARM하고 양쪽 START 뒤 최대2초 동안 관측한다.
3. 오류 raw, 양쪽 engine/lane/fault를 모두 보존한다. 예상 오류로 healthy가0이 되는 것을
   정상 전송 PASS로 바꾸지 않는다. reset·lease 만료·잘못된 case는 실패다.
4. 양쪽 STOP·guard·pin·clock 반환을 확인한 뒤 event·주소·부분 길이를 독립 대조한다.
5. `seed XOR 0x9E3779B9`의 다른 데이터로 다시 구성해 정상1초 양방향 송수신·완료량·hash·가드를
   확인하고 STOP한다. 이1초는180초 안정성의 대체 근거가 아니다.
6. 위 조건을 모두 만족한 회만 성공으로 기록한다. 최초 실패에서 중단하고 원본을 보존한다.

UART 부분량은 nrfx terminal event가 반환한 실제 길이를 사용하며 별도 레지스터 대조로 표시하지 않는다.
SPI/TWI는 API event의 descriptor 길이와 별도 DMA AMOUNT를 구분한다. SPIM 취소 event는0 길이를 반환할 수 있고,
TWIM 오류 event는 요청 descriptor 길이를 포함할 수 있으므로 그것만으로 실제 전송량을 판단하지 않는다.
mode5에서는 RX를 요청하지 않는다. RX AMOUNT는 이전 실행 값이 남을 수 있어 raw만 기록하고
이번 수신량으로 해석하지 않는다. 477e159/03f5ba4의 예행21항목과 UART20 TX100회는104번에 source별로 기록한다.

## 이 구현으로 완료되지 않는 항목

역할 전환 실행기의 source별 실기 완료·실패는107번에 기록한다. `--handover-instance 20|21|22|30`은
UART→SPIM→SPIS→TWIM→TWIS→UART와 그 역방향의10개 전환을 각100회 수행하도록 고정한다.
serial00은 S에서 SPIM00→SPIS00→SPIM00 두 전환을 각100회 수행한다.
`--phase handover-preflight`는 이 순서1회이고 `--phase handover`가100회다.
매 전환은 양쪽 STOP·clock/pin 반환 후 새 personality로 구성하고 실제 PSEL을 확인한 다음,
서로 다른 seed의250ms 정상 양방향 구간·완료량·hash·가드를 대조한다.
첫 송수신 성립을 위한300ms 준비와150ms drain은250ms 측정 밖이다.
SPI는 양쪽 MOSI/MISO 신호명과 master/slave를 함께 바꾸므로 GPIO net은 그대로다.
미완료 instance를 다른 instance의 성공으로 대체하지 않는다.

## UART parity·break 오류 주입

`--phase uart-line-preflight|uart-line-fault --uart-line-mode parity|break --fault-role 1|2`
와 S UART20/21/22/30의 case2/3/4/5를 사용한다. 예행1회와 정식100회를 분리한다.
기존 S TX→RX net을 유지하며 실제 U 실기·RX 공급 지연·정상 soak 완료로 확대하지 않는다.

정상 양방향 baseline250ms와 STOP 이후 DUT는 TX를 억제하고 RX만 동작한다.
parity는 DUT8E1/peer8N1이며 첫 byte의 even parity가0인 seed를 선택해 stop1과의 불일치를 만든다.
최초 실제 error event5·mask2·guard를 요구한다. break는 peer UART를 완전히 STOP·반환한 뒤
원래 TX GPIO만 S0S1로 HIGH→1ms LOW→HIGH 구동하고 즉시 입력/no-pull로 반환한다.
양쪽 별도 owner를 겹치거나 활성 UART의 PSEL을 고치지 않는다. 실제 LOW1000~2000µs,
HIGH/LOW/HIGH 관측·GPIO 반환·DUT 최초 framing/break mask4/8을 요구한다.
framing만 관측되면 break 입력 복구 결과와 BREAK flag 관측 여부를 따로 기록한다.

opcode140은 준비 전 정책,141은 ARM,142는20word 최초 원본,143은 준비된 peer break pulse,
144는 DUT 수신 시작 전 peer UART 반환·GPIO HIGH 준비다. DUT RX를 켠 뒤 오류가 아직 없음을
확인하고 LOW를 주입해 UART→GPIO 전환 구간의 부유 입력을 break 결과로 세지 않는다.
원본은 API의 event·mask·buffer·전송량, device cycle1MHz, 실제 CONFIG/PSEL, GPIO 수준·반환,
serial STOP 결과를 보존한다. API descriptor 길이를 실제 DMA 전송량으로 해석하지 않는다.
양쪽 raw를 먼저 보존한 뒤 STOP·clock·17핀 반환, 정책0 복원, 새 seed의 정상1초 송수신과 STOP까지
완료해야 한 복구 성공으로 센다. 첫 실패에서 해당 조건을 끝내고 원본을 보존한다.
2026-09-08T10:10Z 기준 초안 두 역할 target·T13 Host62시험을 통과했으며 실기 미실행이다.

## SPIS 짧은 DMA·미준비 frame

`--phase spi-boundary-preflight|spi-boundary --spi-boundary-mode short|unready`와 S SPIM case6~10을
사용한다. A SPIM/B SPIS의 기존8MHz·1024byte 설정과 GPIO를 유지한다. 예행은1회, 정식은100회다.
매회 정상250ms baseline·STOP 뒤 B에만512byte TX/RX 한 slot 또는 미등록 DMA를 적용한다.
A는1024byte 한 frame만 송수신한다. 비정상 frame은 정상 complete 통계에 더하지 않는다.

짧은 DMA는 B의512byte 실제 TX/RX·OVERREAD/OVERFLOW·CPU semaphore 반환을 요구한다.
A RX 앞512byte는 peer 전역 pattern, 뒤512byte는 ORC255와 같아야 한다. B RX 앞512byte는
controller pattern이며 나머지는0xCC로 보존돼야 한다. 미준비 조건은 B가 CPU semaphore와
DMA의 이전 설정/AMOUNT를 유지하고 수신 RAM을 고치지 않으며 A RX1024byte가 DEF255여야 한다.
이전 AMOUNT를 이번에 수신한 양으로 세지 않는다.

opcode150 정책·151 ARM·152 원본 네 page·153 STOP 이후 TX/RX RAM16page를 사용한다.
첫 event 시점의 API 길이/주소·DMA·CS HIGH·guard와 양쪽 STOP을 보존하고, 두 보드의 TX/RX
전체4096byte를 기대 pattern/ORC/DEF/sentinel과 독립 대조한다. STOP 전 DMA RAM을 Host에
반환하지 않는다. 정책0 복원 뒤 새 seed 정상1초 전송과 STOP까지 성공해야 한 복구로 센다.
짧은 DMA·미준비 조건을 CS 조기 해제·반대 controller 역할이나 정상 soak의 완료로 확대하지 않는다.

판정 근거는 Nordic의 [SPIS 동작](https://docs.nordicsemi.com/r/bundle/ps_nrf54l15/page/spis.html-concept_abk_lbf_wr?contentId=DpeL3a6spBHM4V72K8W3UA)과
[semaphore 동작](https://docs.nordicsemi.com/r/bundle/ps_nrf54l15/page/spis.html-semaphore_abk_lbf_wr?contentId=qTcpD0dkFyr9JQP3EcH1fg)이다.
2026-09-08 구현 준비이며 실기 PASS는 아직 없다.

## CTS 100ms 정지·재개 전용 fixture

S 단독 UART20/21/22/30에서 `--phase flow-preflight|uart-flow --fault-role 1|2 --cases ...`를
사용한다. 전자는1회이고 후자는100회다. 새 source/현재 S·exact UID·10MHz·controlled flash와
결선 사전검사가 필요하다. 아직 실기를 완료하지 않았다.

시험할 role은4선 hardware flow를 그대로 사용한다. peer는 UART 활성화 전에 TX/RX2선과
별도 소유한 GPIO RTS로 구성하여 기존 RTS→DUT CTS 연결에100ms HIGH를 주입한다.
peer UART의 RTS/CTS PSEL은 disconnected이고, 원본의 `_flow_gpio_peer`가 변형을 명시한다.
활성 UARTE의 PSEL을 변경하거나 두 출력으로 한 net을 구동하지 않는다. 출력은 S의 P1.06 또는
P0.02/P0.03 중 원래 RTS에만 배치하며 GPIO 소유권 반환·입력/no-pull 복귀를 요구한다.

양쪽 정상 payload가 먼저 흐른 뒤 observer를 ARM하고 peer GPIO를 HIGH로 바꾼다.
peer device 시각은100000~105000µs, DUT CTS 입력 관측은90000~120000µs여야 한다.
보류 중인 TX가 관측돼야 하고 HIGH 구간의 완료 증가는 경계상1frame 이하, LOW 복귀 뒤에는
새 frame 완료가 있어야 한다. 별도의 정상500ms·전역 pattern/순서/guard와 양쪽 STOP 뒤,
GPIO 주입 정책을 해제하고 새 seed로 원래4선 경로를 재획득해500ms 정상 데이터를 대조한다.
각500ms는180초 정상 안정성의 대체 근거가 아니다.

Opcode126은 비활성 상태의 policy(0기본/1DUT CTS관측/2peer GPIO)를 고른다.127은20word 원본,
128은 정상 송수신이 시작된 뒤 관측·주입을 시작한다.127 순서는 policy, instance, state, 물리 GPIO,
HIGH 시작/끝 cycle, cycle Hz, 시작/끝/current TX frame, pending TX 관측, HIGH/LOW 관측,
GPIO token, PIN_CNF, TX/RX/RTS/CTS PSEL, CONFIG다. 실패 시 양쪽 원본을 STOP 전에 보존한다.
기본 UART20/21/22/30 모두의 양방향8조건이며 C01/C05 flow·RX 공급 지연·parity/break,
peer hardware RTS 생성 자체·U UART00까지 완료한 것으로 확대하지 않는다.

## I2S/PDM 공급 중단 복구 준비

I2S20은 A master와 B slave 각각, PDM20/21은 실제 수신자인 A에서 시험한다.
정상 완료 버퍼 네 개 이후의 다음 공급 요청을 단 한 번 생략한다. 정상 버퍼 반환·검증은 계속하고,
첫 비정상 event와 당시 가드·완료량·queue량·API state를 별도로 보존한다.
I2S의 실제 `underrun`, PDM의 실제 `overflow`가 오지 않거나 앞서 데이터/가드 오류가 나면 실패다.
이 오류는 정상 연속 전송 PASS로 바꾸지 않으며 기존 engine의 unhealthy·자동 STOP도 그대로 기록한다.

Opcode114(mode1 I2S/mode2 PDM)는 PREPARE 뒤 START 전의 단독 stream에만 허용한다.
Opcode115는 20-word 원본을 반환한다. 순서는 mode, stream index, instance, 생략 횟수,
생략 당시 완료/queue량, 생략 cycle, 최초 오류 event/driver error/cycle, 오류 당시 완료/queue량,
guard, API state, 생략 뒤 관측 event 수, 예약0, 선행 error/detail, role, cycle 주파수다.
Picolibc `EOVERFLOW=139`는 target static_assert와 독립 Host 기대값으로 고정한다.

`--phase stream-fault-preflight --stream-fault-mode 1|2 --fault-role 1|2 --cases ...`는 각1회,
`--phase stream-fault`는 각100회다. I2S A/B와 PDM20/21의 네 role/instance 항목이다.
매회 양쪽 raw와 STOP·pin·clock 반환 뒤 새 seed의 정상1초 stream을 독립 대조한다.
이 재시작 구간은180초 안정성의 대체가 아니다. 현재 source별100회 완료·실패·진행 상태는
[104번](<../../../00_Docs/04_검증 기록/104_T13_S_복구_동시_안정성_검증.md>)과 활성 TODO를 따른다.

## PWM/I2S 최초 실패 원인 분리

f591571의 정식 안정성에서 PWM21 LOW535µs와 I2S 약73초 후 양쪽2word 불일치를 관측했다.
원본은104번에 보존하며 두 현상을 같은 원인으로 단정하지 않는다.

`--phase pwm-diagnostic --cases 25|26|27 --pwm-diagnostic-route led|dap`는 단독180초 관측이다.
첫500±8µs 위반 뒤 최대8에지 또는10ms만 더 보존하고 같은 실패로 STOP한다.
정상 soak와 혼합 topology에는 이 모드를 사용할 수 없다. 오류 없는 진단 종료도
`observation-complete`이며 정상180초의 PASS나 허용 오차 변경으로 표시하지 않는다.
`led`는 기존 B P1.14→A P1.14, `dap`는 S에 이미 있는 B P1.06→A P1.07을 사용한다.
양쪽 DAP UART 분리 확인과 S 확인서가 필요하고 새 점퍼나 GPIO 출력은 추가하지 않는다.
다른 기능은 이 진단 구간 동안 활성화하지 않는다.

Opcode116은 비활성 상태에서0(기본)/1(LED 진단)/2(DATA 교차 진단)를 선택한다.
Opcode117은 A의 TIMER22/GPIOTE20 capture 설정·실패 시각·clock과 B의 PWM instance·mode·top·divider·
decoder·loop·shorts·RAMUNDERFLOW·두 DMA BUSERROR bit·AMOUNT/CURRENTAMOUNT·refresh/enddelay·clock을
읽기만 한다. B의 DMA BUSERROR는 sequence0/1을bit0/1로 묶는다. START 직후와 실패 뒤 값을 구분한다.

I2S opcode118 page0은 seed·padding·첫 불일치 index/expected/actual·실패slot·반환량·guard·state를,
page1~16은 STOP 후 해당 반환 DMA의256word를16word씩 보존한다.
Host는 전체 buffer를 독립 전역 pattern으로 대조해 비트 차이와 인접word 일치를 보고한다.
이 분석은 원인 확정이나 정상 PASS가 아니다. 이전 f591571 원본에는 expected/actual이 없으므로
새 source의 재현이 필요하다.

Nordic 문서의 [DPPI 지연 설명](https://docs.nordicsemi.com/r/bundle/ps_nrf54l15/page/ppi.html-concept_latencies)은
전원 domain과 sleep 상태의 추가 지연을 설명한다. 현재 busy loop·HFXO 관측만으로 그 지연을 원인으로
확정하지 않는다. [PWM 레지스터](https://docs.nordicsemi.com/r/bundle/ps_nrf54l15/page/pwm.html-topic)의
RAMUNDERFLOW·DMA 관측도 읽기 대상으로 추가했다.
[DevZone의 시작 펄스 사례](https://devzone.nordicsemi.com/f/nordic-q-a/124546/first-pwm-pulse-stretched-when-starting-nrfx_pwm_complex_playback-on-nrf54l15)는
첫 펄스에 관한 별도 사례로 Nordic 측 재현이 없었으며, 이번15초 후 PWM 실패의 확인된 원인이 아니다.

| 남은 항목 | 후속 판정 범위 |
| --- | --- |
| UART flow·RX 지연·parity/break | 4선100ms CTS 정지/재개, 2선의 제한된 RX 지연, 별도 parity/break 원인 확인과 복구 |
| SPI slave 조건 | slave 미준비·짧은 DMA 및 CS 조기 종료, 두 역할의 실제 완료·다음 frame 복구 |
| TWI slave·stuck-low | TWIS 공급 지연, 격리 SDA open-drain LOW100ms와 해제/recoverBus 후0x42 정상 송수신 |
| I2S/PDM/PWM | 공급 중단 예행4/4 이후 각100회 진행, 아래 PWM 중간 STOP·미시작 task 취소 실행기 exact 검증·실기 |
| Serial 역할 전환 | 같은20/21/22/30의 UART·SPI master/slave·TWI master/slave 전환, S의SPI00 역할 전환 |
| 자원 충돌 | 같은 block·GPIO alias·DMA 겹침·GPIOTE/DPPI 채널/domain·PWM/analogWrite/tone/Servo 중복의 원자적 거부 |
| U 및 후속 release gate | S 종료 후 U 핀 배치 안내·현재 연결 확인, UART00·지원범위·패키지/RC·승인·공개 |

전체100회 복구 capability나 T13 완료를 이 다섯 mode의 구현/빌드로 선언하지 않는다.


후속 opcode119 page0은 PWM 실제 출력 PSEL·핀 상태 또는 capture GPIO·GPIOTE IRQ enable·DPPI 상태를
읽는다. Page1은 진단 모드에서 첫 잘못된 에지를 관측한 A의 동일 20word를 STOP 전에 보존한다.
첫 오류 뒤 추가 레지스터 읽기가 후속 에지 관측에 영향을 줄 수 있으나 첫 오류 판정은 바꾸지 않는다.
일반 soak에는 tail을 허용하지 않는다. DAP 비교는 T13 전용 P1.06 PWM capability가 필요하며,
fd8d4ee에서 이 설정 누락으로 시작 전 거부된 원본은 104번에 남겼다. 제품 핀 정책은 유지한다.
한쪽 PREPARE 실패 시 아직 준비하지 않은 상대 보드에는 보호된 stream 명령을 보내지 않고
engine·clock만 읽는다. 이 경로에서 403으로 STOP 세션까지 잃었던 실행기 문제를 보완했다.

## RX 취소 시점 보완과 예행 결과

477e159의 serial 고정 오류 예행은21항목 중18항목 PASS다. UART TX4개·SPI5개·TWI 취소4개·
TWI NACK4개와 UART20 RX1개다. UART21 RX는0byte·buffer null로 실패했고 RX22/30은 아직 미실행이다.
UART21은 이미 RX1024byte 한 frame을 완료했으므로 자기 TX 제출 시각이 상대 RX 중간을 보장하지 않는다.
양쪽 STOP·clock0·GPIO 입력 반환은 성공했으며 원본을104번에 남겼다.

보완은 RX 취소만 serial service의 첫 실제 RXDRDY 이후50µs에 요청한다. ARM 시 이전 RXDRDY를
지우고 자기 TX 시각에 RX를 취소하지 않는다. 원래20word fault snapshot의 시각 기준은
mode2에서 RXDRDY 최초 관측이며 다른 mode는 기존 TX 제출이다. Opcode120의8word는 mode,
시각 기준(1=RXDRDY), RXDRDY 관측, 취소 전 RX 완료 frame 수, 첫 RX slot pending, 기준/요청/event cycle이다.
Host는 [2,1,1,0,1]과 원래 fault의 세 cycle 일치를 요구하고 실제0보다 크고1024보다 작은
terminal 길이·buffer 소유권·guard·STOP 후 새 seed 정상 재시작을 계속 요구한다.

[Nordic UARTE 레지스터](https://docs.nordicsemi.com/r/bundle/ps_nrf54l15/page/uarte.html-topic)는
RXDRDY의 RXD 도착과 RAM 저장을 구분하며 DMA.RX.AMOUNT는 END/MATCH 뒤 갱신된다고 명시한다.
따라서 진행 중 AMOUNT를 실시간 byte counter로 사용하지 않고 최종 API terminal event의 실제 길이로 판정한다.
이 보완은 HIL 주입 시점과 증거이며 제품 UART 구현을 바꾼 것이 아니다. 새 source 실기에서 확인해야 한다.

## PDM 반복 STOP과 peer 원본

03f5ba4에서 A의 overflow 자동 STOP 이후 B가 CS 해제 transfer_complete(error6/detail0)를 관측했다.
B 자동 STOP은 주변장치를 해제했지만 후속 Host STOP의 중복 deactivate가 wrong_state로 실패했다.
HIL은 해제 성공 뒤에만 source handle을 비워 반복 STOP을 처리한다. 최초 실패 원본과 제품 API는 유지한다.
Host는 예상한 PDM overflow·가드·양쪽 STOP/clock0/GPIO 반환을 먼저 요구하고 peer가 기록한
error6/detail0의 CS 종료 또는 오류 없는 정지를 별도로 판정한다. 다른 peer 오류와 가드 손상은 거부한다.
새 seed 정상1초 재시작까지 통과해야 해당 회의 복구 성공이며 예행은100회 완료가 아니다.

6782084의 PDM20/21 예행은 두 항목 모두 통과했고 I2S 두 역할과 합쳐4/4다.
PDM은 고정0x55의50% 밀도 신호이며 seed가 바뀐다고 물리 payload가 달라지지는 않는다.
초기화한 DMA 버퍼의 새 완료·샘플 범위·가드와 재구성 후 진행으로 복구를 판정한다.

## PWM 동작 중 STOP·미시작 준비 취소

`--phase pwm-recovery-preflight|pwm-recovery --pwm-recovery-mode 1|2 --cases 25 26 27`로
S P1.14 단독 PWM20/21/22만 선택한다. 예행은 각1회, 정식은 각100회로6개 항목이다.
Mode1은 loop 파형의 실제 capture 뒤 중간 STOP하고 정상1초 capture로 재시작한다.
Mode2는 B의 start_via_task 재생 준비·active API·유효한 START task 주소를 확인하되
START를 호출하거나 DPPI START를 구독하지 않는다.100ms 이상 양쪽 pin idle·capture 에지0·
완료0·SEQSTARTED0·LOOPSDONE0·가드를 확인하고 양쪽 STOP/clock0/pin 반환 후 정상1초 capture로 재시작한다.
DMA 레지스터 원본은 보존하되 이전 실행 값이 남을 수 있는 AMOUNT를 새 전송량으로 읽지 않는다.
양쪽 준비·최초 실패의 raw를 보존하고 정지 증명이 없으면 재시작하지 않는다.

Opcode121은 PREPARE 뒤 START 전 단독 B PWM에서만 받는 무인자 선택이다.
Opcode122의13word는 role, PWM instance, deferred 선택, API state, START task 주소,
ENABLE, SEQSTARTED0/1, LOOPSDONE, STOPPED, guard, cycle, cycle 주파수다.
Normal soak는 기존 자동 시작을 유지하며 새 capability bit256 없이 이 시험을 실행할 수 없다.

4aadf29에서 예행6/6 후 정식 PWM20 mode2의6번째 정상 재시작이 이전 CC0 캡처로 실패했다.
TIMER clear/start 뒤 DPPI enable 성공을 먼저 확인하고 event clear·DSB·readback 후 관측을 시작하도록
HIL 시작 순서를 보완한다. 관측 시작 뒤 timestamp를 버리거나 허용 오차를 완화하지 않는다.
최초 실패와 수정 전후 source별 실기 상태는104번에 보존한다.

## TWIM 취소 RX 원본 계측

Opcode123은 mode4 취소에서 이전 DMA AMOUNT와 새 RX 시작 여부를 분리해 보존한다.
20word 순서는 mode, 계측 준비, 이전 TX/RX AMOUNT, 전송 전 clear 뒤 RXREADY/RXEND,
취소 직전 RXREADY/RXEND, 첫 terminal 관측 RXREADY/RXEND, RX RAM 전체0xCC 유지,
slot, submit/cancel/event cycle, terminal TX/RX AMOUNT, 길이, 전송 전 ENABLE, event 수다.
이벤트 초기화는 첫 전송 제출 전에만 시행한다. 동작 중 이벤트를 지우지 않는다.
Host는 양쪽 원본을 STOP 전에 보존한다. RX AMOUNT256이 이전 완료 잔류라는 가설은 아직
실기로 증명하지 않았으며 이 계측 추가로 기존 부분 DMA 판정을 완화하거나 실패를 PASS로 바꾸지 않는다.

## Serial 최초 payload 오류 원본

Opcode124(lane)은 UART/SPI/TWI에서 첫 byte 불일치가 발생한 시점의20word를 보존한다.
순서는 valid, kind, instance, RX 여부, slot, offset, 실제/기대 byte, seed, 완료 frame,
전역 byte 위치 low/high, DMA 주소, 길이, guard, cycle, 오류 앞4byte/오류부터4byte 원본,
같은 위치의 기대4byte 두 개다. 첫4byte 안에서 실패하면 앞 window는 buffer 시작이다.
STOP이나 나중 event로 원본을 덮어쓰지 않고 새 PREPARE에서만 초기화한다. Host는 최초 오류
처리에서 STOP 전에 이를 수집한다. 진단 때문에 기존 PASS 범위·속도·허용 오차를 바꾸지 않는다.

## P1 UART의 자원 충돌 거부

`--phase conflict-preflight|resource-conflict --conflict-mode 1|2|3 --cases 3 4 5
--fault-role 1|2`는 S UART21/22/30의 해당 보드에만 적용한다. 각 mode는 같은 block의 SPI,
다른 UART의 겹치는 DMA workspace, 다른 UART의 동일 GPIO를 순서대로 뜻한다. 예행은1회,
정식은100회이며 매회 기존 데이터 유지·양쪽 STOP 뒤 다른 seed로 원래 UART를 재획득한다.

후보 SPI의 SCK/MOSI는 원래 UART TX/RTS 핀, MISO는 원래 RX 핀을 사용하고 CS는 연결하지 않는다.
후보 UART도 원래 TX/RX를 사용한다. 따라서 후보 활성화가 잘못 허용되더라도 peer 출력 핀으로
새 출력을 배치하지 않으며 후보를 즉시 STOP하고 실패를 보존한다. GPIO를 임의로 입력받지 않는다.

Opcode125(mode)의20word는 mode, 원래/후보 instance, configure/stage/activate/예외 STOP 결과,
원래 state 전후, TX/RX/RTS/CTS PSEL 전후, ENABLE 전후, guard다. 기대값은 configure/stage0,
activate는 mode2 invalid_argument2, 나머지 ownership_conflict8이다. 예외 STOP은 미실행UINT32_MAX,
기존 state는active3·PSEL/ENABLE 동일·guard1이어야 한다. 진단은 별도 원본이며 정상900초 안정성을
대신하지 않는다. UART00/20, event/PWM/legacy 중복 등 나머지 충돌 조건은 별도 미완료로 남긴다.
