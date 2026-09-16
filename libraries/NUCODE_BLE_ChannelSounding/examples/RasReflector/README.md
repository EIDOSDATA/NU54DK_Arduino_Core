# Ranging Service reflector

이 스케치는 `NU54-CS-RSP` 이름과 Ranging Service UUID `0x185B`로 연결 가능한
광고를 시작합니다. 중앙 장치가 연결되면 공개 `RasReflector` API가 기본 안테나의
CS 설정과 Ranging Service 응답을 준비합니다. 연결이 끊어지면 자원을 반환하고
다시 광고합니다.

Serial Monitor는 115200 baud입니다. `secure L2`, `config ready`,
`CS procedures enabled` 출력은 단계별 상태를 뜻합니다. 거리 측정값은
initiator에서 계산하며, 이 스케치 자체가 거리값을 만들지는 않습니다.
