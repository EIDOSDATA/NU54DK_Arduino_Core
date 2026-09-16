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

## `BapUnicastSink`

- 두 보드를 준비해 이 스케치를 sink 보드에 올린다. 상대 보드에는 고정 NCS v3.4.0의
  `zephyr/samples/bluetooth/bap_unicast_client`를 NU54DK target으로 빌드해 올린다.
  공개 Arduino client 역할 예제는 별도로 개발 중이다.
- 스케치가 PACS/ASCS의 mono LC3 sink를 등록하고 ASCS UUID를 광고한다. 상대 client가
  연결해 codec/QoS와 ASE를 설정하면 40-byte LC3 frame을 실제 CIS로 보낸다.
- `loop()`가 공개 `UnicastServer::readFrame()`으로 frame을 읽고 `Lc3Codec::decode()`를
  호출한다. 115200 baud Serial은 100 frame마다 decoded 수·PCM energy·queue drop 수를
  표시한다. 정상 전송에서는 `dropped=0`을 기대한다.
- 예제의 `prj.conf`는 16 kHz·10 ms LC3, sink ASE 1개, ISO channel 1개와 비영속
  LE Secure Connections pairing을 고정한다. `CONFIG_BT_SETTINGS=n`은 다른 예제에서
  남은 bond를 변경하거나 지우지 않으면서 새 상대와 L2 연결을 시험하기 위한 선택이다.
- 현 빌드는 RAM 약 85%를 사용한다. 외장 mic/speaker나 추가 stream을 이 설정에
  바로 합치지 말고 자원 예산을 다시 계산해야 한다.

## `BapUnicastSource`

- 두 보드에 각각 `BapUnicastSource`와 `BapUnicastSink`를 올린다. Source는
  ASCS UUID를 광고하는 sink를 검색하고 연결한 뒤 공개 `UnicastClient`로
  PACS/ASCS 설정과 CIS 시작을 진행한다.
- Arduino `loop()`에서 16 kHz 합성 PCM을 만들고 `Lc3Codec::encode()`로
  40-byte LC3 frame을 생성해 `UnicastClient::sendFrame()`으로 보낸다.
  Zephyr 호출은 라이브러리 구현 내부에만 있다.
- `prj.conf`는 unicast client, ISO TX와 liblc3를 선택한다. 일시적인 L2
  pairing을 사용하므로 다른 예제의 bond 설정을 변경하지 않는다.

Arduino IDE나 CLI에서 **NU54DK Zephyr / BLE** feature set으로 빌드한다. 115200 baud
Serial의 bounded 검증 명령은 반복 회귀 시험을 위한 구현 세부사항이며 Arduino 공개 API나
호환성 계약에는 포함되지 않는다. PDM/I2S microphone과 I2S codec/speaker 경로는
외장 I/O 예제에서 별도로 다룬다.

## 출처와 라이선스

LC3 frame 계약은 고정 NCS v3.4.0의 `samples/bluetooth/bap_unicast_client`,
`bap_unicast_server`, `bap_broadcast_source`를 기준으로 확인했다. 이 라이브러리 코드는 MIT이고,
고정 SDK의 원본 sample과 liblc3는 각 원본 라이선스를 따른다.
