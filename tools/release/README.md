# 릴리스 자동화 안내

2026-09-08 예외: 소유자가 승인한 v0.3.0 미만 공급 종료와 이력 정리는
[106번 기록](<../../00_Docs/04_검증 기록/106_Git_이력_정리와_구버전_패키지_공급_종료.md>)을 따른다. v0.3.0 payload는
유지하며 catalog만 갱신한다. M18/M22의 과거 index identity는 지우지 않고 현재 catalog의
exact byte를 별도로 추가한다. 역사 버전 생성 allowlist는 공개 공급 목록이 아니다.


이 디렉터리에는 제품 세대별로 고정된 릴리스 자동화가 함께 있습니다. 과거 도구의 version
allowlist와 명령을 현재 릴리스에 재사용하지 않고, 대상 버전의 문서를 먼저 확인합니다.

| 제품선 | 절차 문서 | 주 도구 | 상태 |
| --- | --- | --- | --- |
| `v0.1.0` / M11 | [M11_README.md](M11_README.md) | `nu54_release.py` | 역사적·동결 |
| `v0.2.0` / M18 | [M18_README.md](M18_README.md) | `m18_release.py` | 역사적·동결 |
| `v0.3.0` / M22 | [M22_README.md](M22_README.md) | `m22_release.py`, `m22_cleanroom.py` | 역사적·동결 |
| `v0.4.0` / M27 | [M27_README.md](M27_README.md) | `m27_release.py`, `m27_stable_release.py` | 정식 공개·T24/T25 완료·동결 |

공통 원칙은 다음과 같습니다.

1. exact clean commit과 고정 dependency를 입력으로 사용합니다.
2. version별 package, checksum, SBOM과 evidence를 새 경로에 생성합니다.
3. 공개한 tag와 Release asset은 덮어쓰지 않습니다.
4. 스크립트의 성공을 실제 공개 승인이나 hardware 검증으로 확대하지 않습니다.
5. 현재 사용자 문서와 공개 상태는 [릴리스 문서 안내](../../00_Docs/05_릴리스/README.md)를
   단일 진입점으로 사용합니다.
