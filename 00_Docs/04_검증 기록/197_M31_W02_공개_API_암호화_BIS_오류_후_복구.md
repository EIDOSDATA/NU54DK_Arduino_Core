# M31-W02 공개 API 암호화 BIS 오류 후 복구

> **역사 기록 · 정식 공개 후 안내:** 본문의 버전·진행률·다음 작업은 해당 실행 당시 상태다.
> 현재 설치·지원 버전은 [v0.5.0](<../05_릴리스/v0.5.0/README.md>)이며 개발 기준은 `main`이다.
> 완료된 main 통합·RC 브랜치 정리와 공개 결과는 [274번](274_v0.5.0_정식_릴리스_승인과_공개.md),
> 후속 작업은 [HANDOFF](../HANDOFF.md)를 따른다. 당시 source·수치·PASS/FAIL/HOLD/NOT RUN은 보존한다.

clean Core `54c90bacf730aad959262b713e6e83044a2edb88`에서 공개
`BISEncryptedSource.ino`와 공개 `RawBis` API만 쓰는 전용 receiver fixture를
각각 Arduino CLI로 빌드했다. 두 NU54DK에 CMSIS-DAP V2 sector flash·hardware
reset을 적용하고 VCOM 원본을 수집했다. [manifest](evidence/m31-w02-public-bis-recovery-54c90bac/manifest.json)는
source·config·runner·image와 증거의 SHA-256을 묶는다.

Receiver는 같은 firmware image에서 먼저 첫 byte가 다른 Broadcast Code를
전달했다. [clean 원본](evidence/m31-w02-public-bis-recovery-54c90bac/recovery-positive.json)은
MIC 거부 `-61`, 유효 SDU 노출 **0**, BIG 정지·자원 반환 **1회**를 기록한다.
이후 올바른 Code로 `RawBis::begin()`을 다시 호출하고 사용자 payload의 내용·
순서·개수를 검사해 **100/100 SDU**, 누락·손상·중복 **0**으로 마쳤다.
Source는 복구 전후 2개 session에서 각각 100개를 송신했다. Receiver의 첫
재동기화 시도는 이미 진행 중이던 session 중간에 합류해 27개를 관측하고
정상 종료 후 재시도했으며, 두 번째 시도에서 완전한 100개를 받았다.
예상 밖 오류 줄은 0개다. Source image는 FLASH 226,968 byte/RAM 107,354
byte, receiver fixture는 196,220/106,488 byte였다.

[개발 후보 원본](evidence/m31-w02-public-bis-recovery-54c90bac/diagnostic-candidate.json)은
clean 실기 분모에 합산하지 않는다. 이 결과는 공개 API의 **오류 후 같은 image
복구**를 확인하며, 사용자에게 보이는 암호화 BIS 예제 자체의 20회 payload
검증은 [194번](194_M31_W02_공개_암호화_BIS_사용자_SDU_실기.md)에 기록돼 있다.
Sync loss·재시작 회귀와 설치 package 전수 build는 W02 잔여다.
