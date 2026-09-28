# 릴리스 자동화 안내

정식 지원 버전은 **v0.5.0**입니다. 설치 방법은
[릴리스 안내](../../00_Docs/05_릴리스/README.md)를, 정식 package·승인·공개 절차는
`v050_release.py`와 [v0.5.0 TODO](../../00_Docs/TODO_v0.5.0.md)를 확인합니다.
후속 계획은 [v0.6.0](../../00_Docs/TODO_v0.6.0.md)에 M32·M33, v0.7.0에 M34~M37 Security,
v0.8.0에 M38~M41 Radio/Network, v0.9.0에 M42~M45 Matter를 배정합니다. 이는 구현·공개 완료나
현재 제품 version 변경이 아닙니다. Ubuntu/macOS의 기존 세 Host 계획·OS별 최종 gate를 유지하며,
HOST-W04~HOST-W08은 사용자 보류 상태입니다. 별도 재개 승인과 실물 gate 없이 새 OS 지원을 확정하지 않습니다.

정식 공개에서는 RC2의 Full RC package·evidence와 이후 runtime PM 교정 결과를 검토하고,
stable package를 최종 exact commit에서 두 번 새로 생성했습니다. 전체 예제 113/113·설치 수명주기·
대표 실물 Upload와 사용자 GUI 연속 Upload는 각 source와 실행 범위를 구분합니다. 최종 판정과
공개 결과는 [274번 기록](<../../00_Docs/04_검증 기록/274_v0.5.0_정식_릴리스_승인과_공개.md>)을 따릅니다.

이 디렉터리는 제품 세대별 자동화 계약을 보존합니다. 과거 도구의 version allowlist와
게시 명령을 현재 작업에 재사용하지 않으며, 공개된 버전을 다른 byte로 다시 게시하지 않습니다.

| 제품선 | 절차 문서 | 주 도구 | 상태 |
| --- | --- | --- | --- |
| `v0.5.0` / M31 | [v0.5.0 TODO](../../00_Docs/TODO_v0.5.0.md) | `v050_release.py`, `m31_release.py`, `m31_windows_lifecycle.py`, `m31_windows_example_shard.py`, `m31_ci_aggregate.py` | 정식 공개·stable catalog·공개 smoke 완료 |
| `v0.4.1` 유지보수 | [v0.4.1 TODO](../../00_Docs/TODO_v0.4.1.md) | `v041_release.py` | 역사적·지원 종료 |
| `v0.4.0` / M27 | [M27_README.md](M27_README.md) | `m27_release.py`, `m27_stable_release.py` | 정식 공개·T24/T25 완료·동결 |
| `v0.3.0` / M22 | [M22_README.md](M22_README.md) | `m22_release.py`, `m22_cleanroom.py` | 역사적·동결 |
| `v0.2.0` / M18 | [M18_README.md](M18_README.md) | `m18_release.py` | 역사적·동결 |
| `v0.1.0` / M11 | [M11_README.md](M11_README.md) | `nu54_release.py` | 역사적·동결 |

## 공통 계약

공통 원칙은 다음과 같습니다.

1. exact clean commit과 고정 dependency를 입력으로 사용합니다.
2. version별 package, checksum, SBOM과 evidence를 새 경로에 생성합니다.
3. 공개한 tag와 Release asset은 덮어쓰지 않습니다.
4. 스크립트의 성공을 실제 공개 승인이나 hardware 검증으로 확대하지 않습니다.
5. 현재 사용자 문서와 공개 상태는 [릴리스 문서 안내](../../00_Docs/05_릴리스/README.md)를
   단일 진입점으로 사용합니다.
6. M31 기능 완료, RC 검증과 stable 게시를 구분합니다. Windows exact package의 이중 재현·설치·
   전체 예제·lifecycle·공개 asset을 확인합니다. 후속 OS의 실물 gate는 해당 OS 지원 릴리스로 이관합니다.

## 구버전 공급 종료 이력

2026-09-08 소유자가 승인한 v0.3.0 미만 공급 종료와 이력 정리는
[106번 기록](<../../00_Docs/04_검증 기록/106_Git_이력_정리와_구버전_패키지_공급_종료.md>)에 보존합니다.
v0.5.0 stable catalog는 `0.5.0` 하나만 제공합니다. v0.4.1 이하와 RC package payload,
tag와 Release 자산은 삭제하지 않지만 모두 지원 종료 상태입니다. M18/M22/M27의 과거 index
identity와 역사 version 생성 allowlist는 재현·감사용이며 현재 공개 공급 목록을 뜻하지 않습니다.
