# M21 BLE 보안과 표준 Profile 검증

| 항목 | 내용 |
| --- | --- |
| 문서 ID | VALIDATION-M21-001 |
| 문서 개정 | 1.1 |
| 상태 | **M21 완료 — 자동 RF HIL과 Windows 11 실제 HID 검증 PASS** |
| 최종 갱신일 | 2026-09-01 |
| 대상 | `v0.3.0` M21 |
| 보드 | `nrf54l15dk/nrf54l15/cpuapp/nu54dk` |
| SDK | NCS `v3.4.0`, Zephyr `4.4.0` |

## 1. 목적과 최종 판정

M21은 `NUCODE_BLE` 공통 lifecycle 위에 pairing·bond 관리와 Battery Service(BAS),
Device Information Service(DIS), 암호화된 HID keyboard를 추가한다. 이 기록은 source/host 계약,
production target build, 두 NU54DK 사이의 RF protocol HIL과 실제 Windows 입력 확인을
서로 다른 판정 계층으로 분리한다.

| 계층 | 결과 |
| --- | --- |
| 공개 API·보안·negative M21 host 계약 | **PASS, 39/39** |
| 전체 host 회귀 | **408 total — 406 PASS, 2 skipped** |
| CI contract 회귀 | **PASS, 33/33** |
| Markdown UTF-8·로컬 링크 검사 | **PASS, 83 files** |
| Arduino CLI SecureKeyboard·예제 탐색 | **PASS** |
| exact-commit Arduino SecureKeyboard build·upload | **PASS**, Flash 260,692 B / RAM 69,436 B |
| NU54DK production contract image | **PASS**, Flash 159,696 B / RAM 41,672 B |
| NU54DK board/system + BLE security 통합 image | **PASS**, Flash 174,724 B / RAM 42,444 B |
| NU54DK HIL Central role image | **PASS**, Flash 236,792 B / RAM 54,840 B |
| NU54DK HIL Peripheral role image | **PASS**, Flash 236,388 B / RAM 54,840 B |
| exact-commit 두 보드 RF HIL | **PASS**, evidence schema 3 |
| Windows 11 실제 HID pairing·문자 입력·bond 재연결 | **PASS** |
| 스마트폰 HID 호환성 | **NOT RUN — M21 완료 필수 조건 아님** |

자동 검증 범위는 exact clean commit에서 만든 pristine image와 서로 다른 NU54DK 두 대를 사용해
완료했다. 자동 RF HIL은 암호화된 GATT/HID protocol을 검증하고, 별도의 Windows 11 수동 검증은
운영체제 pairing UI, 실제 키보드 입력과 재부팅 뒤 bond 복원을 확인했다. 자동·수동 완료 조건을
모두 충족했으므로 M21은 **완료**다. 다만 `v0.3.0` stable 지원 선언은 AC-02·AC-03과 M22 통합
gate 뒤에만 수행한다.

## 2. exact revision과 실행 환경

| 항목 | 값 |
| --- | --- |
| Core revision | `065d4f573618aca5da1e715915622e987208b775` |
| Board package revision | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |
| Evidence 생성 UTC | `2026-08-31T14:09:16.017248Z` |
| Evidence 상태 | `schema_version=3`, `status=passed` |
| 실행 nonce | `4fc3a7fd39b216a27c3f4ac1c640aaa5` |
| Central | DAPLink `5415360300052840fcd47678fd7d106d`, `COM13` |
| Peripheral | DAPLink `5415360300052840d9e1e32cc887aaf1`, `COM14` |
| Mass erase 요청 | `false` |
| Factory reset 실행 | `false` |

위 `065d4f5` 자동 RF HIL 기준선에서는 M21 host **38/38**, 전체 host **407개 중 405 PASS,
2 skipped**, Markdown UTF-8·로컬 링크 **82/82 files PASS**였다. 이 수치는 당시 자동 evidence의
revision과 함께 보존한다. `d1902b1` IO capability 교정 뒤 최신 software 회귀 수치는 5.1절과
Windows 수동 결과는 8절에 별도로 기록한다.

두 role의 pristine build record는 모두 Core/Board revision을 위 값으로 고정했고 SHA-256은 다음과
같다.

| Role | Build record SHA-256 |
| --- | --- |
| Central | `c8ee555649d35607b1835836f46db485879035aad4138fc4ab2d63a8f2fb2930` |
| Peripheral | `c8ee555649d35607b1835836f46db485879035aad4138fc4ab2d63a8f2fb2930` |

## 3. 구현 범위와 lifecycle ownership

공개 헤더 `libraries/NUCODE_BLE_Security/src/NUCODE_BLE_Security.h`는 Zephyr type을 노출하지 않고
`NUCODE_BLE.h`를 포함해 다음 기능을 제공한다.

- `SecurityManager`: L2/L3/L4 보안 요청, Just Works·passkey 응답, 취소·timeout, bond 열람·개별 삭제·전체 삭제
- `SecurityIoCapability`: 실제 화면·숫자 입력·확인 버튼 조합에 맞춘 SMP IO capability 선택
- `BatteryService`: BAS level read와 notification
- `DeviceInformationService`: runtime manufacturer/model/serial과 revision 정보
- `HidKeyboard`: 표준 keyboard report map, 8-byte input report, press/release

Bluetooth stack과 연결 callback 소유권은 M19/M20의 공통 backend에 남긴다.

- M21은 `bt_enable()`과 `settings_load()`를 호출하지 않는다.
- M21은 `BT_CONN_CB_DEFINE` 또는 별도 `bt_conn_cb`를 등록하지 않는다.
- 공통 backend의 `securityConnected`, `securityDisconnected`, `securityChanged` hook을 strong 구현한다.
- SMP auth/auth-info callback의 bounded event는 queue를 거쳐 `BLESecurity.poll()`의 Arduino main-thread에서 전달한다.
- 같은 boot의 `settings_save()` 반환값이나 `bt_foreach_bond()` 목록만으로 persistence 성공을 선언하지 않는다.
- `BondState`는 `none`, `persistence_pending`, `restored_candidate`, `verified`, `removal_requested`를 구분한다.
- pairing 직후는 `persistence_pending`이며 `bonded()==false`다. 다음 warm reboot에서 로드된 peer가 새 pairing 없이 L2 이상 `security_changed`에 성공해야만 `verified`와 `bonded()==true`가 된다.
- 연결 주소가 bond 목록에 있다는 이유만으로 `paired()` 또는 `bonded()`를 true로 만들지 않는다. 보안 오류·disconnect는 해당 peer 후보 상태를 안전하게 폐기한다.
- `eraseBond()`와 `eraseAllBonds()`의 true는 stack이 제거 요청을 수락했다는 뜻뿐이다. 영속 삭제는 양쪽 warm reboot 뒤 `bondCount()==0`과 old-key 재연결 실패로 검증한다.
- 제거 범위는 BLE bond뿐이며 mass erase나 factory reset을 수행하지 않는다.

Passkey와 key material은 Core, 예제와 HIL token에 출력하지 않는다. HIDS attribute와 notification은
최소 `BT_SECURITY_L2` 암호화를 요구하며, HIL은 보안 전 report map read가 ATT 오류로 거부되는지도
확인한다.

HIDS lifecycle은 전용 mutex와 exact connection slot로 `begin/connect/disconnect/send`를 직렬화한다.
Protocol Mode callback은 peer별 boot/report mode를 저장하며 boot mode에서는
`bt_hids_boot_kb_inp_rep_send()`, report mode에서는 `bt_hids_inp_rep_send()`를 사용한다. Keyboard
descriptor의 논리 최대값 `0x65`를 넘는 usage는 전송 전에 거부한다.

## 4. 보안 구성 경계

`libraries/NUCODE_BLE_Security/zephyr/ble-security.conf`는 SMP, bond, Settings/ZMS, BAS, runtime DIS와
encrypted HIDS를 활성화한다. 최대 bond 수는 4개다. nRF54L15 RRAM에서 board/system feature와 함께
사용할 때도 `CONFIG_ZMS=y`, `CONFIG_SETTINGS_ZMS=y`인 단일 backend만 선택하며 NVS backend는
활성화하지 않는다. 실제 `NUCODE_NU54DK`와 `NUCODE_BLE_Security` 동시 포함 target도 이 조합으로
compile/link했다.

`CONFIG_BT_SMP_SC_PAIR_ONLY=n`은 Zephyr의 명시적 Just Works `pairing_confirm` callback을 사용할 수
있게 하는 선택이다. Secure Connections를 지원하는 양쪽 장치는 Secure Connections로 협상하지만,
이 설정은 legacy pairing fallback도 허용한다. legacy fallback을 금지해야 하는 제품은
`SecurityLevel::secure_connections`로 L4를 요청하고 제품 profile에서 SC-only 정책을 별도로 고정해야
한다. M21 기본값인 `SecurityLevel::encrypted`는 암호화와 bond 저장을 보장하지만 MITM 인증을
보장한다고 확대 해석하지 않는다.

`SecurityConfig::io_capability`은 장치가 실제 제공하는 사용자 입출력보다 강하게 설정하지 않는다.
Core는 다음 callback 조합만 Zephyr에 등록하므로 OS가 존재하지 않는 화면이나 숫자 입력을 요구하지
않는다.

| `SecurityIoCapability` | 공개하는 SMP 사용자 입출력 | 일반 pairing 경로 |
| --- | --- | --- |
| `no_input_output` | 화면·숫자 입력 없음 | Just Works; L2 암호화 가능, MITM 인증 없음 |
| `display_only` | passkey 표시 | 상대 장치의 passkey 입력 |
| `keyboard_only` | passkey 입력 | 로컬 숫자 입력 |
| `display_yes_no` | passkey 표시 + 일치 확인 | Numeric Comparison |
| `keyboard_display` | 표시·입력·일치 확인 | 협상된 passkey/Numeric Comparison |

NU54DK `SecureKeyboard` 예제는 숫자 화면과 키패드가 없고 SW0 확인만 제공하므로
`no_input_output`을 명시한다. 이 구성에서 `pairing_requested`를 받은 뒤 SW0이
`acceptPairing(true)`를 호출하는 경로가 유효하다. `display_yes_no` 또는 `keyboard_display`가 만든
`passkey_confirmation_requested`에는 실제 화면의 6자리 값을 사람이 비교한 뒤
`confirmPasskey()`로 응답해야 하며, 화면 없는 장치가 이를 흉내 내서는 안 된다.

## 5. 자동 검증

### 5.1 Host·CI·문서 회귀

M21 Host contract와 parser/negative test는 다음 명령으로 실행한다.

```powershell
python -m unittest `
  tests.host.test_m21_ble_security_contract `
  tests.host.test_m21_ble_security_negative `
  tests.host.test_m21_ble_security_hil -v
```

최종 revision에서 M21 **39/39 PASS**를 확인했다. 주요 negative 경계는 stack 중복 초기화·별도
connection callback 금지, 평문 HIDS 전송 금지, 고정 passkey와 secret 로그 금지, 같은 boot의
false verified bond 금지, 삭제 요청 뒤 reboot 전 상태를 삭제 완료로 오판하는 경우, stale
nonce·target FAIL·restore 단계 재-pair·profile token 누락, 128-bit RF nonce binding 누락·축소를
거부하는 것이다. 실제 IO capability와 등록 callback의 exact 조합, 잘못된 enum 값 거부와 화면 없는
SecureKeyboard의 `no_input_output` 선택도 회귀 계약에 포함한다.

전체 host 회귀는 **408개 중 406 PASS, 2 skipped**, CI contract는 **33/33 PASS**, Markdown
UTF-8·로컬 링크 검사는 **83/83 files PASS**였다. Arduino library discovery 단계에서는 공개 헤더만 노출하고 Zephyr 내부
구현은 제외한다. 실제 Arduino CLI에서 `SecureKeyboard` compile과 전체 예제 탐색을 실행해
`PASS: m21`, `PASS: examples`를 확인했다. `NUCODE_BLE_Security`는 공통 BLE lifecycle에 의존하므로
`nucode.ble.nus`와 함께 선택되는 정상 조합을 충돌로 처리하지 않으며, 최종 feature profile은
`ble`로 제한한다.

### 5.2 Pristine target build

NCS toolchain 환경에서 production contract와 두 role image를 다음과 같이 build한다.

```powershell
$CoreRoot = "C:\Users\eidos\GitHub\NU54DK_Arduino_Core"
$Toolchain = "C:\ncs\toolchains\dcbdc366a1"
$West = "$Toolchain\opt\bin\Scripts\west.exe"
$BoardRoot = "$CoreRoot\board_package\NU54DK_Zephyr_DTS"
$env:ZEPHYR_BASE = "C:\ncs\v3.4.0\zephyr"
$env:PATH = "$Toolchain;$Toolchain\mingw64\bin;$Toolchain\bin;" +
  "$Toolchain\opt\bin;$Toolchain\opt\bin\Scripts;$Toolchain\opt\nanopb\generator-bin;" +
  "$Toolchain\nrfutil\bin;$Toolchain\opt\zephyr-sdk\gnu\arm-zephyr-eabi\bin;$env:PATH"

& $West build -p always -b "nrf54l15dk/nrf54l15/cpuapp/nu54dk" `
  -d "$env:TEMP\nu54dk-m21-contract" "$CoreRoot\tests\zephyr\m21_ble_contract" `
  -- "-DBOARD_ROOT=$BoardRoot" "-DEXTRA_ZEPHYR_MODULES=$CoreRoot"

& $West build -p always -b "nrf54l15dk/nrf54l15/cpuapp/nu54dk" `
  -d "$env:TEMP\nu54dk-m21-board-contract" "$CoreRoot\tests\zephyr\m21_ble_board_contract" `
  -- "-DBOARD_ROOT=$BoardRoot" "-DEXTRA_ZEPHYR_MODULES=$CoreRoot"

& $West build -p always -b "nrf54l15dk/nrf54l15/cpuapp/nu54dk" `
  -d "$env:TEMP\nu54dk-m21-hil-central" "$CoreRoot\tests\zephyr\m21_ble_hil" `
  -- "-DBOARD_ROOT=$BoardRoot" "-DEXTRA_ZEPHYR_MODULES=$CoreRoot" "-DM21_ROLE=central"

& $West build -p always -b "nrf54l15dk/nrf54l15/cpuapp/nu54dk" `
  -d "$env:TEMP\nu54dk-m21-hil-peripheral" "$CoreRoot\tests\zephyr\m21_ble_hil" `
  -- "-DBOARD_ROOT=$BoardRoot" "-DEXTRA_ZEPHYR_MODULES=$CoreRoot" "-DM21_ROLE=peripheral"
```

최종 pristine build의 사용량은 다음과 같다.

| Image | Flash | RAM |
| --- | ---: | ---: |
| Production contract | 159,696 B | 41,672 B |
| Board/system + BLE security contract | 174,724 B | 42,444 B |
| Central HIL | 236,792 B | 54,840 B |
| Peripheral HIL | 236,388 B | 54,840 B |

관찰된 NCS HIDS 헤더의 deprecated attribute warning은 upstream header의 C++ 진단이며 M21 source
compile/link 오류가 아니다.

## 6. 두 보드 RF HIL 절차

`tests/zephyr/m21_ble_hil`은 같은 source에서 Central과 Peripheral role별 HEX를 만든다. 추가 신호
배선은 없으며 각 NU54DK의 DAPLink USB와 BLE RF link만 사용한다. Runner
`tests/hil/nu54dk/m21_ble_security.py`는 서로 다른 DAPLink UID, MSD volume과 UART를 요구하고
role별 image SHA-256이 동일하면 실행을 거부한다.

자동 순서는 다음과 같다.

1. 두 보드의 기존 BLE bond 제거 요청 뒤 양쪽을 warm reboot하고 `bond_count=0`을 확인한다.
2. fresh pairing에서 상태가 `persistence_pending`이고 `bonded()==false`인지 확인한다.
3. Central이 보안 전 encrypted HIDS read 거부를 확인한다.
4. 암호화 뒤 BAS read `73`, notification `72`, DIS 문자열과 HID 8-byte `A` key-down/zero release report를 확인한다.
5. 두 보드를 warm reboot하고 새 pairing event 없이 저장 key로 L2가 복원돼 `verified`가 되는지 확인한다.
6. 양쪽 bond 제거 요청 뒤 다시 양쪽을 warm reboot하고 `bond_count=0`을 확인한다.
7. 이전 key 재연결은 새 pairing을 요구하며, runner가 이를 거부했을 때 암호화가 성립하지 않는지 확인한다.
8. 명시적 repair pairing으로 BAS/DIS/HID protocol을 재검증하고 양쪽 final token을 확인한다.

Runner는 실행마다 128-bit nonce를 만든다. Peripheral은 그 전체 128 bit를 binary manufacturer data로
광고하고 Central은 connectable advertising payload에서 company ID와 16-byte nonce를 exact-match한
뒤에만 주소 연결을 시작한다. 같은 이름의 stale image나 주변 M21 장치는 nonce가 일치하지 않으면
무시한다. UART transcript에 nonce를 붙이는 것만으로 RF peer binding을 주장하지 않는다.

Peripheral의 advertising 시작 또는 Central의 연결 시도가 보안·pairing·bond 진행 전에 끊기는 경우,
callback에서는 재시도를 직접 실행하지 않고 main-loop action만 예약한다. Main loop는 **500 ms** 뒤
scan/advertising을 다시 시작하며, 이 bounded recovery는 **phase당 최대 3회**만 허용한다. 보안이나
pairing, persistence가 시작된 이후의 disconnect는 재시도하지 않고 fail-closed 처리한다. 공개 GAP
callback이 raw HCI disconnect reason을 보존하지 않으므로 이 복구를 특정 HCI reason에 대한 처리라고
단정하지 않는다.

Runner는 다음 UART 명령만 사용한다.

```text
NUCODE_M21_CLEAR:<32자리 소문자 hex nonce>
NUCODE_M21_START:<32자리 소문자 hex nonce>
NUCODE_M21_REBOOT:<32자리 소문자 hex nonce>
NUCODE_M21_ERASE:<32자리 소문자 hex nonce>
NUCODE_M21_PROBE:<32자리 소문자 hex nonce>
NUCODE_M21_REPAIR:<32자리 소문자 hex nonce>
```

exact revision의 pristine role image는 다음 형태로 실행했다.

```powershell
$Commit = git -C $CoreRoot rev-parse HEAD
$PeripheralHex = "$env:TEMP\nu54dk-m21-hil-peripheral\m21_ble_hil\zephyr\zephyr.hex"
$CentralHex = "$env:TEMP\nu54dk-m21-hil-central\m21_ble_hil\zephyr\zephyr.hex"
$Evidence = "$CoreRoot\build\m21\hil\m21-ble-security-$($Commit.Substring(0,7)).json"

python "$CoreRoot\tests\hil\nu54dk\m21_ble_security.py" `
  --peripheral-hex $PeripheralHex `
  --central-hex $CentralHex `
  --peripheral-board-id "5415360300052840d9e1e32cc887aaf1" `
  --central-board-id "5415360300052840fcd47678fd7d106d" `
  --expected-core-revision $Commit `
  --evidence $Evidence
```

두 역할의 기대 final token은 실행 nonce와 다음 payload를 가진다.

```text
NUCODE_M21_<CENTRAL|PERIPHERAL>:FINAL:PASS:pairing=PASS:bond_restore=PASS:erase_reboot=PASS:old_key_reconnect=REJECTED:repair=PASS:bas=PASS:dis=PASS:hid_protocol=PASS:nonce=<nonce>
```

Parser는 `first/restore/erased_probe/repair`, pairing event 수 `(1, 0, 1)`, bond count
`(1, 1, 0, 1)`, 상태 `(persistence_pending, verified, none, persistence_pending)`, encrypted
GATT negative, BAS/DIS/HID token 순서와 각 phase의 `rf_nonce_binding_bits=128`을 검증한다. 이전
실행 token, 누락·변조 token, 축소된 RF nonce binding, target FAIL과 서로 다른 실행 nonce를
fail-closed로 거부한다.

## 7. exact RF HIL 결과와 Evidence

Evidence 경로는 다음과 같다.

`build/m21/hil/m21-ble-security-065d4f5.json`

| 로컬 자산 | 경로 |
| --- | --- |
| PASS evidence JSON | `build/m21/hil/m21-ble-security-065d4f5.json` |
| Central raw UART | `build/m21/hil/m21-ble-security-065d4f5.central.transcript.log` |
| Peripheral raw UART | `build/m21/hil/m21-ble-security-065d4f5.peripheral.transcript.log` |

| 검증 항목 | Central | Peripheral |
| --- | --- | --- |
| Final | PASS | PASS |
| Phase | `first`, `restore`, `erased_probe`, `repair` | 동일 |
| Pairing events | `1 / 0 / 1` | `1 / 0 / 1` |
| Bond counts | `1 / 1 / 0 / 1` | `1 / 1 / 0 / 1` |
| Bond states | `persistence_pending / verified / none / persistence_pending` | 동일 |
| RF nonce binding | 128 bit | 128 bit |
| Old key reconnect | REJECTED | REJECTED |
| Erase + warm reboot | PASS | PASS |
| Repair pairing | PASS | PASS |

BAS read/notification, DIS read, 보안 전 encrypted GATT negative, encrypted HID report protocol은 모두
PASS였다. Restore phase의 pairing event는 0이므로 새 pairing이 아니라 저장된 key 복원임을
확인했다. 삭제 뒤 bond count는 0이고 old key는 거부됐으며, 명시적 repair pairing 뒤 전체 profile
protocol을 다시 확인했다.

### 7.1 Image와 transcript 무결성

| 자산 | SHA-256 | Flash sequence |
| --- | --- | ---: |
| Central `zephyr.hex` | `b148b8914b8a542068cbe5d77434e1246032e59d87acbaf157997a2082a4e6e2` | 57 |
| Peripheral `zephyr.hex` | `9de308dee13e1132b91c8c5af1d6b4ea90579e455cedded8b5a955dac06da55e` | 64 |
| Central raw UART transcript | `7bf15a33d536977953e7d7822e57d61fbeec9a50246d740590e928afe256e16a` | — |
| Peripheral raw UART transcript | `acb8d2ca7178d6357bf3af8037fa99f0c6d64ffabe547dd9eb642e45c5d1ea35` | — |
| Evidence JSON | `6ec9a9783a19d49c8abe73a210c0371786725451c8a7daa86d9ec2d6178fdc69` | — |

Evidence coverage와 안전 경계는 다음과 같다.

- `hid_report_protocol=true`
- `bond_persistence_pending_not_verified_same_boot=true`
- `bond_delete_warm_reboot_zero=true`
- `old_key_reconnect_rejected=true`
- `rf_nonce_binding_bits=128`
- `windows_or_smartphone_hid_input=false`
- `manual_os_hid_confirmation_pending=true`
- `mass_erase_requested=false`
- `factory_reset_executed=false`

기존 evidence 파일은 `--overwrite-evidence`를 명시하지 않으면 덮어쓰지 않는다. PASS JSON과 양쪽
raw transcript는 같은 디렉터리에 생성되며, evidence가 기록한 SHA-256으로 exact 실행 자산을
상호 확인한다.

자동 evidence의 `windows_or_smartphone_hid_input=false`와
`manual_os_hid_confirmation_pending=true`는 해당 자동 실행 시점의 역사 기록이므로 수정하거나
덮어쓰지 않는다. 다음 절의 별도 수동 결과가 OS HID 완료 증거를 보완한다.

## 8. Windows 11 실제 HID 수동 검증

### 8.1 환경과 exact image

| 항목 | 값 |
| --- | --- |
| 실행일 | 2026-09-01 |
| Core revision | `d1902b16804a27b77b153eeb9d11a10e088a59ae` |
| Board package revision | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |
| Arduino FQBN | `nucode:zephyr:nu54dk:feature_set=ble,upload_probe=pyocd_uid` |
| Board | DAPLink `5415360300052840fcd47678fd7d106d`, `COM13` |
| 운영체제 | Windows 11 Pro 25H2 x64, build `26200.9168` |
| Bluetooth adapter | Intel Wireless Bluetooth, driver `23.140.0.5` |
| NCS / Zephyr | NCS `v3.4.0` / Zephyr `4.4.0` |
| Arduino build | Flash 260,692 B / RAM 69,436 B |
| HEX SHA-256 | `acd87094e6fb8be64810c91cc14e3d0a83ad214359b83d833b068f5394720b70` |
| Mass erase / recover / factory reset | 사용하지 않음 |

Arduino CLI의 새 build path에서 build record의 Core revision `d1902b16804a`, Board revision
`fe65f2f0880b`, BLE profile과 `nucode.ble.security` feature를 확인한 뒤 같은 manifest를 pyOCD로
업로드했다. 최초 SWD attach의 `No ACK`는 100 kHz under-reset hardware reset으로 target 연결만
복구했고, 이후 일반 sector erase upload를 성공시켰다. mass erase와 recover는 실행하지 않았다.

### 8.2 발견한 Windows pairing 결함과 수정

수정 전 Core는 passkey display·entry·confirm callback을 모두 등록해 Zephyr가 NU54DK를
`KeyboardDisplay`로 판단하게 했다. Windows는 이를 근거로 6자리 Numeric Comparison을 선택했지만,
화면 없는 `SecureKeyboard` 예제의 SW0은 Just Works용 `acceptPairing()`만 호출했다. Numeric
Comparison pending에는 `confirmPasskey()` 응답이 필요하므로 Windows가 기다리던 응답은 소비되지
않았고 30초 뒤 pairing이 만료됐다.

`d1902b1`은 실제 하드웨어에 따라 passkey callback을 선택하는 `SecurityIoCapability`를 추가하고,
SecureKeyboard를 `no_input_output`으로 설정했다. 그 결과 Zephyr는 NoInputNoOutput을 광고하고
Windows는 Numeric Comparison이 아닌 Just Works를 선택한다. 이 경로는 암호화와 bonding을
제공하지만 MITM 인증은 제공하지 않는다.

### 8.3 실행 결과

1. Windows에서 기존 실패한 `NU54-Secure-HID` 항목을 제거했다.
2. `장치 추가 → Bluetooth → NU54-Secure-HID`를 선택했다.
3. 6자리 PIN/Numeric Comparison 화면 없이 보드가 SW0 승인 요청을 출력했다.
4. SW0을 한 번 누르자 Windows가 HID keyboard 연결 완료를 표시했다.
5. 메모장에 초점을 두고 SW0을 눌렀을 때 소문자 `a`가 실제 입력됐다.
6. pyOCD hardware reset 뒤 새 pairing 없이 저장 key로 암호화 재연결했다.
7. 재연결 뒤 SW0을 다시 눌렀을 때 소문자 `a`가 계속 입력됐다.

pairing과 최초 bond 상태의 UART 결과는 다음과 같다.

```text
BLE pairing confirmation requested; press SW0
BLE pairing completed
BLE bond pending reboot verification
```

재부팅 뒤 UART 결과는 다음과 같다.

```text
BLE restored bond candidate awaiting encrypted reconnect
BLE bond restored and verified after reboot
```

운영체제 UI 연결, 실제 HID 입력과 재부팅 뒤 bond 복원이 모두 PASS했으므로 M21의 수동 완료 조건을
충족했다. 스마트폰 호환성은 이번 실행에서 확인하지 않았으며 Windows 또는 스마트폰 중 하나의
실제 OS HID 확인이라는 M21 gate에는 영향을 주지 않는다.

## 9. 공용 builder 통합

새 library feature는 `nucode.ble.security`이며 공용 builder의 `FEATURE_ALLOWLIST`에 다음 mapping을
등록한다.

```python
"NUCODE_BLE_Security": "nucode.ble.security",
```

별도 공용 Kconfig 추가는 필요하지 않다. BLE core queue와 stack/settings lifecycle은 M19/M20 공용
구현이 소유하고 M21 feature conf는 보안·표준 profile symbol만 소유한다.

## 10. 최종 판정과 다음 단계

두 보드 RF HIL은 암호화된 GATT HID report map, CCC와 report payload의 protocol을 검증했고,
Windows 11 수동 검증은 운영체제 pairing UI·HID host stack·실제 키 입력과 bond 재연결을 확인했다.
따라서 M21은 **완료**다.

`v0.3.0` 전체는 아직 정식 지원이 아니다. 다음 순서는 AC-02 주변장치 호환성, AC-03
Storage·대표 library 호환성, M22 통합 package·clean Windows·RC/stable gate다.
