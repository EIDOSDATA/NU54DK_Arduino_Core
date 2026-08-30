# NCS v3.4.0 coverage 요약

> 이 파일은 `tools/coverage/m17_coverage.py render`로 생성합니다. 직접 수정하지 마십시오.

## Exact revision

| 구성 | revision |
| --- | --- |
| ncs | `99553055607b2e9885fbc80ccd11fa9da81c2df0` |
| zephyr | `bf801e4e3d19e1ffa76164346480cb7734dd2800` |
| board | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |

## 집계

- 전체 record: 9
- 상태: build-only=3, deferred=3, supported=3
- 검증: pass=3, planned=6

## Record

| ID | 영역 | 제공 경로 | 상태 | 검증 | profile |
| --- | --- | --- | --- | --- | --- |
| `arduino.adafruit-lsm6ds` | sensor | build-profile-only | build-only | arduino-library-compile:planned | standard |
| `board.system` | board-system | arduino-wrapper | supported | hil:pass | standard |
| `nrf.802154-phy-test` | radio-networking | excluded-deferred | deferred | build-feasibility:planned | radio |
| `nrf.ble-nus` | ble | arduino-wrapper | supported | hil:pass | ble |
| `nrf.crypto-rng` | crypto-random | ncs-direct-example | build-only | ncs-direct-build:planned | standard |
| `nrf.matter-template` | radio-networking | excluded-deferred | deferred | build-feasibility:planned | radio |
| `nrf.openthread-cli` | radio-networking | excluded-deferred | deferred | build-feasibility:planned | radio |
| `zephyr.sensor-direct` | sensor | ncs-direct-example | build-only | ncs-direct-build:planned | standard |
| `zephyr.settings-storage` | settings-storage | arduino-wrapper | supported | hil:pass | standard |

Thread/Matter/802.15.4는 v0.2.0에서 build feasibility만 추적하며 정식 지원이 아닙니다.
Sensor 항목은 direct/build example 또는 외부 library compile만 추적하며 bundled wrapper를 제공하지 않습니다.
