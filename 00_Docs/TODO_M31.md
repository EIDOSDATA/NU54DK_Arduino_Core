# M31 실행 TODO — NCS ISO·LE Audio·Direction Finding·Channel Sounding 예제의 Arduino 실행

| 항목 | 내용 |
| --- | --- |
| 대상 제품선 | `v0.5.0` |
| 현재 상태 | **W01~W03 완료, W04·W05 진행 중 / 완료 3/8 작업 묶음** |
| 선행 완료 | M30 W01~W08 8/8, test ID 10/10, 실제 전원 차단 4지점 × 3회 = 12/12 |
| 병행 Host 상태 | HOST-W01~HOST-W03 완료 3/8, HOST-W04~HOST-W08 사용자 지시로 보류; M31과 독립 집계 |
| 기준 SDK | NCS `v3.4.0`, Zephyr `4.4.0`, 고정 lock revision |
| 기능 검증 장비 | 사용자 보유 NU54DK 3개 중 현재 확인·접근 가능한 보드 2개; 3보드 시험은 연결 재확인 전 `NOT RUN`. 실기 직전 SHA-256 probe identity·serial·role·firmware 재대조 |
| 최종 갱신일 | 2026-09-25 |

2026-09-21 결정으로 **M31 완료 후 v0.5.0 Windows 릴리스**를 준비한다. main 이력 정리 이후의
재개 상태는 [HANDOFF](HANDOFF.md)를 따른다. 과거의 설명 통합 요청은 문서만 수정한
시점의 이력이며, 현재는 `M31-MEM-OPT`에서 P0·P1을 완료하고 P2 실기·진단을 진행 중이다.
이후 W04·W05 → W06 → W07 → W08로 이어간다. **진행 중**은 잔여가 있다는 원장 상태이며
현재 시험 실행 중이라는 뜻이 아니다. Host는 보류한다. M32/M33은 후속 버전(미정)이다.

M31의 목표는 **고정 NCS에서 nRF54L15DK에 적용되는 ISO·LE Audio·DF·connected Channel Sounding
기능과 예제를 NU54DK Arduino 환경에서 사용할 수 있게 하는 것**이다. 고수준 Arduino facade,
고급 직접 API, 검증된 profile·template 중 기능에 맞는 제공 경로를 사용한다. 모든 예제를 한 가지
추상화로 감싸는 것은 필수 조건이 아니다.

제품선 순서는 [제품 로드맵](<01_아두이노 코어 설계/02_구현_로드맵.md>), 전체 기능 소유권과
예제 판정 규칙은 [NCS Bluetooth 전체 기능·예제 실행 계약](<01_아두이노 코어 설계/19_NCS_Bluetooth_전체_기능과_예제_실행_계약.md>),
기능별 목표는 [경쟁 마일스톤](<01_아두이노 코어 설계/08_전_인스턴스_DMA_BLE_경쟁_마일스톤.md>),
Host는 [다중 Host 지원 계약](<02_빌드 설계/10_v0.5.0_다중_Host_지원_착수_계약.md>)이 소유한다.
계획 개정 자체는 구현 증거가 아니다. W01~W03 완료와 W04 이후 미완료 범위는
[착수 계약](<01_아두이노 코어 설계/20_M31_Bluetooth_착수_계약.md>)과
[W02 최종 완료 기록](<04_검증 기록/199_M31_W02_격리_설치본_ISO_11예제와_완료.md>),
[W03 최종 완료 기록](<04_검증 기록/214_M31_W03_LE_Audio_Profile_완료.md>)에서 구분한다.

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
8. HOST-W04~HOST-W06은 별도 재개 지시 후 진행한다. Ubuntu/macOS의 실제 설치·USB upload·
   serial/debug·수명주기는 **해당 OS를 지원하는 후속 릴리스에서 사용자 검증**을 수행하고 HOST
   원장과 M33에 인계한다. v0.5.0은 Windows-only이며 이 후속 gate를 기다리지 않는다.
9. **Apple/Google 기능과 mic/speaker/codec 등 외장 장치 경로는 담당 마일스톤에서 사용 가능한 구현·
   예제·설정/연결 안내와 가능한 자동 검사가 필수**다. Apple/Google은 M33-W03, Audio 외장 경로는
   M31-W03이 소유한다. 실제 제품 운용·상호운용·물리 입출력 검증은 사용자 후속 책임이며
   v0.5.0 개발·릴리스 차단 조건이 아니다. 그 실물 결과는 `NOT RUN`으로 보존하고 구현/build PASS와
   구별한다. 빈 template·성공 출력만 있는 stub 또는 구현 결함을 이 범위 결정으로 면제하지 않는다.

## 2. 작업 묶음 — 8개 유지

| 작업 | 상태 | 구현·검증 범위 | 완료 산출물 |
| --- | --- | --- | --- |
| M31-W01 capability·착수 계약 | **완료** | ISO·전체 Audio profile·DF·CS 적용성, SDC와 Zephyr LL의 기본 안테나 raw IQ 수신 구성 조사·target build, 전체 NCS Bluetooth sample inventory, 역할·자원·시험 기준 고정; 1보드 capability 실행 | 두 JSON·schema/parser·Host 20/20 negative·전체 Host gate·5구성 clean target/HCI query, parity 703행; [W01 exact audit](<04_검증 기록/evidence/m31-w01-exact-8c125a22/w01-closure-audit.json>) |
| M31-W02 raw ISO 기반 | **완료** | 공개 `RawCis`/`RawBis` 기반 **11개 역할**의 사용자 payload와 정지·재시작을 각 20회 실기 PASS. 잘못된 Broadcast Code의 유효 SDU 유출 0, 같은 image의 정상 Code 복구 100/100, 강제 sync loss 후 새 session 100/100. 독립 Sketchbook 개발 package 485파일 무결성·고정 prerequisite·11/11 예제 발견·빌드와 같은 revision의 두/세 보드 11역할 실기 20회씩 PASS. 공개 예제 감사 82개 중 0건 | [W02 최종 완료](<04_검증 기록/199_M31_W02_격리_설치본_ISO_11예제와_완료.md>)·[완료 audit](<04_검증 기록/evidence/m31-w02-installed-examples-b47aaf40/closure-audit.json>)·[오류 후 복구](<04_검증 기록/197_M31_W02_공개_API_암호화_BIS_오류_후_복구.md>)·[sync loss 재시작](<04_검증 기록/198_M31_W02_공개_BIS_sync_loss_재시작_복구.md>)·[이전 고정 시험 audit](<04_검증 기록/evidence/m31-w02-arduino-e6ae812e/closure-audit.json>) |
| M31-W03 전체 LE Audio profile | **완료** | W03-01~11의 공개 Arduino 역할과 적용 가능한 native 기반을 모두 닫았다. BAP unicast/broadcast·BASS·CAP·CSIP·PBP·VCP/VOCS/AICS/MICP, MCP/MCS·CCP/TBS, TMAP/GMAP, HAP/HAS의 build/runtime·negative·peer-loss 복구와 합성 PCM RF data path를 실제 2~3보드에서 확인했다. Media/Call은 각 100/100·negative 각 20/20·reconnect 20/20·180초 soak, TMAP/GMAP은 각 180초·stop/restart 20/20·drop 0, HAP/HAS는 preset 100/100·두 negative 각 20/20·복구 20/20이다. 외장 audio·상용 peer·qualification·의료/음향 성능은 사용자 후속 비차단 `NOT RUN`이며 M31 전체는 W04~W08 잔여로 `not_completed`다 | [native BAP LC3](<04_검증 기록/181_M31_W03_native_BAP_LC3_실제_무선_전송.md>)·[BAP broadcast](<04_검증 기록/202_M31_W03_Arduino_BAP_broadcast_암호화와_negative_완료.md>)·[BASS](<04_검증 기록/203_M31_W03_Arduino_BASS_3역할과_복구.md>)·[CAP](<04_검증 기록/205_M31_W03_Arduino_CAP_unicast_반복_실기.md>)·[Audio Control](<04_검증 기록/208_M31_W03_Arduino_Audio_Control_완료.md>)·[CSIP](<04_검증 기록/209_M31_W03_Arduino_CSIP_완료.md>)·[PBP](<04_검증 기록/210_M31_W03_Arduino_PBP_완료.md>)·[Media/Call](<04_검증 기록/211_M31_W03_Arduino_Media_Call_Control_완료.md>)·[TMAP/GMAP](<04_검증 기록/212_M31_W03_Arduino_TMAP_GMAP_완료.md>)·[HAP/HAS](<04_검증 기록/213_M31_W03_Arduino_HAP_HAS_완료.md>)·[W03 완료 감사](<04_검증 기록/214_M31_W03_LE_Audio_Profile_완료.md>)·[exact closure](<04_검증 기록/evidence/m31-w03-close-dc312cce/closure-audit.json>) |
| M31-W04 Direction Finding | **진행 중** | CTE TX 20회·연결 응답 stop/restart 20회와 내부 Zephyr LL 연결형 IQ 20 report·1,640 sample 및 cleanup을 국소 확인했다. connectionless sync는 CTE-only 옵션·active scan 재진단에도 실패·IQ 0이며 수신 usage fault를 보존한다. 공개 Arduino/SDC RX·각도 계산은 미완료다. | [연결형 IQ](<04_검증 기록/244_M31_P2_DF_연결_IQ_진단.md>) · [연결형 메모리](<04_검증 기록/246_M31_P2_DF_연결_IQ_메모리_계측.md>) · [connectionless 실패](<04_검증 기록/247_M31_P2_DF_connectionless_재진단과_보류.md>) · [active scan 후속](<04_검증 기록/250_M31_P2_native_CS_비교와_DF_재진단.md>) |
| M31-W05 connected Channel Sounding | **진행 중** | secure ACL·raw RAS 100개와 stop/restart·disconnect/reconnect 각 20/20을 확인했다. 간헐 counter 누락은 500건 × 2 국소 PASS 뒤에도 1,000건 장기 시험에 남는다. 후속 진단에서 실제 256-step·분할 RAS 정상 경로 10/10을 확인했지만 같은 image의 100건에는 counter gap 1이 남았다. flash 직후 중단의 단일 원인·wrong-key negative 역시 잔여다. 비보정 RTT의 정확도는 미보증이다. | [비암호화 거부](<04_검증 기록/217_M31_W05_비암호화_RAS_ATT_오류_진단.md>) · [flash 직후 복구](<04_검증 기록/218_M31_W05_flash_직후_RAS_복구_재검증.md>) · [장기 누락 진단](<04_검증 기록/245_M31_P2_CS_장기_연속성_진단.md>) · [256-step·분할 RAS](<04_검증 기록/255_M31_P2_CS_256_step_분할_RAS_진단.md>) |
| M31-W06 자원·수명주기·회귀 | **미착수(사전 메모리 감사만 완료)** | 독립 role image별 RAM/RRAM·stack·buffer·stream/connection 예산, stop/disconnect 뒤 callback·link·radio 자원 회수, M19~M30 영향 회귀. 고점유 image의 공통 정적 예약은 W04·W05 마감 전에 최적화 | [219번 계약](<04_검증 기록/219_M31_W06_메모리_점유_감사와_최적화_계약.md>): main 문서 반영 → `M31-MEM-OPT` 최적화 → W04·W05 잔여·영향 재검증 → W06 manifest·회귀. 네 기능 전체 동시 실행은 완료 조건이 아님 |
| M31-W07 기능 HIL·예제 실행 | **미착수** | 3보드 역할 재배치로 적용 가능한 모든 board-only subcase 유한 실행, Arduino 설치 예제의 실제 실행; 외부 peer 행 별도 관리 | exact image·익명 mapping·transcript·원본 hash, 기능/role별 PASS·FAIL·NOT RUN·UNSUPPORTED 근거 |
| M31-W08 마감·Windows 릴리스 준비 | **미착수** | API·예제·지원표·문서·원장 일치, Host/target 회귀, M31 8/8 판정과 v0.5.0 Windows 패키지·설치·RC 준비. M32/M33은 후속 버전으로 인계 | 기능 완료와 공개 판정 별도. [v0.5.0 공개 gate](TODO_v0.5.0.md#6-결과공개-규칙), known limits·후속 dependency; 실제 공개는 별도 승인 |

M32-A는 modern LE controller/Host·Nordic 확장, M32-B는 Mesh와 Mesh 1.1, M32-C는 최소 radio와
공존을 맡는다. M31-W01에서 발견하는 Power Control/Path Loss, subrating, SCA/frame-space/shorter
interval, 다중 advertising/identity, EAD, LLPM/QoS 등은 전체 원장에 등록하고 M32-A로 연결한다.
추가 GATT service·Fast Pair/Apple peer·DTM/HCI 예제의 catalog와 패키징은 M33에 인계한다.

### W06 범위 해석

W06의 `통합`은 ISO·Audio·DF·CS를 한 image에서 모두 활성화해 동시에 무선 실행한다는 뜻이
아니다. Audio-over-ISO처럼 기능 정의상 결합된 경로는 해당 W02/W03 근거를 재사용하고, DF와 CS는
각 controller/profile의 독립 role image로 유지한다. W06은 각 image의 자원 상한과 종료·재시작·
disconnect 뒤 상태 정리, 공통 Core 변경의 M19~M30 회귀를 확인한다. 동시 실행은 실제 제품 요구와
controller 지원 근거가 따로 고정된 조합에만 별도 subcase로 추가하며, 그런 조합이 없다는 이유로
W06을 미완료로 두지 않는다.

W06 자원 gate는 현재 고점유 수치를 기준선으로 승인하지 않는다. `NUCODE_BLE`의 종합
feature fragment와 `ble` profile이 역할에 필요하지 않은 범용 GATT/L2CAP, advanced GAP,
Arduino peripheral route와 pin ownership state를 포함하는 구조를 먼저 분리한다. full profile의
공개 API 호환성은 유지하고 lean role image에서 source-level 제외와 right-sized pool을 검증한다.
기존 수치·상위 회귀 gate는 [219번 기록](<04_검증 기록/219_M31_W06_메모리_점유_감사와_최적화_계약.md>),
두 설명의 정정과 실제 수정 순서·완료 체크리스트는
[메모리 최적화 통합 설계](<01_아두이노 코어 설계/21_M31_메모리_최적화_통합_설계.md>)를 따른다.
링크 GC만으로 모든 미사용 자원이 제거되거나 CS 50~80KB/50~100KB 절감이 보장된 것으로 해석하지 않는다.
최신 사용자 목표는 동등 기능 nRF native에 우리 API의 최소 필수 비용만 더하는 선언 기반 기본 경로다.
기존 full은 명시적 호환 선택지로 보존하며 일부 BLE 예제만 작게 만드는 것으로 전체 최적화를 닫지 않는다.
Core API는 compiler-assisted capability probe, library 간접 요구는 feature manifest, BLE 역할·용량은
공개 preset/declaration으로 판정해 생성 config/overlay/source에 연결한다. P1은 Core SPI를
50,877→20,589 B로 줄였고, CoC-only 역할에서 NUCODE 범용 GATT facade를 분리해
91,037→70,081 B로 줄였다. 동일 1×1 fixture의 GATT schema·client context·event/TX/inline value를
실제 선언 용량에 연결해 113,218→59,338 B로 줄였다. 이어 generic GATT를
server-only/client-only role로 분리해 동일 server fixture를 48,653 B, 실제 Peripheral을
48,835 B, Central을 53,478 B로 줄였다. 이어 shared TX pool을 선언 용량에 연결해
server fixture를 48,581 B, Peripheral을 48,763 B로 줄였다. GATT client read/write
버퍼도 선언 용량에 연결해 실제 Central의 RAM을 53,478→52,582 B로 줄였다.
P1의 GAP·L2CAP·ISO·CS 잔여 고정 저장소와 역할별 포함 여부까지 감사하고
GATT 방향·CS 전용 pool의 ELF 회귀 문턱을 추가했다. P1 정적 구조는 완료했으며,
stack/heap/controller pool과 burst queue depth는 P2 실물 high-water 및 오류·복구
부하를 측정한 뒤에만 조정한다.
P2 GATT 512 B는 두 보드에서 adaptive 선언만으로 write/read·재연결 20/20,
수신 20/20, STOP 20을 통과했다. [238번 기록](<04_검증 기록/238_M31_메모리_최적화_P2_GATT_실기와_Adaptive_정정.md>)에
계측 분모와 실패 진단을 남겼다. 당시 미계측 역할과 controller pool은
HOLD였다. 후속 [239번 기록](<04_검증 기록/239_M31_메모리_최적화_P2_CoC_CS_계측.md>)의
CoC 두 채널 512 B echo 100건은 PASS다. [251번 재연결 계측](<04_검증 기록/251_M31_P2_CoC_재연결_메모리_계측.md>)은
ACL disconnect/reconnect 20/20과 서버 SWD reset 20/20, 각각 매회 두 채널
준비·누적 echo 42건·양측 STOP을 확인했다. 물리 전원 차단·credit 고갈·다중
link 및 controller 내부 사용 최고치는
별도다. CS raw 100개는 계측 실행에서
counter 누락이 있었으나 후속 연속 100개·양측 STOP은 국소 PASS이며
간헐 누락 원인은 HOLD다. [245번 장기 진단](<04_검증 기록/245_M31_P2_CS_장기_연속성_진단.md>)에서
controller의 CS sync abort와 정상 완료 후 결과 누락을 분리했다. abort 후
로컬 잠금 해제·늦은 RAS 보호 수정으로 500개 연속 실행 두 번은 PASS했지만,
관찰 배열 없는 1,000개 실행에는 누락이 남았다. 후속 subevent abort 분리
수정의 1,000개 실행에서도 두 곳의 누락이 남아 CS 전체는 HOLD다.
추가 로컬 버퍼를 두 개로 늘린 1,000개 시험도 두 곳의 누락이 남고 정적 RAM이
4,380 B 증가해 후보 변경을 되돌렸다. [245번](<04_검증 기록/245_M31_P2_CS_장기_연속성_진단.md>)의
counter별 RAS 도착 순서 진단이 우선이다.
[250번 native 비교](<04_검증 기록/250_M31_P2_native_CS_비교와_DF_재진단.md>)에서
고정 Nordic RAS 계측 복사본도 1,000개 유효 RAS에 gap 4건과 7건을 보였다.
절대 0-gap은 양 경로의 무선·단일 버퍼 현실을 반영하지 못하지만, Arduino의
정상 callback 뒤 누락·불완전 raw 및 동일 기능/설정 RAM 비교는 여전히 잔여다.
[252번 장절차 경계](<04_검증 기록/252_M31_P2_CS_장절차_반복계수_경계_진단.md>)의
두 진단 image는 raw 각 10건을 통과했으나 실제 93~98 step이어서 최대
256-step·분할 RAS 검증으로 승격하지 않는다. 기본 image 복구 100건·양측
STOP도 별도로 확인했다.
[255번 채널맵 반복 진단](<04_검증 기록/255_M31_P2_CS_256_step_분할_RAS_진단.md>)에서는
실제 256-step·분할 RAS 정상 수신 10/10을 처음 확인했다. 같은 진단 image의
100건은 모두 256-step이지만 counter gap 1로 연속성 HOLD였고, 기본 image
복구 100건·양측 STOP은 PASS였다. 분할 손실·재전송/재연결과 장기 최악 부하는
여전히 미검증이다.
[240번](<04_검증 기록/240_M31_메모리_최적화_P2_ISO_CIS_BIS_실기_계측.md>)에서
CIS·BIS 기본 100 SDU × 20세션도 각각 PASS했다.
[241번](<04_검증 기록/241_M31_메모리_최적화_P2_Audio_unicast_실기_계측.md>)의
unicast PCM/LC3/CIS 1,000 frame과 동일 image의 연속 10,000 frame도
drop 0·양측 STOP으로 국소 PASS했다. 정상 장기 부하와 별도로 수행한
후속 [254번 재연결 계측](<04_검증 기록/254_M31_P2_Audio_unicast_재연결_메모리_계측.md>)은
adaptive source의 재연결 scan 결함을 수정하고 source SWD reset 20/20,
sink 누적 decode 2,933·drop 0·양측 STOP을 확인했다. 기존 실패 두 건은
보존했으며 물리 전원 차단·다중 ASE 결과가 아니다.
[243번](<04_검증 기록/243_M31_메모리_최적화_P2_Audio_broadcast_실기_계측.md>)의
암호화 broadcast LC3/BIS 1,000 frame은 최종 image로 8/8회 국소 PASS했다.
동일 image의 연속 10,000 frame도 drop 0·양측 STOP으로 국소 PASS했다.
이 단일 장시간 실행으로 sync loss·재가입을 입증하지 않으며 최초 sink
동기화 실패 원인은 미확인이다. 후속 [253번 재가입 메모리 계측](<04_검증 기록/253_M31_P2_Audio_broadcast_재가입_메모리_계측.md>)은
source SWD reset 뒤 sink 공개 API 재가입 20/20, 누적 LC3 decode 2,107·drop 0·양측
STOP을 확인했다. 매 reset의 기존 sink session 실패 보고는 복구 성공과 구별한다.
sink MPSL Work 관찰 여유는 264 B라 stack을 줄이지 않는다. [242번](<04_검증 기록/242_M31_메모리_최적화_P2_DF_beacon_TX_계측.md>)에서
DF beacon TX 20회는 국소 PASS했지만 해당 실행에서 IQ RX는 관찰하지 않았다.
후속 [244번](<04_검증 기록/244_M31_P2_DF_연결_IQ_진단.md>)에서 Zephyr LL
내부 연결형 IQ report 20건·1,640 sample과 cleanup을 확인했다. 이는
Arduino/SDC 또는 connectionless RX를 대체하지 않는다.
[246번](<04_검증 기록/246_M31_P2_DF_연결_IQ_메모리_계측.md>)에서 같은 내부 LL
진단 경로의 역할별 stack high-water를 추가했지만 공개 RX·오류/장기 부하의
메모리 안전 여유는 아직 확인하지 못했다.
[247번](<04_검증 기록/247_M31_P2_DF_connectionless_재진단과_보류.md>)의
connectionless 재진단에서는 연속 송신으로 바꿔도 periodic sync가 성립하지 않아
IQ 0건이었다. 종료 경로의 기존 종류 fault와 안전 복구를 보존했으며,
connectionless 수신·그 역할의 high-water는 HOLD다.
[250번 후속](<04_검증 기록/250_M31_P2_native_CS_비교와_DF_재진단.md>)의 CTE 전용 sync 옵션을
넣은 재시험도 IQ 0, 반복 시 수신 usage fault·STOP 실패였다. 검증된 CS image
복구 100건·양측 STOP 뒤에만 추가 시험을 했다.
locator 원본의 active scan까지 맞춘 별도 image 단일 실기도 같은 timeout·IQ 0·
수신 usage fault였다. 실패 image를 재실행하지 않고 sector 복구한 native CS
image에서 RAS 100건·양측 STOP을 다시 확인했다.
[248번 SDC pool 감사](<04_검증 기록/248_M31_P2_SDC_pool_정적_경계_감사.md>)는
8개 역할 ELF의 SDK 계산·정렬 예약과 초기화 요구량 검사 경계를 확인했다.
이는 controller 내부 사용 최고치가 아니므로 pool을 임의 축소하지 않는다.
이 관찰값만으로 P2 전체를 완료 처리하거나 stack/heap을 축소하지 않는다.
`SPI.begin()` 사용자에게 SPI용 `prj.conf`를 수동 작성하게 하는 상태도
최적화 완료가 아니다.

P2의 남은 gate는 다음처럼 분리한다.

| 축 | 아직 필요한 증거 |
| --- | --- |
| DF RX | 연결형 Zephyr LL 내부 IQ callback·sample 20건과 정상 종료 뒤 stack high-water는 확인. connectionless sync는 CTE 전용 옵션·active scan을 써도 미수립·IQ 0이며 수신 fault·STOP 실패를 보존. Arduino/SDC RX 적용성, 오류/복구·장기 high-water는 잔여. Beacon TX로 대체 불가. [246번](<04_검증 기록/246_M31_P2_DF_연결_IQ_메모리_계측.md>) · [250번](<04_검증 기록/250_M31_P2_native_CS_비교와_DF_재진단.md>) |
| CS | 일부 누락은 controller의 `NO_CS_SYNC_RECEIVED`, 나머지는 정상 완료 뒤 RAS/단일 로컬 버퍼 결합 경로로 분리. Nordic native 계측 1,000 유효 RAS에서도 abort 2·busy 2·gap 4로 무조건 0-gap 판정은 부적절함을 확인. 진단 image의 실제 256-step·분할 RAS 정상 수신 10/10은 확인했으나 100건에서 gap 1이 남았다. Arduino 정상 callback 뒤 누락 원인과 최대 절차의 segment 손실·재전송·복구 및 장기 최악 부하의 용량/연속성은 잔여. [245번](<04_검증 기록/245_M31_P2_CS_장기_연속성_진단.md>) · [250번](<04_검증 기록/250_M31_P2_native_CS_비교와_DF_재진단.md>) · [255번](<04_검증 기록/255_M31_P2_CS_256_step_분할_RAS_진단.md>) |
| Audio/ISO | unicast source SWD reset 뒤 sink 재연결 20/20·drop 0, 암호화 broadcast source SWD reset 뒤 sink 공개 API 재가입 20/20·drop 0은 확인. broadcast 첫 sync 실패 원인은 미확인. 다른 방향·다중 stream/ASE, 암호화 오류·물리 전원 차단과 장기 부하의 역할별 최악값은 별도. [253번](<04_검증 기록/253_M31_P2_Audio_broadcast_재가입_메모리_계측.md>) · [254번](<04_검증 기록/254_M31_P2_Audio_unicast_재연결_메모리_계측.md>) |
| CoC 복구 | ACL 명시적 disconnect/reconnect 20/20과 서버 SWD reset 20/20, 두 채널 512 B echo·stack/heap 관찰은 확인. 물리 전원 차단·credit 고갈·다중 link의 오류/복구와 최악 고점유는 별도. [251번](<04_검증 기록/251_M31_P2_CoC_재연결_메모리_계측.md>) |
| SDC/stack/heap | SDK 계산·8-byte 정렬 pool과 초기화 요구량 검사 경계는 확인. controller 내부 high-water는 미노출이며 오류·최악 부하 stack/heap 안전 여유는 별도. [248번](<04_검증 기록/248_M31_P2_SDC_pool_정적_경계_감사.md>) |
| native 비교 | 고정 Nordic 원본/계측 sample을 동일 board에서 build하고 RAS gap 경로를 비교했으나 DSP·stack·malloc·로그·payload 조건이 달라 Arduino API 비용은 아직 산정 불가. 동일 기능·설정의 native 대비 FLASH/RAM 항목별 차이가 잔여. [250번](<04_검증 기록/250_M31_P2_native_CS_비교와_DF_재진단.md>) |

## 3. W03 세부 완료 상태 — 11/11

아래 `W03-01`은 Arduino codec 내부 loopback과 Arduino source→sink의 실제 ISO LC3
encode/decode까지, `W03-02`는 native unicast 양방향 ISO 및 Arduino source/sink
단방향 전송·sink 재시작 회복 20회, 명시적 stop/release 20회와 중단 중 잘못된
상태 전이 거부 40회, 원격 ASCS unsupported codec·invalid QoS 거부 각 20회와
idle ASE Release 잘못된 상태 거부 20회, Arduino 양방향 client↔server
LC3 각 방향 1,000 frame과 stop/release·재연결 20/20까지 완료했다.
`W03-03`은 암호화 broadcast LC3, 명시적 stop/restart, wrong code 거부·정상 code 복구,
source hardware-reset sync loss와 재가입을 각각 20/20 확인했다. `W03-04`는 source,
Broadcast Assistant, Scan Delegator sink 3역할의 add/modify/remove, receive-state notification,
invalid/duplicate 거부, peer loss 복구와 180초 연속 stream을 완료했다. W03-05 CAP,
W03-06 CSIP, W03-07 PBP, W03-08 VCP/VOCS/AICS/MICP, W03-09 Media/Call Control,
W03-10 TMAP/GMAP, W03-11 HAP/HAS까지 모두 완료했다.
각 행은 source·target·Arduino build·runtime·negative
상태를 독립적으로 가진다. role 이름만 제공하는 빈 예제나 단일 BAP 성공으로 전체 profile을
완료하지 않는다. 고정 SDK에서 nRF54L15 지원성이 불명확한 profile은 source candidate부터 검증한다.

| 하위 작업 | 구현할 기능과 역할 | Arduino 예제·실제 기능 판정 |
| --- | --- | --- |
| W03-01 LC3·stream data | **완료.** LC3 encode/decode, codec capability·configuration, frame/sample rate/SDU/buffer 계약, 합성 PCM과 encoded source/sink | 합성 신호 → encode → ISO → decode, source→sink 1,000 frame·drop 0, peer 재시작 복구 20/20; lossy codec에 원본 PCM byte 동일성을 요구하지 않음 |
| W03-02 BAP unicast·PACS/ASCS | **완료.** Unicast Client/Server의 Audio Source/Sink, PACS·ASCS, 단방향·양방향 구성 | 양방향 각 1,000 frame, stop/release·재연결 20/20, 잘못된 ASE 상태/codec/QoS 거부; [190번 기록](<04_검증 기록/190_M31_W03_Arduino_BAP_양방향_클라이언트_및_회귀.md>) |
| W03-03 BAP broadcast | **완료.** Broadcast Source/Sink, BIG/BIS 선택·sync·metadata, broadcast code와 암호화, 재동기 | [source](../libraries/NUCODE_BLE_Audio/examples/BapBroadcastSource/BapBroadcastSource.ino) / [sink](../libraries/NUCODE_BLE_Audio/examples/BapBroadcastSink/BapBroadcastSink.ino); LC3 stream·wrong code 거부·sync loss 재가입 20/20, [완료 기록](<04_검증 기록/202_M31_W03_Arduino_BAP_broadcast_암호화와_negative_완료.md>) |
| W03-04 BASS | **완료.** Broadcast Audio Scan Service, Scan Delegator, Broadcast Assistant, receive state notification·source add/modify/remove. 공개 3역할 제어 100/100, invalid/duplicate 각 20/20 거부, Delegator hardware-reset 복구 20/20, 180초 LC3 17,500 frame 증가·drop 0 | [source](../libraries/NUCODE_BLE_Audio/examples/BapBroadcastSource/BapBroadcastSource.ino) / [assistant](../libraries/NUCODE_BLE_Audio/examples/BapBroadcastAssistant/BapBroadcastAssistant.ino) / [delegator-sink](../libraries/NUCODE_BLE_Audio/examples/BapBroadcastDelegatorSink/BapBroadcastDelegatorSink.ino); [완료 기록](<04_검증 기록/203_M31_W03_Arduino_BASS_3역할과_복구.md>) |
| W03-05 CAP | **완료.** Initiator/Acceptor/Commander, broadcast와 single-member unicast, cancel·원격 완료 실패·handover | broadcast 102/102, unicast start/stop 23회·cancel 22회·재연결 48회·LC3 1,800 frame·drop 0, 원격 완료 실패 20/20와 정상 image 복구; [CAP unicast 기록](<04_검증 기록/205_M31_W03_Arduino_CAP_unicast_반복_실기.md>) |
| W03-06 CSIP | **완료.** Coordinated Set Member/Coordinator, set discovery·membership·rank·lock/release. 세 보드 7/7 scenario, valid state/operation report 101건, wrong rank/SIRK/state·security·watchdog fail-closed, member hardware-reset 재가입·lock/release 20/20 | [coordinator](../libraries/NUCODE_BLE_Audio/examples/CsipSetCoordinator/CsipSetCoordinator.ino) / [member](../libraries/NUCODE_BLE_Audio/examples/CsipSetMember/CsipSetMember.ino); [완료 기록](<04_검증 기록/209_M31_W03_Arduino_CSIP_완료.md>) |
| W03-07 PBP | **완료.** Public Broadcast Profile source/sink, public announcement·metadata·broadcast discovery/selection. 180.003초·17,700 frame 증가·drop 0, stop/restart·wrong code·unsupported quality·sync loss 20/20 | [source](../libraries/NUCODE_BLE_Audio/examples/PublicAudioBroadcastSource/PublicAudioBroadcastSource.ino) / [sink](../libraries/NUCODE_BLE_Audio/examples/PublicAudioBroadcastSink/PublicAudioBroadcastSink.ino); Auracast 명칭 승인·qualification·상용 peer 상호운용은 미주장. [완료 기록](<04_검증 기록/210_M31_W03_Arduino_PBP_완료.md>) |
| W03-08 VCP·VOCS·AICS·MICP | **완료.** Volume Controller/Renderer, volume offset, Audio Input Control, Microphone Controller/Device. 정상 control report 273건, invalid range 3종 상태 불변, device hardware-reset 복구 20/20·각 30초 이내 | [controller](../libraries/NUCODE_BLE_Audio/examples/AudioControlController/AudioControlController.ino) / [renderer·microphone device](../libraries/NUCODE_BLE_Audio/examples/AudioControlDevice/AudioControlDevice.ino); 실제 음향·상용 peer·qualification은 별도. [완료 기록](<04_검증 기록/208_M31_W03_Arduino_Audio_Control_완료.md>) |
| W03-09 MCP/MCS·CCP/TBS | **완료.** Media Control과 Call Control client/server 공개 예제 | 각 profile 정상 100/100, negative 각 20/20, recovery 40, reconnect 20/20, 180초 soak와 notification 확인; 실제 미디어/전화 연결은 미주장. [완료 기록](<04_검증 기록/211_M31_W03_Arduino_Media_Call_Control_완료.md>) |
| W03-10 TMAP·GMAP | **완료.** TMAP·GMAP unicast/broadcast 역할·feature 조합 | synthetic PCM 각 180초, stop/restart 20/20, unicast reconnect 20/20, 역할·품질 불일치 거부·drop 0; 실제 전화기·게임 제품 상호운용은 외부 peer 행. [완료 기록](<04_검증 기록/212_M31_W03_Arduino_TMAP_GMAP_완료.md>) |
| W03-11 HAP/HAS | **완료.** Hearing Access client/server preset 조회·선택·변경/알림과 coordinated operation | preset 100/100, invalid index·동기 요청 거부 각 20/20, bond 초기화 뒤 복구 20/20; 의료·음향 성능이나 실제 보청기 상호운용은 미주장. [완료 기록](<04_검증 기록/213_M31_W03_Arduino_HAP_HAS_완료.md>) |

각 행의 다음 점검 항목을 완료했다.

- [x] 고정 upstream sample 경로·test ID·Kconfig·nRF54L15 allow/integration/build-only와 license 기록
- [x] 필요한 controller·Host feature·RAM/RRAM·link/ASE/BIS/codec 자원을 profile별로 고정
- [x] `wrapper`, `direct`, `profile`, `template` 중 제공 경로 선정; 미지원은 근거·후속 소유자 기록
- [x] 최소 시작 예제와 역할별 상대 예제, 오류·해제·재시작 예제를 만들고 Arduino 설치 목록에 등록
- [x] Serial로 role/command를 제어해 버튼·물리 audio 입력 없는 재현 경로와 예상 출력을 문서화
- [x] Host semantic/negative → native/Arduino build → 적용 가능한 2~3보드 기능 HIL 순서로 판정
- [x] 외부 mic/codec/speaker, 상용 phone/headset 확장 경로의 구현·예제·설정/연결 안내·가능한 자동 검사와 사용자 후속 실물 `NOT RUN` 경계를 기록

## 4. 기존 착수 순서와 재개 기준

W01~W03은 이 순서로 완료했다. 1~7번의 원장·기준선은 보존하며 재구현하지 않는다.
후속 기능 개발 재개 시 먼저 219번 메모리 최적화를 수행하고, 최적화 image로 8번과 §2의
W04/W05 잔여를 대조한다. 과거 착수 절차를 현재 미완료 TODO로 다시 집계하지 않는다.

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
   Ubuntu/macOS 실물은 `user`/`final_release`/`false`/`true`로 구분한다. 이 gate의 적용 범위는
   해당 OS를 포함하는 후속 릴리스이며 Windows-only v0.5.0이 아니다. 구현·예제·자동 검사 case는
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
   profile별 자원을 분리한다. HOST-W04 Ubuntu prerequisite·resolver·launcher는 현재 보류 상태다.

## 5. 예제 품질과 설치 계약

- [ ] 예제마다 목표 기능·upstream origin·필요 보드 수·역할·profile 선택·실행 순서·예상 Serial 출력 명시
- [ ] 최소 예제, 상대 역할 예제, negative/recovery 예제를 기능에 맞게 제공; 이름과 경로는 원장에서 고정
- [ ] Arduino `setup()`/`loop()` 경로에서 실제 `NUCODE_*` 공개 API 호출; Zephyr/NCS 호출은 library `.cpp`/`src/internal`에 두고 고급 예제의 Kconfig 설정을 설명
- [ ] queue/buffer 수명, error 처리, timeout, 종료·재시작, 자원 반환을 예제에 포함하고 busy-loop 회피
- [ ] 한국어 Doxygen·BSD/Allman·탭 폭 4·모든 제어문 중괄호 적용
- [ ] clean Arduino package 설치의 example discovery → compile → role firmware → Serial oracle를 연결
- [ ] Kconfig profile과 build options를 코드 밖의 검증된 설정으로 제공하고 임의 SDK patch 요구 금지
- [ ] 실험적·미지원·사용자 후속 실물 검증의 책임·비차단 범위를 example README와 parity 원장에 일치시킴

M31-W07/W08은 v0.5.0에 채택한 M28~M31 예제의 Windows 설치·발견·compile·실행과 배포 준비를
닫는다. M33은 후속 버전의 추가 GATT/profile·template와 전체 NCS catalog, 세 Host 확장 검증을
맡는다. M31 예제 패키징을 M33으로 미뤄 v0.5.0 배포 gate를 생략하지 않는다.

## 6. HOST-W04~HOST-W06 TODO — 사용자 지시로 보류

아래는 재개 후 수행할 계획이다. W04~W08의 구현 상태는 미착수이며 현재 실행하지 않는다.

| Host 작업 | 구현 상태 | 재개 후 할 일 | 증거 경계 |
| --- | --- | --- | --- |
| HOST-W04 prerequisite | **미착수** | Ubuntu 24.04+ AMD64부터 OS/arch별 nRF Util·sdk-manager·NCS·Zephyr·toolchain·Arduino CLI URL/hash/revision manifest; Linux resolver·launcher·실행 권한·serial/USB path·udev 조건과 negative | 정적/Ubuntu CI/unit와 실제 PC clean 설치·USB upload·serial/debug를 별도 칸으로 기록 |
| HOST-W05 portable path/cache | **미착수** | 경로 구분자·executable 탐색·XDG cache, lock·case sensitivity·symlink·execute bit·공백·한글·긴 경로·atomic replace·권한 실패 | 해당 OS native CI/build 증거와 실제 사용자 Host 설치·권한 증거 분리 |
| HOST-W06 package·CI | **미착수** | 세 Host metadata·launcher·archive mode, clean package와 전체 예제 compile matrix·artifact 비교 | native runner의 실제 실행 범위만 PASS, mock/cross-build 결과를 실물 Host PASS로 승격 금지 |

HOST 전체는 **W01~W08의 독립 분모**를 유지한다. 현재 3/8 완료이며 “W04~W08 잔여”는
HOST-W04~HOST-W08을 뜻한다. 실제 Ubuntu/macOS 설치·USB upload·serial/debug·lifecycle는
사용자가 해당 OS를 포함하는 후속 릴리스 단계에서 수행한다. 그 전에는 해당 실물 행을 `NOT RUN`으로 남기며 M31의
필수 firmware gate에 합산하지 않는다. HOST-W07의 사용자 결과와 HOST-W08의 전체 Host 마감은
후속 M33 공개 조건으로 이어진다. Windows-only v0.5.0 공개에는 적용하지 않는다.
Apple/Google 및 외장 I/O의 사용자 후속 검증은 이 최종 Host gate와 달리
개발·릴리스 차단 조건이 아니다.

## 7. 보드 3개 자동화 범위와 다음 개입 지점

| 단계 | 자동으로 진행할 범위·최소 보드 | 미실행·사용자 후속 범위와 책임 |
| --- | --- | --- |
| W01 | source·원장·parser·target, 확인된 NU54DK 1개 capability HIL | probe/serial mapping 불일치·USB 접근 권한·board 미연결 |
| W02 | 2개 CIS/BIS 기본, 3개 복수 receiver·적용 가능한 combined ISO·time sync | 고정 controller/자원 한계가 의도한 역할 조합을 허용하지 않을 때 별도 판정 |
| W03 | 2~3개 합성 PCM/encoded payload와 Audio profile 제어·상태·실제 RF data path; 외장 I/O 구현·예제·설정 안내와 자동 검사 | 외부 mic/codec/speaker·상용 phone/headset의 실물 운용/상호운용은 사용자 후속 `NOT RUN`, 개발·릴리스 비차단 |
| W04 | 1개 CTE TX 설정·시작/중지·controller event; 기본 안테나 RX 조사·build 뒤 적용 가능하면 2개 raw IQ 수신 HIL | RX 미확인은 실제 software/controller 제약을 조사할 개발 항목; 배열 확보를 선행 요구하지 않음. 안테나 전환·실제 각도 계산의 외장 경로는 구현/안내 후 사용자 실기 |
| W05 | 2개 CS initiator/reflector·RAS·raw 결과·거리 추정 출력·보안/복구, 3개 peer 분리 | cross-vendor CS peer 또는 별도로 요청한 정밀 거리/각도 시험 |
| W06~W08 | 3개 역할을 순차 재배치한 기능 HIL, 독립 image별 자원·수명주기, 예제·회귀·원장·문서 인계 | 네 기능 전체 동시 실행은 요구하지 않음. 해결되지 않은 필수 board-only 결함·mapping/접근 문제는 미완료; 사용자 후속 외부 실물 검증은 비차단 |
| HOST | 별도 재개 지시 후 manifest·resolver·launcher·negative와 가능한 자동 검사 | Ubuntu/macOS 실제 설치·USB upload·serial/debug는 해당 OS 후속 릴리스의 사용자 gate; v0.5.0 범위 밖 |

CTE TX 명령 수용·연결 peer 동작만 관찰했다면 그 범위만 기록한다. 수신 IQ 증거가 없는데 CTE
수신이나 각도 측정 PASS로 기록하지 않는다. **IQ report 수신 PASS 역시 실제 AoA 각도 계산 PASS가
아니다.** AoD는 고정 SDC `UNSUPPORTED`, 대체 controller의 raw IQ RX는 적용성 판정 전
`source_candidate`부터 검증 깊이를 기록한다. connected 내부 진단의 일부 수신과 connectionless RX를
분리하며 최신 실패와 cleanup 잔여는 §2를 따른다. 수신 구성의 실제 build/runtime 실패는 그 controller·profile에 한정해 기록하고
칩 전체 불가로 확대하지 않는다. nRF54L15 대상이 아닌 `nrf_dm`을 CS 대체 예제로 등록하지 않는다.

실물 시험 전 SHA-256 probe identity·serial path·role·firmware revision을 다시 결합한다. 여러 probe
중 임의 선택을 금지하며 raw probe UID는 채팅·문서·저장 로그에 남기지 않는다. 기존 배타 lock,
watchdog·lease·STOP·자원 반환 계약을 사용한다. 자동 mass erase/recover·전체 flash 초기화·임의
GPIO·전원 차단을 실행하지 않는다. M30의 4지점 × 3회 정책과 12/12 완료를 다시 변경·재예약하지 않는다.

## 8. 고정 test family와 W01 수치 확정 TODO

다음 **10개 test family는 기능 식별자**다. 작업 분모 8과 다르며 현재 CAP·PARITY·ISO·AUDIO 4/10 PASS다.
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
| M31-REG-01 | W06/W08, 영향 회귀 | M19~M30 영향 목록 전수와 M31 독립 image/profile별 자원·수명주기, family별 기존 수치 재사용; cross-link·보안·자원 회수 오류 0. 네 기능 전체 동시 실행은 분모가 아님 |
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
- [ ] M33 후속 버전의 전체 sample catalog·추가 GATT/profile/template·Apple/Google 구현·
  사용자 후속 상호운용·세 Host·공개 gate에 정확한 잔여 인계
- [ ] M31-W08 소유 v0.5.0 Windows 패키지·설치·RC 준비와 별도 공개 승인 조건을 정리

근거 있는 `UNSUPPORTED`와 사용자 확정 범위 밖 행은 기능 PASS 수에 넣지 않고 판정 완료 수로
별도 보고한다. 필수 board-only 기능의 `FAIL`/`HOLD`/`NOT RUN`이 남으면 해당 W는 미완료다.
사용자에게 인계한 외부 실물 검증의 `NOT RUN`은 이유·사용자 책임·개발/릴리스 비차단을 명시하며
필수 구현·예제·자동 검사의 완료와 구별한다. 범위 결정을 미완성 구현 또는 확정 결함의 면제로 쓰지 않는다.

M31 기능 8/8 완료와 v0.5.0 Windows 공개는 별도 판정이다. M31-W08이 준비하고
[v0.5.0 TODO §6](TODO_v0.5.0.md#6-결과공개-규칙)의 배포 gate·별도 승인을 충족한 뒤 공개한다.
현재 공개·설치 지원은 `v0.4.1`, 개발 소스는 `0.4.1-dev`다. 세 Host 확대·전체 NCS 예제·
M32/M33은 후속 버전이며 Bluetooth qualification이나 실물 상호운용을 자동 완료하지 않는다.
