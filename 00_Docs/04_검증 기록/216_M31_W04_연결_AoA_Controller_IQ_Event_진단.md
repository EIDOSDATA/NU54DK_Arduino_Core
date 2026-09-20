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
