# v0.4.0-rc.1 Release Notes — 비공개 후보

이 문서는 아직 공개되지 않은 v0.4.0 후보의 변경 범위를 설명합니다. 설치 가능한 stable은
v0.3.0이며, tag·GitHub Release·stable index는 T22 소유자 승인 전까지 만들지 않습니다.

## 주요 변경

- nRF54L15의 75개 peripheral identity와 소유권·DMA·HIL 상태를 단일 manifest로 관리합니다.
- `Peripheral Fabric (DAP UART disconnected)` profile과 `<NUCODE_Peripheral_Fabric.h>`를 추가했습니다.
- `SerialFabric`은 UARTE 5개, SPIM 5개, SPIS 5개, TWIM 4개, TWIS 4개를 선택합니다.
- `AnalogFabric`은 SAADC scan/continuous DMA와 PWM20/21/22 sequence를 제공합니다.
- `EventFabric`은 TIMER·GPIOTE·EGU·DPPI·PPIB의 검증된 identity를 제공합니다.
- `StreamFabric`은 PDM20/21과 I2S20의 double-buffer 경로, QDEC20/21의 기본 정·역회전과
  SAMPLE/REPORT event 누산을 제공합니다.
- `SystemFabric`은 온칩 TEMP와 WDT30을 제공합니다.
- 기존 `Serial`, `Serial1`, `Wire`, `SPI`, ADC/PWM/Tone/Servo와 BLE/Storage API는
  `standard`·`ble` profile에 그대로 남습니다.

## 검증과 교정

T11~T15에서 단독 기능, 오류 복구, 허용 동시성, C05 1시간 soak와 UARTE00을 검증했습니다.
T14에서 발견한 Fabric PWM과 공개 PWM의 block identity 불일치는 공통 `pwm_block + instance`
자원 key로 교정하고 Host·target·두 보드 회귀를 통과했습니다. T16은 검증된 직접 API를 설치
profile과 예제에 연결했고, T17은 이 노출을 manifest·API 문서와 맞췄습니다.

## 지원 제한과 의도적으로 지원하지 않는 범위

- QDEC20/21은 지원하지만 동작 중 반복 manual `read()/clear`의 무손실 누산은 보증하지
  않습니다. 연속 카운트에는 SAMPLE/REPORT event 경로를 사용합니다.
- 반복 Serial personality handover는 사용자 결정에 따라 최종 필수 시험에서 제외했습니다.
- 모든 가능한 peripheral 조합, 정밀 ADC 정확도, jitter·음질·신호 품질과 외부 부품별 호환성을
  보증하지 않습니다.
- Native USB, Loader/LLEXT, OTA/DFU, Wi-Fi와 Ethernet은 이번 제품선 범위가 아닙니다.

최종 설치 예제 수는 v0.3 stable 29개와 구분해 v0.4 후보 30개입니다. 전체 package 재현성과
Boards Manager 수명주기는 T20~T21에서 다시 검증합니다.
