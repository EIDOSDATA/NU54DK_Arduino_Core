# NUCODE BLE Direction Finding 예제

이 예제는 개발 소스 `0.4.1-dev`의 Direction Finding 범위이며 수신·IQ 경로는
아직 완료되지 않았다. 현재 설치·지원 package는 `v0.4.1`이며 이 개발 예제가 그
공개 ZIP에 포함됐다는 뜻은 아니다.

[`CteBeacon.ino`](CteBeacon/CteBeacon.ino)는 기본 안테나에서 connectionless AoA CTE를
송신하는 공개 Arduino 예제다. 일반 C++로 `BeaconConfig`를 설정하고 `Beacon::begin()`,
`start()`, `stop()`을 호출한다. Zephyr 광고 set과 Direction Finding 직접 호출은
[`NUCODE_BLE_DirectionFinding.cpp`](../src/NUCODE_BLE_DirectionFinding.cpp)에만 있다.

Arduino IDE 또는 CLI에서 **NU54DK Zephyr / BLE** feature set을 선택한다. 115200 baud
Serial에서 `PROBE`, `START`, `STOP`, `INVALID`를 한 줄씩 보낸다. `START` 뒤
`NUCODE_DF|1|STARTED`, `STOP` 뒤 `NUCODE_DF|1|STOPPED`, `INVALID` 뒤
`NUCODE_DF|1|REJECTED`를 기대한다. `START`와 `STOP`을 반복해 자원 재사용을 확인한다.

이 예제는 CTE 송신 설정과 controller 수락 경로를 제공한다. 실제 무선 CTE와 raw IQ
수신은 별도의 수신 보드가 있어야 검증된다. 1개 안테나의 IQ 값으로 각도를 계산하지
않으며 AoD 송신이나 안테나 전환을 지원한다고 주장하지 않는다.

Zephyr `direction_finding_connectionless_tx` sample의 AoA 설정을 고정 NCS v3.4.0에서
참고했다. 이 라이브러리 코드는 MIT이고 upstream sample은 원본 Apache-2.0을 따른다.
