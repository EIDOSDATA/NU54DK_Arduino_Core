# 연결 기반 CTE 수신 진단

이 앱은 M31-W04의 **내부 Zephyr 진단용**이다. 공개 Arduino 예제가 아니다.
`ConnectedCteResponder` 예제가 올라간 두 번째 NU54DK에 연결한 뒤,
고정 NCS v3.4.0 Zephyr Host의 `bt_df_conn_cte_rx_enable()` 결과를 기록한다.
Host가 거부하면 같은 연결에서 controller HCI의 수신 파라미터와 CTE 요청
명령 수락 여부를 따로 기록한다. 원시 HCI 명령이 성공해도 Host의 연결 상태
검사를 우회하므로 IQ callback이나 AoA 수신 성공으로 해석하지 않는다.

`bt-ll-sw-split` snippet, `nrf54l15dk/nrf54l15/cpuapp/nu54dk` target,
저장소의 `board_package/NU54DK_Zephyr_DTS` board root로 빌드한다.
`tests/hil/nu54dk/m31_df_connected_rx_run.py`는 probe SHA-256 역할 매핑,
sector flash, hardware reset, UART 결과를 JSON으로 기록한다. 원본 probe
UID와 Bluetooth 주소는 기록하지 않는다.

출력 태그 `AOA_RX_ENABLE`, `RAW_RX_PARAM`, `RAW_REQUEST`, `IQ`를 별도로
해석한다. `CONTROLLER_ACCEPTED_HOST_REJECTED`는 HCI 명령 두 개의 수락과
Host API 거부만 뜻하며, 실제 IQ 보고서 미확인을 그대로 유지한다.
