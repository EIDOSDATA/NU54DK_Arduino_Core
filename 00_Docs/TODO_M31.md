# M31 실행 TODO — NCS ISO·LE Audio·Direction Finding·Channel Sounding 예제의 Arduino 실행

| 항목 | 내용 |
| --- | --- |
| 대상 제품선 | `v0.5.0` |
| 현재 상태 | **W01~W08 완료 / 8/8 작업 묶음, M31 완료** |
| 선행 완료 | M30 W01~W08 8/8, test ID 10/10, 실제 전원 차단 4지점 × 3회 = 12/12 |
| 병행 Host 상태 | HOST-W01~HOST-W03 완료 3/8, HOST-W04~HOST-W08 사용자 지시로 보류; M31과 독립 집계 |
| 기준 SDK | NCS `v3.4.0`, Zephyr `4.4.0`, 고정 lock revision |
| 기능 검증 장비 | W08 exact RC 대표 upload/UART/debug PASS 뒤 시험 보드를 W07 CS reflector image로 복구하고 advertising·무연결·CS 비활성 상태 확인 |
| 최종 갱신일 | 2026-09-27 |

2026-09-21 결정으로 **M31 완료 후 v0.5.0 Windows 릴리스**를 준비한다. main 이력 정리 이후의
재개 상태는 [HANDOFF](HANDOFF.md)를 따른다. 과거의 설명 통합 요청은 문서만 수정한
시점의 이력이며, `M31-MEM-OPT`에서 메모리 최적화 P0·P1·P2를 완료한 뒤
`0.5.0-RC1`에서 W04~W08을 닫았다. M31은 완료했고 `v0.5.0-rc.1` 공개 및 공개 설치 smoke도
PASS했다. 정식 `v0.5.0` stable 승격은 별도다.
Host W04~W08은 계속 보류하며 M32/M33은 후속 버전(미정)이다.

M31의 목표는 **고정 NCS에서 nRF54L15DK에 적용되는 ISO·LE Audio·DF·connected Channel Sounding
기능과 예제를 NU54DK Arduino 환경에서 사용할 수 있게 하는 것**이다. 고수준 Arduino facade,
고급 직접 API, 검증된 profile·template 중 기능에 맞는 제공 경로를 사용한다. 모든 예제를 한 가지
추상화로 감싸는 것은 필수 조건이 아니다.

제품선 순서는 [제품 로드맵](<01_아두이노 코어 설계/02_구현_로드맵.md>), 전체 기능 소유권과
예제 판정 규칙은 [NCS Bluetooth 전체 기능·예제 실행 계약](<01_아두이노 코어 설계/19_NCS_Bluetooth_전체_기능과_예제_실행_계약.md>),
기능별 목표는 [경쟁 마일스톤](<01_아두이노 코어 설계/08_전_인스턴스_DMA_BLE_경쟁_마일스톤.md>),
Host는 [다중 Host 지원 계약](<02_빌드 설계/10_v0.5.0_다중_Host_지원_착수_계약.md>)이 소유한다.
계획 개정 자체는 구현 증거가 아니다. W01~W08 완료 범위는
[착수 계약](<01_아두이노 코어 설계/20_M31_Bluetooth_착수_계약.md>)과
[W02 최종 완료 기록](<04_검증 기록/199_M31_W02_격리_설치본_ISO_11예제와_완료.md>),
[W03 최종 완료 기록](<04_검증 기록/214_M31_W03_LE_Audio_Profile_완료.md>)에서 구분한다.

## 1. 착수 원칙과 지원 판정

1. M31-A ISO·전체 LE Audio profile, M31-B Direction Finding, M31-C connected Channel Sounding을
   각각 판정한다. M31-W01~W08의 8개 작업 묶음과 기능별 test ID·role subcase 분모를 구분한다.
2. 고정 SDK의 Kconfig·header·sample 존재, nRF54L15 공식 sample target, NU54DK native build,
   Arduino build, runtime capability, 실제 기능 HIL을 각각 기록한다. nRF54L15DK용 build metadata가
   있는 예제는 우선 구현 대상이며, generic Host source만 있는 예제는 NU54DK 적용성 조사 대상이다.
3. **고정 NCS v3.4.0의 nRF54L15 제품 SDC는 DF AoA 송신만 지원한다.** IQ RX와 AoD는
   `UNSUPPORTED`로 기록하고 P2 필수 범위에서 제외한다. SDK/controller를 바꾸지 않는다.
   [259번 지원 근거](<04_검증 기록/259_M31_P2_DF_고정_SDK_지원_경계.md>)와 Zephyr LL 내부 진단은
   별개다. LL 연결형 IQ 국소 성공·connectionless 실패를 보존하되 제품 수신 지원이나 P2 재시험
   의무로 확대하지 않는다. 원시 IQ·안테나 전환·각도 계산은 다른 기능이며 칩 전체의 불가 판정도 아니다.
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
| M31-W03 전체 LE Audio profile | **완료** | W03-01~11의 공개 Arduino 역할과 적용 가능한 native 기반을 모두 닫았다. BAP unicast/broadcast·BASS·CAP·CSIP·PBP·VCP/VOCS/AICS/MICP, MCP/MCS·CCP/TBS, TMAP/GMAP, HAP/HAS의 build/runtime·negative·peer-loss 복구와 합성 PCM RF data path를 실제 2~3보드에서 확인했다. Media/Call은 각 100/100·negative 각 20/20·reconnect 20/20·180초 soak, TMAP/GMAP은 각 180초·stop/restart 20/20·drop 0, HAP/HAS는 preset 100/100·두 negative 각 20/20·복구 20/20이다. 외장 audio·상용 peer·qualification·의료/음향 성능은 사용자 후속 비차단 `NOT RUN`이다 | [native BAP LC3](<04_검증 기록/181_M31_W03_native_BAP_LC3_실제_무선_전송.md>)·[BAP broadcast](<04_검증 기록/202_M31_W03_Arduino_BAP_broadcast_암호화와_negative_완료.md>)·[BASS](<04_검증 기록/203_M31_W03_Arduino_BASS_3역할과_복구.md>)·[CAP](<04_검증 기록/205_M31_W03_Arduino_CAP_unicast_반복_실기.md>)·[Audio Control](<04_검증 기록/208_M31_W03_Arduino_Audio_Control_완료.md>)·[CSIP](<04_검증 기록/209_M31_W03_Arduino_CSIP_완료.md>)·[PBP](<04_검증 기록/210_M31_W03_Arduino_PBP_완료.md>)·[Media/Call](<04_검증 기록/211_M31_W03_Arduino_Media_Call_Control_완료.md>)·[TMAP/GMAP](<04_검증 기록/212_M31_W03_Arduino_TMAP_GMAP_완료.md>)·[HAP/HAS](<04_검증 기록/213_M31_W03_Arduino_HAP_HAS_완료.md>)·[W03 완료 감사](<04_검증 기록/214_M31_W03_LE_Audio_Profile_완료.md>)·[exact closure](<04_검증 기록/evidence/m31-w03-close-dc312cce/closure-audit.json>) |
| M31-W04 Direction Finding | **완료** | 제품 SDC `CteBeacon` start/stop 20/20·invalid length 거부 20/20, 별도 opt-in Zephyr LL `ConnectedCteResponder` 무선 CTE report 20건·IQ sample 1,640개·cleanup PASS를 현재 소스로 재검증했다. 제품 SDC IQ RX·AoD는 `UNSUPPORTED`로 닫았고, 과거 LL 내부 진단·connectionless 실패는 제품 RX 지원으로 승격하지 않았다. 첫 연결형 재검증 IQ 0건 FAIL은 원본 보존하고 허용된 1회 재시도만 PASS했다. | [W04 완료 263](<04_검증 기록/263_M31_W04_Direction_Finding_완료.md>) · [exact audit](<04_검증 기록/evidence/m31-w04-close-20260925/closure-audit.json>) · [지원 경계 259](<04_검증 기록/259_M31_P2_DF_고정_SDK_지원_경계.md>) |
| M31-W05 connected Channel Sounding | **완료** | secure ACL·raw RAS 100개와 stop/restart·disconnect/reconnect 각 20/20, 실제 256-step·분할 RAS 유효 raw 1,000개·양측 STOP, 최대 절차 peer 이탈·자동 재연결 뒤 유효 raw 20개를 확인했다. 비암호화 ATT 5·wrong peer/service 부재·one-sided stale bond의 secure RAS 수용 0과 flash 직후 전체 경로 독립 2회도 PASS했다. stale-key ACL은 오류 뒤 STOP까지 유지될 수 있고 간헐 counter gap은 비차단 관찰값이다. 비보정 RTT의 정확도는 미보증이다. | [W05 완료 264](<04_검증 기록/264_M31_W05_Channel_Sounding_완료.md>) · [exact audit](<04_검증 기록/evidence/m31-w05-close-20260925/closure-audit.json>) · [비암호화 거부](<04_검증 기록/217_M31_W05_비암호화_RAS_ATT_오류_진단.md>) · [flash 직후 복구](<04_검증 기록/218_M31_W05_flash_직후_RAS_복구_재검증.md>) · [P2 peer-loss](<04_검증 기록/262_M31_메모리_최적화_P2_세_축_완료.md>) |
| M31-W06 자원·수명주기·회귀 | **완료** | 독립 role image 4개 family의 stack/heap·buffer·stream/connection 예산과 stop/disconnect 반환을 P2 exact 수치로 확정하고 기존 크기를 유지했다. M19~M30 12/12는 현재 소스 target 18개 build·전체 Host 회귀와 기존 family별 물리 분모로 PASS했다. 새 HIL 진단의 protected probe 2개는 `HOLD`이며 PASS 근거에서 제외했다 | [W06 완료 265](<04_검증 기록/265_M31_W06_자원_수명주기와_영향_회귀_완료.md>) · [exact audit](<04_검증 기록/evidence/m31-w06-close-20260926/closure-audit.json>) · [P2 완료](<04_검증 기록/262_M31_메모리_최적화_P2_세_축_완료.md>). 네 기능 전체 동시 실행은 완료 조건이 아님 |
| M31-W07 기능 HIL·예제 실행 | **완료** | 독립 설치 package 4개 library·49개 sketch 49/49 build, 공개 예제 113개 issue 0. 3보드 역할 재배치로 ISO 20/20/20·2,000 frame missing 0, Audio 20/20, DF 20/20+invalid 20/20, CS 100+20/20+20/20과 STOP 확인. 적용 39 PASS·외부 3 NOT RUN·제품 SDC IQ RX 1 UNSUPPORTED | [W07 완료 266](<04_검증 기록/266_M31_W07_설치_예제와_3보드_역할_HIL_완료.md>) · [exact audit](<04_검증 기록/evidence/m31-w07-close-20260926/closure-audit.json>) |
| M31-W08 마감·Windows 릴리스 준비 | **완료, RC 공개** | exact private RC 이중 재현, 격리 Windows 설치 예제 113/113 병렬 build, 0.4.1→RC upgrade·uninstall·reinstall/cache 수명주기, 대표 upload/UART/debug와 원장·문서 정합 PASS. 이후 exact RC tag/Pre-release/전용 catalog와 공개 smoke PASS | [W08 완료 267](<04_검증 기록/267_M31_W08_Windows_RC_준비와_M31_완료.md>) · [공개 RC 268](<04_검증 기록/268_v0.5.0-rc.1_공개와_다운로드_smoke.md>) |

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

### 메모리 최적화 현재 상태

**P0·P1·P2 완료**다. 기본 `standard`/full 호환 경로를 유지하며 `adaptive`는 명시적
실험 선택지다. 실제 API 도달성·library manifest·공개 역할/용량 선언을 compiler-assisted probe와
resolver로 해석한다. 일반 사용자에게 기능별 `prj.conf` 수동 OFF 목록을 요구하지 않는다.
전문가 `prj.conf`/`app.overlay` override와 향후 상위 radio 정책 메뉴는
[통합 설계 §4](<01_아두이노 코어 설계/21_M31_메모리_최적화_통합_설계.md#4-사용자-코드와-기능-선택의-계약>)에 구분한다.

| 완료·관찰 범위 | 증거와 해석 |
| --- | --- |
| P0 기능 선택 / P1 정적 저장소 | [222번](<04_검증 기록/222_M31_메모리_최적화_P0_완료.md>) · [237번](<04_검증 기록/237_M31_메모리_최적화_P1_정적_저장소_완료.md>). Core SPI 50,877→20,589 B, CoC-only 91,037→70,081 B, GATT 1×1 server fixture 113,218→48,581 B. 각각의 같은 fixture 비교이며 합산 절감량이 아님 |
| GATT / raw ISO | [238번](<04_검증 기록/238_M31_메모리_최적화_P2_GATT_실기와_Adaptive_정정.md>) GATT 512 B write/read·재연결 20/20. [240번](<04_검증 기록/240_M31_메모리_최적화_P2_ISO_CIS_BIS_실기_계측.md>) CIS/BIS 각 100 SDU×20세션 |
| CoC | [257번](<04_검증 기록/257_M31_P2_CoC_송신_버퍼_부하와_복구.md>) 로컬 TX pool 4개 포화·다섯 번째 busy와 복구. [262번](<04_검증 기록/262_M31_메모리_최적화_P2_세_축_완료.md>) peer 실제 초기 credit 1 직접 보유, 제출 4개 중 3개 대기·반환 뒤 진행·새 SDU 복구 |
| Audio | [253번](<04_검증 기록/253_M31_P2_Audio_broadcast_재가입_메모리_계측.md>) broadcast 재가입 20/20, [254번](<04_검증 기록/254_M31_P2_Audio_unicast_재연결_메모리_계측.md>) unicast 재연결 20/20, [258번](<04_검증 기록/258_M31_P2_Audio_양방향_장시간과_종료_복구.md>) 양방향 각 10,000 frame·drop 0. 262번 wrong Code `-61`·decode 0 뒤 올바른 Code 100 frame 복구 |
| DF | [259번](<04_검증 기록/259_M31_P2_DF_고정_SDK_지원_경계.md>) beacon TX 20/20. 제품 SDC IQ RX는 `UNSUPPORTED`이며 P2 비차단; Zephyr LL 진단은 제품 RX PASS가 아님 |
| CS | [260번](<04_검증 기록/260_M31_P2_CS_누락_분류와_256_step_장시간.md>) 실제 256-step·분할 RAS 유효 raw 1,000건·양측 STOP. gap 3은 비차단. 262번은 첫 raw 전 peer reset·disconnect·자동 재연결 뒤 유효 raw 20개·중복/역행 0 |
| 최종 크기 / SDC | MPSL work의 최소 관찰 여유 264 B 등으로 stack·heap·SDC pool 기존 크기를 유지. SDC는 [248번](<04_검증 기록/248_M31_P2_SDC_pool_정적_경계_감사.md>) SDK 계산·정렬 계약, 최종 표는 [memory JSON](<04_검증 기록/evidence/m31-p2-three-axes-20260925/memory-finalization.json>) |
| Nordic native 비교 | CoC와 암호화 LC3 broadcast source 두 쌍의 동일 SDK/board/SDC/기능·보안·MTU/stream·로그·계측·linker 조건 비교 PASS. [비교 JSON](<04_검증 기록/evidence/m31-p2-three-axes-20260925/native-memory-comparison.json>). 조건이 다른 250번 RAS는 분모에서 제외 |

각 결과는 해당 source·image·조건의 국소 PASS다. 정상 반복만으로 최악 메모리 안전성을 보장하지
않으며, 과거 원본과 세부 시도는 [검증 기록 목차](<04_검증 기록/README.md>)에 보존한다.

### P2 완료 — 세 축

| 번호 | 기술 축 | 완료 근거 |
| --- | --- | --- |
| 1 | **지원 범위 오류·최악 부하** | CoC peer credit, Audio 다중 stream/wrong Code, CS 256-step peer 이탈·복구와 동시 메모리 계측 **PASS** |
| 2 | **메모리 안전 여유·최종 크기** | stack/heap 반환·bounded allocation failure·계측 영향·SDC 계약 확인. 축소 근거가 없어 기존 크기 유지 **PASS** |
| 3 | **동등 조건 Nordic native 비용 비교** | CoC·암호화 Audio의 ELF/map·상위 symbol과 API 비용 하한 비교, native 비팽창·중복 pool 0건 **PASS** |

**범위 고정:** NCS v3.4.0·제품 SDC를 유지한다. DF IQ RX 구현/LL fault 해결,
CS 간헐 RF/controller loss·counter gap 제거, SDC 내부 high-water 계측 API 확보는
P2 필수 조건이 아니다. CS 유효 raw·step·완료 수·STOP·fault·중복/역행 counter 검사는 유지한다.
물리 전원 차단·임의 다중 link·모든 조합을 별도 합의 없이 추가하지 않는다.
SDC 내부 사용 최고치는 노출되지 않으므로 정적 symbol 크기를 실제 사용량으로 쓰지 않는다.
안전한 축소 근거가 없으면 pool을 유지할 수 있으며 **무조건 축소해야 P2 완료인 것은 아니다**.

### 다음 실행 순서

1. 완료한 W04~W08의 기능·자원·회귀·설치 예제·HIL·RC 원본과 실패/HOLD 원본을 다시 쓰지 않는다.
2. 공개 `v0.5.0-rc.1`을 관찰한다. stable 별도 승인 전에는 `v0.5.0` tag/Release/root catalog를
   만들지 않고 M32/M33·Host 보류 작업도 시작하지 않는다.

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

W01~W08과 공개 RC는 완료했다. 1~8번의 원장·기준선은 보존하며 재구현하지 않는다.
후속 작업은 M31과 W08을 다시 열지 않고 stable 별도 승인 지점에서 재개한다.
과거 착수 절차를 현재 미완료 TODO로 다시 집계하지 않는다.

1. 저장소·branch·HEAD·미커밋 변경·board submodule·SDK/toolchain lock과 변경 전 전체 Host 기준선을
   기록한다. 다른 작업의 변경 소유권과 실행 중 검사를 보존한다. W08에서는 사용자가 허용한
   GitHub Actions Windows 8-shard·lifecycle·aggregate와 exact push 결과를 확인했다.
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
8. W04 DF와 W05 CS는 최적화 image에서 채택 기능·negative·복구 경계를 재검증해 완료했다.
   W06 독립 image 자원·수명주기·영향 회귀, W07 설치 예제·3보드 역할 HIL과 W08 Windows
   RC 준비와 공개 `v0.5.0-rc.1` smoke까지 완료했으며 다음은 stable 별도 승인이다.
   앞선 RX 후보 조사·HIL 계획은 [259번](<04_검증 기록/259_M31_P2_DF_고정_SDK_지원_경계.md>)의
   고정 SDK 지원 판정으로 대체됐다. 제품 SDC IQ RX는 `UNSUPPORTED`로 명시하고, 과거 LL
   진단을 자동 재개하거나 SDK/controller를 변경하지 않는다. HOST-W04 이후는 계속 보류한다.

## 5. 예제 품질과 설치 계약

- [x] 예제마다 목표 기능·upstream origin·필요 보드 수·역할·profile 선택·실행 순서·예상 Serial 출력 명시
- [x] 최소 예제, 상대 역할 예제, negative/recovery 예제를 기능에 맞게 제공; 이름과 경로는 원장에서 고정
- [x] Arduino `setup()`/`loop()` 경로에서 실제 `NUCODE_*` 공개 API 호출; Zephyr/NCS 호출은 library `.cpp`/`src/internal`에 두고 고급 예제의 Kconfig 설정을 설명
- [x] queue/buffer 수명, error 처리, timeout, 종료·재시작, 자원 반환을 예제에 포함하고 busy-loop 회피
- [x] 한국어 Doxygen·BSD/Allman·탭 폭 4·모든 제어문 중괄호 적용
- [x] clean Arduino package 설치의 example discovery → compile → role firmware → Serial oracle를 연결
- [x] Kconfig profile과 build options를 코드 밖의 검증된 설정으로 제공하고 임의 SDK patch 요구 금지
- [x] 실험적·미지원·사용자 후속 실물 검증의 책임·비차단 범위를 example README와 parity 원장에 일치시킴

M31-W07은 v0.5.0에 채택한 M31 예제의 독립 설치·발견·compile·3보드 실행을 닫았다. W08도
전체 원장·지원표와 Windows 배포 준비를 닫았다. M33은 후속 버전의 추가 GATT/profile·template와 전체 NCS catalog, 세 Host 확장 검증을
맡는다. M31 예제 패키징을 M33으로 미뤄 v0.5.0 배포 gate를 생략하지 않는다.

## 6. HOST-W04~HOST-W06 TODO — 사용자 지시로 보류

아래는 재개 후 수행할 계획이다. **HOST-W04~HOST-W08**의 구현 상태는 미착수이며 현재 실행하지 않는다.

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
| W04 | 지원되는 CTE TX·response 기능·예제·오류 및 변경 영향 재검증 | 제품 SDC IQ RX·AoD는 고정 SDK `UNSUPPORTED`. LL RX 진단 이력은 보존하고 P2에서 재개하지 않음. 정밀 각도·외장 안테나 실물은 별도 |
| W05 | 2개 CS initiator/reflector·RAS·raw 결과·거리 추정 출력·보안/복구, 3개 peer 분리 | cross-vendor CS peer 또는 별도로 요청한 정밀 거리/각도 시험 |
| W06 완료 | 독립 image별 자원·수명주기와 M19~M30 회귀 | 네 기능 전체 동시 실행은 요구하지 않음. 당시 debug protection 진단 `HOLD`는 W06 PASS 근거와 분리하고 W07 전원 재인가 뒤 접근성 재확인 |
| W07 완료 | 3개 역할을 순차 재배치한 기능 HIL, 설치 예제 49/49·43역할 원장 | 적용 39 PASS, 외부 3 NOT RUN, 제품 SDC IQ RX 1 UNSUPPORTED. 최초 preflight FAIL과 제한 재시도 PASS 모두 보존 |
| W08 완료 | 원장·지원표·문서 인계와 Windows RC 준비, RC tag·Pre-release·전용 catalog·공개 download/install smoke PASS | 정식 stable 승인·tag·Release·root catalog·공개 smoke는 별도 gate; 사용자 후속 외부 실물 검증은 비차단 |
| HOST | 별도 재개 지시 후 manifest·resolver·launcher·negative와 가능한 자동 검사 | Ubuntu/macOS 실제 설치·USB upload·serial/debug는 해당 OS 후속 릴리스의 사용자 gate; v0.5.0 범위 밖 |

CTE TX 명령 수용·연결 peer 동작만 관찰했다면 그 범위만 기록한다. 수신 IQ 증거가 없는데 CTE
수신이나 각도 측정 PASS로 기록하지 않는다. **IQ report 수신 PASS 역시 실제 AoA 각도 계산 PASS가
아니다.** 제품 SDC IQ RX·AoD는 고정 SDK `UNSUPPORTED`로 기록한다.
연결형 LL 내부 진단의 일부 수신과 connectionless 실패는 경로별 역사 기록으로 보존하며,
제품 RX 지원이나 칩 전체 불가로 확대하지 않는다. nRF54L15 대상이 아닌 `nrf_dm`을
CS 대체 예제로 등록하지 않는다.

실물 시험 전 SHA-256 probe identity·serial path·role·firmware revision을 다시 결합한다. 여러 probe
중 임의 선택을 금지하며 raw probe UID는 채팅·문서·저장 로그에 남기지 않는다. 기존 배타 lock,
watchdog·lease·STOP·자원 반환 계약을 사용한다. 자동 mass erase/recover·전체 flash 초기화·임의
GPIO·전원 차단을 실행하지 않는다. M30의 4지점 × 3회 정책과 12/12 완료를 다시 변경·재예약하지 않는다.

## 8. 고정 test family와 판정 기준

다음 **10개 test family는 기능 식별자**다. 작업 분모 8과 다르며 현재 9/10 PASS다.
DF family에는 지원 TX의 PASS와 제품 SDC IQ RX·AoD의 `UNSUPPORTED`가 함께 있어 전체 PASS로
합산하지 않는다. 적용 필수 항목의 판정은 모두 완료됐으며 원본은 [readiness](../variants/nu54dk/m31-ble-readiness.json)다.
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
| M31-EXAMPLE-01 | W07, Arduino 예제 | 채택된 M31 example discovery/build 100%, board-only role runtime 전수와 README oracle 일치; 외부 peer/I/O 미실행 분모 별도 |
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

- [x] M31-W01~W08 **8/8**과 10개 family 아래의 적용 가능한 필수 subcase가 계약대로 완료
- [x] M31-A/B/C와 §3 모든 Audio profile의 지원/실험적/조건부/미지원 판정·근거·제공 경로 확정
- [x] 고정 stack에서 적용 가능한 board-only 기능의 native/Arduino build·실제 기능 HIL·negative PASS
- [x] 고정 SDK 제품 SDC IQ RX·AoD의 미지원 근거를 지원표·예제·기계 원장에 일치시킴;
  과거 LL 진단과 제품 지원을 구분하며 SDK/controller 변경이나 추가 RX HIL을 요구하지 않음
- [x] M31 소유 외부 audio I/O·외장 확장은 사용 가능한 구현·예제·설정/연결 안내·가능한 자동 검사를
  완료하고 실물 운용/검증은 사용자 후속 `NOT RUN`·개발/릴리스 비차단으로 기록; 정밀 RF/음질/각도/
  거리 정확도는 필수 gate 밖이고 기본 안테나 IQ 수신을 각도 계산 PASS로 확대하지 않음
- [x] M19~M30 영향 회귀와 자원·보안·disconnect recovery 오류 0; 과거 실패·HOLD·NOT RUN 원본 보존
- [x] 예제·지원 matrix·readiness·sample parity·검증 기록·HANDOFF의 상태/수치/링크 정합
- [x] M32-A modern controller·Nordic, M32-B Mesh, M32-C 공존에 필요한 자원/profile/예제 dependency 인계
- [x] M33 후속 버전의 전체 sample catalog·추가 GATT/profile/template·Apple/Google 구현·
  사용자 후속 상호운용·세 Host·공개 gate에 정확한 잔여 인계
- [x] M31-W08 소유 v0.5.0 Windows 패키지·설치·RC 준비와 공개 RC, stable 별도 승인 조건을 정리

근거 있는 `UNSUPPORTED`와 사용자 확정 범위 밖 행은 기능 PASS 수에 넣지 않고 판정 완료 수로
별도 보고한다. 필수 board-only 기능의 `FAIL`/`HOLD`/`NOT RUN`이 남으면 해당 W는 미완료다.
사용자에게 인계한 외부 실물 검증의 `NOT RUN`은 이유·사용자 책임·개발/릴리스 비차단을 명시하며
필수 구현·예제·자동 검사의 완료와 구별한다. 범위 결정을 미완성 구현 또는 확정 결함의 면제로 쓰지 않는다.

M31 기능 8/8과 공개 `v0.5.0-rc.1` 검증은 완료됐다. 정식 stable 승격의 남은 조건은
[v0.5.0 TODO §6](TODO_v0.5.0.md#6-결과공개-규칙)에서 관리한다. 현재 stable 지원은 `v0.4.1`이고
RC 사용 경로는 [별도 RC 안내](<05_릴리스/v0.5.0-rc.1/README.md>)를 따른다. 세 Host 확대·전체 NCS 예제·
M32/M33은 후속 버전이며 Bluetooth qualification이나 외부 실물 상호운용은 별도 판정한다.
