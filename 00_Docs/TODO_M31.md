# M31 실행 TODO — ISO·LE Audio·Direction Finding·Channel Sounding

| 항목 | 내용 |
| --- | --- |
| 대상 제품선 | `v0.5.0` |
| 현재 상태 | **착수 대기 — 0/8 작업 묶음** |
| 선행 완료 | M30 W01~W08 8/8, test ID 10/10, 실제 전원 차단 12/12 |
| 병행 Host 상태 | HOST-W01~HOST-W03 완료, HOST-W04~HOST-W06 착수 대상 |
| 기준 SDK | NCS `v3.4.0`, Zephyr `4.4.0`, 고정 lock revision |
| 최종 갱신일 | 2026-09-15 |

이 문서는 M31에서 바로 실행할 작업과 중단 경계를 관리한다. 제품선 전체 순서는
[제품 로드맵](<01_아두이노 코어 설계/02_구현_로드맵.md>), 기능별 목표는
[경쟁 마일스톤](<01_아두이노 코어 설계/08_전_인스턴스_DMA_BLE_경쟁_마일스톤.md>),
Host 범위는 [다중 Host 지원 계약](<02_빌드 설계/10_v0.5.0_다중_Host_지원_착수_계약.md>)이
소유한다. 이 TODO의 계획 항목은 구현·target build·실기 PASS가 아니다.

## 1. 착수 원칙

1. M31-A ISO/LE Audio, M31-B Direction Finding, M31-C connected Channel Sounding을 각각 판정한다.
   일부 하위 gate의 통과를 M31 전체 완료로 계산하지 않는다.
2. 고정 SDK의 Kconfig·header·sample과 실제 nRF54L15 controller capability를 분리한다. Sample 존재나
   정적 symbol만으로 NU54DK 지원을 선언하지 않는다.
3. 기본 SoftDevice Controller, 대체 controller/profile과 하드웨어 기능을 혼동하지 않는다. Controller나
   SDK 변경이 필요하면 별도 영향 범위와 회귀 비용을 먼저 승인한다.
4. Public Arduino API는 Zephyr 구조체를 직접 노출하지 않고 고정 크기 자원·명시적 수명주기·fail-closed
   오류를 사용한다. 기존 M28~M30 link handle과 보안 계약을 유지한다.
5. 장비가 필요한 실기는 fixture·역할·결선·수치 기준을 확정한 뒤 실행한다. 장비 미확보는 `NOT RUN`이며
   Host/parser/target 준비처럼 독립적인 작업을 막지 않는다.
6. HOST-W04~HOST-W06은 RF/audio 장비 준비와 병행한다. Windows mock이나 CI가 실제 Ubuntu/macOS clean
   install·target build를 대신하지 않는다.

## 2. 작업 묶음

| 작업 | 상태 | 구현·검증 범위 | 완료 산출물 |
| --- | --- | --- | --- |
| M31-W01 capability·계약 | **미착수** | ISO/CIS/BIS, BAP/CAP·LC3, DF CTE TX/RX·IQ, connected CS와 controller/profile별 지원성 조사; 실제 HCI/probe 계획과 자원 상한 고정 | M31 착수 계약, `m31-ble-readiness.json`, fail-closed parser와 Host negative test, test ID·장비·수치표 |
| M31-W02 ISO 기반 | **미착수** | CIG/CIS와 BIG/BIS의 생성·연결·동기·해제, TX/RX buffer와 sequence/timestamp, encryption·disconnect recovery | 고정 자원 Arduino facade, Host semantic test, central/peripheral·broadcaster/receiver target build, raw ISO HIL 준비 |
| M31-W03 LE Audio | **미착수** | 채택할 LC3·BAP/CAP unicast/broadcast 범위, codec/frame/clock 계약, audio source/sink와 underrun·overrun 처리 | 선택 profile과 제외 범위, 예제, Host/target test, 실제 audio loss·latency·jitter HIL 근거 |
| M31-W04 Direction Finding | **미착수** | 기본 SDC의 AoA용 CTE TX와 AoD 미지원 경계 확인, RX/IQ·antenna switching용 controller/profile 적용성 판정, calibration 데이터 형식 | controller별 지원 원장, CTE API·parser·target, 승인된 antenna/RF fixture와 실제 지원 경로 HIL 근거 |
| M31-W05 connected Channel Sounding | **미착수** | 보안된 ACL에서 initiator/reflector procedure, capability 교환·procedure 수명주기, raw 결과·거리 산출·보정·오류 복구 | CS API·고정 buffer, Host/target test, 거리 fixture·통계 기준, Nordic/타 vendor 적용성 근거 |
| M31-W06 통합·회귀 | **미착수** | M31-A/B/C 자원 충돌과 link 격리, M19~M30 GAP/GATT/security/profile/DFU 영향 회귀, stale callback·disconnect·재연결 | 통합 target·runner, memory/latency 원장, 회귀 결과와 알려진 제한 |
| M31-W07 실기·상호운용 | **미착수** | 승인된 역할별 보드/peer/fixture로 ISO·audio·DF·CS 유한 HIL, 실패 원본과 동일 조건 재검증 | Exact image·장비 mapping·transcript·evidence, test ID별 분모와 PASS/FAIL/NOT RUN |
| M31-W08 마감·M32 인계 | **미착수** | API·예제·지원표·문서·기계 원장 정합화, 전체 Host/target 회귀, M32 Mesh·공존에 넘길 radio/controller 자원 경계 | M31 완료 기록, readiness 완료 상태, M32 인계와 명시적 미지원·조건부 지원 목록 |

## 3. 가장 먼저 실행할 순서

1. 저장소·board submodule·NCS·Zephyr·toolchain lock과 clean/dirty 상태를 기록한다.
2. 고정 SDK source에서 다음 항목을 기계 원장 후보로 수집한다.
   - SDC multirole의 CIS central/peripheral, ISO broadcaster/synchronized receiver, Channel Sounding
   - Zephyr Host의 `BT_ISO*`, `BT_AUDIO`, `BT_BAP*`, `BT_CAP*`, `BT_DF*`, `BT_CHANNEL_SOUNDING*`
   - NU54DK target에서 선택 가능한 controller/profile, RAM/flash·connection·ISO/CS context 상한
3. M31-W01 착수 계약과 readiness schema를 만들고, 정적 candidate와 runtime capability 상태를 분리한다.
4. Parser 정상·누락·중복·revision mismatch·unsupported 조합 negative test를 먼저 만든다.
5. Capability image를 NU54DK target으로 build한 뒤 한 보드 HCI 실행 계획을 고정한다.
6. W01과 병행해 HOST-W04 prerequisite manifest·검증기부터 구현한다.
7. W01 판정 후 W02 raw ISO를 먼저 구현하고, 그 위에 W03 audio profile을 올린다.
8. W04 DF와 W05 CS는 controller 적용성 결론에 따라 독립 진행한다. W06 통합 전까지 각 기능의
   실패 원인과 자원 사용량을 분리한다.

## 4. HOST-W04~HOST-W06 병행 TODO

| Host 작업 | 상태 | 바로 할 일 | 완료 경계 |
| --- | --- | --- | --- |
| HOST-W04 prerequisite | **미착수** | Windows x64·Ubuntu AMD64·macOS Apple Silicon별 nRF Util/sdk-manager/NCS/Zephyr/toolchain/Arduino CLI URL·hash·revision·architecture manifest와 검증기 작성 | 세 Host가 잘못된 OS/arch/hash/revision을 거부하고 승인 조합을 clean 설치·검증 |
| HOST-W05 portable path/cache | **미착수** | lock·cache·권한·case sensitivity·symlink·실행 bit·공백·한글 경로, 긴 경로와 atomic replace 계약 정리 | 같은 입력의 cache identity·artifact가 Host별로 일치하고 충돌·stale lock·부분 파일을 fail-closed 처리 |
| HOST-W06 package·CI | **미착수** | 세 Host package metadata·launcher·archive mode, install 후 전체 예제 compile matrix와 artifact 비교 추가 | Windows·Ubuntu·macOS native runner에서 clean package install과 target build PASS; mock-only 행은 PASS 금지 |

## 5. 장비와 사람 개입 경계

| 단계 | 최소 장비·접근 | 사람 개입 시점 |
| --- | --- | --- |
| W01 capability | NU54DK 1개와 고유 probe/COM mapping | Flash 직전 실제 보드 identity·role 확인 |
| W02 raw ISO | NU54DK 최소 2개 | 보드 역할·RF 환경 확인과 재연결 |
| W03 LE Audio | 송수신 가능한 승인 peer와 audio 입출력/계측 fixture | Codec/profile 선택, 배선·audio 경로·계측 기준 확정 |
| W04 DF | 승인 controller/profile, antenna array/switch와 IQ 수집·보정 fixture | Antenna 순서·배치·거리·방향과 RF 안전 조건 확정 |
| W05 CS | CS 지원 initiator/reflector, 통제 거리 또는 RF 감쇠·보정 fixture | Peer·거리점·환경·보정 방법 확정 |
| HOST-W04~HOST-W06 | Windows x64, Ubuntu AMD64, Apple Silicon macOS 실행 환경 | 실제 각 Host 제공과 OS별 설치 자격 증명·USB 접근 |

현재 확보된 NU54DK 3개만으로 W01과 일부 W02/CS 준비는 가능하다. Audio, DF, 정량 거리 HIL은
전용 peer·antenna/audio/거리 fixture가 확정되기 전까지 자동 완료할 수 없다. 각 실기 직전에는 필요한
보드 수·역할·USB/GPIO/RF 결선·스위치·사용자 동작·확인 출력을 한 번에 제시한다.

## 6. 시험 수치 확정 TODO

다음 값은 아직 제품 보증 수치로 확정하지 않았다. W01 계약에서 측정 수단과 함께 고정한다.

- ISO: stream/connection 수, SDU와 interval, PHY, sequence 분모, 허용 loss, reconnect·resource recovery 시간
- Audio: codec/frame, sample rate, presentation delay, end-to-end latency, jitter, underrun/overrun, 허용 손실
- DF: CTE 유형·길이, antenna pattern, IQ sample 수·유효률, calibration·오차와 반복성
- CS: mode·channel map·procedure 수, 거리점·방향·환경, 오차 통계·상한, 보안/연결 실패 복구
- 공통: 최대 실행 시간, 반복 수, 즉시 중단 오류, 진단 후 허용할 동일 조건 재검증 횟수

수치를 정하기 전에는 `안정적`, `저지연`, `정확함` 같은 표현으로 PASS를 대신하지 않는다. 실패를
무한 반복해 성공한 마지막 시도만 분모로 기록하지 않는다.

## 7. M31 완료 조건

M31은 다음을 모두 만족해야 완료다.

- M31-W01~W08 8/8과 착수 계약에서 확정한 모든 필수 test ID 완료
- M31-A/B/C 각각의 지원·조건부·미지원 판정과 근거 연결
- 필수 target build·실제 RF/audio/거리 HIL PASS 또는 소유자가 승인한 명시적 범위 제외
- M19~M30 영향 회귀와 자원·보안·disconnect recovery 오류 0
- HOST-W04~HOST-W06의 실제 세 Host 증거; 사용할 수 없는 Host 행은 `NOT RUN`
- API·예제·지원 matrix·readiness JSON·검증 기록·HANDOFF의 상태 일치

M31 완료는 v0.5.0 공개나 Bluetooth qualification 완료가 아니다. 공개 판정은 M33이 소유한다.
