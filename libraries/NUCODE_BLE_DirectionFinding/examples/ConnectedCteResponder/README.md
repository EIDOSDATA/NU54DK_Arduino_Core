# Connected CTE responder

이 예제는 `NU54-CTE-RSP`라는 이름으로 연결 가능한 광고를 시작합니다. 중앙 장치가
연결되면 `ConnectedResponder` 공개 API로 기본 안테나의 AoA CTE 응답을 활성화하고,
연결이 끊어지면 응답 자원을 반환한 뒤 광고를 다시 시작합니다.

Serial Monitor는 115200 baud를 사용합니다. 연결 중 `s`를 입력하면 응답을 멈추고,
`r`을 입력하면 같은 연결에서 재시작합니다. Arduino sketch에는 연결 event와
시작·중단 흐름이 보이며 Bluetooth controller 호출은 라이브러리 구현에 있습니다.

연결과 응답 활성화만으로 상대 장치가 CTE를 요청했거나 IQ sample을 받았다는 뜻은
아닙니다. 실제 IQ 수집은 CTE 요청과 수신 기능을 갖춘 중앙 장치에서 별도로 확인해야
합니다. 단일 기본 안테나 예제는 안테나 배열을 이용한 방향각을 계산하지 않습니다.
