# NUCODE BLE Audio 예제

이 예제들은 `NUCODE_BLE_Audio.h`의 공개 Arduino API로 LC3와 Bluetooth LE Audio 기능을
실행한다. `.ino`에는 일반 C++로 PCM 생성, codec 설정, encode/decode, 결과 검사와 오류 처리를
보여 준다. liblc3와 Zephyr Audio 객체는 라이브러리 구현 내부에 있다.

## `Lc3SyntheticLoopback`

- `Lc3Codec::begin()`으로 16 kHz, 10 ms, 40-byte LC3 frame을 구성한다.
- 서로 다른 합성 삼각파 PCM 100 frame을 `encode()`한 뒤 `decode()`한다.
- frame 수, encoded checksum과 decoded energy를 검사한다. LC3는 손실 codec이므로 입력 PCM과
  출력 PCM의 byte 동일성은 합격 기준으로 사용하지 않는다.
- 잘못된 frame duration과 sample rate가 `Error::invalid_argument`로 거부되는지도 확인한다.

예제의 `prj.conf`는 `CONFIG_LIBLC3`, FPU, Arduino runtime과 Serial을 고정한다. Arduino IDE나
CLI에서 **NU54DK Zephyr / BLE** feature set으로 빌드한다.

115200 baud Serial의 bounded 검증 명령은 반복 회귀 시험을 위한 구현 세부사항이며 Arduino
공개 API나 호환성 계약에는 포함되지 않는다. BAP 무선 전송, PDM/I2S microphone과 I2S
codec/speaker 경로는 각 역할 예제와 외장 I/O 예제에서 별도로 다룬다.

## 출처와 라이선스

LC3 frame 계약은 고정 NCS v3.4.0의 `samples/bluetooth/bap_unicast_client`,
`bap_unicast_server`, `bap_broadcast_source`를 기준으로 확인했다. 이 라이브러리 코드는 MIT이고,
고정 SDK의 원본 sample과 liblc3는 각 원본 라이선스를 따른다.
