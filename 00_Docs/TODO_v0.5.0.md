# v0.5.0 실행 계획 — M31 완료 후 Windows 릴리스

현재 설치·지원 배포는 **v0.4.1 하나**이며 v0.4.0 M27까지의 기능 기준선과 v0.4.1 설치기
유지보수는 완료했다. 이 문서는 다음 제품선의 진행 상태·남은 작업과 판정 산출물을 관리한다.
**M28은 W01~W08·9개 test ID, M29와 M30은 각각 W01~W08·10개 test ID를 완료했다.
M30-W08 `M30-POWER-01`은 네 지점 × 3회 실제 전원 차단 12/12를 통과했고 HOST-W01~HOST-W03도
완료했다. M31은 W01~W03 완료 3/8이고 W03 LE Audio 11/11을 닫았다. W04 DF·W05 CS는 미완료이며 M32·M33은 미착수**다. M28~M30 완료는 v0.5.0 공개, mobile/desktop 전체 상호운용 또는
Bluetooth qualification 완료가 아니다. 현재 v0.4.1 사용자 지원과 후속 개발은 별개다.

**2026-09-21 사용자 결정: v0.5.0은 M31 완료 후 Windows 10/11 x64로 릴리스한다.**
M32/M33의 추가 기능·전체 catalog와 Ubuntu/macOS 지원은 후속 버전(미정)으로 분리한다.
M31 기능 완료만으로 공개하지 않으며 §6의 패키지·설치·RC·공개 승인 gate를 별도로 충족해야 한다.

main 이력 정리 이후의 재개 상태는 [HANDOFF](HANDOFF.md)를 따른다. 최적화 설명 통합은
당시 문서-only 변경이었고, 현재 구현은 **`M31-MEM-OPT`**에서 P0·P1을 마친 뒤
P2 실기와 오류 진단을 진행 중이다. 현재 P2 결과·잔여 조건은 [M31 TODO](TODO_M31.md)에 기록한다.
[250번 native RAS 비교·DF 재진단](<04_검증 기록/250_M31_P2_native_CS_비교와_DF_재진단.md>)도
P2의 미완료 조건을 유지한다. Nordic 계측 RAS에서도 gap이 관찰됐지만,
Arduino의 모든 누락과 DF connectionless fault가 해결된 것은 아니다.
[251번 CoC 재연결](<04_검증 기록/251_M31_P2_CoC_재연결_메모리_계측.md>)은
두 채널 512 B echo, 명시적 ACL 재연결 20/20과 서버 SWD reset 20/20을
추가로 통과했지만 물리 전원 차단·controller 내부 사용 최고치는 별도다.
[252번 CS 장절차](<04_검증 기록/252_M31_P2_CS_장절차_반복계수_경계_진단.md>)는
진단 image 두 가지에서 raw 각 10건을 통과했지만 실제 최대 98 step이라
당시 분할 RAS·256-step 용량 검증을 닫지 못했다. 후속
[255번 진단](<04_검증 기록/255_M31_P2_CS_256_step_분할_RAS_진단.md>)에서는
실제 256-step·분할 RAS 정상 경로 10/10을 확인했으나 같은 image의
100건에는 counter gap 1이 남아 CS/P2 전체는 HOLD다.
[256번 DF 대기 취소 진단](<04_검증 기록/256_M31_P2_DF_sync_대기_취소_진단.md>)도
connectionless sync timeout·IQ 0·수신 bus fault를 보존했고,
기본 CS image 복구 뒤 양측 STOP을 확인했다. 공개 DF RX는 미완료다.
[253번 Audio broadcast 재가입](<04_검증 기록/253_M31_P2_Audio_broadcast_재가입_메모리_계측.md>)은
source SWD reset 뒤 sink 명시적 재가입 20/20과 drop 0을 확인했으나
최초 sync 실패와 다른 역할·부하의 최악값은 별도다.
[254번 Audio unicast 재연결](<04_검증 기록/254_M31_P2_Audio_unicast_재연결_메모리_계측.md>)은
adaptive source 재연결 scan 결함을 수정하고 source SWD reset 20/20,
sink 누적 decode 2,933·drop 0을 확인했다. 앞선 실패 두 건과 다른
방향·다중 ASE·최악 부하는 별도이므로 P2 완료로 승격하지 않는다.
2026-09-25 후속 [CoC 송신 버퍼 포화](<04_검증 기록/257_M31_P2_CoC_송신_버퍼_부하와_복구.md>)는
네 SDU 전송 뒤 `busy`와 복구 20/20×2를, [Audio 양방향](<04_검증 기록/258_M31_P2_Audio_양방향_장시간과_종료_복구.md>)은
각 10,000 LC3 frame·drop 0과 즉시 종료 20/20을 확인했다.
[DF 지원 경계](<04_검증 기록/259_M31_P2_DF_고정_SDK_지원_경계.md>)상
고정 NCS `v3.4.0`의 nRF54L15 제품 수신은 AoA 송신 전용 지원 범위 밖이며,
[CS 장시간](<04_검증 기록/260_M31_P2_CS_누락_분류와_256_step_장시간.md>)은
256-step 유효 raw 1,000건의 gap 3과 기본 image 복구 100건의 gap 1을
보존한다. 이 결과는 P2 전체 완료·메모리 축소·릴리스 승인이 아니다.

이후 구현 순서는 **메모리 최적화 → W04·W05 → W06 → W07 → W08·Windows 릴리스 준비**다.
**HOST-W04~HOST-W08은 사용자 지시로 계속 보류**하며 이번 문서 작업에서 재개하지 않는다.

| 정보 | 단일 원본 |
| --- | --- |
| M28~M45 순서·전체 상태 | [제품 로드맵](<01_아두이노 코어 설계/02_구현_로드맵.md>) |
| BLE 기능군별 목표·완료 조건 | [경쟁 마일스톤](<01_아두이노 코어 설계/08_전_인스턴스_DMA_BLE_경쟁_마일스톤.md>) |
| v0.5.0 착수 체크·결정 상태 | 이 문서 |
| 재개 복구·Adafruit 개선 과제의 배치 | [개정 실행 순서](<01_아두이노 코어 설계/18_문서_전면검토와_개선_마일스톤.md>) |
| M28 API·자원·시험 계약 | [M28 착수 계약](<01_아두이노 코어 설계/15_M28_BLE_GAP_Link_Privacy_착수_계약.md>) |
| M28 기계 판정 원본 | [`m28-ble-readiness.json`](../variants/nu54dk/m28-ble-readiness.json) |
| M29 API·정책·자원·시험 계약 | [M29 착수 계약](<01_아두이노 코어 설계/16_M29_ATT_GATT_L2CAP_착수_계약.md>) |
| M29 기계 판정 원본 | [`m29-ble-readiness.json`](../variants/nu54dk/m29-ble-readiness.json) |
| M30 보안·OOB·profile·DFU 계약 | [M30 착수 계약](<01_아두이노 코어 설계/17_M30_BLE_Security_Profile_DFU_착수_계약.md>) |
| M30 기계 판정 원본 | [`m30-ble-readiness.json`](../variants/nu54dk/m30-ble-readiness.json) |
| M31 실행 TODO | [M31 TODO](TODO_M31.md) |
| M32 최신 LE·Mesh·공존 TODO | [M32 TODO](TODO_M32.md) |
| 후속 버전 M33 전체 예제·상호운용·공개 TODO | [M33 TODO](TODO_M33.md) |
| 기능별 upstream·제공 경로·예제·검증 | [전체 Bluetooth 기능 실행 계약](<01_아두이노 코어 설계/19_NCS_Bluetooth_전체_기능과_예제_실행_계약.md>) |
| 후속 다중 Host 계약·v0.5.0 Windows 경계 | [다중 Host 지원 착수 계약](<02_빌드 설계/10_v0.5.0_다중_Host_지원_착수_계약.md>) — 기존 파일명 유지 |
| v0.4.0 완료·보존할 지원 계약 | [v0.4.0 완료 TODO](TODO_v0.4.0.md) |
| M28~M30 완료 근거 | [검증 기록 목차](<04_검증 기록/README.md>)의 milestone별 완료 기록 |
| M31 W02 / W03 완료 근거 | [ISO 설치본](<04_검증 기록/199_M31_W02_격리_설치본_ISO_11예제와_완료.md>) · [LE Audio 11/11](<04_검증 기록/214_M31_W03_LE_Audio_Profile_완료.md>) |

## 1. 다음 착수 순서

### 현행 순서 — 2026-09-21 릴리스 분리

사용자 목표는 **고정 NCS v3.4.0에서 nRF54L15가 할 수 있는 Bluetooth 기능과 예제를 NU54DK의
Arduino 환경에서 사용할 수 있게 하는 것**이다. 구현 방식은 wrapper/direct/profile/template 중
기능에 맞게 정하고 upstream sample·역할·test ID를 전수 추적한다. 이 장기 목표를 한 릴리스에
모두 넣지는 않는다. v0.5.0에는 M28~M31의 검증된 범위만 포함하고, M32/M33은 후속 제품선으로
유지한다. 계획 문서 작성은 구현 완료에 포함하지 않는다.

| 트랙 | 작업 분모·현재 완료 | 다음 구현과 역할 |
| --- | --- | --- |
| M31 / v0.5.0 | **3/8** | W01~W03 완료. 메모리 최적화 → W04 DF·W05 CS → W06 독립 image 자원·수명주기·회귀 → W07 설치 예제 → W08 마감·Windows 릴리스 준비. 네 기능 전체 동시 실행은 요구하지 않음 |
| M32 / 후속 버전 미정 | **0/12** | W01~W05 최신 LE/Nordic, W06~W08 Mesh/1.1/DFU, W09~W10 단독 radio/공존, W11~W12 회귀·마감 |
| M33 / 후속 버전 미정 | **0/8** | W01~W04 catalog·GATT/beacon·ecosystem·HCI/DTM, W05~W06 예제/통합, W07~W08 후속 Host·RC·공개 |
| Host | **3/8, 보류** | HOST-W01~HOST-W03 완료. 재개 후 HOST-W04 prerequisite·HOST-W05 path/cache부터 진행 |

메모리 최적화의 측정·상위 gate는 [219번 계약](<04_검증 기록/219_M31_W06_메모리_점유_감사와_최적화_계약.md>),
기능 선택·Kconfig/source/link·정적 pool·계측의 수정 방법과 이전 설명 정정은
[통합 설계](<01_아두이노 코어 설계/21_M31_메모리_최적화_통합_설계.md>)를 따른다.
목표 기본 경로는 사용자 선언과 필수 의존성만 포함하는 nRF native 수준의 구성에 우리 API의 최소
필수 비용을 더하는 구조다. full은 명시적 호환 선택지로 보존하고 실제 절감량은 동등 조건에서 검증한다.
W04·W05를 먼저 마감한 뒤 최적화하는 순서는 폐기한다. 기존 evidence를 유지하고 최적화된
image에서 잔여와 영향 재검증을 닫는다. W04·W05의 독립 구현·분석은 병행할 수 있지만 같은
probe/보드를 동시에 점유하지 않는다. 추가 외장 장치 확보는 자동 가능한 구현·검사의 선행조건이 아니다.
M31 8/8과 Host 3/8은 독립 집계하며, v0.5.0 Windows 릴리스 준비는 M31-W08이 소유한다.
사용자가 보드 3개 연결을 확인했다. 실제 mapping은 재검증하며, 정밀 RF·음질·거리/각도 보정은
필수 gate 밖으로 변경한다. 보드 기반 실제 데이터·보안·복구 검증은 계속 필수다.

### 최종 사용자 결정 — 구현과 실물 검증의 책임

| 범위 | 개발에서 반드시 완료할 일 | 실제 운용·실물 검증과 v0.5.0 gate |
| --- | --- | --- |
| Apple/Google 등 외부 ecosystem/peer | 신규 기능·예제는 후속 M33-W03 소유. 채택 기능의 설정·credential·가능한 자동 검사는 담당 단계에서 필수 | 실물은 사용자 후속 NOT RUN. M33 기능을 v0.5.0 지원으로 안내하지 않으며 검증된 상호운용 주장 금지 |
| 마이크·스피커·외장 장치 | 실제 연결해 사용할 API·설정·예제·연결 안내와 가능한 자동 검사; 합성 보드 경로 검증 | 외부 장치의 실제 운용·호환성은 사용자 후속. 개발·공개 차단 아님 |
| DF 원시 IQ | 기본 SDC TX와 Zephyr LL RX 후보 구분, 배열 없이 수신 구성 조사·build·적용 가능한 2보드 HIL | 장비 대기가 아닌 소프트웨어 지원성/기능 판정. 각도 산출·실제 안테나 전환은 별도 외장 경로 |
| Ubuntu/macOS 사용자 Host | 후속 Host 트랙에서 prerequisite·launcher/resolver·설치 도구·자동 검사와 검증 절차 구현; 현재 보류 | 해당 OS를 포함하는 후속 릴리스에서 사용자 실물 gate 유지. Windows-only v0.5.0을 차단하지 않음 |

세 보드의 USB 접근·명확한 mapping을 전제로 추가 부품 연결을 중간 선행조건으로 요구하지 않는다.
이는 지원되는 기능의 실제 자동 HIL이나 결함 수정을 면제하는 결정이 아니다. 사용자 후속 실기,
기술적 미지원, 미해결 결함을 다른 상태로 기록한다. 상세 원본은 [전체 기능 계약](<01_아두이노 코어 설계/19_NCS_Bluetooth_전체_기능과_예제_실행_계약.md>)이다.

### 보존하는 M28~M30 기준선

| 완료 milestone | 최종 상태 | 계약·실기 원본 |
| --- | --- | --- |
| M28 GAP·Link·Privacy | W01~W08 8/8, test ID 9/9 | [계약](<01_아두이노 코어 설계/15_M28_BLE_GAP_Link_Privacy_착수_계약.md>) · [140번 완료 기록](<04_검증 기록/140_M28_W07_3보드_HIL과_W08_완료.md>) |
| M29 ATT/GATT·L2CAP | M29-W01~W08 8/8, test ID 10/10 | [계약](<01_아두이노 코어 설계/16_M29_ATT_GATT_L2CAP_착수_계약.md>) · [149번 완료 기록](<04_검증 기록/149_M29_W07_3보드_회귀_상호운용과_W08_완료.md>) |
| M30 Security·Profile·DFU | M30-W01~W08 8/8, test ID 10/10, 실제 전원 차단 12/12 | [계약](<01_아두이노 코어 설계/17_M30_BLE_Security_Profile_DFU_착수_계약.md>) · [161번 완료 기록](<04_검증 기록/161_M30_W08_실제_전원_HIL과_M30_완료.md>) |
| Host 공통 기반 | HOST-W01~HOST-W03 3/8 | [151번 기록](<04_검증 기록/151_M30_W01_계약과_HOST_W01_W03_기반.md>) |

단계별 exact source·시도·수치는 위 원본과 각 readiness에서 관리한다. 완료 내역을 이 TODO에
반복 복사하지 않는다. P01~P06은 완료한 M28 준비 체크이며 새 작업 분모가 아니다.
M28-CAP-01의 실제 HCI 6/6 PASS와 정적 source candidate는 별도 상태로 보존한다.
M29 Signed Write는 deprecated legacy opt-in, EATT는 experimental opt-in이다.
Windows/Intel 기본 GATT 상호운용 PASS는 모든 OS/adapter의 EATT·cache 지원을 뜻하지 않는다.
M30 NFC adapter는 구현·Host/target build를 통과했고 RF는 사용자 결정대로 `NOT RUN`이다.
M30 전원 차단은 exact `ae5186f7790a748641fb04128c16156519ee1017`의 네 지점 × 3회이며,
reset 대체·mass erase 없이 recovery failure·invalid image boot 0을 확인했다.

## 2. 현재 확인된 지원성 결정 항목

아래 표는 고정 NCS v3.4.0의 source 상태와 프로젝트의 결정·실기 결과를 구분한다.
SDK나 controller/profile을 바꾸면 해당 판정과 관련 회귀 범위를 다시 확인한다.

| 대상 | 고정 SDK의 상태 | 현재 결정·남은 사항 |
| --- | --- | --- |
| M29 Signed Write | Zephyr host `BT_SIGNING`은 `DEPRECATED` | 기본 OFF의 `NUCODE_BLE_LegacySigning`, legacy opt-in으로 구현. CSRK/counter 영속화·replay 거부와 통합 회귀 PASS |
| M29 EATT | Zephyr host `BT_EATT`는 `EXPERIMENTAL` | 기본 OFF의 `NUCODE_BLE_EATT`, experimental opt-in으로 구현. 암호화·2 bearer 부하와 통합 회귀 PASS; 안정 API로 승격하지 않음 |
| M31 방향탐지 | 기본 SDC의 CTE 송신은 AoA 지원·AoD 미지원. 전체 RX/IQ 경로 지원을 뜻하지 않음 | 송신·수신·안테나 전환을 분리해 controller/profile 적용성 판정. 대체 Zephyr LL은 별도 후보이지 검증 완료 대안이 아님 |
| M31 Audio 확장 | W03의 11개 profile/data 하위 작업을 공개 Arduino 예제와 보드 HIL로 완료 | [214번](<04_검증 기록/214_M31_W03_LE_Audio_Profile_완료.md>)의 역할별 적용성·한계 유지. 외장 audio·상용 peer 실물은 사용자 후속 NOT RUN |
| M32-A 최신 LE | 고정 SDC의 power/path loss·subrating·SCA·frame space·shorter interval·extended feature set 및 Nordic 확장 | M28의 기존 6개 capability PASS와 구분해 W01~W05에 신규 구현·예제·negative 배정 |
| M32-A EAD/coding·자원 | EAD Host source·광고 coding 설정, nRF54L15용 multi-set/identity 예제 존재 | EAD/coding은 적용 build·runtime 확인 전 candidate; 1 advertising set 기본값과 확장 preset 분리 |
| M32-B Mesh 1.1 | Remote Provisioning·SAR·Opcode Aggregator·Large Composition·Private Beacon/Proxy·Solicitation·Subnet Bridge source 존재 | node/model 역할·RRAM/RAM·BLOB/DFU/Distribution과 함께 W06~W08에서 검증 |
| M32 공존 | 802.15.4/ESB와 BLE 병행시험에는 동작하는 단독 radio 경로가 먼저 필요 | M32 안에서 최소 검증용 기반·단독 TX/RX를 확보하고, M38/M39는 공개 API·예제·일반 제품화 확장으로 연결 |
| M33 외부 ecosystem·진단 | Fast Pair·ANCS/AMS·HCI/DTM 예제별 peer/credential/transport 전제 존재 | template/direct 제공, 외부 행 NOT RUN 명시; BR/EDR·nRF54L15 비대상 nrf_dm는 비적용 근거 기록 |

정적 근거는 NCS checkout의 `zephyr/subsys/bluetooth/host/Kconfig` (`BT_SIGNING`),
`zephyr/subsys/bluetooth/host/Kconfig.gatt` (`BT_EATT`),
`nrf/subsys/bluetooth/controller/Kconfig`와 `nrfxlib/softdevice_controller/README.rst`다.
고정 환경은 [CI lock](../tools/ci/ncs-3.4.0.lock.json)을 따른다.
[Nordic SDC v3.4.0 지원 명세](https://github.com/nrfconnect/sdk-nrfxlib/blob/v3.4.0/softdevice_controller/README.rst)를
함께 확인하며, 다른 버전의 웹 문서로 고정 SDK의 판정을 덮어쓰지 않는다.

## 3. 기존 구현과 신규 작업의 구분

| 단계 | 유지·회귀할 기존 기능 | 신규 설계·검증할 범위 |
| --- | --- | --- |
| M28 | 단일 링크 GAP, 기존 PHY 갱신·MTU 교환, 광고·스캔·연결 수명주기 | per-link GAP handle/event/control, multi-role/link, 확장·주기 광고·PAwR, privacy |
| M29 | 기존 GATT server/client·read/write/notify/indicate | long/reliable·descriptor/cache·CoC, 별도 정책을 정한 signed write/EATT |
| M30 | 기존 IO capability·LE Secure Connections·pairing/bond API와 BAS/DIS/HID keyboard | OOB·key 정책·migration·추가 profile, 최소 BLE DFU·서명·복구 |

연결 수 Kconfig만 늘려 multi-link 구현으로 처리하지 않는다. 기존 singleton 사용 Sketch의
동작과 오류 의미를 보존하는 방법을 정하고, 각 연결의 소유권·버퍼·해제·재접속 상태를 검증한다.
이 표의 기존 기능은 원래 검증 범위의 재사용 대상이지 신규 조합의 PASS가 아니다.

## 4. M28~M33 실행 묶음과 후속 인계

| 단계 | 구현·검증 순서 | 다음 단계에 넘길 산출물 |
| --- | --- | --- |
| M28 | 지원 원장 → per-link 계약 → GAP/link/privacy 확장 → 다중 peer HIL | 고정 capability/profile·연결/자원 한계·회귀 목록 |
| M29 | GATT/CoC → signed write/EATT 정책 적용 → 오류·상호운용 | client/server·cache·credit·실험/legacy 제약과 시험 근거 |
| M30 | 보안/profile → 최소 boot/layout·서명·BLE update → 실패 복구 + HOST-W01~HOST-W03 | M34~M36이 재사용할 보안 계약과 Host 공통 backend·Windows 전용 가정 inventory |
| M31-A | ISO/CIS/BIS·combined/time sync → LC3·전체 Audio profile → 합성 데이터/제어 HIL | stream/buffer·codec·역할별 짝 예제·미지원/외부 I/O 미검증 행 |
| M31-B | controller 적용성 → CTE TX와 배열 없는 raw IQ 수신 후보 조사/build·적용 HIL; AoD 개별 판정 | TX/RX 증거 깊이, 고정 Zephyr LL 후보의 실제 결과, SDC AoD 미지원·각도/전환 후속 경로 |
| M31-C | Connected ACL·CS/RAS·raw 결과/거리 산출 → security/peer loss/recovery | 기능 동작 근거; 정밀 거리 보정·정확도는 필수 밖 |
| M32-A | power/path loss → timing/subrate → adv/EAD/identity/resource → Nordic LLPM/QoS/event | 새 자원 preset·실험적 opt-in·짝 예제·2/3보드 기능/negative |
| M32-B | Mesh 기본 → Mesh 1.1 → BLOB/Mesh DFU/Distribution | node/model·key/settings·transfer·복구, 내부 RRAM/배포자 한계와 M36 인계 |
| M32-C | 최소 radio/profile·802.15.4/ESB 단독 TX/RX → 선택 공존·복구 | MPSL ownership·loss/서비스 지연·M38/M39 공개 예제 인계 |
| M31 릴리스 | 메모리 최적화·W04~W08 → Windows 패키지·clean 설치·RC → 별도 승인 후 v0.5.0 공개 | M28~M31 채택 범위·image/자원·예제·지원/제약·설치 수명주기 근거 |
| M33 / 후속 버전 | GATT/beacon·ecosystem·HCI/DTM 예제 → 전체 parity·interop → HOST-W08/RC → 후속 공개 | 누락 0 원장·예제 제공 범위·실행 증거·세 Host 지원/제약·qualification 적용성 |

M31-A/B/C는 **M31 내부 작업 ID**다. 하나를 완료해 M31 전체 완료로 계산하지 않는다.
M30 최소 DFU에서는 고정 layout·신뢰키·초기 설치·BLE 갱신·전원 차단 복구와 Arduino 제공 형태를
별도 `secure_ble_dfu` profile에 고정했다. 기본 `--no-sysbuild` build·native HEX upload를 그대로 MCUboot 지원으로 간주하지
않으며, 기본 loaderless 경로는 유지한다. M36은 다중 layout/transport와 hardening 확장이다.

M42 시작 전에는 사용할 Matter transport, Thread 선택 시 M40의 network 근거, M32의 적용 공존
조합, update 경로, RAM/RRAM·저장소 예산과 개발용/생산용 credential 정책을 연결한다.
NU54DK의 외장 flash 미탑재와 factory-data partition 적용성은 설계 입력이며 Matter 불가능 판정이 아니다.

M33의 사용자 경로 정리에 기존 API만 사용하는 ARF-04A 목적별 예제를 연결한다.
Buffered NUS·PWM pool·별도 편의 API는 M30/M33 필수 구현에 합치지 않고
[별도 개선 작업](<01_아두이노 코어 설계/18_문서_전면검토와_개선_마일스톤.md>)으로 검증한다.
BLE role-budget ARF-01은 M32-W04로 통합해 기본 2-link 및 확장 역할 preset과 한 번 검증한다.
후속 배포 버전은 착수 gate에서 확정하며 기존 M34~M45 제품선을 임의 재배치하지 않는다.

## 5. 장비와 정량 판정 기준

### 장비 확보 상태

**NU54DK 3개와 독립 DAP/UART 3경로를 2026-09-13 W07에서 확인**했다. M28 packet 분모는 세
UART와 수신측 GATT/periodic sequence·payload hash를 같은 nonce로 결합했다. 외부 sniffer와
Android/iOS/Linux cross-vendor matrix는 M28/M29 PASS에 포함하지 않는다. Windows/Intel은 M29의
기본 GATT 상호운용만 PASS했고 EATT·robust caching이나 모든 adapter 지원을 뜻하지 않는다.

| 시험군 | 계획상 필요한 구성 | 착수 시 확인할 사항 |
| --- | --- | --- |
| BLE 기본·multi-link | NU54DK 2~3개와 수신측 sequence/hash | probe SHA-256·serial·role·revision; OS peer는 별도 M33 행 |
| ISO/LE Audio | 2보드 송수신, 3보드 source/sink/assistant 또는 broadcast; 합성 PCM/LC3 | 실제 SDU·codec·제어·buffer/복구, 외부 microphone/speaker/codec는 별도 미검증 행 |
| Direction Finding | CTE TX 1보드와 내부 Zephyr LL 연결 IQ 20 report·1,640 sample은 국소 확인 | SDC 공개 RX는 미제공. Connectionless LL은 연속 CTE 송신에도 sync 미수립·IQ 0이며 cleanup fault를 보존했다. 공개 API·각도/전환은 별도. [연결형 244](<04_검증 기록/244_M31_P2_DF_연결_IQ_진단.md>) · [connectionless 247](<04_검증 기록/247_M31_P2_DF_connectionless_재진단과_보류.md>) |
| Channel Sounding | CS initiator/reflector 2보드, 선택 3번째 peer | procedure/RAS·결과·보안·재연결 기능; 정밀 거리·방향 보정 요구 없음 |
| Mesh/coexistence | 승인 topology의 2~3노드, BLE/802.15.4/ESB traffic 관측 | 역할별 노드 수·단독 통신·조합·부하·서비스 지연; 새 power-loss 확장은 M36 후속이며 v0.5.0 추가 필수 gate 아님 |

사용자가 제외한 정밀 계측은 `out_of_scope_by_user_decision`, 사용자 후속 외장/상호운용 실기는
`NOT RUN`과 후속 책임·비차단 범위를 함께 기록한다. DF RX의 경로별 미완료·실패는
별도 기술 상태이며 장비 부족 또는 `UNSUPPORTED`로 자동 분류하지 않는다. 고정 controller의
실제 비지원은 근거와 함께 기록한다. 3보드 결과를 더 큰 topology의 PASS로 확대하지 않는다.

Android/iOS/Linux 항목은 **BLE 상대 장치 상호운용**이며 Arduino Core 개발·설치 Host matrix와
서로 다른 시험이다. v0.5.0 Host 범위는 Windows 10/11 x64다. Ubuntu 24.04 이상 AMD64와
macOS 26 이상 Apple Silicon은 [후속 Host 계약](<02_빌드 설계/10_v0.5.0_다중_Host_지원_착수_계약.md>)으로
유지한다. Peer 자체 미지원은 근거와 함께 비적용으로 분리한다. 실제 외부 peer 시험은 사용자
후속·비차단이며, 해당 OS를 지원하는 후속 릴리스의 필수 Host 실기와 구분한다.
Ubuntu/macOS Host 실기는 사용자 검증 전까지 `NOT RUN`이다. 원장의 `final_release`·
`release_blocker=true`는 해당 OS 지원 선언의 gate이지 v0.5.0 Windows 공개 gate가 아니다.

### 실행 전에 고정할 합격표

M28 GAP/multi-link 9개와 M29 ATT/GATT·L2CAP 10개 test ID를 모두 확정·실행했다.
M30은 [착수 계약](<01_아두이노 코어 설계/17_M30_BLE_Security_Profile_DFU_착수_계약.md>)의 10개 test ID와 수치가 확정됐다.
M31~M33 TODO의 시험 ID·계획 기준은 구현 시 계약/기계 원장에 고정한다. W01에서 역할별
설정·하위 case·숫자·단위·계산식·관측 수단·최대 시간을 확정한 뒤 실행한다. 계획 수치는 성능
보증이나 실제 PASS가 아니다. `장시간`, `안정적`, `저지연`만으로 합격 기준을 대신하지 않는다.

| 시험군 | 반드시 고정할 입력 | 수치·판정 항목 |
| --- | --- | --- |
| GAP/multi-link | 연결 수·역할·PHY·MTU/DLE·interval·전송률·환경 | reconnect 반복 수·timeout, 요청/실제 연속 시간, 송수신 분모·허용 loss/중복/순서 오류, 자원 복구 기준 |
| GATT/CoC/EATT | value/MTU·channel/credit 수·동시 부하·malformed 입력 | payload 일치, 오류 종류·횟수, 최대 서비스 지연·복구 timeout, leak 판정 |
| Security/DFU | IO/OOB·key 정책·서명·image/layout·중단 주입 지점 | 거부해야 할 입력·예상 오류, 전원 차단 반복 수·부팅/복구 timeout, rollback·데이터 보존 기준 |
| ISO/Audio | codec/profile·SDU·buffer·clock·부하 | loss 분모·허용률·sequence/payload·codec 완료·underrun/overrun·복구 시간; 관측 가능한 지연은 측정법과 함께 기록 |
| DF/CS | 역할·controller·CTE/CS procedure·결과 형식·환경 | command/결과 수·유효성·보안 실패·연결 복구; RF 각도/거리 절대 오차와 보정은 필수 밖 |
| Mesh/coexistence | topology·model·동시 조합·각 protocol 부하 | 전달률·서비스 지연 상한·starvation 판정, power-cycle 수·복구 timeout·soak 시간 |

각 test ID에는 최대 실행 시간·반복 수·오류 중단 조건·진단 후 동일 조건 재검증 횟수도 고정한다.
실패는 원인·수정·동일 조건 재검증을 연결하며 무한 재시도로 통과를 만들지 않는다.
통신 손실과 관측 가능한 software 지연·복구 허용치는 기능별 측정법과 함께 고정한다.
모든 주변장치 조합이나 정밀 RF·음질·거리/각도 계측 품질을 일괄 보증하지 않는다.
v0.4.0의 범위 제외는 그대로 보존한다.

## 6. 결과·공개 규칙

- M28·M29·M30의 capability·구현·Host·target·유한 HIL·문서 인계를 완료했다.
  M31~M33과 v0.5.0 공개는 완료 처리하지 않는다.
- 구현·Host·build·실기·상호운용·공개 결과를 분리하고 exact source/profile·조건·raw log를 연결한다.
- 적용 가능한 필수 기능은 증거가 있어야 완료한다. 기능 제외·보증 범위 축소·SDK 교체가 필요하면
  별도 범위 결정으로 기록하고, 조용히 삭제하거나 성공으로 바꾸지 않는다.
- 2026-09-16 결정의 정밀 RF/audio/거리/각도 계측 제외는 유지한다. 이번 2026-09-21 개정은
  릴리스 시점·범위를 M31 Windows로 분리하며 기능 PASS를 추가하지 않는다.
  전체 NCS Bluetooth 기능·예제를 명시한 단계에 배치했다. M31-W01 inventory·readiness·
  capability parser/target의 clean HCI query, parity 703행·negative 20/20으로 W01을
  완료했다. W02 clean CIS·BIS 전체 positive/negative·time sync와
  [combined 세 보드 20회×100](<04_검증 기록/166_M31_W02_3보드_CIS_BIS_통합_실기.md>)은 PASS이며
  독립 개발 package의 설치 Arduino ISO 11예제 빌드·역할별 실기도 완료했다.
  [W02 최종 기록](<04_검증 기록/199_M31_W02_격리_설치본_ISO_11예제와_완료.md>)과
  [W03 LE Audio 11/11](<04_검증 기록/214_M31_W03_LE_Audio_Profile_완료.md>)까지 완료했다.
  DF·CS 및 독립 image별 자원·수명주기·회귀·예제·마감은 잔여다. ISO·Audio·DF·CS 네 기능
  전체를 한 MCU에서 동시에 실행하는 것은 M31 완료 조건이 아니다.
- 외장 Audio 경로는 M31, Apple/Google 신규 기능은 후속 M33의 채택 범위에서 구현·예제·
  가능한 자동 검사를 완료한다. 실물 운용·상호운용은 각 담당 제품선에서 사용자 후속·비차단으로
  유지하며, 그 NOT RUN은 PASS가 아니다.
  원장의 구현 요구·검증 책임·개발/공개 차단 여부를 독립 필드로 구현해 이 구분을 검사한다.
- 문서상의 기능 계획과 Bluetooth/Matter 제품 인증 취득은 별개다.
- v0.4.0·v0.4.1 공개 승인은 v0.5.0 공개 승인이 아니다. M31-W08에서 exact 결과·자산 기준으로
  v0.5.0 Windows 공개 준비를 관리하며, 실제 tag/Release/catalog 공개는 별도 사용자 승인을 받는다.
- 이후 세 Host를 지원하려면 각 OS에 clean 설치·채택된 전체 예제 build·대표 upload/runtime·
  수명주기 증거가 있어야 한다. 후속 OS gate를 삭제하거나 자동 PASS로 올리지 않는다.
- 다음 작업 보고에는 완료 범위·현재 항목·남은 항목과 **해당 작업의 분모**를 적는다.
  P 준비 체크, M28~M33의 6개 마일스톤, v0.4.0의 T13 분모 58을 섞지 않는다.

### v0.5.0 공개 gate — 기능 8/8과 별도 판정

- [ ] 메모리 최적화와 M31-W01~W08 8/8, 적용 가능한 필수 board-only HIL·M19~M30 영향 회귀 완료
- [ ] M28~M31 채택 API·예제·profile·자원 상한·지원표·known limits와 readiness/parity 정합
- [ ] 고정 SDK·board·toolchain과 exact release source의 Windows 패키지·manifest/hash·라이선스 검사
- [ ] clean Windows 설치에서 채택된 전체 예제 발견·compile, 대표 upload/runtime·serial/debug 확인
- [ ] Windows upgrade/reinstall/uninstall/cache 수명주기와 오류 복구 검사, 과거 지원 버전 이동 안내
- [ ] RC 결과·회귀·사용자 후속 NOT RUN·미지원 경계를 검토하고 별도 공개 승인 확보
- [ ] 승인된 exact 자산으로 tag/Release/catalog 공개, 실제 다운로드·설치 smoke와 배포 문서 확인

위 항목은 아직 완료로 표시하지 않는다. 문서 정비나 브랜치 준비는 패키지 제작·공개 실행이
아니다. 준비 산출물은 M31-W08이 소유하되 기능 완료와 실제 배포 결과를 따로 보고한다.
