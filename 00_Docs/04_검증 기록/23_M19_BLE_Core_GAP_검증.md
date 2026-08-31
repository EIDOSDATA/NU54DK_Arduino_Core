# M19 BLE Core/GAP 검증

## 판정

| 항목 | 결과 |
| --- | --- |
| Host API/profile/negative contract | PASS |
| NU54DK target contract build | PASS |
| Peripheral role image build | PASS |
| Central role image build | PASS |
| 두 보드 RF HIL | **NOT RUN — exact commit 뒤 실행 필요** |
| 외부 배선 | 없음 — 각 보드 USB만 사용 |

2026-08-31 dirty 개발 checkout에서 구현과 build-only 검증을 완료했습니다. 이 기록의 target
PASS는 compile/link 결과이며 실제 RF 연결 PASS로 확대하지 않습니다. 두 보드 HIL runner는
exact commit, clean source와 build record가 일치할 때만 flash/evidence 생성을 허용합니다.

## 구현 범위

- Zephyr type을 노출하지 않는 `BLEUuid`, `BLEAddress`, `BLEDevice`, `BLEAdvertising`,
  `BLEScan`, `BLEConnection`
- 31-byte legacy advertising과 flags/UUID/manufacturer/service data 구성
- exact name/UUID/address software filter와 bounded scan queue
- 단일 peer connect/disconnect/explicit reconnect
- ATT MTU, PHY, TX power getter와 connection parameter 요청
- stack `bt_enable()` image-wide once와 optional `settings_load()` once
- M20 GATT와 M21 security가 공유하는 connection lifecycle hook
- ISR/stack callback과 Arduino main thread callback의 고정 queue 분리
- NUS/범용 facade 상호 배제와 pending connect recycle 전 owner 유지
- end/reconnect의 connection·scan·event session generation 격리
- PHY별 TPC 없이 동작하는 legacy TX power 조회
- 실제 Arduino bundle과 같은 NUS+GAP+GATT source 공존 build

## 자동 검증 결과

M19 host API/profile/negative contract 7건과 HIL transcript parser 5건이 모두 PASS했습니다.
M16 target 회귀와 M19 target contract, peripheral/central HIL role은
`nrf54l15dk/nrf54l15/cpuapp/nu54dk`로 compile/link됐습니다. Windows 긴 경로 때문에 초기
Twister archive가 실패한 실행은 결과에서 제외했고 `--short-build-path`로 재실행했습니다.

HIL parser는 정상 transcript뿐 아니라 짧거나 stale인 nonce, token 재배치, target FAIL을 fail-closed로
거부합니다. 실제 HIL은 다음 항목을 두 UART transcript와 JSON evidence에 결합합니다.

- full 128-bit nonce로 만든 service UUID와 48-bit binary manufacturer data 광고
- UUID filter를 통과한 exact advertising 결과
- 첫 connect와 MTU/PHY/connection parameter 요청, legacy TX power 성공
- disconnect, peripheral readvertise, central explicit reconnect
- 두 번째 실제 connect/disconnect
- 모든 공개 callback의 Arduino main-thread 실행

## Exact-commit role image build

NCS v3.4.0 Toolchain terminal에서 실행합니다. Windows에서는 짧은 build 경로를 사용합니다.

```powershell
$CoreRoot = "C:\Users\eidos\GitHub\NU54DK_Arduino_Core"
$NcsRoot = "C:\ncs\v3.4.0"
$BoardRoot = "$CoreRoot\board_package\NU54DK_Zephyr_DTS"
$Python = "C:\ncs\toolchains\dcbdc366a1\opt\bin\python.exe"
$M19Peripheral = "C:\t\m19-peripheral"
$M19Central = "C:\t\m19-central"

Push-Location $NcsRoot
& $Python -I -m west build --sysbuild -p always `
  -b "nrf54l15dk/nrf54l15/cpuapp/nu54dk" `
  -d $M19Peripheral "$CoreRoot\tests\zephyr\m19_ble_gap_hil" `
  -- "-DBOARD_ROOT=$BoardRoot" "-DEXTRA_ZEPHYR_MODULES=$CoreRoot" `
  "-DM19_ROLE=peripheral"
& $Python -I -m west build --sysbuild -p always `
  -b "nrf54l15dk/nrf54l15/cpuapp/nu54dk" `
  -d $M19Central "$CoreRoot\tests\zephyr\m19_ble_gap_hil" `
  -- "-DBOARD_ROOT=$BoardRoot" "-DEXTRA_ZEPHYR_MODULES=$CoreRoot" `
  "-DM19_ROLE=central"
Pop-Location
```

Role image는 각각 다음 위치입니다.

- `C:\t\m19-peripheral\m19_ble_gap_hil\zephyr\zephyr.hex`
- `C:\t\m19-central\m19_ble_gap_hil\zephyr\zephyr.hex`

## 두 보드 HIL 실행

P2.5↔P2.6 점퍼는 이 시험에서 사용하지 않습니다. 보드 두 대를 각각 USB에 연결하고 DAPLink
UID 두 개만 정확히 지정합니다.

```powershell
$Commit = git -C $CoreRoot rev-parse HEAD
& $Python -I "$CoreRoot\tests\hil\nu54dk\m19_ble_gap.py" `
  --peripheral-hex "$M19Peripheral\m19_ble_gap_hil\zephyr\zephyr.hex" `
  --central-hex "$M19Central\m19_ble_gap_hil\zephyr\zephyr.hex" `
  --peripheral-board-id "<peripheral CMSIS-DAP UID>" `
  --central-board-id "<central CMSIS-DAP UID>" `
  --expected-core-revision $Commit `
  --evidence "$CoreRoot\build\m19\hil\m19-gap.evidence.json"
```

Runner는 두 UID·MSD·UART가 모두 다른지, Core/board exact revision과 clean source인지, 두 HEX의
build record와 source digest가 일치하는지, role image SHA-256이 서로 다른지 확인합니다. 이 gate를
통과한 실제 JSON과 companion transcript가 생기기 전까지 M19 RF HIL 상태는 NOT RUN입니다.
Service UUID exact filter가 UART nonce 전체 128 bit를 over-air로 결합하므로 prefix가 같은 주변
보드만으로 false PASS가 만들어지지 않습니다.
