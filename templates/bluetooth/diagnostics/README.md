# NU54DK Bluetooth 진단 application template

이 디렉터리는 Arduino Sketch와 별개로 빌드하는 고급 native application이다. 고정 NCS 3.4.0,
Zephyr `bf801e4e3d19e1ffa76164346480cb7734dd2800`, board
`fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3`, Windows toolchain `dcbdc366a1`을 사용한다.
원본 SDK 파일을 복사·수정하지 않고 해당 checkout의 구현을 링크한다. 설치 Sketch 개수에 합산하지 않는다.

## 목적과 선택

| 경로 | 사용 목적 | 보드 쪽 transport | 실행 범위 |
| --- | --- | --- | --- |
| `dtm_twowire` | 표준 DTM TX/RX·PHY·packet counter | DAPLink VCOM, 19200 8N1 | 두 NU54DK로 자동 시험 가능 |
| `dtm_hci` | HCI DTM 명령·오류·counter | DAPLink VCOM, H4 115200 8N1 | 두 NU54DK로 자동 시험 가능 |
| `uart` | full controller H4 | UART30 1 Mbit/s TX/RX/RTS/CTS | 외부 Host와 실제 결선 필요 |
| `async` | DMA 기반 H4 controller | UART30 1 Mbit/s TX/RX/RTS/CTS | 외부 Host와 실제 결선 필요 |
| `threewire` | reliable H5 controller | UART30 1 Mbit/s TX/RX/GND | H5 handshake를 구현한 peer 필요 |
| `lpuart` | 저전력 UART H4 controller | UART30 1 Mbit/s TX/RX/REQ/RDY | Nordic LPUART handshake peer 필요 |
| `spi` | SPI slave HCI controller | SPIS00 + 별도 IRQ | Zephyr HCI SPI protocol Host 필요 |
| `power_control` | RSSI·동적 TX power 변경 | 고정 SDK native GATT/HCI sample | peer 연결과 실제 값 관측 필요 |
| `scan_request` | scan-request event | SDC 표준 extended advertiser callback | active scanner 필요 |
| `power_profiling` | 광고·연결 notification의 전력 측정용 workload | native 버튼 입력·BLE | 기능 관측과 정밀 전력 측정 분리 |

일반 Arduino 사용자는 먼저 [RSSI power peripheral](../../../libraries/NUCODE_BLE/examples/RssiPowerControlPeripheral/RssiPowerControlPeripheral.ino),
[central](../../../libraries/NUCODE_BLE/examples/RssiPowerControlCentral/RssiPowerControlCentral.ino),
[LE Power Control](../../../libraries/NUCODE_BLE/examples/LePowerControlPeripheral/LePowerControlPeripheral.ino)을 사용한다.
같은 기존 기능은 M33에서 신규 구현으로 중복 계산하지 않는다.

## 준비물과 소유권

- DTM: NU54DK 두 대와 각각의 USB/DAPLink VCOM. 세 번째 보드도 아래 known-safe image/lifecycle 준비가
  필요하다. 임의 image의 snapshot이나 순간 RADIO Disabled만으로 격리 완료라고 판단하지 않는다.
  COM 이름, 익명 probe SHA-256, 실제 image와 역할을 매 실행 전에 대조한다.
  Probe hash는 기존 HIL lock과 동일하게 소문자로 정규화한 UID의 ASCII byte를 SHA-256한 값이다.
- Native controller: 외부 Host와 해당 protocol·3.3 V 신호·공통 GND가 필요하다. 현재 결선을 추정하지 않는다.
  이 template는 결선 변경이나 flash 권한을 부여하지 않는다.
- `uart`/`async`: P0.0 TX, P0.1 RX, P0.2 RTS, P0.3 CTS. Host TX↔RX, RTS↔CTS를 교차 연결한다.
- `threewire`: P0.0 TX, P0.1 RX, 공통 GND. H5의 ‘3-wire’는 실제 TX/RX/GND 경로이며 RTS/CTS가 아니다.
- `lpuart`: P0.0 TX, P0.1 RX, P0.2 REQ, P0.3 RDY. 단순 H4 serial adapter로 대체하지 않는다.
- `spi`: P2.1 SCK, P2.2 MOSI, P2.4 MISO, P2.0 CS, P2.3 IRQ, 공통 GND. 다른 peripheral과 공유하지 않는다.

모든 image는 RADIO·SDC buffer·선택한 UART/SPI·clock을 독점한다. Arduino Core와 정상 Host stack의 동시
편입은 compile guard가 거부한다. DTM/HCI UART에는 banner·`printk`·console·debug log를 넣지 않는다.
Native controller는 watchdog 120초 lease를 갖는다. 시간 초과로 reset되면 reset cause를 확인해 RF를
재시작하지 않는다. 다시 사용할 때는 외부 Host의 연결·Reset 절차와 사용자 의도의 보드 reset을 확인한다.
고정 upstream source의 무한 command 대기를 무제한 RF 실행으로 확대하지 않는다.

## 설정과 빌드

저장소 root에서 다음 도구를 실행한다. `--sdk`, `--toolchain`, `--output`은 사용자 환경 경로다.
출력 경로는 새 짧은 directory로 정한다. 기존 directory와 SDK·board checkout을 덮어쓰지 않는다.

```powershell
python tools/bluetooth/m33_diagnostics.py inventory
python tools/bluetooth/m33_diagnostics.py build --sdk <SDK_ROOT> --toolchain <TOOLCHAIN_ROOT> --output <NEW_SHORT_BUILD_ROOT> --routes dtm_twowire dtm_hci
python tools/bluetooth/m33_diagnostics.py build --sdk <SDK_ROOT> --toolchain <TOOLCHAIN_ROOT> --output <ANOTHER_NEW_BUILD_ROOT> --routes uart async threewire lpuart spi power_control scan_request power_profiling
```

도구는 고정 revision을 확인하고 source·실제 image·config·log hash를 `manifest.json`에 기록한다.
`PASS`는 target build 결과이며 runtime은 `NOT_RUN`으로 남는다. `build`는 flash를 호출하지 않는다.
`power_profiling`은 NU54DK에 제공하지 않는 NFC 실기 경로를 끄고 광고·notification 시간을 각각 3초로 제한한다.
외부 계측기 없이 전류·소비 에너지·정밀 RF 측정 PASS를 만들지 않는다.

## 특수 native workload 실행

- `power_control`: 별도 승인된 image 설치 후 VCOM 115200에서 controller가 반환한 TX power와 RSSI를
  관측한다. 처음 5초 뒤 광고 TX power가 5초마다 계단식으로 바뀐다. Central 연결 후에는 RSSI를 읽어
  연결 TX power를 조절한다. HRS notification은 원본 SDK의 시험용 값이며 실제 심박 측정이 아니다.
  요청 power와 controller가 선택한 power를 구분하고, RF 계측기 없이 실제 방사 출력을 확정하지 않는다.
  원본 sample은 peer disconnect 후에도 광고할 수 있고 UART STOP 명령을 제공하지 않는다. 종료에는
  별도 승인된 RF 유휴 확인/idle image 복원 절차가 필요하다. 120초 watchdog은 유한 안전 경계이며
  이 workload의 정상 STOP 명령 지원을 뜻하지 않는다.
- `scan_request`: exact image를 reset하고 extended active scanner를 함께 실행한다. VCOM 115200에서
  세 번의 `scan-request cycle=N received=M stop=0`와 최종 `error=0 delete=0 disable=0`를 확인한다.
  각 cycle의 `received`는 실제 SDC callback 수다. Passive/legacy-only scanner, peer 부재, zero count는
  scan-request 수신 PASS가 아니다. 모든 광고가 종료된 뒤 reset하면 동일한 세 세션을 다시 시작한다.
- `power_profiling`: UART/LED/NFC가 꺼진 측정 workload다. 보드 DTS의 첫 버튼(DK_BTN1, SW0)은
  connectable 광고, 둘째 버튼(DK_BTN2, SW1)은 non-connectable 광고를 3초 동안 시작한다. 버튼 이름은
  사용 중인 실제 보드 표기와 대조한다. Connectable peer에서 service
  `00001630-1212-EFDE-1523-785FEABCD123`, characteristic
  `00001630-1212-EFDE-1524-785FEABCD123`의 notification을 켜면 3초 뒤 disconnect/system-off로 간다.
  보안 연결의 bond/settings는 비휘발성 상태를 만들 수 있으므로 승인된 시험 장치만 연결한다.
  재시작은 버튼 wake/reset의 실제 관측으로 확인한다. Watchdog guard를 포함한 이 image는 원본 SDK와
  전력 조건이 같다고 가정하지 않으며 PPK2 등 측정 fixture·전원 경로·idle baseline을 별도로 기록한다.

위 세 경로는 source/build와 장비별 runtime 결과를 따로 남긴다. 외부 peer나 계측기가 준비되지 않으면
해당 관측은 `NOT_RUN`이고, 무응답을 성공이나 SDK 결함으로 단정하지 않는다.

## DTM 실행 순서

`python`은 해당 PC에서 pyOCD·pyserial import를 검증한 실행환경으로 바꾼다. 필요하면 검증된
Python 3.12와 해당 의존성의 `PYTHONPATH`를 사용한다. SDK bundled Python을 직접 실행해야 한다는
요구는 없다. 아래 placeholder는 현재 연결 목록과 exact build manifest의 값으로 교체한다.
UID 원문을 명령·공개 문서에 복사하지 않고 SHA-256만 사용한다.

1. 먼저 **plan-only**를 실행한다. USB 열거·probe open·flash·reset 없이 고정 SDK/source/HEX와
   예정 range를 검사하며 `preflight.json`만 생성한다. 이 상태는 `NOT_RUN`이고 fixture가 아니다.

```powershell
$dtmArgs = @(
    'tools/bluetooth/m33_diagnostics.py', 'prepare-pair',
    '--sdk', '<SDK_ROOT>', '--firmware-identity', '<MANIFEST_DTM_IDENTITY_104_HEX>',
    '--transport', 'twowire',
    '--tx-probe-sha256', '<CURRENT_TX_PROBE_SHA256>', '--tx-port', '<CURRENT_TX_COM>',
    '--tx-hex', '<EXACT_TX_HEX>', '--tx-hex-sha256', '<TX_HEX_SHA256>',
    '--rx-probe-sha256', '<CURRENT_RX_PROBE_SHA256>', '--rx-port', '<CURRENT_RX_COM>',
    '--rx-hex', '<EXACT_RX_HEX>', '--rx-hex-sha256', '<RX_HEX_SHA256>',
    '--third-probe-sha256', '<CURRENT_THIRD_PROBE_SHA256>',
    '--third-idle-fixture', '<W02_NATIVE_FINAL_THIRD_IDLE_JSON>',
    '--third-idle-fixture-sha256', '<EXACT_THIRD_IDLE_FIXTURE_SHA256>'
)
python @dtmArgs --output <NEW_PLAN_DIRECTORY>
```

2. 실행은 `--execute`와 다음 **세 실행 범위 확인 flag**가 필요하다. 이미 승인된 W02~W06 연속 작업에서는
   반복 사용자 승인을 뜻하지 않으며 TX/RX sector program, TX/RX flash algorithm SYSRESETREQ,
   third halt/audit를 증거에서 구분한다. 세 보드 모두 strict safe-idle pre-audit를
   통과하지 못하면 TX/RX program/reset도 시작하지 않는다. third는 W02 native final이 남긴
   **START되지 않은 standard-watcher의 fresh STOPPED** 상태만 수용한다. 아래 fixture가 없으면
   probe를 열지 않고 `NOT_RUN`으로 남긴다. 승인된 W02 native runner로 third를 새로 준비하고 새로운
   W02 handoff 증거를 만든 뒤 다시 실행한다. W04 도구 자체에는 third 자동 설치·reset·resume 경로가 없다.

```powershell
python @dtmArgs --output <NEW_PREPARED_DIRECTORY> --execute `
    --authorize-sector-program --authorize-tx-rx-algorithm-reset `
    --authorize-third-halt-audit
```

3. `PREPARED`는 **세 CPU HALTED + third known-safe** 상태다. 실제 RF 시험 PASS가 아니다.
   `fixture.json`, `preflight.json`, `tx.hex`, `rx.hex`와 W02 근거의 exact 사본
   `third-idle-fixture.json`/`third-*.bin`을 보존한다. W04 준비 fixture를 수동 선언하지 않는다.
   W02 watcher HEX의 모든 load range를 실제 readback하고, exact ELF symbol 주소로 현재 RAM의
   nonce·started=0·cleanup_complete=1·stop_reported=1·failed=0·watchdog_channel=-1을 확인한다.
   이는 과거 transcript만으로 현재 상태를 추정하지 않기 위한 추가 검사다. third VCOM은 W04에서
   열지 않으며 외부 UART command source를 연결해서는 안 된다. HALTED 상태에서 DPPI/SHORTS/WDT를
   읽기 전용으로 검사한다. WDT stop/feed/config, RADIO DISABLE/SOFTRESET은 쓰지 않는다.

4. RF 실행에는 **별도 TX/RX 시작 승인**이 필요하다. default는 2-wire이며 H4는 준비 단계의
   `--transport h4`와 실행 단계의 `--h4`가 모두 일치해야 한다.

```powershell
python tools/bluetooth/m33_diagnostics.py run-pair --fixture <NEW_PREPARED_DIRECTORY>/fixture.json `
    --output <NEW_RUNTIME_EVIDENCE_DIRECTORY> --authorize-start-tx-rx
```

Runner는 배타 lock 후 실제 mapping·DP/AP·세 HEX readback·W02 third lifecycle을 재검증하고 TX/RX만
software reset-halt-resume한다. third audit는 각 command/case 전후, serial partial read 전후와
대기 중 최대 100 ms sleep 단위로 반복한다. USB read/audit 자체의 지연은 실시간 보장이 아니며,
raw DHCSR의 S_RESET_ST는 단일 소비 경로에서 software latch한다. Monitor 시작 후 third의
`get_state()`/`read_core_register()`는 사용하지 않으므로 그 API가 reset bit를 먼저 소비하지 않는다.
RAM/상태 변화·읽기 실패·한 번의 reset/running 관측도 실패로 유지한다. RESETREAS는 안전 증명이 아니다.
양쪽 STOP을 시도하되 third reset/recover로 시험을 되살리지 않는다. 두 역할 교대 × 1M/2M ×
channel 0/19/39 = 12 case, 각 PRBS9 37-byte·500 ms 송신을 수행한다. 합격 기준은 각 RX 실제 packet
reporting counter 50~2000, 양쪽 Test End 응답 성공이다. 이 기준은 기능 관측이며 RF packet-error-rate
계측이나 감도·출력 인증 수치가 아니다. Range/length/unsupported command·active 재시작 거부와
3초 RX lease 자동 STOP/restart도 두 보드 각각 검사한다. 실패 transcript와 cleanup 결과는 보존한다.

5. 양쪽 STOP과 실제 RX count를 확인한 뒤 별도 승인된 idle image 복원/종료 절차로 UART·clock·핀
   소유권을 반환한다. Test End는 RF 시험의 종료이며 진단 application 전체의 UART service 종료와 다르다.
   모든 program은 sector-only, `auto_unlock=false`, exact SHA, 공용 probe lock으로 제한한다.
   mass erase·unlock·recover·임의 hardware reset fallback은 제공하지 않는다.

### W02 → W04 third-idle fixture 계약

W02 native final을 수행한 통합자가 실제 산출물로 아래 JSON을 생성한다. 근거 파일의 상대 경로는
fixture 위치 기준이며 absolute path도 허용한다. 선언만으로 통과하지 않고 파일 SHA·protocol·ELF·live
memory를 대조한다. 필수 field 목록은 도구의 `THIRD_IDLE_SCHEMA`, `THIRD_IDLE_FILES`,
`THIRD_IDLE_SOURCES`, `THIRD_IDLE_SYMBOLS` 상수와 동일하다.

| Field | 필수 값/근거 |
| --- | --- |
| `schema` | `nucode-m33-w04-third-idle-v1` |
| `role`, `probe_sha256` | `standard-watcher`, 현재 third exact probe SHA |
| `revisions` | `core`, `board`, `ncs`, `zephyr`의 full 40자리 SHA; 현재 source/lock과 일치 |
| `nonce` | W02 final watcher STOPPED의 32자리 hex nonce |
| `build_defines` | `M33_PROFILE_FAMILY=standard`, `M33_PROFILE_ROLE=watcher`를 JSON key/value로 기록 |
| `files` | `evidence`, `transcript`, `image`, `config`, `sysbuild`, `elf` 각각 `{ "path": "...", "sha256": "..." }` |
| `source_files` | 실제 build의 repository-relative source path → SHA256 사전. 최소 profile HIL의 CMakeLists.txt/prj.conf/app.overlay/src/main.cpp |
| `load_ranges` | HEX 전체 연속 data range의 `{ "start": 숫자, "length": 숫자, "sha256": "binary range hash" }` 배열 |
| `after_stopped_actions` | STOPPED 뒤 실제 수행한 순서. `uart_close`, `debugger_halt`, `read_only_audit`만 허용; 빈 배열·reset/program/resume 거부 |

`evidence`는 native `PASS` 또는 `DEVELOPMENT_PASS`, 동일 watcher probe/image/revision 및
`cleanup.watcher`를 포함해야 한다. Transcript의 watcher 기록은 `READY`(빈 nonce) → `SERVER_STATS`
→ `STOPPED`이며 BEGIN/START/FAIL가 없어야 한다. STOPPED의 `native_links`, `links`, `pending`,
`scan`, `advertising`, `watchdog`은 모두 0이다. `sysbuild`의 FLPR 선택은
`SB_CONFIG_FLPRCORE_NONE=y` 하나뿐이어야 한다. `config`는 실제 watcher application `.config`다.
`elf`는 같은 image의 ARM ELF32이며 익명 namespace의 `nonce`, `started`, `cleanup_complete`,
`stop_reported`, `failed`, `watchdog_channel` symbol의 실제 주소·크기를 해석한다. RAM 주소를 수동으로
대입하지 않는다. source 변경·STOPPED 이후 reset/program/resume·ELF/nonce/readback 불일치는 새
handoff가 필요하며 안전 검사를 완화하지 않는다.

Soft reset을 full-chip 초기화나 WDT/RAM 정리의 증거로 사용하지 않는다.
Nordic [RESET erratum 63](https://docs.nordicsemi.com/r/bundle/errata_nrf54l15_rev1/page/err/nrf54l15/rev1/latest/anomaly_l15_63.html)은
해당 revision에서 power-domain RUN→IDLE 전환과 soft reset이 겹치는 조건의 위험이다. 이번 검사의
보수적 경계이며, 실제 실패를 해당 erratum 때문이라고 단정하거나 자동 reset 우회를 적용하지 않는다.

### 고정 MDK audit 근거

고정 `modules/hal/nordic/nrfx/bsp/stable/mdk/nrf54l15_global.h`와 `nrf54l15_types.h`의 실제 내용/hash를
검증한다. RADIO secure base `0x5008A000`의 정의된 SUBSCRIBE 17개·PUBLISH 27개의 EN bit31은 모두 0,
SHORTS `+0x400`과 STATE `+0x520`은 0이어야 한다. PUBLISH_DISABLED `+0x320`도 포함한다.
WDT30/31 secure base `0x50108000`/`0x50109000`의 SUBSCRIBE_START/STOP `+0x80/+0x84`,
PUBLISH_TIMEOUT/STOPPED `+0x180/+0x184` EN도 모두 0이어야 한다. EVENTS_TIMEOUT `+0x100`은 0이며
RUNSTATUS `+0x400` bit0과 CONFIG `+0x50C` bit3이 동시에 1이면 거부한다. 정의되지 않은 offset을
일괄 읽지 않는다. 이 register audit는 exact known image/lifecycle을 대체하지 않는다.

## 예상 출력과 종료

- Firmware UART: 오직 2-byte DTM event 또는 H4 HCI event. 텍스트가 나오면 잘못된 image 또는 UART 혼입으로 실패한다.
- Host 성공: `M33_DIAG_PAIR_PASS=12; STOP=2; RF_METROLOGY=NOT_RUN`.
- RF command lease는 최대 3초다. Host가 사라져도 firmware가 Test End를 실행하고 실제 packet report를 낸다.
- Controller 응답은 1초, buffer 할당은 100 ms로 제한한다. 복구 불가능한 실패는 reset 후 RF 유휴로 돌아간다.
- Main loop가 정지하면 8초 hardware watchdog이 reset한다. 전용 UART는 재시작 명령 수신을 위해 유지한다.
- 일반 HCI controller template의 정상 종료는 외부 Host HCI Reset→해당 command complete 확인→Host detach다.
  120초 watchdog은 비정상 종료의 최후 수단이며 정상 STOP 증거를 대체하지 않는다.

## 명령과 흔한 오류

`dtm_twowire`는 고정 SDK의 `dtm_tw_to_hci_process_tw_cmd`를 사용한다. CTE/안테나 전환은 고정 SDK
변환기 미지원이며 거부된다. 분리된 두 byte가 5 ms를 초과하면 이전 byte를 버린다.

`dtm_hci`는 Reset `0x0c03`, local version `0x1001`, local features `0x1003`, LE features `0x2003`,
RX/TX v1 `0x201d/0x201e`, RX/TX v2 `0x2033/0x2034`, Test End `0x201f`만 허용한다. 잘못된
길이·channel·PHY·payload는 `0x12`, 알 수 없는 command는 `0x01`, active 중 재시작은 `0x0c`다.
H4 fragment 간격은 20 ms이며 최대 command frame 259 byte를 고정 buffer로 받는다.

실물 source 확인용 읽기 전용 확장: H4 vendor `0xfc80`은 status 뒤 HEAD40+template SHA256을 반환한다.
2-wire setup `0x3f00 | index`는 같은 104 ASCII 문자를 각 `character << 1` event로 제공한다.
이 확장은 RF를 시작하지 않으며 표준 DTM 측정 command의 payload나 counter를 바꾸지 않는다.

| 오류 | 확인할 부분 |
| --- | --- |
| 응답 없음 | exact COM/image, 19200과 115200 선택, 전용 UART인지 확인 |
| identity mismatch | 다른 image/수정 source를 사용한 build인지 확인; 자동 덮어쓰기 금지 |
| count 0 또는 낮음 | RX 먼저 시작했는지, PHY/channel, 두 역할, 실제 RF 간섭과 STOP event 확인 |
| 보드가 3초 후 STOP | RF lease의 정상 경계; 더 긴 송신으로 자동 변경하지 않음 |
| controller 120초 후 멈춤 | native template lease 종료; 원인 기록 후 명시적 reset으로 새 세션 |
| H4/async handshake 실패 | RTS/CTS 포함 실제 4-wire 연결 확인; VCOM 두 선식으로 바꾸지 않음 |
| SDK RX assert | fault/reset cause·조건·원본 로그 확보; DRGN-29228로 즉시 단정하지 않음 |

NCS 3.4.1에 기록된 DRGN-29228은 매우 잡음 많은 DTM RX assert의 조건부 위험이다. 이번 시험은
NCS 3.4.0을 유지하며 watchdog/STOP과 실패 원본을 수집한다. 높은 RX loss만으로 SDK 원인을 확정하지 않는다.

## 비적용 경로와 다음 예제

- `hci_usb`: nRF54L15에는 native USB device controller가 없다. DAPLink의 USB/VCOM을 SoC HCI USB로 세지 않는다.
- `hci_ipc`: 고정 sample은 nRF5340 network core와 IPC topology를 요구한다. NU54DK의 단일 application/SDC
  경로에 그대로 적용할 수 없다. Flpr가 있다는 사실만으로 network-core controller 경로를 지원한다고 쓰지 않는다.
- `rpc_host`: 고정 metadata는 nRF5340 cpunet이며 full Bluetooth API RPC 서버다. UART HCI bridge와 기능이 다르다.
  단일 NU54DK에 복사해 지원 선언하거나 SDK 전환으로 우회하지 않는다.
- `legacy_scan_vendor`: 원본 Zephyr `hci_vs_scan_req`의 `BT_HCI_OP_VS_SET_SCAN_REQ_REPORTS`는
  Zephyr LL `hci.c`가 처리하는 legacy advertising vendor command다. 고정 SDC vendor header에는 해당
  경로가 없어, `scan_request` template는 표준 extended advertising의 `scanned` callback을 사용한다.
  원본 command 지원을 주장하지 않는다. 세 번의 2.5초 광고 뒤 각각 stop하고 마지막에 delete/disable한다.
  출력 `received=0`은 active scanner event 미관측이며 성공 측정으로 세지 않는다.

Source 근거는 `nrf/samples/bluetooth/direct_test_mode`, `hci_lpuart`, `rpc_host`, `peripheral_power_profiling`과
`zephyr/samples/bluetooth/hci_uart`, `hci_uart_async`, `hci_uart_3wire`, `hci_spi`, `hci_usb`, `hci_ipc`,
`hci_pwr_ctrl`, `hci_vs_scan_req`의 README·sample metadata·source다. 실제 inventory는 도구의 `inventory`가 출력한다.

다음 단계는 [BLE 예제](../../../libraries/NUCODE_BLE/examples) 또는
[M33 전체 TODO](../../../00_Docs/TODO_M33.md)의 W05/통합 검증이다. Native build, 실제 두 보드 DTM,
외부 HCI Host interoperability, 정밀 RF/전력 계측은 독립 결과로 기록한다.
