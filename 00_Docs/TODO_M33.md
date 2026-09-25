# M33 실행 TODO — NCS Bluetooth 예제 완성과 후속 릴리스

| 항목 | 내용 |
| --- | --- |
| 대상 제품선 | M31 `v0.5.0` 이후 Bluetooth 확장 제품선; 버전 미정 |
| 현재 구현 상태 | **계획 — 0/8 작업 묶음** |
| 선행 결과 | M28~M32 적용 기능·profile·예제·제한·시험 원장 |
| 병행 Host 계획 | HOST-W08; 현재 W01~W03 완료 3/8, W04 이후 사용자 보류, 재개 후 별도 분모 유지 |
| 기준 | NCS `v3.4.0`, [고정 CI lock](../tools/ci/ncs-3.4.0.lock.json) |
| 현재 공개·개발 | 설치·지원 `v0.4.1`, 개발 source `0.4.1-dev`; 이 계획으로 버전을 올리지 않음 |
| 최종 갱신일 | 2026-09-21 |

M33은 기능을 Arduino 사용자 예제·설치 package·검증 가능한 지원표로 완성한다. 핵심 목표는
고정 NCS에서 nRF54L15에 적용 가능한 Bluetooth 예제를 NU54DK Arduino 환경에서 사용할 수 있게 하는 것이다.
전체 기능·upstream 대응·제공 방식은
[NCS Bluetooth 전체 기능과 예제 실행 계약](<01_아두이노 코어 설계/19_NCS_Bluetooth_전체_기능과_예제_실행_계약.md>),
기능 구현은 [M31 TODO](TODO_M31.md)·[M32 TODO](TODO_M32.md), 제품선 진행은
[제품 로드맵](<01_아두이노 코어 설계/02_구현_로드맵.md>)이 소유한다. 현재 M31은 W01~W06 완료 6/8이며 M32·M33은 미착수다.
아래 항목은 모두 구현·검증 예정이며 완료 실적이 아니다. Host 병행 계획은 별도 재개 지시 이후에 적용한다.

2026-09-21 사용자 결정에 따라 `v0.5.0`은 M31 완료 후 Windows 우선으로 릴리스한다.
그 버전의 재현 package·Windows 설치 수명주기·RC·공개 승인/게시·공개 설치 gate는
[M31-W08](TODO_M31.md)이 소유한다. M33-W07~W08은 추가 기능과 다중 Host를 포함하는
후속 릴리스의 gate로 유지한다. M33 0/8이나 HOST 3/8을 완료로 올리거나 M31 출시에 합산하지 않는다.

## 1. Catalog와 지원 원칙

1. 고정 NCS의 nRF54L15 공식 지원 Bluetooth sample은 전부 원장에 넣고 Arduino 대응 경로를 배정한다.
   일반 Zephyr Host sample·서비스·profile도 전수 조사해 NU54DK candidate와 미적용 사유를 남긴다.
2. `wrapper`, `direct`, `profile`, `template`, `excluded`의 전달 방식을 사용한다. 모든 기능을 새로운
   고수준 class로 만들 필요는 없지만 사용 가능한 경로·설정·예제·실행 절차가 있어야 한다.
3. 고정 SDK에 없는 기능, 다른 SoC 전용 sample, NU54DK에서 연결할 수 없는 hardware, 외부 credential/peer가
   필요한 sample을 정확히 분류한다. 기능/예제 누락을 `excluded`로 자동 처리하지 않는다.
4. 세 NU54DK만으로 가능한 기능은 보드 간 payload·state·counter·hash로 자동 검증한다. 정밀 RF/audio
   품질·calibration은 제품 완료 조건에 추가하지 않는다.
5. Apple/Google·외부 제품 기능과 microphone/speaker/codec/외장 장치는 사용 가능한 구현·예제·설정/연결
   안내·자동 가능한 검사까지 필수다. 실제 운용·제품 상호운용·외장 실물 검증은 사용자 후속이며
   개발·릴리스 필수 gate에서 제외한다. 해당 실제 결과는 `NOT_RUN`·상호운용 미검증으로 유지한다.
   Ubuntu/macOS 실물 Host는 해당 OS를 포함하는 후속 릴리스 때 사용자가 검증하며 해당 OS 지원 gate는 유지한다.
6. 문서에 등록한 예제, source candidate, build PASS, 실제 기능 PASS, 외부 ecosystem 인증은 독립 상태다.
   M33 공개 시 지원한다고 표시할 필수 행은 증거가 필요하며, 미검증 행은 지원 선언에서 구분한다.

위 책임·차단 정책은 [전체 계약의 최종 사용자 결정](<01_아두이노 코어 설계/19_NCS_Bluetooth_전체_기능과_예제_실행_계약.md>)을
단일 원본으로 사용한다. 외부 장치/peer를 기다리며 구현을 중단하지 않으며, 후속 실물 검증을 미룬 것을
구현 면제나 실제 상호운용 PASS로 해석하지 않는다. Windows 회귀는 가능한 자동 개발 범위에 포함한다.

## 2. 작업 배치

| 작업 | 구현·검증 범위 | 현재 상태 |
| --- | --- | --- |
| M33-W01 | 전체 sample inventory 마감·profile/example catalog 범위 | 미착수 |
| M33-W02 | 표준 GATT profile와 beacon·목적별 예제 보강 | 미착수 |
| M33-W03 | Fast Pair·ANCS/AMS 실제 기능·예제·자동 검사, 사용자 후속 상호운용 인계 | 미착수 |
| M33-W04 | DTM/HCI와 특수 진단 application template | 미착수 |
| M33-W05 | 역할별 예제·설치/compile·사용자 문서 수명주기 | 미착수 |
| M33-W06 | 교차 기능 자원·회귀·peer별 검증/지원 분류 | 미착수 |
| M33-W07 | 후속 Host 확대·HOST-W08·재현 package·release candidate | 미착수 |
| M33-W08 | 후속 버전 exact 결과 공개 승인·publish·공개 설치·인계 | 미착수 |

W02~W04는 M31/M32의 해당 API/profile가 준비되는 순서대로 병행한다. W05에서 한 catalog로
합치고 W06~W08에서 실제 배포 입력을 고정한다. HOST-W08은 M33의 8개 작업에 합산하지 않는다.

## 3. 구현 TODO

### M33-W01 — 전체 예제 원장 마감

- [ ] M31-W01의 `variants/nu54dk/ncs-v3.4.0-bluetooth-sample-parity.json`을 고정 SDK의 sample/test
  metadata와 전수 대조한다. 새 탐색 결과·누락·중복을 검출하는 CI gate를 완성한다.
- [ ] 각 upstream 경로에 nRF54L15 target 허용·integration·build-only 여부, 필요한 역할/보드/부품/peer,
  Arduino 경로·profile·owner·예정 test ID를 등록한다.
- [ ] M28~M32에서 구현한 기능과 예제의 일대다 대응을 연결하고 실제 역할별 `.ino`·설정·README를 추적한다.
- [ ] Source candidate/native build/Arduino build/HIL/외부 peer 결과를 각각 기록하고 미배정 owner와
  이유 없는 제외 0을 마감 조건으로 검사한다.
- [ ] SIG adopted service/profile 전체와 고정 SDK sample 전체의 차이를 공개한다. 고정 SDK 적용 sample은
  모두 추적하고, source가 없는 추가 service도 계획 여부·제공 방식·근거를 catalog에 남긴다.
- [ ] `variants/nu54dk/m33-release-readiness.json`과 release 계약을 구현해 필수 행·지원 제외·미검증
  template·실험 기능의 공개 정책 및 test case 분모를 고정한다.
- [ ] Master schema의 `verification_owner`·`verification_stage`·`development_blocker`·`release_blocker`를
  case별로 적용한다. Apple/Google·외장 I/O 실제 case는 `user`/`user_follow_up`/`false`/`false`,
  Ubuntu/macOS 실물은 해당 OS 후속 지원에 대해 `user`/`final_release`/`false`/`true`로 구분한다.
  이 gate는 M31 Windows 릴리스에 적용하지 않는다. 구현·예제·자동 검사 case는
  필수로 남기며 사용자 후속 실제 case와 합치지 않는다. 이 정책은 현재 원장에 구현 완료된 것이 아니다.
- [ ] `M33-INV-01`의 inventory drift·누락·중복·잘못된 지원 승격 negative를 구현한다.
  사용자 후속 실물 `NOT_RUN`의 재차단/PASS 승격, 필수 구현을 후속으로 숨김, 최종 Host gate 면제도 거부한다.

### M33-W02 — 표준 GATT와 beacon 예제

- [ ] 기존 BAS·DIS·HID keyboard/mouse/consumer-control·HRS·ESS 7개 catalog를 회귀하고 M30의 7/7
  완료를 보존한다. 신규 profile를 과거 완료 수에 합산하지 않는다.
- [ ] OTS server·OTC client/OTP의 object 생성·목록·선택·read/write·CoC 전송·권한·중단/재시작 예제를 만든다.
- [ ] ANS(알림), CTS(시각), HTS(체온), CSC/RSCS(운동), CGMS(혈당), BMS(본드 관리)의 고정 SDK
  source·client/server 역할·필드·보안·upstream 예제를 판정하고 Arduino profile/direct 예제를 제공한다.
- [ ] 동일 GATT 기반으로 구현하더라도 characteristic 단위·단위 변환·길이·notify/indicate·authorization·
  malformed 데이터·bond 삭제 권한·동시 두 link 상태 격리를 기능별로 검증한다.
- [ ] iBeacon·Eddystone·BTHome의 advertiser/observer 예제, payload encoder/decoder·filter·변조/길이 경계와
  profile 요구사항을 제공한다. 실제 센서가 없으면 명시적 synthetic 측정값으로 protocol을 검증한다.
- [ ] Generic GATT/NUS·peripheral/central·동시 role·periodic/PAwR·보안·DFU 등 기존 사용자 예제를
  새 catalog에 연결하고 동일 기능을 중복 새 구현으로 계산하지 않는다.
- [ ] [ARF-04A](<01_아두이노 코어 설계/18_문서_전면검토와_개선_마일스톤.md>)의 기존 API 기반
  목적별 Fabric 예제를 연결한다. Buffered NUS·PWM pool 구현은 해당 ARF owner로 유지하고,
  ARF-01 role-budget은 M32-W04로 이관한 resource preset을 사용한다.
- [ ] `M33-PROFILE-01`, `M33-BEACON-01`의 하위 case를 profile·역할별로 만들고 두/세 보드 HIL을 수행한다.

### M33-W03 — 외부 ecosystem와 companion

- [ ] Fast Pair input device·locator tag의 고정 nRF54L15 sample 대응 template·profile·pairing/advertising·
  account key 저장·삭제·provisioning 경로를 제공한다.
- [ ] Google model ID/credential·계정·partner 요구를 저장소 밖 입력으로 분리하고 placeholder/누락 입력을
  fail-closed로 거부한다. 인증/승인 절차를 build 또는 sample 실행으로 완료 처리하지 않는다.
- [ ] ANCS client·AMS client의 discovery·subscription·attribute/control·bond/reconnect 예제를 제공한다.
- [ ] iOS/macOS·Android·Windows/Linux BLE peer의 pairing/bond/HID UX를 실제 기능별 적용 표에 배정한다.
- [ ] 실제 Apple/Google 제품에 사용할 기능·예제·설정을 완성하고 자동 가능한 Host parser/semantic·
  target/Arduino build·scripted peer 시험을 수행한다. 실제 운용·제품 상호운용은 사용자 후속이며
  `NOT_RUN`으로 기록하고 M33 개발·릴리스 필수 gate에서 제외한다. 빈 success stub으로 완료하지 않는다.
- [ ] 사용자용 실제 peer 검증 절차에 모델/OS/앱/adapter·기능 지원성·설정·수동 단계·timeout·보안
  결과 양식을 제공한다. 사용자 후속 결과가 도착하기 전에도 필수 구현·자동 검사를 완료하면 W03을 마감할 수 있다.
- [ ] `M33-ECOSYSTEM-01`에 Fast Pair/ANCS/AMS/OS UX의 독립 하위 case와 unavailable/unsupported 이유를 남긴다.

### M33-W04 — DTM/HCI와 특수 application

- [ ] Direct Test Mode의 고정 nRF54L15 sample을 Arduino에서 선택·build할 수 있는 독립 test profile 또는
  application template로 제공한다. HCI 방식 등 upstream transport별 실제 NU54DK route를 판정한다.
- [ ] 고정 NCS/Zephyr의 HCI controller/Host transport sample을 inventory하고 UART/외부 Host 등 적용
  가능한 경로를 예제로 제공한다. nRF54L15 native USB가 필요한 경로는 비적용 사유를 명시한다.
- [ ] 정상 BLE stack과 DTM/raw controller의 RADIO·clock·UART·buffer 동시 소유를 차단한다.
- [ ] Command parser·지원 command·길이/range 오류·timeout·stop/restart·transport 누락 negative를 구현한다.
- [ ] UART DTM protocol 전용 경로에 console/debug log를 섞지 않는다. 보드 2대를 TX/RX로 실행하고
  유한 시험 종료의 packet reporting event에서 수신 수를 검증한 뒤 역할을 교대한다. 채널·PHY·payload·
  반복 수·timeout·수신 수의 정량 기준을 고정한다. 세 번째 보드는 별도 격리하고 임의 송신하지 않는다.
- [ ] 보드만으로 관측 가능한 command/response·실제 수신 counter를 검증하고 외부 tester·sniffer가 필요한 RF 측정은
  `NOT RUN`/범위 밖으로 남긴다. DTM build를 RF 인증·감도·출력 측정 PASS로 표시하지 않는다.
- [ ] `M33-DIAG-01`의 template build/negative/장비별 runtime case를 제공한다.

### M33-W05 — 예제 품질과 설치 경로

- [ ] 공개 Arduino 예제 단일 원본을 `libraries/*/examples`에 두고 역할별 sketch와 필요한 companion
  runner/config를 연결한다. 독립 application template는 별도 위치·빌드 방식을 catalog에 명시한다.
- [ ] 모든 예제에 목표 기능, upstream path/revision, 필요한 보드 수와 역할, Tools profile/Kconfig,
  예상 출력·종료/재시작·보안·제한·negative·증거 ID를 작성한다.
- [ ] 마이크·스피커·코덱·외장 장치용 adapter/설정·실사용 예제·연결 안내와 자동 가능한 검사를
  owner 결과에서 대조한다. 실물 운용·검증은 사용자 후속 `NOT_RUN`·릴리스 비차단으로 표시하고
  합성 PCM/data PASS를 실제 외장 I/O 검증으로 확대하지 않는다.
- [ ] 초급 예제는 유한하고 작은 기능을 보여 주며 고급 예제는 callback/loop·소유권·buffer·동시성·
  timeout·실험적 선택의 책임을 설명한다. 한국어 Doxygen·Allman·탭 4칸·제어문 괄호 규칙을 적용한다.
- [ ] 실제 package에 포함된 예제 발견 목록과 catalog를 자동 대조하고 한 역할 누락·필요 profile 누락·
  템플릿 placeholder·금지된 Host 절대 경로를 검출한다.
- [ ] Clean 설치본의 전체 예제 compile, 기대 실패 profile 조합, upload 대상 선택·serial 관측 절차를 검증한다.
- [ ] Runtime 예제에는 build-only 예제와 다른 실행 판정을 남기고 물리 보드가 없는 CI는 compile 결과로 기록한다.
- [ ] `M33-EXAMPLE-01`에 catalog 분모·발견 분모·compile 분모·각 role runtime 분모를 따로 기록한다.

### M33-W06 — 자원·회귀·상호운용

- [ ] M28~M32의 connection/adv/sync/ISO/Mesh/CoC/EATT/CS buffer·RAM/RRAM·thread·radio budget을
  profile별로 합치고 허용·거부 조합을 검증한다.
- [ ] GAP/GATT/security/DFU와 신규 profile의 stale handle·cross-link·key/identity 오귀속·cleanup·
  bounded reconnect·cancel·peer loss를 회귀한다.
- [ ] 전체 Host regression·관련 unit/negative·target build·JSON/schema/drift·문서 gate를 실행한다.
- [ ] 세 보드로 가능한 기능 HIL과 대표 부하·soak를 고정한 분모·timeout으로 수행한다. 정밀 RF/audio
  성능 수치는 완료 요구에 추가하지 않는다.
- [ ] Android/iOS/Windows/Linux와 Nordic/타 vendor matrix를 기능별로 만들고 `PASS/FAIL/NOT RUN`,
  peer 자체 미지원과 Core 미지원을 구분한다. Windows 기본 GATT의 과거 PASS를 전체 OS UX에 복사하지 않는다.
- [ ] Apple/Google·외부 제품의 실제 interop 행은 사용자 후속으로 인계한다. 구현·자동 가능한 semantic/
  scripted peer 검사와 실제 제품 interop의 분모를 나누고 후속 실기 부재로 W06/릴리스를 차단하지 않는다.
- [ ] `M33-REG-01`, `M33-RESOURCE-01`, `M33-INTEROP-01`에 exact image·profile·peer 결과를 연결한다.
- [ ] Bluetooth qualification의 Host/controller/Mesh 적용성·component 근거·제품별 추가 절차를 조사해
  별도 문서에 적는다. Component 자격과 제품 자격·예제 사용 가능성을 서로 구분한다.

### M33-W07 — 후속 Host 확대·HOST-W08와 release candidate

M31 Windows 릴리스에서 완료할 package·설치 gate의 절차와 증거를 재사용하되, 후속 기능·Host·
exact source가 바뀐 범위는 새 package와 해당 Host에서 검증한다. M31 공개를 위해 이 작업의
전체 catalog나 세 Host 완료를 기다리지 않는다.

- [ ] [다중 Host 계약](<02_빌드 설계/10_v0.5.0_다중_Host_지원_착수_계약.md>)에 따라 Windows 10/11 x64,
  Ubuntu 24.04 이상 AMD64, macOS 26 이상 Apple Silicon의 지원 version matrix를 release 시점에 고정한다.
- [ ] HOST-W04~HOST-W07의 prerequisite/path/cache/package·자동 검사 결과와 최종 사용자 USB·serial·
  debug 검증 절차를 exact 입력과 대조한다. 중간 단계에서 Ubuntu/macOS PC 연결을 요구하지 않는다.
- [ ] HOST-W08의 clean 설치·전체 예제 compile·대표 실제 upload/runtime·upgrade/reinstall/uninstall을
  실제 각 Host에서 마감한다. Ubuntu/macOS는 해당 OS를 포함하는 후속 릴리스 단계에서 사용자가 실행하며 설치·USB upload·
  serial·debug·수명주기 증거를 인계받는다. 그때까지 해당 행은 `NOT_RUN`이고 해당 OS 정식 지원 공개
  gate는 미완료다. Windows의 가능한 자동 회귀와 나머지 개발·RC 준비는 계속한다.
- [ ] Release candidate의 source/board/SDK/toolchain·profile/catalog·version·hash를 고정하고 package를
  독립 두 번 생성해 재현성과 runtime payload·예제 포함 목록을 검증한다.
- [ ] API/profile migration·known limitation·experimental opt-in·미검증 template·외부 ecosystem·Host
  상태를 release notes와 readiness에 동일하게 기록한다.
- [ ] `M33-PACKAGE-01`, `M33-INSTALL-01`을 HOST-W08 증거와 연결하고 공개할 필수 행의 미완료를 차단한다.
- [ ] 기능 구현 완료, 지원 범위 결정 완료, 세 Host 완료, RC 준비 완료를 각각 보고한다. Apple/Google·
  외장 장치의 사용자 후속 실물 행은 지원 제한으로 남기되 개발·릴리스 blocker로 사용하지 않는다.
  최종 사용자 장비 검증 gate는 Ubuntu/macOS이며 공개 승인·제품 인증은 별도 절차다.

### M33-W08 — 후속 버전 공개·최종 인계

- [ ] 적용 필수 기능·예제·Host·package·회귀의 exact 증거와 남은 외부 행을 전수 검토한다.
- [ ] 공개 대상 지원 범위·source·package plan과 자산 hash에 대한 프로젝트 소유자의 승인을 확보한다.
  이 TODO 작성과 과거 버전의 공개 승인을 후속 버전 tag/Release/index 게시 승인으로 사용하지 않는다.
- [ ] 승인된 exact plan으로 tag·Release·asset·stable index를 게시하고 기존 공개 자산을 보존한다.
- [ ] 공개 URL의 hash·격리 설치·예제·대표 upload/runtime·수명주기를 검증한다.
- [ ] `M33-RELEASE-01`에 승인·공개·공개 설치를 독립 결과로 남긴다. Exact push commit의 CI 확인은
  최신 사용자의 명시적 생략 지시를 우선하며, 현재 인계에서는 CI/CD 실행 요청·조회·대기를 하지 않는다.
- [ ] README·API/profile·example catalog·release-readiness·검증 기록·HANDOFF와 제품 지원 버전을 맞춘다.
- [ ] M34~M45와 별도 ARF에 남은 security/storage/radio/network/Matter·사용자 후속 외부 ecosystem·후속 Host 확대
  요구를 구체적 다음 행동·장비·owner·상태와 함께 인계한다.

## 4. 예정 test ID·장비·완료 입력

다음은 예약 ID이며 W01에서 하위 case·정량 계약을 확정한다. 모든 보드 시험에는 유한 반복 수·
timeout·packet/object 분모·허용 loss/latency·복구 한계·즉시 중단 오류를 둔다.

| 예정 ID | 구성 | 완료·negative 기준 |
| --- | --- | --- |
| M33-INV-01 | Host | 고정 upstream 전수 매핑·누락/중복/미배정 owner 0, 허위 지원 승격 거부 |
| M33-PROFILE-01 | 2~3보드 | Profile/role별 payload·보안·lifecycle, malformed·권한 오류·cross-link 거부 |
| M33-BEACON-01 | 2보드 | Protocol별 실제 수신/decode, length/version·변조 거부 |
| M33-ECOSYSTEM-01 | 자동 검사 Host/적용 보드; 실제 Apple/Google/OS peer는 사용자 후속 | 실사용 구현·예제·설정·자동 검사 필수, credential 누락·bond/access 거부. 실제 제품 시험은 비차단 `NOT_RUN` |
| M33-DIAG-01 | DTM 2보드, 기타 transport별 외부 Host | DTM 양방향 TX/RX·실제 수신 수·유한 STOP·UART 격리·ownership, tester 없는 정밀 RF 측정 NOT RUN/범위 밖 |
| M33-EXAMPLE-01 | 각 build Host, runtime은 해당 role 보드 | 설치 catalog/role 전수 compile·실행 절차, 누락 profile·잘못된 조합 거부 |
| M33-REG-01 / M33-RESOURCE-01 | Host + 최대 3보드 | 이전 기능·명시 조합·자원 회수·오귀속/손상/누수·유한 부하 |
| M33-INTEROP-01 | 자동 가능한 peer 검사 + 실제 외부 BLE 제품은 사용자 후속 | 기능·모델별 상태·peer 미지원 구분; 실제 Apple/Google·외부 제품 검증은 릴리스 비차단, 자동 결과로 대체 금지 |
| M33-PACKAGE-01 / M33-INSTALL-01 | 세 Host와 USB 보드; Ubuntu/macOS 실물은 최종 사용자 검증 | 재현 package·전체 예제·설치/USB upload/serial/debug·수명주기, hash/arch/profile·권한 오류; 최종 OS gate 유지 |
| M33-RELEASE-01 | 승인된 exact plan·공개 URL | 승인·게시·다운로드 byte·공개 설치, 미완료 필수 gate 게시 차단; CI 확인은 최신 사용자 생략 지시 우선 |

## 5. 완료와 보존 계약

- M33의 구현 완료 분모는 W01~W08 **8개**다. 예제 수·role 수·test case 수·HOST-W08은 별도 분모로
  기록하며 원장 검증으로 숫자를 집계한다. 계획 문서 완성을 W 완료로 계산하지 않는다.
- 공개 지원이라고 표시할 모든 적용 기능/예제/Host 행에는 주장 범위에 맞는 증거가 있어야 한다.
  Apple/Google·외장 장치의 구현·예제·자동 검사 완료와 사용자 후속 실물 `NOT_RUN`을 함께 공개하며,
  이 후속 실기만을 이유로 M33 개발·릴리스 gate를 차단하지 않는다. 기본 GATT 또는 보드 peer PASS로
  전체 ecosystem 상호운용·실물 I/O를 대신하지 않는다. Ubuntu/macOS 실물은 사용자 최종 지원 gate다.
- NU54DK 미지원·SDK 미지원·experimental·external-add-on·build-only를 이유와 함께 분류하면 누락
  판정은 닫을 수 있다. 그 행의 runtime 결과가 자동 PASS로 바뀌지는 않는다.
- M28/M29/M30 완료와 M30-POWER-01의 4지점 × 3회·12/12 PASS, 실제 source
  `ae5186f7790a748641fb04128c16156519ee1017`, recovery failure 0, invalid image boot 0을 보존한다.
  NFC adapter의 RF `NOT RUN`·지원 제외와 실제 유선 USB/DAPLink VCOM OOB 경계도 유지한다.
- Probe UID 원문을 채팅·문서·로그에 노출하거나 저장하지 않는다. SHA-256 identity·serial·role·
  firmware revision을 시험 직전 대조한다. 여러 probe 임의 선택·자동 mass erase/recover·전체 flash
  초기화·임의 GPIO·전원 차단을 하지 않는다.
- 실패/HOLD/NOT RUN 원본과 과거 tag/Release/asset은 보존한다. 후속 성공을 같은 원본에 덮어쓰지 않는다.
- M33 계획은 후속 버전 공개 승인이 아니다. 승인 가능한 exact 결과가 준비되면 공개 범위를 확정하고,
  세 Host 정식 지원에 필요한 실제 Host 행이 비어 있으면 해당 공개 gate를 미완료로 유지한다.
