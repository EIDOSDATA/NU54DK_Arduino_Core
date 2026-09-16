# M31 실행 TODO — NCS ISO·LE Audio·Direction Finding·Channel Sounding 예제의 Arduino 실행

| 항목 | 내용 |
| --- | --- |
| 대상 제품선 | `v0.5.0` |
| 현재 상태 | **W01~W02 완료, W03·W04·W05 진행 중 / 완료 2/8 작업 묶음** |
| 선행 완료 | M30 W01~W08 8/8, test ID 10/10, 실제 전원 차단 4지점 × 3회 = 12/12 |
| 병행 Host 상태 | HOST-W01~HOST-W03 완료, HOST-W04~HOST-W08 잔여; M31과 독립된 8개 작업 분모 |
| 기준 SDK | NCS `v3.4.0`, Zephyr `4.4.0`, 고정 lock revision |
| 기능 검증 장비 | 사용자 확인 NU54DK 3개; 실제 시험 직전 SHA-256 probe identity·serial·role·firmware 재대조 |
| 최종 갱신일 | 2026-09-16 |

M31의 목표는 **고정 NCS에서 nRF54L15DK에 적용되는 ISO·LE Audio·DF·connected Channel Sounding
기능과 예제를 NU54DK Arduino 환경에서 사용할 수 있게 하는 것**이다. 고수준 Arduino facade,
고급 직접 API, 검증된 profile·template 중 기능에 맞는 제공 경로를 사용한다. 모든 예제를 한 가지
추상화로 감싸는 것은 필수 조건이 아니다.

제품선 순서는 [제품 로드맵](<01_아두이노 코어 설계/02_구현_로드맵.md>), 전체 기능 소유권과
예제 판정 규칙은 [NCS Bluetooth 전체 기능·예제 실행 계약](<01_아두이노 코어 설계/19_NCS_Bluetooth_전체_기능과_예제_실행_계약.md>),
기능별 목표는 [경쟁 마일스톤](<01_아두이노 코어 설계/08_전_인스턴스_DMA_BLE_경쟁_마일스톤.md>),
Host는 [다중 Host 지원 계약](<02_빌드 설계/10_v0.5.0_다중_Host_지원_착수_계약.md>)이 소유한다.
계획 개정 자체는 구현 증거가 아니다. 현행 W01~W02 완료와 W03 이후 미완료 범위는
[착수 계약](<01_아두이노 코어 설계/20_M31_Bluetooth_착수_계약.md>)과
[W02 완료 기록](<04_검증 기록/167_M31_W02_설치_Arduino_ISO_예제_완료.md>)에서 구분한다.

## 1. 착수 원칙과 지원 판정

1. M31-A ISO·전체 LE Audio profile, M31-B Direction Finding, M31-C connected Channel Sounding을
   각각 판정한다. M31-W01~W08의 8개 작업 묶음과 기능별 test ID·role subcase 분모를 구분한다.
2. 고정 SDK의 Kconfig·header·sample 존재, nRF54L15 공식 sample target, NU54DK native build,
   Arduino build, runtime capability, 실제 기능 HIL을 각각 기록한다. nRF54L15DK용 build metadata가
   있는 예제는 우선 구현 대상이며, generic Host source만 있는 예제는 NU54DK 적용성 조사 대상이다.
3. 기본 SoftDevice Controller(SDC)의 DF는 AoA CTE 송신 범위이며 RX/IQ와 AoD를 지원한다고
   해석하지 않는다. **원시 IQ 수집과 안테나 전환·실제 AoA 각도 계산은 별도 기능**이다. 고정 Zephyr LL의
   RX 코드와 nRF54L15 DTS의 `dfe-supported`는 대체 수신 구성의 조사 근거이지 NU54DK target
   build/runtime PASS가 아니다. 고정 Zephyr connectionless RX 예제의 안테나 배열은 선택 사항이다.
   따라서 추가 배열 확보를 기본 안테나 raw IQ 경로의 조사·build·가능한 HIL 선행조건으로 두지 않는다.
   SDC RX 미제공만으로 nRF54L15 하드웨어 불가를 단정하거나, LL source만으로 동작을 확정하지 않는다.
4. 안정 Arduino facade는 고정 자원·명시적 수명주기·fail-closed 오류를 사용하며 Zephyr 구조체를
   공개 facade에 직접 노출하지 않는다. 고급 직접 API는 별도 opt-in 경로에서 upstream 의존성과
   안정성 수준을 명시한다. M28~M30의 generation handle·link 격리·보안 계약을 유지한다.
5. 사용자는 정밀 RF 보정, 음질·음향 입출력 분석, 각도·거리 정확도를 이번 기능 완료의 필수 gate에서
   제외했다. 합성 payload·PCM과 보드 간 실제 무선 송수신으로 데이터 경로·상태·복구를 검증한다.
   원시 결과와 거리 추정값을 출력할 수 있다는 판정에 정밀도 보증을 덧붙이지 않는다.
6. 보드 3개로 가능한 소스 조사 → 계약·parser → 구현·예제 → build → 기능 HIL → 회귀·인계를
   자동 실행 대상으로 삼는다. mapping 불명확·probe lock 충돌·접근 권한 부족의 해당 실기 행은
   `NOT RUN`으로 남기고 독립 작업은 계속한다. 조사 중인 지원성은 `unresolved/source_candidate`,
   실행한 실패는 `FAIL`, 해결 전 보류는 `HOLD`, 근거로 확인한 미지원만 `UNSUPPORTED`로 구분한다.
7. 고정 stack에서 적용 가능하다고 판정한 필수 board-only 기능은 실제 HIL이 있어야 닫는다. 메모리
   부족·build 실패·SDK 제약은 원인과 해결 또는 profile 분리 TODO를 남긴다. 계획을 적었다는 이유로
   지원 판정이나 작업 묶음을 완료 처리하지 않는다.
8. HOST-W04~HOST-W06 구현·가능한 자동 검사를 병행한다. Ubuntu/macOS의 실제 설치·USB upload·
   serial/debug·수명주기 검증은 **사용자가 최종 릴리스 단계에서 수행**하고 HOST 원장과 M33 release
   gate에 결과를 인계한다. 이 사용자 최종 검증은 M31 firmware 개발의 선행 차단이 아니다.
9. **Apple/Google 기능과 mic/speaker/codec 등 외장 장치 경로는 담당 마일스톤에서 사용 가능한 구현·
   예제·설정/연결 안내와 가능한 자동 검사가 필수**다. Apple/Google은 M33-W03, Audio 외장 경로는
   M31-W03이 소유한다. 실제 제품 운용·상호운용·물리 입출력 검증은 사용자 후속 책임이며
   v0.5.0 개발·릴리스 차단 조건이 아니다. 그 실물 결과는 `NOT RUN`으로 보존하고 구현/build PASS와
   구별한다. 빈 template·성공 출력만 있는 stub 또는 구현 결함을 이 범위 결정으로 면제하지 않는다.

## 2. 작업 묶음 — 8개 유지

| 작업 | 상태 | 구현·검증 범위 | 완료 산출물 |
| --- | --- | --- | --- |
| M31-W01 capability·착수 계약 | **완료** | ISO·전체 Audio profile·DF·CS 적용성, SDC와 Zephyr LL의 기본 안테나 raw IQ 수신 구성 조사·target build, 전체 NCS Bluetooth sample inventory, 역할·자원·시험 기준 고정; 1보드 capability 실행 | 두 JSON·schema/parser·Host 20/20 negative·전체 Host gate·5구성 clean target/HCI query, parity 703행; [W01 exact audit](<04_검증 기록/evidence/m31-w01-exact-8c125a22/w01-closure-audit.json>) |
| M31-W02 raw ISO 기반 | **완료** | CIG/CIS central·peripheral, BIG/BIS source·receiver, combined CIS/BIS 적용성, ISO time sync, buffer·sequence·timestamp·암호화·해제·재시작 | 설치 package 역할 예제 11/11 build, CIS·BIS·암호화·wrong code·sync loss·time sync·세 보드 combined exact HIL PASS; [W02 closure audit](<04_검증 기록/evidence/m31-w02-arduino-e6ae812e/closure-audit.json>) |
| M31-W03 전체 LE Audio profile | **진행 중** | §3의 LC3·BAP/PACS/ASCS·BASS·CAP·CSIP·PBP와 제어/용도별 profile 전부 판정·구현; 합성 PCM·encoded payload source/sink | profile·role별 예제와 build/runtime 상태, 기능 HIL·negative, 자원 예산·외부 I/O 경계 |
| M31-W04 Direction Finding | **진행 중** | connectionless AoA CTE TX 20회, Zephyr LL connected AoA CTE 응답 stop/restart 20회 확인; 기본 안테나 raw IQ RX는 실패·미완료, SDC AoD 미지원; 안테나 전환·각도 계산 확장 경로 별도 구현/판정 | TX·raw IQ 예제·target/HCI/수신 evidence, controller별 build/runtime 판정, 외장 확장 구현·설정/연결 안내와 사용자 후속 실기 구분; [CTE 송신](<04_검증 기록/170_M31_W04_DF_CTE_송신_진행.md>), [연결 응답](<04_검증 기록/174_M31_W04_연결_CTE_응답_실기.md>), [IQ 수신 진단](<04_검증 기록/172_M31_W04_DF_기본안테나_IQ_수신_진단.md>) |
| M31-W05 connected Channel Sounding | **진행 중** | initiator·reflector, secure ACL·capability·procedure, RAS·raw 결과·거리 추정 출력, stop/restart·peer loss·보안 negative | upstream native RAS target build와 2보드 거리 결과 100개 진단 확인; Arduino 역할·procedure 100회·복구·negative는 잔여; [착수 기록](<04_검증 기록/171_M31_W05_CS_native_2보드_착수.md>)·[RAS 진단](<04_검증 기록/173_M31_W05_RAS_native_100회_진단.md>) |
| M31-W06 통합·회귀 | **미착수** | M31-A/B/C 선택 조합의 자원 충돌·link 격리, M19~M30 영향 회귀, stale callback·disconnect·재연결 | 통합 runner, RAM/RRAM·stream/connection 예산, 오류·복구 증거와 명시적 동시 조합 |
| M31-W07 기능 HIL·예제 실행 | **미착수** | 3보드 역할 재배치로 적용 가능한 모든 board-only subcase 유한 실행, Arduino 설치 예제의 실제 실행; 외부 peer 행 별도 관리 | exact image·익명 mapping·transcript·원본 hash, 기능/role별 PASS·FAIL·NOT RUN·UNSUPPORTED 근거 |
| M31-W08 마감·M32/M33 인계 | **미착수** | API·예제·지원표·문서·원장 일치, Host/target 회귀, M32 modern controller·Mesh·공존과 M33 예제 catalog에 인계 | 완료 또는 정확한 잔여 목록, 판정별 분모, known limits·회귀 목록·M32/M33 dependency |

M32-A는 modern LE controller/Host·Nordic 확장, M32-B는 Mesh와 Mesh 1.1, M32-C는 최소 radio와
공존을 맡는다. M31-W01에서 발견하는 Power Control/Path Loss, subrating, SCA/frame-space/shorter
interval, 다중 advertising/identity, EAD, LLPM/QoS 등은 전체 원장에 등록하고 M32-A로 연결한다.
추가 GATT service·Fast Pair/Apple peer·DTM/HCI 예제의 catalog와 패키징은 M33에 인계한다.

## 3. W03 세부 구현·예제 TODO

아래 항목은 **모두 계획/구현 미착수**다. 각 행은 source·target·Arduino build·runtime·negative
상태를 독립적으로 가진다. role 이름만 제공하는 빈 예제나 단일 BAP 성공으로 전체 profile을
완료하지 않는다. 고정 SDK에서 nRF54L15 지원성이 불명확한 profile은 source candidate부터 검증한다.

| 하위 작업 | 구현할 기능과 역할 | Arduino 예제·실제 기능 판정 |
| --- | --- | --- |
| W03-01 LC3·stream data | 적용 가능한 LC3 encode/decode, codec capability·configuration, frame/sample rate/SDU/buffer 계약, 합성 PCM과 encoded source/sink | 합성 신호 → encode → ISO → decode의 frame 길이·수신 수·decoder 상태; lossy codec에 원본 PCM byte 동일성을 요구하지 않음 |
| W03-02 BAP unicast·PACS/ASCS | Unicast Client/Server, 양 역할의 Audio Source/Sink, PACS capability/context·ASCS ASE 상태와 제어, 단방향·양방향 구성 | client/server 역할별 예제, discovery → codec/QoS → enable/start → stream → stop/release, 잘못된 ASE 상태/codec/QoS 거부 |
| W03-03 BAP broadcast | Broadcast Source/Sink, BIG/BIS 선택·sync·metadata, broadcast code와 암호화, 재동기 | source + sink 1개/2개 예제; 실제 payload/sequence, wrong code·sync loss·rejoin |
| W03-04 BASS | Broadcast Audio Scan Service, Scan Delegator, Broadcast Assistant, receive state·source add/modify/remove | source/assistant/delegator-sink 3역할 예제; 검색·위임·sync·상태 통지, 잘못된 source/중복/제거 복구 |
| W03-05 CAP | Initiator/Acceptor/Commander, unicast/broadcast 절차, 적용 가능한 handover | 역할별 예제, discovery·start/update/stop와 coordinated procedure 완료/실패 callback; 필요한 역할 수와 자원 계약 명시 |
| W03-06 CSIP | Coordinated Set Member/Coordinator, set discovery·membership·rank·lock 절차 | coordinator + member 최대 2개 예제, set 식별·잠금/해제·member loss·재가입, 잘못된 key/rank/state 거부 |
| W03-07 PBP | Public Broadcast Profile source/sink, public announcement·metadata·broadcast discovery | public broadcast 검색·선택·수신 예제; PBP 기능 검증과 Auracast 명칭/qualification 판정 별도 |
| W03-08 VCP·VOCS·AICS·MICP | Volume Controller/Renderer, volume offset, Audio Input Control, Microphone Controller/Device 역할·service | 원격 volume/mute/offset/input 상태 왕복 예제; 값 범위·권한·counter·subscription·disconnect negative; 물리 소리 변화는 별도 |
| W03-09 MCP/MCS·CCP/TBS | Media Control Profile/Service, Call Control Profile/Telephone Bearer Service의 client/server 역할 | 합성 player/통화 상태 예제, 명령·상태 통지·object/index·지원 opcode·invalid transition 검증; 실제 미디어/전화 연결 불필요 |
| W03-10 TMAP·GMAP | Telephony and Media Audio Profile, Gaming Audio Profile의 고정 SDK 역할·feature 조합 | 지원 role별 capability·discovery·stream 조합 예제, 역할/품질 설정 불일치 negative; 실제 전화기·게임 제품 상호운용은 외부 peer 행 |
| W03-11 HAP/HAS | Hearing Access Profile/Service client/server, preset 조회·선택·변경/알림과 적용 coordinated operation | 합성 preset·보청기 역할 예제, index·동기 preset·권한·연결 끊김 검증; 의료·음향 성능이나 실제 보청기 상호운용 보증 없음 |

각 행에는 다음 TODO를 적용한다.

- [ ] 고정 upstream sample 경로·test ID·Kconfig·nRF54L15 allow/integration/build-only와 license 기록
- [ ] 필요한 controller·Host feature·RAM/RRAM·link/ASE/BIS/codec 자원을 profile별로 고정
- [ ] `wrapper`, `direct`, `profile`, `template` 중 제공 경로 선정; 미지원은 근거·후속 소유자 기록
- [ ] 최소 시작 예제와 역할별 상대 예제, 오류·해제·재시작 예제를 만들고 Arduino 설치 목록에 등록
- [ ] Serial로 role/command를 제어해 버튼·물리 audio 입력 없는 재현 경로와 예상 출력을 문서화
- [ ] Host semantic/negative → native/Arduino build → 적용 가능한 2~3보드 기능 HIL 순서로 판정
- [ ] 외부 mic/codec/speaker, 상용 phone/headset 등 원래 sample의 확장 경로를 실제 구현하고 예제·설정/연결 안내·가능한 자동 검사를 제공; 실물 운용/검증은 사용자 후속 `NOT RUN`, 개발·릴리스 비차단으로 명시

## 4. W01에서 먼저 구현할 산출물과 실행 순서

1. 저장소·branch·HEAD·미커밋 변경·board submodule·SDK/toolchain lock과 변경 전 전체 Host 기준선을
   기록한다. 다른 작업의 변경 소유권과 실행 중 검사를 보존한다. CI/CD 조회·대기는 최신 사용자
   요청을 따르며, 이번 문서 변경·커밋·푸시 작업에는 CI/CD 확인을 요구하지 않는다.
2. 고정 SDK의 Bluetooth sample 전부를 수집하는
   `variants/nu54dk/ncs-v3.4.0-bluetooth-sample-parity.json`을 구현한다.
   전체 기능 계약의 schema에 따라 upstream path/test ID, nRF54L15 target metadata, dependency,
   필요한 장비·보드 수·role, 제공 경로·담당 M/W, native/Arduino build·runtime·negative 상태를 담는다.
   M31 이외 예제도 누락 없이 M32/M33 또는 후속 radio 마일스톤의 소유자에 연결한다.
3. `variants/nu54dk/m31-ble-readiness.json`과 M31 착수 계약을 만든다. capability별 source candidate,
   controller support, compile 결과, runtime query, 기능 HIL을 분리하고 profile별 opt-in·지원 제한과
   §3의 모든 Audio 행을 담는다. 현행 두 JSON의 구현 단계와 개별 미실행 상태는 원장에 기록한다.
   두 원장에 master 계약의 case별 `verification_owner`·`verification_stage`·`development_blocker`·
   `release_blocker`를 적용한다. Apple/Google·외장 실물은 `user`/`user_follow_up`/`false`/`false`,
   Ubuntu/macOS 실물은 `user`/`final_release`/`false`/`true`로 구분한다. 구현·예제·자동 검사 case는
   필수이며 사용자 후속 실물 case와 합치지 않는다.
4. Schema·capability protocol/parser와 Host unit/negative test를 구현한다. 누락·중복·미지 feature,
   malformed/truncated/noisy output, unknown role·invalid status, revision/image/nonce mismatch,
   unsupported 조합, timeout·중복 완료, raw UID 검출과 build→HIL 부당 승격을 거부한다.
   사용자 후속 실물 `NOT_RUN`의 재차단/PASS 승격, 필수 구현·자동 검사를 사용자 후속으로 숨기는
   입력과 Ubuntu/macOS 최종 실물 gate를 면제하는 입력도 거부한다.
5. M31 capability target image와 build matrix 항목을 구현한다. HCI capability와 Host profile의
   compile/runtime 준비를 구분해 출력하고, query로 입증할 수 없는 peer 기능은 `NOT RUN`으로 남긴다.
   DF는 기본 SDC TX와 별도 Zephyr LL RX 구성을 분리한다. 고정 source·Kconfig·DTS·NU54DK 설정을
   대조해 **기본 안테나·배열 없는 raw IQ**의 target build를 먼저 수행하고 실패 시 실제 오류/제약을
   남긴다. 대체 controller가 기존 기능에 미치는 영향과 opt-in profile을 명시하며 SDK pin을 바꾸지 않는다.
6. test ID·role subcase 목록, board 수·timeout·수신 분모·negative·evidence schema와 fail-fast 기준을
   착수 계약에 고정한다. exact SHA-256 probe identity·serial·role·image mapping이 확인되면 한 보드
   capability HIL을 실행한다. 보드 또는 mapping 미확정이면 build 증거까지 남긴다.
7. W01 판정 후 W02의 CIS 중앙/주변 역할과 BIS source/sink부터 구현한다. 2보드 기본 → 3보드 복수
   수신/적용 가능한 combined 역할 → ISO time sync 순으로 기능을 닫고 W03에 인계한다.
8. W04 DF와 W05 CS는 controller 적용성에 맞춰 병행할 수 있다. W04는 W01의 RX build와 mapping이
   확인되면 기본 안테나 두 보드로 raw IQ report 수신 HIL을 수행한다. 수신 sample count·형식·status·
   start/stop·복구를 검사하며 안테나 배열과 정밀 각도 oracle을 요구하지 않는다. W06 전까지 실패 원인과
   profile별 자원을 분리한다. HOST-W04 Ubuntu prerequisite·resolver·launcher도 독립 진행한다.

## 5. 예제 품질과 설치 계약

- [ ] 예제마다 목표 기능·upstream origin·필요 보드 수·역할·profile 선택·실행 순서·예상 Serial 출력 명시
- [ ] 최소 예제, 상대 역할 예제, negative/recovery 예제를 기능에 맞게 제공; 이름과 경로는 원장에서 고정
- [ ] Arduino `setup()`/`loop()` 경로에서 실제 기능 호출; 고급 직접 API 예제의 Zephyr 의존성·설정은 설명
- [ ] queue/buffer 수명, error 처리, timeout, 종료·재시작, 자원 반환을 예제에 포함하고 busy-loop 회피
- [ ] 한국어 Doxygen·BSD/Allman·탭 폭 4·모든 제어문 중괄호 적용
- [ ] clean Arduino package 설치의 example discovery → compile → role firmware → Serial oracle를 연결
- [ ] Kconfig profile과 build options를 코드 밖의 검증된 설정으로 제공하고 임의 SDK patch 요구 금지
- [ ] 실험적·미지원·사용자 후속 실물 검증의 책임·비차단 범위를 example README와 parity 원장에 일치시킴

M33은 M31/M32가 전달한 예제와 추가 GATT/profile·특수 template의 전체 catalog, package discovery,
세 Host 설치 후 전체 예제 compile·대표 runtime를 마감한다. M31에서는 해당 기능의 Arduino
사용 가능성과 역할별 예제 검증까지 완료해야 한다.

## 6. HOST-W04~HOST-W06 병행 TODO

| Host 작업 | 상태 | 바로 할 일 | 증거 경계 |
| --- | --- | --- | --- |
| HOST-W04 prerequisite | **미착수** | Ubuntu 24.04+ AMD64부터 OS/arch별 nRF Util·sdk-manager·NCS·Zephyr·toolchain·Arduino CLI URL/hash/revision manifest; Linux resolver·launcher·실행 권한·serial/USB path·udev 조건과 negative | 정적/Ubuntu CI/unit와 실제 PC clean 설치·USB upload·serial/debug를 별도 칸으로 기록 |
| HOST-W05 portable path/cache | **미착수** | 경로 구분자·executable 탐색·XDG cache, lock·case sensitivity·symlink·execute bit·공백·한글·긴 경로·atomic replace·권한 실패 | 해당 OS native CI/build 증거와 실제 사용자 Host 설치·권한 증거 분리 |
| HOST-W06 package·CI | **미착수** | 세 Host metadata·launcher·archive mode, clean package와 전체 예제 compile matrix·artifact 비교 | native runner의 실제 실행 범위만 PASS, mock/cross-build 결과를 실물 Host PASS로 승격 금지 |

HOST 전체는 **W01~W08의 독립 분모**를 유지한다. 현재 3/8 완료이며 “W04~W08 잔여”는
HOST-W04~HOST-W08을 뜻한다. 실제 Ubuntu/macOS 설치·USB upload·serial/debug·lifecycle는
사용자가 최종 릴리스 단계에서 수행한다. 그 전에는 해당 실물 행을 `NOT RUN`으로 남기며 M31의
필수 firmware gate에 합산하지 않는다. HOST-W07의 사용자 결과와 HOST-W08의 전체 Host 마감은
M33 공개 조건으로 이어진다. Apple/Google 및 외장 I/O의 사용자 후속 검증은 이 최종 Host gate와 달리
개발·릴리스 차단 조건이 아니다.

## 7. 보드 3개 자동화 범위와 다음 개입 지점

| 단계 | 자동으로 진행할 범위·최소 보드 | 미실행·사용자 후속 범위와 책임 |
| --- | --- | --- |
| W01 | source·원장·parser·target, 확인된 NU54DK 1개 capability HIL | probe/serial mapping 불일치·USB 접근 권한·board 미연결 |
| W02 | 2개 CIS/BIS 기본, 3개 복수 receiver·적용 가능한 combined ISO·time sync | 고정 controller/자원 한계가 의도한 역할 조합을 허용하지 않을 때 별도 판정 |
| W03 | 2~3개 합성 PCM/encoded payload와 Audio profile 제어·상태·실제 RF data path; 외장 I/O 구현·예제·설정 안내와 자동 검사 | 외부 mic/codec/speaker·상용 phone/headset의 실물 운용/상호운용은 사용자 후속 `NOT RUN`, 개발·릴리스 비차단 |
| W04 | 1개 CTE TX 설정·시작/중지·controller event; 기본 안테나 RX 조사·build 뒤 적용 가능하면 2개 raw IQ 수신 HIL | RX 미확인은 실제 software/controller 제약을 조사할 개발 항목; 배열 확보를 선행 요구하지 않음. 안테나 전환·실제 각도 계산의 외장 경로는 구현/안내 후 사용자 실기 |
| W05 | 2개 CS initiator/reflector·RAS·raw 결과·거리 추정 출력·보안/복구, 3개 peer 분리 | cross-vendor CS peer 또는 별도로 요청한 정밀 거리/각도 시험 |
| W06~W08 | 3개 역할을 순차 재배치한 기능·통합·예제·회귀·원장·문서 인계 | 해결되지 않은 필수 board-only 결함·mapping/접근 문제는 미완료; 사용자 후속 외부 실물 검증은 비차단 |
| HOST | 장비 독립 manifest·resolver·launcher·negative와 가능한 자동 검사 | Ubuntu/macOS 실제 설치·USB upload·serial/debug는 사용자 최종 릴리스 검증; 중간 개발 선행조건 아님 |

CTE TX 명령 수용·연결 peer 동작만 관찰했다면 그 범위만 기록한다. 수신 IQ 증거가 없는데 CTE
수신이나 각도 측정 PASS로 기록하지 않는다. **IQ report 수신 PASS 역시 실제 AoA 각도 계산 PASS가
아니다.** AoD는 고정 SDC `UNSUPPORTED`, 대체 controller의 raw IQ RX는 적용성 판정 전
`source_candidate`다. 수신 구성의 실제 build/runtime 실패는 그 controller·profile에 한정해 기록하고
칩 전체 불가로 확대하지 않는다. nRF54L15 대상이 아닌 `nrf_dm`을 CS 대체 예제로 등록하지 않는다.

실물 시험 전 SHA-256 probe identity·serial path·role·firmware revision을 다시 결합한다. 여러 probe
중 임의 선택을 금지하며 raw probe UID는 채팅·문서·저장 로그에 남기지 않는다. 기존 배타 lock,
watchdog·lease·STOP·자원 반환 계약을 사용한다. 자동 mass erase/recover·전체 flash 초기화·임의
GPIO·전원 차단을 실행하지 않는다. M30의 4지점 × 3회 정책과 12/12 완료를 다시 변경·재예약하지 않는다.

## 8. 고정 test family와 W01 수치 확정 TODO

다음 **10개 test family는 기능 식별자**다. 작업 분모 8과 다르며 현재 CAP·PARITY·ISO 3/10 PASS다.
각 family 아래 역할·profile별 subcase를 W01 원장에 전수 열거하고 그 분모를 함께 고정한다.
아래 시간·반복은 기능 검증의 계획 기준이며 제품 성능 보증이 아니다. SDU/codec/PHY·허용 손실과
구체 자원 상한은 고정 sample 기본값·board budget을 대조해 첫 시험 전에 계약과 JSON에 확정한다.
미확정 필드가 남은 subcase는 실행 승격하지 않는다.

| Test ID | 소유 작업·계획 판정 | W01에서 고정할 입력·정량 조건·negative |
| --- | --- | --- |
| M31-CAP-01 | W01, 1보드 capability | profile별 60초 timeout, expected feature/role 응답 전수 일치·revision mismatch 0; unsupported를 supported로 오판 0 |
| M31-PARITY-01 | W01/W08, 전체 sample 원장 | 고정 두 source tree의 Bluetooth sample/test 발견 목록 100% 판정·owner 지정, 중복/누락/근거 없는 PASS 0 |
| M31-ISO-01 | W02/W07, 역할별 raw ISO | CIS 양 역할·BIS source/sink·time sync·combined 적용 subcase; 각 180초·stream start/stop 20회, 30초 내 자원 회수; sequence/송수신 분모·손실 식·허용률 고정 |
| M31-AUDIO-01 | W03/W07, §3 전체 profile subcase | control 역할당 100 operation·stream 각 180초·start/stop 20회, 30초 내 복구; codec/ASE/BASS/CSIP 등 상태 불일치·잘못된 인자 수용 0 |
| M31-DF-01 | W04/W07, CTE TX·기본 안테나 raw IQ RX별 판정 | 적용 mode별 start/stop 20회·전체 180초 timeout, 잘못된 CTE type/length 수용 0; RX 적용 시 report/sample count·형식·status·복구 수치 고정; raw IQ·각도 계산·AoD 상태와 근거 분리 |
| M31-CS-01 | W05/W07, secure initiator/reflector | procedure 100회·전체 600초 timeout·stop/restart 20회, 30초 내 복구; raw/추정 결과 수·유효/invalid 분모, 미인증·wrong peer 수용 0 |
| M31-NEG-01 | W01~W07, parser/API/runtime 오류 | malformed·stale·wrong role·unsupported·자원 고갈·wrong key·peer loss class별 Host/해당 target case, class당 20회·30초 복구 timeout, 잘못된 성공·누수 0 |
| M31-REG-01 | W06/W08, 영향 회귀 | M19~M30 영향 목록 전수와 선택 M31 조합, family별 기존 수치 재사용·신규 통합 180초; cross-link·보안·자원 회수 오류 0 |
| M31-EXAMPLE-01 | W07/W08, Arduino 예제 | 채택된 M31 example discovery/build 100%, board-only role runtime 전수와 README oracle 일치; 외부 peer/I/O 미실행 분모 별도 |
| M31-CLOSE-01 | W08, 문서·원장 인계 | 모든 M31 row의 state·숫자·revision·evidence·링크 정합, 문서 gate·JSON/parser·diff check, M32/M33 미소유 TODO 0 |

각 subcase는 최대 실행 시간, 즉시 중단 오류, 실패 진단 경로와 동일 조건 재검증 횟수를 기록한다.
재검증은 원인·수정이 특정된 뒤 최대 1회씩 별도 attempt로 남기며 새로운 수정 없이 무한 반복하지
않는다. 실패 attempt를 지우거나 최종 성공으로 덮어쓰지 않는다. loss·latency/jitter는 측정 가능한
software timestamp 의미와 오차를 밝히고, 동기화되지 않은 두 보드 timestamp로 정밀 지연을 주장하지 않는다.

증거는 exact Core/board/NCS/Zephyr/toolchain·profile·image hash, SHA-256 probe identity·serial·role,
nonce·test/subcase/attempt, 입력·요청/실제 시간·송수신 분모·negative 기대값·결과, 실패 원본
transcript와 SHA-256 manifest를 결합한다. source/build/runtime/상호운용 결과를 별도 필드로 유지한다.

## 9. M31 완료 조건과 정확한 인계

M31은 다음을 모두 만족해야 완료다.

- [ ] M31-W01~W08 **8/8**과 10개 family 아래의 적용 가능한 필수 subcase가 계약대로 완료
- [ ] M31-A/B/C와 §3 모든 Audio profile의 지원/실험적/조건부/미지원 판정·근거·제공 경로 확정
- [ ] 고정 stack에서 적용 가능한 board-only 기능의 native/Arduino build·실제 기능 HIL·negative PASS
- [ ] 기본 안테나 raw IQ RX의 source/controller·target build·runtime 적용성을 근거로 판정하고,
  지원 가능하면 2보드 실제 IQ 수신까지 검증; 추가 배열 부재로 조사·build를 생략하지 않음
- [ ] M31 소유 외부 audio I/O·외장 확장은 사용 가능한 구현·예제·설정/연결 안내·가능한 자동 검사를
  완료하고 실물 운용/검증은 사용자 후속 `NOT RUN`·개발/릴리스 비차단으로 기록; 정밀 RF/음질/각도/
  거리 정확도는 필수 gate 밖이고 기본 안테나 IQ 수신을 각도 계산 PASS로 확대하지 않음
- [ ] M19~M30 영향 회귀와 자원·보안·disconnect recovery 오류 0; 과거 실패·HOLD·NOT RUN 원본 보존
- [ ] 예제·지원 matrix·readiness·sample parity·검증 기록·HANDOFF의 상태/수치/링크 정합
- [ ] M32-A modern controller·Nordic, M32-B Mesh, M32-C 공존에 필요한 자원/profile/예제 dependency 인계
- [ ] M33 전체 sample catalog·추가 GATT/profile/template·Apple/Google 구현·사용자 후속 상호운용·
  세 Host·release gate에 정확한 잔여 인계

근거 있는 `UNSUPPORTED`와 사용자 확정 범위 밖 행은 기능 PASS 수에 넣지 않고 판정 완료 수로
별도 보고한다. 필수 board-only 기능의 `FAIL`/`HOLD`/`NOT RUN`이 남으면 해당 W는 미완료다.
사용자에게 인계한 외부 실물 검증의 `NOT RUN`은 이유·사용자 책임·개발/릴리스 비차단을 명시하며
필수 구현·예제·자동 검사의 완료와 구별한다. 범위 결정을 미완성 구현 또는 확정 결함의 면제로 쓰지 않는다.

M31 완료는 v0.5.0 공개·Bluetooth qualification·실제 세 Host 완료가 아니다. 현재 공개·설치 지원은
`v0.4.1`, 개발 소스는 `0.4.1-dev`이며, HOST의 실제 장비 증거와 공개 판정은 M33이 소유한다.
