# NU54DK Arduino Core v0.4.0 Release Notes

## 주요 변경

- nRF54L15의 75개 peripheral identity와 block·pin·DMA·event 소유권을 단일 manifest로
  관리합니다.
- `Peripheral Fabric (DAP UART disconnected)` profile과
  `<NUCODE_Peripheral_Fabric.h>`를 추가했습니다.
- `SerialFabric`에서 UARTE 5개, SPIM 5개, SPIS 5개, TWIM 4개, TWIS 4개를 선택할 수
  있습니다.
- `AnalogFabric`은 SAADC scan/continuous DMA와 PWM20/21/22 sequence를 제공합니다.
- `EventFabric`은 TIMER·GPIOTE·EGU·DPPI·PPIB의 검증된 identity를 제공합니다.
- `StreamFabric`은 PDM20/21과 I2S20 double-buffer 경로, QDEC20/21의 기본 정·역회전과
  SAMPLE/REPORT event 누산을 제공합니다.
- `SystemFabric`은 온칩 TEMP와 WDT30을 제공합니다.
- 기존 `Serial`, `Serial1`, `Wire`, `SPI`, ADC/PWM/Tone/Servo, BLE와 Storage API는
  `standard`·`ble` profile에 유지됩니다.
- 설치 package 예제는 `NUCODE Peripheral Fabric` 예제를 포함해 30개입니다.

## 수정한 결함

- Fabric PWM과 공개 PWM이 같은 hardware block을 다른 key로 소유하던 문제를 공통
  `pwm_block + instance` identity로 통합했습니다.
- Windows에서 긴 T16 crypto object 경로가 archive 도구의 260자 경계를 넘던 문제를 짧은
  build root 계약으로 해결했습니다.
- Nordic 공식 고정 URL의 nRF Util 8.2.1 재빌드로 SHA-256이 바뀐 것을 서명·version으로
  확인하고 새 exact byte를 prerequisite pin에 반영했습니다.

## 호환성과 제한

v0.3.0 Sketch는 기본적으로 수정 없이 `standard` 또는 `ble` profile을 사용합니다. 직접 instance
API가 필요한 Sketch만 `fabric`으로 이동하십시오. QDEC20/21은 지원하지만 연속 카운트에는
SAMPLE/REPORT event 경로를 사용해야 하며, 동작 중 반복 manual `read()/clear`의 무손실 누산은
보증하지 않습니다. 반복 Serial personality handover, 모든 가능한 동시 조합, 정밀 ADC 정확도,
jitter·음질·신호 품질과 모든 외부 부품 호환성도 보증하지 않습니다.

공개 여부와 asset identity는 GitHub `v0.4.0` Release와 stable index의 실제 등록을 기준으로
판정합니다.
