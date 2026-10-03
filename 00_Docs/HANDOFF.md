# 개발 인계 — v0.5.0 완료와 v0.6.0 후속 계획

최종 정리: **2026-10-04**. M28~M31, 메모리 최적화 P0~P2, RC1/RC2, RC2 이후 Standard runtime PM
교정과 Windows 정식 `v0.5.0` 공개를 완료했습니다. 현재 stable·지원 버전은 v0.5.0 하나입니다.

## 현재 상태

| 범위 | 상태 | 원본 |
| --- | --- | --- |
| Stable | v0.5.0, Windows 10/11 x64, 16개 library·113개 예제 | [릴리스 안내](<05_릴리스/v0.5.0/README.md>) |
| M28·M29·M30 | 각각 8/8 완료, M30 전원 차단 12/12 | [v0.5.0 TODO](TODO_v0.5.0.md) |
| M31 | W01~W08 8/8, package·설치·예제·수명주기·대표 HIL 완료 | [M31 TODO](TODO_M31.md) |
| RC1/RC2 | 로컬·원격 branch 삭제 완료, 공개 tag·Pre-release·asset과 evidence 보존 | [RC2 TODO](TODO_v0.5.0-RC2.md) |
| 연속 Upload | Standard Blink 250 ms → 100 ms를 USB 재연결 없이 실제 GUI에서 PASS | [273번](<04_검증 기록/273_RC2_GUI_연속_Upload_Runtime_PM_교정.md>) |
| 정식 공개 | exact package 이중 재현·승인·tag/Release·단일 stable catalog·공개 smoke | [274번](<04_검증 기록/274_v0.5.0_정식_릴리스_승인과_공개.md>) |
| v0.6.0 개발 | M32 **12/12 완료**·M33 **2/8**, M33-W01 원장·W02 표준 GATT/Beacon 완료 | [v0.6.0 계획](TODO_v0.6.0.md) · [M32](TODO_M32.md) · [M33](TODO_M33.md) |

완료 기능의 상세 계약과 기계 판정 원장은 다음과 같습니다.

- M28-W01~M28-W08: [GAP·Link·Privacy 계약](<01_아두이노 코어 설계/15_M28_BLE_GAP_Link_Privacy_착수_계약.md>) · [`m28-ble-readiness.json`](../variants/nu54dk/m28-ble-readiness.json)
- M29-W01~M29-W08: [ATT/GATT·L2CAP 계약](<01_아두이노 코어 설계/16_M29_ATT_GATT_L2CAP_착수_계약.md>) · [`m29-ble-readiness.json`](../variants/nu54dk/m29-ble-readiness.json) · 완료 8/8
- M30-W01~M30-W08: [Security·Profile·DFU 계약](<01_아두이노 코어 설계/17_M30_BLE_Security_Profile_DFU_착수_계약.md>) · [`m30-ble-readiness.json`](../variants/nu54dk/m30-ble-readiness.json) · `M30-POWER-01`

## 재개 지점

새 채팅에서는 [M33 개발 순서와 재개 지시](M33_HANDOFF.md)를 먼저 확인합니다. 작업 브랜치는
`Dev-0.6.0-M33`이며, 해당 문서에 전체 실행 순서·M32 이력 백업·복사용 지시문을 모았습니다.
최신 사용자 요청에 따라 원격 CI 결과 조회·완료 대기는 생략하되 로컬 검사와 실제 결과 기록은 유지합니다.

M32-W01~W12는 **12/12 완료**입니다. M33-W01은 exact `a3585ffb…`에서 완료했고 W02는 exact
`4ebd4952…`에서 표준 GATT·Beacon 구현, 공개 예제 9/9 build와 두/세 보드 HIL을 완료했습니다.
다음 기능 작업은 **M33-W03 Fast Pair·ANCS·AMS와 scripted peer 검증**입니다.

| 다음 작업 | 입력·유지할 경계 |
| --- | --- |
| M33-W01~W02 완료 기준선 | W01 전체 원장, W02 profile/Beacon exact evidence와 사용자 후속 `NOT_RUN` 구분 |
| M33-W03~W06 기능·예제·통합 | M32 지원 후보 38개는 `not_published`; 자동 검사와 외부 peer 실제 검증을 구분 |
| M33-W06 이후 Host·package·공개 | W06 완료 후 HOST-W04부터 순차 재개; RC1으로 Host 실기 마감, OS별 최종 gate와 별도 공개 승인 유지 |

착수·완료 조건은 [M33 TODO](TODO_M33.md), 작업별 실제 수치와 원본은 [M32 TODO](TODO_M32.md)가 소유합니다.
완료된 M32 실기를 다음 작업으로 다시 예약하지 않습니다.

**2026-10-03 사용자 결정:** Host는 M33 기능 개발과 병렬 진행하지 않습니다.
M33-W01~W06 완료 → HOST-W04~W06 및 W07 도구 준비 → M33-W07 시험용 RC1 준비 →
HOST-W07 실제 OS 검증·W08 마감 및 M33-W07 완료 → M33-W08 공개 승인·게시·공개 설치 순서입니다.
현재는 M33 2/8·HOST 3/8이며 W06 완료 전까지 Host 착수 대기입니다. Ubuntu/macOS의 실제
장비 검증은 RC 단계에서 수행하며, 접속·결선 상태를 확인하지 않고 사용 가능한 것으로 가정하지 않습니다.

### M32 완료 기준선

| 범위 | 최종 검증과 원본 |
| --- | --- |
| W08 BLOB·signed MDFU | BLOB 10/10회, MDFU 5회×두 target 10/10·negative·confirm/rollback·STOP/cleanup. [294번](<04_검증 기록/294_M32_W08_BLOB_PASS와_MDFU_timeout_진단.md>) |
| W09·W10 radio·공존 | 단독 radio 회귀와 세 내부 조합 protocol별 4,000/4,000. [284번](<04_검증 기록/284_M32_W09_802154_ESB_software와_HIL_blocker.md>) · [285번](<04_검증 기록/285_M32_W10_무선_공존_software와_HIL_blocker.md>) |
| W11 회귀·soak | `94f02544…` native 62/62·exact family 12/12·signed MDFU 10/10·1,800초 soak. [286번](<04_검증 기록/286_M32_W11_software_회귀와_HIL_soak_blocker.md>) |
| W12 정합성·최종 CI | `49099e74…` 원장·예제·후속 인계 정합성, [CI 9/9 성공](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/37099299097). [287번](<04_검증 기록/287_M32_W12_정합성_감사와_후속_인계.md>) |

과거 timeout·Apply·rollback·privacy 실패 원본은 위 기록에 보존합니다. 최종 W11 preflight에서는
세 보드 AHB debug가 열려 있어 승인받은 ERASEALL을 실행하지 않았습니다. 이 관찰은 당시 상태이며,
새 실기 때 probe·COM·image·결선을 다시 확인합니다. HOST-W07은 위 순차 Host 계획을 따릅니다.

### SDK와 후속 버전

현재 v0.6.0 개발에서는 NCS v3.4.0을 유지합니다. **제품 v0.7.0은 NCS v3.4.1 전체 전환만** 수행합니다.
[SDK-W01~W06 계획](TODO_v0.7.0.md)은 기존 기능 유지에 필요한 호환 수정·회귀·배포 전환을 다루며
새로운 Storage/보안 API·TF-M 확장·다중 update transport 같은 기능은 넣지 않습니다.
[SDK 영향 검토](<00_사전 리서치/03_NCS_3.4.1_변경과_개발_영향.md>)에 공식 수정 사항,
현재 설정의 적용성, 업그레이드 회귀 목록을 남깁니다. M32 BLOB의 과거 실패와 고정 NCS v3.4.0에서 완료한 재시험을 SDK 전환 결과로 해석하지 않습니다.

기존 M 번호·기능은 유지하고 M34~M37은 v0.8.0, M38~M41은 v0.9.0, M42~M45는 v0.10.0으로 옮깁니다.
제품 SDC DF IQ RX·AoD의 고정 SDK 미지원, CS 간헐 loss·counter gap 비차단 관찰,
외부 peer/장치·정밀 계측 경계는 유지합니다. 이는 새로운 assert·데이터 손상·보안 오류를
무시하라는 뜻이 아닙니다.

## 고정 환경

| 항목 | 기준 |
| --- | --- |
| 저장소 / 작업 브랜치 | `C:\Users\eidos\GitHub\NU54DK_Arduino_Core` / `Dev-0.6.0-M33` |
| M33 분기 기준 | M32 전체 결과가 통합된 `main`의 `314c04f2…` |
| M32 원본 이력 | 로컬·원격 M32 브랜치 삭제 완료; [M33 인계의 로컬 Git bundle](M33_HANDOFF.md#m32-원본-이력-보관)에 보존 |
| 릴리스 백업 branch | 원격 `Release-0.5.0` |
| v0.5.0 백업 기준선 | `4790e3fa532ffea00bfd96780079cbadea263ca5`; 후속 문서·개발로 이동하지 않음 |
| Target | `nrf54l15dk/nrf54l15/cpuapp/nu54dk` |
| NCS / Zephyr | v3.4.0 · `99553055607b2e9885fbc80ccd11fa9da81c2df0` / `bf801e4e3d19e1ffa76164346480cb7734dd2800` |
| Board gitlink | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |
| Windows toolchain | `dcbdc366a1` |
| 정식 tag source | `v0.5.0` → `0999b6a721b4579faa6a7a4d91d04da5e4960c07` |
| RC1 tag source | `v0.5.0-rc.1` → `7786984a186980f6220271cd506636e4564bc55d` |
| RC2 tag source | `v0.5.0-rc.2` → `b2e7a587ba6fde31e033dc21008d7084bd6e631b` |

정식 tag source와 최종 main/index commit은 다를 수 있습니다. package manifest와 `v0.5.0` tag는 Squash한
exact source commit을 가리키고, root catalog와 공개 결과 마감은 후속 main commit에 기록합니다.
문서 마감 `4790e3fa`의 [M12 CI](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/36316010285)는
9/9 job 성공이며 6개 대표 구성도 실제 build했습니다. 새 v0.6.0 source의 검증 결과를 뜻하지 않습니다.

## 안전·검증 원칙

- 작업 전 [AGENTS](../AGENTS.md)를 읽고 branch·HEAD·미커밋 변경·원격 ref·submodule을 직접 확인합니다.
- 과거 공개 자산과 실패/HOLD/NOT RUN evidence는 수정하거나 삭제하지 않습니다.
- Host/mock/build/CLI Verify/Upload/기능 HIL을 서로 대체하지 않습니다.
- probe lock·watchdog·명령 lease·STOP·clock/핀 반환을 유지합니다.
- 자동 mass erase·unlock·recover, 임의 전원·USB·결선 변경을 하지 않습니다.
- 원시 probe UID·인증 정보를 문서나 공유 로그에 기록하지 않습니다.
- 다른 PC 준비는 [Windows 환경](<02_빌드 설계/09_Windows_개발환경_설정.md>), 이력 정리 뒤 checkout은
  [기여 안내](../CONTRIBUTING.md#이력-정리-뒤-기존-checkout)를 따릅니다.

전체 문서 검토 범위·방법과 hash는 [문서 감사 원장](document-review.json), 이번 문서 정비·main 통합은
[295번 기록](<04_검증 기록/295_M32_문서_전수_정비와_main_Squash_통합.md>), 실행별 실제 결과는
[검증 기록](<04_검증 기록/README.md>)에서 확인합니다. Hash·링크 검사 통과와 본문 의미의 최신성은
별도로 판정하며, 과거 raw evidence를 새 source의 실기 PASS로 재사용하지 않습니다.
