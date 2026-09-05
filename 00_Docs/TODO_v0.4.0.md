# v0.4.0 릴리스까지의 실행 TODO와 재개 기록

| 항목 | 내용 |
| --- | --- |
| 문서 ID / 개정 | TODO-V04-001 / 2.2 |
| 상태 | 활성 TODO — T01~T11 역사적 체크포인트 완료; R00~R13 뒤 current-source T11·T12~T15 통합 실기 |
| 작성·갱신일 | 2026-09-06 |
| 작성 직전 기준 commit | `25c7f035cc10093a370a693871fe2704a5a069f3` |
| 목표 | 합의한 코어 기능 검증을 마치고 Windows용 `v0.4.0` 정식 공개 및 공개 URL 검증 완료 |
| 다음 착수 항목 | **R02 — Serial 전송 완료·timeout·동시 호출 정확성** |
| 이번 요청의 실행 범위 | 2026-09-06 사용자 지시: R00~R13을 번호 순서대로 구현·시험·문서화하고 전체 software/target/examples/style 검증과 main commit/push까지 자동 진행한다. current-source T11 직전에 멈추며 flash·HIL·결선 변경·공개는 수행하지 않는다 |

이 파일은 대화 기억이나 컨텍스트 요약에 의존하지 않고 작업을 이어가기 위한 **활성 실행 목록**이다.
마일스톤의 제품 상태는 [로드맵](<./01_아두이노 코어 설계/02_구현_로드맵.md>), 실제 PASS/FAIL은
[검증 기록](<./04_검증 기록/README.md>), 공개 허용 조건은
[M27 readiness](../variants/nu54dk/v0.4.0-release-readiness.json)가 소유한다.
TODO의 체크만으로 그 원본들의 상태를 바꾸지 않는다. 이 문서는 새 flash·공개·삭제 권한을 주지 않는다.

## 1. 작업 시작·재개 규칙

1. 이 파일 전체와 아래 **재개 체크포인트**를 먼저 읽는다. 새 사용자 지시가 있으면 범위를 대조한다.
2. 실제 checkout에서 `git rev-parse --show-toplevel`, `git status --short`, `git log -1`,
   `git submodule status`를 확인한다. 다른 사람의 미커밋 변경을 되돌리거나 덮어쓰지 않는다.
   이 문서 작성 환경의 저장소는 `C:\Users\eidos\GitHub\NU54DK_Arduino_Core`이며 다른 PC에서는
   실제 checkout 경로를 사용한다. 옛 대화의 폴더명이나 임시 build 경로를 현재 경로로 추정하지 않는다.
3. [42번 범위 합의](<./04_검증 기록/42_v0.4.0_코어_기능_검증_범위_합의.md>)와
   [41번 온보드 실기 기록](<./04_검증 기록/41_M24_M26_온보드_protocol_교정과_실기_재검증.md>)을
   읽고, 해당 작업의 추가 원본을 3절에서 찾아 읽는다. 과거 기록의 HOLD는 당시 상태다.
4. 작업할 T 번호·선행조건·이번에 만들 산출물·검사 방법을 체크포인트에 적은 뒤 구현한다.
5. 완료 기준과 증거가 모두 충족될 때만 해당 `[ ]`를 `[x]`로 바꾼다. 부분 완료는 체크하지 않고
   진행 내용·남은 항목을 적는다. 막힌 작업은 원인과 필요한 사용자 행동을 적고 안전한 독립 작업만 진행한다.
6. 단계별로 구현·시험·문서를 묶는다. **2026-09-05 추가 지시: T01~T09를 마친 뒤 저장소가 직접
   관리하는 전체 C/C++를 한국어 Doxygen 주석, BSD/Allman, 들여쓰기·탭 폭 4칸으로 정리하고,
   한 줄 `if`/`for`/`while` 등을 포함해 제어문 중괄호를 생략하지 않는다. 이후 회귀 검사와 최종
   커밋·푸시를 수행한다.** 이미 있는 로컬 체크포인트 커밋은 보존하며 이 최종 조건 전에는 새로
   푸시하지 않는다. SDK·서드파티·보드 서브모듈·기존 공개 자산은 정렬 대상에서 제외한다.
   `.clang-format`과 재실행 가능한 검사 경로를 남기고, 자동 정렬로 의미가 바뀌지 않았는지 검증한다.
   주석은 정확한 동작·소유권·제한을 설명하며 단순 번역으로 잘못된 보증을 추가하지 않는다.
   종료·중단·인계 전에는 체크포인트를 반드시 갱신한다.
   실행 중 프로세스가 있으면 명령·세션·출력 경로와 종료/대기 상태를 남긴다.
7. 중간 보고는 사용자가 요청한 상태 설명, 오류·안전 문제·결선 요청 위주로 한다. 조용히 작업하더라도
   증거와 TODO 상태 갱신을 생략하지 않는다.

순서는 T01→T11 체크포인트 뒤 R00→R13, current-source T11 회귀, T12→T15, T16→T18,
R14, T19→T25를 기본으로 한다. 독립적인 준비는 겹쳐 진행할 수 있지만 선행조건·안전 확인을
건너뛰지 않는다.
결함 수정은 어느 단계에서든 필요하면 T14로 되돌아간다. 소스가 바뀌면 영향받는 검증을 다시
수행하며, 이전 버전의 PASS를 새 artifact의 PASS로 복사하지 않는다.

## 2. 현재 재개 체크포인트

| 필드 | 현재 값 |
| --- | --- |
| 이번에 끝낸 일 | T01~T11. UART Fixture 101~103, SPI Fixture 201~203에 이어 exact `e2f045c`의 TWI Fixture 301에서 계획 기능 record 1,986개·cleanup 2·campaign 기록 2건, 총 1,990 result를 10 MHz SWD로 PASS |
| 진행 중인 T 항목 | R00·R01 완료. 51번 기준선과 [52번 R01](<./04_검증 기록/52_R01_CMake_source_소속_교정.md>)에 잘못된 target 소속의 실패 재현과 교정·실제 target 9/9·software gate를 보존. 기존 T11 physical 결과와 구분한다 |
| 다음 구체적 행동 | R02에서 SPIM/TWIM stale completion·operation generation·event 소비자·timeout과 같은 handle submit/cancel/deactivate를 실제 production adapter Host fault injection으로 재현하고 파일 이동 없이 교정 |
| 다음 작업에 필요한 사용자 행동 | R00~R13 구현·software gate에는 없음. 최종 current-source T11 회귀를 시작할 때 안내한 첫 fixture로 전원 OFF 상태에서 결선 변경 |
| 외부 결선 상태 | Fixture 301 SDA·SCL·GND가 연결된 상태, 외부 저항·전원 rail 없음, 양쪽 `DISABLE_UART` 분리·`DISABLE_SWD` 연결. R13 뒤 최종 T11 회귀 시작 전 USB 전원을 끄고 해당 fixture 결선으로 변경해야 함 |
| 작업 checkout 분리 | 없음. 제품 작업은 `main`에 통합됐고 과거 임시 worktree/branch는 정리했다 |
| 마지막 정식 외부 HIL source | `e2f045c1b4272d986d17456c5af051fe8af74f19` — Fixture 301 두 보드 exact role image TWI PASS |
| 작성 당시 readiness | 필수 16개 중 미해결 8개; T09 무배선 PASS만 추가됐으며 외부 결선·RC·최종 공개 승인 없음 |
| 알려진 문제 | Fixture 201 RXDELAY와 Fixture 301 TWIS 지연 buffer 재개 결함은 각각 exact 수정 뒤 전체 재시험 PASS. Fixture 301 revision 1 외부 저항 누락 실행은 무효, exact `e25ebb0` 실패는 결함 증거로만 외부 보존. Exact `e2f045c` evidence의 NACK/cancel 복구 record 6쌍은 동일 논리 ID라 journal 순서·seed로 구분하며 기능 누락은 없다. 이후 runner는 오류 원인을 ID에 포함하도록 교정 |
| 이 TODO 작성 작업의 실행 중 시험 | R01 software/target 검사 종료. 실행 중인 장치 시험 없음, 새 flash/HIL 없음. 기존 Fixture 301 실행은 50번 역사 기록을 따른다 |
| 로컬 임시 build·evidence | R00 `C:/r00`, R01 `C:/r01` 보존. 원본 log는 이번 작업 공간 `work/r00/`, `work/r01/`, 영구 JSON은 evidence의 `r00-ec3bba3/`, `r01-d2c125c/`. 이전 성공·무효·실패 evidence는 보존 |
| 최종 정렬 gate | clang-format 22.1.8로 직접 관리 C/C++/ino 227개 write·dry-run PASS. Fixture 102 기록 전 남은 공통 header 들여쓰기 한 곳을 교정했고 M12 Host 전체·DUT/peer target 2/2 재검증 PASS, 실기 image와 runtime HEX SHA-256 동일. 한국어 Doxygen·Allman/4칸/중괄호 필수 적용 |
| CI 확인 | 이전 `661fad9`의 [Software Gates](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/33913811058)와 [Reproducible Builds](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/33913811030) success 보존. `25c7f03` 계획 통합은 로컬 전체 gate를 통과해 원격 `main`에 push됐으며, 당시 로컬 GitHub CLI 인증이 없어 새 Actions 상태는 미확인 |
| 문서 작업 검증 | Markdown 158개 UTF-8·내부 링크 PASS, CI contract 45/45 PASS, inventory 계획 75/M24 23/M26 16/M27 16 PASS, package 20/20 PASS, M12 Host 전체 PASS. M27 미해결 blocker 8개는 유지한다 |
| 커밋 찾기 | `git log -1 -- 00_Docs/TODO_v0.4.0.md`; 자기 commit hash를 본문에 소급 끼워 넣지 않음 |

이미 있는 기반은 M23 inventory, M24/M25 후보 source/build, M26 지원 경계 판정과 네 온보드
runner의 기본 PASS다. 온보드 PASS는 UART 4개·PMIC I2C 3개·내부 VDD/event·TEMP/WDT30에 한정한다.
이전 비공개 후보의 예제 29/29 compile은 [39번 기록](<./04_검증 기록/39_M27_v0.4.0_rc1_자동_준비와_HOLD.md>)의
다른 source 결과이며 최종 RC·stable 검증을 대체하지 않는다. 아래 25개 체크는 **남은 전체 작업**의 완료를 뜻한다.

### 연결 실패를 다시 만났을 때

- `USB 장치/COM 열거`, `SWD 응답`, `firmware READY/결과 수신`을 별도로 기록한다. USB 케이블이
  꽂혀 있다는 이유로 모두 정상이라고 보거나, UART 무응답만으로 CPU가 죽었다고 단정하지 않는다.
- 초기 수신/실행 순서, WDT reset protocol, SAADC SAMPLE, TWIM enable, 꺼진 콘솔 예약은 41번에서
  교정했다. WDT 시험의 의도한 reset을 crash로 세지 않는다. 예상 reset 밖의 잡음을 무시하지 않는다.
- 2026-09-05 peer P0 CTS 고정에 대해 사용자가 HW 엔지니어의 일부 납땜 이슈를 전달했고,
  성공한 정상 경로 근거를 유지하며 계속 진행하도록 지시했다. 이는 현장 HW 진단 전달 기록이다.
  납땜 위치·수리·재시험은 확인되지 않았으므로 해당 FAIL을 지우지 않고 반복 시험은 중단한다.
  외부 MCU 핀까지 불량이라고 일반화하지 않으며 다른 DAP/USB 실패의 원인에도 소급 적용하지 않는다.
- 기존 COM5/COM6 자체의 이탈 원인은 미확정이다. AMD CPU, Windows 차단 알림, SWD 스위치를
  확인 없이 원인으로 확정하지 않는다. [40번 진단](<./04_검증 기록/40_M24_M26_온보드_재개와_USB_UART_진단.md>)을 참조한다.
- 당시에 Windows가 차단한 것은 GDB의 외부 WinLibs `iconv.exe` 실행이었다. pyOCD 차단 근거와
  혼동하지 않는다. Host/target PATH를 분리하고 실제 Python·pyOCD module 경로를 확인한다.
- `auto_unlock=false`, sector erase, exact UID, controlled start를 유지한다. No ACK에 대응해
  자동 mass erase/recover, 무한 재시도, 다른 보드로 무단 전환, 보안 정책 변경을 하지 않는다.
- 재발하면 시각·UID 식별·COM·USB/PnP 오류를 남기고 사용자에게 필요한 재연결을 요청한다.
  포트·케이블·다른 PC 비교는 한 번에 한 조건씩 바꿔 별도 진단으로 기록한다.

## 3. 작업별 원본과 범위

| 작업 | 먼저 대조할 원본 |
| --- | --- |
| 전체 범위·상태 | [로드맵 §8](<./01_아두이노 코어 설계/02_구현_로드맵.md>), [경쟁 마일스톤 M24~M27](<./01_아두이노 코어 설계/08_전_인스턴스_DMA_BLE_경쟁_마일스톤.md>), [42번 합의](<./04_검증 기록/42_v0.4.0_코어_기능_검증_범위_합의.md>) |
| 리팩토링 안정화·선행 구조 작업 | [리팩토링 문서 안내](<./01_아두이노 코어 설계/14_리팩토링/README.md>), [통합 실행계획](<./01_아두이노 코어 설계/14_리팩토링/02_리팩토링_통합_실행계획.md>), [진행 체크리스트](<./01_아두이노 코어 설계/14_리팩토링/05_리팩토링_진행_체크리스트.md>) |
| 인스턴스·공유 자원·DMA | [inventory JSON](../variants/nu54dk/peripheral-manifest.json), [생성 matrix](<./01_아두이노 코어 설계/09_M23_Peripheral_인스턴스_매트릭스.md>), [serial 계약 JSON](../variants/nu54dk/serial-fabric-contract.json) |
| 통신·analog·stream 후보 | [SerialFabric](../cores/arduino/nucode/SerialFabric.h), [AnalogFabric](../cores/arduino/nucode/AnalogFabric.h), [StreamFabric](../cores/arduino/nucode/StreamFabric.h), [Kconfig](../zephyr/Kconfig), [M24 계약](<./01_아두이노 코어 설계/10_M24_Serial_Fabric_경로와_API_계약.md>) |
| HIL·결선·환경 | [HIL README](../tests/hil/nu54dk/README.md), [Windows 개발환경](<./02_빌드 설계/09_Windows_개발환경_설정.md>), [보드 회로도](<../board_package/NU54DK_Zephyr_DTS/NU54-DK Schematic.pdf>)와 해당 board source |
| M25·M26 구현 이력 | [37번 M25](<./04_검증 기록/37_M25_Analog_Event_Stream_Fabric과_온보드_HIL_준비.md>), [M26 지원 경계](<./01_아두이노 코어 설계/11_M26_System_Peripheral_지원_경계.md>), 41번의 최신 기본 실기 증거 |
| RC·공개 | [M27 도구 안내](../tools/release/M27_README.md), [RC 준비 문서](<./05_릴리스/v0.4.0-rc.1/README.md>), [readiness](../variants/nu54dk/v0.4.0-release-readiness.json) |

범위는 Windows용 `v0.4.0` 코어 기능이다. Linux/macOS 지원과 새 BLE 확장을 추가하지 않는다.
온보드 자원·두 NU54DK의 안전한 peer/loopback·합성 신호·capture를 사용하며, 필요한 점퍼·풀업은
시험별로 안내한다. 외부 마이크/코덱/엔코더별 호환성, 정밀 ADC·jitter·전력·음질·신호 품질은
필수 gate 밖이다. **코어의 실제 데이터 경로·DMA·오류 복구·동시성·soak는 면제하지 않는다.**
합성 peer로도 신호를 생성·검증할 수 없는 필수 경로는 HOLD이며, 추가 범위 변경은 사용자에게 확인한다.

생성 문서는 JSON·생성기를 고친 뒤 재생성한다. Board submodule, SDK와 기존 공개 자산은 임의로
수정하지 않는다. `v0.1.0`·`v0.2.0`은 비지원 역사 버전이며, 기존 tag·asset·검증 기록은 보존한다.

## 4. A단계 — 결선 없이 준비 (T01~T09)

- [x] **T01 — 최종 시험 목록 확정**
  - 상태·선행: 완료 / TODO·42번 합의·41번 실기 기록과 exact board gitlink 대조. 결선 불필요.
  - 할 일: 인스턴스·모드·route별 test ID, 속도, buffer 크기, 반복/soak 시간, 예상 결과·오차·오류 조건을 정의한다.
  - 완료 기준: 재사용/신규 시험, 온보드/결선/범위 밖, 적용 가능한 DMA·flow control·errata가 구분된 시험표와 누락 검사가 있다.
  - 증거: [시험 목록](<./01_아두이노 코어 설계/12_v0.4.0_기능_시험_목록.md>)과 [43번 준비 기록](<./04_검증 기록/43_v0.4.0_시험_준비와_구현_대조.md>). 75 identity·19 family와 executable vector/fixture 고정, 누락 검사 PASS.

- [x] **T02 — 현재 코드와 검증 상태 대조**
  - 상태·선행: 완료 / T01과 43번의 기능군별 source·공개 경계·남은 보완 및 75개 생성 matrix 대조. 결선 불필요.
  - 할 일: source·build·실기·공개 API·설치 profile을 별도 축으로 대조하고 누락 구현을 식별한다.
  - 완료 기준: 모든 대상에 근거 파일/시험/commit 또는 구체적 미완료 사유가 연결되고 T04~T07·T16의 보완 목록이 있다.
  - 증거: 43번 §기능별 대조·PREP-01~08·T04~T08 구현 기록. 실제 HIL 미실행과 T16 공개 통합은 별도 유지.

- [x] **T03 — 두 보드 공통 실행기 준비**
  - 상태·선행: 완료 / SWD protocol·exact image/UID·role/nonce·배타 lock·실패 journal/STOP·dual-boot helper와 외부 명시적 CLI 준비.
  - 할 일: DUT/peer UID·COM·role·exact source/HEX hash를 결합하고 명령 순서·nonce·timeout·실패 log·재개 경계를 구현한다.
  - 완료 기준: 동일 보드 중복 선택, role 반전, stale packet, 다른 commit, noisy/truncated frame, 중단 후 잘못된 PASS 재사용을 Host 시험에서 거부한다. 실행 중 보드 점유는 배타적이다.
  - 증거: `v04_pair.py`, `v04_campaign.py`, 두 fixture runner와 Host 전체 gate PASS. stale·중복·중단·poison 조건을 거부.

- [x] **T04 — UART·SPI·I2C 시험 프로그램 준비**
  - 상태·선행: 완료 / 온보드 UART·cancel/handover, 외부 UART 135·SPI 1,513·TWI 328개 sync/async·single/double-buffer·flow/error/cancel/NACK/stuck-low/clock-stretch·정상 재시작 image/oracle·gate·CLI 준비. 외부 실행은 T10 이후.
  - 할 일: UARTE 5개, SPIM/SPIS 각 5개, TWIM/TWIS 각 4개의 승인 경로와 역할에 송수신·flow control·DMA·buffer 전환 시험을 연결한다.
  - 완료 기준: 각 대상의 DUT/peer image와 host 판정이 build/unit을 통과하고 시험표와 연결된다. PMIC는 승인된 읽기 전용 경계를 유지한다.
  - 증거: Host 전체 PASS, `C:/r45` pair image 포함 full20 build-only PASS. 온보드 기존 PASS는 41번, 외부는 NOT RUN.

- [x] **T05 — ADC·PWM·타이머·이벤트 시험 프로그램 준비**
  - 상태·선행: 완료 / 내부 VDD·AVDD와 timer/event, 외부 AIN0~3/AIN7·PWM20/21/22 channel slot 0~3·단일/이중 DMA 판정 준비. AIN4~6은 보드 공유 제한으로 contract-only.
  - 할 일: 안전한 ADC 입력·scan/sample 순서·DMA, PWM 채널/sequence의 peer capture, timer/event/DPPI 소유권을 시험한다.
  - 완료 기준: 예상 값·count·기본 timing 허용 범위를 검사하는 image/runner와 Host 시험이 준비된다. 교정 전압·정밀 jitter 보증과 구분한다.
  - 증거: signal fixture 401~404/408, fixture별 48 vector, Host PASS와 M25 Analog/pair target build PASS. 외부 신호는 NOT RUN.

- [x] **T06 — PDM·I2S·QDEC 합성 신호 프로그램 준비**
  - 상태·선행: 완료 / QDEC sampling/oracle·Stream DAP 격리와 PDM SPIS clock 동기 source·I2S 양방향 pattern·QDEC PWM quadrature generator/receiver 준비. 물리 신호 성립은 T12에서 검증.
  - 할 일: PDM20/21, I2S20, QDEC20/21의 시험 신호 생성·수신, clock 역할, frame/sample 순서, quadrature 방향/count를 구현한다.
  - 완료 기준: 기대 패턴을 독립적으로 판정하고 peer 신호 능력·속도 한계를 명시한 image/runner가 build/unit을 통과한다. 미구현 신호 발생은 HOLD다.
  - 증거: fixture 420/430/440, PDM96·I2S96 vector와 Host 판정 PASS, M25 Stream/pair target build PASS. 실기 NOT RUN.

- [x] **T07 — DMA 오류·복구·동시성·장시간 시험 준비**
  - 상태·선행: 완료 / DMA RAM 끝·overflow·정렬 사전 거부, 오류/cancel 뒤 복구, SPIM00+TWIM22와 PWM20+PWM21+SAADC 최소 동시성, bounded 연속 campaign 준비. 실제 soak는 T13.
  - 할 일: cancel/stop/restart, 적용 가능한 overflow/underrun·bus error·System OFF 복구, buffer 반환, 충돌 거부·허용 최대 동시 조합·soak를 구현한다.
  - 완료 기준: 오류 유도 방법·정상 복구 상태·손실 카운터·자원 누수 판정·지속시간이 정의된다. Host negative와 실물 오류 주입을 구분하고 불가능한 조건은 남긴다.
  - 증거: DMA/수명주기/fixture/campaign Host PASS와 full20 target build PASS. 더 넓은 허용 topology와 600/7200초 결과는 T13이며 미실행.

- [x] **T08 — 시험별 안전한 결선표와 스위치 안내 작성**
  - 상태·선행: 완료 / 회로도 connector mapping, fixture 15개, TWI pull-up과 analog/stream 역할·금지 net·스위치 조건 작성. 아직 T10 결선 요청 아님.
  - 할 일: 회로도·pinctrl과 대조해 묶음별 DUT↔peer 핀, GND·전압·pull-up·출력 방향·DAP UART switch·제어 채널을 명시한다.
  - 완료 기준: 전원 차단 후 연결/변경 순서, 출력 충돌 방지, 필요한 부품과 사용자 확인 절차가 있다. 금지된 P2 bank와 PMIC/LED 공유 신호를 무단 사용하지 않는다.
  - 증거: `v04_fixtures.json`, HIL README, fail-closed confirmation template와 Host catalog/조건 검사 PASS. 묶음마다 T10 확인 반복.

- [x] **T09 — Host 검사·시험 펌웨어 빌드·무배선 추가 시험**
  - 상태·선행: 완료 / clean `696defb`와 exact board gitlink에서 두 보드 역할 image와 primitives를 재검증. 외부 실행은 T10 전 금지.
  - 할 일: Host/계약/문서 검사와 필요한 target build·CI를 실행하고 온보드 UART·I2C·복구 등 가능한 추가 기능을 시험한다.
  - 완료 기준: 새 source의 image·runner·증거가 결합되고 무배선 가능 항목의 기대 결과가 통과한다. 외부 경로는 build-only로 명확히 남긴다.
  - 결선·증거: 외부 점퍼 없이 USB·지정 UID만 사용. M12 Host 전체와 `C:/r48` pair 2/2 build PASS. 두 역할에서 ping, TWIM20/21/22 PMIC, TIMER 7개 44 capture, 내부 VDD/AVDD SAADC 400회, PWM20+PWM21+SAADC 동시성까지 합계 904건 PASS. [결과](<./04_검증 기록/evidence/696defb/pair-primitives-696defb.json>)와 동일 경로 `.json.jsonl` journal에 exact image·UID hash·commit을 보존했다. 외부 경로는 `NOT RUN`.

## 5. B단계 — 사용자 결선 뒤 기능 검증 (T10~T15)

- [x] **T10 — 첫 시험 묶음의 결선 확인**
  - 상태·선행: 완료 / 사용자가 Fixture 101 배선·DUT D/peer E·양쪽 `DISABLE_UART` 분리·USB 재연결을 확인.
  - 할 일: 정확한 두 보드 role과 승인 연결표를 안내하고 사용자의 완료 확인 뒤 preflight한다.
  - 완료 기준: 현재 session의 배선표 개정·두 UID·스위치·전압/pull-up 조건이 기록된다. 사진/장치 열거만으로 전기적 연결 전체를 검증했다고 하지 않는다.
  - 증거: [44번 Fixture 101 기록](<./04_검증 기록/44_M24_Fixture_101_UART_실기_검증.md>). 이후 묶음의 결선 변경 때마다 confirmation을 반복한다.

- [x] **T11 — M24 통신 인스턴스 기능 검증**
  - 상태·선행: 완료 / Fixture 101~103 UART 정상 4,860·예상 오류 72·cleanup 6건 PASS. Fixture 201~203 SPI 계획 record 54,505개·cleanup 6건 PASS. Fixture 301 TWI 기능 record 1,986개·cleanup 2건 PASS. 23개 serial personality의 승인된 단독 경로를 실제 두 보드에서 검증했다.
  - 할 일: UART·SPI·I2C 승인 경로를 역할별로 실행하고 실제 데이터·mode·DMA 결과를 비교한다.
  - 완료 기준: T01 표의 각 단독 기능 결과가 exact evidence에 연결되고 나머지 16개 외부 경로를 build로 대체하지 않는다. 실패는 T14로 넘긴다.
  - 결선·증거: [44번 Fixture 101](<./04_검증 기록/44_M24_Fixture_101_UART_실기_검증.md>), [45번 Fixture 102](<./04_검증 기록/45_M24_Fixture_102_UART_실기_검증.md>), [46번 Fixture 103](<./04_검증 기록/46_M24_Fixture_103_UART_실기_검증.md>), [47번 Fixture 201](<./04_검증 기록/47_M24_Fixture_201_SPI_실기_검증.md>), [48번 Fixture 202](<./04_검증 기록/48_M24_Fixture_202_SPI_실기_검증.md>), [49번 Fixture 203](<./04_검증 기록/49_M24_Fixture_203_SPI_실기_검증.md>), [50번 Fixture 301](<./04_검증 기록/50_M24_Fixture_301_TWI_실기_검증.md>) exact evidence 등록. TWI는 외부 저항 없이 target TWIS 내부 pull-up을 사용했다.

### T11→최종 physical campaign 리팩토링 gate

이 gate는 새 제품 마일스톤이나 T 번호가 아니다. T14의 결함 수정·재시험을 리팩토링 문서의
R00~R14와 연결하고, 구조 변경 뒤 같은 결선을 다시 반복하지 않도록 R00~R13을 최종 외부 HIL보다
먼저 완료하는 실행 순서다.

- [x] **R00:** 현재 commit, board/NCS/toolchain, 공개 API·CLI·artifact·저장 형식, 대표 ELF와
  기존 Host/target/HIL을 [51번 characterization 기준선](<./04_검증 기록/51_R00_리팩토링_기준선.md>)으로 고정했다.
- [x] **R01:** SPIM/SPIS/TWIM/TWIS source를 명시적인 Core CMake target에 등록하고 선택/비선택·
  단독·허용 조합의 resolved config, target membership와 link를 검증한다.
- [ ] **R02:** Serial stale completion·timeout·DMA buffer 반환·같은 handle의 교차 호출을 수정하고
  최종 Fixture 101~301 회귀 범위를 기록한다. 중간 PASS 캠페인은 만들지 않는다.
- [ ] **R03:** Analog/Stream의 ISR 진단 snapshot·overflow·stop generation과 lock 대기를 파일 이동
  없이 수정하고 R11 및 최종 T12가 지킬 동작 계약을 고정한다.
- [ ] **R04/R05:** LittleFS File retain/release와 제품 identity 원본을 구조 분할 전에 정리한다.
- [ ] **R06~R07:** `nu54-builder` 순수 모듈과 `EventFabric` 기계적 분할 파일럿을 외부 계약·target
  결과가 유지되는 작은 변경으로 완료한다.
- [ ] **R08~R10:** 자원/route 책임, Arduino SPI facade/backend, Serial orchestration·동시 호출 정책을
  분리하고 최종 M24·동시성 회귀 범위를 누적한다.
- [ ] **R11~R12:** Analog/Stream peripheral별 분할과 BLE/Storage 수명주기 구조화를 완료하고 최종
  M25·BLE·Storage 회귀 범위를 누적한다.
- [ ] **R13:** package tool·정책 생성·Kconfig/CMake·문서/증거 구조화를 완료하고 전체 Host·target·예제·
  package gate로 최종 실기 source를 고정한다.
- [ ] **current-source T11 회귀:** R00~R13 최종 exact source로 영향받는 UART·SPI·TWI 단독 기능을
  재검증하고 나서 T12로 전환한다.
- [ ] **R14:** T16~T18의 사용자용 통합까지 끝난 뒤 current-source T11과 T12~T15 결과를 포함한
  `v0.4.0` RC를 다시 고정하고 T19로 전환한다.

세부 상태와 완료 조건은 [리팩토링 진행 체크리스트](<./01_아두이노 코어 설계/14_리팩토링/05_리팩토링_진행_체크리스트.md>)가
소유한다. R01~R13 뒤 runtime byte가 바뀌면 과거 T11 PASS를 새 source 결과로 복사하지 않는다.
외부 결선 PASS 캠페인은 R13 뒤 최종 source에 한 번 수행한다.

- [ ] **T12 — M25 입력·출력·스트림 기능 검증**
  - 상태·선행: 내부 VDD/event 기본 근거 외 미완료 / T05·T06·T09, R00~R13과 current-source T11 회귀 완료, 해당 T10 확인.
  - 할 일: ADC·PWM·timer/event·PDM·I2S·QDEC의 물리 신호와 예상 sample/frame/count를 비교한다.
  - 완료 기준: 합성 peer 자체의 동작과 코어 기능을 구분해 검증하고 각 instance/mode의 증거가 있다. 신호 생성 실패는 미완료이지 계측 면제가 아니다.
  - 결선·증거: 묶음별 결선 필요, 확인 뒤 자동 실행. 추가 증거 미등록.

- [ ] **T13 — 복구·동시 실행·장시간 안정성 검증**
  - 상태·선행: 미착수 / T07·해당 T11/T12 단독 PASS·해당 T10 확인.
  - 할 일: 허용 topology의 동시 부하, 충돌 negative, 오류 주입·복구, 반복 handover, 약속한 soak를 실행한다.
  - 완료 기준: source·topology·rate·시간·buffer·loss·latency/CPU 관측 방법과 누수/복구 판정이 기록된다. 장시간 시험을 코드 구현만으로 완료 처리하지 않는다.
  - 결선·증거: 대상에 따라 결선/스위치 조작 필요. 추가 증거 미등록; System OFF 격리·재연결은 명시적으로 안내한다.

- [ ] **T14 — 발견된 결함 수정과 재시험**
  - 상태·선행: 진행 중 / Fixture 101 deferred RX 분기, Fixture 201 RXDELAY, Fixture 301 TWIS 지연 buffer 재개는 각각 exact 수정 뒤 전체 재시험 PASS. 새 진단의 R01~R13을 최종 외부 HIL 선행 작업으로 추가했다.
  - 할 일: 실패 재현·수정·regression test를 연결하고 관련 온보드/기존 기능을 재검증한다. M26 TEMP/WDT 등 영향받는 근거도 재판정한다.
  - 완료 기준: release를 막는 미해결 코어 결함이 없고 변경된 image의 필요한 기능 시험이 통과한다. 실패 기록은 보존한다.
  - 결선·증거: 재시험 대상에 따라 필요. Fixture 201 실패·교정·전체 PASS는 [47번 기록](<./04_검증 기록/47_M24_Fixture_201_SPI_실기_검증.md>), Fixture 301의 무효 결선·실패·교정·전체 PASS는 [50번 기록](<./04_검증 기록/50_M24_Fixture_301_TWI_실기_검증.md>)에 등록했다. R00~R14의 진행은 [리팩토링 체크리스트](<./01_아두이노 코어 설계/14_리팩토링/05_리팩토링_진행_체크리스트.md>)에 기록한다.

- [ ] **T15 — 실기 결과와 지원 범위 확정**
  - 상태·선행: 대기 / R00~R13 최종 source의 current-source T11과 T12~T14.
  - 할 일: instance·mode·route·rate·동시 조합별 결과를 matrix/manifest/검증 기록에 반영한다.
  - 완료 기준: 요구된 기능 HIL을 증거로 판정하고 미측정 품질은 범위 밖으로 표시한다. M24/M25 physical gate가 적법하게 갱신되며 unsupported 경로를 숨기지 않는다.
  - 결선·증거: 정리 자체는 불필요. 아직 전체 지원 승격 없음.

## 6. C단계 — 사용자용 패키지와 최종 RC (T16~T21)

- [ ] **T16 — 검증된 후보 API를 사용자용 설치 경로에 통합**
  - 상태·선행: 대기 / T15; 사전 설계·예제 초안은 준비 가능하나 지원 승격은 HIL 이후.
  - 할 일: Kconfig 후보와 설치 profile·공개 header·사용 예제·capability를 통합한다. 일반 사용자가 임의 raw 설정 편집을 하지 않도록 사용 경로를 정리한다.
  - 완료 기준: 실제 설치본에서 기능을 선택·사용하고 기존 singleton identity와 충돌 계약이 유지된다. 변경된 실행 코드/profile은 영향받는 HIL을 다시 통과한다.
  - 결선·증거: 코드·패키지 준비에는 결선 불필요, 영향받는 실기는 해당 결선 필요. 증거 미등록.

- [ ] **T17 — 문서·지원 매트릭스 정리**
  - 상태·선행: 기존 문서 유지 중, 최종 정리는 대기 / T15·T16.
  - 할 일: README·API·예제·pin/ownership·제한·환경·마일스톤·migration/release notes를 실제 범위와 맞춘다.
  - 완료 기준: 상태 칸은 일관된 상태값만 쓰고 제한은 설명으로 분리한다. 생성 원본/문서가 일치하며 과거 검증·공개 자산을 소급 변경하지 않는다.
  - 결선·증거: 불필요. 최종 문서 검사 증거 미등록.

- [ ] **T18 — M27 정식 공개 절차 준비**
  - 상태·선행: 비공개 prepare 도구만 있음, stable 절차 미완료 / T15~T17.
  - 할 일: RC→stable package·검증·공개 경로를 별도 변경으로 준비하고 잘못된 version/commit·누락 evidence·기존 asset 덮어쓰기를 거부하도록 검사한다.
  - 완료 기준: prepare/dry-run과 실제 publication이 구분되고 모든 technical gate·최종 승인 전에는 tag/Release/index 쓰기가 불가능하다. 계약/unit 검사를 통과한다.
  - 결선·증거: 준비에 불필요. T18 완료가 공개 실행 허가는 아니며 증거 미등록.

- [ ] **T19 — RC 소스 고정과 전체 회귀 검사**
  - 상태·선행: frozen RC 없음 / R14와 T14~T18.
  - 할 일: exact clean Core/board/SDK/toolchain과 예제 집합을 고정하고 Host·문서·inventory·필요한 기존 회귀·전체 target build·CI를 실행한다.
  - 완료 기준: 고정 RC의 모든 해당 gate와 artifact provenance가 통과한다. 소스가 바뀌면 영향 분석 후 필요한 gate를 다시 실행한다.
  - 결선·증거: software gate에는 불필요, 관련 실기 회귀는 별도. 증거 미등록.

- [ ] **T20 — RC 패키지 재현성·설치 수명주기 검증**
  - 상태·선행: 과거 비공개 29/29 기록만 있음, 최종 검증 대기 / T19.
  - 할 일: ZIP·SBOM·checksum·license·manifest를 독립 생성 두 번으로 비교하고 격리 설치·전체 예제 build·실제 upload·제거·재설치·버전 전환을 검사한다.
  - 완료 기준: 현재 예제 전체(기존 29개 + 새로 추가한 예제)를 lock/발견 목록과 대조한다. 직접 staging compile을 Boards Manager 전체 lifecycle로 대체하지 않는다.
  - 결선·증거: 설치/compile에는 불필요, upload에는 지정 USB 보드 필요; 기능별 실행은 해당 결선 필요. 최종 증거 미등록.

- [ ] **T21 — 정식 0.4.0 패키지 생성·최종 검사**
  - 상태·선행: 대기 / T19·T20.
  - 할 일: stable metadata와 exact commit으로 비공개 산출물을 만들고 이중 재현, 설치본 예제·실제 upload, RC 대비 runtime payload를 검사한다.
  - 완료 기준: metadata-only 전환의 실행 코드 동등성이 입증되거나, 실행 코드가 다르면 영향받는 build/실기/설치 검증을 재수행한다. 기술 gate 결과와 후보 최종 문서가 일치한다.
  - 결선·증거: package 검사는 불필요, 업로드는 USB, 변경 기능은 해당 결선 필요. 아직 tag·Release·공개 index를 만들지 않음.

## 7. D단계 — 공개와 마무리 (T22~T25)

- [ ] **T22 — 최종 결과 확인과 공개 승인**
  - 상태·선행: 사용자 승인 대기 / T21까지 기술 gate 충족.
  - 할 일: 대상 commit/version·필수 검증·제외한 품질 측정·known limitations·공개할 자산을 사용자에게 제시한다.
  - 완료 기준: 해당 결과에 대한 프로젝트 소유자의 명시적 승인 근거가 기록된다. 42번 범위 조정이나 TODO 작성 요청을 최종 승인으로 취급하지 않는다.
  - 결선·증거: 불필요, 사람의 승인 필요. 승인 근거 미등록.

- [ ] **T23 — v0.4.0 태그·GitHub Release·자산 공개**
  - 상태·선행: 대기 / T21·T22, remote exact commit·기존 tag/asset 상태 확인.
  - 할 일: 승인한 commit에 tag를 만들고 검증된 asset·release notes를 공개한 뒤 stable index에 등록한다.
  - 완료 기준: 공개 commit·URL·크기·hash가 승인한 산출물과 일치하고 기존 공개 자산이 보존된다. 중간 실패는 상태 확인 후 안전하게 재개하며 같은 버전의 다른 bytes로 덮어쓰지 않는다.
  - 결선·증거: 불필요, 외부 공개 작업. 현재 공개 안 됨.

- [ ] **T24 — 공개 URL에서 최종 설치 검증**
  - 상태·선행: 대기 / T23.
  - 할 일: 새 격리 환경에서 실제 공개 index/archive를 받아 설치·build·upload·제거·재설치·전환을 확인한다.
  - 완료 기준: 로컬 staging/cache만으로 성공했다고 하지 않고 공개 다운로드의 version·hash·설치/실행 근거를 남긴다. 실패하면 최종 완료를 보류하고 공개 자산 불변 정책에 맞게 처리한다.
  - 결선·증거: 대표 upload는 USB 필요; 지정 기능 실행은 해당 결선. 공개 URL 검증 증거 미등록.

- [ ] **T25 — 최종 문서·커밋·푸시·CI·작업 폴더 정리**
  - 상태·선행: 최종 정리 대기 / T23·T24 및 미해결 항목 없음.
  - 할 일: 공개 결과·release identity·검증 기록·README·로드맵을 마무리하고 commit/push·최신 CI를 확인한다. 보존할 증거와 재생성 가능한 임시 출력물을 분리한다.
  - 완료 기준: 근거가 영구 보존되고 남은 이슈/프로세스/미추적 변경이 설명되며 재개할 누락 작업이 없다. 정리는 정확히 확인한 작업 경로만 대상으로 한다.
  - 결선·증거: 문서·정리에는 불필요. TODO 보관/삭제는 10절을 따르며 자동으로 함께 삭제하지 않는다.

## 8. 남은 release gate와 TODO 연결

| Readiness gate | 연결 작업 | 현재 판정 |
| --- | --- | --- |
| `m24_fixture_hil` | T04·T07~T11·T13~T15 | 필수 physical HOLD |
| `m25_fixture_hil` | T05~T10·T12~T15 | 필수 physical HOLD |
| `host_regression`, `documentation`, `zephyr_repro_build` | T16~T19, T21의 변경 영향 재검증 | frozen RC pending |
| `package_reproducibility` | T20·T21 | frozen RC pending |
| `boards_manager_lifecycle` | T20·T21; 공개 후 검증은 추가로 T24 | 필수 physical HOLD |
| `project_owner_approval` | T22 | human HOLD |

M23·후보 source/build·기본 onboard·M26 판정·기존 자산 불변 gate의 근거는 기존 ledger에 있다.
이 목록을 만들었다고 gate state를 바꾸지 않는다. 준비 완료와 실기 PASS, RC 통과와 정식 공개,
정식 공개와 공개 URL 검증 완료를 각각 구분한다.

## 9. 매 작업 종료 시 남길 인계 내용

2절 체크포인트를 갱신하고, 실제 결과는 검증 기록에 추가한 뒤 관련 T 항목의 `증거`에 링크한다.
새 컨텍스트에서 직전 명령을 무작정 다시 실행하지 않도록 다음 정보를 남긴다.

- 수행한 T 번호와 완료/부분/실패, 변경 파일과 commit·push 상태.
- 실행 명령, exact source/board/image hash, 결과·log/evidence 경로, 실제 시험과 mock의 구분.
- 중단 사유, 살아 있는 프로세스/세션, 보드 role·마지막 image·COM·스위치·결선 상태.
- 다음에 할 **구체적 한 행동**, 선행조건, 사용자가 해야 할 결선·재연결·승인.
- 재사용 가능한 build/cache의 identity와 재검증 범위. Commit/hash가 다르면 이전 성공을 이어 붙이지 않는다.
- CI run URL·대상 commit·확인 시각·상태. 미완료 run을 완료로 적거나 확인 없이 background 작업을 약속하지 않는다.

## 10. TODO 보관·삭제 조건

현재는 활성 문서이므로 삭제하지 않는다. 기본은 완료 후 보관이며, 사용자가 허용한 정리 범위에서
다음 조건을 모두 충족하면 archive 또는 삭제할 수 있다.

1. T01~T25 전체 완료와 정식 공개 URL 검증이 끝났고, 재개할 작업·미해결 문제·사용자 요청이 없다.
2. 결정·제한·최종 지원 matrix·명령·실제 증거·공개 identity가 영구 문서에 옮겨져 TODO가 유일한 근거가 아니다.
3. 삭제/이동 대상은 **이 TODO 파일**로 특정한다. 검증 기록·readiness 참조·공개 asset·SDK·사용자 파일은 포함하지 않는다.
4. [루트 작업 지침](../AGENTS.md), README, 문서 안내, 로드맵, RC·도구 안내 등 들어오는 링크를
   같은 변경에서 최종 기록 또는 보관 위치로 바꾸고 문서 검사를 통과한다.
5. 정리 결과와 Git 복구 가능 여부를 남기고 commit/push한다. 미완료 체크를 지워 완료처럼 보이게 하지 않는다.

예상 시간은 대화에서의 계획치일 뿐 완료 기준이 아니다. T01~T03 준비 약 4~8시간, 이전에 설명한
시험 프로그램·실행기·결선 안내 준비 묶음 약 16~32시간에는 결선 후 전체 실기와 릴리스까지의
소요 시간이 포함되지 않는다. 구현·신호 발생 가능성·결함에 따라 다시 추정한다.
