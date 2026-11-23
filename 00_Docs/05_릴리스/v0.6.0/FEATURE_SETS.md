# Arduino IDE에서 Feature set 고르기

`Tools > Board`에서 **NU54DK (nRF54L15, Zephyr)**를 고르면 `Tools > Feature set` 메뉴가 나타납니다. 여기서 스케치를 빌드할 때 사용할 주변장치, 무선 기능, 핀 구성을 고릅니다. 처음 LED를 켜거나 직렬 통신을 해 볼 때는 기본값 **Standard peripherals**로 시작하세요. 다른 예제를 열면 스케치 첫 주석의 권장 항목을 선택하고 다시 **Verify**, **Upload**를 누릅니다. [설치 안내](README.md) · [첫 예제 따라 하기](EXAMPLE_WALKTHROUGH.md)

아래는 v0.6.0의 메뉴 순서입니다. 굵은 이름은 IDE에 보이는 글자이고, `standard` 같은 값은 CLI에서 쓰는 `feature_set` 값입니다. 예제 이름을 누르면 실제 스케치가 열립니다. IDE에서는 `File > Examples` 아래의 NUCODE 라이브러리에서 같은 이름을 찾을 수 있습니다. [보드 메뉴 원본](../../../boards.txt) · [전체 예제 색인](../../../libraries/EXAMPLES.md)

## LED, 직렬 통신, BLE

| IDE 메뉴 / CLI 값 | 언제 고르나요? | 무엇으로 확인하나요? |
| --- | --- | --- |
| **Standard peripherals** / `standard` | 일반 Arduino GPIO, Serial, I2C(Wire), SPI, PWM 등을 쓸 때 | 보드 1대에서 [Blink](../../../libraries/NUCODE_NU54DK/examples/Blink/Blink.ino)를 올리면 내장 LED가 깜빡입니다. [SerialEcho](../../../libraries/NUCODE_NU54DK/examples/SerialEcho/SerialEcho.ino)는 USB 직렬 모니터에서 보낸 한 줄을 돌려줍니다. |
| **Adaptive capabilities (experimental)** / `adaptive` | 사용하는 API, 라이브러리, 예제의 역할 선언에 따라 빌드 기능을 선택하는 실험을 할 때 | [NUSCentral](../../../libraries/NUCODE_BLE/examples/NUSCentral/NUSCentral.ino)은 기본 권장이 BLE NUS이고 adaptive도 허용합니다. 예제 폴더의 [역할 설정](../../../libraries/NUCODE_BLE/examples/NUSCentral/nucode-build.json)을 함께 두고 Verify하세요. 실제 통신에는 상대 보드가 필요합니다. |
| **BLE NUS** / `ble` | Nordic UART Service(NUS)로 BLE를 통해 데이터를 주고받거나 이 구성을 권장하는 BLE 예제를 쓸 때 | [NUSPeripheral](../../../libraries/NUCODE_BLE/examples/NUSPeripheral/NUSPeripheral.ino)이 서비스를 광고하고 [NUSCentral](../../../libraries/NUCODE_BLE/examples/NUSCentral/NUSCentral.ino)이 검색해 연결합니다. 보드 두 대의 직렬 모니터를 열면 한쪽에 입력한 글자가 반대쪽에 보입니다. |
| **Secure BLE DFU (MCUboot)** / `secure_ble_dfu` | MCUboot와 서명된 이미지로 BLE 펌웨어 업데이트를 구현할 때 | [SecureDfuPeripheral](../../../libraries/NUCODE_BLE_DFU/examples/SecureDfuPeripheral/SecureDfuPeripheral.ino)을 빌드하려면 IDE 프로세스에서 읽을 수 있는 외부 ECDSA P-256 키 파일 경로를 `NUCODE_DFU_SIGNING_KEY`에 지정하세요. 업로드 후 직렬 모니터에서 115200 baud와 **Newline**을 선택하고 `STATUS`를 보내 이미지 상태를 읽습니다. 실제 무선 업데이트에는 인증된 상대 장치와 서명된 업데이트 이미지가 필요합니다. [키 준비 및 업데이트 절차](../../../libraries/NUCODE_BLE_DFU/examples/README.md) |

## 주변장치 직접 제어와 외장 오디오

두 메뉴는 디버그 프로브의 UART와 공유하는 핀을 주변장치에 할당합니다. 해당 핀에 외장 장치를 연결할 때는 보드 전원을 끄고 DAP UART의 물리 연결을 분리한 뒤 배선하세요. 업로드에는 CMSIS-DAP USB를 사용합니다. 실행 결과는 예제에서 지정한 LED와 외장 신호로 확인합니다. [P2/P4 커넥터 핀맵](<../../01_아두이노 코어 설계/13_NU54DK_P2_P4_커넥터_핀맵.md>)

| IDE 메뉴 / CLI 값 | 선택 기준과 첫 예제 |
| --- | --- |
| **Peripheral Fabric (DAP UART disconnected)** / `fabric` | UART, SPI, 타이머, DMA 등 특정 주변장치 인스턴스를 직접 다룰 때 선택합니다. [FabricCapabilities](../../../libraries/NUCODE_Peripheral_Fabric/examples/FabricCapabilities/FabricCapabilities.ino)는 보드 한 대에서 주변장치 목록 75개와 필요한 핸들을 확인합니다. 준비되면 초록색 내장 LED가 계속 켜집니다. |
| **BLE Audio external I/O (DAP UART disconnected)** / `ble_audio_io` | 한 보드의 [ExternalPdmMicrophoneSource](../../../libraries/NUCODE_BLE_Audio/examples/ExternalPdmMicrophoneSource/ExternalPdmMicrophoneSource.ino)에서 외장 PDM 마이크 입력을 받고, 다른 보드의 [ExternalI2sSpeakerSink](../../../libraries/NUCODE_BLE_Audio/examples/ExternalI2sSpeakerSink/ExternalI2sSpeakerSink.ino)에서 외장 I2S DAC/앰프로 출력할 때 선택합니다. 예제 폴더의 설정 파일을 유지하고 모듈의 전압, 클록, 공통 GND를 확인하세요. 마이크 쪽 LED는 소스가 스트리밍할 때 켜집니다. 외장 장치의 실제 입출력과 음질은 공개 검증에서 `NOT_RUN`입니다. [배선과 역할별 안내](../../../libraries/NUCODE_BLE_Audio/examples/README.md) |

## 두 보드 사이의 단독 무선

수신 보드를 먼저 준비한 뒤 송신 보드를 켜세요. 두 보드에서 같은 프로토콜과 채널을 사용합니다. 송신 쪽 직렬 모니터의 `acked=` 증가와 수신 쪽의 `sequence=`, `hash=ok`, `duplicate=no`를 함께 보면 실제 패킷이 상대 보드까지 갔는지 알 수 있습니다.

| IDE 메뉴 / CLI 값 | 올릴 예제와 기본 설정 |
| --- | --- |
| **Standalone IEEE 802.15.4 radio** / `radio_ieee802154` | [Radio154Receiver](../../../libraries/NUCODE_Radio_IEEE802154/examples/Radio154Receiver/Radio154Receiver.ino)와 [Radio154Transmitter](../../../libraries/NUCODE_Radio_IEEE802154/examples/Radio154Transmitter/Radio154Transmitter.ino)를 각 보드에 올립니다. 예제의 채널은 20이며 송신 주소는 `0x0001`, 수신 주소는 `0x0002`입니다. |
| **Standalone Enhanced ShockBurst radio** / `radio_esb` | [EsbPrx](../../../libraries/NUCODE_Radio_ESB/examples/EsbPrx/EsbPrx.ino)는 수신, [EsbPtx](../../../libraries/NUCODE_Radio_ESB/examples/EsbPtx/EsbPtx.ino)는 송신입니다. 기본값은 채널 40, 2 Mbit/s입니다. |

## BLE와 다른 무선을 함께 쓸 때

다음 세 예제의 전체 구성을 실행하려면 보드 세 대를 준비합니다. 첫 보드는 아래 표의 공존 스케치, 둘째는 표에 적힌 상대 역할, 셋째는 **BLE NUS**로 빌드한 [NUSCentral](../../../libraries/NUCODE_BLE/examples/NUSCentral/NUSCentral.ino)을 실행합니다. NUSCentral을 스케치북에 복사하고 `scanForNus("NU54-NUS")`의 이름을 아래의 광고 이름으로 바꾸세요. 원래 이름으로 검색하면 공존 보드를 찾을 수 없습니다.

| IDE 메뉴 / CLI 값 | 첫 보드의 스케치와 광고 이름 | 둘째 보드와 관찰할 값 |
| --- | --- | --- |
| **BLE + Bluetooth Mesh coexistence** / `coexistence_ble_mesh` | [BleMeshCoexistence](../../../libraries/NUCODE_Radio_Coexistence/examples/BleMeshCoexistence/BleMeshCoexistence.ino), `NU54-COEX-MESH` | Mesh 네트워크를 구성할 [MeshProvisioner](../../../libraries/NUCODE_BLE_Mesh/examples/MeshProvisioner/MeshProvisioner.ino) 등 호환 상대가 필요합니다. 공존 보드에서 BLE 연결과 Mesh 이벤트 통계를 확인하세요. |
| **BLE + IEEE 802.15.4 coexistence** / `coexistence_ble_154` | [Ble154Coexistence](../../../libraries/NUCODE_Radio_Coexistence/examples/Ble154Coexistence/Ble154Coexistence.ino), `NU54-COEX-154` | 둘째 보드에는 단독 IEEE 802.15.4 구성의 [Radio154Transmitter](../../../libraries/NUCODE_Radio_IEEE802154/examples/Radio154Transmitter/Radio154Transmitter.ino)를 올립니다. BLE 연결을 유지하며 공존 보드의 802.15.4 수신 통계를 봅니다. |
| **BLE + ESB coexistence candidate** / `coexistence_ble_esb` | [BleEsbCoexistence](../../../libraries/NUCODE_Radio_Coexistence/examples/BleEsbCoexistence/BleEsbCoexistence.ino), `NU54-COEX-ESB` | 단독 ESB 구성의 [EsbPtx](../../../libraries/NUCODE_Radio_ESB/examples/EsbPtx/EsbPtx.ino)를 상대로 ESB 수신과 `timeslot_failures`를 관찰합니다. v0.6.0에서는 후보 구성입니다. |

세 스케치의 BLE `delivered`는 연결 중 100 ms마다 증가하는 로컬 계수입니다. 실제 메시지 송수신은 [두 보드의 NUS 예제](EXAMPLE_WALKTHROUGH.md#3-보드-두-대로-ble-메시지-보내기)로 확인하세요.

## 외부 신호선으로 무선 사용을 조정할 때

**BLE external 1-wire coexistence** / `external_coexistence`는 외부 신호 한 선으로 무선 사용을 허용하거나 거부하는 구성입니다. [RadioCoexistenceOneWire](../../../libraries/NUCODE_Radio_Coexistence/examples/RadioCoexistenceOneWire/RadioCoexistenceOneWire.ino)는 NU54DK 한 대에서 이 신호를 만듭니다. 전원을 끈 상태에서 **P4-8(P1.10, 출력)**과 **P4-12(P1.14, 입력)**를 점퍼로 연결하세요. 예제를 올리고 115200 baud에서 `g`(허용)와 `d`(거부)를 차례로 보냅니다. 각 상태에서 1초 간격으로 표시되는 `radio_ready_events=`와 `delta=`를 비교하세요.
