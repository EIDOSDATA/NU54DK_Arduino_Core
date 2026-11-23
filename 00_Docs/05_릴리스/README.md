# 릴리스 문서 안내

**현재 stable은 v0.6.0입니다.** NCS 3.4.0과 라이브러리 24개, 예제 204개를 제공합니다. [설치 안내](v0.6.0/README.md), [GitHub Release](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/releases/tag/v0.6.0)

| 필요한 정보 | 문서 |
| --- | --- |
| 이전 버전에서 이동 | [버전 전환](v0.6.0/MIGRATION.md) |
| 새 기능과 예제 | [릴리스 노트](v0.6.0/RELEASE_NOTES.md) |
| 지원 OS와 검증 범위 | [지원표](v0.6.0/SUPPORT_MATRIX.md), [시험 기록](v0.6.0/TESTING.md) |
| 설치, 컴파일, 업로드 문제 | [문제 해결](v0.6.0/TROUBLESHOOTING.md), [알려진 제한](v0.6.0/KNOWN_ISSUES.md) |
| 게시, 해시, 공개 설치 | [릴리스 체크리스트](v0.6.0/RELEASE_CHECKLIST.md) |

`Release-0.6.0`에서 배포 기록을 관리합니다. 다음 SDK 전환의 범위는 [v0.7.0 계획](../TODO_v0.7.0.md)에 있습니다.

## 이전 버전 — 지원·공급 종료

아래 문서는 당시 artifact·migration 경계·검증 판단을 보존하는 역사 자료입니다. stable 설치 목록에서
제공하지 않으며 문서 안의 “현재 stable”과 예정 gate는 작성 당시 상태입니다.

| 버전 | 보존 문서와 당시 특징 |
| --- | --- |
| v0.5.0 | [릴리스 문서](v0.5.0/README.md). Windows 10/11 x64 대상 공개판 |
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
| v0.1.0-rc.2 | [RC2 문서](v0.1.0-rc.2/README.md) — 초기 후보 이력, 지원·공급 종료 |
| v0.1.0-rc.1 | [RC1 문서](v0.1.0-rc.1/README.md) — 철회된 초기 후보 이력 |

## 검증 수치와 자산 보존

v0.4.0의 공개 identity 64개와 당시 HIL 결과, v0.4.1 유지보수 결과는 역사 기록으로 유지합니다.
QDEC20/21의 기본 정·역회전과 SAMPLE/REPORT event는 지원하지만 반복 manual `read()/clear`의
무손실은 보증하지 않습니다.

- 공개 tag·Release·archive·checksum·SBOM은 immutable이며 문서·브랜치 정리로 다시 만들지 않습니다.
- 공개 자산에 포함된 문서와 과거 실패 원본은 당시 byte·판정을 보존합니다.
- 실제 결과는 [검증 기록](<../04_검증 기록/README.md>), 현재 읽는 기준은 [문서 안내](../README.md)를 따릅니다.
