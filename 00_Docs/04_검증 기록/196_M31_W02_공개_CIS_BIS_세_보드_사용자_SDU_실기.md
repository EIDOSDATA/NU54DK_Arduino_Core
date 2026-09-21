# M31-W02 공개 CIS→BIS 세 보드 사용자 SDU 실기

clean Core `0d092738b56397d4cdd6b67d30a24be01da705fb`에서 Arduino
`CISToBISPeer`·`CISToBISBridge`·`CISToBISReceiver`를 각각 빌드해 NU54DK
세 대에서 실행했다. [manifest](evidence/m31-w02-public-combined-0d092738/manifest.json)는
각 예제 Kconfig·HEX·runner의 SHA-256과 익명 CMSIS-DAP V2 mapping을 고정한다.

Peer `.ino`가 8-byte 사용자 SDU를 만들어 `RawCis::sendFrame()`으로 보낸다.
Bridge `.ino`는 `RawCis::readFrame()`으로 payload·순서를 검사하고 같은 SDU를
`RawBis::sendFrame()`으로 전달한다. Receiver `.ino`는 `RawBis::readFrame()`으로
payload·손실·순서를 확인한다. CIS/BIG의 HCI path·controller QoS·buffer·callback은
library `.cpp`가 소유하며 세 예제에서 Zephyr API를 직접 호출하지 않는다.

[실행 원본](evidence/m31-w02-public-combined-0d092738/combined-positive.json)은
peer 송신, bridge CIS 수신·BIS 전달, receiver 수신이 각각 **20/20회·
2,000/2,000 SDU**다. Receiver 누락·손상·중복·순서 오류는 0이며 세 역할 모두
20/20회 자원을 반환했다. Bridge image는 FLASH 295,076 byte/RAM 121,600 byte,
peer는 272,544/115,565 byte, receiver는 195,988/106,483 byte였다.

첫 후보는 CIS SDU QoS가 검증된 세 보드 backend와 달라 peer HCI path `-5`와
bridge 연결 해제를 관측했다. [원본](evidence/m31-w02-public-combined-0d092738/diagnostic-qos-failure.json)을
보존하고 두 CIS 방향의 SDU를 검증된 8 byte로 맞췄다. 다음 두 후보에서는 실제
전달이 일어났지만 첫 리셋의 stale BIG와 UART 배너 앞 reset noise가 판정을
방해했다. [배너 진단](evidence/m31-w02-public-combined-0d092738/diagnostic-banner-loss.json)과
[리셋 진단](evidence/m31-w02-public-combined-0d092738/diagnostic-reset-race.json)을
보존했다. Runner는 원본 줄을 유지한 채 revision 접미부를 확인하고, receiver는
첫 부팅에서 이전 BIG 해제를 기다린다. [2/2 후보](evidence/m31-w02-public-combined-0d092738/diagnostic-candidate-pass.json)는
clean 판정에 합산하지 않았다. 동시 CMSIS-DAP reset 시도는 도구 단계에서 실패해
채택하지 않았고, 최종 실기는 순차 reset으로 실행했다.

이 기록은 공개 세 역할의 사용자 payload 전달 범위를 닫는다. 82개 설치 예제 감사는
0건이지만 공개 API의 암호화 오류 후 복구·sync loss·재시작 회귀와 설치 package
전수 확인은 별도로 남아 있으므로 W02 전체 완료 판정은 아직 보류한다.
