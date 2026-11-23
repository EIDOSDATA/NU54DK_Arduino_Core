# v0.6.0 릴리스까지 남은 순서

기준일은 2026-11-24다. 현재 **M33-W07 / HOST-W07 배정 완료 / HOST-W08 문서 준비 완료**다.
HOST-W08 최종 gate와 M33-W07은 열려 있고 M33-W08 공개는 미착수다.
Host7/8·지원 목표 검증5/5·M33 수락6/8/기술5/8을 유지한다.

| 순서 | 작업 | 현재 상태·종료 조건 |
| --- | --- | --- |
| 1 | HOST-W08 문서·지원표 선행 정리 | **완료**: 설치·migration·검증·제한·문제 해결·source 색인 작성. 문서 commit의 CI는 실제 결과로 별도 기록 |
| 2 | Mac 배정 실기 | **완료**. macOS26·27의 C11 USB·debug·UART·물리 재연결·Arduino IDE Verify를 기록했다. [337번](<../../04_검증 기록/337_HOST_W07_C11_macOS_27_실기_검증과_마감.md>) |
| 3 | 최종 배포 후보 고정 | **미완료**. C12 비공개 후보에서 C11 IDE Upload 오류를 교정하고 macOS27 정상 Upload·Blink 동작을 확인했다. 공개할 source·제품 식별자·version·세 Host 자산·index plan·license/provenance·hash의 고정과 최종 패키지 재현·변경 영향 검증이 남았다. [338번](<../../04_검증 기록/338_HOST_W07_macOS_27_Arduino_IDE_Upload_교정.md>) |
| 4 | HOST-W08 및 M33-W07 최종 마감 | **미완료**: 공개 필수 행과 package/install case를 exact 증거에 연결하고 지원표·release notes·생성 readiness를 최종 정합화. 전체204는 실제 영향 없으면 반복하지 않음 |
| 5 | M33-W08 공개 승인 | **미승인**: 검토 가능한 exact source·지원 범위·배포 plan·자산 hash를 준비한 뒤 소유자가 승인 |
| 6 | 승인된 공개 실행 | **미실행**: 승인 범위의 tag·Release·asset·stable index 게시. 기존 공개 자산 보존 |
| 7 | 공개 URL 설치·최종 인계 | **미실행**: 실제 다운로드 hash·격리 설치·발견·대표 build/upload/runtime·수명주기를 배정 범위로 확인하고 지원 문서·인계 마감 |
| 8 | 후속 SDK 전환 | v0.6.0 마감 뒤 [v0.7.0 SDK-W01~W06](../../TODO_v0.7.0.md). #29 분석은 유예 상태이며 이번 릴리스 준비에 재삽입하지 않음 |

완료한 macOS26과 Ubuntu24.04는 사용자 지시에 따라 반복하지 않는다. 최종 후보의 관련 변경 영향 검증은 최신 행인 macOS27과 Ubuntu26.04/WSL2에서 진행한다.

이 체크리스트는 공개 승인이 아니다. 검증/수락/PASS의 구분은 [Testing](TESTING.md)과
[Known issues](KNOWN_ISSUES.md), 현행 판정은 [Host 원장](../../../variants/nu54dk/host-readiness.json)을 따른다.
