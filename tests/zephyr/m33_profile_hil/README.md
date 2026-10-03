# M33 profile 개발 HIL

NCS 3.4.0/board submodule lock을 그대로 사용합니다. 실행 전 부모 통합자가 보드 mapping과
image를 확인합니다. 이 fixture를 추가한 사실 자체는 HIL PASS가 아닙니다.

## 빌드

기존 NCS launcher에서 `west build -b nrf54l15dk/nrf54l15/cpuapp/nu54dk`를 사용하고,
`BOARD_ROOT=<repo>/board_package/NU54DK_Zephyr_DTS`, `EXTRA_ZEPHYR_MODULES=<repo>`를 전달합니다.
Windows는 `C:/n54w02p/build-*` 같은 짧은 build 경로를 사용합니다.

- standard: `-DM33_PROFILE_ROLE=server`, `client`, `watcher` 세 image.
- native: `-DM33_PROFILE_FAMILY=native`와 `-DM33_PROFILE_ROLE=server`, `client` 두 image.

standard는 client → server(hub) → watcher 연결입니다. hub의 incoming peripheral
slot과 outgoing central slot을 모두 사용하므로 2개 incoming peripheral을 가정하지 않습니다.
hub는 watcher를 먼저 scan/connect하고 연결 완료 후 client용 광고를 시작합니다.
runner는 watcher의 `advertising-ready`, hub의 watcher 연결·L2 보안 완료 후
`hub-ready`를 차례로 관측해야 다음 역할에 START를 보냅니다. 각 barrier는 30초로 제한하고
미시작 역할도 nonce를 검증한 STOP에는 radio를 시작하지 않고 응답합니다.
기존 generic GAP API가 금지하는 광고 중 scan 시작을 동시에 요청하지 않습니다.
watcher는 ANS category 2만 허용한 채 email category 1이 6초 동안 전달되지 않는지 검사합니다.
client는 실제 email 5개 이상을 받고, runner는 server의 2-link와 전송 횟수도 함께 요구합니다.
실제 native CCC를 link/profile별로 조회하여 구독된 경우에만 주기적으로 전송합니다.
각 link/profile의 no-CCC 거부는 한 번만 시험하며 총 10개 예상 오류와 그 callback 수,
각 실제 send 5회 이상을 bounded summary로 검증합니다. 예상 밖 errno와 event drop은 FAIL입니다.
잘못된 ANS/BMS 요청을 제출할 때 link generation·profile·phase를 먼저 고정합니다.
GAP `-EIO`와 상세 ATT authorization 거부는 어느 순서든 각 한 번씩, 첫 callback부터
100ms 안에 짝을 이뤄야 합니다. 두 callback을 모두 소비하기 전에는 다음 phase로 진행하지
않습니다. 다른 errno·link·단계·중복·한쪽 누락은 FAIL이며 target과 Host가 같은 matcher를 씁니다.

## 안전 runner

저장소 루트에서 다음 형태로 실행합니다. probe는 raw UID 대신 사전에 확인한 SHA-256입니다.

```text
python tests/hil/nu54dk/m33_profile_run.py --family standard --sdk-root C:/ncs/v3.4.0 \
  --role server <probe-sha256> <server.hex> \
  --role client <probe-sha256> <client.hex> \
  --role watcher <probe-sha256> <watcher.hex> \
  --output-prefix <new-attempt-path> --development
```

위 명령은 기본적으로 preflight만 하고 `NOT_RUN`을 반환합니다. `--execute`를 추가해야
해당 image를 기존 safe sector-flash helper로 설치하고 protocol을 실행합니다. mass erase,
unlock, recover, SDK 변경은 하지 않습니다. 기존 attempt 파일은 덮어쓰지 않습니다.
native도 세 mapping을 전달하되 server/client만 START합니다. 세 번째 watcher에는 같은
source의 known standard-watcher image를 설치하고 시작하지 않아 RF idle을 보장합니다.
세 역할 모두 배타 probe lock·READY·종료 시 zero-resource STOPPED를 확인합니다.
native 실행은 세 `--build-record <role> <manifest.json>`과
`--native-security-phase fresh`가 필요합니다. 이어지는 복원 실행은 같은 image/build
record를 사용하고 `--native-security-phase restored --native-prior-evidence <fresh.json>`을
전달해야 하며, 다른 source/image/probe mapping의 fresh 증거는 실행 전에 거부합니다.
각 role을 서로 다른 build 디렉터리에서 빌드한 직후 다음 생성기로 HEX/ELF/config/sysbuild와
compile identity를 새 격리 디렉터리에 고정합니다. generator는 compile database의 실제
role/family/revision, CPUAPP/FLPR 설정, image와 현재 W02 source hash를 검사하며 기존 출력은
덮어쓰지 않습니다. `watcher`는 `--family standard`로 생성해야 합니다.

```text
python tests/hil/nu54dk/m33_profile_build_record.py \
  --family native --role server --build-dir C:/n54w02p/build-native-server \
  --output-dir C:/n54w02p/records/native-server
python tests/hil/nu54dk/m33_profile_build_record.py \
  --family native --role client --build-dir C:/n54w02p/build-native-client \
  --output-dir C:/n54w02p/records/native-client
python tests/hil/nu54dk/m33_profile_build_record.py \
  --family standard --role watcher --build-dir C:/n54w02p/build-standard-watcher \
  --output-dir C:/n54w02p/records/standard-watcher
```

fresh 실행은 위 record가 복사한 `image.hex`와 `build-record.json`을 함께 전달합니다.

```text
python tests/hil/nu54dk/m33_profile_run.py --family native \
  --native-security-phase fresh --sdk-root C:/ncs/v3.4.0 \
  --role server <server-probe-sha256> C:/n54w02p/records/native-server/image.hex \
  --role client <client-probe-sha256> C:/n54w02p/records/native-client/image.hex \
  --role watcher <watcher-probe-sha256> C:/n54w02p/records/standard-watcher/image.hex \
  --build-record server C:/n54w02p/records/native-server/build-record.json \
  --build-record client C:/n54w02p/records/native-client/build-record.json \
  --build-record watcher C:/n54w02p/records/standard-watcher/build-record.json \
  --output-prefix <fresh-attempt-path> --execute
```

restored 실행은 role/build-record 인자를 똑같이 사용하면서 phase와 predecessor만 바꿉니다.

```text
python tests/hil/nu54dk/m33_profile_run.py --family native \
  --native-security-phase restored --native-prior-evidence <fresh-attempt-path>.json \
  <same-sdk-role-and-build-record-arguments> --output-prefix <restored-attempt-path> --execute
```

두 실행 뒤에는 아래 명령으로 fresh evidence SHA chain·서로 다른 nonce·실행 순서와
동일 revision/source/image를 하나의 pair manifest로 검증합니다.

```text
python tests/hil/nu54dk/m33_profile_native_pair.py \
  --fresh <fresh.json> --restored <restored.json> --output <new-pair.json>
```

`PROBE`, nonce+core를 포함한 `START`, 결과 분모, `STOPPED`를 모두 확인하고 transcript와
image SHA-256을 보존합니다. dirty source는 `--development`가 필요하며 결과는
`DEVELOPMENT_PASS`이지 release PASS가 아닙니다. 시작 후 약 2분이 필요한 native CGMS
검사를 짧은 timeout 때문에 생략하지 않습니다.
실행에는 170초 command lease와 WDT30 8초를 적용합니다. 실패 뒤에도 poll을 유지하며,
5초 안에 native 연결/해제 중 상태·pending·scan·advertising을 모두 0으로 확인하고
watchdog을 중지해야 STOPPED를 냅니다. 정리 실패는 FAIL이며 watchdog feed를 종료합니다.
`CLEAN`은 실패 run이 남긴 test-owned bond 전용 복구 명령입니다. 별도 runner가 exact
image/nonce/probe에 결합된 read-only RAM 소유 증거를 검증한 뒤 peer와 원래 snapshot을
전달해야 합니다. target은 현재 목록이 `원래 목록 + 해당 peer 1개`와 정확히 같을 때만
그 peer를 삭제하고 기존 목록의 byte-equivalent 보존을 확인합니다. 광고·scan은 시작하지 않습니다.
일반 기존 bond 또는 소유 증거가 없는 bond를 이 명령으로 지우면 안 됩니다.

## 범위 및 미실행 분모

- standard: 7 profile 경로, client 측 30개 이상 measurement, watcher 25개 이상,
  각 3개 ATT 거부, server 2-link와 ANS delivery를 확인합니다. BMS는 시작 bond 목록에
  없고 이번 시험의 incoming client가 새 pairing한 경우에만 nonce authorization으로
  한 번 삭제합니다. 삭제 수 1·requester 부재·watcher bond 상태/연결 유지가 필요합니다.
  requester도 연결 전 snapshot에 없는 이번 session의 server bond임을 증명해야 합니다.
  server의 scoped 삭제 후 실제 disconnect를 확인한 다음 requester의 해당 fresh bond만
  fixture cleanup으로 삭제합니다. 기존 requester bond 목록 불변을 별도 `BMS_CLEANED`
  증거로 확인해야 성공이며, 이것은 server의 BMS 기능 판정과 분리됩니다.
  고정 SDK의 `bt_unpair()`는 해당 연결을 즉시 끊으므로 삭제 write ACK가 연결 종료와
  경합할 수 있습니다. 같은 phase 4 요청의 `-ENOTCONN`/ATT 0 쌍만 최대 한 번 묶고,
  서버 삭제 증명·실제 requester disconnect·양측 scoped 정리까지 5초 안에 확인해야 합니다.
  client의 오류 하나만으로 삭제 성공을 인정하지 않습니다.
  기존 bond이거나 새 소유 증명이 없으면 삭제하지 않으며 `DEVELOPMENT_PARTIAL`과
  BMS positive `NOT_RUN`을 기록합니다. 이것은 W02 전체 PASS가 아닙니다.
- native: 14 object 단계, CGMS notification 2회, boundary/지원·미지원 control 7판정,
  첫 session 뒤 정상 재연결, 512-byte 객체의 partial 수신 중 cancel, 정리 후 다시 연결해
  대표 read/write를 검사합니다. 총 3 session, 정상/취소 후 재연결 각 1회, server write
  완료 3건을 요구합니다. 단일 link 구성은 두 번째 실물 peer 접속 거부와 다릅니다.
  CGMS authenticated 권한에 맞춰 서버 display-only와 client keyboard-only를 사용하며
  fixture 전용 고정 passkey `472839`를 자동 전달합니다. 이 값은 인증 비밀이 아니라
  두 시험 image가 소유한 자동화 입력이며 공개 예제의 사용자 확인 흐름과 다릅니다.
  fresh phase는 양쪽 passkey event 1회와 세 session의 exact L4를 요구합니다. restored
  phase는 양쪽 passkey 0회, bond restored-candidate/verified 각 3회와 exact L4 3회를
  요구합니다. 두 phase는 동일 build record와 image의 순차 evidence pair여야 합니다.
  기존 bond를 자동 삭제하지 않습니다.
- BMS 재부팅 후 영속 삭제, native 2nd-peer/장시간 reconnect soak, 모든 선택 기능,
  기존 M30 7 profile 실물 재검증, Apple/Google/외장 기기는 이 runner의 PASS 분모가 아닙니다.
- CGMS SOCP start/stop 및 RACP delete의 unsupported 응답을 기대합니다. 지원 완료로
  바꾸어 표시하지 않습니다. `STOPPED`는 BLE 연결 종료이며 CGMS timer 취소를 의미하지 않습니다.
  SOCP read interval 응답은 고정 `cgms_socp.c` 구현대로 `03 01 00`(opcode + LE16)으로
  검사하며 이 SDK 형식을 모든 버전의 SIG wire 적합성으로 확대하지 않습니다.

## 개발 진단 근거

2026-10-03 standard attempt 004는 watcher가 최초 peer handle을 얻기 전 deadline에 도달했고,
native attempt 002는 19-byte initial read 성공 직후 write 제출에서 `-ENOMEM`을 관측했습니다.
둘 다 STOP 확인을 포함한 FAIL 원본을 보존하며 PASS로 바꾸지 않습니다.
고정 SDK `zephyr/subsys/bluetooth/services/ots/ots_client.c`의 `rx_done()`은 final
`obj_data_read` callback 후 CoC disconnect를 비동기로 요청합니다. `ots_l2cap.c`의
disconnect 완료와 다음 connect 사이의 자원 수명에 맞춰 public adapter는 완료 read 후에만
bounded retry를 허용합니다. 이는 관측한 lifecycle 경계이며 SDK 결함 판정이 아닙니다.
