# 릴리스 문서 안내

**현재 stable·지원 버전은 v0.5.0입니다.** Windows 10/11 x64 대상이며,
이전 stable과 RC는 지원·catalog 공급이 끝난 역사 배포로 보존합니다.

## 현재 사용자 문서

| 목적 | Stable v0.5.0 |
| --- | --- |
| 설치·버전 identity | [시작하기](v0.5.0/README.md) |
| 변경 기능 | [Release notes](v0.5.0/RELEASE_NOTES.md) |
| 이전 버전에서 이동·복귀 | [Migration](v0.5.0/MIGRATION.md) |
| 검증 범위와 기본 시험 | [Testing](v0.5.0/TESTING.md) |
| 설치·compile·upload 문제 | [Troubleshooting](v0.5.0/TROUBLESHOOTING.md) |
| 제한·미검증 범위 | [Known issues](v0.5.0/KNOWN_ISSUES.md) |
| 설치 예제 | 16개 library·113개 |

Stable Boards Manager index:

```text
https://raw.githubusercontent.com/EIDOSDATA/NU54DK_Arduino_Core/main/package_nucode_nu54dk_index.json
```

정식 [GitHub Release](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/releases/tag/v0.5.0)와
공개 검증 결과는 [274번 기록](<../04_검증 기록/274_v0.5.0_정식_릴리스_승인과_공개.md>)을 따릅니다.

## 개발 소스와 다음 릴리스

현재 개발 브랜치는 `main`이고 정식 릴리스 백업은 `Release-0.5.0`입니다. M28~M31과 메모리
최적화 P0~P2, RC2 사용자 경험 교정과 stable 공개를 완료했습니다. 현행 소스의 `0.5.0` 문자열은
릴리스 코어 식별자이며 package 재현 기준은 `v0.5.0` tag와 manifest의 source SHA입니다.

v0.4.1 공개 마감 이후 개발 이력은 단일 v0.5.0 릴리스 commit으로 통합했습니다. RC1/RC2 branch는
삭제하되 공개 tag·Pre-release·자산과 과거 검증 기록은 보존합니다. M32/M33과 Ubuntu/macOS 지원은
후속 제품선이며 버전은 미정입니다. 개발 재개는 [HANDOFF](../HANDOFF.md)를 따릅니다.

## 이전 버전 — 지원·공급 종료

아래 문서는 당시 artifact·migration 경계·검증 판단을 보존하는 역사 자료입니다. stable 설치 목록에서
제공하지 않으며 문서 안의 “현재 stable”과 예정 gate는 작성 당시 상태입니다.

| 버전 | 보존 문서와 당시 특징 |
| --- | --- |
| v0.5.0-rc.2 | [RC2 문서](v0.5.0-rc.2/README.md) — 정식 릴리스 이전 공개 후보, 기존 자산 보존 |
| v0.5.0-rc.1 | [RC1 문서](v0.5.0-rc.1/README.md) — RC2 이전 공개 후보, 기존 자산 보존 |
| v0.4.1 | [릴리스 문서](v0.4.1/README.md) — 이전 stable |
| v0.4.0 | [릴리스 문서](v0.4.0/README.md) — v0.4.1의 기능 기준선 |
| v0.4.0-rc.1 | [후보 절차 기록](v0.4.0-rc.1/README.md) — 비공개 후보 |
| v0.3.0 | [릴리스 문서](v0.3.0/README.md) |
| v0.3.0-rc.3 | [RC3 문서](v0.3.0-rc.3/README.md) |
| v0.3.0-rc.2 | [RC2 문서](v0.3.0-rc.2/README.md) |
| v0.3.0-rc.1 | [RC1 문서](v0.3.0-rc.1/README.md), [clean-room 중단](v0.3.0-rc.1/CLEANROOM_ABORT.md) |
| v0.2.0 | [릴리스 문서](v0.2.0/README.md) |
| v0.1.0 | [릴리스 문서](v0.1.0/README.md) |

## 검증 수치와 자산 보존

v0.4.0의 공개 identity 64개와 당시 HIL 결과, v0.4.1 유지보수 결과는 역사 기록으로 유지합니다.
QDEC20/21의 기본 정·역회전과 SAMPLE/REPORT event는 지원하지만 반복 manual `read()/clear`의
무손실은 보증하지 않습니다.

- 공개 tag·Release·archive·checksum·SBOM은 immutable이며 문서·브랜치 정리로 다시 만들지 않습니다.
- 공개 자산에 포함된 문서와 과거 실패 원본은 당시 byte·판정을 보존합니다.
- 실제 결과는 [검증 기록](<../04_검증 기록/README.md>), 현재 읽는 기준은 [문서 안내](../README.md)를 따릅니다.
