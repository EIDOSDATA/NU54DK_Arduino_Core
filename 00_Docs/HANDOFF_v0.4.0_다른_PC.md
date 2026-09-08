# v0.4.0 다른 PC 재개 인계

2026-09-08 현재: R00~R13과 승인 route의 T11 단독 회귀는 완료했다. T12 공통 결선의 GPIO/GPIOTE 2,502개·PWM 675+288개·I2S 432개는 source별 PASS다. QDEC 동작 중 수동 read/clear의 누산 누락은 HOLD이며 추가 진단 반복은 종료했다. T13은 32개 단독·8개 동시 조합과 C→S→U 두 결선 변경 계획까지 확정했고 실기는 0회다. 다음 개발 작업은 QDEC 비의존 T13 runner·preflight·복구/전환 판정 준비다. T12 전체·T13 이후·RC·공개는 미완료다. [문서 감사·요구별 증거 대조](<04_검증 기록/102_개발_문서_전수_검토와_마일스톤_체크포인트.md>), [실행 TODO](<TODO_v0.4.0.md>)를 따른다.

현재 기능 실행(100·101번): GPIO/GPIOTE2502(4e48252), steady PWM675(3334b17), 추가 PWM288(0db0689), I2S432(b5c86a4)는 PASS다. QDEC 기능240은 누산 누락으로 HOLD다. 마지막 ce48471 선점 대비60회에서 일반 read9/30·IRQ 보호 read7/30이399/400으로 실패했다. GPIO/SAMPLE은 모두400, 보호 구간 최대5µs, 제어 오류0·cleanup63·양쪽 postflight PASS다. 3a0e976 SAMPLE IRQ20·REPORT IRQ20은 모두400으로 일치했으나 기능240이나 안정성 PASS로 확대하지 않는다. 사용자 지시대로 진단 반복을 종료하고 유력 원인·미검증 전기 조건·보완·재개 조건을101번에 남겼다. 제품 core·SDK는 미수정이다. T13은32단독/8동시·C→S→U 두 결선 변경의 계획만 확정했고 QDEC 단독2개와C07은 선행 HOLD다. T12전체·T13실기·지원 범위 확정·RC·공개는 미완료다.

[T13 후속 GPIO 결선](../tests/hil/nu54dk/T13_PLAN.md)은 C→S→U 두 단계다.

종료한 실행 범위는 [100번](<04_검증 기록/100_T12_공통_기능_묶음과_T13_조합_확정.md>)의 T12 현재 공통 결선 묶음과 T13 조합·추가 결선 확정까지다. 사용자는 현재 결선 유지와 HW 미조작을 확인했다. 고정 세션은 2026-09-08 07:00 KST까지이며 기존 30분 확인서와 구별한다. 아래 이전 실기 결과를 새 기능 코드의 PASS로 재사용하지 않는다.

현재 재검사: exact d8d1e13에서 P1.10을 포함한 17개 신호가 양방향 각 3회, 총 102 net-round PASS다. LOW 자동 해제 2개·양쪽 lease 만료 1개도 PASS이며 종료 후 양쪽 17개 PIN_CNF=0, PWM/DPPI off를 확인했다. 첫 8c1cfe2의 P1.10 실패 원본은 보존하고 원인은 미확정으로 유지한다. 결선 검사 통과이며 GPIO API·T12 전체·T13 이후·RC 완료는 아니다.

현행 시간 기준: [98번](<04_검증 기록/98_T13_단독_안정성_3분_기준_조정.md>)의 사용자 지시로 T13 단독 안정성은 각 인스턴스 180초다. 후속 99번 사용자 동의로 동시는 각 조합 900초, 전체 대표 고부하 한 조합은 3600초로 대체한다. 과거 인계의 600초 계획과 구분하며 최신 재개 상태는 활성 TODO를 따른다.

새 PC 인수 후속: [96번](<04_검증 기록/96_새_PC_인수와_T12_PWM_peer_capture_준비.md>)의 인수 기록 이후 [97번](<04_검증 기록/97_T12_PWM_peer_capture_첫_240조건_검증.md>)에서 첫 PWM capture 240조건을 통과했다. 활성 TODO가 현재 상태를 소유한다. 이 문서 아래의 보드/경로는 이전 PC 인계 당시 기록이다.

2026-09-07. 사용자가 현재 자동 작업을 마친 뒤 다른 컴퓨터에서 이어가도록 요청했다.
이 문서는 이번 인계 시점의 요약이다. 이후 진행 상태는 [활성 TODO](TODO_v0.4.0.md)가 소유한다.
**R00~R13과 source별 T11 단독 회귀는 완료했다. 다음은 T12의 남은 외부 신호 시험 준비다.**
T12 전체·T13 이후·R14·RC·정식 공개는 완료하지 않았다.

## 이전 PC 인계 당시 저장소와 검증 기준

아래 f42bda5 이전 상태는 역사적 인계다. 새 PC의 최신 완료 source는 1ad4193이며 원격 15/15 SUCCESS를 102번에 보존했다. 마지막 보드 image는 ce48471이고 probe/HIL 실행은 종료했다.

| 항목 | 인계 기준 |
| --- | --- |
| 원격 | <https://github.com/EIDOSDATA/NU54DK_Arduino_Core> |
| 작업 branch | `main`; 새 PC에서 실제 checkout과 origin을 확인 |
| 원격 전체 CI 검증 source | `828166109968b2ceb40fc2d9c054255558d995d5` |
| 마지막 실기 image source | `874658a16db18b283ab7f1b2835111aaf34b42fd` — 두 보드 내부 무점퍼 HIL |
| PWM 수정·전체 로컬 target·설치본 기준 | `080d771ae48e83b4621f3160afed67395ead32cd` |
| 인계 문서 commit 찾기 | `git log -1 --format=fuller -- 00_Docs/HANDOFF_v0.4.0_다른_PC.md` |
| board gitlink | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |
| NCS / Zephyr | `99553055607b2e9885fbc80ccd11fa9da81c2df0` / `bf801e4e3d19e1ffa76164346480cb7734dd2800` |
| Windows Nordic Toolchain | `dcbdc366a1` |

인계 commit은 위 CI source 이후 문서와 증거만 추가한다. 최신 문서 commit의 자동 CI 상태와
8281661의 완료 결과를 구분한다. 후속 코드가 있으면 Git 차이로 영향을 판정하고 예전 결과를 복사하지 않는다.

## 이번에 끝낸 일

- PWM `start_via_task=true` 준비 후 실제 START 없이 stop할 때의 timeout을 수정했다.
  미시작 DMA 준비는 강제 START 없이 취소하며, 실제 시작 흔적·경합에서는 STOP·lease 보호를 유지한다.
  활성 START DPPI 구독은 연결 소유자가 먼저 해제하는 계약이다.
- 080d771 두 보드에서 1,944명령·4,320회 configure/play/stop과 미시작 DMA 취소 1,968회를 통과했다.
- 874658a 두 보드에서 내부 ADC·TIMER·EGU/DPPI/PPIB·시간 함수와 PWM 회귀를 904명령씩,
  합계 1,808명령 통과했다. 원본·최초 실패·판정 교정·종료 register는 [95번](<04_검증 기록/95_T12_내부_ADC_TIMER_이벤트_무점퍼_검증.md>)에 있다.
- 8281661의 [Software Gates](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/34092876776)
  7개와 [Reproducible Builds](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/34092876773)
  8개 job이 모두 SUCCESS다. Host는 85그룹·680 PASS·2 조건부 SKIP다.
  설치 CLI/NCS 환경이 필요한 두 SKIP와 별도 설치본 발견 11개·exact NCS 검사 결과를 구분한다.
- 로컬 전체 target 61/61과 확장 HIL 1/1, 비공개 설치 예제 29/29 및 package 이중 생성 비교를 완료했다.
  원격에서도 Zephyr 네 그룹 61개와 M16 두 role, M14 QEMU·M17 및 Arduino 네 그룹을 확인했다.
  설치 예제의 첫 26 PASS·3 FAIL와 재시도 원본은 지우지 않았다. RC/package lifecycle 전체 완료는 아니다.
- CI의 Windows short path/import·MinGW weak 링크 문제와 격리 package CLI의 CP1252 실패를 교정했다.
  CI Host에 LLD를 선택하고 CLI 진입점의 stdout/stderr를 UTF-8로 지정했다.
  제품 시간 함수·SDK·board source는 바꾸지 않았다.

전체 source·결과·원본 SHA는 [94번](<04_검증 기록/94_T14_PWM_지연_시작_취소와_무점퍼_검증.md>)을 따른다.
최신 로컬 3bc8fad Host는 R02 SPIM 실행에서 Windows `WinError 4551`로 중단됐다.
이를 로컬 PASS로 바꾸지 않았고, 수정 source의 전체 실행은 원격 8281661에서 통과했다.
Windows 보안 정책을 해제하거나 실행 파일을 변형해 차단을 피하지 않았다.

## 이전 PC 인계 당시 보드 상태

이전 PC에서 마지막으로 확인한 상태이며 새 PC의 현재 연결 확인을 대신하지 않는다.

| 항목 | 마지막 관측 |
| --- | --- |
| 보드 간 결선 | 사용자 보고로 모두 해제; 이전 440 등 fixture 확인은 현재 유효하지 않음 |
| 보드 수·제어 | NU54DK 두 개, 각각 USB/SWD; 실기 SWD 10 MHz |
| image | 양쪽 874658a nojumper, UART/console off, 명령 대기 |
| 완료 상태 | 보드별 ready count 904, 실패 latch 0 |
| 주변장치·핀 | ADC/PWM20/21/22 off, 네 DPPI CHEN=0, P1.14 PIN_CNF=2 입력 |
| A probe UID SHA-256 | `32f71533ff6ba27fd38ed32a17bf6d80a90d4f4980221051ed5c5a2e7fdb63a9` |
| B probe UID SHA-256 | `4574ee31f25fe05f154395ea4d8c6aa0583b04a4f7a0ea97fe3d13b05eea8ca0` |

새 PC에서는 probe를 열거하고 UID hash·role·image를 다시 대조한다. COM 번호나 USB 순서는
옛 PC와 같다고 가정하지 않는다. 원시 UID·인증 정보는 공개 기록에 넣지 않는다.
외부 실기 전에는 GPIO 번호로 안내하고 두 USB 분리→결선 변경→재연결 및 DAP UART 분리·SWD
상태의 현재 사용자 확인을 받아야 한다. 스위치 위치를 이름만으로 추정하지 않는다.
승인된 실기 제어는 exact UID·SWD 10 MHz·배타 lock·sector flash·`auto_unlock=false`·controlled
reset/start를 유지한다. 자동 mass erase/recover나 다른 보드로의 임의 전환은 하지 않는다.

## 새 Windows PC에서 먼저 할 일

1. 실제 저장소 위치를 찾거나 위 원격을 recursive clone한다. 기존 checkout은 미커밋 변경을 먼저
   확인하고 보존한다. 깨끗한 `main`에서 fetch와 fast-forward pull, submodule 초기화를 수행한다.
   `git status`, `git log -1`, `git submodule status --recursive`로 확인한다. 강제 reset/clean은 하지 않는다.
2. `AGENTS.md`, [TODO 전체](TODO_v0.4.0.md), 이 문서, 94·95번을 읽는다.
   리팩토링 변경 시 [안내](<01_아두이노 코어 설계/14_리팩토링/README.md>)와
   [진행 체크리스트](<01_아두이노 코어 설계/14_리팩토링/05_리팩토링_진행_체크리스트.md>)도 읽는다.
   현재 시험 조건은 [42번 범위 합의](<04_검증 기록/42_v0.4.0_코어_기능_검증_범위_합의.md>),
   [기능 시험 목록](<01_아두이노 코어 설계/12_v0.4.0_기능_시험_목록.md>)과
   [HIL 안내](../tests/hil/nu54dk/README.md)에서 대조한다.
3. [Windows 개발환경](<02_빌드 설계/09_Windows_개발환경_설정.md>)에 따라 기존 설치를 확인하고
   없는 도구만 준비한다. Host Python 3.12.10·Arduino CLI 1.5.1·고정 NCS/Toolchain과
   `tools/ci/requirements-host.txt`의 hash 고정 의존성을 사용한다. pin 원본은
   [CI lock](../tools/ci/ncs-3.4.0.lock.json)과 [prerequisite pins](../tools/nu54-prerequisites/pins.json)다.
4. Windows Host의 GCC/LLD를 실제로 확인한다. 원격 성공 조합은 GCC 15.2/LLD 20.1.8이며
   로컬 GCC 16.1 또는 LLVM 22.1.8 결과도 94번에 있다. GNU 15의 기본 GNU ld는 BLE weak
   fallback 링크에 실패했다. Host 전용 `NUCODE_HOST_CC_FLAGS`·`NUCODE_HOST_CXX_FLAGS`의
   JSON 배열 `["-fuse-ld=lld"]` 경로를 사용하며 target toolchain 설정에 적용하지 않는다.
   CMake/Ninja는 고정 NCS bundle을 우선한다. 차단이 발생하면 원본 오류를 기록한다.
5. 실제 새 환경에서 canonical contract·docs·inventory·package·example discovery와 Host 검사를
   실행한다. 시작 명령은 `python -B tools/ci/run_m12_gate.py <gate>`이며 gate는
   `contract`, `docs`, `inventory`, `package`, `examples`, `host`다. 결과는 새 PC의 source·환경과
   함께 새 증거로 기록한다. 이전 PC의 PASS로 새 도구 설치가 검증됐다고 하지 않는다.
6. 보드가 연결되지 않았어도 다음 PWM capture HIL의 구현·Host·target build 준비를 진행할 수 있다.
   실제 flash/외부 시험은 새 PC의 장치·결선 조건을 확인한 다음 수행한다.

주석은 **한국어 Doxygen**, 코드는 **BSD/Allman·4칸**, 한 줄 제어문에도 중괄호 필수다.
제품 범위는 Windows용 v0.4.0이며 Linux CI를 제품 Linux 지원으로 표시하지 않는다.

## 현재 다음 작업 순서

1. 이번 C17 묶음은 GPIO/GPIOTE2502·PWM675+288·I2S432를 source별로 완료했다.
   QDEC 기능240은 마지막 선점 대비에서도 누락이 남아 HOLD로 보존하고 사용자 지시대로
   진단 반복을 종료했다. [100번](<04_검증 기록/100_T12_공통_기능_묶음과_T13_조합_확정.md>)과
   [101번](<04_검증 기록/101_T12_QDEC_누산_누락_원인_분리.md>)의 증거·보완·최종 검사와 1ad4193 push/CI 15/15까지 완료했다.
2. 다음 개발은 [T13 계획](../tests/hil/nu54dk/T13_PLAN.md)의 전용
   runner·preflight·복구/handover 판정을 구현한다. 현재 계획은32단독/8동시, 단독180초·
   일반 동시900초·대표 한 조합3600초다. C→S→U 두 결선 변경과 각 현재 확인이 필요하며
   이번 고정 C 세션을 재사용하지 않는다. QDEC20/21 단독·C07은 기능 선행 HOLD다.
3. TIMER는95번 두 보드7,040회 PASS 범위로 기능 완료 정리했다. 추가 TIMER 반복을 요구하지 않는다. QDEC는 문제 기록 후 진단 종료이며 다른 T13 작업을 막지 않는다. 외부 ADC의 초기100회와 실제 각 조건1회 차이는 [103번](<04_검증 기록/103_TIMER_기능_완료와_T13_진행_경계.md>)에 별도 보존한다. 공유 AIN4~6 기능은 이미78·79·82번에서 통과했으므로 미검증으로 돌리지 않는다.
   PDM 기본·연속 PASS(91·92번)를 불필요하게 반복하지 않는다. 공유 자원 경로가 바뀌면
   영향을 받는 최종-source T11 회귀를 후속 통합에서 계획한다. T13 실기 완료는 아직0회다.
4. T15 지원 범위 확정→T16~T18 사용자 통합→R14/T19 RC 고정→T20~T21 package/lifecycle→
   T22 명시적 공개 승인→T23~T25 공개·공개 URL 검증·마무리 순서를 유지한다.
   Readiness 필수 16개 중 미해결 8개는 이번 인계에서 승격하지 않았다.

## Git으로 옮겨지는 자료와 로컬 보존물

코드·시험기·문서·정규화 로그·JSON/JSONL·원본 byte의 `.raw.gz`·SHA manifest는 원격 `main`에 있다.
새 PC에서 전체 작업 폴더나 이전 대화 attachment를 옮겨야만 구현을 계속할 수 있는 구조는 아니다.
각 evidence의 `workspace_original`, build root 등 절대 경로는 이전 PC의 출처 정보다.
새 PC에서 같은 경로가 존재한다고 가정하지 않는다. 저장소 안 사본과 archive를 기준으로 읽는다.

ELF/HEX·전체 compile DB와 큰 설치/build cache는 이전 PC에만 남아 있다. 다음 시험의 image는
새 PC에서 exact source와 고정 SDK로 새로 빌드하고 source·board·설정·artifact hash를 기록한다.
이전 바이너리와의 byte 대조가 꼭 필요할 때만 아래 디렉터리를 별도로 복사하고 기존 manifest와 대조한다.
SDK 설치의 `ready.json`이나 절대경로 cache를 새 PC에 복사해 검증 완료로 간주하지 않는다.

| 이전 PC 경로 | 보존 목적 |
| --- | --- |
| `C:/u4p` | 080d771 전체 target artifact |
| `C:/nj26`, `C:/nj27` | 내부 HIL 최초 두 source의 실패 진단 |
| `C:/nj28` | 874658a 최종 내부 HIL ELF/HEX·build 입력 |
| `C:/u4y` | 29개 설치 예제·재시도·설치 provenance |
| `C:/u4ci15`, `C:/u4ci15n` | Windows compiler 비교·CI 실패 재현 도구 |
| `C:/Users/eidos/Documents/Codex/2026-09-06/new-chat/work/t14-pwm-deferred` | 원본 로그·private package·초안 ZIP·검증 보조 실행 기록 |

자동 승인 검토가 `C:/u4d2`, `C:/u4d3`, `C:/u4x`의 재귀 삭제를 실행 전에 차단했다.
반환 이유는 `blocked by policy`였으며 구체 조건은 제공되지 않았다. 세 폴더는 남겨 두었고,
관련 28개 진단 파일의 hash 검증 ZIP과 차단 기록을 94번에 보존했다. 우회 삭제를 시도하지 않는다.
저장소 안에서 더 이상 쓰지 않는 것으로 확정된 삭제 대상은 없었다.

현재 로컬 HIL·build 프로세스는 종료했다. 문서 commit 이후 자동으로 생성된 GitHub Actions는
해당 push SHA로 조회한다. 이 인계는 무인 background 작업이나 공개 실행 예약을 생성하지 않는다.
