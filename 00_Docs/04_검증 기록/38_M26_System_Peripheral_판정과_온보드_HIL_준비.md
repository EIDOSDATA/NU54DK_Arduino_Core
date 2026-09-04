# M26 System Peripheral 판정과 온보드 HIL 준비 기록

| 항목 | 내용 |
| --- | --- |
| 문서 ID | VERIFY-M26-SYSTEM-001 |
| 기록일 | 2026-09-04 |
| 제품선 | `v0.4.0` M26 |
| System Fabric commit | `5cc0343` |
| 온보드 gate commit | `0bbbfe0` |
| Board gitlink | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |
| 판정 | **16개 기능 경계 확정·unknown 0 / TEMP·WDT30 physical HOLD** |
| 작성자 | Quantum / NUCODE |

## 1. 판정

M26가 소유한 16개 system·security·저수준 기능을 `supported`, `partial`, `silicon-only`,
`not-applicable` 중 하나로 전수 판정했다. Machine-readable 계약과 생성 문서 사이의 drift,
회로도 checksum, peripheral manifest 정합성과 raw RADIO/BLE 배타 정책을 CI에 연결했다.

TEMP와 WDT30/31에는 Kconfig 기본 off의 내부 `SystemFabric` 후보를 구현했다. WDT31과 power는
기존 `BoardSystem` 물리 evidence가 있어 지원 상태를 유지한다. Raw RADIO, CRACEN/RNG, clock은
관리 subsystem 또는 기존 제품 범위 안의 부분 지원이며, 직접 Arduino register API를 공개하지
않는다. NFCT·COMP/LPCOMP·KMU·TAMPC·VPR·sQSPI는 board/product 경계가 없는 상태를 지원으로
과장하지 않는다.

## 2. 기능 판정 요약

| 판정 | 기능 |
| --- | --- |
| supported | WDT31, power |
| partial | TEMP, WDT30, RADIO, CRACEN, RNG, clock |
| silicon-only | COMP, LPCOMP, NFCT, KMU, TAMPC, VPR, sQSPI |
| not-applicable | sketch용 manual cache API |

세부 board route, 공존 계약과 evidence는
[M26 System Peripheral 지원 경계](<../01_아두이노 코어 설계/11_M26_System_Peripheral_지원_경계.md>)가
소유한다. 이 표의 `partial`과 `silicon-only`는 공개 지원 선언이 아니다.

## 3. 자동 gate 결과

| Gate | 결과 |
| --- | --- |
| M26 strict ledger·generated doc | `M26_SYSTEM_CONTRACT_PASS=capabilities:16;unknown:0` |
| `nucode.m26.system` target build | 1/1 PASS, warning 0 |
| `nucode.m26.onboard_hil` target build | 1/1 PASS, warning 0 |
| Host regression | `M12_GATE_PASS=host` |
| 회로도 checksum | SHA-256 `7e959be6d8db5d31c55366bd118093727062588770772b226117dd3826798466` 일치 |

온보드 HIL image는 외부 배선 없이 die TEMP 범위, WDT30 configure/start/feed와 실제 watchdog reset,
reset cause 및 retained TEMP를 DAP VCOM의 고정 32-byte protocol로 검증한다. Runner는 exact clean
commit과 board revision, HEX·source digest를 evidence JSON에 묶고 mass erase/recover를 금지한다.

## 4. 물리 실행 결과와 HOLD

| 항목 | 결과 |
| --- | --- |
| Exact source/image | commit `0bbbfe0` build PASS |
| Probe·VCOM 열거 | 1개 probe, COM5/COM6 확인 |
| Flash | **FAIL — SWD/JTAG No ACK** |
| TEMP 실측 | NOT RUN |
| WDT30 reset·reset-cause | NOT RUN |

M26의 전수 판정 완료 조건은 충족했다. 다만 TEMP·WDT30 후보 API는 실제 runner PASS 전까지
`partial/internal`을 유지한다. NFCT는 온보드 antenna/matching network가 없고 sQSPI는 온보드
외부 memory가 없으므로, 해당 기능은 별도 fixture 또는 후속 profile 범위다.
