# M31-W03 Arduino BAP 잘못된 상태 전이 거부 40회

clean Core `9084063b42e2a63fcb360e8feb75203ea43e5bcf`의 공개
`BapUnicastCycle` 예제에서 매 LC3 stream 120 frame 전송 뒤
`UnicastClient::stop()`을 호출했다. 이어 중단 중인 ASE에 중복 stop과 frame
전송을 각각 한 번씩 시도하고, 두 공개 API가 모두 `Error::not_ready`를
돌려주는지 확인했다. Zephyr API는 예제 `.ino`에서 직접 호출하지 않는다.

Source의 20회 stop/release·연결 해제·재연결이 모두 통과했다. 매 회차에서
두 잘못된 상태 전이를 거부해 **40/40회**, 잘못된 성공 0건이다. Sink의
LC3 복호화는 2,400 frame, queue drop 0이다. 전체 121.360초,
회차별 5.844~6.860초로 30초 회복 한도 안이다. 첫 스트림 이후 설정 오류와
fatal fault는 0건이다. Source FLASH 502,844 B·RAM 227,254 B다.

두 CMSIS-DAP V2 probe는 익명 SHA-256 mapping으로 선택했다. 이미 보드에
있는 동일 해시 Sink 이미지는 유지하고 Source만 sector flash와 hardware
reset으로 갱신했다. [플래시 기록](evidence/m31-w03-bap-invalid-state-9084063b/flash.json),
[회차별 측정](evidence/m31-w03-bap-invalid-state-9084063b/cycles-exact.json),
[manifest](evidence/m31-w03-bap-invalid-state-9084063b/manifest.json)에
이미지·설정과 측정 파일 해시를 보존한다. 원본 probe UID는 저장하지 않았다.

이는 **공개 API의 중단 중 잘못된 상태 전이**에 대한 거부 증거다. 원격 ASCS
제어 지점의 잘못된 ASE 상태, unsupported codec/QoS 거부를 대체하지 않는다.
Arduino 양방향 stream과 나머지 W03 profile도 미완료다. W03-02 전체
`functional_hil`과 M31-W03 완료 상태는 그대로 `NOT_RUN`이다.
