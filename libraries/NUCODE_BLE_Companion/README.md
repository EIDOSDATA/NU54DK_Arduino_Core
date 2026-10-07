# NUCODE BLE Companion

NCS 3.4.0 고정 환경에서 Apple ANCS/AMS의 실제 보안 연결·GATT 데이터 경로와 외부 ecosystem용 독립 application template를 제공한다. SDK·board submodule은 수정하지 않는다. Google/Apple 인증, 실제 휴대전화 상호운용, 외장 센서와 cloud 업로드를 build 성공으로 대체하지 않는다.

## 먼저 고를 예제

| 목적 | 시작점 | 실행 범위 |
|---|---|---|
| 휴대전화 알림 title 읽기·사용자 action | `AppleNotificationClient` | Arduino public C++ API, ANCS peer 필요 |
| 음악 정보·재생 제어 | `AppleMediaClient` | Arduino public C++ API, AMS peer 필요 |
| Google Fast Pair HID input | `FastPairInputDevice` native template | 외부 model/credential, Android Fast Pair Seeker |
| Google Find Hub locator | `FastPairLocatorTag` native template | 외부 locator model/credential, DK 버튼·LED 시뮬레이션 |
| EnOcean switch/sensor | `EnOceanObserver` native template | 실제 호환 장치 commissioning 필요 |
| Memfault 진단 chunk 전송 | `MemfaultDiagnosticService` native template | 외부 key·gateway·cloud account 필요 |
| 공개 오디오 방송 | 기존 `NUCODE_BLE_Audio/PublicAudioBroadcastSource` | 실제 LC3/BIS source와 대응 sink. nRF AuraConfig 원본의 USB/audio gateway 대체품은 아님 |

처음부터 모든 예제를 읽지 않아도 된다. 위 표에서 목적 하나를 선택하고 해당 예제의 목적·준비물·설정·실행·성공 출력·흔한 오류·다음 예제만 따라간다. 다른 예제와 SDK 원본은 필요할 때 확장하는 참고 경로다.

## Apple Arduino API

`BLE NUS (ble)` feature set, NU54DK, Serial 115200을 선택한다. 공개 `.ino`는 Zephyr header를 포함하지 않으며 `NUCODE_BLE_Companion.h`와 공개 `NUCODE_BLE`만 사용한다.

- `AppleClient::advertise()`는 ANCS 또는 AMS의 service solicitation을 광고한다. 연결된 GAP handle을 `begin()`에 전달한다.
- `begin()`은 L2 암호화 후 해당 service를 실제로 발견하고 두 CCC를 순차 구독한다. UUID·속성·descriptor가 부족하면 연결을 닫는다. 보안·발견 한도 15초다.
- `poll()`을 main loop에서 10ms 이내 간격으로 호출한다. 한 image에 한 client session만 지원하며 `BLEClient`와 동시에 discovery하지 않는다. 객체는 static 수명으로 둔다.
- ANCS는 정확히 8-byte notification과 UID/attribute가 일치하는 분할 응답을 검사한다. 요청당 text 상한은 128 byte, action은 notification flag가 허용할 때만 전송한다.
- AMS는 허용된 remote command bit만 전송한다. entity update와 truncated flag를 처리하며 전체 attribute는 선택 write 후 실제 GATT long read로 최대 512 byte까지 읽는다.
- 요청은 한 번에 하나, timeout 5초다. invalid argument·busy·unsupported와 비동기 native error를 구분한다. malformed/overflow/timeout은 fail-closed로 disconnect한다.
- callback의 `data`는 callback 동안만 유효하다. text byte를 포맷 문자열이나 실행 명령으로 취급하지 않는다. 종료 시 buffer를 지우며 disconnect는 queue 포화와 독립된 terminal 신호다.
- bond 저장은 Core BLE settings를 따른다. disconnect 뒤 새로운 handle로 다시 발견·구독하며 이전 session의 요청을 재사용하지 않는다. 예제의 `q`는 연결과 광고를 중단한다. bond 삭제를 자동 실행하지 않는다.

고정 source 근거는 `nrf/samples/bluetooth/peripheral_ancs_client`, `peripheral_ams_client`, `nrf/include/bluetooth/services/{ancs_client,ams_client}.h`다. SDK sample과 같은 UUID/순서를 사용하되 sketch payload·오류·사용자 명령 흐름은 공개 C++ API로 구현했다.

## 독립 application template

Template는 Arduino sketch처럼 보이는 성공 stub가 아니다. 고정 SDK의 실제 application source 전체를 외부 output으로 복제하고 NU54DK board/configuration을 적용한다. upstream license는 그대로 유지한다. 재생성할 때 기존 output을 덮어쓰지 않는다.

저장소 루트에서 다음 명령을 사용한다. 경로·종류는 실제 환경에 맞춘다. toolchain은 고정 `dcbdc366a1`, SDK는 3.4.0이어야 한다.

```powershell
python libraries/NUCODE_BLE_Companion/tools/prepare_template.py `
  --kind fast_pair_input --sdk-root C:/ncs/v3.4.0 `
  --output C:/work/FastPairInputDevice `
  --credentials C:/private/fast-pair-input.json `
  --build --toolchain-root C:/ncs/toolchains/dcbdc366a1
```

`--kind`는 `fast_pair_input`, `fast_pair_locator`, `enocean`, `mds`다. `enocean`은 credential 인자가 필요 없다. `--build`를 빼면 source와 재현 명령만 준비한다. flash/erase/recover 기능은 없다. 생성물의 `template-manifest.json`은 고정 revision, upstream/생성 source hash, 명령, 실제 build 결과를 기록한다.

Fast Pair JSON 필드는 `schema_version: 1`, `use_case`(정확한 kind), `environment`(`test` 또는 `production`), `model_id`(6 hex), `anti_spoofing_key_base64`(32-byte P-256 private scalar)다. MDS는 마지막 두 필드 대신 `project_key`(32 hex)와 `device_id`를 쓴다. JSON은 저장소와 SDK 밖에 둔다. 실제 비밀을 명령행이나 repository에 넣지 않는다. key는 생성 firmware에도 포함되므로 output 전체를 비공개로 관리한다.

누락·placeholder·개행 주입·잘못된 EC scalar는 거부한다. `test`에는 명시적인 `--allow-test-credentials`가 필요하고 production에서는 SDK debug model과 명백한 placeholder key를 거부한다. 형식 검증은 Google/Memfault 권한이나 인증을 증명하지 않는다. 예제 자동 build에 사용한 수학적 시험 credential은 실제 등록·인증 credential이 아니며 제품에 사용하지 않는다.

Fast Pair는 loaderless NU54DK layout으로 `slot0 [0,0x174000)`, provisioning `[0x174000,0x175000)`, settings `[0x175000,0x17d000)`을 사용한다. 기존 Arduino layout과 다르므로 **기존 image/settings에 자동 덮어쓰지 않는다.** DFU/MCUboot는 이 template 범위에서 제외한다. 이 sysbuild에서는 application `build/source/zephyr/zephyr.hex`와 credential이 든 `build/modules/nrf/subsys/bluetooth/fast_pair/fp_provisioning_data.hex`가 별도 산출물일 수 있다. `zephyr.hex`만으로 provisioning 완료라 가정하지 않는다. manifest의 모든 hex·주소 범위·기존 settings 충돌을 검토한 다음 사용자가 명시적으로 승인한 flash 절차를 별도로 수행한다. tool이 두 hex를 자동 병합·flash하지 않는다.

### FastPairInputDevice

- 목적: SDK의 실제 GFPS pairing, discoverable/non-discoverable 광고, account-key storage와 HIDS consumer volume을 사용한다.
- 준비물: Google에 등록된 input model, 그 model의 credential, 승인된 시험 계정/Android Fast Pair Seeker, NU54DK.
- 설정: `fast_pair_input` credential 및 고정 SDK template. DK TX-power correction은 NU54DK 안테나 교정 완료를 뜻하지 않는다.
- 실행: nRF54 DK 표기의 버튼 0은 광고 3모드, 버튼 1/3은 volume up/down, 버튼 2는 bond만 삭제한다. **버튼 2는 account key를 지우지 않는다.**
- 성공 출력: 실제 pairing·HID 전송·재연결과 credential/account-key 저장을 각각 관측한다. 광고 LED만으로 pairing PASS를 쓰지 않는다.
- 흔한 오류: registered model과 key mismatch, Android debug-result 설정/계정 누락, non-discoverable 모드에서 일반 pairing 시도. 비밀을 로그로 공유하지 않는다.
- 다음 단계: disconnect 후 명시적 `companion_keys_reset CONFIRM`으로 account-key와 bond 삭제를 요청할 수 있다. 이 명령은 연결 중 거부하며 성공 후 사용자가 재시작한다. 이어 새 pairing을 확인한다. 삭제는 사용자 선택이며 자동 시험에서 실행하지 않는다.

### FastPairLocatorTag

- 목적: 고정 SDK의 실제 GFPS/FHN/DULT, provisioning·광고·ringing·식별·account-key/reset 경로를 실행한다.
- 준비물: locator 전용 model/credential, Google Find Hub 지원 Android·시험 계정. 실제 제품의 speaker/motion/battery 회로는 별도 후속이다.
- 설정: `fast_pair_locator`; input model을 재사용하지 않는다. loaderless이므로 DFU는 제외한다. 고정 SDK의 `APP_RANGING`/`FHN_PF` 경로는 그대로 build하되 실제 Google precision finding·거리 정확도는 별도 실물 후속이다.
- 실행: SDK의 생성된 `source/README.rst` 중 nRF54 DK 절차를 따른다. 버튼 0으로 discoverable, 버튼 1은 ringing 중지/모션 시뮬레이션, 버튼 2는 배터리 시뮬레이션, 버튼 3은 식별 모드다. 부팅 시 버튼 3을 누르는 factory reset은 사용자 승인 후에만 수행한다.
- 성공 출력: 실제 provisioning, 소유자·비소유자 모드, ring/식별, unprovision/reset 후 저장 상태를 각각 기록한다. LED/버튼 시뮬레이션을 실제 speaker/motion PASS로 승격하지 않는다.
- 흔한 오류: model use case·계정 불일치, 권한 미승인, FHN provision 상태·advertising trigger. 위치/계정 데이터와 키는 비공개로 유지한다.
- 다음 단계: 아래 양식으로 실제 Google peer, DULT unwanted-tracking 경계, 물리 하드웨어 결과를 추가한다. 인증은 별도 절차다.

### EnOceanObserver

- 목적: 실제 `bt_enocean` library가 광고를 검증하고 switch/sensor callback을 전달하도록 한다.
- 준비물: SDK에서 지원하는 실제 EnOcean switch/sensor와 commissioning 정보, NU54DK.
- 설정: `--kind enocean`; credential JSON 없음. 원본은 nRF52 sample 목록이므로 NU54DK target build 증거와 외장 실기는 분리한다.
- 실행: generated README와 SDK commissioning 절차에 따라 장치를 등록한 뒤 버튼·occupancy·light·energy 입력을 만든다.
- 성공 출력: `EnOcean Device commissioned`, 실제 `EnOcean button RX` 또는 `EnOcean sensor RX`와 입력에 맞는 값. `sample is ready`는 초기화 성공만 의미한다.
- 흔한 오류: 지원하지 않는 EnOcean 모델, commissioning 키/주소 mismatch, 수신 범위. commissioning data를 공개 로그로 남기지 않는다.
- 다음 단계: 전원 재인가 후 등록 복구·변조/잘못된 장치 광고 거부·decommission을 실제 장치에서 확인한다.

### MemfaultDiagnosticService

- 목적: Memfault SDK의 실제 metrics·trace·coredump를 MDS GATT chunk로 gateway에 전달한다.
- 준비물: Memfault project key·device ID·account, 호환 BLE gateway/앱과 인터넷. 사용자 진단 데이터가 cloud로 전송됨을 먼저 확인한다.
- 설정: `--kind mds`, 외부 credential JSON. 키/장치 ID는 정확한 project로 제한한다.
- 실행: generated README nRF54 DK 절차를 따른다. 버튼 0은 elapsed time, 버튼 1은 trace, 버튼 2는 press-count다. 버튼 3/명시적 crash command는 의도적 fault이므로 사용자 선택 후에만 수행한다.
- 성공 출력: 실제 chunk 수와 gateway/cloud에서 동일 device·image의 metrics/trace를 대조한다. 광고/연결만으로 cloud 전송 PASS를 쓰지 않는다.
- 흔한 오류: key/device mismatch, gateway 인터넷·권한·pairing 실패, symbol ELF 불일치. log에 key를 포함하지 않는다.
- 다음 단계: 정확한 build ELF를 사용자가 project에 등록하고 reconnect·chunk 중단/재개·선택한 crash 복구를 관측한다. 자동 tool은 cloud 업로드하지 않는다.

### nRF AuraConfig의 적용 경계

고정 `nrf/samples/bluetooth/nrf_auraconfig/sample.yaml`은 `nrf5340_audio_dk/nrf5340/cpuapp`만 허용하고 README도 그 Audio DK를 유일한 대상으로 명시한다. NU54DK에는 원본 USB/audio gateway·codec 하드웨어·nRF5340 구성의 지원을 주장하지 않는다. 원본 native 경로는 `NOT_APPLICABLE`이다.

공개 broadcast capability를 배우려면 이미 구현된 `PublicAudioBroadcastSource`/`PublicAudioBroadcastSink`의 BLE profile과 sidecar를 사용한다. 합성 PCM→LC3→실제 BIG/BIS 전송, 시작·종료·재시도·metadata는 그 예제에서 확인한다. 외부 Auracast receiver와 실제 오디오 I/O·원본 shell UI·최대 2 BIG/4 BIS 구성 지원이나 인증까지 동일하다는 뜻은 아니다. 이 경계는 `templates/catalog.json`에도 기록한다.

## 자동 검사와 실물 후속

다음은 기존 도구의 재현 예시이며 새 검증 파이프라인의 실행 지시가 아니다. D 출력 경로는
각 실행의 새 root로 바꾸고, C의 SDK/toolchain 설치본은 입력으로만 사용한다.

```powershell
$env:CXX = 'C:/msys64/ucrt64/bin/g++.exe'
$env:CC = 'C:/msys64/ucrt64/bin/gcc.exe'
$env:PATH = 'C:/msys64/ucrt64/bin;' + $env:PATH
python -m unittest discover -s tests/host -p 'test_m33_ecosystem*.py' -v
python libraries/NUCODE_BLE_Companion/tools/build_examples.py --work-root D:/w06/runs/companion-build
python tools/bluetooth/m33_ecosystem_hil.py build --role client --sdk C:/ncs/v3.4.0 --toolchain C:/ncs/toolchains/dcbdc366a1 --output D:/w06/runs/eco-client
```

`--role peer`도 별도로 build한다. 합성 peer는 실제 GATT에서 ANCS notification·분할 attribute·action, AMS supported-command·truncated attribute·long-read·control을 검증한다. Host 시험은 malformed·길이·범위·stale UID·credential/identity/분모 오류를 검사한다. 합성 peer 시험은 Apple 제품의 상호운용 PASS가 아니다.

실물 runner는 `tests/zephyr/m33_ecosystem_hil/README.md`를 따른다. fixed revision+source hash, image readback, nonce, 2회 재연결, 다른 peer nonce, malformed packet, STOP을 요구한다. 45초 lease/5초 hardware watchdog이 있으며 flash·mass erase·unlock·recover를 실행하지 않는다.

고정 SDK 위험 기록의 Fast Pair 광고/인증 경계 및 DULT start/stop·motion 중단 위험을 실제 Google 후속 시험에 포함한다. malformed·인증 거부·disconnect/재연결·start/stop을 각각 분리해 기록하며 근거 없이 SDK 문제로 실패 원인을 단정하지 않는다. 3.4.1 또는 DULT v2 전환은 이 library 작업이 아니다.

| peer/OS | 적용 기능 | 현재 분류 |
|---|---|---|
| iOS/iPadOS의 실제 ANCS/AMS provider | 알림 공유·title/action·media subscription/control·bond/reconnect | 사용자 후속 `NOT_RUN` |
| macOS | ANCS/AMS service 지원성을 먼저 발견으로 확인; 일반 BLE pairing/HID UX 별도 | 자동으로 iOS와 동등 지원이라 가정하지 않음, `NOT_RUN` |
| Android Fast Pair/Find Hub | input HID·GFPS·FHN/DULT·account-key lifecycle | 사용자 후속 `NOT_RUN` |
| Windows/Linux/일반 Android/macOS BLE Host | Fast Pair input의 discoverable 모드에서 일반 HID pairing/bond/control | GFPS/FHN 또는 Apple service 제공을 가정하지 않음, `NOT_RUN` |
| EnOcean 장치·Memfault gateway/cloud·외부 audio receiver | 각 실제 외장 기능 | 사용자 후속 `NOT_RUN` |

사용자 후속 결과에는 `case ID`, 날짜, core/SDK/board revision, image SHA-256, peer 모델/OS/앱/adapter, service 지원 여부, credential 종류(test/production, 비밀 제외), 설정/수동 승인 단계, 수행한 데이터/명령, 예상/실제 값, timeout, pairing 보안 결과, 재연결/정리 결과, `PASS/FAIL/NOT_RUN/NOT_SUPPORTED`와 근거를 기록한다. Apple 세션 15초/요청 5초, Google pairing 관측 120초를 기본 한도로 두되 SDK의 장기 unwanted-tracking/clock 시나리오는 별도 이름과 실제 경과시간을 남긴다. 미실행·지원성 미확인은 PASS가 아니다.
