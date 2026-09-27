# M31-W03 Arduino BAP 원격 codec·QoS 거부 각 20회

clean Core `db99597094da758628445f8fb23e780b5e9f3b5a`의 공개
`BapUnicastSink` Arduino 예제를 서버로 실행했다. 고정 NCS v3.4.0의
`bap_unicast_client`를 원본 해시 검증 뒤 저장소 밖에 복사하고, 두 독립
시험 요청만 삽입해 원격 ASCS 응답을 확인했다. 원본 NCS·Zephyr와 보드
submodule은 수정하지 않았다.

| 원격 요청 | 서버 응답 | 결과 | 회차별 소요 |
| --- | --- | --- | --- |
| 서버가 지원하지 않는 24 kHz LC3 codec | `code=7 reason=2` | **20/20 거부** | 7.375~14.734초 |
| 서버의 40 B 한도를 넘는 41 B QoS SDU | `code=7 reason=6` | **20/20 거부** | 7.766~8.219초 |

모든 회차에서 client 연결과 sink discovery 뒤 해당 제어 응답을 확인했다.
각 회차는 두 보드를 hardware reset해 연결·보안 상태를 분리했다. 초기
bondable fixture는 17회 성공 뒤 재시도에서 보안 상태가 어긋났으며,
fixture에 `bt_set_bondable(false)`를 적용하고 양쪽 보드 reset을 명시한 뒤
위 clean revision으로 처음부터 각각 20회를 재실행했다. 최종 결과에서
예상 밖 성공·fatal fault·보안 오류는 없었다.

CMSIS-DAP V2의 client COM7과 server COM5는 원시 UID 대신 probe
SHA-256으로 선택했다. client는 각 case의 이미지를 sector flash와
hardware reset으로 올렸다. QoS 이미지의 최초 flash 기록은 commit 전
candidate로 남기되, clean revision에서 다시 생성한 fixture와 사용한
이미지·설정이 byte 단위로 동일함을 확인했다. 서버는 앞선 공개 예제
검증의 동일 이미지가 이미 올라간 상태였고, 매 회차 hardware reset했다.

| 항목 | SHA-256 |
| --- | --- |
| Arduino server HEX | `53cfdadc8de7276ac6fb00def4dc1e6c61a5b5097d48e6f3d4026b46048fd8c8` |
| unsupported codec client HEX | `f316603bff3fc2069ed52f62ca3886669815e0041e3bc655b78639006b3191c0` |
| invalid QoS client HEX | `0625792ecc89ff5634a127684e389f91cde09a91df25599bb8e853062955d12c` |
| client `.config` | `2b05c55266947e7415ebd663bd5f7255730bc42962167341d22e9ee3caa06df9` |
| server `.config` | `580f72c5838e0622658c2ac12b1d2cdc849d943c4e64893373fc05f65a7530b4` |

[codec 회차](evidence/m31-w03-bap-remote-negative-db995970/codec-exact.json),
[QoS 회차](evidence/m31-w03-bap-remote-negative-db995970/qos-exact.json),
[fixture 원본·생성 해시](evidence/m31-w03-bap-remote-negative-db995970/fixture-prepare.json),
[build 요약](evidence/m31-w03-bap-remote-negative-db995970/build-summary.json),
[전체 manifest](evidence/m31-w03-bap-remote-negative-db995970/manifest.json)에
설정·이미지·build log·flash 기록의 무결성 증거를 보존한다. 원시 probe UID는
기록하지 않았다.

이는 원격 ASCS의 **unsupported codec과 invalid QoS** 거부만 입증한다.
원격 잘못된 ASE 상태 제어와 Arduino 양방향 stream은 잔여다. W03-02 전체
`functional_hil`과 M31-W03 완료 상태는 `NOT_RUN`으로 유지한다.
