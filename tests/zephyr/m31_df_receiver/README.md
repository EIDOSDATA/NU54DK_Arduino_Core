# 기본 안테나 CTE 수신 진단

이 앱은 M31-W04의 내부 Zephyr 진단용이며 W04는 아직 완료되지 않았다. 공개
[`CteBeacon.ino`](../../../libraries/NUCODE_BLE_DirectionFinding/examples/CteBeacon/CteBeacon.ino)와
그 backend [`NUCODE_BLE_DirectionFinding.cpp`](../../../libraries/NUCODE_BLE_DirectionFinding/src/NUCODE_BLE_DirectionFinding.cpp)가
구성한 `NU54-CTE` 송신자를 고정 Zephyr LL controller에서 찾아 periodic sync와
공개 AoA CTE RX API의 반환값을 분리 확인한다. Arduino 사용자 예제가 아니다.
수신 콜백은 IQ report가 실제 도착했을 때만 `M31_RX|1|IQ`를 출력한다.

고정 NCS `v3.4.0`에서 NU54DK board root와 `bt-ll-sw-split` snippet을 지정해
`west build --no-sysbuild`로 빌드한다. 테스트 중 한 번의 sync 실패를 반복 생성하지
않으며, timeout 뒤 연결 객체를 삭제하지 않아 실패 조사 중 sample의 삭제 race를 피한다.
`CTE_ENABLE|code=0`만으로 IQ 수신을 판정하지 않는다. 1안테나 Host 제약 및
판정 범위는 [W04 진단 기록](<../../../00_Docs/04_검증 기록/172_M31_W04_DF_기본안테나_IQ_수신_진단.md>)에 둔다.
