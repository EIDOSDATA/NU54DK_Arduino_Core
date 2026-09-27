# M31-W05 미암호화 RAS Features 읽기 거부 20회

공개 Arduino `RasReflector`와 [내부 미암호화 GATT client fixture](../../tests/hil/nu54dk/fixtures/RasInsecureRead/RasInsecureRead.ino)를
NU54DK 두 대에서 실행했다. Client는 `CONFIG_BT_SMP=n`이며 보안 요청을 하지 않는다.
광고의 Ranging UUID `0x185B`로 연결하고 공개 `BLEClient` API로
Ranging Features characteristic `0x2C14`를 찾은 뒤 읽는다.

runner revision `da5803415519823cbe489ed1616ee4889ef11a9d`의 clean source에서
client를 빌드했다. FLASH 332364 B, RAM 191364 B, HEX SHA-256은
`53a9d324d4a075295ffb3b3b99902750fb5f9940a8ea638606ba06c766535aff`이다.
상대 Arduino reflector image SHA-256은
`cc0919207c424ee52cd2d22aaabbbe98d668c9f8e493a88d74a6c67b2202500b`이다.
CMSIS-DAP V2 역할을 SHA-256으로 고정하고 DP/AP register identity를 확인했으며,
두 image를 sector flash한 뒤 **client만 hardware reset하여 별개 ACL 20회**를 만들었다.
원본 probe UID와 Bluetooth 주소는 저장하지 않았다.

[exact 실행 결과](evidence/m31-w05-insecure-ras-da580341/insecure-read-20-exact.json)는
20회 모두 Ranging Features 탐색 후 `ATT 15`(Insufficient Encryption)로
읽기를 거부했다. 허용된 읽기 0회, reflector의 `secure L2` 상태 출력 0회,
전체 112.938초였다. [image·build·해시 manifest](evidence/m31-w05-insecure-ras-da580341/insecure-read-manifest.json)를
함께 보존했다. 이는 **미암호화 ACL에서 RAS Features를 읽을 수 없음**을 입증한다.
RAS 전체 속성의 권한과 wrong-key, CS 절차 자체의 미인증 거부까지 입증한 것은 아니다.

처음에는 한 ACL에서 읽기를 연속 20회 시도했다. 그
[개발용 실행](evidence/m31-w05-insecure-ras-da580341/candidate-repeat-read-fail.json)은
`ATT 15` 4회 뒤 연결 상태가 바뀌고 fixture counter가 1부터 다시 시작해
20회 연속 기준에 실패했다. 그 뒤 CMSIS-DAP V2로 읽은
[CPU register](evidence/m31-w05-insecure-ras-da580341/candidate-after-fail-registers.json)는
sleep 상태, CFSR/HFSR 0이었다. reset reason register 읽기는 SWD access fault로
성공하지 못했다. 따라서 반복 중단을 CPU fault나 보안 정책으로 단정하지 않는다.
이 경로의 정확한 원인과 정상 peer의 flash 직후 간헐 연결 중단은 W05 잔여다.
