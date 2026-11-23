# 릴리스 자동화 안내

v0.6.0은 공개 stable입니다. 당시 C11/C12 검증에는 `host_rc_kit.py`와 `host_rc_entry.py`를 사용했습니다. 공개 자산 및 설치 결과는 [릴리스 체크리스트](<../../00_Docs/05_릴리스/v0.6.0/RELEASE_CHECKLIST.md>), 후보별 소스는 [검증 근거](<../../00_Docs/05_릴리스/v0.6.0/TESTING.md>)에서 확인하세요.

공개 v0.5.0의 도구는 `v050_release.py`입니다. 당시 정식 공개 자산과 재현 근거는 [274번 기록](<../../00_Docs/04_검증 기록/274_v0.5.0_정식_릴리스_승인과_공개.md>)에서 확인할 수 있습니다.

이 디렉터리는 제품 세대별 자동화 계약을 보존합니다. 과거 도구의 version allowlist와
게시 명령을 현재 작업에 재사용하지 않으며, 공개된 버전을 다른 byte로 다시 게시하지 않습니다.

| 제품선 | 절차 문서 | 주 도구 | 상태 |
| --- | --- | --- | --- |
| `v0.6.0` / M32·M33 | [공개 기록](<../../00_Docs/04_검증 기록/340_v0.6.0_정식_게시와_공개_설치_검증.md>) | RC kit 준비 및 실행은 `host_rc_kit.py`, `host_rc_entry.py` | 정식 공개 및 공개 URL 설치 검증 완료 |
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
v0.5.0 공개 당시 stable catalog는 `0.5.0` 하나를 제공했습니다. v0.4.1 이하와 RC package payload,
tag와 Release 자산은 삭제하지 않지만 모두 지원 종료 상태입니다. M18/M22/M27의 과거 index
identity와 역사 version 생성 allowlist는 재현·감사용이며 현재 공개 공급 목록을 뜻하지 않습니다.

비공개 v0.6.0 Host RC1 준비는 `host_rc_kit.py`·`host_rc_entry.py`·`host_native_lifecycle.py`와 [Host RC1 절차](<../../00_Docs/02_빌드 설계/15_Host_RC1_실기_도구와_증거_절차.md>)를 사용합니다. 게시 명령은 제공하지 않으며 exact source의 새 실제 검증이 필요합니다.

NU54DK CMSIS-DAP의 `ble-pair`는 C9부터 `--assert-dtr`로 VCOM 수신 준비를 명시한다.
기본 DTR=false·RTS=false 조건과 nonce 판정은 유지하며, 이 옵션은 DTR만 켠다.

### C10 SerialEcho 첫 입력 줄 동기화

NU54DK CMSIS-DAP/WSL2의 재연결 UART는 `serial` 명령에 `--synchronize-line`을 추가한다.
각 open의 LF1회·완성된 setup echo를 별도 기록하고, 그 뒤 기존2open×3fresh nonce·정확 비교·
각5초 제한을 적용한다. setup는 PASS nonce에 포함하지 않으며 DTR/RTS=false와 재시도 금지를
유지한다. 옵션 기본값은 false다. setup 오류·timeout도 FAIL로 보존한다. USB attach 후에는
Linux udev 준비와 inventory의 identity·by-id·접근 권한을 확인한다. C9 재연결 FAIL은 보존하며
C10 새 attempt의 결과만 C10으로 기록한다. BLE의 `--assert-dtr`와 다른 옵션이다.
