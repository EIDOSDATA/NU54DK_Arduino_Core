# v0.5.0-rc.1 Testing

## 완료한 검증

| 검사 | 결과 | 근거 |
| --- | --- | --- |
| 비공개 exact package 이중 생성·byte 재현 | PASS | [267번 W08](<../../04_검증 기록/267_M31_W08_Windows_RC_준비와_M31_완료.md>) |
| GitHub Actions Windows 설치 예제 | 113/113 PASS, 8 shard, 누락·중복 0 | 267번 |
| v0.4.1 → RC upgrade·uninstall·reinstall·cache | PASS | 267번 |
| 대표 NU54DK upload·UART·`setup()` breakpoint | 물리 HIL PASS | 267번 |
| 공개 자산 인증 없는 재다운로드·SHA-256 | 7/7 PASS | [268번 공개 smoke](<../../04_검증 기록/268_v0.5.0-rc.1_공개와_다운로드_smoke.md>) |
| 공개 index 새 설치·예제 발견 | PASS, 113개 | 268번 |
| 공개 설치본 대표 clean compile | PASS, CteBeacon / `ble` | 268번 |
| 공개 설치본 uninstall·reinstall·marker 보존 | PASS | 268번 |

113/113은 **설치본 compile 분모**이며 113개 전부를 실제 보드에서 실행했다는 뜻이 아닙니다.
공개 smoke는 새 물리 HIL을 수행하지 않았습니다. 실물 결과는 동일 runtime payload의
W08 bounded upload/UART/debug PASS를 사용하며, CI/build 결과를 추가 실물 PASS로 확대하지 않습니다.

공개 source는 `7786984a186980f6220271cd506636e4564bc55d`입니다.
비공개 준비·공개 재포장·실물 image의 source와 runtime payload 관계는 각 기록에서 구분합니다.
최초 실패와 원인·교정 기록은 보존하며 후속 PASS로 덮어쓰지 않습니다.

## 설치한 사용자의 기본 확인

1. Boards Manager 또는 `arduino-cli core list`에서 설치 버전 `0.5.0-rc.1`을 확인합니다.
2. Post-install 최종 PASS와 고정 NCS v3.4.0 환경을 확인합니다.
3. 한 대의 NU54DK로 `Standard peripherals`의 `Blink`를 Verify·Upload합니다.
4. LED의 250 ms 점멸을 확인하고, Serial 예제를 사용할 때는 해당 DAP UART COM을 115200 8N1로 엽니다.
5. 고급 BLE 예제는 해당 README의 profile·역할·상대 보드·STOP 절차를 먼저 확인합니다.

여러 probe가 연결된 상태에서 대상을 추측해 flash하지 않습니다.
[업로드·디버그 안내](<../../02_빌드 설계/05_업로드와_디버그.md>)를 따라 대상과 COM을 결합합니다.
자동 mass erase·unlock·recover를 일반 오류 복구로 실행하지 않습니다.

제품 SDC DF IQ RX·AoD는 `UNSUPPORTED`, 외장 audio·정밀 보정 등은 미검증 범위입니다.
[Known issues](KNOWN_ISSUES.md)의 경계를 유지하며 Host/mock/build를 물리 PASS로 기록하지 않습니다.
