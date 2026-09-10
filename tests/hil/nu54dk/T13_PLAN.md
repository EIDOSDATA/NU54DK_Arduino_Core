# T13 시험 조합과 S/U GPIO 결선

현재 결선은 **S**이며, 합의한 S 범위는 **56 PASS + System OFF 2건 제외로 정리 완료(100%)**입니다.
U 소프트웨어 준비도 완료했지만, U 재결선·flash·실기는 **NOT RUN**입니다.
현재 결과와 다음 마일스톤은 [TODO](../../../00_Docs/TODO_v0.4.0.md),
오류 주입 계약은 [복구 안내](T13_RECOVERY.md), 제외된 추가 전원 시험 설계는 [T13 System OFF](T13_POWER.md)를 확인합니다.

## 현재 적용 범위

- 단독 180초·일반 동시 900초·대표 C05 3600초를 유지합니다. 정상 S 36항목은 source별 완료했습니다.
  C05의 1시간 soak도 이미 PASS했으며, U 뒤의 미실행 필수 시험으로 중복 등록하지 않습니다.
- QDEC20/21·C07은 알려진 문제 보고 후 제외했습니다. T12 완료를 다시 보류하지 않습니다.
- serial00/20/21/22/30의 연속 personality/역할 전환과 같은 경로의 timing 진단은 사용자 결정으로 제외했습니다.
  과거 handover2/5를 현재 미완료 항목으로 요구하거나 다시 실행하지 않습니다.
- 제외 결정은 오류 수정·새 PASS가 아닙니다. 같은 기능의 취소·STOP·정상 재시작은 별도 복구 범위입니다.
- [Topology JSON](v04_t13_topologies.json)은 원래32단독/8동시 정의입니다. QDEC의 required gate와 현재 제외 결정을 함께 적용합니다.
- S 종료·U 준비는 [113번](<../../../00_Docs/04_검증 기록/113_T13_S_범위_종료와_U_준비.md>),
  전체 문서 정리와 남은 마일스톤은 [114번](<../../../00_Docs/04_검증 기록/114_전체_문서_정비와_남은_마일스톤.md>)을 따릅니다.
  이전 기록의 미완료 수치와 다음 실행은 각 source 당시의 상태입니다.

## 결선 변경이 필요한 이유와 순서

P2 전용 serial00/20은 임의 GPIO로 재배치할 수 없다. UART는 RX=P2.00, TX=P2.02,
CTS=P2.04, RTS=P2.05다. SPIM은 SCK=P2.01, MOSI=P2.02, MISO=P2.04, CS=P2.05이고,
SPIS는 **MISO=P2.02, MOSI=P2.04**다. 같은 P2 GPIO끼리 연결하면 SPIM/SPIS의
data 출력끼리 이어지므로 실행할 수 없다. UART00은 별도의 RX/TX·CTS/RTS 교차가 필요하다.
PDM의 검증된 clock/CS 배치도 이전 C 결선의 I2S용 P1.04/05 직결과 다르다.

전체 결선 순서는 **C → S → U**이며 C→S 변경과 합의한 S 검증은 완료했다.
U는 아직 실행하지 않은 UART00 단독/flow/복구용 후속이다.
System OFF 추가 결합 시험은 기존 S의 UART21 중계와 P1.14 GPIO wake를 사용하도록 준비했다.
공개 API의 GRTC·사용자 버튼 wake는 M15에서 이미 실기 PASS했고 이후 해당 구현의 실질 변경이
없으므로, T13 peer 제어 timer/GPIO 2조건은 필수 S gate에서 제외했다. T13 PASS로 소급하지 않으며
최신 근거는 [113번](<../../../00_Docs/04_검증 기록/113_T13_S_범위_종료와_U_준비.md>)을 따른다.
예약 P2.07/08이나 PMIC 선은 추가하지 않는다.

각 단계에서 두 USB를 분리하고 아래 B 쪽 끝을 옮긴 후, GPIO 대응·GND·동일 I/O 전압,
DAP UART 분리/SWD 연결·전원 레일 미연결을 현재 상태로 확인한다. 새 UID 식별과 해당
catalog의 단일 open-drain 결선 검사를 통과해야 push-pull 출력을 허용한다.
위 전원 분리·재배치는 실제 결선을 바꿀 때의 절차다. 유지 중인 S를 이유 없이 분리하지 않는다.
현재 사용자가 유지한다고 확인한 S 결선에는 임의 시간 만료를 적용하지 않으며, 재개와 새 이상 발생 시
전체 GPIO 연결성을 먼저 확인한다. T13 runner도 시간 만료를 제거했지만 firmware lease·watchdog,
exact UID/image와 단절 fault latch는 유지한다. C 세션 확인을 S/U 허가로 재사용하지 않는다.
분기 배선이나 외부 pull-up은 추가하지 않는다.

| A GPIO | 이전 기능 C의 B GPIO | 현재 S의 B GPIO | 후속 U의 B GPIO |
| --- | --- | --- | --- |
| P1.14 | P1.14 | P1.14 | P1.14 |
| P1.10 | P1.10 | P1.10 | P1.10 |
| P1.04 | P1.04 | **P1.05** | P1.05 |
| P1.05 | P1.05 | **P1.04** | P1.04 |
| P1.06 | P1.07 | P1.07 | P1.07 |
| P1.07 | P1.06 | P1.06 | P1.06 |
| P0.00 | P0.00 | P0.00 | P0.00 |
| P0.01 | P0.01 | P0.01 | P0.01 |
| P0.02 | P0.02 | P0.02 | P0.02 |
| P0.03 | P0.03 | P0.03 | P0.03 |
| P2.00 | P2.00 | P2.00 | **P2.02** |
| P2.01 | P2.01 | P2.01 | P2.01 |
| P2.02 | P2.02 | **P2.04** | **P2.00** |
| P2.03 | P2.03 | P2.03 | P2.03 |
| P2.04 | P2.04 | **P2.02** | **P2.05** |
| P2.05 | P2.05 | P2.05 | **P2.04** |
| P2.06 | P2.06 | P2.06 | P2.06 |
| GND (P2-30) | GND (P2-30) | GND (P2-30) | GND (P2-30) |

C→S에서는 B 쪽 P1.04/05 두 끝과 P2.02/04 두 끝을 바꾼다.
S→U에서는 A P2.00/.02/.04/.05에서 오는 네 선의 B 끝을 위 표대로 재배치한다.
P1.04/05 교차는 유지한다. Header 위치가 필요한 경우 [현재 GPIO/header 표](COMMON_WIRING.md)를
함께 보되 `P2.02`라는 GPIO를 `P2` header의 2번 핀으로 오해하지 않는다.

### U 실행 소프트웨어 경계

U는 `nucode.v04.t13_u_dut`/`nucode.v04.t13_u_peer` 두 image와 firmware
`CONFIG_NUCODE_T13_HARNESS=3`을 사용한다. Host runner는 `--harness U --cases 1`을
요구하며 UARTE00 1 Mbit/s 8N1 full-duplex 180초, 양방향100 ms RTS→CTS 정지/재개,
TX/RX DMA 취소·STOP 뒤 새 nonce 재시작만 허용한다. U에서 SPI/TWI/I2S/PDM/PWM,
parity/break, reverse-serial, resource handover를 요청하면 probe를 열기 전에 거부한다.

S 확인서는 U에 재사용하지 않는다. 실제 U 실행 전에 두 USB를 분리하고 위 네 선을
재배치한 뒤, 현재 UID·U 결선·DAP UART 분리·SWD 연결·전압·전원 레일·GND를
다시 확인한 `v04-t13-u-session` 승인서가 필요하다. 그 다음 U 전체17선
open-drain 결선 검사가 통과하기 전에는 push-pull 통신을 시작하지 않는다.

## 단독 32개와 동시 8조합

다음은 원래 계획의 전체 정의다. QDEC 단독 2개와 C07을 제외한 현재 대상은 단독 30개·동시 7조합이며,
S의 단독 29개·동시 7조합은 완료했고 UARTE00 단독 1개가 남았다. 후속 runtime 변경의 영향 회귀는
기존 완료 이력과 분리해 결정한다.

단독은 UART 5·SPIM 5·SPIS 5·TWIM 4·TWIS 4·SAADC 1·PWM 3·PDM 2·I2S 1·QDEC 2,
각 180초다. 각 대상의 역할·route·핀·속도·buffer는 JSON의 `standalone`에 고정했다.
UART00만 U, 나머지는 S다. UART는 1 Mbaud/8N1/1024 byte×2/RTS-CTS,
SPI는 8 MHz/mode0/MSB/1024 byte×2, TWI는 400 kHz/0x42/write-read/256 byte×2를 목표로 한다.
단독 기능 PASS가 없는 새 route/rate는 먼저 짧은 기능 preflight를 수행한다.
TWI는 peer 내부 pull-up의 실제 통신을 먼저 확인하며, 실패하면 원본을 남기고 HOLD한다.
속도를 임의로 낮춰 목표 속도의 PASS를 만들지 않는다. PMIC 공유 bus에는 적용하지 않는다.

아래 표의 UART20/21은 동시 P1 pin 수에 맞춘 2선이며 UART30만 RTS/CTS 4선이다.
단독 flow 시험을 생략하는 의미가 아니다. 동시에 사용되는 buffer는 모두 별도 RAM이며
요청 영역 앞뒤 16-byte guard를 둔다. 전용 runner의 구현·실기 진행은
[104번](../../../00_Docs/04_검증%20기록/104_T13_S_복구_동시_안정성_검증.md)에 기록한다.

| ID | 동시에 계속 활성화할 경로 | 시간 | 선택 이유 |
| --- | --- | --- | --- |
| C01 | UART20 + UART21 + TWIM22↔TWIS22 + UART30 | 900초 | 세 P1 block과 P0 block, UART/TWI 동시 IRQ/DMA |
| C02 | SPIM20↔SPIS20 + UART21 + UART30 | 900초 | SPI 연속 완료와 두 UART 수신 공급 |
| C03 | UART20 + SPIM30↔SPIS30 + TWIM22↔TWIS22 | 900초 | P0 SPI와 P1 UART/TWI domain 배치 |
| C04 | SPIM20↔SPIS20 + TWIM21↔TWIS21 + TWIM30↔TWIS30 | 900초 | 서로 다른 두 I2C bus와 SPI |
| C05 | SPIM00↔SPIS00 + UART20 + UART21 + TWIM22↔TWIS22 + UART30 | **3600초** | 양쪽 serial00/20/21/22/30 다섯 block 대표 부하. 이 조합의 900초를 대체 |
| C06 | I2S20 + B PWM20→A capture + A SAADC + UART30 | 900초 | full-duplex I2S와 event capture·ADC·serial 공존 |
| C07 | A QDEC20←B phase + UART20 + UART21 + UART30 + A SAADC | 900초 | 짧은 QDEC read 주기와 연속 UART 수신의 공존 |
| C08 | A PDM20←B SPIS21 mono source + B PWM21→A capture + A SAADC + UART30 | 900초 | PDM 지속 buffer 공급과 serial/event/ADC 공존 |

S의 P1.04/05 교차에 맞추어 peer SCK/LRCK/CS/TX/RX를 재할당한다. 현재 T12의 고정 530
I2S runner를 S에서 그대로 실행해서는 안 된다. C06은 A SCK=P1.04/LRCK=P1.05,
B SCK=P1.05/LRCK=P1.04, 양쪽 TX=P1.06/RX=P1.07이다. C08은 A CLK=P1.04,
DATA=P1.06, CS=P1.05 → B SCK=P1.05, MISO=P1.07, CS=P1.04다. B MOSI=P1.06은 입력이다.

C01~C04·C07은 이전 C에서도 peer pin 재할당으로 계획할 수 있고 C06은 이전 530 배치가
맞지만, 현재 실행은 사용자가 확인한 **S에 모은 C01~C06·C08**이다. C07은 알려진 QDEC 제한으로 제외한다.
C05의 SPI00과 C08의 기존 PDM 신호원은 C에서 실행하지 않는다.

I2S는 48 kHz/32-bit/stereo/256 word×3 슬롯, PDM은 16 kHz/mono/1024 sample×4,
PWM은 TOP1000/individual/32 values/loop(C06 50%, C08 25%), QDEC은 256µs sampling,
2ms/step·5ms hardware read·100회전마다 방향 전환이다. SAADC는 12-bit/32 sample×2,
2ms SAMPLE의 내부 VDD 또는 VDD/AVDD scan을 사용한다. 상세 자원과 GPIO는 JSON에 있다.

## 실제로 측정할 내용

- nonce·전역 sequence가 다른 양방향 payload를 계속 공급한다. 각 buffer의 실제 길이,
  raw/CRC와 순서, DMA 소유권과 guard를 검사한다. 같은 정상 buffer를 반복 읽어 PASS로 세지 않는다.
- 시작/종료 device monotonic 시각, 실제 계속 활성 상태, 완료 byte/sample/edge 수, 누락·중복,
  의도하지 않은 reset, 오류 event와 최대 buffer 공급 시간을 저장한다. 예상 밖 loss/reset은 0이어야 한다.
- 매 service 구간의 cycle 수·최대 service gap, queue 처리와 API 제출→완료 event 관측의
  histogram/max/합계를 기록한다. Service 밖의 시간에는 mailbox·대기·OS 작업도 포함되므로
  순수 CPU idle/사용률로 표시하지 않는다. IRQ 발생→진입이나 하드웨어 요청→Host 관측 지연의
  측정도 아니다. 계측되지 않은 구간을 이 histogram의 PASS로 대체하지 않는다.
- 180/900/3600초 동안 정상 데이터 흐름을 끊지 않는다. 매 vector에서 STOP하는 sweep은
  이 연속 시간의 대체 근거가 아니다. 의도적 오류/복구는 아래 별도 ID에서 실행한다. 연속 handover는 제외했다.
- STOP 후 DMA·pin·DPPI 구독·IRQ/clock 소유권 반환을 확인하고 17개 net을 입력으로 복원한다.
  중단 이전 시간을 다른 실행에 더하지 않으며 재시작은 새 결과 ID와 새 원본을 가진다.

## 오류 복구·자원 충돌과 제외 범위

구현한 고정 serial 취소/NACK의 mode·원본·100회 판정은
[복구 실행 항목](T13_RECOVERY.md)에 보존한다. 정상 안정성 시험과 오류 복구 완료는 별개다.
아래는 원래 오류·충돌 요구의 전체 정의이지 남은 S 실행 대열이 아니다. 조기 CS, TWIS read 공급 지연,
전체 GPIO/overlap, active GPIOTE/DPPI 및 PWM/analogWrite/tone/Servo 충돌의 추가 증거 경계는
[110번 요구 대조](<../../../00_Docs/04_검증 기록/110_문서_정리와_T13_S_잔여_재개.md>)와 T14/T15에서 판단한다.

| 대상 | 의도한 오류 또는 전환 | 각 100회 판정 |
| --- | --- | --- |
| UART | DMA 도중 cancel, 제한된 peer RX 공급 지연, 100ms CTS 정지/재개; 별도 peer parity/break | 해당 error/cancel 길이·소유권 확인 후 다음 nonce 정상 송수신. CTS는 단독 4선 및 C01/C05 UART30에서만 |
| SPI | controller CS 조기 해제·slave 미준비/짧은 DMA, 도중 cancel | 불완전 frame을 정상 PASS로 인정하지 않고 다음 CS frame 전체 복구 |
| TWI | peer 전용 미할당 0x44 NACK, TWIS buffer 공급 지연, 승인 격리 bus의 한쪽 SDA open-drain LOW 100ms | 제한 시간 내 오류 검출, LOW 해제·필요한 bus clear/STOP 뒤 0x42 정상 read/write. PMIC 0x6A·P1.02/03에는 주입 금지 |
| I2S/PDM | 한 번의 의도적 buffer 미공급, cancel/STOP, 재구성/재시작 | underrun/overflow/STOP 계약과 guard를 보존하고 새 전역 pattern의 정상 연속 buffer로 복구 |
| QDEC/PWM | 원래 QDEC 방향 변경·STOP 요구는 제외. PWM STOP·미시작 task 취소는 완료 | QDEC 원본과 알려진 제한 유지. PWM 출력 idle·pin·DMA 반환·재획득 판정은 복구 기록 참조 |
| 공유 serial block 연속 전환 | **사용자 결정으로 필수 검증 제외·재실행 중단** | 기존 증거 보존. 동일 block 동시 소유 거부의 별도 자원 충돌 결과는 유지 |
| GPIO/stream/PWM/event | active GPIO alias, overlapping DMA, 같은 GPIOTE/DPPI 채널, 다른 domain 연결, PWM과 analogWrite/tone/Servo 중복 | 이전 실행·guard·출력을 훼손하지 않는 거부와 반환 뒤 재획득. DPPI START 구독은 PWM STOP 전에 해제 |

serial00의 SPI↔UART **외부 송수신** handover는 S/U 결선이 서로 달라 무인 반복 대상이 아니다.
S의 SPIM00↔SPIS00 연속 역할 전환도 제외한다. U의 UART00 stop/restart는 별도 복구 범위이며,
서로 다른 personality ownership 거부는 Host/target 입력 상태 검사로 구분한다. 재결선이
필요한 실제 UART↔SPI 전환을 수행한 것처럼 기록하지 않는다.

### 고정 CTS 시험의 양쪽 수신 준비

CTS runner의 유지 구간과 정상 재획득 구간은98의 인수1로 먼저 양쪽 RX DMA만 준비한다.
두 성공 응답을 모두 받은 뒤184로 각 보드의 송신을 허용한다. 인수 없는98을 쓰는 다른
시험의 시작 절차는 유지한다. 이 선택은 S의 UART20/21/22/30 및 C01/C05로 제한한다.
PREPARE/STOP에서 송신 보류 상태를 초기화하며 수신 준비 실패 후에는 송신을 허용하지 않는다.

기존 보드별100ms 지연만으로는 PC의 두 시작 명령 사이가100ms를 넘을 때 peer 준비를
보장할 수 없다. 새 절차는 이 Host 간격과 수신 준비를 분리한다. 각 시작·허용 응답의 Host
상대 시각도 원본에 남긴다. payload·CTS100ms·guard·기존 통신 재개 기준은 유지하며,
이 보완만으로 이미 발생한 runtime UART/I2S 오류가 해결됐다고 기록하지 않는다.

## 시간과 남은 경계

초기 계획의 순차 연속 측정 총량은 **32×180 + 7×900 + 3600 = 15,660초, 4시간 21분**이었다.
QDEC의 알려진 제한 보고와 완료 결정을 반영한 현재 S 정상 대상은 단독29개와 동시7개로,
**29×180 + 6×900 + 3600 = 14,220초, 3시간 57분**의 전체 측정 분량이다. 이미 완료한 측정까지
포함한 양이며 앞으로 남은 시간 예측이 아니다. U UART00 180초는 별도이며 QDEC 재진단은 예약하지 않는다.
위 시간에는 preflight·복구 반복·결선·원인 조사·감사가 포함되지 않는다. C→S와 합의한 S 반복은 이미 완료했다.
실제 남은 U는 S→U 한 차례 재결선·17선 검사·단독 180초 및 양 역할 CTS/TX/RX 복구이며,
후속 영향 회귀·T14/T15 판단과 최종 감사 시간은 별도로 결정한다.

다섯 block 동시 대표 한 조합을 모든 통신/stream 조합의 PASS로 확대하지 않는다.
P1의 승인 출력 여섯 개로 P1 UART 세 개를 모두 4선 flow로 동시에 쓰는 구성은 불가능하다.
P2 dedicated21 bank, LFXO/PMIC/버튼/전원 신호를 추가 자유 GPIO로 쓰지 않는다.
TIMER 기능 완료 정리·QDEC 알려진 제한·외부 ADC 반복 수 차이는103번에 구분한다. 후속 runtime 변경의 영향 T11 회귀, T14 결함 조치, T15 지원 범위,
T16~T18 통합·문서·절차, R14/RC·전체 회귀·사용자 승인·정식 배포는 각각 후속 gate다.

U 직전 S 종료 범위와 peer 제어 System OFF 제외는 TODO와
[113번 기록](<../../../00_Docs/04_검증 기록/113_T13_S_범위_종료와_U_준비.md>)을 따른다.
