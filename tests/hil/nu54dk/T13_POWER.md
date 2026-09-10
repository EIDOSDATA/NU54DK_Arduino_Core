# S 결선에서 A가 제어하는 B System OFF 시험

> 현재 v0.4.0 S 종료 범위에서는 이 T13 peer 제어 결합 시험을 필수 gate로 사용하지 않는다.
> 공개 `BoardSystem` API의 GRTC·사용자 버튼 System OFF wake는 M15 실기에서 완료됐고,
> 이 문서의 T13 timer/GPIO PASS는 주장하지 않는다. 범위 결정과 마지막 원본은
> [113번 기록](<../../../00_Docs/04_검증 기록/113_T13_S_범위_종료와_U_준비.md>)을 따른다.

T13에 추가한 UART DMA 정지·System OFF·복구 경로다. 기존 M15의 사용자 SW0/P1.13 검증과
별도로 기록한다. 이 경로의 성공을 전체 peripheral System OFF·T13·T14·RC 완료로 확대하지 않는다.

## 고정 물리 범위

- A GPIO P1.06 TX → B GPIO P1.07 RX, B GPIO P1.06 TX → A GPIO P1.07 RX.
- A GPIO P1.14 → B GPIO P1.14: A는 평소 입력/no-pull, 예약2초 후 S0D1 LOW100ms.
  B는 GPIO wake 직전 input/pull-up/SENSE_LOW, LOW가 이미 걸려 있으면 진입 거부.
- S 17신호+GND를 유지한다. 나머지 신호는 입력/no-pull이다. UART21 115200 8N1·flow off,
  role별128byte TX/RX DMA workspace 두 개를 사용한다. DAP UART는 계속 분리한다.
- UART의 소유 RX P1.07은 상대 reset/OFF 동안 LOW로 뜨지 않도록 내부 pull-up을 적용한다.
  STOP 뒤에는 input/no-pull로 반환한다. 외부 저항이나 추가 결선을 요구하는 설정이 아니다.
- B의 SWD 하드웨어 스위치를 GPIO로 제어한다고 가정하지 않는다. pyOCD의 정상 disconnect로
  core debug와 DP power request를 해제한 뒤 **B debug-control SW1의 `DISABLE_SWD`만 물리적으로
  격리**한다. `DISABLE_UART`, S 17신호·GND와 USB는 유지한다. 그 뒤 CMSIS-DAP nRESET만20ms
  사용하며 pin-only reset에는 SWD connect·DP/AP 접근을 수행하지 않는다.

## 별도 image와 단계

`nucode.v04.t13_power_s_dut/peer`만 `CONFIG_NUCODE_T13_POWER`를 사용한다. 일반 S image에는
power 모듈·RAM retention·poweroff를 추가하지 않는다. 마지막 SRAM4KiB는 Nordic sample과 같은
0x2002e000에 예약하고 source40자·nonce·sequence·예정 reset 원인·회차·seed·DMA 반환을
checksum으로 보존한다. 명시된 예상 reset 외에는 자동 UART 재시작을 하지 않는다.
GRTC wake에 쓰이는 LFXO는 생산 image와 M15 System OFF 성공 image와 동일하게 NU54DK에
실장된 외부 부하 커패시터 DTSI를 사용한다. 보드 기본 internal 17 pF로 되돌아가면 계약시험이
실패한다.

1. exact source/UID·SWD1MHz·controlled flash 후 기존 S 전기 검사를 모두 수행한다.
   직전 System OFF로 debug power가 해제된 B도 다시 기록할 수 있도록 flash 접속은
   `under-reset`을 사용한다. sector erase·exact UID·`auto_unlock=false`·`--no-reset`은 그대로다.
   System OFF 후 B의 debug power가 해제된 상태에서 10MHz flash가 CMSIS-DAP probe read
   timeout을 남긴 원본을 보존하고, power 실행기만 안정적으로 확인한 1 MHz를 사용한다.
2. 양쪽 TX idle 준비 뒤 A RX를 먼저 시작한다. A ENABLE8·실제 PSEL·RX pending1·기존 오류/트래픽0을
   확인한 다음 B의 예정 pin reset을 기록한다. B debug session을 닫고 pin-only reset한다.
   A의 UART가 ENABLE0인 상태에서 B가 먼저 RX를 시작하지 않도록 실행 순서를 고정한다.
3. A mailbox를 통해서만 B와 통신한다. B source·retention·RESET_PIN·debug request0·C_DEBUGEN0과
   새 challenge20word를 검증해야 `bridge` 단계가 성공한다. 이 단계는 System OFF PASS가 아니다.
4. `timer`는2초 GRTC, `gpio`는 A의 P1.14 LOW로 wake한다. B는 응답 DMA가 끝난 뒤 UART
   deactivate·buffer 소유권·guard·핀 반환·HFXO 정지를 확인하고 OFF에 들어간다.
5. 다른 nonce 명령에 대한300ms 무응답을 A에서 관측한다. 정상 nonce의 sequence는 소비하지 않는다.
   wake 뒤 source·boot+1·정확한 RESET_CLOCK/RESET_LOW_POWER_WAKE·해당 회차/seed·반환 근거·
   새 DMA challenge 응답과 시간 범위를 모두 대조한다. DEBUG reset이나 로그 단절만으로 통과시키지 않는다.
6. 역할별10초 lease를 유지한다. 실패는 원본을 보존하고 자동 재전송하지 않는다. B SWD 재접속은
   마지막 cleanup에서만 허용하며 이 접근이 B를 깨웠다면 System OFF 성공에 포함하지 않는다.
   identity 마지막word의 STOP stamp·소유권·17 PIN_CNF를 확인한다.

B pin-only reset 해제 후에는0.7초를 보장한 뒤 첫 UART 중계를 시작한다. B debug session을
닫은 뒤부터 cleanup 전까지는 `get_all_connected_probes`를 포함한 전체 CMSIS-DAP 열거를
금지한다. 중계 중 상태 검사는 이미 열려 있는 A session의 exact identity만 읽는다.
이를 어기면 nRF54L15의 DIF reset으로 B가 깨어나므로 GRTC/GPIO wake PASS로 세지 않는다.

`v04_t13_power.py --phase bridge|timer|gpio|timer-gpio --repeats 1|100`은 기본 read-only preflight다.
실행은 현재 S grant와 `--execute-fixture --evidence`가 필요하다. 예행1회를100회로 세지 않는다.
System OFF 실행은 `--manual-swd-switch`가 필수다. `timer-gpio`는 B SWD를 한 번 격리한 상태에서
timer와 GPIO를 각1회 연속 검증하고, 둘 다 끝난 뒤 SWD 복원을 확인해 cleanup한다.
유지 중인 S 결선에는 시간 기반 만료를 적용하지 않는다. Firmware 10초 lease·STOP·
전기 검사·probe lock은 유지하며 회차 시작 전 exact grant·A runtime identity를 계속 확인한다.

`--phase bridge-debug --repeats 1`은 응답 손실 원인을 구분하는 단일 진단이다. B의 debug를
유지하고 pin reset·OFF 없이 같은 UART GPIO·DMA와 source/challenge를 검사한다. 이 결과에는
`diagnostic_only=true`, `system_off_requested=false`, `normal_mode_proven=false`를 기록한다.
정상 debug 분리 bridge나 timer/GPIO 복구 성공으로 대체하지 않는다. B의 중계 sequence를 이용해
마지막 STOP을 요청하며, 중계 실패 시 자동 재전송하지 않고 lease 종료·원본·핀 상태를 확인한다.

`--phase bridge-fast-poll --repeats 1`은 정상 debug 분리·pin reset을 유지한 단일 진단이다.
power 소유 구간의 main polling을1ms sleep 대신10us busy wait로 비교한다. 응답 전2ms
간격·DMA·GPIO·오류 판정은 유지한다. 정책을 checksum retention에 보존하고 reset 전후
양쪽 응답으로 대조한다. `diagnostic_only=true`이며 firmware도 이 정책에서 OFF 명령을
거부한다. 성공해도 원래 polling의 bridge나 System OFF 복구 완료로 대체하지 않는다.

고정115200 UART 중계는 요청 RX 완료 후2ms의 응답 간격을 둔다. 다음 RX를 먼저 준비한 뒤
응답 TX를 시작하며, OFF/최종 STOP 응답에서는 다음 RX를 열지 않는다. RX_DONE을 RX_DISABLED와
동일시하지 않기 위한 시험 프로토콜 간격이다. 재준비 거부는 `100 + SerialFabricResult` 오류로
보존하며 자동 재시도하지 않는다. 이 변경은 일반 UART 속도·오류 판정을 완화하지 않는다.

전용 power image도 UART 활성화 전에 Zephyr on/off 관리자로 HFXO 참조를 획득한다.
UART DMA 정지 후 이 참조를 반환하고 XO 정지 확인 뒤 OFF에 들어간다. reset/wake 뒤에는
다시 획득하며 정상 bridge 응답은 XO 실행 bit를 요구한다. STOP stamp의 bit3은 아직 보유한
clock 참조를 표시하므로 정리 성공은 이 bit도0이어야 한다. clock을 강제로 정지시키지 않는다.

## Mailbox

| Opcode | 경로 | 용도 |
| --- | --- | --- |
| 130 | SWD A/B | power magic 확인 후 UART TX·wake pin 준비. 두 번째 인수1은 단일 빠른 polling 진단 |
| 131 | SWD A/B, peer B | RX 시작; peer 경로에서는 compiled source 응답 |
| 132/133 | A | B 요청32word를16word 두 page로 준비·DMA 송신 |
| 134 | A/B | 인수 없음: debug·reset·retention·DMA20word. 인수1: GPIO·UART 유휴선20word. 인수2: polling 정책5word |
| 135 | A | 받은 B 응답의16word page 조회 |
| 136 | peer B | mode·회차·seed를 고정하고 응답 종료 후 OFF 예약 |
| 137 | SWD B / peer B | 예정 pin reset / seed와 결합한 새20word challenge 응답 |
| 138 | A | P1.14의2초 후 LOW100ms 예약 |
| 139 | A/B | UART·wake·retention 허가 해제; B peer 응답은 전송 후 정리 |

134의20word: magic, role, UART active, RX pending, 최초 error, boot count, reset cause,
예정 reset, mode, round, TAD system/debug request, C_DEBUGEN, XO.STAT, TX/RX 완료 수,
OFF 전 DMA 반환 증명, retention 유효, seed, uptime ms.

초기 구현은 [107번 기록](<../../../00_Docs/04_검증 기록/107_T13_S_자동_진행과_System_OFF_계획.md>),
최신 Host/target 준비와 중계 실패·실기 잔여는 [110번 기록](<../../../00_Docs/04_검증 기록/110_문서_정리와_T13_S_잔여_재개.md>)을 따른다.
SPI/TWI/TWIS 완료와 물리 SWD 격리 원인은 [112번 기록](<../../../00_Docs/04_검증 기록/112_T13_S_SPI_TWI_완료와_System_OFF_원인.md>)을 따른다.
전용 image 준비와 실제 OFF/wake 성공은 별개다.

## 최초 UART 오류 원본

`v04_power_fault`는80byte 정렬 SRAM이며 처음 발생한 UARTE event만 기록한다.
20word는 magic0x50464531, role, uptime, event type, error mask, buffer address, transferred,
RX pending, TX pending, ready, BAUDRATE, CONFIG, ENABLE, TX/RX PSEL, TX/RX 수준,
XO.STAT, retained boots, active/wake/TX guard/RX guard bit 순서다. marker는 마지막에 기록한다.
STOP 뒤에도 남으며 새 부팅 때 초기화한다. cleanup 재접속 시 source/role/주소를 검증하여 읽고,
진단 읽기 실패와 STOP 증명 실패는 구분한다. 이 SWD 관측은 debug-free/OFF 성공 증거가 아니다.

`v04_power_idle`의 별도80byte는 초기 RX 설정 전후를 보존한다.20word는 magic0x50494431,
role, uptime, UART21, TX38, RX39, TX PIN_CNF, 이전 RX PIN_CNF·수준, pull-up 뒤 RX PIN_CNF·수준,
TX 수준, ENABLE, CONFIG, BAUDRATE, XO.STAT, retained boots, active1/RX0/TX0이다.
첫 오류 원본과 겹치지 않는 SRAM 주소를 검증한다. 이 원본은 LOW→HIGH 변화 또는 여전히 LOW인
상태를 그대로 보고하며 실제 System OFF·원인 확정의 PASS로 세지 않는다.

`v04_power_hardware_fault`의 독립80byte는 동일 형식으로 최초 저위4bit UART 오류를 보존한다.
합성 큐 초과0x80000000은 이 영역에 넣지 않으며 기존 최초 오류는 그대로 유지한다.
이벤트를 버리거나 이벤트 큐 크기를 늘리지 않는다.

134의 인수1은 magic0x50504931, role, uptime, P1 OUT/IN, P1.06/07 PIN_CNF,
UARTE21 ENABLE/TX/RX PSEL, XO.STAT, active/RX/TX pending, error, TX/RX count,
retained boots, TAD system/debug request를 읽는다. 이 조회는 lease를 갱신하지 않는다.
runner는 기존 연결에서 양쪽 reset 전 상태, A의 peer reset 뒤·RX 시작 뒤·실패 시 상태를
기록한다. B의 debug 분리 뒤 접근 제한과 nonce·sequence·STOP 판정은 유지한다.

134의 인수2는 magic0x50504F31, role, polling 정책, 현재 빠른 polling 활성, error를 읽는다.
이 조회도 lease를 갱신하지 않으며 정책0이 기존 실행 경로다.
