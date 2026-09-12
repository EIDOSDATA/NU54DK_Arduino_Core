# M28-W01 Capability image와 Host·target 준비

| 항목 | 결과 |
| --- | --- |
| 작업일 | 2026-09-12 |
| 시작 branch / HEAD | `main` / `0042d2c4188d973425c1e1b8713f8a5cb6433dde` |
| 시작 상태 | `origin/main` 일치, 미커밋 변경 없음, board `fe65f2f0880b…` |
| 작업 묶음 | `M28-W01` |
| 현재 판정 | **Host·target 준비 PASS / 실제 HCI NOT RUN / W01 진행 중** |
| M28 진행률 | **완료 0/8, 0%** |

## 1. 구현 범위

| 산출물 | 구현 내용 |
| --- | --- |
| `tests/zephyr/m28_ble_capability` | nRF54L15·NCS v3.4.0·SDC capability image, 필수 Host Kconfig compile-time assert |
| `M28CAP/1` | flash 뒤 PROBE/READY handshake, BEGIN, full revision, Host config, HCI version·commands·features·자원, 6개 capability, END의 고정 15줄 |
| `tests/hil/nu54dk/m28_ble_capability.py` | exact image/board/nonce 결합, 180초 timeout, raw HCI와 CAP 판정의 fail-closed 대조, JSON·raw transcript 증적 |
| `tests/host/test_m28_ble_capability.py` | 정상과 noise·중복·누락·stale nonce·wrong revision·raw feature/resource mismatch·target FAIL·timeout 검증 |
| CI target group | `v0.5.0` Zephyr group과 GitHub pinned container matrix에 W01 suite 추가 |

Capability image는 `bt_enable()` 뒤 다음 command를 실제 controller에 한 번씩 보낸다.

- Read Local Version Information
- Read Local Supported Commands
- LE Read Local Supported Features
- LE Read Maximum Advertising Data Length
- LE Read Number of Supported Advertising Sets
- LE Read Periodic Advertiser List Size
- LE Read Resolving List Size

Host parser는 출력된 CAP 문자열만 신뢰하지 않고 64-byte command mask, 8-byte LE feature mask와
자원 값을 다시 계산한다. PAwR은 controller LE feature bit 43/44를 사용한다. Multi-role은 host의
2-link/역할별 1개 구성과 central/extended advertiser command를 확인하며, 실제 동시 2-link 동작은
W02 이후 `M28-LINK-01`에서 별도로 검증한다.

## 2. 실패 분류와 수정

| 순서 | 실패 | 원인 | 수정·동일 조건 재검증 |
| --- | --- | --- | --- |
| 1 | CMake configure FAIL | CMake regex에서 `{40}` 반복 표현을 Git SHA 검사에 사용 | 길이 40과 lowercase hex 검사를 분리 |
| 2 | compile FAIL `cerrno` / `cstring` | 고정 Zephyr C++ runtime에서 해당 wrapper header가 제공되지 않음 | C header `errno.h`·`string.h`와 global 함수를 사용 |
| 3 | 첫 build의 `CONFIG_BT_PRIVACY=n` | Host privacy의 `BT_SMP` 의존 누락 | `CONFIG_BT_SMP=y` 추가, resolved `.config` 재검사 |
| 4 | build는 PASS하지만 HCI 자원 기준 미달 | SDC 기본값이 광고 data 31 byte, periodic advertiser list 0개 | 각각 255 byte·1개로 명시하고 compile-time assert 추가 |
| 5 | 첫 실보드 수집이 READY 전 noise로 FAIL | Zephyr banner와 별개인 `CONFIG_NCS_BOOT_BANNER=y`가 boot 문자열 출력 | NCS banner를 명시적으로 끄고 compile-time assert 뒤 동일 보드·UART로 재검증 |
| 6 | banner 제거 뒤 READY 앞 4-byte noise로 FAIL | target reset 동안 USB-UART가 관측한 TX high-Z 글리치 | flash 후 입력을 비우고 exact `PROBE`로 검증 세션을 arm하는 handshake 추가 |

각 수정은 이전 실패 출력 폴더를 재사용하지 않고 같은 board/SDK/toolchain 조건의 새 build로
재검증했다. 이유 없는 반복이나 결과 선별은 하지 않았다.

## 3. 검증 결과

| 검사 | 결과 |
| --- | --- |
| W01 parser·readiness·build runner 관련 Host | **PASS, 27개** (`11 + 7 + 9`) |
| 신규 C++ source clang-format 22.1.8 | **PASS** |
| `nucode.m28.ble_capability` target build | **PASS, 1/1**, 71.90초, warning 없음, NCS `995530…`, Zephyr `bf801e…`, board `fe65f2…` |
| Resolved 필수 Kconfig | **PASS, 18/18**; 2-link·extended/periodic/PAST/PAwR/privacy/link-control Host와 controller 자원 구성 |
| 최종 로컬 HEX | 753,365 byte, SHA-256 `59e643ce4ac566a93b2e57fc3f7695e875b6ef219a88253bdf00bcd77964398d` |
| 실제 `M28-CAP-01` | **NOT RUN** |

위 HEX는 미커밋 working-tree build이므로 구조·compile 검증 근거다. 실제 HIL은 commit 뒤 같은 exact
source로 다시 만든 image만 사용한다. 이 build 결과는 controller HCI PASS가 아니며 readiness의
6개 `source_status=candidate`, `runtime_hci_status=not_run`을 바꾸지 않는다.

로컬 전체 gate 중 contract 46/46, package 21/21, 문서 266/266, inventory는 PASS했다. 전체 Host
gate는 W01 관련 18/18을 포함해 R03 이전까지 PASS했지만, 기존 R03 PWM 임시 실행 파일만 Windows
Application Control 오류 4551로 2회 실행이 차단됐다. 같은 시험의 compile과 analog·stream 실행은
PASS했으며 M28 변경 경로와 무관하다. 이 환경 실패를 제품 또는 W01 PASS로 바꾸지 않고 exact push
commit의 독립 GitHub CI에서 전체 Host gate를 다시 확인한다.

## 4. 다음 실행

다음 한 단계는 NU54DK 한 대의 USB/SWD/UART가 연결되고 debug-control `DISABLE_SWD`와
`DISABLE_UART`가 모두 연결 위치인지 확인한 뒤, clean exact commit image로 `M28-CAP-01`을
한 번 실행하는 것이다. GPIO 점퍼와 두 번째 보드는 필요 없다.

결과가 실패하면 USB/UART endpoint와 image identity를 먼저 대조한다. 연결이 정상이면
CMSIS-DAP으로 controller·GPIO·오류 레지스터를 확보해 원인을 분류하고, 수정 뒤 같은 조건으로
재검증한다. 실제 HCI 6개가 모두 확인되기 전에는 W01을 완료하거나 W02 구현 입력을 PASS로
승격하지 않는다.
