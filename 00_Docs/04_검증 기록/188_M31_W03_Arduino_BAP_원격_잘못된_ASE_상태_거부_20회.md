# M31-W03 Arduino BAP 원격 잘못된 ASE 상태 거부 20회

clean Core `df7bf15a58dc0e853efdb8b83b9532c7b767ca0b`의 공개
`BapUnicastSink` Arduino 예제를 서버로 사용했다. 고정 NCS v3.4.0
`bap_unicast_client`의 해시 검증 복사본을 client로 빌드했다. client는
sink ASE를 발견한 뒤 **idle** 상태와 실제 ASE ID를 확인하고, ASCS 제어
지점을 UUID로 검색해 그 ASE에 Release opcode `0x08`을 보냈다. 서버의
원격 알림은 매회 `code=4`(invalid ASE state), `reason=0`이었다.

두 CMSIS-DAP V2 보드를 매회 hardware reset해 연결·보안 상태를 분리한
clean 반복 **20/20회가 거부**되었다. 회차별 응답 소요는 7.250~7.640초,
30초 한도 초과와 예상 밖 성공·fatal fault·보안 오류는 0건이다. 원시 probe
UID는 기록하지 않고 익명 SHA-256 mapping으로 선택했다.

client FLASH 349,600 B·RAM 71,936 B다. client HEX SHA-256은
`809f3038dc9788d79226628869ccd7d954b20575968e92cb5666939104b3660d`,
client `.config`는
`2b05c55266947e7415ebd663bd5f7255730bc42962167341d22e9ee3caa06df9`다.
서버 HEX는 앞선 [원격 codec·QoS 기록](187_M31_W03_Arduino_BAP_원격_codec_QoS_거부_각_20회.md)의
`53cfdadc8de7276ac6fb00def4dc1e6c61a5b5097d48e6f3d4026b46048fd8c8`과 같다.
client는 sector flash·hardware reset으로 올렸다. 첫 flash는 commit 전
candidate였으나 clean revision에서 재생성한 fixture가 빌드 때 사용한
소스와 byte 단위로 같고 이미지·설정 해시도 변하지 않았다.

[회차별 원본](evidence/m31-w03-bap-state-df7bf15a/state-exact.json),
[fixture 원본·생성 해시](evidence/m31-w03-bap-state-df7bf15a/fixture-prepare.json),
[build 요약](evidence/m31-w03-bap-state-df7bf15a/build-summary.json),
[manifest](evidence/m31-w03-bap-state-df7bf15a/manifest.json)에 이미지·설정·
build log·flash 기록 해시를 보존한다. NCS·Zephyr·보드 submodule 원본은
수정하지 않았다. 공개 `.ino`는 `NUCODE_BLE_Audio` API만 사용하며 시험용
Zephyr 호출은 저장소 밖에서 생성한 native fixture에만 있다.

이 결과와 앞선 codec·QoS 거부는 W03-02의 원격 negative 범위다. Arduino
양방향 stream과 나머지 W03 profile은 미완료이므로 W03-02 전체
`functional_hil`과 M31-W03은 계속 `NOT_RUN`이다.
