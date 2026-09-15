# M33 실행 TODO — NCS Bluetooth 예제 완성과 v0.5.0 릴리스

| 항목 | 내용 |
| --- | --- |
| 대상 제품선 | `v0.5.0` Bluetooth LE Complete |
| 현재 구현 상태 | **계획 — 0/8 작업 묶음** |
| 선행 결과 | M28~M32 적용 기능·profile·예제·제한·시험 원장 |
| 병행 Host | HOST-W08; HOST-W01~HOST-W08의 별도 완료 분모 유지 |
| 기준 | NCS `v3.4.0`, [고정 CI lock](../tools/ci/ncs-3.4.0.lock.json) |
| 현재 공개·개발 | 설치·지원 `v0.4.1`, 개발 source `0.4.1-dev`; 이 계획으로 버전을 올리지 않음 |
| 최종 갱신일 | 2026-09-16 |

M33은 기능을 Arduino 사용자 예제·설치 package·검증 가능한 지원표로 완성한다. 핵심 목표는
고정 NCS에서 nRF54L15에 적용 가능한 Bluetooth 예제를 NU54DK Arduino 환경에서 사용할 수 있게 하는 것이다.
전체 기능·upstream 대응·제공 방식은
[NCS Bluetooth 전체 기능과 예제 실행 계약](<01_아두이노 코어 설계/19_NCS_Bluetooth_전체_기능과_예제_실행_계약.md>),
기능 구현은 [M31 TODO](TODO_M31.md)·[M32 TODO](TODO_M32.md), 제품선 진행은
[v0.5.0 TODO](TODO_v0.5.0.md)가 소유한다. 아래 항목은 모두 구현·검증 예정이며 완료 실적이 아니다.

## 1. Catalog와 지원 원칙

1. 고정 NCS의 nRF54L15 공식 지원 Bluetooth sample은 전부 원장에 넣고 Arduino 대응 경로를 배정한다.
   일반 Zephyr Host sample·서비스·profile도 전수 조사해 NU54DK candidate와 미적용 사유를 남긴다.
2. `wrapper`, `direct`, `profile`, `template`, `excluded`의 전달 방식을 사용한다. 모든 기능을 새로운
   고수준 class로 만들 필요는 없지만 사용 가능한 경로·설정·예제·실행 절차가 있어야 한다.
3. 고정 SDK에 없는 기능, 다른 SoC 전용 sample, NU54DK에서 연결할 수 없는 hardware, 외부 credential/peer가
   필요한 sample을 정확히 분류한다. 기능/예제 누락을 `excluded`로 자동 처리하지 않는다.
4. 세 NU54DK만으로 가능한 기능은 보드 간 payload·state·counter·hash로 자동 검증한다. 정밀 RF/audio
   품질·calibration은 제품 완료 조건에 추가하지 않는다.
5. Apple/Android/Google/외부 vendor 상호운용과 Ubuntu/macOS 실물 Host가 없는 행은 `NOT RUN`이다.
   적용 가능한 기능 구현·예제 build를 계속하고 실제 검증한 지원 catalog와 미검증 template를 명시한다.
6. 문서에 등록한 예제, source candidate, build PASS, 실제 기능 PASS, 외부 ecosystem 인증은 독립 상태다.
   M33 공개 시 지원한다고 표시할 필수 행은 증거가 필요하며, 미검증 행은 지원 선언에서 구분한다.

## 2. 작업 배치

| 작업 | 구현·검증 범위 | 현재 상태 |
| --- | --- | --- |
| M33-W01 | 전체 sample inventory 마감·profile/example catalog 범위 | 미착수 |
| M33-W02 | 표준 GATT profile와 beacon·목적별 예제 보강 | 미착수 |
| M33-W03 | Fast Pair·ANCS/AMS 등 외부 ecosystem template·상호운용 | 미착수 |
| M33-W04 | DTM/HCI와 특수 진단 application template | 미착수 |
| M33-W05 | 역할별 예제·설치/compile·사용자 문서 수명주기 | 미착수 |
| M33-W06 | 교차 기능 자원·회귀·peer별 검증/지원 분류 | 미착수 |
| M33-W07 | HOST-W08·재현 package·release candidate | 미착수 |
| M33-W08 | Exact 결과 공개 승인·publish·공개 설치·인계 | 미착수 |

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
- [ ] `M33-INV-01`의 inventory drift·누락·중복·잘못된 지원 승격 negative를 구현한다.

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
- [ ] Apple/Google peer가 없을 때 Host parser/semantic·target/Arduino build·scripted peer 시험을 수행하고
  실제 외부 ecosystem runtime은 `NOT RUN`으로 남긴다.
- [ ] 실제 peer를 사용할 때 모델/OS/앱/adapter·기능 지원성·수동 단계·timeout·보안 결과를 기록한다.
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
- [ ] `M33-REG-01`, `M33-RESOURCE-01`, `M33-INTEROP-01`에 exact image·profile·peer 결과를 연결한다.
- [ ] Bluetooth qualification의 Host/controller/Mesh 적용성·component 근거·제품별 추가 절차를 조사해
  별도 문서에 적는다. Component 자격과 제품 자격·예제 사용 가능성을 서로 구분한다.

### M33-W07 — HOST-W08와 release candidate

- [ ] [다중 Host 계약](<02_빌드 설계/10_v0.5.0_다중_Host_지원_착수_계약.md>)에 따라 Windows 10/11 x64,
  Ubuntu 24.04 이상 AMD64, macOS 26 이상 Apple Silicon의 지원 version matrix를 release 시점에 고정한다.
- [ ] HOST-W04~HOST-W07의 prerequisite/path/cache/package/USB·serial·debug 결과를 exact 입력과 대조한다.
- [ ] HOST-W08의 clean 설치·전체 예제 compile·대표 실제 upload/runtime·upgrade/reinstall/uninstall을
  실제 각 Host에서 마감한다. PC 또는 USB 접근이 없으면 해당 행은 `NOT RUN`이고 세 Host 정식 지원
  공개 gate는 미완료다.
- [ ] Release candidate의 source/board/SDK/toolchain·profile/catalog·version·hash를 고정하고 package를
  독립 두 번 생성해 재현성과 runtime payload·예제 포함 목록을 검증한다.
- [ ] API/profile migration·known limitation·experimental opt-in·미검증 template·외부 ecosystem·Host
  상태를 release notes와 readiness에 동일하게 기록한다.
- [ ] `M33-PACKAGE-01`, `M33-INSTALL-01`을 HOST-W08 증거와 연결하고 공개할 필수 행의 미완료를 차단한다.
- [ ] 기능 구현 완료, 지원 범위 결정 완료, 세 Host 완료, RC 준비 완료를 각각 보고한다. 외부 peer 미확보는
  관련 지원 행에 남기며 독립적으로 가능한 RC 준비까지 진행한다.

### M33-W08 — 공개·최종 인계

- [ ] 적용 필수 기능·예제·Host·package·회귀의 exact 증거와 남은 외부 행을 전수 검토한다.
- [ ] 공개 대상 지원 범위·source·package plan과 자산 hash에 대한 프로젝트 소유자의 승인을 확보한다.
  이 TODO 작성과 과거 v0.4.1 공개 승인을 새 v0.5.0 tag/Release/index 게시 승인으로 사용하지 않는다.
- [ ] 승인된 exact plan으로 tag·Release·asset·stable index를 게시하고 기존 공개 자산을 보존한다.
- [ ] 공개 URL의 hash·격리 설치·예제·대표 upload/runtime·수명주기를 검증한다.
- [ ] `M33-RELEASE-01`에 승인·공개·공개 설치를 독립 결과로 남기고 exact push commit의 CI 완료를 확인한다.
- [ ] README·API/profile·example catalog·release-readiness·검증 기록·HANDOFF와 제품 지원 버전을 맞춘다.
- [ ] M34~M45와 별도 ARF에 남은 security/storage/radio/network/Matter·외부 ecosystem·미검증 Host
  요구를 구체적 다음 행동·장비·owner·상태와 함께 인계한다.

## 4. 예정 test ID·장비·완료 입력

다음은 예약 ID이며 W01에서 하위 case·정량 계약을 확정한다. 모든 보드 시험에는 유한 반복 수·
timeout·packet/object 분모·허용 loss/latency·복구 한계·즉시 중단 오류를 둔다.

| 예정 ID | 구성 | 완료·negative 기준 |
| --- | --- | --- |
| M33-INV-01 | Host | 고정 upstream 전수 매핑·누락/중복/미배정 owner 0, 허위 지원 승격 거부 |
| M33-PROFILE-01 | 2~3보드 | Profile/role별 payload·보안·lifecycle, malformed·권한 오류·cross-link 거부 |
| M33-BEACON-01 | 2보드 | Protocol별 실제 수신/decode, length/version·변조 거부 |
| M33-ECOSYSTEM-01 | 해당 Apple/Google/OS peer | Template build와 실제 peer 결과 분리, credential 누락·bond/access 거부 |
| M33-DIAG-01 | DTM 2보드, 기타 transport별 외부 Host | DTM 양방향 TX/RX·실제 수신 수·유한 STOP·UART 격리·ownership, tester 없는 정밀 RF 측정 NOT RUN/범위 밖 |
| M33-EXAMPLE-01 | 각 build Host, runtime은 해당 role 보드 | 설치 catalog/role 전수 compile·실행 절차, 누락 profile·잘못된 조합 거부 |
| M33-REG-01 / M33-RESOURCE-01 | Host + 최대 3보드 | 이전 기능·명시 조합·자원 회수·오귀속/손상/누수·유한 부하 |
| M33-INTEROP-01 | 기능별 외부 BLE peer | 모델·OS·기능별 actual 결과, peer 미지원·장비 부재 구분 |
| M33-PACKAGE-01 / M33-INSTALL-01 | 실제 세 Host와 USB 보드 | 재현 package·전체 예제·수명주기, hash/arch/profile·권한 오류 |
| M33-RELEASE-01 | 승인된 exact plan·공개 URL | 승인·게시·다운로드 byte·공개 설치·CI, 미완료 필수 gate 게시 차단 |

## 5. 완료와 보존 계약

- M33의 구현 완료 분모는 W01~W08 **8개**다. 예제 수·role 수·test case 수·HOST-W08은 별도 분모로
  기록하며 원장 검증으로 숫자를 집계한다. 계획 문서 완성을 W 완료로 계산하지 않는다.
- 공개 지원이라고 표시할 모든 적용 기능/예제/Host 행에는 실제 필요한 증거가 있어야 한다. 외부 장비나
  credential이 없는 행은 `NOT RUN`·지원 제한·template 상태를 공개하며 기본 GATT 또는 보드 peer PASS로
  전체 ecosystem 상호운용을 대신하지 않는다.
- NU54DK 미지원·SDK 미지원·experimental·external-add-on·build-only를 이유와 함께 분류하면 누락
  판정은 닫을 수 있다. 그 행의 runtime 결과가 자동 PASS로 바뀌지는 않는다.
- M28/M29/M30 완료와 M30-POWER-01의 4지점 × 3회·12/12 PASS, 실제 source
  `ae5186f7790a748641fb04128c16156519ee1017`, recovery failure 0, invalid image boot 0을 보존한다.
  NFC adapter의 RF `NOT RUN`·지원 제외와 실제 유선 USB/DAPLink VCOM OOB 경계도 유지한다.
- Probe UID 원문을 채팅·문서·로그에 노출하거나 저장하지 않는다. SHA-256 identity·serial·role·
  firmware revision을 시험 직전 대조한다. 여러 probe 임의 선택·자동 mass erase/recover·전체 flash
  초기화·임의 GPIO·전원 차단을 하지 않는다.
- 실패/HOLD/NOT RUN 원본과 과거 tag/Release/asset은 보존한다. 후속 성공을 같은 원본에 덮어쓰지 않는다.
- M33 계획은 v0.5.0 공개 승인이 아니다. 승인 가능한 exact 결과가 준비되면 공개 범위를 확정하고,
  세 Host 정식 지원에 필요한 실제 Host 행이 비어 있으면 해당 공개 gate를 미완료로 유지한다.
