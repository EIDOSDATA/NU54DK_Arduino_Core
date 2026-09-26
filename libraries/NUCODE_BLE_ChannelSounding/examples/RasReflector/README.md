# Ranging Service reflector

이 예제는 공개 후보 `v0.5.0-rc.1`에 포함되며 Channel Sounding 검증을 완료했다.
Windows 설치 방법은 [RC 안내](<../../../../00_Docs/05_릴리스/v0.5.0-rc.1/README.md>)를 따른다.
정식 지원 버전 `v0.4.1`에는 포함되지 않는다.
아래 준비 상태는 거리 정확도·cross-vendor 상호운용 보증이 아니다.

고정 NCS v3.4.0 제품 SDC에서 secure raw 100건, stop/restart·disconnect/reconnect 각 20/20,
256-step 유효 raw 1,000건과 peer-loss 복구를 확인했다. reflector bond만 삭제한 negative에서는
새 pairing·L2·ready·active·raw 없이 양쪽 STOP으로 정리됐다.

이 스케치는 `NU54-CS-RSP` 이름과 Ranging Service UUID `0x185B`로 연결 가능한
광고를 시작합니다. 중앙 장치가 연결되면 공개 `RasReflector` API가 기본 안테나의
CS 설정과 Ranging Service 응답을 준비합니다. 연결이 끊어지면 자원을 반환하고
다시 광고합니다.

Serial Monitor는 115200 baud입니다. `secure L2`, `config ready`,
`CS procedures enabled` 출력은 단계별 상태를 뜻합니다. 거리 측정값은
initiator에서 계산하며, 이 스케치 자체가 거리값을 만들지는 않습니다.
