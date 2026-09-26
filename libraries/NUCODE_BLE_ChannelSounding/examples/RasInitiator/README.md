# Ranging Service initiator

이 예제는 공개 후보 `v0.5.0-rc.1`에 포함되며 Channel Sounding 검증을 완료했다.
Windows 설치 방법은 [RC 안내](<../../../../00_Docs/05_릴리스/v0.5.0-rc.1/README.md>)를 따른다.
정식 지원 버전 `v0.4.1`에는 포함되지 않는다.
아래 출력은 구현된 비보정 RTT 경로의 의미이며 거리 정확도·cross-vendor 상호운용 보증이 아니다.

고정 NCS v3.4.0 제품 SDC에서 secure raw 100건, stop/restart·disconnect/reconnect 각 20/20,
256-step 유효 raw 1,000건과 peer-loss 복구를 확인했다. 비암호화·wrong peer·one-sided stale-key는
secure RAS를 열지 않았고, stale-key 오류 때 ACL은 명시적 STOP까지 유지될 수 있다.

이 스케치는 Ranging Service UUID를 광고하는 reflector를 검색해 연결합니다. 공개
`RasInitiator` API가 L2 보안, Ranging Service 탐색, CS capability·config·보안
절차를 진행합니다. 준비가 되면 CS 절차를 시작하고 같은 counter의 로컬·상대
raw step 개수와 유효한 mode 1 왕복 시간으로 계산한 거리 추정치를 출력합니다.

Serial Monitor는 115200 baud입니다. 연결 중 `s`는 CS 절차 중단, `r`은
재시작, `d`는 연결 해제를 요청합니다. 해제 후에는 검색·연결·보안·CS 설정을
다시 진행합니다. `CS_RAW`의 `rtt`와 `tone`은 각 mode의 step 개수,
`valid_rtt`는 유효한 RTT 쌍의 수, `distance_m`은 미보정 RTT 거리(m)입니다.
RTT 쌍이 없을 때는 거리를 출력하지 않습니다. 장애물·안테나·환경에 따른
정확도는 별도로 검증해야 합니다.
