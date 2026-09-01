# NU54DK Arduino Core — 릴리스 문서 안내

| 항목 | 내용 |
| --- | --- |
| 현재 정식 버전 | `v0.2.0` |
| 설치 channel | Stable Boards Manager index |
| 공식 사용자 OS | Windows 10/11 x64 |
| 최종 갱신일 | 2026-09-02 |

신규 production 설치와 현재 정식 사용법은 **`v0.2.0` 문서**를 사용한다. 공개 검증된
`v0.3.0-rc.2`는 시험용 문서이며, 그보다 오래된 `v0.1.0`과 RC 문서는 당시 artifact와
migration 경계를 보존하는 역사 자료다.

`v0.3.0-rc.2`는 RC1 clean-room 실행기 결함을 교정해 별도 RC index로 공개 검증을 완료한 다음
버전 후보다. Stable `v0.2.0`과 stable index는 바뀌지 않았으며 생산용 최신 버전으로 표시하지
않는다.

## 현재 시험 후보 — v0.3.0-rc.2

| 목적 | 문서 |
| --- | --- |
| 후보 범위와 공개 경계 | [RC2 문서](v0.3.0-rc.2/README.md) |
| 추가·변경된 기능 | [RC2 Release notes](v0.3.0-rc.2/RELEASE_NOTES.md) |
| GitHub·Arduino IDE 설치와 시험 | [RC2 Testing](v0.3.0-rc.2/TESTING.md) |
| Stable에서 이동·복귀 | [RC2 Migration](v0.3.0-rc.2/MIGRATION.md) |
| 알려진 제약·제외 범위 | [RC2 Known issues](v0.3.0-rc.2/KNOWN_ISSUES.md) |
| 설치·build·storage·BLE 진단 | [RC2 Troubleshooting](v0.3.0-rc.2/TROUBLESHOOTING.md) |

RC index는 다음 Public Prerelease 고정 URL에서 사용한다.

```text
https://github.com/EIDOSDATA/NU54DK_Arduino_Core/releases/download/v0.3.0-rc.2/package_nucode_nu54dk_rc_index.json
```

## 현재 정식 버전 — v0.2.0

| 목적 | 문서 |
| --- | --- |
| 릴리스 개요와 exact 기반 | [v0.2.0 문서](v0.2.0/README.md) |
| 추가·변경된 기능 | [Release notes](v0.2.0/RELEASE_NOTES.md) |
| `v0.1.0`/RC에서 이동 | [Migration](v0.2.0/MIGRATION.md) |
| 설치·compile·upload 문제 | [Troubleshooting](v0.2.0/TROUBLESHOOTING.md) |
| 지원 경계와 미검증 범위 | [Known issues](v0.2.0/KNOWN_ISSUES.md) |

Stable package index:

```text
https://raw.githubusercontent.com/EIDOSDATA/NU54DK_Arduino_Core/main/package_nucode_nu54dk_index.json
```

## 보존된 정식 버전 — v0.1.0

`v0.1.0`은 첫 정식 버전이다. 현재 stable index에는 upgrade/downgrade 검증을 위해 보존되지만
신규 사용자는 `v0.2.0`을 선택한다.

| 목적 | 역사 문서 |
| --- | --- |
| Migration | [v0.1.0 migration](09_v0.1.0_마이그레이션.md) |
| Troubleshooting | [v0.1.0 문제 해결](10_v0.1.0_문제해결.md) |
| Release notes | [v0.1.0 릴리스 노트](11_v0.1.0_릴리스_노트.md) |
| Known issues | [v0.1.0 알려진 제약](12_v0.1.0_알려진_제약.md) |

## 보존된 Release Candidate

### v0.1.0-rc.2

RC1의 Windows UTF-8 설치 표시 결함을 교정하고 `v0.1.0` 승격 전 clean Windows와 실제
NU54DK에서 검증한 후보였다. 신규 설치 channel로 사용하지 않는다.

- [Migration](05_v0.1.0_rc2_마이그레이션.md)
- [Troubleshooting](06_v0.1.0_rc2_문제해결.md)
- [Release notes](07_v0.1.0_rc2_릴리스_노트.md)
- [Known issues](08_v0.1.0_rc2_알려진_제약.md)

### v0.1.0-rc.1 — 회수됨

Arduino IDE `post_install` 완료 출력의 invalid UTF-8 gRPC 결함 때문에 배포를 중단했다.
설치가 실제로 끝났더라도 IDE가 실패로 표시할 수 있으므로 사용하지 않는다.

- [배포 중단 기록](00_v0.1.0_rc1_배포_중단_기록.md)
- [Migration 역사 문서](01_v0.1.0_rc1_마이그레이션.md)
- [Troubleshooting 역사 문서](02_v0.1.0_rc1_문제해결.md)
- [Release notes 역사 문서](03_v0.1.0_rc1_릴리스_노트.md)
- [Known issues 역사 문서](04_v0.1.0_rc1_알려진_제약.md)

## 버전별 문서 규칙

1. 정식 버전의 사용자 문서는 버전별 디렉터리에 보관한다.
2. 공개한 RC/stable의 tag, archive, checksum과 문서는 덮어쓰지 않는다.
3. 최신 stable URL과 과거 version 고정 artifact를 구분한다.
4. 공개 검증 수치는 [검증 기록](<../04_검증 기록/README.md>)에서 확인한다.
5. 다음 버전 계획은 [Master roadmap](<../01_아두이노 코어 설계/02_구현_로드맵.md>)에서 관리한다.
