# Ranging Service initiator

이 예제는 정식 `v0.5.0`에 포함되며 Channel Sounding 검증을 완료했다.
Windows 10/11 x64 설치 방법은 [v0.5.0 안내](<../../../../00_Docs/05_릴리스/v0.5.0/README.md>)를 따른다.
아래 출력은 구현된 비보정 RTT 경로의 의미이며 거리 정확도·cross-vendor 상호운용 보증이 아니다.

보드 **NU54DK (nRF54L15, Zephyr)**, Feature set **BLE NUS**를 권장한다.
**Adaptive capabilities (experimental)**는 실험적 대안이다. NU54DK 두 대에 Initiator와
Reflector를 각각 업로드하고 Reflector를 먼저 켠다. `nucode-build.json`과 `prj.conf`를 `.ino`와
함께 유지한다. 여러 probe를 연결한 CLI Upload는 `NUCODE_PROBE_UID`로 exact UID를 지정하며,
GUI Upload는 한 번에 대상 보드 한 대만 연결한다. 업로드 후에는 두 보드를 모두 연결해 실행한다.

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
