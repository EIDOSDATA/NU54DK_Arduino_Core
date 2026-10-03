# M32-W03 연결 timing·feature exact HIL 완료

## 1. 판정

| 항목 | 결과 |
| --- | --- |
| 작업 | `M32-W03` |
| exact source | `9b3badc4ce252e01d6d8d637e175d3f22bff0bc9` |
| 고정 NCS / Zephyr | `99553055607b…` / `bf801e4e3d19…` |
| 두 역할 target build | **2/2 PASS** |
| Host·negative 계약 | **17 test PASS + M32 contract PASS** |
| exact HIL | **4 family PASS, packet 2,000/2,000, loss 0** |
| W03 상태 | **완료** |
| M32 완료 수 | **3/12** |

## 2. 장비와 flash 안전 경계

`F:`를 central(`COM13`), `G:`를 peripheral(`COM10`)로 SHA-256 probe identity에 고정했다.
두 probe는 CMSIS-DAP v2 interface에서 DP/AP 초기화가 불안정했으므로 CMSIS-DAP v1·100 kHz·
`attach`로 전환했다. `auto_unlock=false`, sector erase, 역할별 HEX, hardware reset만 사용했으며
mass erase·recover·unlock은 실행하지 않았다. `E:` probe는 비파괴 DP/AP 질의가 실패해 이 시험에
사용하지 않았다.

## 3. exact 결과

- central은 229,376 bytes, peripheral은 225,280 bytes를 sector programming했다.
- `M32-SUB-01`: 두 역할 Subrating change 20/20, 손실 0이다.
- `M32-SCA-01`: 두 역할에서 controller procedure 지원 경계를 10/10회 확인했다. 고정 Host에는
  요청·report API가 없으므로 `unsupported_host_initiator_api`로 닫고 지원 catalog에는 올리지 않는다.
- `M32-TIME-01`: packet 2,000/2,000, Frame Space central 20회·peripheral 2회,
  Shorter Interval 20/20, 최소 interval 750 us, 최대 packet gap 9 ms다.
- `M32-FEAT-01`: feature 20/20, central channel classification 20회, callback 문맥 PASS다.
- 최대 procedure gap은 907 ms이며 역할별 STOP 2/2를 확인했다.

원본은 [`m32-timing-feature-01.json`](<evidence/m32-w03-exact-9b3badc4/m32-timing-feature-01.json>),
빌드 요약은 [`native-build-summary.json`](<evidence/m32-w03-exact-9b3badc4/native-build-summary.json>),
마감 감사는 [`w03-closure-audit.json`](<evidence/m32-w03-exact-9b3badc4/w03-closure-audit.json>)에 있다.

## 4. 판정 경계

Connection Subrating, Frame Space, Shorter Connection Interval, Extended Feature Set과 channel/throughput
경로는 `applicable`로 승격한다. Sleep Clock Accuracy Update의 controller 지원 자체와 Host에서 직접
요청·report하는 API는 분리하며, 후자는 `unsupported`다. 외부 제품 peer 상호운용은 사용자 후속
`NOT_RUN`으로 유지하고 W03 개발 완료를 막지 않는다.
