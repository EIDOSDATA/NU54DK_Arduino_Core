# NU54DK Arduino Core v0.4.0-rc.1 — 준비 상태

| 항목 | 내용 |
| --- | --- |
| 제품선 | Peripheral Parity |
| 현재 상태 | **내부 준비 중 / 공개 HOLD** |
| 공개 tag | 없음 |
| GitHub Release | 없음 |
| Boards Manager 공개 index | 없음 |
| 현재 사용자용 stable | `v0.3.0` |

이 디렉터리는 `v0.4.0-rc.1`의 공개 릴리스 문서가 아니라 M27 준비 경계를 명확히 하기 위한
초안이다. Source/build가 끝난 후보 기능도 실제 HIL과 release gate 전에는 공개 지원이 아니다.

후속 작업의 순서·현재 재개 위치는 [v0.4.0 실행 TODO](../../TODO_v0.4.0.md)를 따른다.
T01~T15는 시험 준비·기능 검증, T16~T21은 사용자용 통합·RC/stable 비공개 검증,
T22~T25는 최종 승인·공개·공개 URL 검사·마무리다.

## 준비된 범위

- M23: 75개 peripheral identity와 공통 block/channel/DMA ownership 계약
- M24: UARTE·SPIM/SPIS·TWIM/TWIS 전 instance 후보와 온보드 runner
- M25: SAADC·PWM·timer/event·PDM·I2S·QDEC 후보와 온보드 runner
- M26: 16개 system 기능의 지원 경계, TEMP·WDT30/31 후보와 온보드 runner
- M27: package·checksum·SBOM·license·RC index 이중 재현과 격리 staging 예제 29/29 compile PASS,
  fail-closed HOLD plan

Exact source·artifact·runner와 남은 재개 조건은
[M27 자동 준비·HOLD 기록](<../../04_검증 기록/39_M27_v0.4.0_rc1_자동_준비와_HOLD.md>)을 따른다.
Staging compile은 공개 URL 설치·실제 upload·제거·재설치·version 전환을 대신하지 않는다.
이는 당시 후보의 결과이며 최종 frozen RC에서 다시 검증해야 한다.

`51c1986`의 UART 4개·TWIM 3개·내부 VDD/event·TEMP/WDT30 기본 HIL은
[온보드 교정·실기 재검증](<../../04_검증 기록/41_M24_M26_온보드_protocol_교정과_실기_재검증.md>)에서
PASS했다. `2542a01`의 [UART Fixture 101](<../../04_검증 기록/44_M24_Fixture_101_UART_실기_검증.md>)과
`ff3423e`의 [Fixture 102](<../../04_검증 기록/45_M24_Fixture_102_UART_실기_검증.md>),
`b3c689b`의 [Fixture 103](<../../04_검증 기록/46_M24_Fixture_103_UART_실기_검증.md>)은
P2/P0/P1↔P1 UARTE 양방향 data·DMA·RTS/CTS를 통과했다. 남은 SPI/TWI·analog/stream fixture와
아래 범위 합의는 최종 공개 승인이 아니다.

## 기능 검증과 사용자 통합 검증의 경계

[프로젝트 소유자와의 범위 합의](<../../04_검증 기록/42_v0.4.0_코어_기능_검증_범위_합의.md>)에 따라
온보드 자원과 두 NU54DK의 안전한 peer/loopback·합성 신호·capture로 코어 기능을 검증한다.
별도 계측기·교정 신호원·실제 마이크/코덱/엔코더를 필수 준비물로 요구하지 않는다.
정밀 정확도·jitter·전력·신호 품질 및 부품별 호환성은 보증하지 않으며 제품 통합 단계에서 확인한다.
코어의 실제 데이터 경로·DMA·오류 복구·동시성·장시간 안정성은 계속 필수이며 미실행은 HOLD다.

## 공개 전 필수 항목

1. M24의 SPI/TWI peer·허용 최대 동시성·복구·처리량·soak
2. M25 analog/PWM/PDM/I2S/QDEC 합성 신호·capture, 기본 timing·DMA·overrun·복구·동시성·soak
3. M26 TEMP·WDT30 reset 온보드 PASS 증거 유지와 관련 변경 시 회귀 검증
4. Frozen RC commit의 host/docs/전체 Zephyr build와 이중 package 재현성
5. 격리 Boards Manager 설치·전체 예제 compile·실제 upload·제거·version 전환
6. 프로젝트 소유자의 명시적 공개 승인

모든 gate가 PASS하기 전에는 tag·Release asset·stable index를 만들지 않는다. 이전 공개 버전과
RC의 tag·asset·문서는 삭제하거나 덮어쓰지 않는다.
