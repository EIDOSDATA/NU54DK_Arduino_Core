# Host 재검증과 T12 이후 남은 작업

> 과거 검증 이력입니다. 준비·다음 작업·실행 조건은 기록 당시 기준이며, 현재 상태는 [v0.4.0 TODO](../TODO_v0.4.0.md)를 따릅니다.

현재 문제 상태: Host 실행 환경 차단은 아래 전체 재검증으로 **해결 완료**입니다. 당시 우선 과제였던 공용 PWM 미시작 STOP 결함도 **해결 완료([94번](94_T14_PWM_지연_시작_취소와_무점퍼_검증.md))**입니다. 아래 T12·이후 표는 당시 대조 이력이며 현재 잔여 목록이 아닙니다.

**Exact e6979af6545e2cc9525f54695eee965fc25d683e의 canonical Host 83 그룹은 664 PASS·1 조건부 SKIP로 완료했다. LLVM compiler와 WinLibs sysroot를 유지하고 CMake·Ninja만 기존 NCS bundle에서 선택했다. 보드·보안 정책·제품 코드는 변경하지 않았다.**

기록일: 2026-09-07. 사용자가 “Windows 실행 차단으로 미완료인 전체 Host 검사? 다시 함 해봐. 그리고 나머지 요구사항과 해야 할 일을 나열해.”라고 요청했다. 아래 결과는 Host/mock 검사이며 새 flash·실기가 아니다. 보드의 마지막 결과는 [92번 PDM 연속 전체 검증](92_T12_Fixture_440_PDM_연속_전체_검증.md)의 f02734d다.

## 재실행 결과

| 실행 | 판정 |
| --- | --- |
| 기존 LLVM + WinLibs CMake/Ninja의 전체 재시도 | 83 개 중 67 그룹 실행 뒤 `test_v04_cmake_sources.py`의 7 개 구성에서 Ninja 실행 실패. 기존 R02 등 native는 통과 |
| 위 실행에서 아직 안 돌았던 16 그룹 | 모두 PASS. 새 PDM native 연속 helper 포함. 첫 전체 gate 실패는 그대로 유지 |
| LLVM + WinLibs sysroot + NCS CMake/Ninja의 CMake 단독 검사 | 1 test / 7 개 personality 구성 PASS |
| 같은 새 도구 환경의 canonical 전체 재실행 | **83/83 그룹, 664 PASS·1 조건부 SKIP**, `M12_GATE_PASS=host` |

SKIP 1 개는 `test_m13_profiles.py`의 설치본 Arduino CLI discovery다. `NUCODE_M13_CLI_DISCOVERY=1`과 실제 M13 설치본이 필요한 별도 검사이며 native compiler SKIP는 0이다. 설치 수명주기는 T20/T24에 남는다. 이번 전체 결과를 frozen RC의 readiness gate로 승격하지 않는다.

[첫 전체 원본](evidence/host-retry-e6979af/host-all.log), [미실행 그룹 결과](evidence/host-retry-e6979af/host-remaining.json), [CMake 단독](evidence/host-retry-e6979af/cmake-sdktools.json), [최종 전체 원본](evidence/host-retry-e6979af/host-sdktools.log), [계획·그룹·개수 감사](evidence/host-retry-e6979af/host-sdktools-audit.json), [선택 도구와 SHA-256](evidence/host-retry-e6979af/host-sdktools.json).

첫 실패 시각의 [CodeIntegrity 3077/3033](evidence/host-retry-e6979af/code-integrity.json)는 WinLibs `cmake.exe`가 같은 디렉터리의 `ninja.exe`를 실행할 때 차단됐음을 확인한다. 새 선택은 `C:/ncs/toolchains/dcbdc366a1/opt/bin`의 기존 CMake/Ninja다. 차단된 실행 파일을 복사·수정하거나 정책/예외를 바꾸지 않았다. 이 환경은 child process PATH에만 적용한다. [재현 wrapper](evidence/host-retry-e6979af/software_sdktools.py), [Windows 안내](<../02_빌드 설계/09_Windows_개발환경_설정.md>)에 연결한다.

## 당시 T12 잔여 기능 대조

[42번 범위 합의](42_v0.4.0_코어_기능_검증_범위_합의.md), [시험표](<../01_아두이노 코어 설계/12_v0.4.0_기능_시험_목록.md>), 현재 runner와 실기 기록을 대조했다. 기존 fixture 기본 sweep의 PASS와 전체 family 요구는 다르다. 새 요구를 추가한 목록이 아니라, 현재 증거로 아직 닫을 수 없는 시험표 항목이다. 실행 전에 family별 vector·관측 자원·안전한 결선과 허용 오차를 확정해야 한다.

| 영역 | 확보한 실제 근거 | 남은 일 |
| --- | --- | --- |
| SAADC | 401~408의 AIN0~7 개별 기능·DMA, 내부 VDD/AVDD 반복 | calibration API 완료/복구, 다중 채널 scan 순서·buffer 경계, 적용할 sample/event 경로. 정밀 전압 정확도·선형성·ENOB는 제외 |
| PWM20/21/22 | 12 개 channel slot의 기본 출력·DMA, QDEC 합성 파형 | peer capture로 주기·듀티 ±5%, duty 0/25/50/75/100%, TOP 1000/4000, common/grouped/individual/wave-form·invert·sequence0/1·loop·DPPI start·triggered-step·소유권 충돌 검증 |
| GPIO/GPIOTE | 승인 fixture에서 사용한 일부 핀·event 경로 | 승인 GPIO의 input/output/open-drain·edge/level, GPIOTE20/30 가용 channel의 rising/falling/toggle·task set/clear·누출/충돌 거부 |
| TIMER/EGU/DPPI/PPIB/GRTC | TIMER 44 개 CC capture 및 기본 EGU→DPPI→TIMER 근거 | compare/capture·자동 clear/stop, EGU10/20·DPPIC domain/channel/group, PPIB 양 끝 연결, disable/release·예약 자원 거부, 기존 GRTC endpoint 회귀 |
| I2S20 | 430의 16/48 kHz·8/16/24/32bit·좌/우/stereo·master 교대·32/256 word·1/2 buffer 총 192 개 | 시험표의 1024 word, 100 개 측정 buffer의 연속 교대, TX-only/RX-only 역할별 동작 근거. 기존 192 개는 유한 전송 sweep 완료이며 연속 100 개 결과는 없음 |
| QDEC20/21 | 420의 1/100 cycle·2 ms·정/역·debounce 설정·48 개와 시작 전 취소 6 개 | 실행 중 방향 전환·read-clear/restart, 대각 전이 검출·경계, 시험표의 1000 cycle·10 ms·반복 조건. 오류 주입/복구는 T13과 연계 |
| PDM20/21 | 440 기본 192·밀도 32, 연속 96·밀도 16 전체 PASS | 현재 440 기본·연속 sweep 추가 미실행은 없음. 강제 overrun/underrun·복구·동시성·soak는 T13에서 별도 검증 |

앞선 “ADC 정량 검증” 표현은 **calibration API와 채널 순서 등 코어 기능 검증**으로 바로잡는다. 외부 교정 전압원·오실로스코프·마이크/코덱/엔코더 호환성·정밀 jitter/음질은 42번에 따라 필수 준비물이나 보증 범위가 아니다. GPIO port 이름이 모든 pad의 구동 허가를 뜻하지 않으며 공유 ADC 핀의 기존 오픈드레인/입력 바이어스 제한은 유지한다.

## 당시 후속 작업 순서

| 순서 / 단계 | 해야 할 일 |
| --- | --- |
| T14 공용 PWM | **해결 완료([94번](94_T14_PWM_지연_시작_취소와_무점퍼_검증.md))** — `play(start_via_task=true)` 후 실제 START 없이 `stop()`할 때 timeout하던 결함을 `080d771`에서 수정하고 Host·두 보드 실기로 재검증. 420 HIL 우회와 구분 |
| T12 | 위 잔여 기능의 실행기·독립 판정·target build 준비 후 필요한 묶음별 실기 |
| T13 | DMA 경계·16-byte guard 기준·메모리/정렬 사전 거부, cancel/stop/restart·timeout 시 lease·강제 오류/복구, handover/복구 100 회, 동일 block 방향 충돌 86 개·허용 동시 조합, 단독 600 초·동시 7200 초 soak. loss/reset/guard 손상 0·count/hash·자원 반환·관측 방법 기록 |
| T14/T15 | 이후 발견한 결함 수정·영향 회귀, 최종 source의 instance/mode/route/rate/동시 조합 지원 matrix·실기 근거 확정. 공용 DMA 자원 변경 이후 필요한 T11 회귀 포함 |
| T16~T18 | 검증된 후보 API를 설치 profile·header·예제에 통합, 최종 문서/지원 범위 정리, RC→stable prepare/dry-run·공개 절차 구현·검사 |
| R14·T19 | RC source/board/SDK/toolchain 고정, 전체 Host·계약·문서·Inventory·target/예제 build·CI 및 영향 실기 회귀 |
| T20~T21 | package 두 번 생성해 byte 재현성, ZIP/SBOM/checksum/license/manifest, 격리 설치·전체 예제·upload·제거·재설치·버전 전환, stable 후보와 RC runtime 동등성 |
| T22~T24 | 기술 gate 완료 뒤 소유자 공개 승인, 승인 commit의 tag/Release/index 공개, 실제 공개 URL로 설치·build·upload·재설치 재검증 |
| T25 | 최종 문서·커밋·푸시·CI 확인, 재생성 가능한 임시 파일 정리와 증거 보존 |

T13의 7200 초는 **해당 동시 topology 한 실행의 2 시간**이며 전체 남은 작업의 예상 시간이 아니다. 현재 PDM 결선을 다른 시험의 결선으로 간주하지 않는다. 이번에는 새 실기나 다음 단계 구현을 실행하지 않았다.

Readiness 필수 16 개 중 미해결 8 개는 M24/M25 전체 physical, frozen RC Host/문서/전체 build/package, Boards Manager lifecycle, 소유자 승인이다. 이번 개발 source의 Host PASS로 frozen RC gate를 완료 처리하지 않는다.

## 증거와 문서 검증

[Manifest](evidence/host-retry-e6979af/raw-files.json)에 실행별 원본 byte gzip·SHA-256와 UTF-8/LF 사본을 보존한다. `cmake-sdktools-invocation.log`의 첫 wrapper 문자열 준비 오류는 test 실행 전 오류이며, 실제 CMake 결과는 `cmake-sdktools.json`과 재실행 invocation log에 구분했다. 준비 script의 존재나 Host mock의 upload 성공 문자열은 실제 보드 실행 증거가 아니다.

활성 문서 8 개·Windows 안내·이 기록을 갱신했다. Markdown 202 개·원본 22 개 gzip/hash·JSON/JSONL/Python 문법·Git stage 56 개 byte 대조를 통과했다. 92번 이하 역사 기록·보드·SDK·제품 code·공개 자산은 유지한다. 실행 중 프로세스는 없다.
