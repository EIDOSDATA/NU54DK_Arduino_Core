# S 결선에서 A가 제어하는 B System OFF 시험

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
  core debug와 DP power request를 해제한 뒤 CMSIS-DAP nRESET만20ms 사용한다.
  pin-only reset에는 SWD connect·DP/AP 접근을 수행하지 않는다. 실제 성립은 peer 응답으로 판정한다.

## 별도 image와 단계

`nucode.v04.t13_power_s_dut/peer`만 `CONFIG_NUCODE_T13_POWER`를 사용한다. 일반 S image에는
power 모듈·RAM retention·poweroff를 추가하지 않는다. 마지막 SRAM4KiB는 Nordic sample과 같은
0x2002e000에 예약하고 source40자·nonce·sequence·예정 reset 원인·회차·seed·DMA 반환을
checksum으로 보존한다. 명시된 예상 reset 외에는 자동 UART 재시작을 하지 않는다.

1. exact source/UID·SWD10MHz·controlled flash 후 기존 S 전기 검사를 모두 수행한다.
2. 양쪽 TX idle 준비 후 B의 예정 pin reset을 기록한다. B debug session을 닫고 pin-only reset한다.
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

`v04_t13_power.py --phase bridge|timer|gpio --repeats 1|100`은 기본 read-only preflight다.
실행은 현재 S grant와 `--execute-fixture --evidence`가 필요하다. 예행1회를100회로 세지 않는다.
새 회차 전 남은 확인 시간이20초 미만이면 시작하지 않는다. 사용자 확인의 원래 만료를 연장하지 않는다.

`--phase bridge-debug --repeats 1`은 응답 손실 원인을 구분하는 단일 진단이다. B의 debug를
유지하고 pin reset·OFF 없이 같은 UART GPIO·DMA와 source/challenge를 검사한다. 이 결과에는
`diagnostic_only=true`, `system_off_requested=false`, `normal_mode_proven=false`를 기록한다.
정상 debug 분리 bridge나 timer/GPIO 복구 성공으로 대체하지 않는다. B의 중계 sequence를 이용해
마지막 STOP을 요청하며, 중계 실패 시 자동 재전송하지 않고 lease 종료·원본·핀 상태를 확인한다.

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
| 130 | SWD A/B | power magic 확인 후 UART TX·wake pin 소유권 준비 |
| 131 | SWD A/B, peer B | RX 시작; peer 경로에서는 compiled source 응답 |
| 132/133 | A | B 요청32word를16word 두 page로 준비·DMA 송신 |
| 134 | A/B | 인수 없음: debug·reset·retention·DMA20word. 인수1: GPIO·UART 유휴선20word |
| 135 | A | 받은 B 응답의16word page 조회 |
| 136 | peer B | mode·회차·seed를 고정하고 응답 종료 후 OFF 예약 |
| 137 | SWD B / peer B | 예정 pin reset / seed와 결합한 새20word challenge 응답 |
| 138 | A | P1.14의2초 후 LOW100ms 예약 |
| 139 | A/B | UART·wake·retention 허가 해제; B peer 응답은 전송 후 정리 |

134의20word: magic, role, UART active, RX pending, 최초 error, boot count, reset cause,
예정 reset, mode, round, TAD system/debug request, C_DEBUGEN, XO.STAT, TX/RX 완료 수,
OFF 전 DMA 반환 증명, retention 유효, seed, uptime ms.

구현·Host/target 결과와 실제 성공/실패는 [107번 기록](../../../00_Docs/04_검증%20기록/107_T13_S_자동_진행과_System_OFF_계획.md)에 따로 남긴다.

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
