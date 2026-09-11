# T16 Peripheral Fabric 설치 통합

> 이 기록의 지원 상태·후보·다음 단계는 작성 당시 기준입니다. 이후 QDEC20/21 지원 범위와
> 영향 재검증은 [124번](124_T22전_QDEC_지원_범위_재확정.md), 최종 승인·공개·T24/T25 완료는
> [125번](125_v0.4.0_정식_릴리스_공개와_T24_T25_마감.md)에 있습니다. 당시 판정과 artifact identity는 그대로 보존합니다.

T16은 **완료**했습니다. T15에서 지원 범위를 확정한 Serial·Analog·Event·Stream·System Fabric을
Arduino 설치본에서 별도 raw Kconfig 편집 없이 선택할 수 있도록 `fabric` profile과
`NUCODE Peripheral Fabric` library로 통합했습니다. 구현 기준 commit은
`14a979620bb241c8030d7d1bf339564ccecd0b38`입니다.

## 1. 사용자 진입 경로

1. Arduino의 `Tools → Feature set`에서 `Peripheral Fabric (DAP UART disconnected)`를 선택합니다.
2. Sketch에서 `#include <NUCODE_Peripheral_Fabric.h>`를 사용합니다.
3. `File → Examples → NUCODE Peripheral Fabric → FabricCapabilities`로 설치 상태를 확인합니다.

예제에는 `prj.conf`나 `app.overlay` sidecar가 없습니다. Profile과 library feature resolver가 필요한
구성을 합성하므로 사용자가 raw 설정 파일을 직접 편집하지 않습니다.

## 2. 자원·지원 경계

| 항목 | T16 계약 |
| --- | --- |
| profile | `fabric` |
| feature | `nucode.peripheral.fabric` |
| 지원 | Serial, Analog, Event, PDM, I2S, System Fabric |
| QDEC | **unsupported**; T15 partial 결과를 공개 지원으로 승격하지 않음 |
| 기존 singleton | `Serial`, `Serial1`, `Wire`, `SPI`, ADC, PWM과 같은 profile에서 활성화하지 않음 |
| DAP UART | P1.4~P1.7 사용을 위해 물리 분리한 경우에만 profile 선택 |
| package 예제 | v0.4.0 후보 30개; v0.3.0 stable 29개는 역사적으로 유지 |

Factory가 반환하는 handle은 정적 view이며 조회만으로 주변장치를 시작하거나 핀을 구동하지 않습니다.
같은 serial block의 personality는 기존 소유권 계약에 따라 동시에 활성화할 수 없습니다. 따라서
설치 경로 추가가 singleton identity나 물리 block 충돌 규칙을 바꾸지 않습니다.

## 3. 검증 결과

| 검사 | 결과 |
| --- | --- |
| T16 profile/facade 계약 | **6/6 PASS** |
| 영향 Host 묶음 | **24 PASS, 조건부 Arduino discovery 1 SKIP** |
| CI 계약 | **46/46 PASS** |
| generated drift | 생성기 4개·생성물 5개 PASS |
| inventory·지원 계약 | identity 75, M24 23, M26 capability 16 PASS |
| M27 계약 | gate 16, blocker 6 유지 |
| C/C++/INO 정렬 | clang-format 22.1.8, 423개 PASS |
| T16 target | 324/324 build, FLASH 118,856 B / RAM 90,976 B |
| 설치형 Arduino build | `feature_set=fabric`, profile·feature provenance 확인, 153,936 B / RAM 123,074 B |
| 설치 staging와 source | 핵심 6개 파일 SHA-256 일치 |
| patch 공백 | `git diff --check` PASS |

Target build record는 clean `14a979620bb2`, NCS `v3.4.0`, Zephyr `4.4.0`, board
`nrf54l15dk/nrf54l15/cpuapp/nu54dk`를 기록했습니다. 설치형 build manifest는
`nucode:zephyr:nu54dk:feature_set=fabric`, profile `fabric`, feature
`nucode.peripheral.fabric`, selected library `NUCODE_Peripheral_Fabric`를 확인했습니다.

첫 target 구성은 TEMP·WDT device가 profile overlay에서 활성화되지 않아 실패했습니다. 원인은
System Fabric device 누락으로 특정했고 `temp`, `wdt30`, `wdt31`을 명시적으로 활성화한 뒤 같은
target을 324/324로 통과했습니다. `CONFIG_PRINTK=n` 경고도 불필요한 override를 제거해 해소했습니다.
형식 검사의 한 차례 실패는 clang-format이 initializer를 한 줄로 배치한 뒤 Host 정규식이 줄바꿈을
강제한 테스트 문제였으며, 공백 배치를 허용하도록 판정식을 고쳐 6/6으로 재검증했습니다.

## 4. 종료 상태

- T16: **100% 완료**
- 보드 flash·결선 변경: **없음**
- 새 물리 PASS 주장: **없음**; T11~T15의 검증된 지원 범위를 설치 경로에 연결함
- 공개 상태: **아직 v0.4.0 개발 후보**; tag·Release·stable index 생성 없음
- 다음 작업: **T17 — 최종 사용자 문서·지원 매트릭스 정리**
