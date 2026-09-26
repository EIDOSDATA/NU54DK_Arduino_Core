# 릴리스 문서 안내

**현재 stable·지원 버전은 v0.4.1, 공개 시험 후보는 v0.5.0-rc.1입니다.**
두 버전 모두 Windows 10/11 x64 대상입니다. v0.5.0 stable은 아직 공개하지 않았습니다.
일반 설치는 stable, 새 기능 시험은 별도 RC index를 선택합니다.

## 현재 사용자 문서

| 목적 | Stable v0.4.1 | 공개 RC v0.5.0-rc.1 |
| --- | --- | --- |
| 설치·버전 identity | [시작하기](v0.4.1/README.md) | [시작하기](v0.5.0-rc.1/README.md) |
| 변경 기능 | [Release notes](v0.4.1/RELEASE_NOTES.md) | [Release notes](v0.5.0-rc.1/RELEASE_NOTES.md) |
| 이전 버전에서 이동·복귀 | [Migration](v0.4.1/MIGRATION.md) | [Migration](v0.5.0-rc.1/MIGRATION.md) |
| 검증 범위와 기본 시험 | [Testing](v0.4.1/TESTING.md) | [Testing](v0.5.0-rc.1/TESTING.md) |
| 설치·compile·upload 문제 | [Troubleshooting](v0.4.1/TROUBLESHOOTING.md) | [Troubleshooting](v0.5.0-rc.1/TROUBLESHOOTING.md) |
| 제한·미검증 범위 | [Known issues](v0.4.1/KNOWN_ISSUES.md) | [Known issues](v0.5.0-rc.1/KNOWN_ISSUES.md) |
| 설치 예제 | 9개 라이브러리·30개 | 16개 라이브러리·113개 |

Stable Boards Manager index:

```text
https://raw.githubusercontent.com/EIDOSDATA/NU54DK_Arduino_Core/main/package_nucode_nu54dk_index.json
```

RC index와 설치 절차는 [RC 시작하기](v0.5.0-rc.1/README.md)에 있습니다.
RC는 공개 [GitHub Pre-release](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/releases/tag/v0.5.0-rc.1)이지만
stable root index와 분리되어 있습니다. 공개 다운로드·설치·대표 compile·재설치 결과는
[268번 기록](<../04_검증 기록/268_v0.5.0-rc.1_공개와_다운로드_smoke.md>)을 따릅니다.

## 개발 소스와 다음 릴리스

현재 개발 브랜치는 `main`이고 `0.5.0-RC1`은 별도로 보존합니다. M28~M31과 메모리 최적화 P0~P2는 완료했고,
다음 배포 판단은 RC 관찰 후의 **별도 stable 승격 승인**입니다.
현행 소스의 `0.4.1-dev` 문자열은 개발 코어 식별자이며 설치한 RC package 버전과 다릅니다.
패키지의 재현 기준은 해당 공개 tag와 release manifest의 source SHA입니다.

[Main 통합·이력 정리](<../04_검증 기록/270_main_RC_통합_Squash와_문서_동기화.md>)는 새 릴리스가 아닙니다.
Stable v0.4.1 catalog·공개 자산과 공개 RC tag의 원래 source
`7786984a186980f6220271cd506636e4564bc55d`는 유지합니다.

남은 승인·후속 범위는 [v0.5.0 TODO](../TODO_v0.5.0.md), 개발 재개는
[HANDOFF](../HANDOFF.md)를 봅니다. M32/M33, Ubuntu/macOS 지원은 후속 제품선이며 버전은 미정입니다.
과거 TODO의 다음 작업을 완료한 RC의 새 필수 gate로 되살리지 않습니다.

## 이전 버전 — 지원·공급 종료

아래 문서는 당시 artifact·migration 경계·검증 판단을 보존하는 역사 자료입니다.
stable 설치 목록에서 제공하지 않으며, 문서 안의 “현재 stable”과 예정 gate는 작성 당시 상태입니다.

| 버전 | 보존 문서와 당시 특징 |
| --- | --- |
| v0.4.0 | [릴리스 문서](v0.4.0/README.md) — v0.4.1의 기능 기준선 |
| v0.4.0-rc.1 | [후보 절차 기록](v0.4.0-rc.1/README.md) — 비공개 후보 |
| v0.3.0 | [릴리스 문서](v0.3.0/README.md) |
| v0.3.0-rc.3 | [RC3 문서](v0.3.0-rc.3/README.md) — stable runtime 동등성 기준 |
| v0.3.0-rc.2 | [RC2 문서](v0.3.0-rc.2/README.md) — lifecycle 이후 memory 계약 교정 |
| v0.3.0-rc.1 | [RC1 문서](v0.3.0-rc.1/README.md), [clean-room 실행기 중단](v0.3.0-rc.1/CLEANROOM_ABORT.md) |
| v0.2.0 | [릴리스 문서](v0.2.0/README.md) |
| v0.2.0-rc.1/rc.2 | [M18 공개·교정 기록](<../04_검증 기록/20_M18_v0.2.0_rc1_공개_검증과_rc2_교정.md>) |
| v0.1.0 | [릴리스 문서](v0.1.0/README.md) |
| v0.1.0-rc.2 | [RC2 문서](v0.1.0-rc.2/README.md) |
| v0.1.0-rc.1 | [RC1 문서](v0.1.0-rc.1/README.md), [배포 중단](v0.1.0-rc.1/WITHDRAWAL.md) |

## 검증 수치와 자산 보존

v0.4.0의 공개 identity는 **64개**, 단독 HIL 상태는 **62 PASS + QDEC20/21 2 PARTIAL**입니다.
QDEC의 기본 정·역회전과 SAMPLE/REPORT event는 지원하지만 반복 manual `read()/clear`의
무손실은 보증하지 않습니다. 이 범위는 [124번 지원 결정](<../04_검증 기록/124_T22전_QDEC_지원_범위_재확정.md>)을 따릅니다.

- 공개 tag·Release·archive·checksum·SBOM은 immutable이며 문서·브랜치 정리로 다시 만들지 않습니다.
- 공개 자산에 포함된 문서와 과거 실패 원본은 당시 byte·판정을 보존합니다. 이 저장소의 후속 안내를 배포 자산 수정으로 해석하지 않습니다.
- 공급 종료 기록에도 고유한 결정·증거가 있으므로 단순히 오래되었다는 이유로 삭제하지 않습니다.
- 실제 결과는 [검증 기록](<../04_검증 기록/README.md>), 현재 문서의 읽는 기준은 [문서 안내](../README.md)를 따릅니다.
