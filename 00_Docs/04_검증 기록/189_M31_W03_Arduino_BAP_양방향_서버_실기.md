# M31-W03 Arduino BAP 양방향 서버 실기

clean Core `e613b01066b488ce8510c6306e323260172f2aeb`에서 공개
[`BapUnicastDuplexServer`](../../libraries/NUCODE_BLE_Audio/examples/BapUnicastDuplexServer/BapUnicastDuplexServer.ino)를
NU54DK Zephyr / BLE로 빌드했다. Sketch는 `NUCODE_BLE_Audio` 공개 API로
sink/source ASE를 각각 하나 등록하고, 수신 LC3를 복호화하며 합성 PCM을
LC3로 인코딩해 반대 방향으로 송신한다. Zephyr의 PACS/ASCS·CIS 호출은
라이브러리 `.cpp`가 소유한다. 상대는 고정 NCS v3.4.0의 native
`bap_unicast_client`이다. 따라서 이 시험만으로 Arduino client 예제의
양방향 기능을 완료 처리하지 않는다.

서버 image는 FLASH 515,484 B, RAM 231,579 B(88%), 남은 RAM 30,565 B다.
HEX SHA-256은 `adf5a9258c40d9bbd867dc9f2aa675a4110a3a1a0448f1c13ab6b4025f646714`,
`.config` SHA-256은 `913a7fdd3cf709a0b559d6982ff675297b6a6881dc897d1aaef1d159f7873d4e`다.
기존 단방향 `BapUnicastSink`는 같은 변경에서 별도로 빌드했고 기존
`UnicastServer::begin()` 진입점을 유지했다. 공개 예제 audit는 81개, 문제 0개다.

두 CMSIS-DAP V2 probe의 익명 SHA-256 mapping과 보호 상태를 확인하고
두 이미지를 sector flash했다. [flash 원본](evidence/m31-w03-bap-duplex-server-e613b010/flash-exact.json)의
서버 image hash와 [독립 reset 실기](evidence/m31-w03-bap-duplex-server-e613b010/pair-exact.json)의
참조 hash가 같다. 실제 CIS에서 native client TX 1,000 frame → Arduino
서버 수신·복호화 1,000 frame과 Arduino 서버 TX 1,000 frame → native client
수신 1,000 frame을 확인했다. 서버 PCM energy는 3,330,223, queue drop은
0이며 20.844초가 걸렸다. 보드 재설정만으로 반복한 clean-source 결과다.

처음 reset-only 측정은 결과 자체가 통과였지만 보드에 올라간 후보 HEX
`613b8121d691c81748303704bd8f8335ee9c25316ea29b4324fbb7296b23fdaa`와
최종 참조 HEX hash가 달랐다. 그 결과를 완료 증거에서 제외하고
[무효 원본](evidence/m31-w03-bap-duplex-server-e613b010/preflash-invalid.json)과
[불일치 판정](evidence/m31-w03-bap-duplex-server-e613b010/provenance-audit.json)을
보존했다. 최종 image를 실제 flash한 뒤 다시 측정한 결과만 채택한다.
[manifest](evidence/m31-w03-bap-duplex-server-e613b010/manifest.json)에
source/image/config/build log·원본 HIL JSON의 SHA-256을 남겼다.

이 결과는 W03-02의 **Arduino 양방향 서버 ↔ native client** 경로만
검증한다. 공개 Arduino 양방향 client와 Arduino↔Arduino 양방향 pair,
stop/release·재연결 회귀와 나머지 W03 profile은 미완료다. W03-02 전체와
M31-W03 전체 `functional_hil`은 계속 `NOT_RUN`이다. CI/CD 결과는 조회하지 않았다.
