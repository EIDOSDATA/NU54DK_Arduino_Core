# 개발 인계 — M31 W04·W05 병행 진단 진행 중

현재 설치·지원 배포는 **v0.4.1**, 개발 소스는 **m31-w04-dev / 0.4.1-dev**입니다.
M31은 W01~W03 **3/8 완료**, W03 LE Audio는 **11/11 PASS**입니다.
M31-W04 Direction Finding과 M31-W05 Channel Sounding을 병행 중이며 둘 다 아직
**진행 중**입니다. **HOST-W04 이후는 계속 보류**합니다. main 반영·squash·release는
사용자의 별도 지시 전까지 수행하지 않습니다.

## 1. 현재 상태와 원본

| 범위 | 상태 | 근거 |
| --- | --- | --- |
| 공개 설치본 | v0.4.1 단독 지원 | [릴리스 안내](<05_릴리스/v0.4.1/README.md>) |
| M28 | W01~W08 8/8 완료 | [v0.5.0 계획](TODO_v0.5.0.md), [readiness](../variants/nu54dk/m28-ble-readiness.json) |
| M29 | M29-W01~W08 8/8 완료 | [계약](<01_아두이노 코어 설계/16_M29_ATT_GATT_L2CAP_착수_계약.md>), [readiness](../variants/nu54dk/m29-ble-readiness.json) |
| M30 | M30-W01~W08 8/8 완료 | [계약](<01_아두이노 코어 설계/17_M30_BLE_Security_Profile_DFU_착수_계약.md>), [readiness](../variants/nu54dk/m30-ble-readiness.json) |
| M31-W01 | 원장·capability 완료 | [M31 readiness](../variants/nu54dk/m31-ble-readiness.json) |
| M31-W02 | 설치본 ISO 11예제·11역할 완료 | [199번 최종 기록](<04_검증 기록/199_M31_W02_격리_설치본_ISO_11예제와_완료.md>) |
| M31-W03 | LE Audio 11/11 완료 | [214번 완료 기록](<04_검증 기록/214_M31_W03_LE_Audio_Profile_완료.md>), [closure audit](<04_검증 기록/evidence/m31-w03-close-dc312cce/closure-audit.json>) |
| M31-W04 | controller IQ event 102건, Host gate 폐기 확인; raw sample 0으로 HOLD | [216번 진단](<04_검증 기록/216_M31_W04_연결_AoA_Controller_IQ_Event_진단.md>) |
| M31-W05 | 동일 ACL read 20/20, flash 직후 raw RAS 100·복구 20/20을 두 번 PASS; wrong-key 잔여 | [217번](<04_검증 기록/217_M31_W05_비암호화_RAS_ATT_오류_진단.md>), [218번](<04_검증 기록/218_M31_W05_flash_직후_RAS_복구_재검증.md>) |
| M31-W06~W08 | 미착수 | 통합·회귀·예제·최종 인계 |
| M32 / M33 | 0/12 · 0/8, 미착수 | [M32 TODO](TODO_M32.md), [M33 TODO](TODO_M33.md) |
| Host | W01~W03 완료 3/8, W04~W08 보류 | [다중 Host 계약](<02_빌드 설계/10_v0.5.0_다중_Host_지원_착수_계약.md>) |

M31 전체는 `not_completed`입니다. W03 완료를 DF·CS·전체 통합 완료로 확대하지 않습니다.
M28~M31 개발 결과는 v0.4.1 설치본에 추가된 기능이나 v0.5.0 공개를 뜻하지 않습니다.

## 2. 고정 환경과 Git 이력

| 항목 | 값 |
| --- | --- |
| 기준 main | `8b20157d33f1d216620726d92d88f65c25491b4d` |
| 작업·재개 브랜치 | `m31-w04-dev` / 원격과 fast-forward 동기 상태 확인 후 계속 |
| 최근 검증 묶음 | `ea23636426acbd5d0c6b5c9051a74d7e2071ad8d` |
| Target | nRF54L15 CPUAPP / `nrf54l15dk/nrf54l15/cpuapp/nu54dk` |
| NCS | v3.4.0 / `99553055607b2e9885fbc80ccd11fa9da81c2df0` |
| Zephyr | `bf801e4e3d19e1ffa76164346480cb7734dd2800` |
| Board submodule | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |
| Windows toolchain | bundle `dcbdc366a1` |
| SDK lock | [`ncs-3.4.0.lock.json`](../tools/ci/ncs-3.4.0.lock.json) |
| Squash 전 W03 완료 | `dac8ea8a85b8d2e1a84aa4299529a37e10f6c0f7` |
| 원본 이력 보존 태그 | `archive/m31-w03-before-squash-dac8ea8a` |

Squash는 개발 커밋을 묶는 이력 정리입니다. 증거에 기록된 당시 Core/image SHA는 바꾸지 않습니다.
기존 [200번 다른 PC 인계](<04_검증 기록/200_M31_다른_PC_작업_인계.md>)의 `m31-w01`은 당시
재개 기록이며 현재 브랜치 선택은 위 표를 따릅니다. 정리 범위와 검사는
[215번 기록](<04_검증 기록/215_M31_W03_이력과_문서_정비.md>)에 남깁니다.

## 3. 다른 PC에서 재개할 때

1. 실제 저장소의 [AGENTS.md](../AGENTS.md), branch·HEAD·미커밋 변경 소유권을 확인합니다.
   `git fetch origin --tags` 후 clean 상태에서 `m31-w04-dev`와 `origin/m31-w04-dev`를
   대조하고 fast-forward로만 갱신합니다. Dirty/diverged 상태를 덮어쓰지 않습니다.
2. 이 문서와 [M31 TODO](TODO_M31.md), [전체 기능 계약](<01_아두이노 코어 설계/19_NCS_Bluetooth_전체_기능과_예제_실행_계약.md>),
   readiness를 대조하고 board submodule·SDK lock을 확인합니다.
3. W04는 controller IQ event가 Host까지 오지만 raw HCI 우회가 Host의 RX enable/type
   상태를 설정하지 않아 callback 전에 폐기되는 경계부터 계속합니다. sample 수신·안테나
   전환·각도는 HOLD/NOT RUN이며 CTE 송신 성공을 RX/각도 PASS로 쓰지 않습니다.
4. W05는 wrong-key negative와 flash 간헐 중단의 원인 분리부터 계속합니다. 동일 ACL
   비암호화 read는 ATT 5로 20/20 PASS했고, exact flash 직후 secure RAS 100·stop/restart
   20·disconnect/reconnect 20은 두 번 PASS했습니다. 두 번의 성공으로 과거 중단의 단일
   원인을 확정하지 않습니다. wrong-key는 양쪽을 정상 bonding한 뒤 reflector bond만 공개
   `eraseAllBonds()`로 지우고, 재연결 repair pairing을 거부하는 one-sided stale-key 시험이
   최소 범위입니다. 이는 임의의 서로 다른 LTK 직접 주입 PASS로 확대하지 않습니다.
   RTT 출력은 비보정이므로 거리 정확도는 NOT RUN입니다.
5. 실제 보드 시험 직전에 CMSIS-DAP V2 probe의 SHA-256 identity·COM·role·firmware를 다시 결합합니다.
   과거 세 보드 mapping이나 임시 HEX 경로를 새 PC 결과물로 가정하지 않습니다.
6. 공개 `.ino`는 사용자가 읽고 수정할 수 있는 C++/NUCODE API 흐름을 유지합니다.
   Zephyr 직접 호출과 개발 마일스톤 이름은 공개 예제에 노출하지 않습니다.
7. HOST-W04 이후는 별도 재개 지시까지 보류합니다. 이번 문서 정리를 Host 구현 실적으로 계산하지 않습니다.

## 4. 검증·지원 경계

- W02 설치본 ISO 증거와 W03 profile별 원본은 보존합니다. W03-09~11의 최종 결과는
  [Media/Call](<04_검증 기록/211_M31_W03_Arduino_Media_Call_Control_완료.md>),
  [TMAP/GMAP](<04_검증 기록/212_M31_W03_Arduino_TMAP_GMAP_완료.md>),
  [HAP/HAS](<04_검증 기록/213_M31_W03_Arduino_HAP_HAS_완료.md>)를 따릅니다.
- M30-POWER-01 실제 전원 차단은 네 지점 × 3회 **12/12**입니다. [161번 기록](<04_검증 기록/161_M30_W08_실제_전원_HIL과_M30_완료.md>)의
  source·image와 reset 대체 없음·invalid boot 0을 보존하며 재예약하지 않습니다.
- Apple/Google·외장 마이크/스피커/코덱은 사용 가능한 구현·예제·설정/연결 안내·자동 검사가 필수입니다.
  실물 운용·상호운용은 사용자 후속 `NOT RUN`이며 v0.5.0 개발·공개 비차단입니다.
- Ubuntu/macOS 설치·USB·serial·debug 실기는 사용자가 최종 릴리스 단계에서 수행합니다.
  해당 OS 최종 지원 gate는 유지하며 외부 peer의 비차단 `NOT RUN`과 구분합니다.
- 정밀 RF·음질·거리/각도 보정과 Bluetooth qualification은 보드 기반 기능 PASS에 포함하지 않습니다.
- 실제 오류는 로그·레지스터로 원인을 확인하고 수정 후 동일 조건을 재검증합니다.
  실패 원본·source/image hash·조건·수치·timeout을 보존하고 새 성공으로 덮어쓰지 않습니다.
- 자동 mass erase/unlock/recover와 임의 결선·전원 변경을 하지 않습니다. Probe lock·watchdog·lease·STOP 계약을 유지합니다.

## 5. 이번 작업의 종료 범위

이번 묶음은 `m31-w04-dev`에서 W04/W05 진단 runner·fixture와 실기 원본을 보강하고
안정 단위마다 커밋·push합니다. main 반영, squash, branch/worktree 대량 정리,
release/tag 공개는 하지 않습니다. CI/CD 실행 요청·조회·대기도 생략하고 로컬 build·
host test·실기 HIL만 기록합니다.
