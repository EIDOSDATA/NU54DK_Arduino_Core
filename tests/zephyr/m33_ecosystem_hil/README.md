# M33-ECOSYSTEM-01 합성 ANCS/AMS peer 시험

이 application은 public `AppleClient`를 실제 BLE GATT에 연결한다. peer image가 ANCS/AMS schema·notification·attribute·control을 제공하며 client image는 production library를 그대로 링크한다. 두 역할 모두 public `BLESecurity`로 L2 pairing·bond·같은 boot 재연결을 검증한다. 실제 Apple 제품·OS UX·Google 인증은 검증하지 않으며 `NOT_RUN`으로 분리한다.

## Build

다음은 기존 도구의 재현 예시이며 새 검증 파이프라인의 실행 지시가 아니다. D 출력 경로는
각 실행의 새 root로 바꾸고, C의 SDK/toolchain 설치본은 입력으로만 사용한다.

저장소 루트에서 고정 SDK 3.4.0과 고정 toolchain으로 각각 build한다. source에 수정이 있으면 새로운 output 경로로 다시 build한다.

```powershell
python tools/bluetooth/m33_ecosystem_hil.py build --role client --sdk C:/ncs/v3.4.0 --toolchain C:/ncs/toolchains/dcbdc366a1 --output D:/w06/runs/eco-client
python tools/bluetooth/m33_ecosystem_hil.py build --role peer --sdk C:/ncs/v3.4.0 --toolchain C:/ncs/toolchains/dcbdc366a1 --output D:/w06/runs/eco-peer
```

성공한 `build-manifest.json`의 `identity_stable`을 확인한다. `identity`는 core HEAD(40 hex)+관련 source SHA-256(64 hex)이며 양 역할이 같아야 한다. source dirty 개발 검증과 clean revision 릴리스 검증은 구분한다. image SHA-256은 역할마다 다르다.

각 image를 정확한 NU54DK에 배치하는 flash, debugger CPUID/FICR 확인, verify/readback은 부모 HIL 관리자가 수행한다. 이 tool은 flash·unlock·recover·mass erase를 하지 않는다. 세 번째 등 참여하지 않는 보드는 CPU halt와 RADIO disabled를 실제로 확인하여 격리한다. raw probe UID는 공개 증거에 기록하지 않는다.

## Fixture와 실행

사전 검증 자료를 외부 파일로 보존하고 그 SHA-256을 계산한다. fixture는 다음 필드를 가진다. 값은 실제 관측/산출물로 채워야 하며 아래 설명은 성공 증거가 아니다.

- `schema_version`: 1.
- `identity`: 양쪽 실제 build의 104 hex identity.
- `other_radios`: `isolated_verified`.
- `isolated_probe_sha256`: 연결되어 있지만 격리한 모든 비참여 probe SHA-256 목록.
- `preflight_evidence`: 역할↔probe hash↔VCOM↔image hash 매핑, debugger silicon/readback 및 다른 radio 격리 검증을 담은 실제 파일 경로.
- `preflight_sha256`: 그 파일의 SHA-256.
- `boards`: 두 항목. 각 항목에 `role`(`client` 또는 `peer`), `port`, `probe_sha256`, `image`(실제 hex 경로), `image_sha256`, `readback: verified`를 기록한다.

```powershell
python tools/bluetooth/m33_ecosystem_hil.py run --fixture D:/w06/runs/eco-fixture.json --output D:/w06/runs/eco-attempt-01
```

실행은 probe SHA-256별 기존 HIL OS lock을 잡는다. 한 보드를 두 역할로 중복 지정할 수 없으며 이미지 파일·preflight 자료의 실제 hash를 확인한다. 기존 evidence output을 덮어쓰지 않는다. firmware에서 받은 identity도 정확히 비교하므로 잘못된 image 또는 dirty source 변경을 HEAD만으로 통과시키지 않는다.

## 고정 case와 판정

| case | 실제 경로 | client 기준 | peer 기준 |
|---|---|---|---|
| `ancs` | L2 보안→discover→두 CCC→8-byte event→UID 지정 title request→분리된 8+5 byte response→positive action | packets 1, attributes 1, writes 2, negative 1 | packets 1, attributes 1, writes 2, negative 0 |
| `ams` | L2 보안→discover→두 CCC→supported commands→track title selection→truncated update→selection+GATT long read→toggle command | packets 1, attributes 1, writes 2, negative 1 | packets 1, attributes 0, writes 3, negative 0 |
| `ancs_bad` | event ID 3을 수신한 production codec이 malformed 거부 후 disconnect | packets 0, attributes 0, writes 0, negative 2 | packets 1, attributes 0, writes 0, negative 1 |
| `ams_bad` | reserved update flag를 malformed 거부 후 disconnect | packets 0, attributes 0, writes 1, negative 2 | packets 1, attributes 0, writes 1, negative 1 |
| `access_denied` | 양 역할이 `pairing_requested`를 명시적으로 거부하고 비동기 보안 실패를 관측 | data counter 전부 0, security_rejects 1 | data counter 전부 0, security_rejects 1 |

AMS의 peer `attributes`는 분할 ANCS response 수이므로 0이다. client의 두 write 완료는 EU 구독 선택과 RC 제어이며, EA 선택 write는 long-read 단계에 포함되어 별도 완료 event로 세지 않는다. full title은 실제 14-byte 값 대조로 판정한다.

`access_denied`는 bond 생성 전에 실행하며 `pairings=0`, `bonded=0`, `reconnects=0`, `test_bond=0`을 요구한다. 첫 정상 data case는 두 역할 각각 `pairings=1`, `bonded=1`, `test_bond=1`이어야 한다. 이후 같은 boot의 data case는 exact 시험 peer와 현재 bond 집합을 재검증하고 `pairings=0`, `bonded=1`, `reconnects=1`, `test_bond=1`이어야 한다. 정상 case는 PASS 때 link 1이어야 한다. malformed case는 error→disconnect race를 허용하여 PASS 때 link 0 또는 1, 이후 STOP 때 반드시 0이어야 한다. STOPPED는 연결 수 0이고 연결 시도 중인 pending link도 없을 때만 내보낸다. 단순 `ready`나 광고 시작은 PASS가 아니다.

추가 negative는 0/형식오류 nonce·overlong command·다른 nonce peer 2초 관측·잘못된 STOP nonce 거부다. 다른 nonce로 시작한 두 보드는 packet/write/attribute/link 모두 0이어야 한다. 모든 활성 session은 finally에서 STOP하고 `STOPPED links=0`을 요구한다.

## 시험 bond 정리

첫 START 직전의 bond 주소 집합을 RAM baseline으로 고정한다. pairing 완료 peer가 baseline에 없고 현재 집합이 `baseline + peer`와 정확히 같을 때만 그 peer 한 개를 시험 소유 bond로 인정한다. 모든 case를 STOP한 idle 상태에서 최초 소유 nonce와 함께 `CLEANUP <nonce>`를 보내면 양 역할이 각각 그 exact peer만 `eraseBond()`하고 baseline의 수와 원소가 모두 복원됐을 때 `CLEANED`를 출력한다. `CLEANED`의 data·보안 counter와 `test_bond`는 모두 0이다. 전체 bond 삭제와 peer 주소 출력은 허용하지 않는다.

## 유한 동작·잔여 경계

명령은 `STATUS`, `START <32 lowercase hex nonce> <case>`, `STOP <matching nonce>`, idle의 `CLEANUP <owned nonce>`만 허용한다. wire record는 `M33ECO|2`이며 기존 data 분모 외에 `security`, `pairings`, `bonded`, `reconnects`, `security_rejects`, `test_bond`를 항상 포함한다. firmware lease 45초, discovery 15초, 요청 5초, main loop hardware watchdog 5초다. runner case 한도 25초/역할, 일반 command 10초다. 부팅·watchdog·stack·settings 초기화 실패 후 START는 거부하며 storage를 자동 format/erase하지 않는다.

저장 파일은 원본 `transcript.log`, hash·분모·cleanup이 있는 `result.json`이다. 실패도 보존하며 재시도는 새 output을 사용한다. 실패 시 SDK 위험과의 연관은 packet/상태/log 증거로 확인하기 전까지 추정하지 않는다. Apple/macOS/Android/Windows/Linux 실제 peer UX, Fast Pair 계정·Google Find Hub·DULT/물리 motion/speaker 및 cloud/EnOcean은 library README의 사용자 후속 양식으로 별도 기록한다.
