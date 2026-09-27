# M30-W01 capability 실기 완료

## 결과

M30-W01을 exact Core `6254398c1ea4e7320b1905014dce1c2a405a53fc`, board
`fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3`, NCS v3.4.0에서 완료했다. 고정 NU54DK 한 대의
DAPLink MSD와 VCOM을 UID로 함께 식별한 뒤 비파괴 sector flash를 수행했고 `M30-CAP-01`의
7개 capability와 revision mismatch 0을 확인했다.

| Gate | 결과 |
| --- | --- |
| M30 capability parser | **13/13 PASS** |
| M30 readiness·canonical build matrix 포함 선택 회귀 | **31/31 PASS** |
| M12 전체 Host gate | **PASS** |
| Zephyr target build | **1/1 PASS** |
| 실제 `M30-CAP-01` | **1/1 PASS — capability 7/7, mismatch 0** |

원본은 [구조화 evidence](evidence/m30-w01-6254398c-cap/m30-capability-evidence.json)와
[UART transcript](evidence/m30-w01-6254398c-cap/m30-capability-evidence.transcript.log)에 보존한다.
HEX는 630,919 byte였고 DAPLink가 보고한 flash byte는 631,296 byte다. 공개 evidence에는 raw
probe UID 대신 SHA-256만 기록했다.

## 실제 확인한 경계

- Bluetooth Host는 connection 2, SMP·application pairing accept·SC-only·16-byte 최소 key,
  bond 4, privacy를 실제 resolved configuration으로 보고했다.
- target에서 authentication callback 등록, local LE SC OOB 생성, 동적 profile service 등록과
  MCUmgr BLE service 재등록이 모두 성공했다.
- 고정 자원은 link security context 2, pairing slot 2, OOB record 2, OOB frame 192 byte,
  bond record 4, profile entry 7, DFU slot 2다.
- MCUboot signed image와 rollback recovery는 W01에서 `source_only` 후보로 유지했다. W05/W06의
  실제 build·boot·update 증거로 승격하기 전에는 runtime PASS가 아니다.
- NFC OOB RF는 사용자 범위 결정대로 `NOT RUN`이며 지원 기능으로 표시하지 않는다.
- 외부 GPIO, mass erase, recover와 실제 전원 차단은 사용하지 않았다.

첫 원격 착수 커밋의 Windows CI는 Toolchain Git 경로가 8.3 이름과 긴 이름 사이에서 정규화되어
기존 lexical-path 회귀 한 건이 실패했다. package가 준 lexical root를 보존하도록 수정한 뒤 해당
시험과 전체 Host gate를 다시 실행해 PASS했다. 별도로 첫 target configure는 Nordic
`environment.json`의 `PYTHONPATH`를 수동 실행에 전부 적용하지 않아 실패했으며, 전체 환경을 적용한
뒤 실제 compile 오류와 분리했다. 최소 Zephyr C++ runtime에 없는 `<cstring>`은 C 호환 `<string.h>`로
교정했고 target을 새 output root에서 다시 빌드해 PASS했다.

## 다음 작업

M30은 **1/8 작업 묶음, 1/10 test ID PASS**다. 현재 작업은 M30-W02 link별 security·pairing·key
수명주기다. HOST-W01~W03은 완료 상태를 유지하며 HOST-W04~W08의 실제 Ubuntu/macOS 및 release
확장은 아직 `NOT RUN`이다. 자동 작업은 `M30-POWER-01` 실제 target USB 전원 차단 직전까지
계속하며 reset을 그 시험의 대체 근거로 사용하지 않는다.
