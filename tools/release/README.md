# 릴리스 자동화 안내

현재 설치·지원 버전은 **v0.4.1 하나**입니다. 설치·지원 문서는
[릴리스 안내](../../00_Docs/05_릴리스/README.md), v0.4.1 유지보수 절차는
`v041_release.py`와 [v0.4.1 TODO](../../00_Docs/TODO_v0.4.1.md)를 확인합니다.
현재 `main`은 `0.4.1-dev` 개발 소스이며 M31 진행 결과를 공개 v0.4.1 package 지원 범위로
해석하지 않습니다. v0.5.0은 아직 공개하지 않았으며 M31 완료 뒤 Windows 10/11 x64 우선
릴리스로 준비합니다. M32/M33 추가 기능과 Ubuntu/macOS 지원은 버전 미정인 후속 제품선입니다.

이 디렉터리는 제품 세대별 자동화 계약을 보존합니다. 과거 도구의 version allowlist와
게시 명령을 현재 작업에 재사용하지 않으며, 공개된 버전을 다른 byte로 다시 게시하지 않습니다.

| 제품선 | 절차 문서 | 주 도구 | 상태 |
| --- | --- | --- | --- |
| `v0.4.1` 유지보수 | [v0.4.1 TODO](../../00_Docs/TODO_v0.4.1.md) | `v041_release.py` | 현재 설치·지원 기준 |
| `v0.5.0` / M31 | [v0.5.0 TODO](../../00_Docs/TODO_v0.5.0.md) | 새 version 전용 절차·gate 준비 필요 | 미공개; M31 8/8 뒤 Windows package·설치·RC 검증 |
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
6. M31 기능 완료와 최종 배포 검증을 구분합니다. Windows exact package의 이중 재현·설치·
   전체 예제·lifecycle·RC 결과를 확인한 뒤 별도 공개 승인을 받습니다. 후속 OS의 필수 실물
   gate는 해당 OS 지원 릴리스로 이관하며 생략·완료 처리하지 않습니다.

## 구버전 공급 종료 이력

2026-09-08 소유자가 승인한 v0.3.0 미만 공급 종료와 이력 정리는
[106번 기록](<../../00_Docs/04_검증 기록/106_Git_이력_정리와_구버전_패키지_공급_종료.md>)에 보존합니다.
이후 v0.4.1부터 stable catalog는 `0.4.1` 하나만 제공합니다. v0.4.0 이하의 package payload,
tag와 Release 자산은 삭제하지 않지만 모두 지원 종료 상태입니다. M18/M22/M27의 과거 index
identity와 역사 version 생성 allowlist는 재현·감사용이며 현재 공개 공급 목록을 뜻하지 않습니다.
