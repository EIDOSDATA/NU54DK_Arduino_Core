# NU54DK Arduino Core v0.3.0-rc.3 문제 해결

> `v0.3.0-rc.3`는 Release Candidate입니다. Production stable은 계속 `v0.2.0`입니다.

| 항목 | 값 |
| --- | --- |
| Package | `nucode:zephyr` |
| Board FQBN | `nucode:zephyr:nu54dk` |
| RC version | `0.3.0-rc.3` |
| 기본 Upload | CMSIS-DAP V2 + pyOCD |

## 1. RC3가 Boards Manager에 보이지 않음

RC3가 Public Prerelease로 공개된 뒤 다음 per-tag URL을 사용합니다.

```text
https://github.com/EIDOSDATA/NU54DK_Arduino_Core/releases/download/v0.3.0-rc.3/package_nucode_nu54dk_rc_index.json
```

- 과거 RC URL만 있다면 제거하고 RC3 URL로 교체합니다.
- Boards Manager index를 새로 고친 뒤 Arduino IDE를 다시 시작합니다.
- Stable URL만 등록하면 RC3가 보이지 않는 것이 정상입니다.

## 2. 설치가 오래 걸리거나 실패함

첫 설치는 Nordic NCS v3.4.0과 Toolchain `dcbdc366a1`을 내려받으므로 오래 걸릴 수 있습니다.

- Arduino IDE와 post-install 확인 창을 닫지 말고 완료를 기다립니다.
- 충분한 디스크 공간과 안정적인 네트워크를 확인합니다.
- 설치 version이 `0.3.0-rc.3`인지 확인합니다.
- 중단됐다면 설치된 platform의 `post_install.bat`을 일반 사용자 권한으로 다시 실행합니다.
- 관리자 권한, 시스템 PATH 변경 또는 공유 NCS/Toolchain 수동 삭제를 먼저 시도하지 않습니다.

## 3. Maximum이 712704 byte로 표시됨

RC3의 정상 maximum Sketch size는 `1490944` byte입니다. 712,704 byte는 RC1/RC2 package의
역사 값입니다.

1. Boards Manager에서 설치 version이 `0.3.0-rc.3`인지 확인합니다.
2. 과거 RC per-tag URL을 제거하고 RC3 URL만 남깁니다.
3. Arduino IDE를 다시 시작하고 Blink를 clean compile합니다.
4. 결과가 계속 같으면 Arduino data directory의 package 설치 경로와 실제 `boards.txt` version을
   기록해 Issue에 첨부합니다.

사용자 설치본의 숫자만 수동으로 고치지 마십시오. UI maximum, Devicetree와 linker 경계가 함께
바뀌지 않으면 storage를 덮어쓸 수 있습니다.

## 4. `[NU54:E_MEMORY_LAYOUT]`로 build 실패

이 오류는 Build Adapter가 generated Devicetree code partition과 linker FLASH origin/size의
불일치 또는 storage 겹침을 발견해 artifact 공개를 중단했다는 뜻입니다.

- Standard/ BLE 기본 예제에서 발생하면 전체 오류와 `.nu54-build.json`을 보존합니다.
- Sketch에 `prj.conf`나 `app.overlay`가 있다면 잠시 별도 보관하고 기본 profile로 다시 확인합니다.
- `CONFIG_USE_DT_CODE_PARTITION`을 끄거나 maximum size만 바꿔 우회하지 않습니다.
- RC3는 사용자 임의 memory layout을 정식 지원하지 않습니다.

## 5. Compile 실패 또는 예제가 보이지 않음

1. Board가 `NU54DK (nRF54L15, Zephyr)`인지 확인합니다.
2. 설치된 Core가 `0.3.0-rc.3`인지 확인합니다.
3. 예제에 맞는 Feature set을 선택합니다.
4. Arduino IDE를 다시 시작해 library/example index를 갱신합니다.
5. `File → Examples`에 library 8개와 예제 29개가 있는지 확인합니다.

## 6. CMSIS-DAP Upload 실패

- Probe가 한 대면 `CMSIS-DAP (pyOCD)`를 사용합니다.
- Probe가 둘 이상이면 `CMSIS-DAP with UID (pyOCD)`와 정확한 UID를 사용합니다.
- Compile과 Upload에 같은 Board, Feature set과 probe 설정을 사용합니다.
- 다른 프로그램이 CMSIS-DAP 또는 VCOM을 점유하지 않는지 확인합니다.
- 일반 실패 뒤 mass erase 또는 recover를 자동 복구 절차로 사용하지 않습니다.

## 7. Serial 또는 Serial1 출력이 없음

- 기본 `Serial`은 CMSIS-DAP VCOM 115200 8N1입니다.
- Upload한 보드의 COM port인지 확인하고 다른 serial monitor를 닫습니다.
- `SerialEcho`로 기본 경로를 먼저 확인합니다.
- `Serial1`은 UART30과 보조 VCOM route를 사용합니다. 보드의 solder bridge/조립 조건이 해당
  route를 연결하는지 확인합니다.
- `Serial1RuntimePins`의 begin/end/rebegin 순서와 첫 실패 출력을 보존합니다.

## 8. Wire/I2C가 응답하지 않음

- 기본 `Wire`는 I2C22, SDA P1.2, SCL P1.3입니다.
- 온보드 BQ25186 시험 주소는 `0x6A`, ID register는 `0x0C`, 기대 값은 `0x41`입니다.
- 먼저 100 kHz에서 read-only로 확인하고 400 kHz로 진행합니다.
- `endTransmission(false)` 뒤 같은 주소의 `requestFrom(..., true)`만 지원하는 repeated-start
  계약을 확인합니다.
- `requestFrom(..., false)`, Wire target/slave와 `Wire1`은 지원하지 않습니다.
- 외부 sensor를 연결했다면 전원, 공통 GND, 주소 충돌과 pull-up을 별도로 확인합니다.

## 9. EEPROM 또는 LittleFS 문제

- EEPROM 값을 바꾼 뒤 `commit()` 결과와 `lastError()`를 확인합니다.
- `reset()`과 LittleFS `format()`은 데이터를 삭제하므로 자동 호출하지 않습니다.
- `LittleFS.begin(false)`는 손상 또는 미초기화 filesystem을 자동 format하지 않습니다.
- Version 전환 전 중요한 데이터를 백업합니다. RC3가 RC2와 storage 주소를 유지하더라도
  application schema migration을 자동 수행하지 않습니다.

## 10. BLE 연결 또는 pairing 실패

- Peripheral/Central 역할, Feature set과 예제가 올바른지 확인합니다.
- 두 보드 reset 순서와 advertising timeout을 기록합니다.
- Windows SecureKeyboard는 OS bond와 보드 bond가 서로 다르지 않은지 확인합니다.
- BLE Mesh, OpenThread, Matter 또는 USB HID 동작을 BLE 예제에서 기대하지 않습니다.

## 11. Issue에 포함할 정보

- Core version, Arduino IDE/CLI와 Windows version
- Board FQBN과 Feature set
- 예제 또는 최소 Sketch
- 첫 실패 단계와 오류 전문
- FLASH/RAM 사용량과 표시된 maximum size
- Compile/post-install log와 `.nu54-build.json`
- Upload runner 종류와 장치 수 — 전체 probe UID 제거
- UART/I2C이면 pin, VCOM 또는 address·속도·register 값
- Storage이면 reset/format 여부, BLE이면 peer와 pairing 상태

비밀, 사용자 계정 경로와 전체 probe UID는 공개 Issue에 올리지 마십시오.
