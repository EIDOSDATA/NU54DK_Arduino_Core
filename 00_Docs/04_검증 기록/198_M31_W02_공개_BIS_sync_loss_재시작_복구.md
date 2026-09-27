# M31-W02 공개 BIS sync loss·재시작 복구

clean Core `41a56627e3666ededf4fff57d7ee1f2ade425822`의 공개
`BISSource.ino`·`BISReceiver.ino`를 각각 Arduino CLI로 빌드해 NU54DK 두
대에서 실행했다. CMSIS-DAP V2로 receiver가 BIG에 동기화한 뒤 source를
hardware reset하여 세션을 강제로 끊었다. [manifest](evidence/m31-w02-public-bis-sync-loss-41a56627/manifest.json)는
sketch·config·runner·HEX의 SHA-256과 익명 probe mapping을 고정한다.

[clean 원본](evidence/m31-w02-public-bis-sync-loss-41a56627/sync-loss-positive.json)에서
첫 세션은 source reset 후 receiver의 `-67`로 종료됐고, 그때까지 64개를
받았으나 완료 세션으로 수락하지 않았다. Receiver는 자원을 해제하고 다시
스캔·동기화해 새 source session의 사용자 SDU **100/100개**를 받았다.
새 세션의 누락·손상·순서 오류는 0개이며 예상 밖 오류 줄도 0개다. Source와
receiver의 image는 각각 FLASH 226,896/195,904 byte, RAM 107,354/106,483
byte였다. 공개 일반 BIS의 별도 정상 20회 반복은 [193번](193_M31_W02_공개_BIS_사용자_SDU_실기.md)에 있다.

첫 [후보 실패 원본](evidence/m31-w02-public-bis-sync-loss-41a56627/diagnostic-zero-assumption-failure.json)은
동기화 직후 받은 SDU가 항상 0개라는 시험기 가정을 반증했다. 실제로는
source reset 전에 데이터가 도착했고, 중단 세션은 `-67`로 반환됐다. 판정은
중단 세션을 완결로 세지 않고 loss → 재스캔 → 재동기화 → 새 100개 완료를
확인하도록 수정했다. [수정 후보](evidence/m31-w02-public-bis-sync-loss-41a56627/diagnostic-candidate-pass.json)은
clean 결과에 합산하지 않는다. 설치 package 전수 build는 W02 잔여다.
