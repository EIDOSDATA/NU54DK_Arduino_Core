# M26 System Peripheral 지원 경계

> 이 파일은 `variants/nu54dk/system-capability-contract.json`에서 자동 생성합니다. 직접 수정하지 마세요.

| 항목 | 값 |
| --- | --- |
| 제품선 / 마일스톤 | `v0.4.0` / `M26` |
| Board | `nrf54l15dk/nrf54l15/cpuapp/nu54dk` |
| 전체 판정 | 16개, unknown 0개 |
| 상태 합계 | `not-applicable` 1, `partial` 6, `silicon-only` 7, `supported` 2 |
| raw RADIO 정책 | `exclusive-with-managed-ble-and-not-public-in-v0.4.0` |

## 상태 의미

- `supported`: 공개 surface와 자동·물리 PASS가 모두 있다.
- `partial`: Core/upstream 통합 경로가 있지만 API 또는 물리 검증 범위가 완전하지 않다.
- `silicon-only`: silicon에는 있으나 v0.4.0 Arduino 제품 surface로 노출하지 않는다.
- `board-unroutable`: silicon 기능을 현재 NU54DK 회로에서 사용할 수 없다.
- `not-applicable`: 사용자 기능이 아니라 Core/driver 내부 책임으로 유지한다.

## 판정표

| Identity | 판정 | surface | 자동 gate | 물리 gate | 보드 경계 | 공존·소유권 |
| --- | --- | --- | --- | --- | --- | --- |
| `comp` | `silicon-only` | `none` | `pass` | `not_run` | AIN0~AIN7은 P1 header에 있으나 comparator API와 threshold fixture는 v0.4.0 공개 범위가 아니다. | LPCOMP와 comparator106 block을 상호배타적으로 사용해야 한다. |
| `lpcomp` | `silicon-only` | `none` | `pass` | `not_run` | AIN0~AIN7은 P1 header에 있으나 저전력 comparator fixture와 Arduino API는 후속 제품선 범위다. | COMP와 comparator106 block을 상호배타적으로 사용해야 한다. |
| `temp` | `partial` | `internal` | `pass` | `not_run` | 온칩 TEMP라 외부 배선이 필요 없고 centi-Celsius 후보 API와 target contract를 제공한다. | Zephyr sensor driver가 단일 TEMP block을 직렬화한다. |
| `wdt30` | `partial` | `internal` | `pass` | `not_run` | secure-domain WDT30 후보 handle을 빌드하지만 reset-cause HIL 전에는 공개하지 않는다. | 한 WDT block의 timeout channel은 해당 Zephyr watchdog device가 소유한다. |
| `wdt31` | `supported` | `public` | `pass` | `pass` | BoardSystem.watchdog가 application-domain WDT31을 사용한다. | SystemFabric 후보와 BoardSystem production path는 같은 image에서 함께 활성화하지 않는다. |
| `nfct` | `silicon-only` | `none` | `pass` | `not_run` | NFC1/NFC2는 P1.2/P1.3 header와 Wire에 공유되며 보드에 NFC antenna matching network가 없다. | NFCT를 선택하면 Wire/TWIM22와 해당 두 pad를 동시에 사용할 수 없다. |
| `radio` | `partial` | `public` | `pass` | `pass` | 온보드 2.4 GHz RF 경로는 NUCODE_BLE의 검증된 BLE 범위에서 사용한다. | raw RADIO는 managed BLE controller와 배타적이며 v0.4.0 public surface가 아니다. |
| `cracen` | `partial` | `internal` | `partial` | `not_applicable` | 온칩 security accelerator이며 NCS PSA/RNG direct build 경로만 검증됐다. | PSA Crypto와 NCS security subsystem이 자원과 key lifecycle을 소유한다. |
| `kmu` | `silicon-only` | `none` | `pass` | `not_applicable` | 온칩 key management block이며 secure provisioning 정책 없이 Arduino API로 노출하지 않는다. | PSA key lifecycle과 secure-domain 정책만 소유할 수 있다. |
| `rng` | `partial` | `internal` | `partial` | `not_applicable` | NCS PSA RNG direct sample은 build되지만 stable Arduino CSPRNG API는 후속 security 제품선 범위다. | CRACEN/PSA entropy provider를 우회하는 raw register 접근은 허용하지 않는다. |
| `tampc` | `silicon-only` | `none` | `pass` | `not_applicable` | 온칩 tamper controller이며 보드 센서와 제품 tamper policy가 없다. | secure-domain policy 없이 application에 직접 소유권을 넘기지 않는다. |
| `power` | `supported` | `public` | `pass` | `pass` | BoardSystem.systemOff와 온보드 wake source가 검증됐다. | Zephyr PM과 BoardSystem이 system power transition을 직렬화한다. |
| `clock` | `partial` | `internal` | `pass` | `partial` | 32.768 kHz 외부 crystal과 system clock은 board DTS/Zephyr가 관리하며 raw Arduino clock API는 없다. | clock-control과 Bluetooth/system consumer의 reference lifecycle을 우회하지 않는다. |
| `cache` | `not-applicable` | `internal` | `pass` | `not_applicable` | cache coherency는 Core/driver의 DMA 계약 책임이며 sketch용 manual cache API를 제품 기능으로 두지 않는다. | DMA adapter가 필요한 clean/invalidate와 barrier를 내부에서 수행한다. |
| `vpr` | `silicon-only` | `none` | `pass` | `not_applicable` | FLPR/VPR은 별도 firmware image와 IPC 계약이 필요해 단일 Arduino cpuapp Core 범위가 아니다. | cpuapp가 VPR firmware lifecycle과 shared memory를 명시적으로 소유하는 profile에서만 사용한다. |
| `sqspi` | `silicon-only` | `none` | `pass` | `not_run` | sQSPI soft peripheral은 VPR firmware와 외부 memory fixture가 필요하며 온보드 전용 memory가 없다. | VPR image, assigned pins와 DMA buffer 계약이 모두 있는 별도 profile에서만 사용할 수 있다. |

## M27 전 남은 물리 gate

TEMP와 WDT30 후보 API의 온보드 실행, comparator threshold, NFC antenna/reader, sQSPI 외부 memory, raw RF 계측은 build나 문서 판정으로 대체하지 않는다. M27은 이 항목을 `NOT RUN`으로 보존하고 stable 공개를 HOLD한다.

## 단일 원본과 검사

- Contract: [`variants/nu54dk/system-capability-contract.json`](../../variants/nu54dk/system-capability-contract.json)
- Verifier: [`tools/peripheral/verify_m26_system_contract.py`](../../tools/peripheral/verify_m26_system_contract.py)
- Peripheral manifest: [`variants/nu54dk/peripheral-manifest.json`](../../variants/nu54dk/peripheral-manifest.json)
