# M31-W04 연결 AoA 수신의 Host·controller 경계

> **후속 지원 판정:** 아래 결과는 당시 LL 진단이다. 후속 내부 IQ 진단은 [244번](244_M31_P2_DF_연결_IQ_진단.md),
> 제품 SDC IQ RX의 `UNSUPPORTED`·P2 비차단 경계는 [259번](259_M31_P2_DF_고정_SDK_지원_경계.md)을 따른다.

고정 NCS v3.4.0의 Zephyr LL로 [저장소 소유 진단 앱](../../tests/zephyr/m31_df_connected_receiver/README.md)을
`8bcb3e049f2e5ff5cf8a9d08fba8dfd0842e06fb`에서 clean build했다.
NU54DK 두 대의 CMSIS-DAP V2 SHA-256 역할 매핑과 DP/AP register identity를 확인하고
sector flash·hardware reset만 실행했다. 수신 앱은 FLASH 125920 B, RAM 29712 B였으며
HEX SHA-256은 `f0c106266c8abdffe6243819073da4d3c19bbc5766b25fab95d310cda963639a`이다.
상대는 이미 [연결 CTE 응답 실기](174_M31_W04_연결_CTE_응답_실기.md)에 사용한 공개
Arduino `ConnectedCteResponder` image를 그대로 사용했다. [실행 원본](evidence/m31-w04-df-connected-rx-8bcb3e04/connected-aoa-host-controller-diagnostic.json)과
[image·해시 manifest](evidence/m31-w04-df-connected-rx-8bcb3e04/diagnostic-manifest.json)를 보존했다.

| 단계 | 실기 결과 | 해석 |
| --- | --- | --- |
| HCI 안테나 정보 | `num_ant=1`, 최대 pattern 12, 최대 CTE 길이 20 | 이 보드 구성은 기본 안테나 1개 |
| BLE 연결·응답 준비 | 연결 성공, 상대 Arduino의 CTE 응답 활성 메시지 확인 | peer와 TX 설정까지만 확인 |
| Zephyr Host AoA RX API | `bt_df_conn_cte_rx_enable()` → `-22` (`EINVAL`) | 고정 Host의 `valid_cte_rx_common_params()`가 안테나 2개 이상과 RX antenna switching feature를 요구 |
| 직접 HCI 수신 파라미터·요청 | `LE Set Connection CTE Receive Parameters` → 0, `LE Connection CTE Request Enable` → 0 | 같은 연결에서 controller가 **명령을 수락**했을 뿐, CTE 응답 도착이나 IQ report 수신은 확인하지 못함 |
| Host IQ callback | 보고 없음 | 원시 HCI 경로는 Host의 `BT_CONN_CTE_RX_ENABLED`·CTE type 상태를 설정하지 않으며, 그 Host 내부 상태가 없는 report는 callback 전에 거부됨 |

고정 SDK의 `zephyr/subsys/bluetooth/host/direction.c`에서 AoA RX 공통 검증은
`df_ant_info.num_ant < DF_SAMPLING_ANTENNA_NUMBER_MIN`과
`BT_FEAT_LE_ANT_SWITCH_RX_AOA`를 검사한다. 연결 IQ report 준비 경로도
`BT_CONN_CTE_RX_ENABLED`와 `conn->cte_types`를 검사한다. 따라서 직접 HCI 성공을
공개 API 지원이나 raw IQ HIL PASS로 대체할 수 없다. SDK 원본은 수정하지 않았다.

이 실기는 앞선 connectionless sync 실패와 별개인 **연결 기반** 진단으로,
기본 1안테나 NU54DK에서 Host API가 막는 위치를 분리했다. 외장 안테나 전환
구성·각도 계산의 사용자 후속 실기와 구분한다. W04의 `raw_iq_rx` 및
`M31-DF-01:raw_iq_rx_candidate`는 IQ report 0건이므로 **FAIL/미완료**를 유지한다.
