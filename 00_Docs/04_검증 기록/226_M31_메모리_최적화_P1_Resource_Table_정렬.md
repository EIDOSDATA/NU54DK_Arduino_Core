# 226 — M31 메모리 최적화 P1 Resource Table 정렬

## 1. 판정

2026-09-22 중앙 `IoResourceTable`의 48-slot 용량과 범용 lease 16-entry 계약을 유지하면서,
`ResourceSlot`과 `IoResourceLeaseEntry`의 필드 순서를 target ABI에 맞게 재배치했다. 64-bit
generation 두 개 뒤에 owner/state flag를 모아 alignment padding을 제거했다.

adaptive에서 slot 수를 임의로 16으로 줄이지 않았다. GPIO 사용자는 동시에 여러 pad를 소유할 수
있고 Peripheral Fabric은 별도 profile에서 최대 128-slot을 요구하므로 capacity는 기능/제품 선언
근거 없이 축소하지 않는다. generation은 계속 64-bit이며 stale lease, rollback, DMA overlap과
동시성 의미는 바뀌지 않는다.

## 2. 정적 RAM 전후 비교

동일 `p0_serial_spi` adaptive clean image에서 직전 route 기준과 비교했다.

| 항목 | Route 변경 뒤 | 정렬 변경 뒤 | 절감 |
| --- | ---: | ---: | ---: |
| 전체 정적 RAM | 21,013 B | 20,589 B | 424 B |
| 중앙 `table` | 2,320 B | 1,936 B | 384 B |
| `spi_route` | 624 B | 584 B | 40 B |
| RAM 사용률 | 8.0158% | 7.8541% | 0.1617%p |
| RAM headroom | 241,131 B | 241,555 B | +424 B |
| FLASH | 60,332 B | 59,996 B | -336 B |

P0 50,877 B 대비 P1 누적 정적 RAM 절감은 30,288 B(59.5%)다. 금지 symbol은 0건이고
budget gate는 PASS다. Core SPI clean-example 상한은 22,500 B에서 22,000 B로 낮췄다.

## 3. 검증

| 검증 | 결과 |
| --- | --- |
| R08 resource/route Host 23 scenario | PASS |
| compact token Host | PASS |
| M23 inventory Host | 9 PASS |
| AC-02A ownership target build-only | 1/1 PASS, warning 0 |
| adaptive Serial-only/include-only/SPI clean + cache reuse | PASS |
| 물리 HIL | NOT RUN — 저장 구조 layout과 기존 target semantic 계약 범위 |

## 4. 다음 작업

Core 공통 pin/route/table 고정 저장소 right-size는 완료했다. P1의 다음 축은 BLE 역할별 GATT
event queue/state와 server/client 저장소다. P0 역할 image의 실제 map에서 GATT facade를 사용하는
대표 server/client와 facade를 쓰지 않는 upstream Audio/CS 역할을 다시 분류하고, queue depth와
배열 capacity가 실제 Kconfig/role 선언에 연결되는지를 먼저 확인한다.
