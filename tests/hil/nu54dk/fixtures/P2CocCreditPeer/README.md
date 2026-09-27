# P2 CoC 상대 credit 고갈 fixture

고정 NCS v3.4.0과 제품 SDC에서 Zephyr LE CoC endpoint가 연결 때 부여하는
초기 credit 1개를 `-EINPROGRESS`로 보류해 상대 credit을 직접 고갈시킨다.
Arduino client가 512-byte SDU 4개를 제출하면 첫 SDU만 peer callback에 도달하고
나머지 3개는 remote-credit 대기로 남는다. UART `r` 명령에서
`bt_l2cap_chan_recv_complete()`로 1개를 반환하며, 대기 SDU와 새 SDU echo가
복구 기준이다. `h`/`r`/`s`만 허용하고 무한 재시도하지 않는다.

기본 `prj.conf`는 위 HIL의 516-byte ACL·TX buffer 8개 조건을 보존한다. 동일 조건
CoC server 정적 크기 비교에서는 `comparison.conf`를 `EXTRA_CONF_FILE`로 추가해
Arduino image와 같은 ACL 251-byte·TX buffer 4개·로그 OFF·loaderless partition으로
빌드한다. Arduino의 dual-role·연결 2개 설정은 native에 추가하지 않는다.
Arduino client의 로컬 TX buffer 포화만으로 상대 credit 고갈을 주장하지 않는다.
