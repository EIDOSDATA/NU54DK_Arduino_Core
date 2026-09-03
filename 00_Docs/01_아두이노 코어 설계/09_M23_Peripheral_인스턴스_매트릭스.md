# M23 — nRF54L15/NU54DK Peripheral 인스턴스 매트릭스

> 이 파일은 `variants/nu54dk/peripheral-manifest.json`에서 자동 생성합니다. 직접 수정하지 마세요.
> 표의 `candidate`, `absent`, `not-run`은 현재 지원 선언이 아닙니다.

| 항목 | 값 |
| --- | --- |
| SoC | `nRF54L15` |
| NCS / Zephyr | `v3.4.0` / `4.4.0` |
| Board | `nrf54l15dk/nrf54l15/cpuapp/nu54dk` |
| Manifest schema | `1` |
| 추적 identity | **75개** |
| 현재 public surface가 있는 identity | **17개** |
| 현재 HIL PASS identity | **10개** |
| 후속 구현 배정 | M24 23 / M25 36 / M26 16 |

## 판정 읽는 법

- `source`는 NU54DK Core 자체 구현 수준이며 upstream driver 존재 여부와 다릅니다.
- `public`은 Arduino 사용자가 선택할 surface가 있다는 뜻이지 전 기능 완료를 뜻하지 않습니다.
- `build`, `semantic`, `HIL`, `concurrent`는 서로 독립이며 앞 단계 PASS가 뒤 단계 PASS를 대신하지 않습니다.
- 같은 `block` 값의 personality는 같은 register/IRQ 자원을 공유하므로 동시에 사용할 수 없습니다.
- 서로 다른 block도 pin, DPPI, timer channel과 DMA RAM lease가 모두 성공해야 동시 실행할 수 있습니다.

## M24 배정 identity

| Identity | block / DTS | board route | source / public | DMA | build | semantic | HIL | concurrent |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `uarte00` | `serial00` / `uart00` | candidate: `header-p2` | absent / none: — | EasyDMA/16 bit; driver; none | not-run | not-run | not-run | not-run |
| `uarte20` | `serial20` / `uart20` | verified: `console-p1.4-p1.7` | implemented / public: `Serial`, `HardwareSerial` | EasyDMA/16 bit; driver; none | pass | pass | pass | not-run |
| `uarte21` | `serial21` / `uart21` | candidate: `header-p1` | absent / none: — | EasyDMA/16 bit; driver; none | not-run | not-run | not-run | not-run |
| `uarte22` | `serial22` / `uart22` | candidate: `header-p1` | absent / none: — | EasyDMA/16 bit; driver; none | not-run | not-run | not-run | not-run |
| `uarte30` | `serial30` / `uart30` | verified: `dap-vcom-p0.0-p0.3` | implemented / public: `Serial1`, `Nu54HardwareSerial` | EasyDMA/16 bit; driver; none | pass | pass | pass | partial |
| `spim00` | `serial00` / `spi00` | verified: `header-p2.1-p2.4` | implemented / public: `SPI`, `SPIClass` | EasyDMA/16 bit; driver; synchronous | pass | pass | pass | partial |
| `spim20` | `serial20` / `spi20` | candidate: `header-p1-console-conflict` | absent / none: — | EasyDMA/16 bit; driver; none | not-run | not-run | not-run | not-run |
| `spim21` | `serial21` / `spi21` | candidate: `header-p1` | absent / none: — | EasyDMA/16 bit; driver; none | not-run | not-run | not-run | not-run |
| `spim22` | `serial22` / `spi22` | candidate: `header-p1-wire-conflict` | absent / none: — | EasyDMA/16 bit; driver; none | not-run | not-run | not-run | not-run |
| `spim30` | `serial30` / `spi30` | candidate: `header-p0-dap-conflict` | absent / none: — | EasyDMA/16 bit; driver; none | not-run | not-run | not-run | not-run |
| `spis00` | `serial00` / `spi00` | candidate: `header-p2` | absent / none: — | EasyDMA/16 bit; direct 예정; none | not-run | not-run | not-run | not-run |
| `spis20` | `serial20` / `spi20` | candidate: `header-p1-console-conflict` | absent / none: — | EasyDMA/16 bit; direct 예정; none | not-run | not-run | not-run | not-run |
| `spis21` | `serial21` / `spi21` | candidate: `header-p1` | absent / none: — | EasyDMA/16 bit; direct 예정; none | not-run | not-run | not-run | not-run |
| `spis22` | `serial22` / `spi22` | candidate: `header-p1-wire-conflict` | absent / none: — | EasyDMA/16 bit; direct 예정; none | not-run | not-run | not-run | not-run |
| `spis30` | `serial30` / `spi30` | candidate: `header-p0-dap-conflict` | absent / none: — | EasyDMA/16 bit; direct 예정; none | not-run | not-run | not-run | not-run |
| `twim20` | `serial20` / `i2c20` | candidate: `header-p1-console-conflict` | absent / none: — | EasyDMA/16 bit; driver; none | not-run | not-run | not-run | not-run |
| `twim21` | `serial21` / `i2c21` | candidate: `header-p1` | absent / none: — | EasyDMA/16 bit; driver; none | not-run | not-run | not-run | not-run |
| `twim22` | `serial22` / `i2c22` | verified: `header-p1.2-p1.3` | implemented / public: `Wire`, `TwoWire` | EasyDMA/16 bit; driver; synchronous | pass | pass | pass | partial |
| `twim30` | `serial30` / `i2c30` | candidate: `header-p0-dap-conflict` | absent / none: — | EasyDMA/16 bit; driver; none | not-run | not-run | not-run | not-run |
| `twis20` | `serial20` / `i2c20` | candidate: `header-p1-console-conflict` | absent / none: — | EasyDMA/16 bit; direct 예정; none | not-run | not-run | not-run | not-run |
| `twis21` | `serial21` / `i2c21` | candidate: `header-p1` | absent / none: — | EasyDMA/16 bit; direct 예정; none | not-run | not-run | not-run | not-run |
| `twis22` | `serial22` / `i2c22` | candidate: `header-p1-wire-route` | absent / none: — | EasyDMA/16 bit; direct 예정; none | not-run | not-run | not-run | not-run |
| `twis30` | `serial30` / `i2c30` | candidate: `header-p0-dap-conflict` | absent / none: — | EasyDMA/16 bit; direct 예정; none | not-run | not-run | not-run | not-run |

## M25 배정 identity

| Identity | block / DTS | board route | source / public | DMA | build | semantic | HIL | concurrent |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `gpio0` | `—` / `gpio0` | verified: `header-p0-conditional-dap` | implemented / public: `pinMode`, `digitalRead`, `digitalWrite` | 없음 | pass | pass | partial | partial |
| `gpio1` | `—` / `gpio1` | verified: `header-p1-mixed-policy` | implemented / public: `pinMode`, `digitalRead`, `digitalWrite` | 없음 | pass | pass | partial | partial |
| `gpio2` | `—` / `gpio2` | verified: `header-p2-mixed-policy` | implemented / public: `pinMode`, `digitalRead`, `digitalWrite` | 없음 | pass | pass | partial | partial |
| `gpiote20` | `—` / `gpiote20` | verified: `gpio1-events` | internal / public: `attachInterrupt` | 없음 | pass | pass | partial | not-run |
| `gpiote30` | `—` / `gpiote30` | verified: `gpio0-events` | internal / public: `attachInterrupt` | 없음 | pass | pass | partial | not-run |
| `egu10` | `—` / `egu10` | not-required: `internal-event` | absent / none: — | 없음 | not-run | not-run | not-run | not-run |
| `egu20` | `—` / `egu20` | not-required: `internal-event` | absent / none: — | 없음 | not-run | not-run | not-run | not-run |
| `dppic00` | `—` / `dppic00` | not-required: `domain-00` | absent / none: — | 없음 | not-run | not-run | not-run | not-run |
| `dppic10` | `—` / `dppic10` | not-required: `domain-10` | absent / none: — | 없음 | not-run | not-run | not-run | not-run |
| `dppic20` | `—` / `dppic20` | not-required: `domain-20` | absent / none: — | 없음 | not-run | not-run | not-run | not-run |
| `dppic30` | `—` / `dppic30` | not-required: `domain-30` | absent / none: — | 없음 | not-run | not-run | not-run | not-run |
| `ppib00` | `—` / `ppib00` | not-required: `domain-00-bridge` | absent / none: — | 없음 | not-run | not-run | not-run | not-run |
| `ppib01` | `—` / `ppib01` | not-required: `domain-00-bridge` | absent / none: — | 없음 | not-run | not-run | not-run | not-run |
| `ppib10` | `—` / `ppib10` | not-required: `domain-10-bridge` | absent / none: — | 없음 | not-run | not-run | not-run | not-run |
| `ppib11` | `—` / `ppib11` | not-required: `domain-10-bridge` | absent / none: — | 없음 | not-run | not-run | not-run | not-run |
| `ppib20` | `—` / `ppib20` | not-required: `domain-20-bridge` | absent / none: — | 없음 | not-run | not-run | not-run | not-run |
| `ppib21` | `—` / `ppib21` | not-required: `domain-20-bridge` | absent / none: — | 없음 | not-run | not-run | not-run | not-run |
| `ppib22` | `—` / `ppib22` | not-required: `domain-20-bridge` | absent / none: — | 없음 | not-run | not-run | not-run | not-run |
| `ppib30` | `—` / `ppib30` | not-required: `domain-30-bridge` | absent / none: — | 없음 | not-run | not-run | not-run | not-run |
| `timer00` | `—` / `timer00` | not-required: `domain-00` | absent / none: — | 없음 | not-run | not-run | not-run | not-run |
| `timer10` | `—` / `timer10` | not-required: `domain-10` | absent / none: — | 없음 | not-run | not-run | not-run | not-run |
| `timer20` | `—` / `timer20` | not-required: `domain-20` | absent / none: — | 없음 | not-run | not-run | not-run | not-run |
| `timer21` | `—` / `timer21` | not-required: `domain-20` | absent / none: — | 없음 | not-run | not-run | not-run | not-run |
| `timer22` | `—` / `timer22` | not-required: `domain-20` | absent / none: — | 없음 | not-run | not-run | not-run | not-run |
| `timer23` | `—` / `timer23` | not-required: `domain-20` | absent / none: — | 없음 | not-run | not-run | not-run | not-run |
| `timer24` | `—` / `timer24` | not-required: `domain-20` | absent / none: — | 없음 | not-run | not-run | not-run | not-run |
| `grtc` | `—` / `grtc` | not-required: `system-counter` | partial / public: `millis`, `micros`, `BoardSystem.counter`, `BoardSystem.alarm` | 없음 | pass | pass | pass | not-run |
| `saadc` | `—` / `adc` | partial: `ain0-ain7-policy-limited` | partial / public: `analogRead` | EasyDMA/16 bit; driver; synchronous | pass | pass | pass | partial |
| `pwm20` | `—` / `pwm20` | verified: `header-p1-runtime` | partial / public: `analogWrite` | EasyDMA/15 bit; driver; synchronous | pass | pass | pass | partial |
| `pwm21` | `—` / `pwm21` | verified: `header-p1-runtime` | partial / public: `tone`, `noTone` | EasyDMA/15 bit; driver; synchronous | pass | pass | not-run | not-run |
| `pwm22` | `—` / `pwm22` | verified: `header-p1-runtime` | partial / public: `Servo` | EasyDMA/15 bit; driver; synchronous | pass | pass | not-run | not-run |
| `pdm20` | `—` / `pdm20` | candidate: `header-p1` | absent / none: — | EasyDMA/16 bit; direct 예정; none | not-run | not-run | not-run | not-run |
| `pdm21` | `—` / `pdm21` | candidate: `header-p1` | absent / none: — | EasyDMA/16 bit; direct 예정; none | not-run | not-run | not-run | not-run |
| `i2s20` | `—` / `i2s20` | candidate: `header-p1` | absent / none: — | EasyDMA/16 bit; driver; none | not-run | not-run | not-run | not-run |
| `qdec20` | `—` / `qdec20` | candidate: `header-p1` | absent / none: — | 없음 | not-run | not-run | not-run | not-run |
| `qdec21` | `—` / `qdec21` | candidate: `header-p1` | absent / none: — | 없음 | not-run | not-run | not-run | not-run |

## M26 배정 identity

| Identity | block / DTS | board route | source / public | DMA | build | semantic | HIL | concurrent |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `comp` | `comparator106` / `comp` | candidate: `analog-input-policy` | absent / none: — | 없음 | not-run | not-run | not-run | not-run |
| `lpcomp` | `comparator106` / `comp` | candidate: `analog-input-policy` | absent / none: — | 없음 | not-run | not-run | not-run | not-run |
| `temp` | `—` / `temp` | not-required: `on-chip` | absent / none: — | 없음 | not-run | not-run | not-run | not-run |
| `wdt30` | `—` / `wdt30` | not-required: `secure-domain` | absent / none: — | 없음 | not-run | not-run | not-run | not-run |
| `wdt31` | `—` / `wdt31` | not-required: `application-domain` | partial / public: `BoardSystem.watchdog` | 없음 | pass | pass | pass | not-run |
| `nfct` | `—` / `nfct` | candidate: `p1.2-p1.3-wire-conflict` | absent / none: — | EasyDMA/9 bit; direct 예정; none | not-run | not-run | not-run | not-run |
| `radio` | `—` / `radio` | not-required: `on-chip-antenna-network` | partial / public: `NUCODE_BLE` | EasyDMA; driver; none | pass | pass | pass | not-run |
| `cracen` | `security` / `—` | not-required: `secure-system` | internal / internal: — | EasyDMA; driver; none | partial | not-run | not-run | not-run |
| `kmu` | `security` / `—` | not-required: `secure-system` | absent / none: — | 없음 | not-run | not-run | not-run | not-run |
| `rng` | `security` / `—` | not-required: `secure-system` | internal / internal: — | 없음 | partial | not-run | not-run | not-run |
| `tampc` | `security` / `—` | not-required: `secure-system` | absent / none: — | 없음 | not-run | not-run | not-run | not-run |
| `power` | `system` / `power` | not-required: `soc-system` | internal / public: `BoardSystem.systemOff` | 없음 | pass | pass | pass | not-run |
| `clock` | `system` / `clock` | not-required: `soc-system` | internal / internal: — | 없음 | pass | partial | partial | not-run |
| `cache` | `system` / `—` | not-required: `cpuapp-system` | internal / internal: — | 없음 | pass | not-run | not-run | not-run |
| `vpr` | `—` / `cpuflpr_vpr` | not-required: `cpuflpr` | absent / none: — | 없음 | not-run | not-run | not-run | not-run |
| `sqspi` | `—` / `—` | candidate: `vpr-softperipheral-board-audit` | absent / none: — | EasyDMA; direct 예정; none | not-run | not-run | not-run | not-run |

## 단일 원본과 검사

- Manifest: [`variants/nu54dk/peripheral-manifest.json`](../../variants/nu54dk/peripheral-manifest.json)
- Schema: [`tools/peripheral/peripheral-manifest.schema.json`](../../tools/peripheral/peripheral-manifest.schema.json)
- 검증·생성기: [`tools/peripheral/verify_m23_inventory.py`](../../tools/peripheral/verify_m23_inventory.py)
- Runtime table: [`cores/arduino/generated/PeripheralInventory.inc`](../../cores/arduino/generated/PeripheralInventory.inc)
- M24 serial-fabric route/API 계약: [`10_M24_Serial_Fabric_경로와_API_계약.md`](10_M24_Serial_Fabric_경로와_API_계약.md)

검증기는 identity 누락, public object 중복 alias, 공유 block 오류, evidence 파일 누락과 생성물 drift를 거부한다.
`--ncs-root`를 주면 exact NCS DTS checksum과 node label까지 대조한다.
