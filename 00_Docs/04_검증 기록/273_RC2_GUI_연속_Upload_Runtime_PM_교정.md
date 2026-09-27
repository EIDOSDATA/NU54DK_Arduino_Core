# 273 — RC2 GUI 연속 Upload runtime PM 교정

> **역사 기록 · 정식 공개 후 안내:** 본문의 버전·진행률·다음 작업은 해당 실행 당시 상태다.
> 현재 설치·지원 버전은 [v0.5.0](<../05_릴리스/v0.5.0/README.md>)이며 개발 기준은 `main`이다.
> 완료된 main 통합·RC 브랜치 정리와 공개 결과는 [274번](274_v0.5.0_정식_릴리스_승인과_공개.md),
> 후속 작업은 [HANDOFF](../HANDOFF.md)를 따른다. 당시 source·수치·PASS/FAIL/HOLD/NOT RUN은 보존한다.

## 1. 범위와 결론

2026-09-27 실제 Windows Arduino GUI와 NU54DK 한 대에서 공개 `v0.5.0-rc.2` 설치본의
Blink 연속 Upload를 확인했다. 250 ms Blink의 최초 compile·Upload·실행은 성공했지만,
Sketch를 100 ms로 수정한 두 번째 Upload는 pyOCD가 target에 연결하는 단계에서
`SWD/JTAG communication failure (No ACK)`로 실패했다. USB를 뺐다 다시 연결하면 같은 100 ms
image가 성공했으므로 source compile, link와 HEX 생성 결함은 아니었다.

VS Code에서 사용한 `NU54DK_Zephyr_DTS`와 같은 board target으로 Zephyr 기본 Blink를 clean build해
최종 Kconfig를 비교했다. Zephyr 기본 Blink에는 device runtime PM이 없었고 Arduino Standard에는
다음 설정이 추가되어 있었다.

- `CONFIG_PM_DEVICE=y`
- `CONFIG_PM_DEVICE_RUNTIME=y`
- `CONFIG_PM_DEVICE_RUNTIME_DEFAULT_ENABLE=y`
- `CONFIG_PM_DEVICE_POWER_DOMAIN=y`

Standard는 Wire·SPI·PWM의 runtime route 때문에 device runtime PM 자체가 필요하다. 각 backend는
사용 시 `pm_device_runtime_enable()`과 `pm_device_runtime_get()`을 명시적으로 호출하므로 전역
`PM_DEVICE_RUNTIME_DEFAULT_ENABLE`은 필요하지 않다. Standard profile에
`CONFIG_PM_DEVICE_RUNTIME_DEFAULT_ENABLE=n`을 명시해 부팅 시 모든 runtime 장치의 자동 suspend만
막았다.

수정 설치본에서 Standard Blink를 다시 build했고, 사용자 GUI에서 250 ms → 100 ms 변경 후 두 번째
Upload를 USB 재연결 없이 성공했다. 따라서 연속 Upload 실패 원인은 pyOCD runner, Blink source 또는
board DTS가 아니라 Standard image의 전역 runtime PM 자동 enable로 판정한다.

## 2. 진단 중 배제한 항목

| 후보 | 결과 |
| --- | --- |
| build cache·수정 source 미반영 | 두 image hash가 달랐고 compile·link·artifact 검증은 모두 성공하여 배제 |
| pyOCD `smart_flash`·packet 제한 | 동일 옵션 변경 뒤에도 성공/실패가 반복되어 원인 아님 |
| board DTS runner 차이 | 사용자 VS Code board도 custom `board.cmake`의 pyOCD를 사용하므로 runner 종류 차이 아님 |
| SWD 주파수·배선 | USB 재연결만으로 같은 image가 성공하고 첫 Upload가 반복 성공하여 주원인 아님 |
| `under-reset` 자동 복구 | 쓰기 없는 진단에서 DAPLink USB timeout과 probe 소실이 발생해 일반 해결책에서 제외 |

진단에서는 recover, unlock, mass erase를 실행하지 않았다. 원시 probe UID는 문서와 공유 log에
기록하지 않았다.

## 3. 구현

| 파일 | 변경 |
| --- | --- |
| `variants/nu54dk/profiles/standard/prj.conf` | `CONFIG_PM_DEVICE_RUNTIME_DEFAULT_ENABLE=n` 고정 |
| `tools/nu54-builder/src/nu54_builder_impl/upload.py` | No ACK 안내에서 이 보드에 부적합한 under-reset 권고를 제거하고 USB 재연결 진단 경계 명시 |
| `tests/host/test_m15_board_system_contract.py` | Standard profile이 전역 runtime PM 자동 enable을 다시 허용하지 않는 회귀 검사 추가 |

시험 중 검토한 DAPLink MSD 업로드 통합은 원인 교정이 아니므로 최종 구현에서 제거했다. 기본 Upload는
계속 `CMSIS-DAP + pyOCD`이고 외장 J-Link 선택 경로도 유지한다.

## 4. 검증

| 검사 | 결과 |
| --- | --- |
| 동일 DTS Zephyr 기본 Blink clean build | PASS, FLASH 30,292 B / RAM 5,800 B |
| Arduino Adaptive Blink clean build | PASS, FLASH 40,832 B / RAM 17,423 B; runtime PM 없음 |
| 교정한 Arduino Standard Blink clean build | PASS, FLASH 81,572 B / RAM 29,439 B |
| 최종 Standard Kconfig | `PM_DEVICE_RUNTIME=y`, `PM_DEVICE_RUNTIME_DEFAULT_ENABLE` 비활성 |
| 사용자 GUI 250 ms → 100 ms 연속 Upload | PASS, 두 번째 Upload 전에 USB 재연결 없음 |
| 관련 Host unit | `test_m8_flash` + `test_m15_board_system_contract`, 30 tests PASS |
| 문서 UTF-8·상대 링크 | M12 docs, Markdown 445개 PASS |
| Python 구문·staged diff | `py_compile`, `git diff --cached --check` PASS |

사용자 GUI의 정확한 IDE patch version과 화면 캡처는 수집하지 않았다. 따라서 RC2 GUI 전체 체크리스트를
PASS로 바꾸지 않고 Blink 단일·연속 Upload 항목만 별도 PASS로 기록한다.

## 5. 배포 경계

공개 `v0.5.0-rc.2` tag, archive와 RC index는 immutable 자산으로 유지하며 다시 만들거나 교체하지 않는다.
이번 교정은 실제 사용자 설치 경로에 적용해 확인한 뒤 main과 정식 v0.5.0에 포함했다. 기존 공개 RC2를
Boards Manager에서 제거·재설치하면 공개 archive 원본으로 돌아가므로 이 후속 교정이 포함되지 않는다.
RC2 재설치·로컬 수정 대신 [v0.5.0 stable](<../05_릴리스/v0.5.0/README.md>)을 설치한다.
정식 package source·공개 설치 smoke와 RC branch 정리는 [274번](274_v0.5.0_정식_릴리스_승인과_공개.md)을 따른다.
