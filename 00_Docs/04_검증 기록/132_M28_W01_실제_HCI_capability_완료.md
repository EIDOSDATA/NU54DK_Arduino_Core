# M28-W01 실제 HCI capability 완료

| 항목 | 결과 |
| --- | --- |
| 작업일 | 2026-09-12 |
| 실제 시험 Core | `78078a422351cd373e0d153987add2c5b770acbb` |
| Board / NCS / Zephyr | `fe65f2f0880b…` / `99553055607b…` / `bf801e4e3d19…` |
| Toolchain | Windows bundle `dcbdc366a1` |
| Test ID | `M28-CAP-01` |
| 최종 판정 | **Host·target·실제 HCI 6/6 PASS / M28-W01 완료** |
| M28 진행률 | **완료 1/8, 12.5% / 다음 M28-W02** |

## 1. 실제 controller와 Host 결과

`M28CAP/1` runner가 한 NU54DK의 exact image를 flash한 뒤 PROBE/READY handshake, 128-bit nonce,
고정 15줄과 Core·board·NCS·Zephyr revision을 모두 대조했다. 임의 banner·중복·누락·순서 변경·
stale nonce·wrong revision·timeout은 허용하지 않았다.

| 기능군 | Host | 실제 controller HCI | M28 production 구현 |
| --- | --- | --- | --- |
| Multi-role / multi-link | 2-link, central 1 + peripheral 1 구성 PASS | 필수 command PASS | W02 이후 구현·동시 2-link HIL 미실행 |
| Extended advertising/scanning | Kconfig PASS | feature·command·실제 광고 set 생성/삭제 PASS | W03 미착수 |
| Periodic advertising/sync·PAST | Kconfig PASS | feature·command·periodic list add/remove PASS | W04 미착수 |
| PAwR advertiser/scanner | Kconfig PASS | advertiser/scanner feature PASS | W05 미착수 |
| Privacy/RPA | privacy·settings 구성 PASS | feature·필수 command·resolving list 8 PASS | W06 회전·bond 재연결 미실행 |
| Per-link control | DLE·remote-info·PHY 구성 PASS | feature·필수 command PASS | W02/W06 두 link 격리 미실행 |

HCI version은 17, manufacturer는 89였다. 실제 controller가 보고하거나 Host API 왕복으로 확인한
자원은 advertising data 257 byte, advertising set 최소 1개, periodic advertiser list 최소 1개,
resolving list 8개다. 이 결과는 readiness의 `source_status=candidate`를 바꾸지 않는다. 별도
`runtime_hci_status`만 `passed`이며, Core 공개 API·RF 동작·전체 M28 HIL은 아직 PASS가 아니다.

## 2. 실패 분류와 동일 조건 재검증

| exact source | 관측 | 원인 분류와 수정 |
| --- | --- | --- |
| `3d15c852…` | READY 앞 NCS boot banner | `CONFIG_NCS_BOOT_BANNER=n`과 compile-time assert |
| `e3314f0b…` | reset 직후 UART high-Z byte | reset 구간 폐기 뒤 exact PROBE로 세션 arm |
| `f1b4e59f…` | advertising-set 수 직접 HCI가 `-EIO` | combined adapter 경계에 맞춰 실제 Host API set/list 왕복으로 교체 |
| `c3859cc3…` | 광고 set 생성 `-EAGAIN` | `CONFIG_BT_SETTINGS=y`에서 누락한 `settings_load()`로 identity·Host READY 완료 |
| `9b05787b…` | 첫 probe MSD timeout, 두 번째 probe raw command 판정 실패 | 반복을 중단하고 정상 probe로 분리; SDC v3.4.0 command map의 optional query·clear와 필수 명령 재분류 |
| `78078a42…` | 고정 protocol 15줄·6개 기능군 | 같은 SDK/toolchain과 정상 DAP/UART 경로에서 **PASS** |

첫 probe의 DAPLink 전송 실패는 3,072 byte에서 `transfer timed out`, 이어진 재시도는 permission
denied였다. BLE 실행 전 transport 실패이므로 HCI 결과로 세지 않았고 같은 probe 반복을 중단했다.
GPIO 점퍼를 쓰지 않는 시험이라 연결성 진단 대상 GPIO는 없었다. 두 번째 probe에서 flash·UART·
revision이 정상임을 확인한 뒤 controller 결과만 수정·동일 조건 재검증했다.

## 3. 검증과 증거

| 검사 | 결과 |
| --- | --- |
| W01 parser + readiness Host | **19/19 PASS** |
| 전체 Host gate | **PASS** (`M12_GATE_PASS=host`) |
| 신규 C++ clang-format 22.1.8 | **PASS** |
| `nucode.m28.ble_capability` exact target build | **1/1 PASS**, 72.80초, warning 0 |
| 실제 `M28-CAP-01` | **6/6 PASS**, 외부 GPIO 결선·mass erase·recover 없음 |
| HEX | 757,844 byte, SHA-256 `65f531e6be6e0ecfa6e64139a860613d773f8ad8682626970ba5283d4de3b121` |
| Evidence JSON | 2,903 byte, SHA-256 `8037f43780e1e993eb9c5a847936edfb4922e3950b0ff4615b0cdfcca01350cf` |
| Raw CRLF transcript | 2,014 byte, SHA-256 `1aa891eaa7594db85f8d78f98571aaf2acd60b40320d29a2dcd762cba65d3347` |

[증거 manifest](evidence/m28-cap-01-78078a42/manifest.json)는 exact image·build record·raw artifact
hash를 연결한다. [Evidence JSON](evidence/m28-cap-01-78078a42/evidence.json)은 runner 원본이며,
[정규화 transcript](evidence/m28-cap-01-78078a42/m28-cap-01-78078a42.normalized.log)는 Git의 LF
정규화를 적용한 공개 복사본이다. Raw CRLF transcript의 길이와 hash는 evidence와 manifest에
별도로 보존해 정규화본과 혼동하지 않는다. Probe UID 원문은 기록하지 않고 SHA-256만 남겼다.

## 4. 다음 작업과 장비 경계

다음 작업은 `M28-W02`의 고정 크기 per-link slot, generation 기반 opaque handle과 link별 event
기반이다. Host 계약·구현·단위시험·target build까지 자동 진행한다. 현재 NU54DK와 독립 DAP/UART
경로는 2개를 확인했지만 M28-LINK/PER/CTRL/SOAK에 필요한 3개 중 하나가 부족하고 packet trace
수단은 미확인이다. 세 보드 실기 시점 전까지 이 부족분을 W02 Host 작업의 차단 사유로 사용하지 않는다.
