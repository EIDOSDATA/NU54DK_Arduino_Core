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

## 공개 전 필수 항목

1. M24 UARTE/TWIM 온보드 HIL과 serial 외부 fixture·최대 동시성·복구·성능·전력
2. M25 내부 event/VDD 온보드 HIL과 analog/PWM/audio/QDEC fixture·jitter·overrun·soak
3. M26 TEMP·WDT30 reset 온보드 HIL
4. Frozen RC commit의 host/docs/전체 Zephyr build와 이중 package 재현성
5. 격리 Boards Manager 설치·전체 예제 compile·실제 upload·제거·version 전환
6. 프로젝트 소유자의 명시적 공개 승인

모든 gate가 PASS하기 전에는 tag·Release asset·stable index를 만들지 않는다. 이전 공개 버전과
RC의 tag·asset·문서는 삭제하거나 덮어쓰지 않는다.
