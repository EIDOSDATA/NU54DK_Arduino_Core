# T12 PWM peer capture 첫 240 조건 검증

> 과거 검증 이력입니다. 준비·다음 작업·실행 조건은 기록 당시 기준이며, 현재 진행 상태는 [v0.5.0 TODO](../TODO_v0.5.0.md)를 따릅니다.

2026-09-07. Exact `0d7f3822fe0f1b564ef629613a048b433e8fdeee`에서 Fixture 408의
**기능 240 개·cleanup 240 개·원본 관측 240 개를 통과했다.** 실측 실행은 100.563 초이며
두 보드 SWD 10 MHz, `cmsis_dap.limit_packets=true`를 사용했다. **T12 전체·T13 이후·R14·
RC·정식 공개와 readiness 미해결 8 개는 유지한다.** 첫 경로 준비·인수 근거는 [96번](96_새_PC_인수와_T12_PWM_peer_capture_준비.md)이다.

## 현재 결선과 실행 입력

- 사용자가 두 USB 분리 후 **B GPIO P1.14 → A GPIO P1.14, GND ↔ GND** 결선 완료를 확인했다.
  양쪽 DAP UART 분리·SWD 연결, 동일 I/O 전압·전원 레일/다른 신호/외부 풀업 미연결을 함께 물었다.
  첫 실패 뒤에는 같은 결선과 SWD 위치를 유지한 두 USB 재연결 완료를 별도로 확인했다.
- 새 PC의 A COM12/13·B COM14/15와 각각의 exact UID SHA-256을 새로 대조했다.
  역할은 USB 열거 순서로 정하지 않았다. 원문 UID는 로컬에만 보존한다.
- Board gitlink는 `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3`, NCS/Zephyr/toolchain은 96번과 같다.
  `C:/pwq04`의 clean exact 두 role ELF/HEX·source·board·mailbox identity를 검사했다.
- 초기 image source는 `054d08fc869cb4089434f02800b5c438c1407be9`였다. 0d7f382는 HIL의
  명시적 USB packet 옵션·Host 검사·문서 변경이며 Core/libraries/variants/Zephyr/board 입력은 같다.
  새 SHA의 두 image를 다시 빌드했다. 결선 확인 시각은 새 source에 묶을 때 갱신하지 않았다.
- 배타 probe lock·exact UID·sector erase·`auto_unlock=false`·`--no-reset` load 뒤 controlled
  reset/halt/identity/start를 유지했다. mass erase/recover·속도 하향·SDK/보안 정책 변경은 없다.

## 최초 실패와 USB 진단

| 순서 | source / 설정 | 결과 |
| --- | --- | --- |
| 첫 실행 | 054d08f / 기본 USB 8 packets | A flash 9.344 초·runtime identity 성공, B flash 연결 No ACK; 외부 실행 전·기능 0 개 |
| 첫 읽기 진단 | 같은 source / 10 MHz attach | A identity·출력 off 확인, B는 COM이 보이지만 SWD 읽기도 No ACK |
| 사용자 USB 재연결 | 같은 결선·SWD 위치 유지 | 두 CPUID 읽기 회복, PWM off·P1.14 입력 확인; B의 새 image identity는 미확립 |
| 한 번의 새 실행 | 054d08f / 기본 USB | A flash 중 probe 읽기 timeout; 외부 실행 전·기능 0 개 |
| 두 번째 읽기 진단 | reset/halt/flash 명령 없음 | A HALTED·B SLEEPING, 두 CPUID와 PWM off·P1.14 입력 확인 |
| A flash 원문 대조 | USB 8 packets / 1 packet 각각 | 두 설정 모두 194,188바이트 읽기 완료·HEX 불일치 0; 각각 1.953/2.985 초 |
| 단일 packet 진단 campaign | exact 0d7f382 / 1 packet | A/B flash 4.032/7.203 초·runtime identity 성공, 기능 240·cleanup 240 PASS |

`--cmsis-dap-limit-packets`는 [pyOCD 공식 옵션](https://pyocd.io/docs/options.html)의
단일 in-flight USB 명령 설정을 flash와 이후 mailbox session에 전달한다. 기본 설정은 유지한다.
실제 backend packet 수가 1인지 두 보드에서 읽었고 evidence에도 남겼다. 이 설정으로 이번
campaign은 성공했지만 timeout의 근본 원인이나 모든 PC의 해결책으로 확정하지 않는다.
두 실패의 시간·결과를 성공 campaign에 합산하거나 자동 무한 재시도하지 않았다.

## 기능 범위와 원본 감사

PWM20/21/22 × slot 0~3 × TOP 1000/4000 × duty 0/25/50/75/100% × DMA bit15 극성
두 가지 = 240 조건이다. **Individual load·4 values·CPU start·loop의 첫 capture 경로**에 한정한다.
DMA word 극성과 idle inversion은 별개다. A는 GPIOTE20→DPPI20→TIMER22 CC0 1 MHz로
시각을 capture하고 CPU는 저장된 timestamp/level만 수집한다.

| 감사 항목 | 결과 |
| --- | --- |
| 독립 논리 ID·순서·누락 | 240 개 기대 vector와 정확히 일치, 중복/미실행 0 |
| 비정적 144 조건 | 원본 에지 28,944 개·실측 14,400주기; 에지 시각 증가·level 교대·각 period/duty ±5% PASS |
| 정적 96 조건 | 0/100% level과 에지 없음, 각 100주기 길이인 100,000/400,000 µs 관측 PASS |
| 원본 journal | 실행 결과 배열과 JSONL 전부 일치; 판정 전에 raw가 기록됐는지 확인 |
| 정리 | 모든 조건에서 B 출력 STOP→A capture 반환 순서, 두 응답 `[0,1,1]` 확인 |
| 종료 | 두 role/source identity, SLEEPING, PWM20/21/22 ENABLE=0, DPPI20 CHEN=0 확인 |

실측 period의 전체 범위는 1002~4050 µs다. 서로 다른 TOP의 범위를 합친 값이며 각 조건을
자신의 TOP과 비교했다. duty의 목표 대비 비율은 `1000/1003`~`2077/2005`로 모두 상대 ±5%
안에 있다. 평균으로 이상을 숨기지 않았고 절대 clock 교정·jitter 보증으로 확대하지 않는다.

보조 postflight 스크립트는 처음에 두 P1.14 PIN_CNF를 모두 reset 기본값 2로 기대해 실패했다.
실제 관측은 **A=0, B=2**다. `GpioteFabric::release()`는 `GPIO_INPUT`으로 반환하므로 A=0은
입력 buffer 연결·pull 없음·sense 없음이다. PWM 반환 B=2는 입력 buffer 분리다. 두 값 모두
입력이며, 이 구현의 해제 동작과 맞는다. 원본 관측과 최초 assertion을 가진 스크립트를 보존하고
별도 감사에서 이 차이를 명시했다. 하드웨어 상태를 바꾸거나 A를 2로 복원했다고 주장하지 않는다.

## Host·target·원격 검사

- Clean exact 0d7f382 Host: **86 그룹·689 PASS·2 조건부 SKIP**. 추가 USB 계약 검사 2 개 포함.
  SKIP는 M13 설치본 CLI 발견 조건과 M14 생성 native executable의 Windows Application Control
  차단이다. compile/link·constexpr 결과와 native 실행을 구분하며 정책을 변경하지 않았다.
- 계약 45·package 20·문서 207 개 PASS, C/C++ 정렬 373 개 PASS. DUT/peer target **2/2**,
  109.915 초 build-only. HIL wrapper만 달라졌지만 새 SHA로 두 이미지를 준비했다.
- 앞서 푸시한 054d08f는 [Software Gates](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/34100094685)
  7/7과 [Reproducible Builds](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/34100094766)
  8/8 모두 SUCCESS다. 인계 f42bda5의 15/15는 96번의 별도 결과다. 이 후속 push의 CI는 새 SHA로 구분한다.

## 증거와 다음 단계

- [독립 기능·종료·Host 감사](evidence/t12-pwm-capture-0d7f382/hardware/audit.json)
- [성공 campaign](evidence/t12-pwm-capture-0d7f382/hardware/attempt1.json) / [원본 에지 journal](evidence/t12-pwm-capture-0d7f382/hardware/attempt1.json.jsonl)
- [첫 실패](evidence/t12-pwm-capture-0d7f382/initial-failures/attempt1.json) / [두 번째 실패](evidence/t12-pwm-capture-0d7f382/initial-failures/attempt2.json)
- [실제 flash 읽기 진단](evidence/t12-pwm-capture-0d7f382/initial-failures/flash-read-diagnostic.json)
- [현재 결선 확인](evidence/t12-pwm-capture-0d7f382/hardware/confirmation.json) / [종료 raw](evidence/t12-pwm-capture-0d7f382/hardware/postflight.json)
- [ELF/HEX 식별](evidence/t12-pwm-capture-0d7f382/hardware/images.json) / [58 개 원본·공개 사본·gzip SHA](evidence/t12-pwm-capture-0d7f382/raw-files.json)
- [054d08f 후속 CI snapshot](evidence/t12-pwm-capture-0d7f382/ci-054d08f.json)

원본 58 개 중 두 번째 실패 JSON 1 개는 오류 문자열의 UID만 공개 사본에서 가렸다.
그 파일의 원문은 로컬에 보존하며 원문 SHA와 공개 사본 SHA를 구별한다. `.raw.gz`는 이 경우
공개용 마스킹 사본이다. 나머지 57 개는 원문을 gzip으로 복원할 수 있다. ELF/HEX는 이 PC의
`C:/pwh04`·`C:/pwq04`에 보존한다. 원본 실패·중간 보존 폴더·build 경로를 삭제하지 않았다.

초기 기록 commit `0128953`의 공개 사본 검사에서는 네 target build.log의 SHA 목록이 Git blob과
달랐다. 원문에 남아 있던 CRLF를 Git이 추가로 LF로 바꾼 결과이며, 각 360바이트 차이를 줄바꿈만의
차이로 확인했다. 원문 gzip·원문 SHA는 유지하고 `normalized_sha256`을 실제 Git blob에 맞게
보정했다. 최초 SHA도 manifest의 `initial_normalized_sha256`에 남겼다. 수정 뒤 58 개 Git 사본·
gzip·공개 UID 비노출을 모두 다시 검사한다. 이는 로그 사본의 metadata 교정이며 실기 결과 변경은 아니다.

다음은 PWM common/grouped/wave-form·32/256 values·sequence0/1 순서와 end/repeat·DPPI
START·triggered-step·idle inversion의 준비/실기다. 이후 GPIO/GPIOTE, I2S 100 연속 buffer와
TX-only/RX-only·1024 word, QDEC 1000 cycle·방향 전환·read/clear/restart·invalid transition·반복을
이어간다. 현재 408 두 선은 유지된 상태이며 다음 외부 실행 전 현재 확인의 유효시간과 조건을
다시 검사한다. 이 기록으로 T12 전체나 T13 이후·RC·정식 공개를 완료 처리하지 않는다.
