# M31-W02 공개 BIS 시각 동기 사용자 SDU 실기

clean Core `7e4c0109d0f292c32257a3f0dfeb5bbbb5353da9`에서 Arduino
`BISTimeSource`·`BISTimeReceiver`를 각각 빌드하고 NU54DK 두 대에서 실행했다.
[manifest](evidence/m31-w02-public-bis-time-7e4c0109/manifest.json)는 예제
Kconfig·HEX·runner의 SHA-256과 익명 CMSIS-DAP V2 mapping을 고정한다.

두 `.ino`는 사용자 SDU 생성·검증, 시작·종료, 실패 처리를 직접 보여 준다.
Source는 첫 SDU를 `RawBis::sendFrame()`으로 보내 HCI 송신 완료 시각을 얻고,
이후 99개는 `sendFrameAt()`으로 보낸다. Receiver는 `readFrame()`으로 받은
payload·순서·controller 시각의 유효성과 단조 증가를 검사한다. Zephyr
BIG·HCI data path·buffer·callback 구현은 library `.cpp`가 소유한다.

[실행 원본](evidence/m31-w02-public-bis-time-7e4c0109/time-positive.json)은
source·receiver **20/20회**, 2,000/2,000 SDU, 허용 누락 **0개**, payload·시각
오류 **0개**다. Source의 매 회차 99개 명시 시각 송신과 HCI 시작·끝 시각 증가,
receiver의 매 회차 100개 유효·단조 시각을 확인했다. 송신 image는 FLASH
228,216 byte/RAM 107,389 byte, 수신 image는 FLASH 195,888 byte/RAM
106,484 byte였다.

개발 후보에서 HCI sequence를 사용자 payload 번호와 같다고 둔 검사 때문에
[첫 실패](evidence/m31-w02-public-bis-time-7e4c0109/diagnostic-sequence-assumption.json)가
발생했다. HCI 값의 실제 계약인 단조 증가 검사로 고친 뒤, 처음 동기화한 receiver가
첫 세 frame을 놓친 [후보 실패](evidence/m31-w02-public-bis-time-7e4c0109/diagnostic-startup-loss.json)를
확인했다. 송신 시작 여유를 늘려 [3/3 후보](evidence/m31-w02-public-bis-time-7e4c0109/diagnostic-candidate-pass.json)를
통과시켰다. 세 후보는 clean 판정에 합산하지 않고 원본으로 보존했다.

공개 시각 동기 두 예제만 닫았다. CIS→BIS bridge·peer·receiver 세 예제의 사용자
payload API와 새 exact HIL은 남아 있으므로 W02와 M31 전체는 진행 중이다.
