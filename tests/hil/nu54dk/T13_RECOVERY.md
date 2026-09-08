# T13 S 오류 복구 실행 항목과 판정

2026-09-08 f591571의26개와43bc032의 I2S/PWM21/PWM22 세 항목으로 정상 안정성 근거29/36을 확보했다.
단독29/29·동시0/7이며 source별 증거다. 고정 serial 복구21항목 중 UART20 TX100회1항목을 완료했다. 이전 실패 원인은 미확정이다.
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

역할 전환 실행기는 준비됐으며 실기는 미실행이다. `--handover-instance 20|21|22|30`은
UART→SPIM→SPIS→TWIM→TWIS→UART와 그 역방향의10개 전환을 각100회 수행하도록 고정한다.
serial00은 S에서 SPIM00→SPIS00→SPIM00 두 전환을 각100회 수행한다.
`--phase handover-preflight`는 이 순서1회이고 `--phase handover`가100회다.
매 전환은 양쪽 STOP·clock/pin 반환 후 새 personality로 구성하고 실제 PSEL을 확인한 다음,
서로 다른 seed의250ms 정상 양방향 구간·완료량·hash·가드를 대조한다.
첫 송수신 성립을 위한300ms 준비와150ms drain은250ms 측정 밖이다.
SPI는 양쪽 MOSI/MISO 신호명과 master/slave를 함께 바꾸므로 GPIO net은 그대로다.
이 경로의 actual PSEL·역할 반전·생산 route 대조는 아직 새 source 실기로 완료하지 않았다.

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
이 재시작 구간은180초 안정성의 대체가 아니며, 아직 실기100회 완료는 없다.

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
| I2S/PDM/PWM | 위 공급 중단 실행기의 새 source 실기, PWM 중간 STOP와 미시작 task 취소 구현·실기 |
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
