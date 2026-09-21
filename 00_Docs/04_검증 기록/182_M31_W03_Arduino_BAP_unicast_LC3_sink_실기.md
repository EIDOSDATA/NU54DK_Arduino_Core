# M31-W03 Arduino BAP unicast LC3 sink 실기

공개 `NUCODE_BLE_Audio::UnicastServer`와 설치 예제
[`BapUnicastSink`](../../libraries/NUCODE_BLE_Audio/examples/BapUnicastSink/BapUnicastSink.ino)를
추가했다. `.ino`는 `BLEDevice`/광고·`UnicastServer::readFrame()`·
`Lc3Codec::decode()`·PCM energy와 오류 처리를 직접 보여 준다. PACS/ASCS와
Zephyr ISO callback은 라이브러리 `.cpp` 안에 있다.

clean Core `58f0e701646cf14a3fbd6088255e23d5a95a62fb`의 NU54DK Zephyr / BLE
설치 예제를 Arduino CLI로 빌드했다. FLASH 474,180 B, RAM 225,024 B
(256 KiB의 85%, 여유 37,120 B), Arduino HEX SHA-256
`7542183c36587efc75e336fff82128a8fba5b8d3a35ab69bb2461fb5a36bff03`이다.
기존 `Lc3SyntheticLoopback`도 새 라이브러리 소스로 다시 빌드해 PASS했다.

고정 NCS upstream `bap_unicast_client`의 native LC3 이미지
`8b0e801b1b13e3ec2f62e328f83227ae1144220fb50b839cc48ed945037d3a50`를
상대 보드에 올렸다. CMSIS-DAP V2로 익명 probe mapping과 register를 확인하고
두 이미지 모두 sector flash/hardware reset했다. PACS discovery → sink ASE
codec/QoS 설정 → enable/start가 이어졌고, client가 40-byte LC3 ISO SDU
1,000개를 보냈다. Arduino sink는 18.203초 관찰에서 1,000 frame을
복호화했고 PCM energy는 3,330,223, queue drop은 0이었다.

첫 개발 후보는 ACL 연결 뒤 SMP peer reason `0x03`으로 페어링이 거부돼
stream이 시작되지 않았다. 고정 SDK SMP source에는 같은 오류를 내는 복수 경로가
있으므로 오래된 bond가 원인이라고 확정하지 않는다. 예제에
`CONFIG_BT_SETTINGS=n`을 적용해 이 역할의 pairing을 비영속화하자 같은 두
보드의 후보 재시험과 clean 시험이 모두 통과했다. 다른 예제의 저장 bond는
삭제·변경하지 않았다. 향후 영속 bonding을 요구하는 제품 경로는 별도
원인 분석과 key 갱신/거부 검증이 필요하다.

[exact manifest](evidence/m31-w03-bap-arduino-sink-58f0e701/arduino-sink-manifest.json),
[원본 HIL JSON](evidence/m31-w03-bap-arduino-sink-58f0e701/arduino-sink-exact.json),
Arduino 빌드 artifact·HEX·로그와 실패/재시험 후보 원본을 같은 evidence
directory에 보존했다. image/config·probe SHA-256, UART 원본과 파일 hash를
대조했다. `m31_example_audit.py`는 설치 예제 78개·문제 0개였고, M13
예제 계약 14개(1 skip)와 M31 Host 49개가 통과했다. CI/CD는 조회하지 않았다.

이 결과는 **Arduino BAP unicast sink 한 역할의 실제 LC3 수신 PASS**다.
Arduino client/source·양방향 Arduino 역할, stop/release 20회와 재연결,
잘못된 codec/QoS·ASE 상태 negative, 외장 audio 입출력과 나머지 Audio
profile은 남아 있다. W03-01/02 family와 M31-W03 전체 완료로 승격하지 않는다.
