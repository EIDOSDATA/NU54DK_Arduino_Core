# NU54DK Arduino Core — 릴리스 문서 안내

2026-09-08T07:28Z T13: original4aadf29 UART RX400회·SPIM 취소500회·TWI NACK400회를
완료했다. 고정 serial 복구는17/21이며 TWI 취소4항목은 첫 DMA 판정 실패 조치 뒤에 남는다.
양쪽 STOP과 원본을 보존했고506680f PWM 후속 실행으로 이동한다. 전체 진행은104번/활성 TODO를 따른다.

2026-09-08 현재: R00~R13·source별 T11 단독 회귀와 **T12 기능검증은 완료**했다. **QDEC도 일부 문제·제한사항을 101번에 보고하고 검증 작업을 완료**했다. 동작 중 수동 read/clear 누산 누락은 미해결이며 실패 결과를 PASS로 변경하지 않는다. 사용자 완료 결정은 T12 마일스톤에 적용하며 알려진 제한은 T14/T15에서 정리한다. 현재는 사용자 S 재배치·실행 중 유지 확인에 따라 T13 실기와 실패 원인 분석을 진행 중이다. S 단독 29개·동시 7조합 및 복구/전환을 진행하고 종료 후 U 결선을 안내한다. S 정상 안정성은 f591571·43bc032의 source별 근거29/36항목이며 복구/전환100회·T13 전체·RC·공개는 미완료다. [문서 감사·요구별 증거 대조](<../04_검증 기록/102_개발_문서_전수_검토와_마일스톤_체크포인트.md>), [실행 TODO](<../TODO_v0.4.0.md>)를 따른다.

| 항목 | 내용 |
| --- | --- |
| 문서 ID | RELEASE-INDEX-001 |
| 문서 개정 | 2.2 |
| 현재 정식 버전 | `v0.3.0` |
| 설치 channel | Stable Boards Manager index |
| 공식 사용자 OS | Windows 10/11 x64 |
| 이전 버전 상태 | 공개 공급 종료, archive 브랜치에 원본 보존 |
| 최종 갱신일 | 2026-09-08 |

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

## 다음 버전 준비 — v0.4.0-rc.1

`v0.4.0-rc.1`은 [내부 준비 문서](v0.4.0-rc.1/README.md)만 있으며 공개 tag·Release·index는
없습니다. M24~M26 physical gate와 M27 release gate가 모두 끝나기 전에는 설치 대상으로 사용하지
않습니다.

## 보존된 이전 stable

2026-09-08 소유자 지시로 v0.3.0 미만의 stable·RC·preview 공급을 종료한다. Stable index는 0.3.0만 제공하며 preview URL은 빈 목록을 유지한다. 원본 이력과 자산은 별도 archive 브랜치에서 보존한다. v0.3.0 태그·설치 ZIP·checksum·SBOM 등 6개 payload/sidecar는 그대로 유지하고, 해당 Release의 catalog index만 현재 공급 목록과 일치시킨다.
[106번 정리·보존 기록](<../04_검증 기록/106_Git_이력_정리와_구버전_패키지_공급_종료.md>)을 참조합니다.

### v0.2.0

- [릴리스 개요](v0.2.0/README.md)
- [Release notes](v0.2.0/RELEASE_NOTES.md)
- [Migration](v0.2.0/MIGRATION.md)
- [Troubleshooting](v0.2.0/TROUBLESHOOTING.md)
- [Known issues](v0.2.0/KNOWN_ISSUES.md)

### v0.1.0

- [릴리스 개요](v0.1.0/README.md)
- [Release notes](v0.1.0/RELEASE_NOTES.md)
- [Migration](v0.1.0/MIGRATION.md)
- [Troubleshooting](v0.1.0/TROUBLESHOOTING.md)
- [Known issues](v0.1.0/KNOWN_ISSUES.md)

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

1. 현재 공급하는 v0.3.0 tag·설치 archive·checksum·SBOM은 그대로 유지합니다.
2. 소유자가 승인한 2026-09-08 공급 종료 대상은 원본을 archive 브랜치로 보존합니다.
3. Stable root와 v0.3.0 Release catalog는 0.3.0만 제공하며 preview catalog는 빈 목록입니다.
4. 실제 검증 수치는 [검증 기록](<../04_검증 기록/README.md>)에서 확인합니다.
5. 다음 버전 계획은 [제품 로드맵](<../01_아두이노 코어 설계/02_구현_로드맵.md>)에서 관리합니다.
