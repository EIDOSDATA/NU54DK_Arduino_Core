# BLE 보안과 표준 Profile API

| 항목 | 내용 |
| --- | --- |
| 문서 ID | FW-BLE-SECURITY-001 |
| 문서 개정 | 2.0 |
| 문서 상태 | `v0.3.0` 정식 계약 |
| 최종 갱신일 | 2026-09-03 |
| 대상 library | `NUCODE_BLE_Security` |
| 기준 SDK | NCS `v3.4.0`, Zephyr `4.4.0` |

## 1. 목적과 범위

`NUCODE_BLE_Security`는 `NUCODE_BLE`의 단일 Bluetooth stack·connection lifecycle 위에 다음 기능을
추가한다.

- SMP security level 요청과 pairing 사용자 응답
- bond 열람·삭제와 재부팅 뒤 persistence 검증
- Battery Service(BAS)
- Device Information Service(DIS)
- 암호화된 BLE HID keyboard

library는 Zephyr type을 Sketch에 노출하지 않으며 별도의 `bt_enable()`, `settings_load()` 또는
connection callback을 소유하지 않는다. 범용 advertising·connection·poll은 `NUCODE_BLE` API를
계속 사용한다.

## 2. 초기화와 loop 순서

HIDS service와 SMP callback은 Bluetooth stack 시작 전에 등록한다. 다음 코드는 초기화 순서만
보여주는 축약 예시이며, pairing event 응답·오류 처리·advertising은 7절의 실제 `SecureKeyboard`
예제를 따른다.

```cpp
#include <NUCODE_BLE_Security.h>

void setup()
{
    nucode::ble::SecurityConfig security = {};
    security.minimum_level = nucode::ble::SecurityLevel::encrypted;
    security.bonding = true;
    security.response_timeout_ms = 30000U;
    security.io_capability =
        nucode::ble::SecurityIoCapability::no_input_output;

    BLESecurity.begin(security);
    BLEKeyboard.begin();
    BLEDevice.begin("NU54-Secure-HID");
}

void loop()
{
    BLEDevice.poll();
    BLESecurity.poll();
}
```

축약 예시에서는 흐름을 보기 위해 반환값 처리를 생략했지만 실제 Sketch에서는 모두 확인해야 한다.
`BLESecurity.poll()`은 bounded event queue와 사용자 응답 timeout을 Arduino main-thread에서
처리하므로 생략하지 않는다.

## 3. Security level과 실제 IO capability

### 3.1 Security level

| `SecurityLevel` | 의미 |
| --- | --- |
| `none` | 암호화되지 않은 L1 |
| `encrypted` | 암호화된 L2; MITM 인증은 보장하지 않음 |
| `authenticated` | MITM 인증을 요구하는 L3 |
| `secure_connections` | LE Secure Connections + MITM 인증 + 128-bit key를 요구하는 L4 |

`authenticated`와 `secure_connections`는 peer 지원뿐 아니라 실제 사용자 입출력 능력과 제품
profile 정책이 함께 성립해야 한다. 화면 없는 `no_input_output` 장치에 L3/L4가 항상 성립한다고
가정하지 않는다.

### 3.2 IO capability

`SecurityConfig::io_capability`는 **장치에 실제 존재하는 기능만** 선택한다.

| `SecurityIoCapability` | 필요한 실제 장치 | 등록하는 passkey callback |
| --- | --- | --- |
| `no_input_output` | 화면·숫자 입력 없음 | 없음; Just Works 사용 |
| `display_only` | 6자리 값을 표시할 화면 | display |
| `keyboard_only` | 6자리 숫자 입력 장치 | entry |
| `display_yes_no` | 화면 + 일치/불일치 버튼 | display + confirm |
| `keyboard_display` | 화면 + 숫자 입력 + 확인 | display + entry + confirm |

호환성을 위해 구조체 기본값은 `keyboard_display`지만, 제품 Sketch는 기본값에 의존하지 않고 실제
하드웨어 값을 명시해야 한다. NU54DK `SecureKeyboard`는 화면과 숫자 키패드가 없으므로
`no_input_output`을 사용한다. 이 설정은 L2 암호화와 bonding을 제공하지만 Numeric Comparison을
통한 MITM 인증은 제공하지 않는다.

화면 없는 장치가 `display_yes_no` 또는 `keyboard_display`를 선택하면 Windows가 6자리 Numeric
Comparison을 요구할 수 있다. 실제 숫자를 비교하지 않고 버튼만 누르거나 passkey를 log에 출력해
우회해서는 안 된다.

## 4. Pairing event와 사용자 응답

`BLESecurity.onEvent()` callback은 `BLESecurity.poll()`을 호출한 Sketch main-thread에서 실행된다.

| Event | Sketch 응답 |
| --- | --- |
| `pairing_requested` | Just Works 승인/거부를 `acceptPairing()`으로 전달 |
| `passkey_display` | `record.passkey`를 실제 보안 화면에 표시 |
| `passkey_input_requested` | 사용자 입력을 `enterPasskey()`로 전달 |
| `passkey_confirmation_requested` | 실제 표시값 비교 뒤 `confirmPasskey()` 호출 |
| `pairing_cancelled`, `pairing_failed`, `timeout` | 보류 중인 UI 상태 정리 |
| `paired` | 현재 boot의 pairing 완료 |
| `bond_persistence_pending` | 저장 요청 뒤 재부팅 검증 대기 |
| `bond_restored_candidate` | boot에서 로드한 peer의 암호화 재연결 대기 |
| `bond_verified` | 새 pairing 없이 저장 key로 L2 이상 복원 완료 |

passkey와 key material을 Serial log, HIL token 또는 영구 파일에 기록하지 않는다. 사용자 응답은
callback 안에서 block하며 기다리지 않고, 버튼·UI event가 발생했을 때 해당 API로 전달한다.

## 5. Bond 수명주기

`paired()`는 현재 연결에서 pairing이 끝났음을 나타내며 영구 저장 검증을 뜻하지 않는다.
`bonded()`는 다음 warm reboot에서 저장된 peer가 새 pairing 없이 L2 이상 보안 재연결에 성공한 뒤에만
true다.

```text
none
  → persistence_pending
  → (warm reboot) restored_candidate
  → verified
```

`eraseBond()`와 `eraseAllBonds()`의 true는 Zephyr stack이 제거 요청을 수락했다는 뜻이다. 영속 삭제는
재부팅 뒤 `bondCount()==0`과 이전 key 재연결 거부로 확인한다. 이 API는 mass erase나 factory reset을
실행하지 않는다.

## 6. BAS, DIS와 HID keyboard

### 6.1 Battery Service

`BLEBattery.setLevel()`은 `0`~`100` 값을 저장하고 구독된 peer에 notification을 보낸다. 범위를 벗어난
값은 거부한다.

### 6.2 Device Information Service

`BLEDeviceInformation.configure()`는 manufacturer, model, serial number와 firmware/hardware/software
revision을 runtime cache에 복사한다. 호출자가 넘긴 포인터의 수명에 의존하지 않으며 전체 필드를
검증한 뒤 한 번에 반영한다.

### 6.3 HID keyboard

`BLEKeyboard.begin()`은 표준 keyboard report map을 등록한다. `press()`는 USB HID usage ID와
modifier를 사용하며 `releaseAll()`은 zero report를 보낸다. HIDS attribute와 notification은 암호화된
L2 이상 연결에서만 허용되고, report subscription 전 전송은 거부된다.

소문자 `a`의 usage ID는 `0x04`다.

```cpp
if (BLEKeyboard.connected() && BLEKeyboard.press(0x04U))
{
    delay(15);
    BLEKeyboard.releaseAll();
}
```

## 7. SecureKeyboard 예제 사용 절차

Arduino IDE에서 `NUCODE BLE Security → SecureKeyboard` 예제를 열고 `Feature set → BLE NUS`를
선택해 build/upload한다. 현재 profile 이름은 NUS지만 builder는 library include를 감지해
`nucode.ble.security` feature도 함께 선택한다.

Windows 시험 절차는 다음과 같다.

1. 이전 실패 pairing이 있으면 Windows Bluetooth 설정에서 `NU54-Secure-HID`를 제거한다.
2. `장치 추가 → Bluetooth → NU54-Secure-HID`를 선택한다.
3. Serial에 승인 요청이 나타나면 SW0을 한 번 누른다.
4. 6자리 PIN 화면 없이 keyboard 연결이 완료되는지 확인한다.
5. 메모장에 초점을 두고 SW0으로 소문자 `a`가 입력되는지 확인한다.
6. 보드를 재부팅하고 새 pairing 없이 자동 재연결되는지 확인한다.
7. 재연결 뒤 SW0 입력이 계속 동작하는지 확인한다.

## 8. 오류와 현재 제약

- 모든 facade의 `lastError()`를 먼저 확인하고 필요한 경우 `lastDriverError()`로 NCS 오류를 진단한다.
- 동시 BLE 연결은 1개이며 bond 저장 한도는 4개다.
- HID는 keyboard input report만 제공한다. Consumer Control, mouse와 복합 HID는 현재 범위가 아니다.
- 사용자 UI callback에서 Bluetooth API를 재진입하거나 무제한 block하지 않는다.
- `no_input_output` Just Works는 수동 승인과 암호화·bonding을 제공하지만 MITM 보호가 필요한 제품의
  최종 보안 정책을 대신하지 않는다.
- Windows 11 검증은 완료했지만 스마트폰별 HID 호환성은 별도 제품 호환성 시험 대상이다.

## 9. 관련 문서

- [BLE Core/GAP API](07_BLE_Core_GAP_API.md)
- [BLE 범용 GATT API](08_BLE_범용_GATT_API.md)
- [M21 BLE 보안과 표준 Profile 검증](<../04_검증 기록/25_M21_BLE_보안과_표준_Profile_검증.md>)
- [v0.3.0 구현 마일스톤](<../01_아두이노 코어 설계/07_v0.3.0_구현_마일스톤.md>)
