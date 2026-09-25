# 연결 기반 CTE 수신 진단

이 앱은 M31-W04의 **내부 Zephyr 진단용**이다. 공개 Arduino 예제가 아니다.
W04는 아직 완료되지 않았으며 이 앱의 build나 HCI 명령 수락만으로 완료 처리하지 않는다.
고정 NCS v3.4.0·nRF54L15 제품 SDC의 IQ RX는 `UNSUPPORTED`·P2 범위 제외다.
이 앱의 결과는 과거 LL 진단으로 보존하며 P2 완료를 위해 자동 재실행하거나 controller를 교체하지 않는다.
공개 [`ConnectedCteResponder.ino`](../../../libraries/NUCODE_BLE_DirectionFinding/examples/ConnectedCteResponder/ConnectedCteResponder.ino)와
그 backend [`NUCODE_BLE_DirectionFinding_Connected.cpp`](../../../libraries/NUCODE_BLE_DirectionFinding/src/NUCODE_BLE_DirectionFinding_Connected.cpp)가
올라간 두 번째 NU54DK에 연결한 뒤,
고정 NCS v3.4.0 Zephyr Host의 `bt_df_conn_cte_rx_enable()` 결과를 기록한다.
Host가 거부하면 같은 연결에서 controller HCI의 수신 파라미터와 CTE 요청
명령 수락 여부를 따로 기록한다. 원시 HCI 명령이 성공해도 Host의 연결 상태
검사를 우회한다. 이 내부 fixture는 controller가 수락한 수신 설정의 수명에만
`BT_CONN_CTE_RX_ENABLED`, `BT_CONN_CTE_RX_PARAMS_SET`, `cte_types`를 동기화해
Host가 실제 controller event를 IQ callback으로 전달하도록 한다. 이 동기화는
IQ event나 sample을 생성하지 않으며 공개 API·Arduino 예제에는 포함하지 않는다.

`bt-ll-sw-split` snippet, `nrf54l15dk/nrf54l15/cpuapp/nu54dk` target,
저장소의 `board_package/NU54DK_Zephyr_DTS` board root로 빌드한다.
자동 central PHY 변경 오류와 IQ 안정성을 분리하도록 이 진단은
`CONFIG_BT_AUTO_PHY_CENTRAL_NONE=y`를 사용한다. 이는 이전 재부팅의
원인이 PHY였다는 확정이 아니다. [244번 실기 기록](<../../../00_Docs/04_검증 기록/244_M31_P2_DF_연결_IQ_진단.md>)의
내부 연결형 IQ 20 report·1,640 sample·cleanup 국소 PASS는 공개 Arduino/SDC RX 지원을 뜻하지 않는다.

`tests/hil/nu54dk/m31_df_connected_rx_run.py`는 probe SHA-256 역할 매핑,
exact app·aux COM, auto unlock 없는 sector flash, reset-halt-drain-resume,
UART 결과를 JSON으로 기록한다. 원본 probe
UID와 Bluetooth 주소는 기록하지 않는다.

출력 태그 `AOA_RX_ENABLE`, `RAW_RX_PARAM`, `HOST_RX_STATE`, `RAW_REQUEST`,
`IQ`를 별도로 해석한다. HCI 명령 수락, controller IQ event 도달, Host callback,
양수 sample 수신은 각각 독립 판정한다. 연결 기반 결과를 connectionless AoA나
각도 측정, 안테나 전환, 외장 RF 경로의 PASS로 확대하지 않는다.

P2 계측 구성은 `CONFIG_THREAD_ANALYZER`와 heap runtime stats를 켠다.
`s`로 수신과 연결을 종료한 뒤 `P2_STACK`·`P2_MALLOC`·`P2_KHEAP`을
출력한다. 이는 내부 LL 진단 image의 관찰값이며 Arduino/SDC RX의
high-water나 controller 내부 pool 사용량이 아니다.
[246번 계측 기록](<../../../00_Docs/04_검증 기록/246_M31_P2_DF_연결_IQ_메모리_계측.md>)에서
실기 원본과 판정 경계를 확인할 수 있다.
