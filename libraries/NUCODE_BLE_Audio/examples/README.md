# NUCODE BLE Audio 예제

이 예제들은 `NUCODE_BLE_Audio.h`의 공개 Arduino API로 LC3와 Bluetooth LE Audio 기능을
실행한다. `.ino`에는 일반 C++로 PCM 생성, codec 설정, encode/decode, 결과 검사와 오류 처리를
보여 준다. liblc3와 Zephyr Audio 객체는 라이브러리 구현 내부에 있다.

이 예제 집합은 개발 소스 `0.4.1-dev`의 LE Audio 표면이다. 완료 감사에 채택된
profile·역할 예제는 build와 합성 PCM/payload의 보드 간 데이터·제어·복구 경로를
검증했다. `ExternalPdmMicrophoneSource`와 `ExternalI2sSpeakerSink`는 build 가능한 실제
연결 예제이지만, 외장 PDM/I2S 장치의 실물 입출력·음질·전기적 호환성은
사용자 후속 `NOT RUN`이다. 현재 설치·지원 package는 `v0.4.1`이며 이 개발
예제들이 그 공개 ZIP에 포함됐다는 뜻은 아니다. 세부 판정은
[검증 기록 목차](<../../../00_Docs/04_검증 기록/README.md>)에서 확인한다.

RAM 사용량은 선택한 역할·Core revision·buffer 설정에 따라 달라진다. 빌드가 표시하는 정적
RAM에는 Audio buffer뿐 아니라 공통 Core 저장소도 포함되므로 Audio 기능만의 요구량으로
해석하지 않는다. 기능을 추가하기 전에 해당 ELF/map과 최종 `.config`로 자원 예산을 확인한다.

BAP 예제 9개(`BapUnicastSource`, `BapUnicastSink`, `BapUnicastCycle`, duplex client/server,
broadcast source/sink/delegator sink/assistant)는 각각 공개 `nucode-build.json` role 선언을 제공한다.
실험적 **NU54DK Zephyr / Adaptive** feature set에서는 이 선언으로 연결 수·ISO stream 수와 필수
Kconfig를 생성하고, 공통 `NUCODE_BLE_Audio.cpp`와 선택 역할의 unicast/broadcast backend만 빌드한다.
예제의 저수준 `prj.conf` 목록을 adaptive 역할 해석의 단일 원본으로 사용하지 않으며, 현재 기본
`standard`와 BLE 호환 profile의 동작은 바꾸지 않는다.

`HearingAccessServer`와 `HearingAccessClient`도 각각 공개 role 선언을 제공한다. Adaptive
feature set은 HAS server/client 설정과 연결·ISO capacity를 생성하고, Audio 공통 facade와
`NUCODE_BLE_Audio_HearingAccess.cpp`만 선택한다. 두 예제의 `NUCODE_BLE_Security` 의존성은
pairing·bond·ZMS settings backend만 포함하며, 사용하지 않는 BAS·DIS·HID·HRS source와 Kconfig는
제외한다.

## `Lc3SyntheticLoopback`

- `Lc3Codec::begin()`으로 16 kHz, 10 ms, 40-byte LC3 frame을 구성한다.
- 서로 다른 합성 삼각파 PCM 100 frame을 `encode()`한 뒤 `decode()`한다.
- frame 수, encoded checksum과 decoded energy를 검사한다. LC3는 손실 codec이므로 입력 PCM과
  출력 PCM의 byte 동일성은 합격 기준으로 사용하지 않는다.
- 잘못된 frame duration과 sample rate가 `Error::invalid_argument`로 거부되는지도 확인한다.

예제의 `prj.conf`는 `CONFIG_LIBLC3`, FPU, Arduino runtime과 Serial을 고정한다. Arduino IDE나
CLI에서 **NU54DK Zephyr / BLE** feature set으로 빌드한다.

## `BapUnicastSink`

- 두 보드를 준비해 이 스케치를 sink 보드에 올린다. 상대 보드에는 같은 라이브러리의
  `BapUnicastSource` 예제를 올린다.
- 스케치가 PACS/ASCS의 mono LC3 sink를 등록하고 ASCS UUID를 광고한다. 상대 client가
  연결해 codec/QoS와 ASE를 설정하면 40-byte LC3 frame을 실제 CIS로 보낸다.
- `loop()`가 공개 `UnicastServer::readFrame()`으로 frame을 읽고 `Lc3Codec::decode()`를
  호출한다. 115200 baud Serial은 100 frame마다 decoded 수·PCM energy·queue drop 수를
  표시한다. 정상 전송에서는 `dropped=0`을 기대한다.
- 예제의 `prj.conf`는 16 kHz·10 ms LC3, sink ASE 1개, ISO channel 1개와 비영속
  LE Secure Connections pairing을 고정한다. `CONFIG_BT_SETTINGS=n`은 다른 예제에서
  남은 bond를 변경하거나 지우지 않으면서 새 상대와 L2 연결을 시험하기 위한 선택이다.
- 연결이 끊기면 광고를 다시 시작한다. Source는 새 sink 광고를 검색해 새 LC3
  stream을 연다. 보드 재시작 뒤 새 연결의 frame 수를 확인할 수 있다.
- 외장 mic/speaker나 추가 stream을 합치기 전에 해당 build의 RAM 여유와 buffer 예산을
  다시 계산해야 한다.

## `BapUnicastSource`

- 두 보드에 각각 `BapUnicastSource`와 `BapUnicastSink`를 올린다. Source는
  ASCS UUID를 광고하는 sink를 검색하고 연결한 뒤 공개 `UnicastClient`로
  PACS/ASCS 설정과 CIS 시작을 진행한다.
- Arduino `loop()`에서 16 kHz 합성 PCM을 만들고 `Lc3Codec::encode()`로
  40-byte LC3 frame을 생성해 `UnicastClient::sendFrame()`으로 보낸다.
  Zephyr 호출은 라이브러리 구현 내부에만 있다.
- `prj.conf`는 unicast client, ISO TX와 liblc3를 선택한다. 일시적인 L2
  pairing을 사용하므로 다른 예제의 bond 설정을 변경하지 않는다.
- sink 보드가 재시작되면 검색과 연결을 다시 시도한다. 두 역할의 Serial에서
  `source streaming`, `sent frames=100`, `decoded frames=100`을 새로 확인한다.
- Serial에 `s`를 보내면 공개 `UnicastClient::stop()`으로 ASE를 disable·release한 뒤
  연결을 끊고 새 stream을 연다.

## `BapUnicastDuplexServer`

- 두 보드 중 서버에 올린다. 이 예제는 `UnicastServerMode::duplex`로 sink와
  source ASE를 각각 하나 등록하고 ASCS UUID를 광고한다. 상대 client에는 양방향
  BAP 지원 image가 필요하다. 같은 목록의 `BapUnicastDuplexClient`를 짝으로
  사용할 수 있으며, 고정 NCS `bap_unicast_client`와도 별도로 확인한다.
- `loop()`가 수신 LC3 frame을 복호화하고 PCM energy를 계산한다. 동시에 일반
  C++로 합성 PCM을 만들어 LC3로 인코딩한 뒤 공개 `sendFrame()`으로 반대 방향에
  보낸다. 정상 동작이면 115200 baud Serial에 `duplex received=... energy=...
  dropped=0`과 `duplex sent=...`가 각각 100 frame마다 나타난다.
- `prj.conf`는 sink/source ASE 각 1개, 양방향 ISO channel 2개, LC3와 비영속
  L2 pairing을 고정한다. 추가 buffer/stream과 외장 audio I/O를 합치기 전에 해당 build의
  RAM 여유와 자원 예산을 다시 측정한다.

## `BapUnicastDuplexClient`

- 상대 보드에 `BapUnicastDuplexServer`를 올리고 이 예제를 client 보드에 올린다.
  ASCS UUID를 검색한 뒤 공개 `UnicastClientMode::duplex`로 PACS/ASCS의
  sink/source ASE를 한 unicast group에 묶는다.
- `loop()`에서 합성 PCM을 LC3로 encode해 보내고, 반대 방향의 LC3 frame을
  `readFrame()`으로 꺼내 decode한다. 115200 baud Serial의 `duplex sent
  frames=...`와 `duplex received=... energy=... dropped=0`을 두 보드에서
  확인한다. `s`를 입력하면 양쪽 ASE의 disable/release를 요청한다.
- 고정 SDK는 client의 방향별 ASE 검색 용량을 0 또는 2개 이상으로 요구한다.
  따라서 `prj.conf`는 각 방향 검색 용량 2개, 실제 group stream 2개와
  ISO channel 2개를 설정한다. 예제는 각 방향 첫 ASE 하나만 사용한다.

## `BapUnicastCycle`

- `BapUnicastSink`와 짝을 이뤄 실행한다. 매 연결에서 합성 LC3 frame 120개를
  보내고 `UnicastClient::stop()`으로 ASE를 disable·release한다.
- `stream stopped`와 `completed cycles=N`을 출력한 뒤 연결을 끊고 새 광고를
  검색한다. 두 보드가 다시 연결되면 새로운 frame을 보낸다. 외부 Serial 명령이나
  오디오 장치 없이 stream 수명과 복구를 반복 시험하는 예제다.
- stop 직후 중복 stop과 frame 전송을 각각 거부하는지 확인하고
  `invalid transition rejected`를 출력한다.

## `BapBroadcastSource`

- BAP Broadcast Audio announcement와 BASE를 extended/periodic advertising으로 게시하고,
  16 kHz·10 ms·40-byte LC3 frame 한 개를 BIS 1로 보낸다. 공개 `BroadcastSource`와
  `BroadcastCode`, `Lc3Codec`만 사용하며 `loop()`가 일반 C++로 합성 PCM을 생성한다.
  예제의 16-byte `broadcastCode`를 바꾸면 암호화 code를 직접 선택할 수 있다.
- 정상 동작이면 `broadcast source streaming` 뒤 `broadcast sent frames=...`가 100 frame마다
  출력된다. `s`는 방송과 광고를 정리하고 `r`은 같은 객체로 다시 시작한다.

## `BapBroadcastSink`

- 이름이 `NU54-AUDIO-BROADCAST`인 Broadcast Audio source를 검색한 뒤 periodic advertising,
  BASE, BIGInfo, BIS 1 순서로 동기화한다. 공개 `BroadcastSink::poll()`이 비동기 단계를
  진행하며 `readFrame()`으로 받은 LC3 frame을 `Lc3Codec`으로 decode한다. source와 같은
  `broadcastCode`를 사용해야 암호화 BIS를 수신한다.
- 정상 동작이면 `broadcast sink streaming` 뒤 `broadcast received=... energy=...
  dropped=...`가 100 frame마다 출력된다. `s`와 `r`로 BIS/PA 동기화 중단과 재시작을
  반복할 수 있다. `w`는 한 byte가 다른 code로 다시 동기화해 거부 경로를 확인한다.

## `BapBroadcastDelegatorSink`

- 세 보드 중 Delegator-Sink 보드에 올린다. `BroadcastSink::beginDelegated()`가 BASS와
  PACS를 제공하고, 연결 광고는 공개 `BLEAdvertising`으로 BASS/PACS UUID를 게시한다.
- Assistant가 source를 추가하면 주소·SID·Broadcast ID가 모두 일치하는 광고만 선택해
  PA, BASE, BIG, BIS 1 순서로 동기화한다. 암호화 code도 Assistant가 BASS로 전달한다.
- Serial은 add/modify/remove 수락 수와 실제 LC3 decode frame·energy·drop을 출력한다.
  remove 뒤에는 수신 자원만 반환하고 BASS/PACS와 연결 광고는 유지해 새 add를 받을 수 있다.
- 추가 stream이나 큰 queue를 합치기 전에 해당 build의 RAM 여유와 자원 예산을 확인한다.

## `BapBroadcastAssistant`

- 세 보드 중 Assistant 보드에 올린다. BASS UUID를 광고하는 Delegator에 연결하고 공개
  `BLESecurity`로 encrypted ACL을 만든 뒤 `BroadcastAssistant`로 BASS를 검색한다.
- 공개 `BLEScan` 결과에서 Broadcast Audio announcement를 선택해 add와 Broadcast Code를
  전달한다. receive state 통지의 source ID, PA sync, BIS sync 상태를 Serial에 출력한다.
- `m`은 PA/BIS 해제 modify, `d`는 해제된 source remove, `r`은 resume 또는 re-add,
  `a`는 duplicate add, `x`는 올바른 announcement가 없는 source 선택 거부, `q`는 receive
  state 재읽기다. remove는 먼저 `m`으로 PA/BIS를 해제한 뒤 실행한다.

## `AudioControlDevice`

- `VolumeRenderer`와 `MicrophoneDevice`가 VCP·MICP service를 제공한다. Volume Renderer에는
  output offset용 VOCS 한 개와 program input용 AICS 한 개가 포함되고, Microphone Device에는
  microphone gain용 AICS 한 개가 별도로 포함된다.
- 광고 전에 초기 volume·step·offset·input gain과 설명을 일반 C++ config로 지정한다. `loop()`의
  Serial 명령은 local volume, offset, 두 input gain과 microphone mute를 공개 API로 바꾸며 원격
  Controller의 변경도 `stateUpdates()`와 snapshot으로 확인한다.
- service는 image 수명 동안 유지된다. 연결이 끊기면 profile을 재등록하지 않고 같은 VCS·MICS UUID
  광고를 다시 시작한다.

## `AudioControlController`

- VCS UUID를 광고하는 장치를 검색해 연결하고 encrypted link가 된 뒤 `VolumeController`로 VCP와
  포함 VOCS·AICS를 검색한다. 이 검색이 끝난 다음 `MicrophoneController`로 MICP와 별도 AICS를
  검색하므로 한 연결의 GATT discovery를 겹치지 않는다.
- Serial 명령으로 volume up/down/mute, offset, program input gain, microphone mute와 microphone
  input gain을 변경한다. 각 요청은 완료 callback 전까지 busy이며 범위 밖 값, 쓰기 권한 거부와
  연결 소실의 원본 오류를 `nativeCode()`로 확인할 수 있다.
- 연결이 끊기면 두 controller facade를 종료하고 새 handle에서 보안과 discovery를 다시 수행한다.
  이전 generation의 callback은 새 session 상태로 수락하지 않는다.
- active 연결에서 facade를 먼저 종료하면 이전 callback을 새 소유자와 구분할 수 없으므로, 같은 profile
  client는 그 연결이 끊길 때까지 새 facade의 `begin()`을 `busy`로 거부한다.

## `HearingAccessServer`

- `HearingAccessServer`가 HAS를 광고 전에 등록하고 Universal·Outdoor·Noisy room preset을
  고정 메모리에 게시한다. `1`, `5`, `8` 명령으로 local active index를 바꾸며 연결된 client에도
  변경을 알린다.
- `n`은 writable preset의 이름을 바꾸고 `a`는 preset availability를 전환한다. 범위 밖 index,
  빈 이름, unavailable preset 선택은 공개 오류와 `nativeCode()`로 구분한다.
- HAS service 자체는 image 수명 동안 유지된다. `end()`는 preset과 facade 소유권만 반환하므로
  같은 image에서 다시 시작할 때 최초 보청기 형식을 유지한다.

## `HearingAccessClient`

- HAS UUID를 검색해 bonded encrypted link를 만든 뒤 `HearingAccessClient`로 service와 notification을
  찾는다. 준비되면 공개 `readPresets()`로 index·availability·writable·name을 Arduino 메모리에
  복사한다.
- `1`, `5`, `8`은 특정 preset, `n`과 `p`는 다음·이전 preset을 선택한다. `r`은 목록을 다시
  읽고 `s`는 active index와 cache를 출력한다. 지원되지 않는 index는 원격 ATT/HAS 오류로
  거부되며 연결 해제 뒤 새 handle에서 검색을 다시 시작한다.
- 두 예제의 `c` 명령은 각 장치에 저장된 bond를 공개 Security API로 지우고 남은 수를 출력한다.

## TMAP 역할 예제

`TelephonyMediaGateway`와 `TelephonyMediaTerminal`은 각각 CG+UMS와 CT+UMR 역할을
게시한다. Gateway는 TMAS(`0x1855`)를 검색해 encrypted 연결을 만든 뒤 실제 TMAP Role
characteristic을 읽고 CT+UMR bit가 모두 있는지 검사한다. 역할이 맞으면 `UnicastClient`가
PACS/ASCS 절차를 시작하고 합성 PCM을 LC3로 encode해 보낸다. Terminal의 `UnicastServer`는
frame을 읽어 PCM으로 decode한다. `s`는 stream 또는 server를 중단하고 `r`은 새 session을
시작하며 `x`는 유효하지 않은 handle 또는 image에 없는 역할이 거부되는지 확인한다.

`TelephonyMediaBroadcaster`와 `TelephonyMediaReceiver`는 BMS와 BMR을 각각 게시한다.
Broadcaster는 `BroadcastSource`로 LC3 BIS를 보내고 Receiver는 `BroadcastSink`로 frame을
읽어 decode한다. Serial `s`는 방송을 종료하고 `r`은 공개 API로 같은 방송을 다시 시작한다.
`x`는 image에 없는 반대 역할 요청을 거부한다. 각 `prj.conf`는 역할별 CAP/BAP/VCP/MCS/TBS
의존성과 ISO buffer/channel 수를 고정한다.

## GMAP 역할 예제

`GamingAudioGateway`와 `GamingAudioTerminal`은 UGG와 UGT 역할을 제공한다. Gateway는
encrypted GMAS(`0x1858`) 검색으로 역할·feature characteristic을 읽고 UGT를 검사한다.
Terminal은 sink feature를 게시한다. 역할 확인 뒤 Gateway의 `UnicastClient`가 LC3 frame을
보내고 Terminal의 `UnicastServer`가 이를 읽어 decode한다. Serial `s`는 stream을 중단하고
`r`은 disconnect/광고 재시작 경로이며 `x`는 stale/invalid peer 또는 image에 없는 역할
요청의 fail-closed 경로다.

`GamingAudioBroadcaster`와 `GamingAudioReceiver`는 BGS와 BGR을 각각 게시한다. 실제 공개
facade가 사용하지 않는 96 kbps·multiplex 선택 feature는 주장하지 않는다. 네 GMAP 예제의
`q` 명령은 예약 feature bit를 거부하는 품질 설정 불일치 경로다. 방송 두 예제는
`BroadcastSource`/`BroadcastSink`로 LC3 BIS를 실제로 보내고 읽으며 `s`/`r`로
중단·재시작한다. 이 예제는 역할·필수 service 조합과 stream procedure를 제공하지만
지연·음질·상용 게임 제품 상호운용을 보증하지 않는다.

네 TMAP 예제는 고정 Zephyr의 `samples/bluetooth/tmap_central`, `tmap_peripheral`,
`tmap_bms`, `tmap_bmr`와 `subsys/bluetooth/audio/tmap.c`를 기준으로 구성했다. GMAP은 같은
revision의 `include/zephyr/bluetooth/audio/gmap.h`, `gmap_server.c`, `gmap_client.c`가
원본이다. upstream 파일은 Apache-2.0, 이 Arduino library와 예제는 MIT를 따른다. upstream
sample은 nRF54L15를 allowlist에 직접 열거하지 않으므로 NU54DK target build와 board runtime은
별도로 판정한다. 실제 phone, headset, console 상호운용은 사용자 후속 `NOT RUN`이며 개발
기능의 build/board 검증과 합산하지 않는다.

Arduino IDE나 CLI에서 **NU54DK Zephyr / BLE** feature set으로 빌드한다. 115200 baud
Serial의 frame 카운터는 실기 확인용이다. PDM/I2S microphone과 I2S codec/speaker 경로는
외장 I/O 예제에서 별도로 다룬다.

## 외부 microphone·codec·speaker 연결

`ExternalPdmMicrophoneSource`와 `ExternalI2sSpeakerSink`는 **NU54DK Zephyr / BLE Audio
external I/O (DAP UART disconnected)** feature set으로 빌드한다. 이 profile은 PDM/I2S의
EasyDMA와 IRQ를 `StreamFabric`이 직접 소유하도록 표준 Serial·Wire·SPI·ADC·PWM을 끈다.
두 예제는 Zephyr API를 직접 호출하지 않으며 공개 `NUCODE_BLE_Audio`와
`NUCODE_Peripheral_Fabric` API만 사용한다.

- 두 보드 모두 전원을 끈 상태에서 DAP UART routing을 분리한다. 이 profile에서는 P1.4~P1.7을
  외부 audio에 사용하므로 같은 핀에 DAP VCOM이나 다른 출력이 연결된 채 실행하면 안 된다.
- PDM microphone 보드는 P1.4를 `CLK`, P1.6을 `DATA`에 연결하고 3.3 V와 GND를 공유한다.
  예제는 PDM20, 16 kHz mono, 160 sample(10 ms) double buffer를 사용한다. 1.8 V 전용 microphone은
  직접 연결하지 말고 올바른 level shifter와 전원을 사용한다.
- I2S speaker 보드는 P1.4를 `BCLK/SCK`, P1.5를 `LRCLK/WS`, P1.7을 `SDOUT/DIN`에 연결하고
  GND를 공유한다. 예제는 NU54DK master, 16 kHz, 16-bit stereo를 사용하며 MCLK는 출력하지 않는다.
  따라서 16 kHz BCLK 기반 동작을 지원하는 외부 codec/DAC·amplifier만 연결한다. passive speaker를
  GPIO에 직접 연결하지 않는다.
- microphone source의 LED는 source ASE가 streaming일 때, speaker sink의 LED는 client stream이
  준비됐을 때 켜진다. DAP UART를 분리하므로 이 두 예제는 Serial 성공 문자열에 의존하지 않는다.
- 먼저 source를 켜고 sink를 켠다. sink는 ASCS 광고를 찾아 연결하고, PDM PCM은 LC3 encode → CIS →
  LC3 decode → I2S DMA 경로를 통과한다. 연결이 끊기면 source는 다시 광고하고 sink는 다시 검색한다.
- 핀·sample rate·frame 크기를 바꾸려면 두 `.ino`의 `PdmConfiguration` 또는
  `I2sConfiguration`과 `samplesPerFrame`, 양쪽 LC3 설정을 함께 바꾼다. DMA buffer는 함수 지역
  임시 배열로 바꾸지 않는다.

외부 장치의 전압·clock 방식·증폭기 요구사항은 부품 datasheet가 우선한다. 위 경로는 실제 연결용
구현과 build 가능한 예제이며, 특정 microphone/codec/speaker의 음질·전기적 호환성 실물 검증을
대신하지 않는다.

## `MediaControlPlayer` / `MediaControlClient`

- Player는 고정 Zephyr `BT_MPL` 합성 player와 `BT_MCS`를 등록한다. 실제 음원 없이도 track title,
  duration/position, 재생 상태, 지원 opcode와 OTS 48-bit track object를 실제 GATT characteristic으로
  읽고 Media Control Point 명령을 전달할 수 있다.
- Client는 MCS UUID를 검색하고 encrypted ACL에서 `MediaControlClient::begin()`을 호출한다. `poll()`이
  player name → track title → duration/position → media state → opcode → CCID → object ID를 순차로
  읽는다. Serial `p/u/x/n/b/+`는 play/pause/stop/next/previous/move-relative 명령이고 `i`는 현재
  object ID 선택, `r`은 전체 snapshot 재읽기다. `k`는 지원하지 않는 opcode, `z`는 존재하지 않는
  object ID를 보내 negative 경로와 자동 복구를 확인한다.
- `0` 또는 48-bit 범위 밖 object ID, discovery 전 명령, 완료 전 중복 명령은 공개 오류로 거부한다.
  연결이 끊기면 old handle을 폐기하고 새 encrypted 연결에서 discovery를 다시 수행한다.
- Player service는 image 수명 자원이다. `end()`는 공개 소유권만 해제하며 같은 부팅에서 service를
  다시 등록하지 않는다. 실제 media engine 연결은 이 예제의 합성 player 범위 밖이며 필요하지 않다.

## `CallControlServer` / `CallControlClient`

- Server는 `BT_CCP_CALL_CONTROL_SERVER`와 GTBS 한 개를 등록한다. Serial `i`는 `tel:` URI의 합성
  incoming call을 만들고 `a/h/r/x`는 remote answer/hold/retrieve/terminate 상태를 실제 TBS
  characteristic과 notification에 반영한다.
- Client는 GTBS UUID를 검색하고 encrypted ACL에서 discovery와 call-state 구독을 시작한다. Serial
  `o/a/h/r/x`는 originate/accept/hold/retrieve/terminate control point를 사용하고 `q`는 상태를
  다시 읽는다. `j`는 stale call index, `v`는 현재 상태와 맞지 않는 retrieve 전이를 요청한다.
  거부 결과는 `*_NEG_* rejected=1`로, 정상 완료 누계는 `complete=1 normal_ops=N`으로 출력한다.
- 각 예제는 한 연결, 최대 두 call과 12 ATT TX buffer를 고정한다. 실제 전화망·휴대전화·음향 경로는
  사용하지 않으며 합성 URI와 call state로 server/client 명령·통지·복구를 재현한다.

MCP/MCS 구현 근거는 고정 Zephyr의 `subsys/bluetooth/audio/mpl.c`, `mcs.c`, `mcc.c`와
`samples/bluetooth/tmap_central`, `tmap_peripheral`이다. CCP/TBS 근거는
`samples/bluetooth/ccp_call_control_server`, `ccp_call_control_client`이다. 두 CCP sample의
upstream `sample.yaml`은 nRF5340/QEMU를 명시하고 nRF54L15를 allowlist에 넣지 않으므로,
NU54DK Arduino build와 실제 보드 실행은 별도 판정한다. 라이브러리 코드는 MIT이고 고정 SDK
원본은 Apache-2.0을 따른다.

## 출처와 라이선스

LC3 frame 계약은 고정 NCS v3.4.0의 `samples/bluetooth/bap_unicast_client`,
`bap_unicast_server`, `bap_broadcast_source`, `bap_broadcast_sink`,
`bap_broadcast_assistant`, Zephyr `hap_ha`와 HAS client test를 기준으로 확인했다.
이 라이브러리 코드는 MIT이고, 고정 SDK의
원본 sample과 liblc3는 각 원본 라이선스를 따른다.
