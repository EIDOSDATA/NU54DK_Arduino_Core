# Ranging Service initiator

이 스케치는 `NU54-CS-RSP` 이름의 reflector를 검색해 연결합니다. 공개
`RasInitiator` API가 L2 보안, Ranging Service 탐색, CS capability·config·보안
절차를 진행합니다. 준비가 되면 CS 절차를 시작하고 같은 counter의 로컬·상대
raw step 개수와 유효한 mode 1 왕복 시간으로 계산한 거리 추정치를 출력합니다.

Serial Monitor는 115200 baud입니다. 연결 중 `s`는 CS 절차 중단, `r`은
재시작, `d`는 연결 해제를 요청합니다. 해제 후에는 검색·연결·보안·CS 설정을
다시 진행합니다. `CS_RAW`의 `rtt`와 `tone`은 각 mode의 step 개수,
`valid_rtt`는 유효한 RTT 쌍의 수, `distance_m`은 미보정 RTT 거리(m)입니다.
RTT 쌍이 없을 때는 거리를 출력하지 않습니다. 장애물·안테나·환경에 따른
정확도는 별도로 검증해야 합니다.
