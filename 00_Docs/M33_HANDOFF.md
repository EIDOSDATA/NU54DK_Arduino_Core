# M33 개발 순서와 새 채팅 인계

2026-10-03에 확정한 M33 개발, 후속 Host 이식, RC 검증과 v0.6.0 공개 순서를 정리한다.
현재 작업은 실제 저장소의 `Dev-0.6.0-M33`에서 **M33-W01 원장·계약을 구현 중**이다.
Host 작업은 M33 기능 개발과 병렬 진행하지 않고 **M33-W06 완료 직후 HOST-W04부터** 시작한다.
이 문서 작성은 기능 구현이나 실물 검증 완료가 아니다.

## 현재 상태와 작업 위치

| 항목 | 확인한 상태 |
| --- | --- |
| 실제 저장소 | `C:\Users\eidos\GitHub\NU54DK_Arduino_Core` |
| 작업 브랜치 | `Dev-0.6.0-M33`, 원격 `origin/Dev-0.6.0-M33` 추적 |
| M33 분기 기준 | M32 전체 결과를 squash 통합한 `main`의 `314c04f2b3e342df5aafa7ba8d950643e9124fe6` |
| Host 순서 확정 커밋 | `ce689fd2c14b7fd8f04cbdeafafb6b0fe7c72d9c`; 이 인계 문서는 그 이후 변경이며 재개 시 실제 HEAD를 확인 |
| M32 | W01~W12 12/12 완료; 전체 파일 내용은 main에 반영됨 |
| M33 | W01~W08 0/8; W01 원장·계약 후보 구현과 local 검사를 진행 중 |
| Host | W01~W03 3/8 완료; W04~W08은 M33-W06 완료 전까지 착수 대기 |
| 현재 공개 제품과 소스 버전 | Windows용 stable v0.5.0, source version 0.5.0; v0.6.0은 아직 미공개 |
| SDK | NCS v3.4.0 유지; lock·toolchain·SDK checkout을 임의 변경하지 않음 |
| Board submodule | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |
| 다음 실제 행동 | W01 후보를 clean exact source에서 재검사하고 증거·TODO·readiness를 연결한 뒤 W02 착수 |

이 채팅의 projectless 폴더를 저장소로 착각하지 않는다. 현재 브랜치는 이미 생성·푸시되어 있으므로
main에서 새 M33 브랜치를 다시 만들거나 기존 변경을 reset하지 않는다. M33의 8개 작업과 Host의
8개 작업은 독립 분모이며, 아래 실행 순서의 행 수를 완료 분모로 사용하지 않는다.

## M32 원본 이력 보관

사용자 요청으로 `Dev-0.6.0-M32`의 로컬·원격 브랜치를 삭제했다. 구현·예제·문서·검증 자료의
최종 파일 내용은 main에 남아 있고 M33은 그 기준에서 분기했다. Squash 전 원본 커밋 이력은
다음 Git bundle에 별도로 보관했다.

- 이 PC의 위치: `C:\Users\eidos\Documents\Codex\2026-10-02\di-x20\outputs\M32-history-0c2af5bd.bundle`
- 원본 tip: `0c2af5bdd561c7d271dd21041e2294aba0ea6005`
- 크기: 149,421,813 byte
- SHA-256: `12e3f96ae50d30ac721bf43fdc217b7819ff7b388e046d622326d013ff99bdb1`
- `git bundle verify`로 전체 이력 포함과 유효성을 확인했다.

Bundle은 저장소에 커밋하거나 GitHub에 업로드한 파일이 아니다. 다른 PC에서 원본 M32 커밋을
복원할 필요가 있을 때는 이 파일도 별도로 전달해야 한다. 평상시 M33 개발을 위해 과거 브랜치를
복원하거나 main에 다시 merge하지 않는다. 원격 `Release-0.5.0`의 `4790e3fa…` 기준선과 과거
공개 tag·Release·asset은 그대로 보존한다. [295번 기록](<04_검증 기록/295_M32_문서_전수_정비와_main_Squash_통합.md>)은
당시 통합 결과이며, 이후 브랜치 삭제 결정은 이 인계 문서의 상태를 따른다.

## 시작 전에 읽을 문서

1. [AGENTS.md](../AGENTS.md)와 그 문서가 요구하는 완료 TODO·계약을 읽는다.
2. [HANDOFF](HANDOFF.md), [v0.6.0 계획](TODO_v0.6.0.md), [M33 TODO](TODO_M33.md)를 읽는다.
3. [전체 Bluetooth 기능과 예제 계약](<01_아두이노 코어 설계/19_NCS_Bluetooth_전체_기능과_예제_실행_계약.md>)과
   [다중 Host 계약](<02_빌드 설계/10_v0.5.0_다중_Host_지원_착수_계약.md>)을 확인한다.
4. [NCS 3.4.1 변경과 개발 영향](<00_사전 리서치/03_NCS_3.4.1_변경과_개발_영향.md>)에서 현재
   NCS 3.4.0의 알려진 문제·조건부 위험·재검증 항목을 읽는다. SDK 결함과 실제 재현된 원인을 구분한다.

## 전체 실행 순서

### M33 기능 개발

| 순서 | 작업 | 수행할 내용과 완료 근거 |
| --- | --- | --- |
| 1 | 착수 기준 정리 | 현행 문서의 M32 브랜치 보존 표현은 이번 인계 정비에서 수정했다. 재개 시 경로·브랜치·HEAD·미커밋 변경·submodule을 확인한다. 실기 직전에는 보드 mapping·역할·image·결선을 확인한다. |
| 2 | M33-W01 전체 목록 확정 | 고정 NCS의 sample/test metadata와 Arduino 예제를 전수 대조한다. 누락·중복·미배정 owner·이유 없는 제외를 없애고 역할·test ID·정량 합격 기준과 release-readiness를 확정한다. |
| 3 | M33-W02 GATT와 beacon | 기존 7개 profile을 회귀하고 OTS/OTC·ANS·CTS·HTS·CSC/RSCS·CGMS·BMS를 보강한다. iBeacon·Eddystone·BTHome 송수신과 payload·보안·오류·수명주기를 2~3보드로 검증한다. 기존 API 기반 목적별 Fabric 예제도 연결한다. |
| 4 | M33-W03 외부 제품 연동 | Fast Pair 입력 장치·locator tag, ANCS·AMS의 실사용 구현·설정·예제·자동 검사를 완성한다. 인증정보 누락을 거부하고 pairing/bond/reconnect를 검사한다. 실제 외부 제품 검증 절차와 미검증 결과는 사용자 후속으로 분리한다. |
| 5 | M33-W04 DTM과 HCI | 독립 test profile/template와 적용 가능한 transport를 제공한다. RADIO·clock·UART 소유 충돌, 잘못된 command·timeout·stop/restart를 검사한다. DTM은 두 보드의 실제 수신 수와 역할 교대를 검증하며 UART에 debug 출력을 섞지 않는다. |
| 6 | M33-W05 예제와 설치 경로 | 역할별 공개 sketch·설정·README·연결 안내·오류 처리·제한을 완성한다. Windows clean 설치본의 전체 예제 발견·compile·기대 실패 조합을 검사하고 build-only와 실제 runtime을 구분한다. |
| 7 | M33-W06 통합 검증 | M28~M32와 신규 기능의 자원 예산·보안·재접속·취소·peer loss·cleanup을 회귀한다. 3보드 기능·부하·유한 soak, 원장·문서 검사와 peer별 지원표를 마감한다. Bluetooth qualification 적용성은 조사하되 인증 취득으로 표시하지 않는다. |

W01~W06의 Host regression은 기존 Windows 개발환경과 공통 단위 검사를 뜻한다. 이 단계에서
Ubuntu/macOS 이식을 시작하거나 해당 OS 완료를 선행조건으로 요구하지 않는다. M33 내부의 독립
작업을 나누는 것과 Host 트랙을 병행하는 것은 다르며, Host 착수 금지 시점은 W06 완료 전이다.

### W06 완료 후 Host 이식

| 순서 | 작업 | 수행할 내용과 완료 근거 |
| --- | --- | --- |
| 8 | HOST-W04 설치 기반 | OS별 nRF Util·sdk-manager·NCS·Zephyr·toolchain·Arduino CLI의 공식 자산·버전·hash·revision을 고정한다. 설치/검증기, Linux 장치·udev·실행 권한, macOS native 자산·Gatekeeper와 Windows 회귀를 처리한다. |
| 9 | HOST-W05 경로와 cache | OS별 cache·lock·사용자 경로·atomic replace를 이식한다. 공백·한글·긴 경로·대소문자·symlink·stale/partial 파일·권한 오류를 검증한다. |
| 10 | HOST-W06 build와 package | 세 OS의 CI/build 구성을 마련하고 native 설치·전체 역할 예제 compile·package metadata·산출물 차이를 검증한다. CI 구성 개발과 현재 사용자가 생략한 원격 CI 상태 조회를 구분한다. |
| 11 | HOST-W07 도구 준비 | CMSIS-DAP/pyOCD upload·serial·ELF debug·재연결·설치 수명주기의 실행기와 로그 수집·체크리스트를 준비한다. Windows 회귀와 실제 Ubuntu/macOS 시험 준비를 구분한다. |

### RC 검증과 정식 공개

| 순서 | 작업 | 수행할 내용과 완료 근거 |
| --- | --- | --- |
| 12 | M33-W07 RC1 준비 | source·board·SDK·toolchain·profile·catalog·version·hash를 고정한다. 시험용 package를 독립 두 번 생성해 재현성과 포함 목록을 검사하고 migration·known limits·미검증 행을 release notes에 기록한다. 이 단계만으로 W07 완료가 아니다. |
| 13 | HOST-W07 실제 OS 검증 | 해당 RC를 지원 대상 Windows·Ubuntu·macOS에 설치한다. 전체 예제 cold/warm compile, 대표 Blink·Serial·BLE upload/runtime, serial·debug·재연결·upgrade/reinstall/uninstall을 검증한다. GUI 확인과 CLI 검사는 분리한다. |
| 14 | HOST-W08 및 M33-W07 마감 | 문제를 수정하면 새 exact 후보로 영향 범위를 재검증한다. 실제 OS별 증거·지원표·사용 안내·문제 해결을 정리해 Host를 마감하고, 기능·package·Host 필수 결과를 결합해 M33-W07을 완료한다. |
| 15 | M33-W08 공개와 인계 | exact source·package plan·자산 hash에 대한 별도 소유자 승인을 받은 뒤 tag·Release·asset·stable index를 게시한다. 공개 URL hash·격리 설치·예제·대표 upload/runtime·수명주기를 확인하고 문서·지원 버전·후속 인계를 마감한다. |

각 작업의 세부 체크와 test case는 [M33 TODO](TODO_M33.md)와 [다중 Host 계약](<02_빌드 설계/10_v0.5.0_다중_Host_지원_착수_계약.md>)이
소유한다. 완료 시 구현·검사·실기 결과·미해결 항목을 해당 TODO와 검증 기록에 연결한다.
M33 다음은 [v0.7.0 SDK-W01~W06](TODO_v0.7.0.md)의 NCS 3.4.1 전체 전환이며 이번 개발에 섞지 않는다.

### 현재 M33-W01 구현 결과

- 고정 NCS sample 190개와 test variant 474개를 owner·test ID에 연결했고 M33 범위는 sample 108개,
  variant 318개다.
- 설치 Arduino Sketch 전체 187개를 전수 등록했다. BLE·radio 164개와 core·peripheral 23개이며,
  파일 내용·Sketch 이름 완전 중복은 모두 0개다.
- 모든 예제는 28개 primary Recipe 중 하나에 속한다. 사용자 첫 화면은 12개 사용 시나리오와 대표
  Sketch 24개만 보여 주고, 전체 187개 Reference와 M33 신규 22개 기능군은 그대로 보존한다.
- `m33-release-readiness.json`, `m33_contract.py`, `test_m33_readiness_contract.py`와 전체 원장·릴리스
  계약을 추가했다. NCS 3.4.0 유지, 외부 peer 후속과 Ubuntu/macOS 최종 gate, 공개 승인 분리를 검사한다.
- 아직 W01 완료가 아니다. clean exact source의 local 검사와 증거 연결 뒤에만 1/8로 올린다.

## OS 장비와 검증 경계

- 현재 목표는 Windows 10/11 x64, Ubuntu 24.04 이상 AMD64, macOS 26 이상 Apple Silicon native다.
  다른 Linux 배포판·Linux ARM64·Intel Mac·Rosetta를 자동으로 지원 범위에 추가하지 않는다.
  공개 시 지원표에 올리는 OS별 행은 실제 증거가 필요하다.
- 사용자는 Linux를 SSH로 사용할 가능성을 말했다. 접속 정보·권한·보드 USB 연결은 아직 확정하지
  않았다. Mac도 SSH 또는 RC package·검증 스크립트를 실행한 사용자 결과로 검증할 수 있으나,
  현재 장비·접속 가능 여부는 미확정이다. 실행 시 해당 Host의 권한과 장치 접근을 확인한다.
- 실제 upload·serial·debug 검증에는 해당 OS가 보드에 접근할 수 있어야 한다. CI build나
  Windows의 성공을 Mac/Linux USB PASS로 대체하지 않는다. RC1에서 Blink 한 번 성공한 것으로
  전체 지원을 마감하지 않으며, 기존 보드 간 무선 시험 전체를 OS마다 무조건 반복하지도 않는다.
- Apple/Google BLE peer와 외장 audio 장치의 실제 운용은 사용자 후속 `NOT_RUN`이며 개발·릴리스
  비차단이다. 실사용 구현·예제·설정·가능한 자동 검사는 필수다. Ubuntu/macOS 개발 Host의 최종
  실물 지원 gate와 이 외부 제품 상호운용 정책을 혼동하지 않는다.

## 재개 시 지킬 운영 규칙

- 최신 사용자 요청대로 **원격 CI 결과를 조회하거나 완료를 기다리지 않는다.** 미확인을 PASS로
  기록하지 않는다. 이 지시는 로컬 문서·단위·build·필요 HIL 검사의 생략이나 workflow 비활성화가 아니다.
- 코드 주석은 한국어 Doxygen, BSD/Allman, 들여쓰기·탭 폭 4칸, 한 줄 제어문도 중괄호를 사용한다.
- 공개 Arduino 예제는 `.ino`에서 공개 `NUCODE_*` API와 사용자 데이터 흐름을 보여 준다.
  Zephyr 직접 호출·개발 마일스톤 이름·시험 전용 oracle을 공개 예제에 노출하지 않는다.
- 과거 3보드 연결 기록을 현재 상태로 가정하지 않는다. 실기 전에 비식별 probe mapping·image·
  결선·유한 횟수·timeout을 고정하고 lock·watchdog·STOP·clock/핀 반환 규칙을 유지한다.
- M32 당시 ERASEALL 승인은 역사 맥락으로 보존한다. 새로운 M33 대상의 포괄적 flash 삭제 권한으로
  확대하지 않으며 자동 mass erase·unlock·recover·임의 배선/전원 변경을 하지 않는다.
- 오류는 진단 근거 확보 → 원인에 맞는 수정 → 동일 조건 재검증 순서로 해결한다. 필요한 경우
  승인된 디버거 경로에서 레지스터를 읽고 고정 SDK source·공식 문서·데이터시트와 대조한다.
- 과거 PASS/FAIL/HOLD/NOT_RUN·공개 자산·기존 사용자 변경을 보존한다. 실제 장비 접근이나 공개 등
  새 권한이 필요한 지점은 구체적으로 보고하고 확인받는다. 이 인계는 공개 승인이나 main 재통합·
  추가 squash·브랜치 삭제 지시가 아니다.

## 새 채팅에 붙여 넣을 내용

아래 지시문은 새 채팅에서 M33 개발을 시작하기 위한 복사용 본문이다. 이번 문서 정비에서는
M33 구현·보드 시험·Host 이식을 실행하지 않았다.

```text
실제 저장소에서 M33 개발을 이어가자.

작업 경로: C:\Users\eidos\GitHub\NU54DK_Arduino_Core
작업 브랜치: Dev-0.6.0-M33

먼저 AGENTS.md와 00_Docs/M33_HANDOFF.md를 전체 읽고, 거기서 지정한 TODO·계약·SDK 문제 기록을 확인해.
실제 경로·브랜치·HEAD·미커밋 변경·board submodule을 확인하고 사용자 변경을 보존해.
M33 브랜치는 이미 생성·푸시되어 있으니 새로 만들거나 main에서 다시 분기하지 마.

현재 M32는 12/12 완료되어 main에 반영됐고, M32 브랜치는 삭제됐어.
원본 이력은 인계 문서에 적힌 로컬 Git bundle로 보관돼 있어.
M33은 0/8 미착수, HOST는 W01~W03만 3/8 완료 상태야.

M33-W01부터 실제 구현과 검증을 시작해.
M33-W01~W06을 먼저 완료하고, HOST 작업은 절대로 그 과정과 병렬로 진행하지 마.
W06 완료 후 HOST-W04~W06 및 W07 도구 준비 → M33-W07 RC1 준비 → HOST-W07 실제 OS 검증·W08 마감
→ M33-W07 완료 → M33-W08 공개 승인·게시·공개 설치 검증 순서로 진행해.
각 단계의 구현·검사·증거·남은 문제를 TODO와 인계 문서에 갱신해.

NCS 3.4.0을 유지해. SDK 3.4.1 전체 전환은 다음 v0.7.0 작업이야.
기록된 SDK 위험을 관련 시험에 반영하되, 근거 없이 현재 실패 원인으로 단정하지 마.
원격 CI 결과를 조회하거나 기다리지 마. 로컬 검사와 필요한 build/HIL은 별도로 수행하고 미실행을 PASS로 쓰지 마.

보드·Linux SSH·Mac 접근 가능 여부는 현재 상태를 확인해. 접속 정보나 결선 상태를 추정하지 마.
실제 Ubuntu/macOS 지원 검증은 RC 단계에서 수행하고, 외부 Apple/Google peer·외장 장치 실기는 사용자 후속으로 구분해.
자동 mass erase·unlock·recover나 임의 SDK 변경을 하지 말고, 필요한 새 권한과 최종 공개 승인은 별도로 요청해.
한국어 Doxygen, BSD/Allman, 4칸 들여쓰기, 제어문 중괄호 필수 규칙을 지켜.

먼저 확인한 현재 상태와 M33-W01에서 할 첫 작업을 짧게 설명한 뒤 착수해.
```
