# M31-W02 공개 암호화 BIS 사용자 SDU와 잘못된 Code 거부

clean Core `1bb127b4d211c0a7b85da16cb3de8dc8e130b4dc`에서 Arduino
`BISEncryptedSource`·`BISEncryptedReceiver`를 각각 빌드해 NU54DK 두 대에서 실행했다.
[manifest](evidence/m31-w02-public-bis-encrypted-1bb127b4/manifest.json)는 예제·
Kconfig·HEX·runner의 SHA-256, 익명 CMSIS-DAP V2 mapping, build 수치와
원본 실행 결과를 묶는다.

양 `.ino`는 서로 일치하는 16-byte session ID와 별도의 16-byte Broadcast Code를
명시하고 `RawBis::begin()`에 전달한다. Source는 사용자가 만든 8-byte SDU를
`sendFrame()`으로 보내고 Receiver는 `readFrame()`으로 payload·순서·손실을
검사한다. Zephyr BIG 암호화 인자·PA sync·HCI data path·buffer는 library
`.cpp` 내부에 있다. 예제 Code는 두 보드의 동작을 보여 주는 값이므로 실제 사용자는
양쪽에 동일한 별도 Code를 설정해야 한다.

[양성 원본](evidence/m31-w02-public-bis-encrypted-1bb127b4/encrypted-positive.json)은
송신·수신 **20/20회**, 2,000/2,000 SDU, 누락·손상·중복·순서 오류·예상 밖
해제 **0개**다. 송신 image FLASH 226,968 byte/RAM 107,354 byte,
수신 image FLASH 195,992 byte/RAM 106,483 byte였다.

별도 공개 API 시험 fixture는 첫 byte만 다른 Code로 같은 광고에 동기화했다.
[잘못된 Code 원본](evidence/m31-w02-public-bis-encrypted-1bb127b4/wrong-code-negative.json)에서
source는 100개를 송신했고 receiver는 MIC 오류 `-61`로 거부했으며 유효 사용자
SDU **0개**, 자원 반환 1회를 확인했다. 이 시험은 **잘못된 Code 거부**에 해당하며,
같은 image 안에서 올바른 Code로 다시 연결하는 시험으로 확대하지 않는다.
직전 [고정 시험 backend의 복구 증거](evidence/m31-w02-arduino-e6ae812e/closure-audit.json)는
별도 원본으로 보존한다.

암호화 API를 추가한 뒤 일반 BIS도 새 source에서 재빌드해
[2/2회·200/200 SDU 회귀](evidence/m31-w02-public-bis-encrypted-1bb127b4/plain-regression.json)를
통과했다. 개발 후보 두 결과는 manifest에 별도 진단으로 보관하고 clean PASS에
합산하지 않았다.

이 기록은 공개 암호화 BIS source/receiver 두 예제와 잘못된 Code의 SDU 비유출
범위를 닫는다. 이후 같은 image에서 올바른 Code로 복구하는 공개 API 실기는
[197번](197_M31_W02_공개_API_암호화_BIS_오류_후_복구.md)에 별도로 기록했다.
W02와 M31 전체는 아직 진행 중이다.
