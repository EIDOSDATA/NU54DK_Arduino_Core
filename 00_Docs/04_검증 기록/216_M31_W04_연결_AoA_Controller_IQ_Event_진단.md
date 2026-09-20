# M31-W04 연결 AoA controller IQ event 진단

`7586cb14bbea666b7ad2a49280be4a9dbc1fd846`의 clean source와 고정 NCS
v3.4.0, Zephyr `bf801e4e3d19e1ffa76164346480cb7734dd2800`, Windows toolchain
`dcbdc366a1`로 연결 수신 진단 앱과 공개 `ConnectedCteResponder`를 새로 빌드했다.
실기 직전 두 probe의 SHA-256 역할, 현재 COM14/COM13, DP/AP identity를 다시 확인하고
probe lock 안에서 sector flash와 hardware reset만 수행했다.

[첫 실행 원본](evidence/m31-w04-w05-7586cb14/connected-rx-diagnostic-01.json)은
기존 실패 원본을 덮어쓰지 않고 별도 보존한다.

| 판정 범위 | 결과 | 근거와 경계 |
| --- | --- | --- |
| exact image/source | PASS | Core·board commit과 두 HEX SHA-256, controller/SoC register를 실행 원본에 기록 |
| 공개 Host AoA RX | HOLD | 기본 안테나 1개에서 `bt_df_conn_cte_rx_enable()`의 `-EINVAL` 경계 유지 |
| controller HCI 명령 | PASS | 같은 ACL에서 RX parameter와 CTE request enable이 각각 `code=0` |
| controller IQ event 존재 | PASS | LE meta subevent `0x16` 뒤 Host의 `Received conn CTE report when CTE receive disabled`를 9회 관측 |
| Host raw IQ callback | HOLD | Host 내부 RX enable/type 상태가 없어서 callback 전에 `-EINVAL`로 폐기, IQ sample 0건 |
| STOP/cleanup | FAIL | debug 전량 출력이 UART를 포화시켜 STOP 확인 문자열을 보존하지 못함 |
| 각도 계산·외장 RF | NOT RUN | IQ callback·안테나 전환·보정·상용 peer 실물이 없음 |

이 결과는 이전의 “HCI 명령 수락 뒤 IQ report 미관찰”보다 한 단계 좁혀진다.
LL controller는 실제 연결 IQ event를 Host까지 전달했다. 실패 지점은 CTE TX나 peer가
아니라, raw HCI 우회가 Zephyr Host의 `BT_CONN_CTE_RX_ENABLED`와 `conn->cte_types`를
설정하지 않는 경계다. 그렇더라도 sample payload를 callback으로 받지 못했으므로
`raw_iq_rx` 전체 PASS나 각도 측정 PASS로 확대하지 않는다.

이번 run은 전체 판정을 **FAIL**로 유지한다. 진단에 불필요한 Bluetooth debug 전량
출력이 수백 개 메시지를 drop시킨 것이 직접 원인이므로, 후속 image는 Host 오류를
보존하는 `CONFIG_BT_LOG_LEVEL_ERR=y`만 사용한다. 후속 run은 같은 exact 역할에서
요청 disable, sampling disable, ACL disconnect와 상대 disconnect를 모두 확인해야 한다.

## 로그 축소 후 재실행

`b5294c86da32a9ebde86db96ca3cff08b4a96859`의 clean source에서 Host 로그를
오류 수준으로 제한하고 연결 수신 image를 다시 빌드했다. 공개 responder도 같은
revision의 source manifest로 다시 빌드한 뒤 같은 현재 mapping에서 실행했다.
[재실행 원본](evidence/m31-w04-w05-b5294c86/connected-rx-diagnostic-02.json)은
첫 실행 원본과 분리해 보존한다.

| 판정 범위 | 결과 | 근거와 경계 |
| --- | --- | --- |
| exact image/source | PASS | clean core revision과 receiver/responder HEX SHA-256을 원본에 기록 |
| controller HCI 명령 | PASS | RX parameter·CTE request enable과 두 disable 명령이 모두 `code=0` |
| controller IQ event 존재 | PASS | 연결 IQ event가 Host 상태 게이트까지 102회 도달 |
| Host raw IQ callback | HOLD | callback sample 0건, Host 상태 게이트 폐기 102건 |
| STOP/cleanup | PASS | request disable, sampling disable, local disconnect, receiver stop, peer disconnect 확인 |
| 각도 계산·외장 RF | NOT RUN | IQ sample·안테나 전환·보정·상용 peer 실물이 없음 |

따라서 W04 연결 기반 기본 안테나 경로는 `CONTROLLER_IQ_EVENT_HOST_DROPPED`로
재현 가능하게 좁혀졌지만, W04 전체와 `raw_iq_rx`는 여전히 **HOLD**다. controller
event 존재를 IQ payload 수신 또는 각도 측정 PASS로 확대하지 않는다.

## 고정 Zephyr source의 상태 경계

고정 Zephyr revision의 `subsys/bluetooth/host/direction.c`를 controller event와 다시
대조했다. `valid_cte_rx_common_params()`는 AoA 요청에서 controller antenna 수가 2보다
작으면 false를 반환하므로, 기본 안테나 1개의 공개 Host API는 HCI 전송 전에
`-EINVAL`로 종료된다. 반면 이번 진단의 raw HCI 우회는 controller 명령만 전송하므로,
공개 API의 성공 경로가 수행하는 아래 Host 상태 변경을 건너뛴다.

- `BT_CONN_CTE_RX_ENABLED` flag를 command state와 결합
- 수락된 CTE type을 `conn->cte_types`에 저장
- `BT_CONN_CTE_RX_PARAMS_SET` flag를 설정

연결 IQ event handler는 sample을 채우기 전에 먼저 `BT_CONN_CTE_RX_ENABLED`를 검사하고,
다음으로 event CTE type과 `conn->cte_types`를 대조한다. 따라서 102회의 동일 오류는
controller가 IQ event를 생성하지 못한 결과가 아니라 raw HCI와 Host connection state가
분리된 결과다. connectionless periodic sync 경로와 connected ACL 경로는 서로 다른 HCI
command·state 객체를 사용하므로 이 결과를 connectionless AoA RX 판정으로 재사용하지 않는다.

후속 시험은 공개 Arduino API가 아니라 전용 내부 HIL 진단에서만 Host 상태와 controller
명령을 같은 수명으로 결합해야 한다. 그 진단으로 sample을 받아도 기본 안테나 RSSI/IQ
원본 수신 범위일 뿐이며, 안테나 전환·각도 계산·외장 RF PASS가 되지는 않는다.
