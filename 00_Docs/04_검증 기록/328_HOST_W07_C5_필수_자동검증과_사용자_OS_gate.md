# HOST-W07 C5 필수 자동 검증과 사용자 OS gate

2026-11-15 현재 **Host6/8·HOST-W07 준비 완료·사용자 OS 실기 대기**다. 제품 검증 source는
`5ee7c10368b554ca23d68f8f82e39308b91df6de`(C5)이며 이후 문서 기록 commit과 구분한다. 같은 C5의 필수 자동 검증과
Windows11 조건부 J-Link 대표 실기를 마감했다. OS7행·IDE·물리 USB·기본 CMSIS-DAP 실기는
미완료다. M33-W07·HOST-W08·정식 다중 OS 지원과 공개를 완료로 표시하지 않는다.

| 범위 | 같은 C5의 실제 결과 |
| --- | --- |
| producer·kit | 독립 archive2회 byte 동일, core archive SHA `9e392dcaf6b314362d07061634a345b11718074179cc6e49d3f422dcda933e15`. kit 원형220파일, manifest SHA `a6690c66c90da263981d1f972810f82bd0c6efc08af351ac5614266658512f34` |
| SDK·수명주기 | NCS3.4.0·bundle dcbdc366a1·nrfutil8.2.1·manager1.16.1. SDK `b939ed/exit0`, lifecycle `fd0091/exit0`. 설치960파일·24 library·204예제, 사용자 데이터·공유 SDK 보존 |
| 대표 빌드 | `f519d8/exit0`:4 cold·4 warm. 16 산출물·실제 flash 전제4종과 설치 byte 독립 검사 PASS |
| Windows 빌드 | C5 첫 실행 `build-20261114T053737401804Z`은 146 cold·2 warm 완료 후 중단. 재개 실행 `build-20261114T202944997266Z`은 58 cold·2 warm·negative9 PASS (`native-pid13264/exit0`). 같은 SDK 검증 결과와 826 실제 산출물·208 복사 manifest를 구간별로 대조해 204개 범위를 확인했다. 첫 실행의 종료 코드는 미확인이다. |
| 대표 실기 | fresh a001 `81d7b4/exit0`:identity A/B, 잘못된 probe hash 사전 거부, Blink ELF/GPIO·debug, Serial2 open/close·fresh nonce6, NUS 양방향 fresh nonce2, 양쪽 Blink 정리. 11단계+정리2·child0·probe/port close |
| exact CI | software43561471549 9, prerequisites43561469023 3, build-only43561475997 6, native43561469020 30. 같은 C5/attempt1의48 job success·skip0. 원형 raw log48·ZIP57 보존 |
| native 독립 감사 | 같은 run/attempt/source의24 worker 실제 산출물·profile·서명·negative·source checkpoint 대조. OS별204 positive·9 negative, 전체612 positive·27 negative, 3OS의204 image 비교 PASS |
| 비공개 전달 kit | 원형220+manifest=221항목을 ZIP 내부 byte 전수 검사. START.sh POSIX0755. 실행 출력·사용자 signing key 제외. 공개 tag·Release 없음 |

C5는 negative profile 검증 예산을120초에서 유한300초로 맞춘 검증기 교정이다. 실제 개발
진단에서는 예상 거부에172.718초가 걸렸고 nonzero exit·정확한 profile marker·성공 산출물 없음·
child0을 확인했다. 그 개발 진단은 C4 payload와 미커밋 checker였으므로 최종 C5 실적에 합산하지
않았다. 최종 실적은 위 C5 fresh 실행의 negative9개와 같은-source CI 원형으로 판정했다.
성공 exit·다른 오류·성공 ELF를 거부하는 조건, SDK pin·보안 수준·재시도 횟수는 유지했다.

C4 `85812309fca62b9fa418490becbe7696aa2aa148`의 대표8빌드·실기11 PASS는 C4에 보존한다.
C4 native Windows shard5는 positive25 PASS 후 negative 준비120초 timeout으로 FAIL이었다.
C4 로컬 전체204는 cold37개 완료 후 통제 종료한 `c96af2/exit1`이며 전체 PASS가 아니다.
중단된 C4의 승인 임시 Mesh patch4개는 예상 적용 byte와 대조·보존한 뒤 작업용 SDK의 원래
CRLF byte로 복원했다. 개발 guard FAIL·복원 대조 FAIL도 원형으로 보존했다.

원형 ZIP 수집에서는 전송 중0바이트 표시를 실패로 오판해 수집기만 통제 중단했다.
완료한 원형6개는 다시 받지 않고 유지했으며, 부분 전송과 별도120초 진단의 timeout도
보존했다. 이는 수집 판단 오류이며 제품·CI 시험 FAIL이 아니다. 해당 ZIP 수집 조치는 SDK 빌드·실기에 영향을 주지 않았다. 최종 원형57개는 같은 C5/run/attempt의 크기·digest로 별도 검증했다.

C3의 NUS 실패는 비활성 Generic GAP의 전역 연결 callback이 NUS 소유 연결을 해제한 원인으로
확정했고 C4에서 교정했다. C5는 C4 대비 cores·libraries·templates·tests/hil 입력을 유지했다.
C5 실기의 양방향 nonce로 동작을 다시 확인했으나 W06 #29 원인으로 소급 판정하지 않는다.
SDK Python locator 교정과 제어기의 FICR 주소 치환 오류, 이전 source의 PASS/FAIL은
[326번](326_HOST_W07_C3_전체빌드와_C4_NUS_소유권_교정.md),
[327번](327_HOST_W07_C4_실기_통과와_C5_거부_검증_예산_교정.md)에 source별로 보존한다.

W06 S19는 **실제 PASS46+승인 수락 #29·40·44**로 마감·동결한다. 기존 FAIL은 기술 PASS와
구분해 보존하며 #29 원인 분석은 사용자 지시로 유예한다. C3·C4·C5의 실적과 각 CI run/attempt의 판정은 원형대로 기록한다. 로컬 C5 중단 및 재개 구간도 각각의 증거를 인용한다. W06 build-only CI도 원래 HIL·수락 결과를 변경하지 않는다.

다음은 같은 private kit를 이용한 OS7행의 필수 실기와 IDE·실제 USB 재연결·기본 CMSIS-DAP·
적용 대상 Windows stable0.5 migration이다. 현재 Windows11 Pro/build26300의 완료한 자동 빌드와
조건부 J-Link 실기는 보존하고 필요한 미실행 항목만 보완한다. 다른 OS의 CI를 사용자 실물
PASS로 바꾸지 않는다. 사용자 결과를 검토한 뒤 HOST-W08 지원표·문서와 M33-W07을 마감하고,
M33-W08 공개는 별도 승인으로 진행한다. 자동점검 w06은 PAUSED, 새 예약은0이다.

비공개 kit: `D:\w06\h7c5\NU54-0.6.0-rc.1-C5-private-kit.zip`. SHA-256: `4311f9753fd76d23d04d320c164d33a5e0f96ea51d64b0ff3f4d7d56ab797e11`.
OS tracker: `D:/w06/control/host-w07-c5-user-OS-gates-20261114.json`.
[RC1 실기 절차](<../02_빌드 설계/15_Host_RC1_실기_도구와_증거_절차.md>)와
[현행 Host 원장](../../variants/nu54dk/host-readiness.json)을 따른다.
