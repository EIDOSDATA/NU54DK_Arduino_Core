# NU54DK Arduino Core v0.3.0 stable 공개 전 인계

| 항목 | 내용 |
| --- | --- |
| 문서 ID | RELEASE-v0.3.0-HANDOFF-001 |
| 대상 버전 | `v0.3.0` |
| 현재 상태 | **소스·패키징 메타데이터 준비 / 공개 전** |
| 현재 공개 stable | `v0.2.0` |
| 승격 근거 | 공개 `v0.3.0-rc.3` |
| 작성자 | Quantum / NUCODE |

이 디렉터리는 다른 Windows PC에서 stable 검증과 공개를 이어가기 위한 인계 기준이다. 현재
`platform.txt`와 패키징 허용목록은 `0.3.0`을 인식하지만, `v0.3.0` tag·GitHub Release·stable
index 항목은 아직 존재하지 않는다. 일반 사용자는 공개가 끝날 때까지 `v0.2.0` stable 또는
별도 RC index의 `v0.3.0-rc.3`을 사용해야 한다.

## 공개 전 필수 순서

1. 인계 commit과 board submodule identity 확인
2. host/software/reproducible gate PASS
3. `0.3.0` package 두 번 독립 생성 및 byte 일치 확인
4. RC3와 stable의 version-independent runtime payload 일치 확인
5. 격리 Windows Boards Manager 수명주기와 29/29 예제 compile
6. 설치본 NU54DK pyOCD Upload
7. exact commit annotated tag와 stable Release 생성
8. root stable index 갱신 및 익명 공개 URL 재검증
9. 공개 identity를 패키징 도구와 검증 기록에 고정

세부 RC3 근거와 중단 사유는
[M22 RC3 검증·인계 기록](<../../04_검증 기록/31_M22_v0.3.0_rc3_검증과_stable_인계.md>)을
따른다. 공개 전에는 RC3 문서의 Release notes, Known issues, Migration과 Troubleshooting을
stable 이름으로 복사해 확정하지 않는다. 실제 stable asset identity가 생긴 뒤 최종 문서를
작성해 역사적 RC 문서와 구분한다.
