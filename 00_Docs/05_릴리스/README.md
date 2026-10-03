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

후속 개발의 출발점은 M32를 통합한 `main`입니다. `Dev-0.6.0-M32`는 단계별 구현·실기 source의
원본 이력으로, `Release-0.5.0`은 정식 릴리스 기준선으로 보존합니다. 통합 범위와 squash 대응은
[295번 기록](<../04_검증 기록/295_M32_문서_전수_정비와_main_Squash_통합.md>)을 따릅니다.

| 제품선·트랙 | 현재 상태 | 다음 작업 |
| --- | --- | --- |
| v0.5.0 | Windows stable 공개·지원 | 공개 tag와 manifest의 source SHA로 패키지 재현 |
| [v0.6.0](../TODO_v0.6.0.md) | M32 **12/12 완료**, M33 **0/8**, 미공개 | M33-W01부터 전체 예제·상호운용·배포 준비 |
| Host | HOST-W01~W03 완료, W04~W08 사용자 보류 | 별도 재개 지시 후 OS별 실물 지원 gate 수행 |
| [v0.7.0](../TODO_v0.7.0.md) | SDK-W01~W06 **0/6** | NCS v3.4.0 → v3.4.1 전체 전환만 수행 |

M32 완료 근거는 [M32 TODO](../TODO_M32.md), 다음 개발 절차는 [HANDOFF](../HANDOFF.md)가
관리합니다. M34~M37은 v0.8.0, M38~M41은 v0.9.0, M42~M45는 v0.10.0 계획입니다.
현행 소스의 제품 식별자는 `0.5.0`이고 v0.6.0 개발은 NCS v3.4.0을 유지합니다. 개발 소스의
M32 기능은 현재 stable 패키지에 포함되지 않으며, v0.6.0 공개는 M33의 검증·승인 경계를 따릅니다.

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
