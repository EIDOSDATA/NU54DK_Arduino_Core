# 224 — M31 메모리 최적화 P1 UART20 lease 절감

## 1. 판정

2026-09-22 부팅 고정 UART20의 등록 transaction에 쓰던 792-byte `IoResourceLease`를 전역
정적 상태에서 제거했다. UART20 pad 네 개와 serial block 하나를 reserve/commit하는 동안만 지역
lease를 유지하고, commit 뒤 owner와 generation은 중앙 `IoResourceTable`이 보존한다.

reserve/commit 실패 때 reserved 또는 committed lease를 되돌리는 기존 fail-closed unwind는
그대로 유지했다. cleanup 실패가 원래 등록 실패보다 우선 반환되는 계약도 바꾸지 않았다.
`CONFIG_ZTEST`의 충돌 후 재초기화와 실제 boot의 한 번 초기화 경계도 유지한다.

## 2. 정적 RAM 전후 비교

동일 `p0_serial_spi` adaptive clean image에서 직전 P1 GPIO 기준과 비교했다.

| 항목 | P1 GPIO 뒤 | UART20 변경 뒤 | 절감 |
| --- | ---: | ---: | ---: |
| 전체 정적 RAM | 25,405 B | 24,613 B | 792 B |
| `uart20_lease` | 792 B | 0 B | 792 B |
| RAM 사용률 | 9.6912% | 9.3891% | 0.3021%p |
| RAM headroom | 236,739 B | 237,531 B | +792 B |

P0의 50,877 B와 비교한 P1 누적 절감은 26,264 B다. 새 image의 금지 symbol은 0건이고
budget gate는 PASS다. Core SPI clean-example 상한은 27,000 B에서 26,000 B로 낮췄다.

## 3. 검증

| 검증 | 결과 |
| --- | --- |
| GPIO/registry Host 계약 | 9 PASS |
| AC-02A ownership target build-only | 1/1 PASS, warning 0 |
| adaptive Serial-only/include-only/SPI clean + cache reuse | PASS |
| `uart20_lease` map 검색 | 0건 |
| 물리 HIL | NOT RUN — 정적 저장소와 기존 target semantic 계약 범위 |

## 4. 다음 작업

SPI adaptive image의 다음 Core 고정 저장소는 `spi_route` 4,224 B와 중앙 resource table
2,320 B다. route는 block lease와 pin handover의 STOP/rollback/faulted 수명을 포함하므로 단순 지역
변수화하지 않는다. 실제 SPI route의 최대 pin 수와 active 상태에 필요한 compact persistent 정보,
전환 중 rollback snapshot의 수명을 먼저 분리한 뒤 AC-02A/R08/R09 회귀와 fresh ELF delta를 확인한다.
