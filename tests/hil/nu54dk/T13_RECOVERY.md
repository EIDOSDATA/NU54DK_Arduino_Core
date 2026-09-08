# T13 S 오류 복구 실행 항목과 판정

2026-09-08 현재 S의 정상 사전검사36/36은 f591571에서 통과했고 같은 image의 정식 안정성 시험을
진행 중이다. 아래 오류 주입은 별도 개발·실기 항목이며 아직 실제100회 완료가 없다.
원본과 source별 결과는 [104번](<../../../00_Docs/04_검증 기록/104_T13_S_복구_동시_안정성_검증.md>),
전체 범위와 결선은 [T13 계획](T13_PLAN.md)을 따른다. T12 완료와 QDEC 문제 보고 후 종료 결정은 유지한다.

## 먼저 구현한 고정 serial 오류

| mode | S 대상·주입 역할 | 고정 주입 | 필요한 관측 |
| --- | --- | --- | --- |
| 1 | UART20/21/22/30, 선택한 물리 role | 첫 TX 제출50µs 뒤 cancelTransmit | tx_cancelled·실제0보다 크고1024보다 작은 길이·정확한 buffer 주소·가드 |
| 2 | UART20/21/22/30, 선택한 물리 role | 첫 TX 제출50µs 뒤 cancelReceive | rx_cancelled·실제 부분 RX 길이·정확한 buffer 주소·가드 |
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
이번 수신량으로 해석하지 않는다. 아직 새 source의 실기로 확정한 결과는 없다.

## 이 구현으로 완료되지 않는 항목

| 남은 항목 | 후속 판정 범위 |
| --- | --- |
| UART flow·RX 지연·parity/break | 4선100ms CTS 정지/재개, 2선의 제한된 RX 지연, 별도 parity/break 원인 확인과 복구 |
| SPI slave 조건 | slave 미준비·짧은 DMA 및 CS 조기 종료, 두 역할의 실제 완료·다음 frame 복구 |
| TWI slave·stuck-low | TWIS 공급 지연, 격리 SDA open-drain LOW100ms와 해제/recoverBus 후0x42 정상 송수신 |
| I2S/PDM/PWM | 의도적 한 번의 공급 중단·STOP/재구성, PWM 중간 STOP와 미시작 task 취소 |
| Serial 역할 전환 | 같은20/21/22/30의 UART·SPI master/slave·TWI master/slave 전환, S의SPI00 역할 전환 |
| 자원 충돌 | 같은 block·GPIO alias·DMA 겹침·GPIOTE/DPPI 채널/domain·PWM/analogWrite/tone/Servo 중복의 원자적 거부 |
| U 및 후속 release gate | S 종료 후 U 핀 배치 안내·현재 연결 확인, UART00·지원범위·패키지/RC·승인·공개 |

전체100회 복구 capability나 T13 완료를 이 다섯 mode의 구현/빌드로 선언하지 않는다.
