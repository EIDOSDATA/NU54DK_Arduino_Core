# 134 — M28-W02 고정 2-slot·generation link 기반

## 결론

M28-W02를 완료했다. Production BLE profile과 공개 API는 central 1개, peripheral 1개의 역할 고정
2-slot을 사용하며, slot 재사용은 generation을 결합한 불투명 handle로 구분한다. 기존 singleton과
기존 callback은 source 호환으로 남고, 새 상세 event만 link handle과 local 역할을 추가한다.

이 기록의 PASS는 Host 수명 계약과 고정 NCS v3.4.0 target compile/link에 적용한다. 실제 RF 동시
2-link와 장시간 동작은 `M28-LINK-01`·`M28-CTRL-01`·`M28-SOAK-01`에서 아직 `NOT RUN`이다.

## 구현 결과

| 항목 | 결과 |
| --- | --- |
| Controller/Host partition | `CONFIG_BT_MAX_CONN=2`, SDC peripheral 1, central 1 |
| Public identity | `BLEConnectionHandle`, `BLELinkRole`, `BLEEventInfo` |
| Legacy compatibility | 네 singleton·기존 callback 유지, handle 없는 link 제어는 central 우선 |
| Slot lifecycle | disconnect/end 선무효화, slot별 generation·peer·device session |
| Callback isolation | connection pointer와 generation handle 대조, 늦은 MTU/PHY/parameter event 폐기 |
| 고정 자원 | connection slot 2개, MTU exchange context 4개, heap 추가 없음 |
| 예제 | `libraries/NUCODE_BLE/examples/MixedRoleLinks/MixedRoleLinks.ino` |

## 검증 결과

| 검증 | 결과 |
| --- | --- |
| `tests/host/test_m28_ble_links.py` | 5/5 PASS |
| `tests/host/test_r12_ble_gap.py` | production GAP 13개 시나리오 PASS |
| 신규 runtime scenario | `multi_link`, `generation`, `end_two_links` PASS |
| `tests/host/test_build_matrix_runner.py` | 9/9 PASS |
| 고정 NCS target | `nucode.m28.ble_link_contract` 1/1 build-only PASS, warning 0 |
| target 실행 시간 | 62.02초 |

Target build는 NCS `99553055607b2e9885fbc80ccd11fa9da81c2df0`, Zephyr
`bf801e4e3d19e1ffa76164346480cb7734dd2800`, board
`fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3`, toolchain bundle `dcbdc366a1` 조건에서 수행했다.

## 중복 없는 HIL 분리

현재 확인한 두 보드에서는 기존 M19~M21 회귀, extended advertising, PAwR, privacy처럼 두 node로
완결되는 시험만 수행한다. 세 번째 보드가 준비되면 image/UID/UART/역할 preflight만 다시 확인하고
다음 3-node 전용 시험을 수행한다.

- DUT central 1 + peripheral 1 동시 link와 link별 sequence
- periodic sync transfer(PAST)의 advertiser/transfer receiver/sync receiver 분리
- 두 link 제어 격리와 1,800초 soak

따라서 두 보드 feature 시험 전체를 세 보드에서 반복하지 않는다.

## 다음 작업

M28-W03 extended advertising/scanning의 advertising set handle, 255-byte payload, SID·primary/secondary
PHY와 extended scan result lifetime을 같은 Host → target 순서로 구현한다. W03의 2보드 RF 시험은
W07의 `M28-ADV-01`에 합쳐 증거를 한 번만 만든다.
