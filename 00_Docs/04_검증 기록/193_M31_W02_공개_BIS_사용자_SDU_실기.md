# M31-W02 공개 BIS 사용자 SDU 두 역할 실기

clean Core `f1c5ea60493ed79829885887d67dd5693c7b9c87`에서 Arduino
`BISSource`와 `BISReceiver`를 BLE feature set으로 각각 빌드하고 두 NU54DK에
sector flash했다. [원본 manifest](evidence/m31-w02-public-bis-f1c5ea60/manifest.json)에
sketch·Kconfig·image·runner SHA-256, 익명 CMSIS-DAP V2 mapping, 빌드 사용량과
[20회 실기 원본](evidence/m31-w02-public-bis-f1c5ea60/public-bis-exact.json)을 결합했다.

두 `.ino`는 공유 16-byte session ID를 설정하고 사용자가 만든 8-byte SDU를
`RawBis::sendFrame()`으로 보내거나 `RawBis::readFrame()`으로 읽어 payload와 순서를
검사한다. Zephyr 광고·periodic sync·BIG·HCI buffer와 callback은 library `.cpp`가
소유한다. 방송 송신에는 수신 확인이 없으므로 수신 예제는 packet 손실과 손상을 별도로
센다. 공개 `Error::peer_stopped`는 송신자가 BIG을 정상 종료했을 때 남은 수신량을
판정하게 하고, 예상 밖 native 오류는 `transport_failure`로 남긴다.

실기는 source와 receiver 각각 **20/20회** 종료·재시작했고 source 2,000/2,000,
receiver **1,999/2,000** 유효 SDU를 확인했다. 매 회차는 최소 99/100개이며,
누락 1개, payload 손상·중복·순서 오류·비정상 종료는 0개다. 이 수치는
[M31-ISO-01:bis 계약](../TODO_M31.md)의 회차별 최소 99개 기준을 만족한다.
Source image는 FLASH 226,860 byte/RAM 107,338 byte, receiver는 FLASH 195,868
byte/RAM 106,467 byte였다. 양 image의 Serial revision은 clean source와 일치한다.

이전 정확한 실행에서 20/20 송수신을 끝냈어도 중간 native `-19`를 무조건 오류로
처리해 FAIL했다. 당시 수신 프레임 수를 출력하지 않아 그 한 회차의 손실 수는
확정할 수 없다. 별도 진단에서는 동시 보드 reset이 이전 BIG 세션을 최종 boot
뒤에 섞는 현상을 확인해 reset 순서를 고쳤고, 20회 후보 실기에서
1,997/2,000·회차별 99개 이상을 확인했다. 모든 실패·후보 원본은 manifest에
`diagnostics_excluded`로 남기고 위 clean 실기 PASS에 합산하지 않았다.

이 결과는 **비암호화 BIS source/receiver 두 공개 예제**의 사용자 데이터 경로만
닫는다. 암호화·timestamp·CIS→BIS 세 보드의 공개 예제 7개는 여전히 고정 시험
backend 중심이다. 전체 W02와 M31은 진행 중이며, 시험용 무선 HIL의 이전 PASS를
공개 Arduino 예제 완료로 대신하지 않는다.

후속 [194번 암호화 BIS 실기](194_M31_W02_공개_암호화_BIS_사용자_SDU_실기.md)에서
암호화 두 역할을 더 전환해 현재 남은 공개 ISO 예제는 **5개**다.
