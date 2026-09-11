# NU54DK Arduino Core — 릴리스 문서 안내

**현재 정식 버전은 v0.4.0이며 T01~T25를 완료했습니다.** 신규 설치와 지원 요청은 아래 v0.4.0
문서를 사용합니다. 공개·설치 검증 결과는 [125번 마감 기록](<../04_검증 기록/125_v0.4.0_정식_릴리스_공개와_T24_T25_마감.md>),
완료 범위는 [v0.4.0 TODO](../TODO_v0.4.0.md)에서 확인합니다.

| 항목 | 내용 |
| --- | --- |
| 문서 ID | RELEASE-INDEX-001 |
| 문서 개정 | 2.6 |
| 현재 정식 버전 | `v0.4.0` |
| 설치 channel | Stable Boards Manager index |
| 공식 사용자 OS | Windows 10/11 x64 |
| 이전 버전 상태 | `v0.3.0` stable index에 설치 가능, 그 이전 version은 역사 자료로 보존 |
| 최종 갱신일 | 2026-09-12 |

신규 설치, 지원 요청과 현재 API 기준은 `v0.4.0` 문서를 사용합니다. 이전 stable과 RC 문서는
당시 artifact, migration 경계와 검증 판단을 보존하는 역사 자료입니다.

## 현재 정식 버전 — v0.4.0

| 목적 | 문서 |
| --- | --- |
| 릴리스 개요와 공개 identity | [v0.4.0 문서](v0.4.0/README.md) |
| 추가·변경된 기능 | [Release notes](v0.4.0/RELEASE_NOTES.md) |
| 이전 버전/RC에서 이동 | [Migration](v0.4.0/MIGRATION.md) |
| 설치와 기본 시험 | [Testing](v0.4.0/TESTING.md) |
| 설치·compile·upload 문제 | [Troubleshooting](v0.4.0/TROUBLESHOOTING.md) |
| 지원 경계와 미검증 범위 | [Known issues](v0.4.0/KNOWN_ISSUES.md) |

Stable package index:

```text
https://raw.githubusercontent.com/EIDOSDATA/NU54DK_Arduino_Core/main/package_nucode_nu54dk_index.json
```

## 버전별 상태와 문서

| 버전 | 현재 상태 | 문서 |
| --- | --- | --- |
| `v0.4.0` | 현재 stable·신규 설치와 지원 기준 | [현재 릴리스](v0.4.0/README.md) |
| `v0.4.0-rc.1` | 비공개 내부 후보·정식 runtime 동등성 확인 완료 | [후보 절차 기록](v0.4.0-rc.1/README.md) |
| `v0.3.0` | 이전 stable·Sketch 전환과 복구용 설치 가능 | [이전 릴리스](v0.3.0/README.md) |
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

1. 현재 정식 `v0.4.0` tag·Release·archive·checksum·SBOM은 immutable로 유지합니다.
2. 이전 stable `v0.3.0` tag·설치 archive·checksum·SBOM도 그대로 유지합니다.
3. Stable root는 0.4.0과 0.3.0을 제공하고 preview catalog는 빈 목록입니다.
4. 소유자가 승인한 v0.2.0 이하 공급 종료 대상은 원본을 archive 브랜치로 보존합니다.
5. 실제 검증 수치는 [검증 기록](<../04_검증 기록/README.md>)에서 확인합니다.
6. 다음 버전 계획은 [제품 로드맵](<../01_아두이노 코어 설계/02_구현_로드맵.md>)에서 관리합니다.
