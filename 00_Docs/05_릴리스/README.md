# NU54DK Arduino Core — 릴리스 문서 안내

**현재 설치·지원 버전은 v0.4.1 하나입니다.** 이전 stable·RC·preview는 지원하지 않으며 stable
Boards Manager 목록에서도 제공하지 않습니다. v0.4.1 유지보수 결과는
[129번 기록](<../04_검증 기록/129_v0.4.1_설치기_유지보수_릴리스.md>)에서 확인합니다.

| 항목 | 내용 |
| --- | --- |
| 문서 ID | RELEASE-INDEX-001 |
| 문서 개정 | 3.6 |
| 현재 정식 버전 | `v0.4.1` |
| 설치 channel | Stable Boards Manager index |
| 공식 사용자 OS | Windows 10/11 x64 |
| v0.5.0 릴리스 목표 | M31 완료 뒤 Windows 10/11 x64 우선 |
| 후속 제품선 | M32/M33 추가 기능, Ubuntu/macOS 지원; 버전 미정 |
| 이전 버전 상태 | `v0.4.1` 미만 모두 지원·catalog 공급 종료, 원본 자산은 보존 |
| 최종 갱신일 | 2026-09-25 |

신규 설치와 지원 요청은 `v0.4.1` 문서를 사용합니다. 이전 stable과 RC 문서는
당시 artifact, migration 경계와 검증 판단을 보존하는 역사 자료입니다.

## 설치 버전과 개발 소스 구분

| 구분 | 현재 상태 |
| --- | --- |
| Boards Manager `v0.4.1` | 공개·지원 중인 고정 패키지; v0.4.0 기능 기준선과 설치기 유지보수 |
| `main`의 `0.4.1-dev` | v0.5.0을 준비하는 개발 소스; M28·M29·M30 완료, M31은 W01~W03 완료로 3/8 |
| M29 검증 | W01~W08 8/8·test ID 10/10, 세 보드 통합·회귀와 Windows/Intel 기본 GATT PASS |
| M30 검증 | W01~W08 8/8·test ID 10/10, W08 실제 전원 차단 4지점 × 3회(12/12) PASS |
| M31 검증 | W01·W02·W03 완료; W03 LE Audio profile 11/11 PASS. W04~W08은 완료 아님 |
| `v0.5.0` | 미공개; M31 8/8 뒤 Windows package·설치·RC와 공개 gate를 판정 |
| 후속 Host | HOST-W01~HOST-W03 완료 3/8, HOST-W04~HOST-W08 사용자 보류; 해당 OS를 추가할 릴리스에서 검증 |

진행 중인 작업과 남은 검증은 [v0.5.0 TODO](../TODO_v0.5.0.md)를 따릅니다. 개발 문서의
M28·M29·M30과 M31 완료분의 PASS를 공개 v0.4.1 패키지의 기능 추가나 v0.5.0 릴리스 완료로
해석하지 않습니다.
다중 Host의 시작 시점·지원 범위·검증 절차는
[후속 다중 Host 계약](<../02_빌드 설계/10_v0.5.0_다중_Host_지원_착수_계약.md>)에 고정합니다.

## v0.5.0 공개 전 남은 순서

완료한 메모리 최적화 P0~P2 → W04 DF·W05 CS → W06 자원·회귀 → W07 설치 예제·세 보드 역할 재배치 →
W08 API·예제·지원표·readiness 마감 → Windows 최종 package·설치·lifecycle → RC → 별도 공개 승인 순서입니다.
W06은 ISO·Audio·DF·CS 전체 동시 실행을 요구하지 않으며 독립 image의 자원·수명주기를 검증합니다.
M32·M33 추가 기능과 Ubuntu/macOS 지원을 이번 릴리스의 선행조건으로 두지 않습니다.
릴리스 범위 변경은 개발 완료나 공개 승인이 아니므로 현재 version·stable index·공개 자산은 유지합니다.

현재 `M31-MEM-OPT`의 P0·P1·P2는 완료했습니다. 지원 범위 오류·최악 부하,
stack/heap 최종 크기, 동일 조건 Nordic native FLASH/RAM 비교 결과는
[262번](<../04_검증 기록/262_M31_메모리_최적화_P2_세_축_완료.md>)에 기록합니다. 제품 SDC DF IQ RX 미지원, CS 간헐 loss/gap과
SDC 내부 high-water 비노출을 P2의 추가 차단 조건으로 두지 않습니다. 이 범위 정리만으로
완료한 P2를 넘어 W04·W05 또는 릴리스까지 완료 처리하지 않습니다.

문서 전면 검토 후의 실행 순서와 Adafruit 개선 과제는
[개선 마일스톤](<../01_아두이노 코어 설계/18_문서_전면검토와_개선_마일스톤.md>)을 따릅니다.
후속 M33에는 기존 API의 목적별 예제·안내를 보강하고, 새 공개 API를 포함한 후속 ARF 과제의 배포
버전은 별도 gate에서 결정합니다. `v0.5.1`로 미리 확정하거나 기존 M34~M45를 대체하지 않습니다.

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
