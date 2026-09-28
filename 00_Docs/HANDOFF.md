# 개발 인계 — v0.5.0 완료와 v0.6.0 후속 계획

최종 정리: **2026-09-28**. M28~M31, 메모리 최적화 P0~P2, RC1/RC2, RC2 이후 Standard runtime PM
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
| v0.6.0 계획 | M32 0/12, M33 0/8, HOST-W04~W08 사용자 보류 | [v0.6.0 계획](TODO_v0.6.0.md) · [M32](TODO_M32.md) · [M33](TODO_M33.md) |

완료 기능의 상세 계약과 기계 판정 원장은 다음과 같습니다.

- M28-W01~M28-W08: [GAP·Link·Privacy 계약](<01_아두이노 코어 설계/15_M28_BLE_GAP_Link_Privacy_착수_계약.md>) · [`m28-ble-readiness.json`](../variants/nu54dk/m28-ble-readiness.json)
- M29-W01~M29-W08: [ATT/GATT·L2CAP 계약](<01_아두이노 코어 설계/16_M29_ATT_GATT_L2CAP_착수_계약.md>) · [`m29-ble-readiness.json`](../variants/nu54dk/m29-ble-readiness.json) · 완료 8/8
- M30-W01~M30-W08: [Security·Profile·DFU 계약](<01_아두이노 코어 설계/17_M30_BLE_Security_Profile_DFU_착수_계약.md>) · [`m30-ble-readiness.json`](../variants/nu54dk/m30-ble-readiness.json) · `M30-POWER-01`

## 재개 지점

v0.5.0의 완료 gate를 다시 열지 않습니다. M32·M33의 다음 기능 개발은 v0.6.0 계획을 따릅니다.
다음 구현 항목은 M32-W01이며 버전 배정과 문서 변경만으로 구현·보드 시험을 시작하지 않습니다.
후속 버전은 M34~M37 v0.7.0, M38~M41 v0.8.0, M42~M45 v0.9.0입니다. 번호와 기능 범위는
유지하며 [276번 결정](<04_검증 기록/276_v0.6.0_후속_버전_배정과_문서_동기화.md>)을 따릅니다.
M32/M33, Ubuntu/macOS Host 확대, 외장 audio 장치와 상용 peer 실물 상호운용은 v0.5.0 완료 조건이
아니며 자동으로 재개하지 않습니다.

제품 SDC의 DF IQ RX·AoD는 고정 NCS v3.4.0에서 `UNSUPPORTED`입니다. Zephyr LL 연결형 내부 진단을
제품 지원으로 승격하지 않습니다. CS 간헐 RF/controller loss·counter gap, SDC high-water 비노출,
정밀 RF·음질·거리/각도 보정도 v0.5.0의 새 차단 조건으로 되살리지 않습니다.

## 고정 환경

| 항목 | 기준 |
| --- | --- |
| 저장소 / 기본 branch | `C:\Users\eidos\GitHub\NU54DK_Arduino_Core` / `main` |
| 릴리스 백업 branch | `Release-0.5.0` |
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

전체 문서 검토 범위·방법과 hash는 [문서 감사 원장](document-review.json), 공개 후 누락 교정은
[275번 기록](<04_검증 기록/275_v0.5.0_공개_후_문서_전수_재검토.md>), 실행별 실제 결과는
[검증 기록](<04_검증 기록/README.md>)에서 확인합니다. Hash·링크 검사 통과와 본문 의미의 최신성은
별도로 판정하며, 과거 raw evidence를 새 source의 실기 PASS로 재사용하지 않습니다.
