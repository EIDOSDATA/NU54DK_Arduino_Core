# M31-W05 Ranging UUID 위장 peer 거부 20회

공개 Arduino `RasInitiator`가 Ranging Service UUID `0x185B`를 광고하지만
실제 GATT Ranging Service가 없는 peer를 거부하는지 시험했다. 시험 peer는
[저장소 내부 fixture](../../tests/hil/nu54dk/fixtures/RasMissingService/RasMissingService.ino)이며
정상 `RasReflector`는 이번 시험에 참여하지 않았다. CMSIS-DAP V2 SHA-256
역할 매핑과 DP/AP register identity를 재확인하고 sector flash·hardware reset만
사용했다. 원본 probe UID와 Bluetooth 주소는 증거에 남기지 않았다.

runner revision은 `add22762f8d2bc1d4bb0de480170dafa590a412d`이며
실기 시작 시 저장소가 clean임을 확인했다. initiator는 앞선
`907ab2f7493cf5f866d7690ffc35fef00da1b192` build의 image SHA-256
`07f7905304c718995f20ebdcccc74751880649554e0c2b1038e48a8e18c8bcdf`이다.
위장 peer의 clean Arduino build는 FLASH 371120 B, RAM 202151 B,
image SHA-256
`b220162f8baf649e97229d97f56c350f78aa26ef0f1ae1dfc5b50f11d3d7e2ef`이다.
[실행 결과](evidence/m31-w05-missing-ras-add22762/missing-service-20-rejections.json)와
[image·build·해시 manifest](evidence/m31-w05-missing-ras-add22762/missing-service-manifest.json)를
보존했다.

두 보드에서 `CS missing service connected` 21회,
`CS initiator failed: -2` 20회, initiator 연결 해제 20회,
위장 peer 연결 해제 19회를 관찰했다. runner는 실패 후 공개 예제의
`d` 명령을 19회 보내고, **새 연결의 보안 시작 → Ranging GATT 서비스 부재**
판정이 다시 발생하는지 순서대로 확인했다. 20회 모두 거부됐고
`CS_RAW`/CS procedure 시작은 0건이었다. 총 24.640초였다.

이는 광고 UUID와 실제 GATT 서비스의 불일치를 공개 API 경로에서
20회 거부하고 명시적 연결 해제로 복구할 수 있음을 보인다. 미인증
접근·wrong-key, Ranging Service가 있으나 속성/권한이 잘못된 peer,
정상 peer의 flash 직후 간헐 중단 원인은 별도 잔여다. 따라서
`M31-CS-01` 및 W05 전체는 아직 완료가 아니다.
미암호화 상태의 실제 RAS Features 읽기는
[별도 20회 시험](180_M31_W05_미암호화_RAS_Features_읽기_거부_20회.md)에서 확인했다.
