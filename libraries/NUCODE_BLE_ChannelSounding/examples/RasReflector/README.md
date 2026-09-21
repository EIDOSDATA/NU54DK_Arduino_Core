# Ranging Service reflector

이 예제는 개발 소스 `0.4.1-dev`의 Channel Sounding 범위이며 전체 검증은 아직 완료되지 않았다. 현재
설치·지원 package는 `v0.4.1`이며 이 개발 예제가 그 공개 ZIP에 포함됐다는 뜻은 아니다.
아래 준비 상태는 전체 기능 완료나 거리 정확도 보증이 아니다.

이 스케치는 `NU54-CS-RSP` 이름과 Ranging Service UUID `0x185B`로 연결 가능한
광고를 시작합니다. 중앙 장치가 연결되면 공개 `RasReflector` API가 기본 안테나의
CS 설정과 Ranging Service 응답을 준비합니다. 연결이 끊어지면 자원을 반환하고
다시 광고합니다.

Serial Monitor는 115200 baud입니다. `secure L2`, `config ready`,
`CS procedures enabled` 출력은 단계별 상태를 뜻합니다. 거리 측정값은
initiator에서 계산하며, 이 스케치 자체가 거리값을 만들지는 않습니다.
