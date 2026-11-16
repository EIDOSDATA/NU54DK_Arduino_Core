# v0.6.0 릴리스까지 남은 순서

기준일: 2026-11-16. 현재 **M33-W07 / HOST-W08 문서 준비 완료**다.
HOST-W07·HOST-W08 최종 gate와 M33-W07은 열려 있고 M33-W08 공개는 미착수다.
Host6/8·지원 목표 검증3/5·M33 수락6/8/기술5/8을 유지한다.

| 순서 | 작업 | 현재 상태·종료 조건 |
| --- | --- | --- |
| 1 | HOST-W08 문서·지원표 선행 정리 | **완료**: 설치·migration·검증·제한·문제 해결·source 색인 작성. 문서 commit의 CI는 실제 결과로 별도 기록 |
| 2 | Mac 지원 gate 처리 | **대기**: 현재 다섯 OS 목표에서는 Mac26·27의 장치·IDE 실기가 필요. 장비가 없으므로 `NOT_RUN` 유지. 지원 범위를 별도로 변경하는 결정은 아직 없음 |
| 3 | 최종 배포 후보 고정 | **미완료**: 공개할 source·제품 식별자·version·세 Host 자산·index plan·license/provenance·hash 정합화, 독립 package 재현과 실제 변경 영향 검증. 기존 C5/C10/C11 원본 보존 |
| 4 | HOST-W07·HOST-W08 및 M33-W07 최종 마감 | **미완료**: 공개 필수 행과 package/install case를 exact 증거에 연결하고 지원표·release notes·생성 readiness를 최종 정합화. 전체204는 실제 영향 없으면 반복하지 않음 |
| 5 | M33-W08 공개 승인 | **미승인**: 검토 가능한 exact source·지원 범위·배포 plan·자산 hash를 준비한 뒤 소유자가 승인 |
| 6 | 승인된 공개 실행 | **미실행**: 승인 범위의 tag·Release·asset·stable index 게시. 기존 공개 자산 보존 |
| 7 | 공개 URL 설치·최종 인계 | **미실행**: 실제 다운로드 hash·격리 설치·발견·대표 build/upload/runtime·수명주기를 배정 범위로 확인하고 지원 문서·인계 마감 |
| 8 | 후속 SDK 전환 | v0.6.0 마감 뒤 [v0.7.0 SDK-W01~W06](../../TODO_v0.7.0.md). #29 분석은 유예 상태이며 이번 릴리스 준비에 재삽입하지 않음 |

2번의 Mac 실기가 없다고 문서·최종 후보 준비 전체를 중단할 필요는 없다. 다만 미충족 필수 행을
PASS 또는 수락으로 바꾸지 않고, 다섯 OS 정식 지원과 공개 완료를 선언하지 않는다.
사용자가 현재 직접 수행할 작업은 없고 Mac 환경을 확보할 때 장치 검증을 재개한다.

이 체크리스트는 공개 승인이 아니다. 검증/수락/PASS의 구분은 [Testing](TESTING.md)과
[Known issues](KNOWN_ISSUES.md), 현행 판정은 [Host 원장](../../../variants/nu54dk/host-readiness.json)을 따른다.
