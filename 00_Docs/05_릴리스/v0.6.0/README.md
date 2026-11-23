# v0.6.0 릴리스 준비 문서 — 미공개

기준일: 2026-11-16. 이 문서는 **HOST-W08의 문서 선행 정리 결과**이며 공개 설치 안내가 아니다.
현재 stable은 [v0.5.0](../v0.5.0/README.md)이고 공개 Boards Manager URL은 그 버전을 제공한다.
Git commit·push만으로 v0.6.0 패키지가 배포되지는 않는다.

| 구분 | 현재 값 |
| --- | --- |
| 제품 검증 source | C11 `d304f369c0d3ebbac35c3bf0ef3b7b2887f40dfa` |
| 비공개 검증 package | `0.6.0-rc.1`; 최종 정식 source·version·배포 plan은 미확정 |
| SDK | NCS 3.4.0 고정; 3.4.1 전환은 v0.7.0 |
| 개발 단계 | M33-W07, HOST-W08 문서 준비 완료·최종 gate 미완료 |
| 완료 분모 | M33 수락6/8·기술5/8, Host6/8, 지원 목표 검증3/5 |
| Mac 실기 | macOS26.7.3 준비 중 Gatekeeper에서 차단. macOS26·27 실기 `NOT_RUN`, software CI PASS. [334번](<../../04_검증 기록/334_HOST_W07_C11_macOS_26_실기_시작과_Gatekeeper_차단.md>) |

## 읽는 순서

- [지원표](SUPPORT_MATRIX.md): 실제 검증 환경, source별 근거와 미실행 항목.
- [Release notes 초안](RELEASE_NOTES.md): 개발 기능과 사용자 수락 예외.
- [Migration](MIGRATION.md): profile·설치 전이와 기존 stable 복귀 범위.
- [Testing](TESTING.md): 기존 기준선 재사용과 제한 검증 원칙.
- [Troubleshooting](TROUBLESHOOTING.md): Host별 설치·USB·IDE 문제 수집.
- [Known issues](KNOWN_ISSUES.md): 해결된 실패, 수락 예외와 미검증 범위.
- [릴리스 체크리스트](RELEASE_CHECKLIST.md): 현재 문서 완료부터 공개 설치 확인까지의 순서.

## 비공개 후보 설치

검증에는 [Host RC1 절차](<../../02_빌드 설계/15_Host_RC1_실기_도구와_증거_절차.md>)의
고정 kit·별도 work root를 사용한다. `START.cmd` 또는 `START.sh`로 `plan`을 확인한 뒤
`install-sdk`·`lifecycle`·대표 `build`를 진행한다. 실제 인자는 해당 절차와 kit의 도움말을 따른다.
실패 attempt를 덮어쓰거나 다른 후보 kit에 파일을 복사하지 않는다.

macOS용 C11 kit는 [331번](<../../04_검증 기록/331_HOST_W07_C11_macOS_26_27_호환성.md>)에
원본 SHA-256과 Windows 보존 위치가 있다. Mac으로 이동할 때는 [Mac 인계](../../MAC_HANDOFF.md)의 전달 묶음·복구 절차와 [작업지시문](../../MAC_START_PROMPT.txt)을 사용한다. Mac 확보 전에는 장치 단계를 실행하지 않는다.
예정 공개 URL·정식 archive hash는 최종 plan에 고정해 승인받고, 실제 게시·다운로드 확인은 승인 뒤 수행한다.
현재 이 문서에는 미확정 URL을 만들지 않는다.

문서 선행 정리의 판정과 보존 감사는 [332번](<../../04_검증 기록/332_HOST_W08_문서_지원표_선행_정리.md>)을 따른다.
