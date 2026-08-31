# M21 BLE 보안과 표준 Profile 검증

| 항목 | 내용 |
| --- | --- |
| 문서 ID | VALIDATION-M21-001 |
| 문서 개정 | 0.4 |
| 상태 | persistence·HIDS lifecycle·128-bit RF peer binding 구현 완료, host·target 재검증 및 exact-commit 두 보드 RF HIL 대기 |
| 최종 갱신일 | 2026-08-31 |
| 대상 | `v0.3.0` M21 |
| 보드 | `nrf54l15dk/nrf54l15/cpuapp/nu54dk` |
| SDK | NCS `v3.4.0`, Zephyr `4.4.0` |

## 1. 목적과 현재 판정

M21은 `NUCODE_BLE` 공통 lifecycle 위에 pairing·bond 관리와 Battery Service(BAS),
Device Information Service(DIS), 암호화된 HID keyboard를 추가한다. 이 기록은 source/host 계약,
production target build, 두 NU54DK 사이의 RF protocol HIL과 실제 Windows·스마트폰 입력 확인을
서로 다른 판정 계층으로 분리한다.

| 계층 | 현재 결과 |
| --- | --- |
| 공개 API·보안·negative host 계약 | PASS, 22 tests |
| Arduino CLI SecureKeyboard·예제 탐색 | PASS |
| NU54DK production contract image | PASS, Flash 159,488 B / RAM 41,672 B |
| NU54DK board/system + BLE security 통합 image | PASS, Flash 174,724 B / RAM 42,444 B |
| NU54DK HIL Central role image | PASS, Flash 235,080 B / RAM 54,736 B |
| NU54DK HIL Peripheral role image | PASS, Flash 235,520 B / RAM 54,832 B |
| exact-commit 두 보드 RF HIL | NOT RUN — 전체 변경 commit과 pristine rebuild 뒤 실행 |
| Windows·스마트폰 실제 HID 문자 입력 | NOT RUN — 수동 확인 항목 |

현재 build는 dirty working tree의 통합 가능성을 확인한 결과다. 실제 RF PASS와 증적은 runner가
요구하는 exact clean commit, role별 build record와 서로 다른 두 보드를 만족한 실행에서만 만든다.

## 2. 구현 범위와 lifecycle ownership

공개 헤더 `libraries/NUCODE_BLE_Security/src/NUCODE_BLE_Security.h`는 Zephyr type을 노출하지 않고
`NUCODE_BLE.h`를 포함해 다음 기능을 제공한다.

- `SecurityManager`: L2/L3/L4 보안 요청, Just Works·passkey 응답, 취소·timeout, bond 열람·개별 삭제·전체 삭제
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

## 3. 보안 구성 경계

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

## 4. 자동 검증

Host contract와 parser/negative test는 다음 명령으로 실행했다.

```powershell
python -m unittest `
  tests.host.test_m21_ble_security_contract `
  tests.host.test_m21_ble_security_negative `
  tests.host.test_m21_ble_security_hil -v
```

22/22 PASS를 확인했다. 주요 negative 경계는 stack 중복 초기화·별도 connection callback 금지,
평문 HIDS 전송 금지, 고정 passkey와 secret 로그 금지, 같은 boot의 false verified bond 금지,
삭제 요청 뒤 reboot 전 상태를 삭제 완료로 오판하는 경우, stale nonce·target FAIL·restore 단계
재-pair·profile token 누락, 128-bit RF nonce binding 누락·축소를 거부하는 것이다.

Arduino library discovery 단계에서는 공개 헤더만 노출하고 Zephyr 내부 구현은 제외한다. 실제
Arduino CLI에서 `SecureKeyboard` compile과 전체 예제 탐색을 실행해 `PASS: m21`, `PASS: examples`를
확인했다. `NUCODE_BLE_Security`는 공통 BLE lifecycle에 의존하므로 `nucode.ble.nus`와 함께 선택되는
정상 조합을 충돌로 처리하지 않으며, 최종 feature profile은 `ble`로 제한한다.

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

관찰된 NCS HIDS 헤더의 deprecated attribute warning은 upstream header의 C++ 진단이며 M21 source
compile/link 오류가 아니다.

## 5. 두 보드 RF HIL

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
무시한다. UART transcript에 nonce를 붙이는 것만으로 RF peer binding을 주장하지 않는다. Runner는
다음 UART 명령만 사용한다.

```text
NUCODE_M21_CLEAR:<32자리 소문자 hex nonce>
NUCODE_M21_START:<32자리 소문자 hex nonce>
NUCODE_M21_REBOOT:<32자리 소문자 hex nonce>
NUCODE_M21_ERASE:<32자리 소문자 hex nonce>
NUCODE_M21_PROBE:<32자리 소문자 hex nonce>
NUCODE_M21_REPAIR:<32자리 소문자 hex nonce>
```

최종 commit에서 pristine role image를 다시 만든 뒤 다음 명령으로 실행한다.

```powershell
$Commit = git -C $CoreRoot rev-parse HEAD
$PeripheralHex = "$env:TEMP\nu54dk-m21-hil-peripheral\m21_ble_hil\zephyr\zephyr.hex"
$CentralHex = "$env:TEMP\nu54dk-m21-hil-central\m21_ble_hil\zephyr\zephyr.hex"
$Evidence = "$CoreRoot\build\m21\hil\m21-ble-security-$($Commit.Substring(0,7)).json"

python "$CoreRoot\tests\hil\nu54dk\m21_ble_security.py" `
  --peripheral-hex $PeripheralHex `
  --central-hex $CentralHex `
  --peripheral-board-id "<Peripheral DAPLink UID>" `
  --central-board-id "<Central DAPLink UID>" `
  --expected-core-revision $Commit `
  --evidence $Evidence
```

기대 final token은 두 역할 모두 다음 payload와 해당 실행 nonce를 가진다.

```text
NUCODE_M21_<CENTRAL|PERIPHERAL>:FINAL:PASS:pairing=PASS:bond_restore=PASS:erase_reboot=PASS:old_key_reconnect=REJECTED:repair=PASS:bas=PASS:dis=PASS:hid_protocol=PASS:nonce=<nonce>
```

Parser는 `first/restore/erased_probe/repair`, pairing event 수 `(1, 0, 1)`, bond count
`(1, 1, 0, 1)`, 상태 `(persistence_pending, verified, none, persistence_pending)`, encrypted
GATT negative, BAS/DIS/HID token 순서와 각 phase의 `rf_nonce_binding_bits=128`을 검증한다. 이전
실행 token, 누락·변조 token, 축소된 RF nonce binding, target FAIL과 서로 다른 실행 nonce를
fail-closed로 거부한다.

## 6. Evidence와 수동 확인 경계

PASS 때 `--evidence` 경로와 같은 디렉터리에 다음 세 로컬 파일을 신규 생성한다.

| 자산 | 경로 형식 |
| --- | --- |
| PASS evidence JSON | `build/m21/hil/m21-ble-security-<commit7>.json` |
| Peripheral raw UART | `build/m21/hil/m21-ble-security-<commit7>.peripheral.transcript.log` |
| Central raw UART | `build/m21/hil/m21-ble-security-<commit7>.central.transcript.log` |

기존 파일은 `--overwrite-evidence`를 명시하지 않으면 덮어쓰지 않는다. Evidence는 exact Core/board
revision, 두 장치 식별자, role별 image와 raw transcript SHA-256, pairing/bond/profile 결과와 다음
coverage 경계를 기록한다.

- `hid_report_protocol=true`
- `bond_persistence_pending_not_verified_same_boot=true`
- `bond_delete_warm_reboot_zero=true`
- `old_key_reconnect_rejected=true`
- `rf_nonce_binding_bits=128`
- `windows_or_smartphone_hid_input=false`
- `manual_os_hid_confirmation_pending=true`
- `mass_erase_requested=false`, `factory_reset_executed=false`

따라서 두 보드 HIL PASS는 암호화된 GATT HID report map, CCC와 report payload의 protocol 검증이다.
Windows 또는 스마트폰에 실제 키보드로 연결해 문자가 입력되는지 확인하는 UI/OS 검증은 자동 PASS에
포함하지 않으며 별도 수동 증적이 필요하다.

## 7. 공용 builder 통합

새 library feature는 `nucode.ble.security`이며 공용 builder의 `FEATURE_ALLOWLIST`에 다음 mapping을
등록한다.

```python
"NUCODE_BLE_Security": "nucode.ble.security",
```

별도 공용 Kconfig 추가는 필요하지 않다. BLE core queue와 stack/settings lifecycle은 M19/M20 공용
구현이 소유하고 M21 feature conf는 보안·표준 profile symbol만 소유한다.

## 8. 남은 완료 조건

1. M19/M20/M21과 병렬 변경을 하나의 exact commit에 포함한다.
2. 그 commit에서 contract와 두 role image를 pristine rebuild한다.
3. 서로 다른 NU54DK 두 대에서 RF HIL runner를 실행한다.
4. PASS JSON과 양쪽 raw transcript의 revision·SHA-256을 이 기록에 추가한다.
5. Windows 또는 스마트폰에서 실제 HID 문자 입력을 수동 확인하고 자동 protocol PASS와 별도로 기록한다.

현재 host·target build 결과를 RF 또는 OS HID 실기 PASS로 확대하지 않는다.
