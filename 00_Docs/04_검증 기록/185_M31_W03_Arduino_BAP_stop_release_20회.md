# M31-W03 Arduino BAP stop/release 20회

clean Core `860a3eedac5625ec34d33a179c20fe284e19af5c`에서 공개
`BapUnicastCycle`와 `BapUnicastSink` 예제를 빌드했다. Source HEX SHA-256은
`89281fe9043425f01491a9eeda32e4bb4927a78a0c2b62c693e0e193ea0040c4`,
Sink는 `53cfdadc8de7276ac6fb00def4dc1e6c61a5b5097d48e6f3d4026b46048fd8c8`이다.
두 구성 모두 LC3와 `CONFIG_BT_TX_PROCESSOR_STACK_SIZE=3200`을 포함한다. Source는
FLASH 502,728 B·RAM 227,254 B, Sink는 FLASH 474,736 B·RAM 227,320 B다.

두 CMSIS-DAP V2 probe의 익명 SHA-256 mapping을 확인했다. Sink는 앞서 기록한
동일 해시의 이미지를 유지하고 Source만 sector flash·hardware reset했다.
[플래시 기록](evidence/m31-w03-bap-stop-release-860a3eed/flash.json)은 이를
`sector_flash_client_reset`으로 표시한다. Sink를 같은 clean Core에서 다시 빌드해 HEX와
설정 해시가 이미 보드에 기록된 이미지와 일치함을 확인했다.

[20회 측정](evidence/m31-w03-bap-stop-release-860a3eed/cycles-exact.json)에서
매 연결마다 Source가 LC3 120 frame을 전송하고 공개 `UnicastClient::stop()`으로
ASE를 disable·release한 뒤 ACL을 해제했다. 각 회차에서 Source의 100 frame
전송 로그, `stream stopped`, `completed cycles=N`, 연결 해제와 Sink의 누적
100 frame 이상 복호화를 요구했다. **20/20 PASS**, Sink 복호화 합계 2,400 frame,
전체 120.015초, 회차별 5.828~6.750초로 30초 회복 한도 안이다. 첫 스트림
이후 setup failure는 0건이고 fatal fault와 queue drop도 기록되지 않았다.

첫 측정은 20회 수치가 통과했으나 정상 release 후 ACL 해제를 backend가 오류로
기록한 두 사례를 발견했다. `expected_disconnect`를 release 완료 뒤에만 세우고
시험기가 첫 스트림 이후의 setup failure를 즉시 실패 처리하도록 수정했다.
수정한 clean Core에서 위 20회를 다시 측정했으며 해당 오류는 0건이다. 첫 연결
이전에는 이전 flash의 bond 불일치로 보안 재시도가 생길 수 있고, 판정은 실제
새 stream의 전송·복호화·해제 완료를 기준으로 한다.

[manifest](evidence/m31-w03-bap-stop-release-860a3eed/manifest.json)는 측정,
플래시, 두 빌드 기록, 압축 HEX·설정의 SHA-256을 보존한다. 원본 probe UID는
증거에 저장하지 않았다. M31 Host 49개, M13 Host 14개 중 13개 통과·1개 skip,
공개 예제 80개 점검과 M31 계약 검사도 통과했다. CI/CD는 조회하지 않았다.

이 증거는 **Arduino 단방향 BAP unicast stop/release와 재연결**만 입증한다.
Arduino 양방향 stream 및 잘못된 ASE 상태·codec/QoS negative, W03-03 이후
profile은 남아 있다. W03-01/02 전체 `functional_hil`이나 M31-W03 완료로
승격하지 않는다.
