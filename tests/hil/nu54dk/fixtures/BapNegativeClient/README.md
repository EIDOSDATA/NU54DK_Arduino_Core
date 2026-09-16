# BAP unicast 원격 ASCS 거부 시험 client

`prepare.py`는 고정 NCS v3.4.0의
`zephyr/samples/bluetooth/bap_unicast_client`를 저장소 밖의 새 디렉터리로
복사하고, 원본 `main.c`·`CMakeLists.txt` 해시를 확인한 뒤 시험 코드를
추가한다. SDK와 board submodule 원본은 수정하지 않는다.

생성된 app을 `nrf54l15dk/nrf54l15/cpuapp/nu54dk` 대상으로
`west build --no-sysbuild`로 빌드한다. 추가 CMake 인자
`M31_BAP_NEGATIVE_CASE=codec`은 서버가 제공하지 않는 24 kHz LC3를,
`M31_BAP_NEGATIVE_CASE=qos`는 서버의 40-byte 고정 SDU와 다른 41 byte를
요청한다. 두 경우 모두 기존
[`BapUnicastSink`](../../../../../libraries/NUCODE_BLE_Audio/examples/BapUnicastSink/BapUnicastSink.ino)
Arduino 예제를 상대 역할로 사용한다.

`m31_audio_bap_negative_run.py`는 원격 ASCS 응답 code 7과 codec reason 2
또는 QoS SDU reason 6을 확인한다. 매 반복에서 두 보드를 함께 hardware
reset하고 시험 client의 bonding flag를 끄므로 이전 연결의 휘발성 bond가
다음 회차의 보안 절차에 영향을 주지 않는다. 한 회차의 거부만으로 전체
W03-02를 완료로 판정하지 않으며, 원격의 잘못된 ASE 상태 요청과 Arduino
양방향 stream은 별도 시험이 필요하다.
