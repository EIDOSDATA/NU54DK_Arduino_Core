# v0.4.1 설치기 유지보수 릴리스

`v0.4.1`은 공개 `v0.4.0`의 기능·지원 경계를 유지하면서 prerequisite 설치 로그 판정을
교정하는 patch release다. 프로젝트 소유자는 2026-09-12에 새 버전 공개와 stable index를
`0.4.1` 단독으로 전환하고, 이전 모든 버전의 지원을 종료하도록 명시적으로 요청했다.

| 단계 | 상태 | 완료 조건 |
| --- | --- | --- |
| P41-01 범위·기준선 | 완료 | clean exact source·board·기존 공개 자산과 변경 범위 기록 |
| P41-02 코드·정책·문서 | 완료 | 설치기 수정·0.4.1 사용자 문서·이전 버전 지원 종료 표현 일치 |
| P41-03 로컬·원격 gate | 진행 중 | Host·package·문서·inventory·CI와 재현 빌드 PASS |
| P41-04 비공개 package | 미착수 | 0.4.1 archive/sidecar 이중 생성·byte 재현·단독 index 검증 |
| P41-05 공개 | 미착수 | exact 승인 source에 tag·Release 생성, asset byte 재검증 후 index 게시 |
| P41-06 공개 URL 설치 | 미착수 | index에 0.4.1만 노출, 격리 설치·예제 30/30 compile |
| P41-07 마감 | 미착수 | 영구 identity·문서·기록 갱신, commit·push·exact CI 확인 |

## 지원·보존 계약

- 일반 사용자가 설치·지원받는 버전은 `0.4.1` 하나로 제한한다.
- `0.4.0` 이하 stable·RC·preview는 지원·catalog 공급을 종료한다.
- 과거 tag·GitHub Release·asset과 당시 검증 기록은 이력·재현 근거로 보존하며 덮어쓰지 않는다.
- v0.4.1의 Arduino API·보드 기능·QDEC 및 비보증 경계는 v0.4.0과 같다.
- 이번 patch의 runtime 변경은 `tools/nu54-prerequisites/install-nordic.ps1`과 관련 설치 문서·검사다.
  SDK·Toolchain pin, board gitlink, firmware API와 HIL image는 변경하지 않는다.

진행 결과와 exact identity는 [129번 기록](<04_검증 기록/129_v0.4.1_설치기_유지보수_릴리스.md>)에 남긴다.
