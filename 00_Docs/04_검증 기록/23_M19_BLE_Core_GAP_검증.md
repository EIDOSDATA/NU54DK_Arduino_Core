# M19 BLE Core/GAP 검증

## 판정

| 항목 | 결과 |
| --- | --- |
| Host API/profile/negative contract | PASS |
| NU54DK target contract build | PASS |
| Peripheral role image build | PASS |
| Central role image build | PASS |
| 두 보드 RF HIL | **PASS — exact commit `0103a8434ac205a953c981385ae26a2a64aeeccc`** |
| 외부 배선 | 없음 — 각 보드 USB만 사용 |

2026-08-31 dirty 개발 checkout에서 구현과 build-only 검증을 먼저 완료한 뒤 clean exact commit의
두 보드 HIL을 실행했습니다. 첫 `ac10ba3` 실행에서 연결 뒤 link request 오류를 발견했고, 원인을
교정한 `0103a843`에서 advertise·scan·connect·disconnect·explicit reconnect와 callback 문맥까지
PASS했습니다. Build-only 결과와 실제 RF PASS는 아래에서 구분해 보존합니다.

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

## 첫 exact 실행에서 발견한 오류와 교정

`ac10ba3b253bd6bf76bcf73aa2c79278304908a4`의 첫 두 보드 실행은 UUID/manufacturer filter와
첫 연결까지 성공했지만 Central이 `NUCODE_M19_FAIL:role=central:reason=link-request`를 출력했습니다.
자동 PHY 요청이 peer/controller가 지원하는 PHY를 확인하지 않고 수행된 것이 원인이었습니다.

`0103a8434ac205a953c981385ae26a2a64aeeccc`에서는 연결이 보고한 local/remote PHY capability에서
실제로 사용할 수 있는 PHY만 요청하도록 고쳤습니다. 이 실패 transcript는 수정 뒤 PASS로
덮어쓰지 않고 회귀 원인으로 보존합니다.

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
build record와 source digest가 일치하는지, role image SHA-256이 서로 다른지 확인합니다. 최종
실행은 이 gate를 통과해 `m19-ble-gap-0103a84.json`과 양쪽 companion transcript를 생성했습니다.
Service UUID exact filter가 UART nonce 전체 128 bit를 over-air로 결합하므로 prefix가 같은 주변
보드만으로 false PASS가 만들어지지 않습니다.

## 최종 exact-commit HIL 결과

| 항목 | Peripheral | Central |
| --- | --- | --- |
| Core revision | `0103a8434ac205a953c981385ae26a2a64aeeccc` | 동일 |
| Board revision | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` | 동일 |
| Probe/UART | `5415360300052840d9e1e32cc887aaf1` / `COM14` | `5415360300052840fcd47678fd7d106d` / `COM13` |
| Image SHA-256 | `22f2b5917bfb18d84d0abcfc2f901d4c960b5fbc7a49b03a1051a77adfe18883` | `66ed78694dd7a23cf12aea0ce1a533f05fd9d205552a06b1bed3f916695a221b` |
| Transcript SHA-256 | `2254eeab43bdf03e8994b8c064c93423e11a4f5d6b820812930be4636c25f578` | `de6cfd27a997c6ffe9faadfe35cc70eab0a2274d239bb02f9411df4e5bf05232` |
| 연결 round | 1, 2 | 1, 2 |
| 결과 | callback main-thread·readvertise PASS | filter·explicit reconnect·link requests PASS |

완료 시각은 `2026-08-31T11:21:53.309840+00:00`이며, RF binding nonce는 전체 128 bit다. ATT MTU,
PHY, connection parameter와 TX power 요청을 포함했고 양쪽 disconnect 2회와 explicit reconnect가
PASS했다. 추가 GPIO 배선, mass erase와 PMIC write는 사용하지 않았다.
