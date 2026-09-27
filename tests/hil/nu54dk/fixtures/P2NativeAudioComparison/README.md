# P2 동등 조건 native Audio 비교

고정 NCS v3.4.0의 Zephyr `bap_broadcast_source`를 제품 SDC와 NU54DK target으로
빌드한다. `source.conf`는 Arduino P2 source와 동일하게 encrypted BAP broadcast,
LC3 16 kHz mono, stream/subgroup/ISO channel 1개, 40-byte SDU, TX buffer 6개,
main 8,192 B, system workqueue 4,096 B, libc arena 8,192 B, 로그 비활성,
thread/heap 계측 활성으로 고정한다.

`P2NativeTelemetry` module과 `dts/nucode/nu54dk-arduino-storage.dtsi`를 함께 전달해
계측 코드와 loaderless `slot0 [0, 0x16c000)` 영역이 양쪽 image에서 같게 한다.
native sample 고유 제어 코드와 Arduino/NUCODE facade 비용은 ELF/map symbol 분류에서
따로 기록하며, Arduino 설정을 native 쪽에 추가해 차이를 숨기지 않는다.
