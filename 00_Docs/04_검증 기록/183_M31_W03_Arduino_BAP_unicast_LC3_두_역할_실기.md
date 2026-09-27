# M31-W03 Arduino BAP unicast LC3 두 역할 실기

clean Core `b5623c7de6941ed043d3b2a50f4171f990cdbff5`에서 공개
[`BapUnicastSource`](../../libraries/NUCODE_BLE_Audio/examples/BapUnicastSource/BapUnicastSource.ino)와
[`BapUnicastSink`](../../libraries/NUCODE_BLE_Audio/examples/BapUnicastSink/BapUnicastSink.ino)를
NU54DK Zephyr / BLE 설치 예제로 각각 빌드했다. Source `.ino`가 합성 PCM을
`Lc3Codec::encode()`로 40-byte LC3 frame에 넣고, `UnicastClient::sendFrame()`으로
보낸다. Sink `.ino`는 공개 `UnicastServer::readFrame()`과
`Lc3Codec::decode()`로 수신 frame을 처리한다. 스케치는 일반 C++과 `NUCODE_*`
API만 사용하며 PACS/ASCS·GATT·CIS·Zephyr callback은 라이브러리 `.cpp`에 있다.

Source HEX SHA-256은 `89c53a8b09d1f87de5d575fd8c6322268e7a9e636b128f809cb087fd0afd178f`이고
FLASH 500,904 B·RAM 224,941 B다. Sink HEX SHA-256은
`7542183c36587efc75e336fff82128a8fba5b8d3a35ab69bb2461fb5a36bff03`이고
FLASH 474,180 B·RAM 225,024 B다. 두 역할 모두 256 KiB RAM의 약 85%를
사용하므로 외장 입출력이나 stream 추가 전에 자원 예산을 다시 검토해야 한다.

두 CMSIS-DAP V2 probe의 익명 SHA-256 mapping과 DP/AP 보호 상태를 확인한 뒤
두 이미지를 sector flash·hardware reset했다. flash와 측정을 분리하고 다시
hardware reset한 clean-source run에서 PACS/ASCS 검색, codec/QoS, ASE enable,
CIS 시작이 이어졌다. Source가 40-byte LC3 frame 1,000개를 전송하고 Sink가
1,000개를 복호화했다. Sink PCM energy는 1,159,890, queue drop은 0이며
관찰 시간은 15.5초다. 이는 두 Arduino 역할 사이의 실제 무선 LC3
encode → CIS → decode 확인이다.

초기 후보는 ASCS 명령 응답을 ASE 상태 변경 완료로 잘못 취급해 QoS를 일찍
요청했다. 고정 SDK의 `bt_bap_stream_ops` 상태 callback을 기준으로 고쳤다.
플래시 뒤 실행기에서 다시 reset하면 첫 연결과 재부팅 로그가 섞여 거짓
실패가 생겼다. 따라서 exact run은 [flash 기록](evidence/m31-w03-bap-arduino-pair-b5623c7d/flash.json)과
[독립 reset 측정](evidence/m31-w03-bap-arduino-pair-b5623c7d/pair-exact.json)을
분리했다. [manifest](evidence/m31-w03-bap-arduino-pair-b5623c7d/manifest.json)에는
이미지·설정·빌드 로그·원본 HIL JSON의 hash와 자원 수치를 기록했다.
`m31_example_audit.py`는 예제 79개·문제 0개, M31 Host 49개와 M13 예제 계약
14개(1 skip)가 통과했다. CI/CD는 조회하지 않았다.

이 결과는 W03-01/02의 **Arduino source-to-sink 단방향 LC3 역할 검증**이다.
양방향 stream, stop/release 20회·재연결, 잘못된 ASE 상태·codec/QoS negative,
외장 audio I/O와 W03-03 이후 profile은 남아 있다. W03-01/02 전체 또는
M31-W03 완료로 승격하지 않는다.
