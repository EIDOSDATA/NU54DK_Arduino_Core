# HOST-W05 native 마감과 HOST-W06 package 착수

기록일: 2026-11-10. Host 완료5/8, 현재 HOST-W06 진행 중.

W05 완료 source는 H5 `2dd1455e771afdeab5a599874bf634659bf3b643`이다.
[native CI42759627688](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/42759627688)는
세 OS 모두 실제 SDK 설치·저장 상태 재검증을 통과했다. 공식 asset·SDK/Zephyr revision·bundle과
실제 도구 실행 결과, 원문 로그와 artifact ZIP 세 개의 SHA-256·크기·source binding을 대조했다.

| 실제 Host | 보고한 unit | PASS | 조건부 SKIP | SDK 설치·재검증 |
| --- | --- | --- | --- | --- |
| Windows x86-64 | 66 | 61 | 5 | PASS |
| Ubuntu AMD64 | 66 | 66 | 0 | PASS |
| macOS Apple Silicon | 66 | 65 | 1 | PASS |

Windows의 POSIX mode·읽기 전용·FIFO·lock-file 검사4개와 case-sensitive 파일 이름1개는 SKIP이다.
macOS는 case만 다른 두 파일을 분리하지 않는 filesystem의 해당1개만 SKIP이며 Ubuntu에서 실제 통과했다.
공백·한글·260자 초과 경로, Unicode alias·symlink, 다른 TMP의 두 process 배타성·timeout·종료 후 회수와
캐시 소유권·권한의 OS별 실제 의미를 검사했다. SKIP을 PASS로 올리지 않았다.

같은 H5의 [공통 software CI42759630820](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/42759630820)도
실제9/9 성공·SKIP0으로 종료했다. 전체 Host·PowerShell 계약, core semantic runtime, package 재현성,
문서·CI 계약·예제 발견과 6개 feature profile 대표 target build를 포함한다. H2/H4 실적을 H5로 옮기지 않았다.
H5의 자동 [build-only CI42759627539](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/42759627539)는
이 마감 시점에 별도 실행 중이며 성공을 미리 기록하지 않는다. 이 실행도 S19 HIL 실적에 합산하지 않는다.

비공개 native audit와 완료 receipt는 `D:/w06/control/host-w05-h5-native-audit-20261110.json`,
`D:/w06/control/host-w05-h5-closure-20261110.json`이다. 로컬 초기 실패·교정과 전체 회귀 시점의
byte freeze 범위는 [314번](314_HOST_W05_경로_cache_lock_교정과_native_검증.md)에 그대로 보존한다.

W06은 초기 설치 Python의 순환 의존성, native package의 pin hash·OS별 bundle map, 초기 runtime
의존성과 동일 backend를 부르는 post-install/recipe부터 교정한다. 이후 세 OS의 실제 Boards Manager
격리 설치·전체204개 공개 예제 발견·권장 profile compile과 target artifact 비교를 수행한다.
역할 metadata372개를 독립 compile372회로 부풀리지 않는다. W06 구현·검증은 아직 완료되지 않았다.

S19의 실제 PASS46 + 명시 수락 #29·40·44와 원형 FAIL은 보존한다. #29 원인 분석·새 HIL은 수행하지 않았다.
완료 TODO6개와 과거 source별 판정은 동결한다. w06 PAUSED 요청을 유지하며 예약작업을 생성하거나
재활성화하지 않는다. 추가 OS의 실제 USB·serial·debug·lifecycle은 RC1 최종 사용자 gate `NOT_RUN`이며
Host 전체8/8·정식 지원·공개 완료로 표시하지 않는다.
