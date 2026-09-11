# NU54DK Arduino Core — 릴리스 문서 안내

**현재 설치·지원 버전은 v0.4.1 하나입니다.** 이전 stable·RC·preview는 지원하지 않으며 stable
Boards Manager 목록에서도 제공하지 않습니다. v0.4.1 유지보수 결과는
[129번 기록](<../04_검증 기록/129_v0.4.1_설치기_유지보수_릴리스.md>)에서 확인합니다.

| 항목 | 내용 |
| --- | --- |
| 문서 ID | RELEASE-INDEX-001 |
| 문서 개정 | 3.0 |
| 현재 정식 버전 | `v0.4.1` |
| 설치 channel | Stable Boards Manager index |
| 공식 사용자 OS | Windows 10/11 x64 |
| 이전 버전 상태 | `v0.4.1` 미만 모두 지원·catalog 공급 종료, 원본 자산은 보존 |
| 최종 갱신일 | 2026-09-12 |

신규 설치와 지원 요청은 `v0.4.1` 문서를 사용합니다. 이전 stable과 RC 문서는
당시 artifact, migration 경계와 검증 판단을 보존하는 역사 자료입니다.

## 현재 정식 버전 — v0.4.1

| 목적 | 문서 |
| --- | --- |
| 릴리스 개요와 공개 identity | [v0.4.1 문서](v0.4.1/README.md) |
| 추가·변경된 기능 | [Release notes](v0.4.1/RELEASE_NOTES.md) |
| 이전 버전에서 이동 | [Migration](v0.4.1/MIGRATION.md) |
| 설치와 기본 시험 | [Testing](v0.4.1/TESTING.md) |
| 설치·compile·upload 문제 | [Troubleshooting](v0.4.1/TROUBLESHOOTING.md) |
| 지원 경계와 미검증 범위 | [Known issues](v0.4.1/KNOWN_ISSUES.md) |

Stable package index:

```text
https://raw.githubusercontent.com/EIDOSDATA/NU54DK_Arduino_Core/main/package_nucode_nu54dk_index.json
```

## 버전별 상태와 문서

| 버전 | 현재 상태 | 문서 |
| --- | --- | --- |
| `v0.4.1` | 유일한 stable·신규 설치와 지원 기준 | [현재 릴리스](v0.4.1/README.md) |
| `v0.4.0` | 지원·catalog 공급 종료·역사 자료 | [보존 문서](v0.4.0/README.md) |
| `v0.4.0-rc.1` | 지원 종료·비공개 후보 기록 | [후보 절차 기록](v0.4.0-rc.1/README.md) |
| `v0.3.0` | 지원·catalog 공급 종료·역사 자료 | [보존 문서](v0.3.0/README.md) |
| `v0.2.0` | 공급 종료·역사 자료 | [보존 문서](v0.2.0/README.md) |
| `v0.1.0` | 공급 종료·역사 자료 | [보존 문서](v0.1.0/README.md) |

각 버전 README에서 해당 Release notes·Migration·Testing·Troubleshooting·Known issues로
이동할 수 있습니다. 이전 버전 문서의 “현재 stable”, 지원 대상과 예정 gate는 **작성 당시의
상태**입니다. 현재 설치·지원 정책보다 우선하지 않으며, 과거 후보를 다시 공개하라는 지시도 아닙니다.

## 검증 수치와 보존 문서 해석

v0.4.0의 공개 identity는 **64개**, 단독 HIL 상태는 **62 PASS + QDEC20/21 2 PARTIAL**입니다.
QDEC20/21은 기본 정·역회전과 SAMPLE/REPORT event를 지원하지만 반복 manual `read()/clear`의
무손실을 보증하지 않습니다. “공개 identity HIL 통과”와 같은 요약을 QDEC까지 포함한 전 항목
PASS로 읽지 않습니다. 최종 범위는 [124번 지원 결정](<../04_검증 기록/124_T22전_QDEC_지원_범위_재확정.md>)을 따릅니다.

정식 Release에 포함된 사용자 문서 5종은 공개 당시 byte를 보존합니다. 현행 지원 범위·시점에
대한 보충 안내는 이 페이지와 각 버전 README에서 제공하며, 과거 실패나 제외를 새 PASS로 바꾸지 않습니다.

## 보존된 v0.3.0 Release Candidate

RC1~RC3의 공개 Release·tag·설치 목록은 공급 종료 대상입니다. 교정 과정과 승격 근거는
아래 역사 문서와 archive 브랜치의 원본 자산에 보존합니다.

| 후보 | 상태 | 문서 |
| --- | --- | --- |
| `v0.3.0-rc.3` | Stable runtime 동등성 기준 | [RC3 문서](v0.3.0-rc.3/README.md) |
| `v0.3.0-rc.2` | 공개 lifecycle 통과, 이후 memory 계약 교정 | [RC2 문서](v0.3.0-rc.2/README.md) |
| `v0.3.0-rc.1` | Clean-room 실행기 결함으로 중단 | [RC1 문서](v0.3.0-rc.1/README.md), [중단 기록](v0.3.0-rc.1/CLEANROOM_ABORT.md) |

## 그 밖의 역사적 RC

- `v0.2.0-rc.1`/`rc.2`: [M18 기록](<../04_검증 기록/20_M18_v0.2.0_rc1_공개_검증과_rc2_교정.md>)
- `v0.1.0-rc.2`: [역사 문서](v0.1.0-rc.2/README.md)
- `v0.1.0-rc.1`: [역사 문서](v0.1.0-rc.1/README.md), [배포 중단 기록](v0.1.0-rc.1/WITHDRAWAL.md)

## 문서와 자산 보존 규칙

1. 현재 정식 `v0.4.1` tag·Release·archive·checksum·SBOM은 immutable로 유지합니다.
2. 이전 버전의 tag·Release·archive·checksum·SBOM도 감사용 원본 그대로 유지합니다.
3. Stable root는 `0.4.1` 하나만 제공하고 preview/RC는 지원 목록에 넣지 않습니다.
4. 공급 종료된 모든 이전 버전은 원본 자산과 문서만 역사 자료로 보존합니다.
5. 실제 검증 수치는 [검증 기록](<../04_검증 기록/README.md>)에서 확인합니다.
6. 다음 버전 계획은 [제품 로드맵](<../01_아두이노 코어 설계/02_구현_로드맵.md>)에서 관리합니다.
