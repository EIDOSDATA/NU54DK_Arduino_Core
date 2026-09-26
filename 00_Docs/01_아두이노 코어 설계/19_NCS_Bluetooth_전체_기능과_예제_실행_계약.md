# NCS Bluetooth 전체 기능과 Arduino 예제 실행 계약

| 항목 | 계약 |
| --- | --- |
| 목표 | 고정 NCS `v3.4.0`에서 nRF54L15에 적용 가능한 Bluetooth 기능·예제를 NU54DK Arduino 환경에서 사용할 수 있게 한다 |
| 대상 | 개발 source `0.4.1-dev`의 M31 `v0.5.0` Windows 릴리스와 M32·M33 후속 기능(버전 미정), M34~M45 인계 의존성 |
| 현재 상태 | **M31 W01~W08 완료 8/8**. W02 설치본 ISO 11예제·11역할, W03 Audio 11/11, W04 DF·W05 CS·W06 자원/회귀·W07 예제/HIL·W08 Windows RC 준비 완료. M32·M33은 미착수 |
| 장비 입력 | 사용자가 NU54DK 3개 연결·보드만 보유한다고 확인. 실제 시험 전 identity·serial·role·firmware를 다시 대조 |
| 기능 검증 범위 | 예제의 실제 송수신·제어·보안·오류 복구와 Arduino 사용성. 합성 데이터·합성 PCM을 사용할 수 있음 |
| 범위 제외·후속 | 정밀 RF·거리/각도·음질 보증은 범위 밖. Apple/Google와 외장 I/O 실물 운용·검증은 사용자 후속이며 개발·릴리스 필수 gate가 아님 |
| 최종 갱신일 | 2026-09-27 |

전체 번호·제품선은 [제품 로드맵](02_구현_로드맵.md), 작업 묶음은 [M31 TODO](../TODO_M31.md),
[M32 TODO](../TODO_M32.md), [M33 TODO](../TODO_M33.md), 현재 상태는
[v0.5.0 TODO](../TODO_v0.5.0.md)가 관리한다. 이 문서는 구현할 기능·예제의 세부 범위와 누락 방지
계약을 소유한다. 기존 [NCS API matrix](06_NCS_3.4.0_기능과_예제_지원_매트릭스.md)는 현재 공개 지원표이며
이 계획 문서와 상태를 구분한다. `coverage/generated` 등 생성 문서는 해당 원본·생성기를 갱신하고
재생성하며 생성 Markdown을 수작업으로 수정하지 않는다.

완료 근거는 [M31 readiness](../../variants/nu54dk/m31-ble-readiness.json)와
[W03 완료 감사](<../04_검증 기록/214_M31_W03_LE_Audio_Profile_완료.md>)다. Host는 W01~W03 완료
3/8이고 **W04 이후는 사용자 지시로 보류**다. 아래 범위·병행 계획은 재개 지시 후 적용한다.

### 2026-09-21 릴리스 범위 결정

`v0.5.0`은 완료한 M31을 기준으로 Windows 우선으로 릴리스한다. M31-W08에서 해당 버전의 재현
package·Windows 설치 수명주기·RC 준비를 완료했다. 이후 공개 `v0.5.0-rc.1` 승인·게시·다운로드
smoke까지 [268번 기록](<../04_검증 기록/268_v0.5.0-rc.1_공개와_다운로드_smoke.md>)에서 닫았으며 정식 stable gate는 별도다.
M31 기능 8/8과 릴리스 판정은 별도 집계한다. `M31-MEM-OPT`에서 메모리 최적화
P0·P1·P2를 완료했다. P2의 지원 범위 오류·최악 부하,
stack/heap 안전 여유·최종 크기, 동일 조건 Nordic native FLASH/RAM 비교는
[262번](<../04_검증 기록/262_M31_메모리_최적화_P2_세_축_완료.md>)이 소유한다.
SDK/controller와 standard/full 기본값은 바꾸지 않았다.

M32·M33 추가 기능과 Ubuntu/macOS 확대는 버전 미정 후속 범위다. M33-W07~W08은 후속
다중 Host·RC·공개를 계속 소유한다. 전체 parity 원장의 owner·미착수·NOT_RUN 행을 삭제하지
않고 제품선별 적용 범위로 구분한다. 후속 기능을 v0.5.0 구현 누락으로 계산하지 않는다.
현재 stable `v0.4.1`, 공개 RC `v0.5.0-rc.1`, 개발 source 식별자 `0.4.1-dev`,
M31 8/8·M32 0/12·M33 0/8·HOST 3/8을 구분한다.

### 구현 책임과 실물 검증 gate

이 표는 M31~M33과 Host 문서가 참조하는 **현행 범위 원본**이다. 앞선 계획에서 외부 장치·peer를
일반적인 개발 선행조건으로 적은 문구보다 아래 결정을 우선한다. 구현·예제·자동 가능한 검사를
완료할 의무와 실제 제품·외장 장치 검증의 담당자를 분리하며, 후속 시험을 PASS로 대신 기록하지 않는다.
2026-09-16의 사용자 후속 실물 정책은 유지하되, 각 기능 owner가 속하는 제품선에 적용한다.

| 대상 | 해당 owner 개발에서 반드시 제공할 것 | 실제 운용·검증 담당과 시점 | 해당 제품선의 개발·릴리스 gate |
| --- | --- | --- | --- |
| 보드 기반 Bluetooth 기능 | 사용 가능한 구현·설정·역할별 Arduino 예제·Host/negative·target build·지원 가능한 1~3보드 기능 HIL | 개발 자동화; 실제 시험 전 mapping 재대조 | 적용 필수 기능의 구현·자동 검증은 필수. SDK 제약/미지원/미판정은 근거를 남기고 임의 PASS·제외 금지 |
| Apple/Google 및 외부 제품 ecosystem | 실사용 가능한 기능·예제·설정·credential 입력 안내, 자동 가능한 parser/semantic·build·scripted peer 검증. 빈 stub·문서만 제공 금지 | 실제 운용·제품 상호운용은 사용자 추후 | 구현·예제·자동 검사는 필수. 사용자 후속 실제 제품 시험은 필수 gate에서 제외; `NOT_RUN`·상호운용 미검증 표시는 유지 |
| 마이크·스피커·코덱·센서·외장 장치 | 실제 연결용 adapter/설정·예제·연결 안내와 자동 가능한 검사; 합성 PCM/data의 실제 protocol 경로 검증 | 실물 연결·운용·검증은 사용자 추후 | 구현·예제·자동 검사는 필수. 외장 I/O 실물 시험은 필수 gate에서 제외; `NOT_RUN`과 검증 범위 유지 |
| DF 원시 IQ 수신 | 고정 NCS v3.4.0·nRF54L15 제품 SDC는 AoA 송신만 지원하므로 IQ RX는 `UNSUPPORTED` | P2 범위 제외. 별도 Zephyr LL 진단은 과거 증거로 보존하며 제품 수신 구현 의무로 승계하지 않음 | 안테나 배열 부족이 원인이 아님. SDK/controller 교체는 별도 범위 결정이며 이번 완료 조건이 아님 |
| DF 실제 AoA 각도·안테나 전환 | 적용 가능한 설정·예제·연결 안내와 raw IQ/각도 계산 경계 | 외부 안테나 구성의 실물 운용·검증은 사용자 추후 | 외장 실물 시험은 필수 gate 제외. 정밀 각도 보정·정확도 보증은 범위 밖 |
| Connected Channel Sounding | 기본 안테나의 initiator/reflector·RAS·결과 처리·보안·복구 예제 | 기본 보드 2개로 개발 자동화; 필요 시 세 번째 peer | 지원 경로의 board-only 기능 HIL 필수. 정밀 거리 보정·정확도는 범위 밖 |
| Windows 실제 Host | M31 package 재현성·설치 예제·업로드·serial/debug·설치 수명주기 | M31-W08 릴리스 검증 | v0.5.0 Windows 지원에 필요한 실제 증거 필수 |
| Ubuntu/macOS 실제 Host | 후속 prerequisite·resolver/launcher·path/권한·package·자동 검사·최종 검증 절차 | 해당 OS 지원을 포함할 후속 릴리스 때 사용자가 설치·USB upload·serial·debug·수명주기를 검증 | HOST-W04 이후 보류. M31 Windows 릴리스 비차단; 해당 OS 후속 정식 지원의 최종 실물 gate 유지 |

외부 장치·계정이 없다는 이유로 위 사용자 후속 실물 시험을 다시 개발/릴리스 blocker로 만들지 않는다.
반대로 아직 구현하지 않은 기능의 SDK 결함·자원 제한까지 해결됐다고 선언하는 결정도 아니다.
새롭게 발견한 실제 소프트웨어 제약은 코드·빌드·실행 근거로 조사하고, SDK 교체·기본 controller 변경·
지원 범위 축소가 필요하면 별도 결정으로 다룬다. 이 문서는 그러한 변경을 자동 승인하지 않는다.

## 1. 완료 기준선과 추가 구현의 경계

- stable 설치·지원 버전은 `v0.4.1`이며 공개 RC는 별도 채널이다. RC 기능을 stable 설치본 지원으로 안내하지 않는다.
- M28은 GAP/link/privacy 8/8·test ID 9/9, M29는 ATT/GATT/L2CAP 8/8·10/10, M30은
  security/profile/DFU 8/8·10/10 완료다. 완료 계약과 원본을 유지하고 여기서 추가한 기능의 소유자는
  M31~M33으로 지정한다.
- M30 `M30-POWER-01`의 실제 source `ae5186f7790a748641fb04128c16156519ee1017`,
  **4개 주입 지점 × 3회 = 12/12 PASS**, recovery failure 0, invalid image boot 0은 변하지 않는다.
  NFC adapter의 RF `NOT RUN`과 유선 USB/DAPLink VCOM OOB 경계를 유지한다.
- M28의 2-link, 광고 set 1개, periodic sync 1개 계약은 완료 당시 기준선이다. 더 많은 set/identity/link를
  요구하는 NCS 예제는 M32-W04의 새 자원 profile로 구현·검증한다.
- 지원 기능을 Arduino facade 하나에 모두 넣는 방식으로 제한하지 않는다. 역할별 profile와 직접 API를
  포함해 설치·build·실행 가능한 Arduino 예제를 제공한다. 기본 singleton의 ABI·오류·소유권은 보존한다.
- 설치 Arduino 예제의 `.ino`는 일반 C/C++과 `NUCODE_*` 공개 API 사용 흐름을 보여 준다. Zephyr
  header·type과 `bt_*`, `k_*` 직접 호출은 library 구현 내부에 두고, 개발 마일스톤 식별자는
  공개 API·macro·예제·사용자 출력에 넣지 않는다. 역할 선택은 공개 enum과 Kconfig가 함께 소유한다.
- 데이터 경로 예제는 `.ino`에 payload 생성·송신·수신 처리·종료와 오류 처리를 드러낸다.
  고정 시험 payload와 Serial oracle이 library 내부에서 실행되고 `.ino`가 `begin()`/`poll()`만
  호출하는 경우, 무선 HIL이 통과해도 사용자용 예제와 공개 API 완료로 세지 않는다.

| 재사용할 완료 기능 | 추가 구현·예제로 연결할 범위 | 후속 소유자 |
| --- | --- | --- |
| GAP central/peripheral/observer/broadcaster, 1M/2M/Coded PHY, DLE·MTU·connection parameter | 여러 역할·자원 profile, 지원 feature 교환과 timing/power 제어 | M32-W02~W05 |
| Legacy/extended/periodic 광고·스캔, PAST sender/receiver, PAwR advertiser/scanner | 여러 set/sync, accept/periodic advertiser list, directed advertising, EAD, coding selection | M32-W04 |
| RPA/privacy와 link별 상태 | 여러 local identity, identity별 bond/filter/광고 격리 | M32-W04 |
| Generic GATT server/client, long/reliable read/write, descriptor·authorization·cache | 표준 서비스·client와 외부 ecosystem 예제 | M33-W02~W03 |
| CoC credit/buffer, legacy Signed Write, experimental EATT | OTS transport 및 새 profile 조합의 회귀 | M31-W06, M33-W02·W06 |
| SMP/LESC·IO capability·bond·유선 OOB·BAS/DIS/HID/HRS/ESS | Audio/Mesh/profile별 보안 적용과 예제 catalog 확대 | M31-W03, M32-W06~W08, M33-W02~W03 |
| Secure BLE DFU·서명·rollback·실제 전원 복구 | Mesh DFU transport/배포자와 후속 다중 layout·key 정책 | M32-W08 → M34~M36 |

## 2. 고정 source와 판정 용어

### 조사 기준

[NCS lock](../../tools/ci/ncs-3.4.0.lock.json)을 기준으로 다음 checkout을 조사했다. 로컬 절대 경로는
구현·검증기 입력으로 고정하지 않는다. 실제 작업 때 resolver로 찾은 SDK와 lock revision을 대조한다.

| 근거 | 고정 revision 또는 경로 | 사용하는 정보 |
| --- | --- | --- |
| NCS | `99553055607b2e9885fbc80ccd11fa9da81c2df0` | `nrf/samples/bluetooth`, software maturity, Nordic Host/controller extension |
| Zephyr | `bf801e4e3d19e1ffa76164346480cb7734dd2800` | `zephyr/samples/bluetooth`, Kconfig, 공개 header, Audio/Mesh 구현 |
| nrfxlib | `d4ce5fe1a7d8af29bc01a4e1ddf5540ef65b6a3b` | SDC feature·제한·variant·vendor 명령 |
| Board | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` | NU54DK 실제 DTS·핀·메모리·peripheral 적용성 |

주요 원본은 [SDC 기능·제한](https://github.com/nrfconnect/sdk-nrfxlib/blob/d4ce5fe1a7d8af29bc01a4e1ddf5540ef65b6a3b/softdevice_controller/README.rst),
[NCS software maturity](https://github.com/nrfconnect/sdk-nrf/blob/99553055607b2e9885fbc80ccd11fa9da81c2df0/doc/nrf/releases_and_maturity/software_maturity.rst),
[NCS Bluetooth 예제](https://github.com/nrfconnect/sdk-nrf/tree/99553055607b2e9885fbc80ccd11fa9da81c2df0/samples/bluetooth),
[Zephyr Bluetooth 예제](https://github.com/nrfconnect/sdk-zephyr/tree/bf801e4e3d19e1ffa76164346480cb7734dd2800/samples/bluetooth),
[Host 기능 Kconfig](https://github.com/nrfconnect/sdk-zephyr/blob/bf801e4e3d19e1ffa76164346480cb7734dd2800/subsys/bluetooth/Kconfig),
[Audio Kconfig](https://github.com/nrfconnect/sdk-zephyr/tree/bf801e4e3d19e1ffa76164346480cb7734dd2800/subsys/bluetooth/audio),
[Mesh Kconfig](https://github.com/nrfconnect/sdk-zephyr/blob/bf801e4e3d19e1ffa76164346480cb7734dd2800/subsys/bluetooth/mesh/Kconfig)다.

표에서 `N:`은 `nrf/samples/bluetooth/`, `Z:`는 `zephyr/samples/bluetooth/`를 뜻한다.
`CONFIG_` 접두사는 Kconfig symbol 표에서 생략한다. 예제 이름은 **신규 산출물의 계획 이름**이며
현재 파일의 존재를 뜻하지 않는다. 비슷한 기존 예제가 있으면 새 복사본 대신 해당 예제를 확장하고
원장에 실제 경로를 연결한다.

### 지원·실행 상태

| 판정 축 | 값·뜻 |
| --- | --- |
| Source 발견 | `source_candidate`: 고정 source에 symbol/API/sample가 있음. target 적용성은 아직 별도 |
| Upstream nRF54L15 근거 | sample의 `platform_allow`, `integration_platforms`, board overlay 및 maturity를 각각 저장. 명시가 없으면 `null` 또는 미판정 |
| Target 적용성 | `unresolved`, `applicable`, `experimental`, `unsupported`, `not_applicable`; controller/profile별 이유·근거 필수 |
| 실행 결과 | `NOT_RUN`, `PASS`, `FAIL`, `HOLD`, `NOT_APPLICABLE`; native nRF54L15 build·NU54DK build·Arduino build·runtime·negative·interop마다 독립 |
| Scope | 필수 구현/자동 검증, 사용자 후속 실물 검증, 최종 Host 실물 gate, 사용자 제외, 고정 SDK 비적용을 이유·소유자와 함께 기록 |

`build_only: true`는 upstream 시험 실행 방식이며 nRF54L15 미지원 표시가 아니다. 반대로
`build_only: false`, `integration_platforms`에 target이 있음, Kconfig enable 성공 중 어느 하나도
실제 NU54DK runtime PASS가 아니다. NCS maturity와 Zephyr Kconfig의 experimental 표기가 다르면
양쪽 근거를 남기고 이 Core의 opt-in 정책을 명시한다. M29 EATT의 기존 experimental 정책은 유지한다.

| Arduino 제공 경로 | 사용 계약 |
| --- | --- |
| `wrapper` | 한국어 Doxygen 문서·고정 자원·Arduino 자료형의 public facade. Zephyr 내부 구조체를 public ABI로 노출하지 않음 |
| `direct` | 별도 고급 `NUCODE_*` 공개 header/profile에서 고정 NCS 기능을 직접 제어하는 Arduino API를 사용. Zephyr/NCS header·type·함수는 library `.cpp`/`src/internal`에만 둔다. version·lifetime·callback 제약과 facade 혼용 금지를 명시 |
| `profile` | 필요한 Kconfig·partition·controller·자원 preset와 Arduino 예제를 함께 설치. 기존 기본 profile의 동작을 보존 |
| `template` | 외부 credential/peer/배선/별도 application 구조가 필요한 시작 프로젝트. build와 실제 external runtime 상태를 표시 |
| `excluded` | BR/EDR, 고정 nRF54L15 비적용 등 증명된 제외. 이유·upstream 경로를 남겨 원장에서는 제거하지 않음 |

한 기능은 복수 경로를 가질 수 있지만 기본 권장 경로 하나를 지정한다. `direct` 또는 `template`라는
이유로 build·예제 설명·보안 negative 검증 의무를 생략하지 않는다.

공개 `.ino`는 일반 C/C++과 `NUCODE_*` API로 `setup()`/`loop()`의 역할별 동작,
연결·송수신·오류 처리를 읽고 실행할 수 있어야 한다. Zephyr `bt_*`·`k_*` 호출이나
header-only 위임 몇 줄로 예제를 대신하지 않는다. `M31` 등 개발 마일스톤 이름은
공개 class/macro/API·광고명에 넣지 않는다. 예제 변경은 공개 경계 audit와 해당
Arduino 빌드 및 가능한 실제 역할 HIL을 통과해야 한다.

## 3. 실행 순서와 소유 마일스톤

| 순서·우선순위 | 구현할 묶음 | 선행 입력 | 산출물·다음 의존성 |
| --- | --- | --- | --- |
| 완료 / P0 | M31-W01 전체 source inventory·capability·실행 계약 | M28~M30 기준선, lock, 세 보드 role inventory | 전체 예제 parity 원장 후보와 M31 capability 원장·parser·target |
| 완료 / P0 | M31-A: W02 ISO → W03 Audio | controller capability·고정 stream/buffer | raw data/합성 PCM 예제, Audio role별 profile와 test |
| 완료 / P0 | M31 메모리 최적화 | W01~W03 완료와 W04·W05 기존 성공/실패 원본 | P0~P2 완료, 최종 크기 유지; [262번 완료](<../04_검증 기록/262_M31_메모리_최적화_P2_세_축_완료.md>) |
| 완료 / P0 | M31-B W04 DF | W01 controller별 판정과 최적화 image | 지원 CTE TX·연결 응답 PASS, 제품 SDC RX/AoD `UNSUPPORTED`; [263번 완료](<../04_검증 기록/263_M31_W04_Direction_Finding_완료.md>) |
| 완료 / P0 | M31-C W05 CS | W01 controller별 판정과 최적화 image | connected CS 예제, negative·복구 완료; [264번](<../04_검증 기록/264_M31_W05_Channel_Sounding_완료.md>) |
| 완료 / P0 | M31-W06 독립 image 자원·수명주기·회귀, W07 설치 예제·3보드 HIL, W08 Windows RC | 위 기능별 build/negative. 네 기능 전체 동시 실행은 요구하지 않음 | 기능 8/8·Windows package·설치·공개 RC smoke 완료; stable 별도 gate와 M32 자원 인계 |
| 4 / P0 | M32-A W01~W05 modern LE·Nordic 확장 | M31 W01 inventory와 기존 GAP | power/timing/광고/resource/diagnostic 예제 |
| 5 / P0 | M32-B W06 Mesh 기반 → W07 Mesh 1.1 → W08 BLOB/DFU | 설정·보안·고정 memory budget | Mesh role/model·전송·update 예제 |
| 5 / P0 | M32-C W09 단독 radio → W10 공존 | BLE/Mesh 단독 PASS, 최소 802.15.4/ESB profile | 지원 조합·중재·복구 예제; M38/M39 재사용 |
| 6 / P0 | M32-W11~W12 회귀·HIL·인계 | M32-A/B/C | 자원 상한·적용 조합·전체 원장 |
| 7 / P1 | M33-W01~W04 catalog·GATT·ecosystem·DTM/HCI | 각 기능의 owner 산출물 | 누락 없는 예제 경로, 조건부 external template |
| 8 / P0 | M33-W05~W08 후속 예제·설치·통합·Host 확대·공개 | 기능 원장, native Host, exact image·package | 후속 제품선의 기능별 지원표와 공개 gate; 버전 미정 |

P1은 생략 가능 표시가 아닌 구현 순서다. 공식 nRF54L15 적용 예제에는 실행 가능한 Arduino 경로를
제공하고, 기능·외부 의존성의 정당한 예외만 원장에 기록한다. 문서 계획 진척과 구현·runtime 진척은
각각 별도 분모로 보고한다. HOST-W04~HOST-W08은 Host 작업이며 M30 잔여 작업이 아니다.
M32-A 중 M31의 ISO/Audio/CS 자원을 사용하지 않는 항목은 공통 capability·자원 계약 뒤 M31과
기술적으로 독립 병행할 수 있다. M31은 완료했으며 M32·M33은 별도 착수 지시 후 진행한다.
최종 M32 통합 HIL에는 M31 인계와 해당 protocol 단독 결과가 필요하다.

## 4. M31-A — ISO와 LE Audio 구현 목록

### M31-W02 raw ISO

| 기능 | 고정 source 근거 | Arduino 경로·계획 예제와 역할 | 검증·장비 |
| --- | --- | --- | --- |
| CIG/CIS central·peripheral, unidirectional/bidirectional ISO | `BT_ISO`, `BT_ISO_CENTRAL`, `BT_ISO_PERIPHERAL`; `Z:iso_central`, `Z:iso_peripheral` | `wrapper/profile`: `RawIsoCentral`, `RawIsoPeripheral` | 2보드; 생성→연결→TX/RX→해제, sequence·payload·stream 격리 |
| BIG/BIS broadcaster·synchronized receiver, broadcast encryption | `BT_ISO_BROADCASTER`, `BT_ISO_SYNC_RECEIVER`; `Z:iso_broadcast`, `Z:iso_receive` | `wrapper/profile`: `RawIsoBroadcaster`, `RawIsoReceiver` | 2보드, 3보드 다중 receiver; code mismatch·sync loss·재동기 |
| SDU/frame/interval/PHY, timestamp·sequence, TX/RX buffer 소유권 | `Z:iso_connected_benchmark`, `Z:iso_broadcast_benchmark`; ISO header | `wrapper`: `IsoSequenceBenchmark` sender/receiver | 2보드; 분모·loss·duplicate·out-of-order·buffer 반환과 과도 자원 요청 |
| BIS+CIS 조합 | `N:iso_combined_bis_and_cis`에 nRF54L15 metadata 존재 | `profile/direct`: `IsoCombinedBisCis` broadcaster/central와 peer | topology별 2~3보드; 동시 stream·ACL·역할 충돌·종료 누수 |
| ISO time synchronization | `N:iso_time_sync`에 nRF54L15 metadata 존재 | `profile/direct`: `IsoTimeSyncSender`, `IsoTimeSyncReceiver` | 2보드, 3번째 receiver 확장; timestamp 관계·restart. 외부 계측 정확도는 범위 제외 |
| 자원·보안·복구 | ISO callback·error 경로와 M28/M30 link/security 계약 | 위 예제 공통 finite runner | 2~3보드; stale callback, disconnect 중 pending TX, wrong broadcast code, timeout, 재시작 |

W02는 clean `e6ae812e…` private package에서 설치 sketch 11개를 11/11 빌드하고,
CIS·BIS·암호화·wrong code·sync loss·time sync·세 보드 CIS→BIS 무선 시험을 통과했다.
하지만 2026-09-17 공개 예제 점검에서 11개 sketch가 `Program::begin()`/`poll()`만
호출하고 시험용 고정 SDU·Serial protocol을 library backend에 맡기는 결함을 확인했다.
이에 W02를 **진행 중**으로 되돌려 공개 ISO 데이터 API와 사용자 편집 가능한 송수신 예제를
구현·재검증했다. 이전 무선 시험의 역할별 경로와 image·transcript hash는
[W02 closure audit](<../04_검증 기록/evidence/m31-w02-arduino-e6ae812e/closure-audit.json>)가 소유한다.
그 audit는 현재 공개 예제 완료 판정의 근거가 아니다. 계획 예제 이름은 기능 계약이며
실제 설치 이름은 readiness의 `actual_sketch`가 기준이다.

현재 W02는 [199번 최종 기록](<../04_검증 기록/199_M31_W02_격리_설치본_ISO_11예제와_완료.md>)의
설치본 11/11 build·11역할 실기, wrong code 거부 후 복구와 sync loss 재시작까지 완료했다.
이전 실패·완료 철회 기록은 당시 판정으로 보존한다.

### M31-W03 LE Audio 하위 계약

아래 11개 묶음은 [214번 완료 감사](<../04_검증 기록/214_M31_W03_LE_Audio_Profile_완료.md>)에서
공개 역할별 build·기능·negative·복구 검증을 닫았다. 표는 각 묶음의 기능 계약을 유지하며 실제 Sketch와
source별 증거는 readiness가 소유한다. nRF5340·simulation의 결과를 NU54DK로 복사하지 않고,
지원 가능한 역할을 임의로 생략하지 않는다.

| 묶음 | 반드시 명시·구현할 기능 | 고정 source 근거 | Arduino 경로·계획 예제 | 검증·장비 |
| --- | --- | --- | --- | --- |
| W03-01 | LC3 encode/decode, codec/frame/sample rate/channel, PCM buffer와 presentation delay | `zephyr/subsys/bluetooth/audio`, 관련 codec module·sample 설정 | `profile/direct`: `Lc3SyntheticLoopback` | 1보드 codec, 2보드 transport; 합성 PCM oracle·frame 크기·underrun/overrun·buffer 회수 |
| W03-02 | BAP Unicast Client/Server, PACS capability/context, ASCS ASE 상태 | `BT_BAP_UNICAST_CLIENT/SERVER`, `BT_PACS`, `BT_ASCS`; `Z:bap_unicast_client/server` | `wrapper/profile`: `AudioUnicastClient`, `AudioUnicastServer` | 2보드; discovery→codec/QoS→enable→start→stop, unsupported codec·잘못된 ASE 전이 |
| W03-03 | BAP Broadcast Source/Sink, BASE/BIGInfo·metadata·broadcast code | `BT_BAP_BROADCAST_SOURCE/SINK`; `Z:bap_broadcast_source/sink` | `wrapper/profile`: `AudioBroadcastSource`, `AudioBroadcastSink` | 2보드, 복수 sink 3보드; stream 수·암호·재동기·잘못된 BASE |
| W03-04 | BASS, Scan Delegator와 Broadcast Assistant | `BT_BAP_SCAN_DELEGATOR`, `BT_BAP_BROADCAST_ASSISTANT`; `Z:bap_broadcast_assistant` | `profile/direct`: `AudioScanDelegator`, `AudioBroadcastAssistant` | source+sink/delegator+assistant 3보드; source add/modify/remove·code 전달·잘못된 source |
| W03-05 | CAP Initiator/Acceptor/Commander, unicast/broadcast 절차·handover 적용성 | `BT_CAP_INITIATOR/ACCEPTOR/COMMANDER/HANDOVER`; `Z:cap_initiator/acceptor` | `profile/direct`: `CapInitiator`, `CapAcceptor`, `CapCommander` | 2~3보드; group 절차·부분 실패·cancel·handover. role 결합 한도 고정 |
| W03-06 | CSIP Set Member/Coordinator, SIRK·rank·set size·lock | `BT_CSIP_SET_MEMBER`, `BT_CSIP_SET_COORDINATOR` | `profile/direct`: `CsipSetMember`, `CsipCoordinator` | coordinator+2 member 3보드; lock 해제·잘못된 SIRK·member 소실 |
| W03-07 | PBP Public Broadcast source/sink·announcement·metadata | `BT_PBP`; `Z:pbp_public_broadcast_source/sink` | `profile`: `PublicAudioBroadcastSource`, `PublicAudioBroadcastSink` | 2보드; public discovery·metadata·sync. Auracast 상호운용·인증 주장은 별도 |
| W03-08 | VCP volume renderer/controller, VOCS offset, AICS input, MICP mic device/controller | `BT_VCP_*`, `BT_VOCS*`, `BT_AICS*`, `BT_MICP_*` | `profile/direct`: `AudioVolumeControl`, `AudioInputControl`, `AudioMicrophoneControl` 양 역할 | 2보드; virtual volume/mute/gain/description 상태·range·counter 오류. 실제 mic 불필요 |
| W03-09 | MCP/MCS media player/controller, CCP/TBS call server/client | `BT_MCC`, `BT_MCS`, `BT_CCP_CALL_CONTROL_CLIENT/SERVER`, `BT_TBS*`; `Z:ccp_call_control_client/server` | `profile/direct`: `MediaControlPlayer`, `MediaControlClient`, `CallControlServer`, `CallControlClient` | 2보드; 합성 track/call 상태·control point·unsupported opcode·stale ID |
| W03-10 | TMAP CG/CT/UMS/UMR/BMS/BMR, GMAP UGG/UGT/BGS/BGR | `BT_TMAP*`, `BT_GMAP*`; `Z:tmap_central/peripheral/bms/bmr` | `profile`: `TelephonyMediaRoles`, `GamingAudioRoles` 역할별 preset | 2~3보드; role bit·필수 service·stream procedure·미지원 역할 요청 |
| W03-11 | HAP/HAS hearing access, preset·active index·name·client | `BT_HAS*`; `Z:hap_ha` | `profile/direct`: `HearingAccessServer`, `HearingAccessClient` | 2보드; 합성 preset·동기화·범위 오류. 실제 보청기·음질은 별도 peer 시험 |

합성 PCM은 LC3·BAP·ISO 데이터 경로가 실제로 통과해야 한다. Boot banner, 광고 시작, callback 한 번을
audio 송수신 PASS로 판정하지 않는다. 송신 frame과 수신 frame·decode 결과·sequence를 결합하고,
timestamp에 근거한 소프트웨어 관측 지연과 외부 계측 end-to-end 지연을 구분한다.
외장 microphone/speaker/codec를 연결해서 사용할 구현·예제·설정·연결 안내도 필수 산출물이다.
그 실물 운용·검증은 사용자 후속으로 인계하며 M31/M33 개발·릴리스 필수 gate에서 제외한다.
합성 PCM 검증을 외장 음성 입출력 검증으로 표시하지 않는다.

## 5. M31-B/C — Direction Finding과 connected Channel Sounding

| 소유자·기능 | 고정 source·지원 경계 | Arduino 경로·계획 예제 | 검증·장비 |
| --- | --- | --- | --- |
| M31-W04 connectionless AoA CTE TX | SDC CTE advertising, `N:direction_finding_connectionless_tx` nRF54L15 metadata. NCS maturity는 experimental | `profile/direct`: `DirectionFindingCteBeacon` | 1보드 capability/start/stop; CTE 실제 수신 확인은 지원 RX peer 필요. 보드 3개 보유만으로 IQ RX를 가정하지 않음 |
| M31-W04 connected AoA CTE response TX | `N:direction_finding_peripheral` metadata와 실제 controller 적용성은 별도. 고정 SDC 실기는 HCI `0x2055` Unknown Command, 별도 Zephyr LL 응답은 국소 PASS | `profile/direct`: 공개 `ConnectedCteResponder`는 별도 LL 설정 사용 | [174번](<../04_검증 기록/174_M31_W04_연결_CTE_응답_실기.md>)의 시작·중단·재시작만 검증. 실제 CTE 요청·IQ 수신 판정과 구분 |
| M31-W04 원시 AoA RX/IQ | 고정 NCS v3.4.0의 nRF54L15 제품 SDC는 AoA 송신 전용. IQ RX는 `UNSUPPORTED` | 제품 RX 예제를 제공한다고 약속하지 않음. 기존 Zephyr LL fixture는 내부 진단용 | connected 내부 진단은 IQ 20 report·1,640 sample·cleanup 국소 PASS, connectionless는 IQ 0·fault. 둘 다 제품 SDC RX·P2 gate가 아님 |
| M31-W04 실제 AoA 각도·antenna switching | 공간적 위상차를 이용한 각도 계산과 외장 antenna 제어는 원시 IQ 수집과 다른 경로 | 적용 가능한 설정·예제·연결 안내를 별도 제공 | 실물 안테나 구성의 운용·검증은 사용자 후속·릴리스 비차단 `NOT_RUN`; 정밀 각도 보정·정확도 보증은 범위 제외 |
| M31-W04 AoD | 고정 SDC의 connectionless/connected CTE는 AoD 미지원 | 기본 SDC `excluded`; 명확한 오류·capability 예제로 표시 | Unsupported negative. 다른 controller가 필요하면 별도 영향 평가; 자동 전환하지 않음 |
| M31-W05 CS initiator/reflector | `BT_CHANNEL_SOUNDING`; `N:channel_sounding/ras_initiator`, `ras_reflector` nRF54L15 metadata·`build_only` 존재, initiator의 `A1_B1`은 양쪽 안테나 1개 | `wrapper/profile`: `ChannelSoundingInitiator`, `ChannelSoundingReflector` | 기본 안테나의 2보드; ACL→security→capability/config→procedure→result→stop. 안테나 배열을 요구하지 않음 |
| M31-W05 RAS 결과 전송 | NCS RAS initiator/reflector와 service/header | `profile/direct`: 위 CS 예제의 RAS mode | 2보드; raw subevent·결과 길이·분할/재조합·procedure ID·buffer 소유권 |
| M31-W05 계산 결과·반복 실행 | sample의 ranging 결과와 선택 algorithm | `wrapper/direct`: `ChannelSoundingResults` | 2보드; 실제 procedure 수·유효 결과·finite/invalid 값 구분. 미보정 추정 거리의 정확도는 보증하지 않음 |
| M31-W05 CS negative·다중 peer | 보안·procedure/state·M28 link handle | CS 예제 공통 runner, `ChannelSoundingMultiPeer` | 2보드 negative, 3보드 peer 격리; insecure ACL·잘못된 config·timeout·peer loss·reconnect |

고정 [Zephyr 수신 README](https://github.com/nrfconnect/sdk-zephyr/blob/bf801e4e3d19e1ffa76164346480cb7734dd2800/samples/bluetooth/direction_finding_connectionless_rx/README.rst)는
AoA antenna matrix를 선택 사항으로 적는다. 이는 NU54DK 수신 PASS가 아니라 **배열이 없다는 이유만으로
원시 IQ의 지원 여부를 안테나 배열 유무만으로 판단하면 안 된다는 근거**다. 같은 경로의 `sample.yaml`에는 nRF54L15가 없으므로,
Zephyr LL RX 코드·DTS `dfe-supported` 존재만으로 해당 SoC/보드의 수신 적용성을 확정하지 않는다.
제품 지원 판정은 [259번 고정 SDK 지원 경계](<../04_검증 기록/259_M31_P2_DF_고정_SDK_지원_경계.md>)를 따른다.
Zephyr LL의 내부 Host 상태 우회 진단과 connectionless 실패는 보존하되 제품 SDC IQ RX의
미완료 blocker로 재등록하지 않는다. 기존 SDC의 제한을 전체 칩·다른 Nordic 제품의 RX 불가능으로 확대하지 않는다.
CS의 단일 안테나 계획은 고정 [RAS initiator 설정](https://github.com/nrfconnect/sdk-nrf/blob/99553055607b2e9885fbc80ccd11fa9da81c2df0/samples/bluetooth/channel_sounding/ras_initiator/src/main.c#L963)에
근거하며 DF의 각도용 배열 조건과 혼동하지 않는다.

CS의 간헐 RF/controller loss·counter gap은 P2에서 관찰값으로만 기록한다. 0-gap이나
loss 없는 재전송을 완료 조건으로 추가하지 않는다. 유효 raw·step·결과 수, 양측 STOP,
fault·중복·역행 counter 검사는 유지하며 최대 절차 중 peer 이탈·복구는 별도 부하 검증이다.

NCS의 `nrf_dm`은 이 고정 버전의 sample metadata에 nRF54L15가 없고 nRF52/nRF5340 대상으로
한정되어 있다. 해당 예제는 `not_applicable/excluded` 근거를 남기고 nRF54L15의 connected CS 경로를
연결한다. Source 폴더가 있다는 이유로 오래된 nRF Distance Measurement를 별도 지원 기능으로 약속하지 않는다.

## 6. M32-A — modern LE controller·Host와 Nordic 확장

다음 표가 M28 완료 이후 추가하는 controller/Host 기능의 구현 목록이다. NCS maturity·SDC 기능표와
Host API의 존재를 대조하고 NU54DK image·runtime을 별도로 기록한다.

| 소유자·기능 | 고정 source 근거 | Arduino 경로·계획 예제와 역할 | 검증·장비 |
| --- | --- | --- | --- |
| W01 capability·controller variant·확장 feature page | SDC variant 표, `BT_LE_EXTENDED_FEAT_SET`, HCI feature/header | `wrapper/profile`: `ModernLeCapabilities` | 1보드; revision·feature 길이·누락/중복·잘못된 variant |
| W02 LE Power Control Request·TX Power Report | `BT_TRANSMIT_POWER_CONTROL`, `N:rssi_power_control/central`, `peripheral` | `wrapper/direct`: `LePowerControlCentral`, `LePowerControlPeripheral` | 2보드; local/remote TX power·변경 event·PHY별 상태·허용 range |
| W02 Path Loss Monitoring | `BT_PATH_LOSS_MONITORING`, `N:path_loss_monitoring/central`, `peripheral` | `wrapper`: `PathLossMonitorCentral`, `PathLossMonitorPeripheral` | 2보드; threshold/hysteresis/min-time·report enable/disable·invalid range. 보정된 경로손실 정확도 제외 |
| W03 Connection Subrating | `BT_SUBRATING`, `N:subrating` | `wrapper/profile`: `ConnectionSubratingCentral`, `ConnectionSubratingPeripheral` | 2보드; request/actual factor·continuation·timeout·거절·복구 |
| W03 Sleep Clock Accuracy Update | `BT_SCA_UPDATE` | `wrapper/direct`: `SleepClockAccuracyUpdate` central/peripheral | 2보드; peer SCA 조회/갱신·지원 미일치·절차 종료 |
| W03 Frame Space Update | `BT_FRAME_SPACE_UPDATE`와 Extended Feature Set | `wrapper/direct`: `FrameSpaceUpdate` 양 역할 | 2보드; 요청·협상 값·unsupported peer·충돌 |
| W03 Shorter Connection Intervals | `BT_SHORTER_CONNECTION_INTERVALS`, `N:shorter_conn_intervals` | `profile/direct`: `ShorterConnectionIntervals` 양 역할 | 2보드; negotiated interval·PHY·DLE/frame space 조건·negative. SDC 최솟값을 모든 profile 보증으로 확대하지 않음 |
| W03 LL Extended Feature Set | `BT_LE_EXTENDED_FEAT_SET`, extension page read/교환 | `wrapper/direct`: `ExtendedLeFeaturePages` | 1~2보드; page 수·길이·미지원 page와 link 격리 |
| W04 여러 advertising set·periodic sync | `BT_EXT_ADV_MAX_ADV_SET`, `BT_PER_ADV_SYNC_MAX`; `N:multiple_adv_sets`, `Z:broadcaster_multiple` | `wrapper/profile`: `MultipleAdvertisingSets`, `MultiplePeriodicSyncs` | 2~3보드; 실제 상한·set/SID ownership·exhaustion·stop/recreate |
| W04 여러 local identity·RPA·bond | `BT_ID_MAX`, `N:peripheral_with_multiple_identities`, `Z:peripheral_identity` | `wrapper/profile`: `MultipleBleIdentities` | 2~3보드; identity별 주소/광고/bond·잘못된 ID·삭제 중 사용 |
| W04 Filter Accept List·Periodic Advertiser List | Bluetooth Host filter/periodic advertiser list API; `Z:peripheral_accept_list` | `wrapper`: `AdvertisingAcceptList`, `PeriodicAdvertiserList` | 3보드 positive+negative peer; add/remove/clear·활성 상태 변경·비허가 수용 0 |
| W04 Directed Advertising | `Z:direct_adv`와 광고 option | `wrapper`: `DirectedAdvertisingPeripheral`, `DirectedAdvertisingCentral` | 2~3보드; 지정 peer/RPA·timeout·잘못된 peer·high/low duty 적용성 |
| W04 Encrypted Advertising Data | `BT_EAD`; `Z:encrypted_advertising/central`, `peripheral`는 Host source candidate | `profile/wrapper`: `EncryptedAdvertisingCentral`, `EncryptedAdvertisingPeripheral` | 2보드; key/IV·randomizer/RPA·decrypt·tamper/wrong-key/replay 정책. nRF54 target build 별도 |
| W04 Advertising Coding Selection | `BT_EXT_ADV_CODING_SELECTION`, `Kconfig.adv` | `wrapper/direct`: `AdvertisingCodingSelection` advertiser/scanner | 2보드; Coded PHY coding 요구·불가 조건·controller 응답 |
| W04 Scan while initiating·identity scan | `BT_SCAN_AND_INITIATE_IN_PARALLEL`, `BT_SCAN_WITH_IDENTITY`; `N:scanning_while_connecting` | `wrapper/profile`: `ScanWhileConnecting` scanner/initiator·peers | 3보드; 진행 중 scan event·connect timeout·취소·자원 제한 |
| W03 throughput·channel classification/map·event timing | `N:throughput`, LE channel map/classification와 controller timing API | `profile/direct`: `BleThroughputPair`, `LeChannelMapControl` | 2~3보드; 전송 분모/실측률·map 유효성·invalid all-disabled map·복구·다른 link 보존 |
| W04 scalable resource profile | multi-link/adv/sync Kconfig, ARF-01 role budget | `profile`: `ScalableBleResources` | 2~3보드; RAM/RRAM·buffer 상한·stale handle·다른 link 보존. throughput oracle은 W03 재사용 |
| W05 LLPM | `BT_CTLR_SDC_LLPM`, `N:llpm` | `profile/direct`: `NordicLlpmPair` | 2보드; vendor capability·interval·fallback/거절. 표준 Shorter CI와 별도 |
| W05 QoS Connection Event Reports | `BT_CTLR_SDC_QOS_CONN_EVENT_REPORT` | `direct/profile`: `NordicConnectionEventQos` | 2보드; report 수·event/link·CRC/timeout 통계·disable·과도 callback |
| W05 QoS Channel Survey | `BT_CTLR_SDC_QOS_CHANNEL_SURVEY`, SDC vendor API | `direct/profile`: `NordicChannelSurvey` | 1~2보드; channel/energy 결과 형식·start/stop·callback 수명. RF 정밀 측정 제외; 표준 channel map 제어는 W03 |
| W05 connection time sync | `N:conn_time_sync` | `direct/profile`: `ConnectionTimeSyncCentral`, `ConnectionTimeSyncPeripheral` | 2보드; time reference·wrap·reconnect·sample 손실 |
| W05 Event Trigger·Radio Notification | `BT_CTLR_SDC_EVENT_TRIGGER`, `N:event_trigger`; `BT_RADIO_NOTIFICATION_CONN_CB`, `N:radio_notification_cb` | `direct/profile`: `RadioEventTrigger`, `ConnectionRadioNotification` | 1~2보드; callback lifetime·priority·등록/해제·late event. GPIO 경로는 명시된 fixture만 사용 |
| W05 LE Flushable ACL Data | `BT_CTLR_LE_FLUSHABLE_ACL_DATA`, SDC experimental 기능 | experimental opt-in `profile/direct`: `FlushableAclData` | 2보드; flushable/non-flushable 구분·expiry/drop·buffer 회수·지원 미일치 |

현재 `txPower()` 조회 성공은 W02 Power Control/Path Loss 절차 완료가 아니다. 마찬가지로 Kconfig의
허용 최대값이나 upstream 예제의 set 개수를 그대로 Core 자원 상한으로 삼지 않는다. 해당 NU54DK
profile가 실제로 build·동작하는 상한을 측정하고 요청 초과는 명시적 오류로 거부한다.
ARF-01 BLE role-budget의 `C1P1/C2P0/C0P2`는 M32-W04 자원 preset에 통합한다. 기존 기본값
2-link·1-set을 유지하고 새 preset별 역할·buffer·상한·초과 거절을 검증한다. ARF-01을 별도 구현
분모로 중복 계산하지 않는다.

## 7. M32-B/C — Mesh 전체 기능과 공존

| 소유자·기능 | 고정 source 근거 | Arduino 경로·계획 예제와 역할 | 검증·장비 |
| --- | --- | --- | --- |
| W06 provisioning·configuration·health | `Z:mesh`, `mesh_provisioner`; `N:mesh` 및 `BT_MESH` | `wrapper/profile`: `MeshProvisioner`, `MeshNode`, `MeshHealth` | 2~3보드; provision→bind→publish/subscribe→unprovision·key/settings·malformed/unauthorized |
| W06 relay·friend·LPN·GATT proxy | `BT_MESH_RELAY`, `BT_MESH_FRIEND`, `BT_MESH_LOW_POWER`, proxy 설정 | `profile`: `MeshRelay`, `MeshFriend`, `MeshLowPowerNode`, `MeshProxy` | 최소 topology 3보드; 역할 조합·friendship·queue/TTL·peer 소실·복구. 외부 proxy client 조건부 |
| W06 standard models·settings·key refresh | `N:mesh` 모델과 Zephyr Mesh model/header | `wrapper/direct/profile`: `MeshOnOff`, `MeshLevel`, `MeshLight`, `MeshSensor`, `MeshTimeSceneScheduler` server/client | 2~3보드; 고정 upstream 모델 inventory 전수 매핑, state/transition/transaction·replay·settings 재시작 |
| W07 Remote Provisioning | `BT_MESH_RPR_CLI/SRV` | `profile/direct`: `MeshRemoteProvisioner`, `MeshRemoteProvisioningServer` | 3보드; client/server/unprovisioned node·scan report·link open/close·timeout |
| W07 SAR Configuration | `BT_MESH_SAR_CFG_CLI/SRV` | `profile/direct`: `MeshSarConfiguration` 양 역할 | 2~3보드; segmentation/reassembly parameter·상한·malformed segment·시간 만료 |
| W07 Opcodes Aggregator | `BT_MESH_OP_AGG_CLI/SRV` | `profile/direct`: `MeshOpcodeAggregator` 양 역할 | 2보드; 순서·부분 오류·길이·잘못된 opcode |
| W07 Large Composition Data | `BT_MESH_LARGE_COMP_DATA_CLI/SRV` | `profile/direct`: `MeshLargeCompositionData` 양 역할 | 2보드; page/offset·chunk 재조합·out-of-range |
| W07 Private Beacon | `BT_MESH_PRIV_BEACONS`, `BT_MESH_PRIV_BEACON_CLI/SRV` | `profile/direct`: `MeshPrivateBeacon` 양 역할 | 2~3보드; enable/update·key/IV 상태·잘못된 key·public/private 정책 |
| W07 On-Demand Private Proxy·Solicitation PDU/RPL | `BT_MESH_OD_PRIV_PROXY_CLI/SRV`, `BT_MESH_SOLICITATION`, `BT_MESH_SOL_PDU_RPL_CLI` | `profile/direct`: `MeshOnDemandPrivateProxy`, `MeshProxySolicitation` | 2~3보드; solicitation·proxy 수명·replay list·잘못된 identity |
| W07 Subnet Bridging | `BT_MESH_BRG_CFG_CLI/SRV`, bridge table | `profile/direct`: `MeshSubnetBridge` | 3보드 최소 두 subnet+bridge; table·방향·허용되지 않은 subnet 전달·loop/TTL |
| W08 BLOB Transfer client/server | `BT_MESH_BLOB_CLI/SRV`, flash IO·block/chunk 설정 | `profile/direct`: `MeshBlobClient`, `MeshBlobServer` | 2~3보드; object hash·누락 chunk·cancel/resume·저장 공간 초과 |
| W08 Mesh DFU·Firmware Distribution | `BT_MESH_DFU_CLI/SRV`, `BT_MESH_DFD_SRV` 및 firmware slot | `profile/template`: `MeshDfuTarget`, `MeshFirmwareDistributor` | distributor+2 target 3보드; 서명/hash·wrong image·version·전송/설치 단계·재시작. 외장 flash 없는 layout 예산 필수 |
| W09 최소 802.15.4·ESB 단독 radio | 고정 NCS radio/ESB/MPSL·Zephyr IEEE 802.15.4 API | 검증용 `profile/direct`: `Radio154Pair`, `EsbPair` | 2보드; 각 protocol 단독 TX/RX·channel·payload·종료/재시작 |
| W10 BLE↔Mesh↔802.15.4↔ESB 공존 | MPSL/timeslot·profile 적용 조합; `N:radio_coex_1wire` | `profile/direct`: `BleMeshCoexistence`, `Ble154Coexistence`, `BleEsbCoexistence` | 최소 3보드; 조합별 단독 기준→공존·기아/지연·priority·자원 반환. 모든 protocol 동시 실행을 가정하지 않음 |
| W10 외부 radio coexistence 제어선 | `N:radio_coex_1wire`와 해당 hardware 요구 | `template`: `RadioCoexistenceOneWire`, 실제 연결용 구현·예제·안내 필수 | build·계약·자동 검사 수행. 외장 실물 신호 검증은 사용자 후속 `NOT_RUN`이며 개발·릴리스 비차단 |
| W11~W12 통합·회귀·마감 | 위 기능 + M19~M31 회귀; HOST-W07 절차 준비는 독립 | role별 runner·예제·readiness·handoff | 실제 topology별 2~3보드 또는 필요한 수; 초과 topology는 별도 필요 수·검증 범위. Ubuntu/macOS 실물은 최종 사용자 gate |

Mesh 1.1이라는 버전명만으로 모든 선택 기능을 지원한다고 선언하지 않는다. 예를 들어 directed
forwarding처럼 고정 source에서 적용성을 아직 확인하지 않은 기능은 W01/W07 조사 행으로 남기고,
구현 가능·SDK 미제공·controller/자원 제한 중 근거 있는 판정을 기록한다. 향후 source inventory에서
추가 모델이 발견되면 W06/W07에 소유자를 부여하고 누락시키지 않는다.

DFU의 memory erase는 승인된 profile의 지정 image/storage 영역에 한정한다. Mesh 시험 계획이
mass erase, recover, 임의 전원 차단을 허가하지 않는다. M30의 실제 전원 시험 원본을 Mesh DFU
PASS로 재사용하지 않으며 새 power-loss 확장이 필요하면 M36의 명시적 시험 계약으로 인계한다.

## 8. M33 — 표준 profile·특수 template·예제 완성

M33은 후속 제품선의 공개 정리와 함께 generic GATT 위에서 제공할 신규 서비스·client 예제를 소유한다.
M31 v0.5.0 Windows 릴리스는 M31-W08이 담당하며 이 전체 catalog의 완성을 기다리지 않는다.
서비스가 많다는 이유로 각각 Core singleton을 만들지 않고 `profile/direct/template`를 활용한다.
기존 M30 7개 profile와 ARF-04A 목적별 예제의 완료·미착수 상태는 각각 기존 원본에서 가져온다.

| 소유자·기능 | 고정 source 근거 | Arduino 경로·계획 예제 | 검증·장비 |
| --- | --- | --- | --- |
| W01 전체 sample catalog와 추가 후보 | 모든 `N:`·`Z:` sample YAML/test ID·고정 설정 | §10 parity 원장; 모든 행을 실제 Sketch/profile/template에 연결 | inventory 누락·중복·미배정 0, 적용성 근거 |
| W02 OTS/OTP·OTC | `Z:peripheral_ots`, `central_otc`, GATT+CoC | `profile/direct`: `ObjectTransferServer`, `ObjectTransferClient` | 2보드; object metadata·read/write/delete·hash·offset·권한·CoC 복구 |
| W02 ANS | `Z:peripheral_ans` | `profile`: `AlertNotificationServer`, 해당 client 예제 | 2보드 synthetic alert·잘못된 category/control |
| W02 CTS·HTS | `N:peripheral_cts_client`, `Z:peripheral_ht`, `central_ht` | `profile`: `CurrentTimeClient`, `HealthThermometerServer/Client` | 2보드 synthetic time/temperature·길이/range·시간 갱신 |
| W02 CSC·RSCS | `Z:peripheral_csc`, `N:peripheral_rscs` | `profile`: `CyclingSpeedCadence`, `RunningSpeedCadence` server/client | 2보드 synthetic count/speed·wrap·control point |
| W02 CGMS·BMS | `N:peripheral_cgms`, `peripheral_bms` | `profile`: `ContinuousGlucoseService`, `BondManagementService` 양 역할 | 2보드 synthetic 측정/RACP·인증된 bond 삭제·비허가 요청 거절. 의료 성능 보증 아님 |
| W02 기존 BAS/DIS/HID/HRS/ESS·GAP/배터리 client | `N:central_bas`, `central_hids`, `central_and_peripheral_hrs`, `central_hr_coded`, `peripheral_hr_coded`; `Z:peripheral_dis/hr/hids/esp/gap_svc` | 기존 예제 확장 + `BatteryClient`, `HidHost`, `CodedHeartRatePair` | 2~3보드; 역할별 discovery/read/notify/control·원래 M30 범위 회귀 |
| W02 NUS·LBS·GATT discovery/MTU·장문 예제 | `N:central_uart`, `peripheral_uart`, `peripheral_lbs`, `peripheral_gatt_dm`, `shell_bt_nus`; `Z:peripheral_nus`, `central_gatt_write`, `peripheral_gatt_write`, `mtu_update` | `wrapper/direct/profile`: `UartOverBlePair`, `LedButtonPair`, `GattDiscoveryClient`, `GattMtuTransfer` | 2보드; 실제 payload·MTU·disconnect·특성 미발견. 새 buffered NUS API는 ARF owner와 별도 연계 |
| W02 iBeacon·Eddystone·BTHome·beacon/observer | `Z:ibeacon`, `eddystone`, `bthome_sensor_template`, `beacon`, `observer` | `template/profile`: `IBeacon`, `EddystoneBeacon`, `BTHomeSensor`, `BeaconObserver` | 2보드; AD byte·UUID/service data·암호 적용성·decode·malformed AD |
| W02 additional GATT/service candidates | `Z:peripheral_ets`, `N:peripheral_status`, 기타 고정 sample service·client | 원장에 서비스와 owner·제공 경로를 개별 추가 | synthetic peer로 가능한 기능 실행, source가 없는 항목은 별도 candidate 사유 |
| W03 ANCS·AMS | `N:peripheral_ancs_client`, `peripheral_ams_client` | `template/profile`: 실사용 구현·`AppleNotificationClient`·`AppleMediaClient`·설정 안내 | build/Host parser·자동 가능한 semantic/peer 검사 필수. 실제 Apple 운용·interop는 사용자 후속 `NOT_RUN`, 릴리스 비차단 |
| W03 Fast Pair input device·locator tag | `N:fast_pair/input_device`, `locator_tag` | `template/profile`: 실사용 구현·`FastPairInputDevice`·`FastPairLocatorTag`·credential 안내 | 시험/production credential 구분·자동 검사 필수. 실제 Google 제품 운용·interop는 사용자 후속 `NOT_RUN`, 릴리스 비차단 |
| W03 외부 ecosystem·진단 transport template | `N:enocean`, `nrf_auraconfig`, `peripheral_mds`, 관련 별도 service/backend | `template`: 실제 기능·설정·연결/계정 안내·자동 검사 필수; 빈 success stub 금지 | EnOcean/audio gateway/cloud 등 실제 운용·외장 검증은 사용자 후속 `NOT_RUN`, 개발·릴리스 비차단 |
| W04 Direct Test Mode | `N:direct_test_mode` nRF54L15 metadata와 2-DK UART 절차 | 독점 test `profile/template`: `DirectTestMode` | 1보드 command/상태·stop, 2보드 TX/RX·수신 packet count·역할 교대 자동화. RF 감도·출력·스펙트럼 측정은 별도 tester 없으면 `NOT RUN`/범위 밖 |
| W04 HCI UART·3-wire·async·LPUART | `Z:hci_uart`, `hci_uart_3wire`, `hci_uart_async`; `N:hci_lpuart` | 독점 controller `profile/template`: `HciUartController`, `HciThreeWireController`, `HciLowPowerUartController` | Host transport·결선/flow·frame·reset·malformed command; 보드 실제 UART 경로에 맞춰 판정 |
| W04 HCI SPI·USB·IPC·RPC | `Z:hci_spi`, `hci_usb`, `hci_ipc`; `N:rpc_host` | 적용 시 `profile/template`, 비적용은 `excluded` 이유 | SPI peer·USB device hardware·IPC core 구조 각각 별도. DAPLink VCOM을 SoC native USB controller로 간주하지 않음 |
| W04 vendor HCI·power/scan request·power profiling | `Z:hci_pwr_ctrl`, `hci_vs_scan_req`; `N:peripheral_power_profiling` | `direct/profile/template`: `HciPowerControl`, `ScanRequestDiagnostics`, `BlePowerProfiling` | 기능 command/event는 자동화; 실제 소비전력 수치는 전력계 없으면 `NOT RUN` |
| W05 설치 예제·입문 경로·문서 | 각 owner 산출물·ARF-04A 기존 API 목적별 예제 | package 예제 lock·README·역할별 실행법·문제 해결·지원표 | Windows/Ubuntu/macOS compile matrix·예제 목록 일치 |
| W06~W08 회귀·상호운용·RC·공개 | 전체 원장·HOST-W08·기존 release 계약 | 적용 기능/조건부/미지원이 드러나는 release 지원표 | exact build/runtime/interop·package/install·qualification 적용성 |

BR/EDR Classic sample(`Z:classic`)은 nRF54L15 내장 BLE radio 지원 목표 밖으로 `excluded` 처리한다.
외부 HCI controller를 붙여 Classic을 실행하는 별도 제품 구성을 nRF54L15 자체 지원으로 계산하지 않는다.
다른 board 전용 sensor/application 예제는 board 종속 부분을 식별하고, Bluetooth 경로의 Arduino port,
외부 sensor template 또는 비적용 사유를 원장에 남긴다.

## 9. 예제 코드의 필수 산출물

모든 예제는 최소 동작 흐름을 실제 구현한다. Build만 되는 placeholder와 출력만 하는 sample을
기능 완료로 처리하지 않는다. 원본 sample의 copyright·license·수정 이력을 보존한다.

1. Upstream module·exact revision·sample path·test ID, 변경한 board dependency를 기록한다.
2. 역할별 Sketch, 필요한 library/header, 권장 profile·Kconfig·resource budget를 제공한다.
3. 사용자용 `setup()/loop()` 흐름과 자동 시험용 start/stop/status 경로를 함께 마련한다.
   버튼·콘솔 메뉴를 대체하는 serial 명령은 원래 기능 경로를 호출하고 결과 oracle을 유지한다.
4. 필요한 보드 수·역할·peer·배선·전원·외부 credential을 한 곳에 적는다. 보드만 필요한 예제는
   합성 data/PCM 생성과 수신 검증 방법을 제공한다.
5. 정상 시 기대 출력, timeout, 지원되지 않는 profile/role 요청의 오류, 종료·재실행 방법을 적는다.
6. Arduino compile 명령·CI matrix ID·대상 image/profile, firmware revision 표시와 sample manifest를
   연결한다. 부가 profile가 필요하면 기본 profile에서 발생할 오류도 설명한다.
7. 기능별 negative, finite 반복·분모·자원 회수 검사를 마련한다. callback/handle 수명과 ISR 사용 제한을
   설명하고 기존 singleton/Zephyr direct API의 이중 ownership을 거부한다.
8. First-party 주석은 한국어 Doxygen, BSD/Allman, 탭 폭 4칸, 모든 제어문 중괄호를 사용한다.
9. 이중 role 예제는 두 역할을 모두 설치한다. 상위 BAP sample 한 개를 raw ISO·CAP·PBP 모든 예제의
   완료 증거로 대체하지 않는다. 공통 구현을 공유하더라도 원장에서는 역할별 행을 보존한다.

공개 Arduino 예제의 `setup()`·`loop()`에는 사용자가 읽고 수정할 수 있는 실제
설정·호출·결과 처리 흐름을 둔다. 일반 C/C++ 계산은 Sketch에 두어도 되지만,
Zephyr header·type과 `bt_*`·`k_*`·`device_*` 직접 호출은 공개 `.ino`에
두지 않는다. 해당 동작은 library 구현과 공개 `NUCODE_*` API가 소유한다.
include-only Sketch 또는 개발 마일스톤(`M31` 등)을 포함한 공개 macro·class·
광고 이름·출력은 예제 완료로 인정하지 않는다. `NUCODE_*` 명칭과 사용자가
이해할 수 있는 역할·설정으로 표현한다.

예제 완료 판정 전에 `tools/ci/m31_example_audit.py`로 모든 설치 예제의
진입점·공개 경계·역할 설정을 전수 검사하고, 변경한 역할별 Sketch를 실제
Arduino target으로 build한다. 기능 HIL과 negative가 필요한 항목은 별도
증거가 있어야 PASS다. 새 공개 예제를 추가할 때 audit 규칙도 함께 확장하며,
검사가 통과하더라도 `.ino`에서 사용자에게 핵심 동작이 보이는지 검토한다.

초보자용 최소 예제, 고급 직접 API 예제, 자동 regression runner는 목적이 다르므로 각 실행 경로와
지원 범위를 설명한다. NCS sample의 모든 내부 helper를 public Arduino API로 승격할 의무는 없다.

## 10. 전체 source·예제 parity 기계 원장

다음 산출물의 생성기·schema·원장·Host 20/20 negative와 local drift gate는 **M31-W01에서 구현해
완료**했다. W08에서는 GitHub Actions 병렬 Windows RC 검증까지 수행했다. M31 capability 원장과 전체
sample 원장은 서로 다른 목적이며 함께 연결한다. 개별 예제 target/Arduino build·기능 HIL은
해당 M31/M32/M33 owner가 완료 전 별도로 닫는다.

- `variants/nu54dk/m31-ble-readiness.json`: M31 기능·고정 test ID·target·runtime 판정.
- `variants/nu54dk/ncs-v3.4.0-bluetooth-sample-parity.json`: 고정 upstream Bluetooth 예제 전수와
  Arduino 제공 경로·owner·개별 증거.
- 전체 원장 schema·수집기·validator·Host positive/negative test와 읽기용 생성 표.
- 기존 coverage 원본/생성기에 새 원장 연결이 필요한지 판정하고 생성 문서의 `--check`로 drift를 검출.
  06번 수동 NCS matrix에는 현재 지원과 계획 원장을 구분해 연결.

### 수집 범위와 누락 방지

1. NCS `samples/bluetooth`, Zephyr `samples/bluetooth`를 재귀 수집한다. 각 `sample.yaml`의
   `tests` key와 configuration variant를 별도 행으로 만들고, sample directory에는 안정적인 상위 key를 둔다.
   Bluetooth tag·의존성이 있는 별도 application/sample는 추가 discovery root와 이유를 기록한다.
2. `common`과 test override를 각각 원본으로 보존하고 적용된 metadata를 계산한다. `platform_allow`,
   `platform_exclude`, `integration_platforms`, `filter`, `depends_on`, `build_only`, `sysbuild`, harness,
   extra args/config/overlay, board qualifier를 기록한다. Metadata가 없으면 `null`; 빈 목록과 혼동하지 않는다.
3. `nrf54l15dk/nrf54l15/cpuapp`를 정확히 매칭한다. 이름에 `nrf54l15dk`가 있어도 L05/L10 qualifier를
   L15 근거로 세지 않는다. `filter` 미평가와 일반적인 allowlist 부재는 미지원 판정이 아니다.
4. sample마다 README·관련 Kconfig/header·board overlay·maturity/controller 근거를 연결한다.
   Symbol-only 기능은 별도 `features` 행으로 등록해 sample 부재가 기능 누락으로 이어지지 않게 한다.
5. SDK 갱신·source 추가/삭제·test ID 변경 시 원장 diff를 생성한다. 과거 행은 이전 revision 이력으로
   보존하고 새 행의 owner 미지정·이유 없는 제외·중복 identity를 gate 오류로 처리한다.

### 필수 schema 필드

| 영역 | 필수 정보 |
| --- | --- |
| 문서 identity | `schema_version`, `generated_from` module/revision, board/toolchain/SDK lock identity, 수집 roots·수집기 version |
| Sample identity | `id`, `upstream_module`, `upstream_path`, `test_id`, `variant_id`, parent sample key, source SHA-256 |
| Upstream metadata | 원본과 해석 결과, target allow/exclude/integration 각각의 nullable 값, build-only/sysbuild/harness/filter·config·overlay |
| Support 판단 | source 발견, nRF54L15 근거, SDC/controller variant, maturity·experimental 근거, target 적용성·판정 이유·근거 경로 |
| Feature 연결 | `feature_ids`, 필수 role·protocol·dependency, owner milestone/work ID, priority, 원본 sample 대체·공유 관계 |
| Arduino 제공 | 기본 `route`와 보조 route, 계획/실제 sketch·profile·library·build matrix ID, public/direct API 경계 |
| 자원·장비 | 최소 보드 수, roles, controller/peer·외부 장비/계정·결선 의존성, RAM/RRAM/slots/buffer 상한 |
| 검증 계약 | 고정 local test ID, timeout/iterations/denominator, metric·단위·수락 조건, negative 기대 오류, 중단/재시험 한도 |
| 책임·차단 정책 | case별 `verification_owner`·`verification_stage`·`development_blocker`·`release_blocker`, 사용자 결정 근거/날짜. 구현/자동 검사와 외부 실물 case를 분리 |
| 개별 결과 | native nRF54L15 build, NU54DK target build, Arduino build, runtime, negative, interoperability 각각 status·exact source/profile·evidence |
| 증거 identity | firmware/image SHA-256, board/submodule·SDK lock, probe SHA-256 identity, role·serial mapping의 익명화된 참조, nonce·attempt ID·raw evidence hash |
| 예외·인계 | `scope_status`, reason, 결정 근거·날짜, external dependency, follow-up owner, 알려진 제한 |

`supported` 같은 boolean 하나로 source·build·runtime을 합치지 않는다. 실행하지 않은 결과에
`PASS`·빈 success evidence를 허용하지 않고, 미확정 측정값은 `null`로 유지하면서 필수 시험 착수 전에
값을 고정하도록 gate를 둔다. 실제 board serial/probe 원문을 원장에 저장하지 않는다.
W01 schema/validator는 이 stage와 source-only 부당 승격을 거부한다. 사용자 후속 Apple/Google·외장 I/O 실물 case는
`verification_owner: user`, `verification_stage: user_follow_up`, `development_blocker: false`,
`release_blocker: false`로 분리하고, 해당 기능의 구현·예제·자동 검사 case는 필수로 유지한다.
Ubuntu/macOS 실물 case는 `verification_owner: user`, `verification_stage: final_release`,
`development_blocker: false`, `release_blocker: true`로 두어 해당 OS 최종 지원 검증을 보존한다.
이 값은 Ubuntu/macOS 지원을 포함할 후속 릴리스의 조건이며 M31 Windows 공개에 적용하지 않는다.
릴리스 gate는 제품선·Host 범위를 먼저 선택해 판정한다. 기존 schema의 필드를 문서 개정으로
구현 완료 또는 면제로 바꾸지 않으며 필요한 판정 도구의 범위 처리는 M31-W08에서 검증한다.
위 필드값은 현행 readiness/parity schema의 계약이다. 외부 실물 `NOT_RUN`과 필수 개발
case를 합치지 않으며, 기능별 외부 경로 구현/검증은 담당 작업에서 계속한다.

### Host unit·negative와 CI 계약

- 정상 metadata·common/test merge·여러 role/variant·nullable field·한글/공백 경로를 검사한다.
- 중복 ID, 누락 sample/test, 잘못된 revision/target qualifier, 잘못된 route/owner, 삭제된 evidence link,
  잘못된 status 전이, source-only의 runtime PASS, `build_only`를 support로 해석하는 입력을 거부한다.
- 사용자 후속 실물 case의 `NOT_RUN`을 PASS로 바꾸거나 개발·릴리스 blocker로 재분류하는 입력,
  구현/자동 검사 case를 사용자 후속으로 숨기는 입력, Ubuntu/macOS 최종 실물 gate를 면제하는 입력을 거부한다.
- HIL parser는 revision/nonce/role mismatch, 누락·중복 결과, timeout·partial transcript,
  unsupported 조합·범위 밖 수치·negative의 예상 외 성공을 fail-closed 처리한다.
- M31 고정 시험 family는 `M31-CAP-01`, `M31-PARITY-01`, `M31-ISO-01`, `M31-AUDIO-01`,
  `M31-DF-01`, `M31-CS-01`, `M31-NEG-01`, `M31-REG-01`, `M31-EXAMPLE-01`, `M31-CLOSE-01`이다.
  위 표의 W03-01~11은 하나의 Audio test 안에서 집계할 기능 묶음이며 전역 test ID 분모에 섞지 않는다.
- CI는 inventory/schema/문서 drift, Host unit/negative, 예제 존재·install lock·Arduino compile,
  target/profile별 build matrix를 검사한다. 실제 native Host 설치·USB/debug/serial과 board runtime은
  해당 evidence가 있을 때만 별도 PASS로 기록한다.

### 분모와 제품선별 release gate

다음 수치를 매번 동시에 출력한다. 고정 source W01 수집 결과는 sample 190, test variant
474, source-only M31 symbol 39, parity 703행이며 pin 변경 시 생성기 `--check`로 다시 대조한다.

- `discovered`: 전체 sample·test variant·source-only feature 각각의 원수.
- `mapped`: owner와 Arduino 제공 경로 또는 근거 있는 제외를 가진 행 수.
- `unresolved`: target 적용성, owner, 제공 경로 중 미판정이 남은 행 수.
- `applicable_required`: nRF54L15/NU54DK에 적용되는 필수 행 수.
- build/runtime/negative/interop의 `PASS`, `FAIL`, `HOLD`, `NOT_RUN`, `NOT_APPLICABLE` 각각의 수.
- 조건부 external 행·사용자 범위 제외·고정 SDK 비적용 행 수와 이유별 합계.
- 구현/자동 검증 필수 case, 사용자 후속 실물 case, 최종 Host 실물 case의 분모와 blocker 수.

`mapped == discovered`와 `unresolved == 0`은 누락 방지 완료 조건이다. 기능 구현 완료율은 적용되는
필수 case의 실제 Arduino build/runtime/negative를 별도로 계산한다. 사용자 후속 실물 case와 범위 제외를 PASS 분자에 더하지 않는다.
공식 nRF54L15 sample 중 필수 경로가 빠졌거나 board-only runtime이 미실행이면 M33 완료로 올리지 않는다.
M31 v0.5.0은 M31 필수 행과 영향 회귀·Windows package/설치·공개 gate로 판정한다. M32·M33
소유의 미착수 행은 후속 상태로 공개하며 M31 완료 분모에 합산하지 않는다. 전체 원장에 owner와
제공 계획이 있다는 사실만으로 해당 기능을 v0.5.0에서 지원한다고 선언하지 않는다.
Apple/Google·외장 I/O의 사용자 후속 실물 시험은 지원표에 `NOT_RUN`으로 드러내며 필수 완료 결과와
합산하거나 M33/릴리스 blocker로 사용하지 않는다. 구현·예제·자동 검사 의무는 유지한다.
Ubuntu/macOS 실제 Host는 해당 OS 후속 릴리스의 사용자 검증까지 지원 gate를 미완료로 유지한다.

## 11. 세 보드 자동 실행과 증거의 경계

M31-W01~W08의 구현·Host/negative·target build·문서·예제와 지원 가능한 board-only 기능 HIL은
자동 실행 흐름으로 설계한다. 세 보드가 모든 RF 역할을 지원한다는 전제는 두지 않는다. 제품 SDC의
DF IQ RX는 고정 SDK 미지원으로 P2 범위에서 제외하며 과거 LL 진단을 자동 재개하지 않는다. USB HCI의 SoC 적용성,
큰 Mesh topology는 별도 근거로 판정하고 외부 audio/Apple/Google 실물 시험은 사용자 후속으로 인계한다.

| 자동화 수준 | 할 일 | 멈추거나 `NOT RUN`으로 남길 조건 |
| --- | --- | --- |
| 보드 없이 가능 | source 조사·schema/parser·Host unit/negative·CI·역할별 native/Arduino build·예제/문서 | SDK/toolchain 접근 실패 등 실제 원인을 기록 |
| 1보드 | capability, codec 합성 loopback, local command·resource·start/stop | probe SHA-256·serial·role·image mapping 미확정 |
| 2보드 | ISO·Audio synthetic 송수신, 기본 안테나 CS, 대부분 GAP/GATT/Nordic 기능 | 제품 SDC DF IQ RX는 미지원·P2 범위 제외. 사용자 후속 외장 실물 경로는 별도 비차단 행 |
| 3보드 | BIS 복수 수신·BASS assistant·CSIP set·다중 peer·Mesh 기본 topology·선택 공존 | 별도 네 번째 역할이나 더 큰 topology가 필수이면 추가 보드 필요 |
| 사용자 후속 | 실제 Apple/Google·외장 audio/I/O·각도용 antenna 구성 | 사용 가능한 구현·예제·안내·자동 검사를 완료하고 실물 행만 `NOT_RUN`으로 인계; 개발·릴리스 비차단 |
| 후속 Host 실물 | Ubuntu/macOS 설치·USB upload·serial·debug·수명주기 | 해당 OS를 포함하는 후속 릴리스 때 사용자 검증. M31 Windows 공개 비차단, 해당 OS 지원 gate 유지 |
| 정밀 계측 | RF tester·전력계·정밀 음질·각도/거리 보정 | 사용자 범위 밖 결과를 PASS로 만들지 않으며 보드 기능 검증의 선행조건으로 요구하지 않음 |

실물 작업 직전에 probe는 원문 UID를 출력·저장하지 않고 SHA-256 identity만 비교한다. 여러 probe 중
임의 선택을 금지하고 firmware revision·image hash·serial/COM·role를 다시 대조한다. 승인된 대상의
sector-only upload, `auto_unlock=false`, probe lock·watchdog·명령 lease·STOP 계약을 사용한다.
mass erase/recover, 전체 flash 초기화, 임의 GPIO, 전원 차단은 자동화에 넣지 않는다.

각 HIL은 실행 전 반복 수·timeout·payload/frame/sequence 분모·허용 손실·복구 한도를 고정한다.
일반적인 필수 무결성 항목인 잘못된 image/role 수용, cross-link payload 수용, 잘못된 보안 수용,
반환하지 않은 자원은 0을 기준으로 하며, 무선 손실 허용량은 기능별 조건과 계산식을 함께 정한다.
실패 attempt의 원본은 보존하고 수정·동일 조건 재시험을 새 attempt로 연결한다. 성공한 마지막 시도만
남기거나 불편한 `HOLD/NOT RUN` 행을 지워 완료 분모를 줄이지 않는다.

## 12. M34~M45로 넘길 산출물

후속 번호·제품선은 유지한다. 다음 표의 입력을 각 착수 계약에서 받아 무선 기능과 보안·저장·network의
누락을 막는다. M31~M33에서 필요한 최소 기능을 전부 미래 마일스톤으로 미루는 의미는 아니다.

| 후속 | M31~M33에서 넘길 구체적 입력 |
| --- | --- |
| M34 Storage·PSA/Cracen·KMU | EAD key/IV·CSIP SIRK·Audio broadcast code·bond·Mesh NetKey/AppKey·DFU key의 식별자, 저장 수명·접근·삭제·migration 요구 |
| M35 TF-M·secure/non-secure | SDC non-secure experimental 판정, radio/crypto/IPC ownership, direct API 경계·fault/복구 영향 |
| M36 layout·MCUboot·다중 DFU | M30 서명/복구 기준선, M32 Mesh DFU/BLOB/distributor 공간·서명·transport, 외장 flash 없는 NU54DK 예산·복구 요구 |
| M37 Security/Update 공개 | 변경된 key/layout/profile의 BLE/Mesh 회귀·예제·지원표와 설치 migration |
| M38 공개 Radio profile | M32 최소 802.15.4/ESB backend, clock/radio/timeslot 자원·release·직접 API 예제 |
| M39 802.15.4·ESB 제품화 | M32 단독 TX/RX·선택 공존 증거, 확대 PHY/channel/topology·예제·negative 목록 |
| M40 OpenThread | 최소 802.15.4 및 BLE 공존 예산, join/UDP/persistence/recovery·commissioning 연결 요구 |
| M41 Radio/Network 공개 | profile 전환·설치·예제 parity, network/공존 적용 조합과 Host matrix |
| M42 Matter provisioning | BLE commissioning transport·보안, Thread 선택 시 M40 근거, partition/factory-data/credential 예산 |
| M43 Matter template·Arduino UX | wrapper/direct/template 경계, NCS 예제 metadata·license·자동 실행·계정 입력 방식 재사용 |
| M44 Matter runtime HIL | controller·fabric/network·reset persistence와 BLE 공존의 실제 peer·장비 matrix |
| M45 Matter 공개 | Bluetooth 기능을 포함한 실제 지원 profile·미실행 interoperability·qualification/certification 경계 |

M31~M33의 기능 동작 PASS는 Bluetooth qualification, Auracast 적합성, Google/Apple 인증 또는
Matter 인증 취득을 뜻하지 않는다. M31과 각 후속 release gate에서 실제 제공할 범위·증거·남은 외부
의존성을 연결하고, 인증이 필요한 제품 주장은 해당 별도 근거가 있을 때만 사용한다.
