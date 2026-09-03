# NU54DK Arduino Core — 릴리스 문서 안내

| 항목 | 내용 |
| --- | --- |
| 현재 정식 버전 | `v0.3.0` |
| 설치 channel | Stable Boards Manager index |
| 공식 사용자 OS | Windows 10/11 x64 |
| 이전 버전 상태 | 역사적·비지원, 공개 자산은 불변 보존 |
| 최종 갱신일 | 2026-09-03 |

신규 설치, 지원 요청과 현재 API 기준은 `v0.3.0` 문서를 사용합니다. 이전 stable과 RC 문서는
당시 artifact, migration 경계와 검증 판단을 보존하는 역사 자료입니다.

## 현재 정식 버전 — v0.3.0

| 목적 | 문서 |
| --- | --- |
| 릴리스 개요와 공개 identity | [v0.3.0 문서](v0.3.0/README.md) |
| 추가·변경된 기능 | [Release notes](v0.3.0/RELEASE_NOTES.md) |
| 이전 버전/RC에서 이동 | [Migration](v0.3.0/MIGRATION.md) |
| 설치와 기본 시험 | [Testing](v0.3.0/TESTING.md) |
| 설치·compile·upload 문제 | [Troubleshooting](v0.3.0/TROUBLESHOOTING.md) |
| 지원 경계와 미검증 범위 | [Known issues](v0.3.0/KNOWN_ISSUES.md) |

Stable package index:

```text
https://raw.githubusercontent.com/EIDOSDATA/NU54DK_Arduino_Core/main/package_nucode_nu54dk_index.json
```

## 보존된 이전 stable

`v0.1.0`과 `v0.2.0`은 신규 수정·지원 대상이 아닙니다. 하지만 재현성 감사와 검증된
downgrade를 위해 공개 tag·Release asset과 stable index 항목을 삭제하거나 덮어쓰지 않습니다.

### v0.2.0

- [릴리스 개요](v0.2.0/README.md)
- [Release notes](v0.2.0/RELEASE_NOTES.md)
- [Migration](v0.2.0/MIGRATION.md)
- [Troubleshooting](v0.2.0/TROUBLESHOOTING.md)
- [Known issues](v0.2.0/KNOWN_ISSUES.md)

### v0.1.0

- [Migration](09_v0.1.0_마이그레이션.md)
- [Troubleshooting](10_v0.1.0_문제해결.md)
- [Release notes](11_v0.1.0_릴리스_노트.md)
- [Known issues](12_v0.1.0_알려진_제약.md)

## 보존된 v0.3.0 Release Candidate

RC1~RC3는 stable 설치 channel이 아닙니다. 당시 공개 자산과 기록은 교정 과정과 승격 근거를
보존하기 위해 그대로 유지합니다.

| 후보 | 상태 | 문서 |
| --- | --- | --- |
| `v0.3.0-rc.3` | Stable runtime 동등성 기준 | [RC3 문서](v0.3.0-rc.3/README.md) |
| `v0.3.0-rc.2` | 공개 lifecycle 통과, 이후 memory 계약 교정 | [RC2 문서](v0.3.0-rc.2/README.md) |
| `v0.3.0-rc.1` | Clean-room 실행기 결함으로 중단 | [RC1 문서](v0.3.0-rc.1/README.md) |

## 그 밖의 역사적 RC

- `v0.2.0-rc.1`/`rc.2`: [M18 기록](<../04_검증 기록/20_M18_v0.2.0_rc1_공개_검증과_rc2_교정.md>)
- `v0.1.0-rc.2`: [Migration](05_v0.1.0_rc2_마이그레이션.md), [Troubleshooting](06_v0.1.0_rc2_문제해결.md), [Release notes](07_v0.1.0_rc2_릴리스_노트.md), [Known issues](08_v0.1.0_rc2_알려진_제약.md)
- `v0.1.0-rc.1`: [배포 중단 기록](00_v0.1.0_rc1_배포_중단_기록.md)

## 문서와 자산 보존 규칙

1. 공개한 tag, archive, checksum, SBOM과 Release 문서는 덮어쓰지 않습니다.
2. Stable index에는 최신 버전을 앞에 두고 검증된 이전 stable을 downgrade용으로 보존합니다.
3. 최신 stable URL과 version별 불변 Release index를 구분합니다.
4. 실제 검증 수치는 [검증 기록](<../04_검증 기록/README.md>)에서 확인합니다.
5. 다음 버전 계획은 [제품 로드맵](<../01_아두이노 코어 설계/02_구현_로드맵.md>)에서 관리합니다.
