# T13 시험 조합과 후속 GPIO 결선

2026-09-08T11:10Z: 정상 단독29/29·동시5/7(C01~05) 완료, C06 실행 중이다.
고정 serial17/21·stream3/4·PWM6/6·역할 전환2/5와 TWIM/System OFF/충돌/CTS의 순차 예약,
UART parity/break/SPI boundary/동시 CTS/RX 공급 지연 예약과 SDA LOW 도구 준비는 [107번](../../../00_Docs/04_검증%20기록/107_T13_S_자동_진행과_System_OFF_계획.md)을
따른다. S 물리 확인 만료21:26:14KST를 연장하지 않으며 미시작/부분 시험은 완료로 세지 않는다.

2026-09-08T09:36Z: 정상 단독29/29·동시2/7(C01·02)이고 C03 실행 중이다.
고정 serial 복구17/21, stream3/4, PWM6/6, 역할 전환2/5와 추가 도구/무인 System OFF의
source별 원본은 [107번](../../../00_Docs/04_검증%20기록/107_T13_S_자동_진행과_System_OFF_계획.md)을 따른다.
아래29/36 등의 수치는 당시 결과이며 현재 완료 수와 합산하지 않는다.

T13 S의 정상 안정성·오류 복구·역할 전환은 별도 완료 기준으로 집계한다.
과거 실패 원본을 유지하고 현재 source별 완료 수와 실행 중 항목은 아래104번 및 활성 TODO에서 확인한다.
T12 완료·QDEC 문제 보고 후 종료 결정은 유지한다. 현재 source별 원본·Host/target·진행도는
[104번](<../../../00_Docs/04_검증 기록/104_T13_S_복구_동시_안정성_검증.md>)을 따른다. 아래 이전 source 이력은 당시 결과다.

2026-09-08 현재: R00~R13·source별 T11 단독 회귀와 **T12 기능검증은 완료**했다. **QDEC도 일부 문제·제한사항을 101번에 보고하고 검증 작업을 완료**했다. 동작 중 수동 read/clear 누산 누락은 미해결이며 실패 결과를 PASS로 변경하지 않는다. 사용자 완료 결정은 T12 마일스톤에 적용하며 알려진 제한은 T14/T15에서 정리한다. 현재는 사용자 S 재배치·실행 중 유지 확인에 따라 T13 실기와 실패 원인 분석을 진행 중이다. S 단독 29개·동시 7조합 및 복구/전환을 진행하고 종료 후 U 결선을 안내한다. S 정상 안정성은 f591571·43bc032의 source별 근거29/36항목이며 복구/전환100회·T13 전체·RC·공개는 미완료다. [문서 감사·요구별 증거 대조](<../../../00_Docs/04_검증 기록/102_개발_문서_전수_검토와_마일스톤_체크포인트.md>), [실행 TODO](<../../../00_Docs/TODO_v0.4.0.md>)를 따른다.

2026-09-07 조합을 확정했고 2026-09-08 사용자가 S 재배치·최대 12시간 유지와 T13 실행을 확인했다.
현재 전용 실행기의 source별 S 정상 안정성 근거29/36항목을 확보했고 실패 원인을 조사 중이다. T12는 문제 보고를 포함해 완료했다.
실행 정의는 [JSON](v04_t13_topologies.json), 생성·검사는 [계획 도구](v04_t13_plan.py)다.

2026-09-08 후속 정정: **다음 마일스톤은 T13 준비·복구·동시·안정성 실기**다.
TIMER는 95번의 두 보드 7,040회 PASS 범위로 기능 완료 정리했으며 추가 필수 반복을 요구하지 않는다.
요구 대조·외부 ADC 반복 수 차이와 승인 전 자동 진행의 경계는
[103번](../../../00_Docs/04_검증%20기록/103_TIMER_기능_완료와_T13_진행_경계.md)을 따른다.

**QDEC는 문제·보완 기록 후 진단을 종료했으며 QDEC20/21 단독과 C07은 현재 실행 목록에서 제외한다.**
[101번 진단](../../../00_Docs/04_검증%20기록/101_T12_QDEC_누산_누락_원인_분리.md)에서
동작 중 manual read/clear 누락을 재현했고 읽기 구간의 IRQ 보호만으로도 해결되지 않았다.
아래 5ms read 구성은 실행 허가가 아닌 원래 시험 목표다. 알려진 제한은 T14/T15에 남기고
다른 T13 조합으로 진행한다. 이 경로의 수정·T12 기능240 재시험을 전체 작업의 선행조건으로
요구하지 않는다. 재개는 별도 범위 결정과 선택 경로의 검증 근거가 필요하다. REPORT-only IRQ는 짧은20회가
일치한 대안 후보이며 기능·포화·큐 오류·연속 조건의 별도 검증 없이 자동 대체하지 않는다.
JSON의 `prerequisite_gates`와 해당 세 실행의 `required_gates`는 알려진 실패 경로의 자동 실행을 막는다.
이 기술적 `hold` 값은 진단을 계속하거나 QDEC 해결까지 다른 개발을 대기한다는 뜻이 아니다.
다른 조합은 이 QDEC 결함에 종속시키지 않되 새 runner·개별 preflight·결선 확인을 거친다.

## 결선 변경이 필요한 이유와 순서

P2 전용 serial00/20은 임의 GPIO로 재배치할 수 없다. UART는 RX=P2.00, TX=P2.02,
CTS=P2.04, RTS=P2.05다. SPIM은 SCK=P2.01, MOSI=P2.02, MISO=P2.04, CS=P2.05이고,
SPIS는 **MISO=P2.02, MOSI=P2.04**다. 현재 같은 P2 GPIO끼리 연결하면 SPIM/SPIS의
data 출력끼리 이어지므로 실행할 수 없다. UART00은 별도의 RX/TX·CTS/RTS 교차가 필요하다.
PDM의 검증된 clock/CS 배치도 현재 I2S용 P1.04/05 직결과 다르다.

후속 실행은 **C → S → U 두 번의 결선 변경**으로 묶는다. S는 SPI00·PDM과 동시 8조합,
U는 UART00 단독/flow/복구용이다. 한 번 바꾸면 T13의 모든 외부 검증이 끝난다고 약속하지 않는다.
System OFF 기본 wake는 기존 검증 근거가 있다. T13의 새 DMA/복구 조건에 재시험이 필요한지
먼저 대조하며, 현재 구체 시험 ID 없이 격리·재연결을 필수 수동 단계로 확정하지 않는다.
필요하다고 판정되면 해당 T13 조건·기존 근거의 부족한 부분·실제 조작을 함께 명시한다.
예약 P2.07/08이나 PMIC 선은 추가하지 않는다.

각 단계에서 두 USB를 분리하고 아래 B 쪽 끝을 옮긴 후, GPIO 대응·GND·동일 I/O 전압,
DAP UART 분리/SWD 연결·전원 레일 미연결을 현재 상태로 확인한다. 새 UID 식별과 해당
catalog의 단일 open-drain 결선 검사를 통과해야 push-pull 출력을 허용한다.
현재 C 세션 확인을 S/U 허가로 재사용하지 않는다. 분기 배선이나 외부 pull-up은 추가하지 않는다.

| A GPIO | 현재 C의 B GPIO | 후속 S의 B GPIO | 후속 U의 B GPIO |
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

## 단독 32개와 동시 8조합

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
  이 연속 시간의 대체 근거가 아니다. 의도적 오류/복구·handover는 아래 별도 ID에서 실행한다.
- STOP 후 DMA·pin·DPPI 구독·IRQ/clock 소유권 반환을 확인하고 17개 net을 입력으로 복원한다.
  중단 이전 시간을 다른 실행에 더하지 않으며 재시작은 새 결과 ID와 새 원본을 가진다.

## 오류 복구와 충돌·handover 시험

구현한 고정 serial 취소/NACK의 mode·원본·100회 판정과 아직 남은 주입은
[복구 실행 항목](T13_RECOVERY.md)에 구분한다. 정상 안정성 시험과 오류 복구 완료는 별개다.

| 대상 | 의도한 오류 또는 전환 | 각 100회 판정 |
| --- | --- | --- |
| UART | DMA 도중 cancel, 제한된 peer RX 공급 지연, 100ms CTS 정지/재개; 별도 peer parity/break | 해당 error/cancel 길이·소유권 확인 후 다음 nonce 정상 송수신. CTS는 단독 4선 및 C01/C05 UART30에서만 |
| SPI | controller CS 조기 해제·slave 미준비/짧은 DMA, 도중 cancel | 불완전 frame을 정상 PASS로 인정하지 않고 다음 CS frame 전체 복구 |
| TWI | peer 전용 미할당 0x44 NACK, TWIS buffer 공급 지연, 승인 격리 bus의 한쪽 SDA open-drain LOW 100ms | 제한 시간 내 오류 검출, LOW 해제·필요한 bus clear/STOP 뒤 0x42 정상 read/write. PMIC 0x6A·P1.02/03에는 주입 금지 |
| I2S/PDM | 한 번의 의도적 buffer 미공급, cancel/STOP, 재구성/재시작 | underrun/overflow/STOP 계약과 guard를 보존하고 새 전역 pattern의 정상 연속 buffer로 복구 |
| QDEC/PWM | 유한 방향 변경·중간 STOP·다시 시작, PWM 미시작 task 취소 | count/sample/STOP과 시작 전 출력 idle, pin·DMA 반환 후 다음 실행 성공 |
| 공유 serial block | 같은 20/21/22/30에서 UART↔SPI master/slave↔TWI master/slave 순차 전환 | 이전 block/IRQ/DMA/pin 해제 후 새 personality 활성, peer 재구성 뒤 정상 payload; 동일 block 동시 소유는 원자적 거부 |
| GPIO/stream/PWM/event | active GPIO alias, overlapping DMA, 같은 GPIOTE/DPPI 채널, 다른 domain 연결, PWM과 analogWrite/tone/Servo 중복 | 이전 실행·guard·출력을 훼손하지 않는 거부와 반환 뒤 재획득. DPPI START 구독은 PWM STOP 전에 해제 |

serial00의 SPI↔UART **외부 송수신** handover는 S/U 결선이 서로 달라 무인 반복 대상이 아니다.
S에서 SPIM00↔SPIS00 역할 전환 100회, U에서 UART00 stop/restart 100회를 별도 수행하고,
서로 다른 personality ownership 거부는 Host/target 입력 상태 검사로 구분한다. 재결선이
필요한 실제 UART↔SPI 전환을 수행한 것처럼 기록하지 않는다.

## 시간과 남은 경계

초기 계획의 순차 연속 측정 총량은 **32×180 + 7×900 + 3600 = 15,660초, 4시간 21분**이었다.
QDEC의 알려진 제한 보고와 완료 결정을 반영한 현재 S 정상 대상은 단독29개와 동시7개로,
**29×180 + 6×900 + 3600 = 14,220초, 3시간 57분**의 전체 측정 분량이다. 이미 완료한 측정까지
포함한 양이며 앞으로 남은 시간 예측이 아니다. U UART00 180초는 별도이며 QDEC 재진단은 예약하지 않는다.
짧은 preflight, 100회 복구/전환, 결선 두 단계, 구현·실패 조사·최종 감사 시간은 별도다.
양쪽 peer 결과로 일부 시간을 묶을 가능성은 실제 instance별 연속 증거를 감사한 뒤 결정한다.

다섯 block 동시 대표 한 조합을 모든 통신/stream 조합의 PASS로 확대하지 않는다.
P1의 승인 출력 여섯 개로 P1 UART 세 개를 모두 4선 flow로 동시에 쓰는 구성은 불가능하다.
P2 dedicated21 bank, LFXO/PMIC/버튼/전원 신호를 추가 자유 GPIO로 쓰지 않는다.
TIMER 기능 완료 정리·QDEC 알려진 제한·외부 ADC 반복 수 차이는103번에 구분한다. 후속 runtime 변경의 영향 T11 회귀, T14 결함 조치, T15 지원 범위,
T16~T18 통합·문서·절차, R14/RC·전체 회귀·사용자 승인·정식 배포는 각각 후속 gate다.


현재 U 직전 자동 실행·peer 제어 System OFF의 추가 범위는 [107번 계획](<../../../00_Docs/04_검증 기록/107_T13_S_자동_진행과_System_OFF_계획.md>)을 따른다.
