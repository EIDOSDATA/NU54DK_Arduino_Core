# Connected CTE responder

이 예제는 개발 소스 `0.4.1-dev`의 Direction Finding 진단 범위이며 수신·IQ
경로는 아직 완료되지 않았다.
현재 설치·지원 package는 `v0.4.1`이며 이 개발 예제가 그 공개 ZIP에 포함됐다는 뜻은 아니다.

[`ConnectedCteResponder.ino`](ConnectedCteResponder.ino)는 `NU54-CTE-RSP`라는 이름으로
연결 가능한 광고를 시작합니다. 중앙 장치가
연결되면 `ConnectedResponder` 공개 API로 기본 안테나의 AoA CTE 응답을 활성화하고,
연결이 끊어지면 응답 자원을 반환한 뒤 광고를 다시 시작합니다.

이 보드의 기본 SoftDevice Controller는 연결 기반 CTE 송신 명령을 제공하지 않습니다.
따라서 예제의 `app.overlay`와 `prj.conf`가 Zephyr LL controller 및 연결 CTE 응답
기능을 선택합니다. 다른 BLE 예제의 controller 설정을 그대로 복사하면 시작이 실패할 수
있습니다.

Serial Monitor는 115200 baud를 사용합니다. 연결 중 `s`를 입력하면 응답을 멈추고,
`r`을 입력하면 같은 연결에서 재시작합니다. Arduino sketch에는 연결 event와
시작·중단 흐름이 보이며 Bluetooth controller 직접 호출은
[`NUCODE_BLE_DirectionFinding_Connected.cpp`](../../src/NUCODE_BLE_DirectionFinding_Connected.cpp)에 있습니다.

연결과 응답 활성화만으로 상대 장치가 CTE를 요청했거나 IQ sample을 받았다는 뜻은
아닙니다. 실제 IQ 수집은 CTE 요청과 수신 기능을 갖춘 중앙 장치에서 별도로 확인해야
합니다. 단일 기본 안테나 예제는 안테나 배열을 이용한 방향각을 계산하지 않습니다.
