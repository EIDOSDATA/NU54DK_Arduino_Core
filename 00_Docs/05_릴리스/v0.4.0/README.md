# NU54DK Arduino Core v0.4.0

`v0.4.0`은 nRF54L15 주변장치의 직접 instance·DMA 제어를 `Peripheral Fabric` profile로
추가하면서 기존 Arduino singleton API와 BLE·Storage profile을 유지하는 릴리스입니다.

| 항목 | 값 |
| --- | --- |
| 제품선 | Peripheral Parity |
| 보드 | NU54DK v2, nRF54L15 application core |
| SDK | nRF Connect SDK v3.4.0 |
| 기본 설치 channel | Stable Boards Manager index |
| 현재 배포 상태 확인 | GitHub `v0.4.0` Release와 stable index의 실제 등록 여부 |

이 디렉터리의 문서는 release 후보와 공개 asset에 함께 쓰입니다. 문서가 저장소에 있다는 사실만으로
공개가 완료된 것은 아닙니다. 설치 가능한 최신 version은 stable index의 실제 항목을 기준으로
확인하십시오.

| 문서 | 내용 |
| --- | --- |
| [Release notes](RELEASE_NOTES.md) | 주요 변경과 지원 범위 |
| [Migration](MIGRATION.md) | v0.3.0 Sketch 이동 |
| [Testing](TESTING.md) | 검증 범위와 결과 해석 |
| [Troubleshooting](TROUBLESHOOTING.md) | 설치·빌드·실행 진단 |
| [Known issues](KNOWN_ISSUES.md) | 의도적 제한과 미지원 항목 |

## 설치

Arduino IDE의 Additional Boards Manager URLs에 stable index를 추가합니다.

```text
https://raw.githubusercontent.com/EIDOSDATA/NU54DK_Arduino_Core/main/package_nucode_nu54dk_index.json
```

Boards Manager에서 `NUCODE NU54DK Zephyr Boards`의 `0.4.0`을 선택합니다. 설치 후
post-install이 nRF Util 8.2.1, sdk-manager 1.16.1, NCS v3.4.0과 Toolchain
`dcbdc366a1`을 exact identity로 검사합니다. 설치 메시지에 prerequisite 실패가 있으면 platform
목록만 보고 성공으로 판단하지 말고 [Troubleshooting](TROUBLESHOOTING.md)을 따르십시오.

## Profile

| 목적 | Feature set |
| --- | --- |
| 기존 GPIO·Serial·Wire·SPI·ADC·PWM·Storage | `Standard peripherals` |
| BLE와 BLE library | `BLE NUS` |
| 직접 peripheral instance·DMA API | `Peripheral Fabric (DAP UART disconnected)` |

`fabric` profile은 DAP UART와 공유하는 pin을 직접 peripheral route에 사용합니다. 해당 DAP UART
switch 상태, 공통 GND와 I/O 전압을 실제 배선에 맞게 확인하십시오. SWD debug는 별도이며 유지할
수 있지만 watchdog·System OFF 관측에 영향을 줄 수 있습니다.

## 검증 해석

M24 Serial 23개 identity, M25 공개 대상 Analog/Event/Stream, M26 TEMP/WDT30과 합의한
동시성·오류 복구·안정성 범위를 실제 NU54DK로 검증했습니다. QDEC20/21은 기본 정·역회전과
SAMPLE/REPORT event 누산을 지원하지만 반복 manual `read()/clear`의 무손실은 보증하지
않습니다. 반복 Serial personality handover, 모든 주변장치 동시 조합과 정밀 계측·모든 외부
부품 조합도 보증 범위가 아닙니다. 상세 근거는 [검증 기록](<../../04_검증 기록/README.md>)과
[Known issues](KNOWN_ISSUES.md)를 따릅니다.
