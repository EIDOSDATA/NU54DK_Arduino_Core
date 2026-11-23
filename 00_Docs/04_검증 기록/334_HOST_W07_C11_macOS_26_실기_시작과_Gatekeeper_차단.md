# HOST-W07 C11 — macOS 26 준비와 Gatekeeper 차단

2026-11-23, 실제 macOS 26.7.3 (25G342) 네이티브 Apple Silicon ARM64에서 C11 실기 준비를 시작했다. Host6/8, 지원 목표 검증3/5, M33 수락6/8·기술5/8이다.

| 입력 | 검증 결과 |
| --- | --- |
| 인계 당시 checkout·원격 | `Dev-0.6.0-M33`의 `dfdfb1834ecabcf703eef71eaf3d24db2e490a3d`, clean checkout, Windows 해제 receipt와 일치 |
| Windows 종료와 exact 문서 CI | `RELEASED_FOR_MAC_HANDOFF`, writer 해제 확인, native·heavy·WSL 실행 없음. [CI43817305059/attempt1](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/43817305059) 8 PASS·범위 SKIP 1 |
| 전달 ZIP | SHA-256 `190de259c5cedd0f01e9244d3d2eed332863fb34cf78451cc5a62b38f5f07cfb`. 외부 checksum·내부 SHA256SUMS·manifest의 58개 항목 확인 |
| C11 제품과 kit | `d304f369c0d3ebbac35c3bf0ef3b7b2887f40dfa`, 201857017 bytes 및 SHA-256 `c1792818979453ce3150d7b19abf960f3d14a31f970c4578f5f41afcf5cf8208` 일치 |
| 보드와 SDK pin | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3`, NCS 3.4.0, macOS bundle `ccc010f809`. 사용자 관리자 인증 뒤 `/opt/nordic/ncs` 생성 및 쓰기 권한 확인 |
| Mac 실행 | 새 로컬 root와 단일 writer claim, `mac26-c11-a001.r3nEa6`. Windows/WSL 실행 상태는 역사 증거로 보존 |

## 새 실패와 진단

원본 Mac 전달본에서 kit를 추출한 뒤 `START.sh --work-root <Mac work root> plan`을 실행했다. macOS가 kit 내장 Python 3.12의 실행을 차단했다. 프로세스는 SIGKILL(9)로 종료됐으며 stdout·stderr가 비어 있었다. Kernel/AMFI는 CMS 서명 문제를 기록했고 `syspolicyd`에는 Gatekeeper 거부가 남았다. 원본 OS 로그 SHA-256은 `482cc2018aed4897ae6c635c0136724f86c4975163fda801a037981554c4f96b`다.

같은 hash의 내장 Python archive를 별도 폴더에 추출해 조사했다. 실행 파일은 ARM64이며 SHA-256은 `7a427de7a538c033f821bae69d18dba1fcf01e1947f8fdfece0d9654f680a787`다. `codesign --verify --strict`는 파일 무결성을 통과했다. `codesign -d`에서 ad hoc 서명이 확인됐고 `spctl --assess --type execute`는 exit 3으로 거부했다. 정책 평가 로그 SHA-256은 `ef5473e950c50a5b7b9a90634f4aadfe709919473bee6ed1d7667be0675db71c`다. 전달본과 추출본의 quarantine 상태를 보존했다.

새 Mac의 IORegistry 사전 확인에서 NU54DK USB 장치 두 대(`0d28:0204`)가 열거됐다. Kit probe·serial·path inventory 및 포트 접근 확인은 후속 단계다. Arduino IDE 2.3.11 ARM64 설치본은 확인했으며 격리 설치·예제 발견·Verify는 아직 대기 중이다.

| 단계 | 결과 |
| --- | --- |
| 원본 확인·SDK 경로 준비 | PASS |
| C11 `plan` Mac a001 | FAIL — Gatekeeper 실행 차단 |
| SDK 설치/verify·lifecycle·대표 build·kit inventory | NOT_RUN |
| macOS 26 USB/Blink/serial/debug/물리 재연결/IDE 및 별도 BLE | NOT_RUN |
| macOS 27 실기 | NOT_RUN |

보드 flash·reset·halt·UART open은 시작 전에 차단됐다. 원본 로그, 종료 상태, 해시, writer 원장은 Mac 실행 `control/`에 보존한다. macOS가 해당 파일에 정상 승인 경로를 제공하는지 확인한 뒤 원본 kit와 새 attempt로 재개한다. Mac26·27 software CI와 C5/C10 실적은 별도 원본에 남아 있다. W06은 실제 PASS46·명시 수락 #29·40·44이며 #29 분석은 유예한다.
