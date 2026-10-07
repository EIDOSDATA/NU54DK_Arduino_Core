# NU54DK 예제 안내

공개 예제는 모두 보존하되, 처음부터 204개를 읽지 않아도 되도록 `Start Here → Functional Recipe → Reference` 순서로 찾습니다.
Build 결과와 실제 보드 runtime, 외부 제품 상호운용은 서로 다른 판정입니다. 각 Sketch 맨 위의 생성 안내에서 profile·역할·성공 조건을 먼저 확인하십시오.

## Start Here — 12개 사용 시나리오

### 1. 보드 연결과 첫 실행

- [NUCODE_NU54DK/Blink](<NUCODE_NU54DK/examples/Blink/Blink.ino>): NU54DK 내장 LED를 250 ms 간격으로 점멸합니다.
- [NUCODE_NU54DK/BoardInfo](<NUCODE_NU54DK/examples/BoardInfo/BoardInfo.ino>): NU54DK 모델, target, device ID와 reset 원인을 출력합니다.

### 2. 통신과 runtime pin 변경

- [NUCODE_NU54DK/Serial1RuntimePins](<NUCODE_NU54DK/examples/Serial1RuntimePins/Serial1RuntimePins.ino>): uart30 Serial1의 핀 선택과 begin/end 재시작 예제입니다.
- [NUCODE_NU54DK/WireRuntimePins](<NUCODE_NU54DK/examples/WireRuntimePins/WireRuntimePins.ino>): TWIM22 controller의 runtime SDA/SCL 선택 예제입니다.
- [NUCODE_NU54DK/SPI00RuntimePins](<NUCODE_NU54DK/examples/SPI00RuntimePins/SPI00RuntimePins.ino>): SPI00 전용 SCK/MISO/MOSI route와 transaction 예제입니다.

### 3. 설정과 파일 저장

- [NUCODE_NU54DK/SettingsStorage](<NUCODE_NU54DK/examples/SettingsStorage/SettingsStorage.ino>): NU54DK 내부 storage_partition에 boot count를 저장합니다.
- [LittleFS/LittleFSPersistence](<LittleFS/examples/LittleFSPersistence/LittleFSPersistence.ino>): 비파괴 mount와 명시적 LittleFS 복구 사용법을 보여 줍니다.

### 4. 주변장치 직접 제어

- [NUCODE_Peripheral_Fabric/FabricCapabilities](<NUCODE_Peripheral_Fabric/examples/FabricCapabilities/FabricCapabilities.ino>): `NUCODE_Peripheral_Fabric/FabricCapabilities` 공개 API의 기본 사용 흐름을 실행합니다.

### 5. BLE 연결부터 시작

- [NUCODE_BLE/GAPPeripheral](<NUCODE_BLE/examples/GAPPeripheral/GAPPeripheral.ino>): 이름·UUID·manufacturer data를 포함한 connectable 광고 예제입니다.
- [NUCODE_BLE/GAPCentral](<NUCODE_BLE/examples/GAPCentral/GAPCentral.ino>): exact local-name scan 결과에 한 번 연결하는 GAP central 예제입니다.

### 6. BLE UART로 데이터 교환

- [NUCODE_BLE/NUSPeripheral](<NUCODE_BLE/examples/NUSPeripheral/NUSPeripheral.ino>): NU54DK를 Nordic UART Service Peripheral로 실행합니다.
- [NUCODE_BLE/NUSCentral](<NUCODE_BLE/examples/NUSCentral/NUSCentral.ino>): 이름과 NUS service로 Peripheral을 찾는 NU54DK Central 예제입니다.

### 7. 보안 센서와 입력 장치

- [NUCODE_BLE_Security/HeartRate](<NUCODE_BLE_Security/examples/HeartRate/HeartRate.ino>): 표준 BLE Heart Rate Service 측정값을 갱신합니다.
- [NUCODE_BLE_Security/SecureKeyboard](<NUCODE_BLE_Security/examples/SecureKeyboard/SecureKeyboard.ino>): 버튼 확인 뒤 bonding하고 암호화 BLE HID key report를 보냅니다.

### 8. 두 link와 L2CAP CoC

- [NUCODE_BLE/MixedRoleLinks](<NUCODE_BLE/examples/MixedRoleLinks/MixedRoleLinks.ino>): 한 NU54DK가 central 1-link와 peripheral 1-link를 동시에 유지하는 예제입니다.
- [NUCODE_BLE/L2capCocClient](<NUCODE_BLE/examples/L2capCocClient/L2capCocClient.ino>): 한 BLE link에 두 LE CoC channel을 열고 512-byte echo를 확인하는 client 예제입니다.
- [NUCODE_BLE/L2capCocServer](<NUCODE_BLE/examples/L2capCocServer/L2capCocServer.ino>): 두 LE CoC channel에서 최대 512-byte SDU를 그대로 돌려주는 echo server 예제입니다.

### 9. Mesh 장치 제어

- [NUCODE_BLE_Mesh/MeshOnOff](<NUCODE_BLE_Mesh/examples/MeshOnOff/MeshOnOff.ino>): Generic OnOff acknowledged와 unacknowledged 전송을 번갈아 실행합니다.
- [NUCODE_BLE_Mesh/MeshProvisioner](<NUCODE_BLE_Mesh/examples/MeshProvisioner/MeshProvisioner.ino>): PB-ADV와 PB-GATT beacon을 발견해 순차 provisioning합니다.

### 10. LE Audio 양방향 stream

- [NUCODE_BLE_Audio/BapUnicastDuplexClient](<NUCODE_BLE_Audio/examples/BapUnicastDuplexClient/BapUnicastDuplexClient.ino>): 합성 PCM을 보내고 상대 LC3 frame을 복호화하는 양방향 client입니다.
- [NUCODE_BLE_Audio/BapUnicastDuplexServer](<NUCODE_BLE_Audio/examples/BapUnicastDuplexServer/BapUnicastDuplexServer.ino>): 한 CIS의 양방향 LC3 stream을 받아 복호화하고 합성 PCM을 보냅니다.

### 11. Channel Sounding 거리 측정

- [NUCODE_BLE_ChannelSounding/RasInitiator](<NUCODE_BLE_ChannelSounding/examples/RasInitiator/RasInitiator.ino>): 보안 연결의 Ranging Service를 찾아 CS raw step을 수집합니다.
- [NUCODE_BLE_ChannelSounding/RasReflector](<NUCODE_BLE_ChannelSounding/examples/RasReflector/RasReflector.ino>): 보안 BLE 연결에서 Ranging Service와 CS reflector를 실행합니다.

### 12. 서명된 BLE firmware update

- [NUCODE_BLE_DFU/SecureDfuPeripheral](<NUCODE_BLE_DFU/examples/SecureDfuPeripheral/SecureDfuPeripheral.ino>): 인증된 BLE SMP DFU와 MCUboot image 확인 절차를 실행합니다.

## Functional Recipe — 29개 기능군

한 기능군 안에서도 central/peripheral, advertiser/observer처럼 역할과 상태 전이가 다르면 별도 Sketch로 유지합니다.

### `analog_pwm_tone` (6개)

[NUCODE_NU54DK/AnalogChannels](<NUCODE_NU54DK/examples/AnalogChannels/AnalogChannels.ino>), [NUCODE_NU54DK/AnalogReadA0](<NUCODE_NU54DK/examples/AnalogReadA0/AnalogReadA0.ino>), [NUCODE_NU54DK/AnalogResolution](<NUCODE_NU54DK/examples/AnalogResolution/AnalogResolution.ino>), [NUCODE_NU54DK/DynamicPWM](<NUCODE_NU54DK/examples/DynamicPWM/DynamicPWM.ino>), [NUCODE_NU54DK/PWMFade](<NUCODE_NU54DK/examples/PWMFade/PWMFade.ino>), [NUCODE_NU54DK/ToneOutput](<NUCODE_NU54DK/examples/ToneOutput/ToneOutput.ino>)

### `ble_advertising_scanning` (18개)

[NUCODE_BLE/AdvertisingAcceptList](<NUCODE_BLE/examples/AdvertisingAcceptList/AdvertisingAcceptList.ino>), [NUCODE_BLE/AdvertisingCodingSelection](<NUCODE_BLE/examples/AdvertisingCodingSelection/AdvertisingCodingSelection.ino>), [NUCODE_BLE/DirectedAdvertisingCentral](<NUCODE_BLE/examples/DirectedAdvertisingCentral/DirectedAdvertisingCentral.ino>), [NUCODE_BLE/DirectedAdvertisingPeripheral](<NUCODE_BLE/examples/DirectedAdvertisingPeripheral/DirectedAdvertisingPeripheral.ino>), [NUCODE_BLE/EncryptedAdvertisingCentral](<NUCODE_BLE/examples/EncryptedAdvertisingCentral/EncryptedAdvertisingCentral.ino>), [NUCODE_BLE/EncryptedAdvertisingPeripheral](<NUCODE_BLE/examples/EncryptedAdvertisingPeripheral/EncryptedAdvertisingPeripheral.ino>), [NUCODE_BLE/ExtendedAdvertising](<NUCODE_BLE/examples/ExtendedAdvertising/ExtendedAdvertising.ino>), [NUCODE_BLE/ExtendedScanner](<NUCODE_BLE/examples/ExtendedScanner/ExtendedScanner.ino>), [NUCODE_BLE/MultipleAdvertisingSets](<NUCODE_BLE/examples/MultipleAdvertisingSets/MultipleAdvertisingSets.ino>), [NUCODE_BLE/MultiplePeriodicSyncs](<NUCODE_BLE/examples/MultiplePeriodicSyncs/MultiplePeriodicSyncs.ino>), [NUCODE_BLE/PastReceiver](<NUCODE_BLE/examples/PastReceiver/PastReceiver.ino>), [NUCODE_BLE/PastSender](<NUCODE_BLE/examples/PastSender/PastSender.ino>), [NUCODE_BLE/PawrAdvertiser](<NUCODE_BLE/examples/PawrAdvertiser/PawrAdvertiser.ino>), [NUCODE_BLE/PawrScanner](<NUCODE_BLE/examples/PawrScanner/PawrScanner.ino>), [NUCODE_BLE/PeriodicAdvertiser](<NUCODE_BLE/examples/PeriodicAdvertiser/PeriodicAdvertiser.ino>), [NUCODE_BLE/PeriodicAdvertiserList](<NUCODE_BLE/examples/PeriodicAdvertiserList/PeriodicAdvertiserList.ino>), [NUCODE_BLE/PeriodicScanner](<NUCODE_BLE/examples/PeriodicScanner/PeriodicScanner.ino>), [NUCODE_BLE/PrivacyPeripheral](<NUCODE_BLE/examples/PrivacyPeripheral/PrivacyPeripheral.ino>)

### `ble_audio` (37개)

[NUCODE_BLE_Audio/AudioControlController](<NUCODE_BLE_Audio/examples/AudioControlController/AudioControlController.ino>), [NUCODE_BLE_Audio/AudioControlDevice](<NUCODE_BLE_Audio/examples/AudioControlDevice/AudioControlDevice.ino>), [NUCODE_BLE_Audio/BapBroadcastAssistant](<NUCODE_BLE_Audio/examples/BapBroadcastAssistant/BapBroadcastAssistant.ino>), [NUCODE_BLE_Audio/BapBroadcastDelegatorSink](<NUCODE_BLE_Audio/examples/BapBroadcastDelegatorSink/BapBroadcastDelegatorSink.ino>), [NUCODE_BLE_Audio/BapBroadcastSink](<NUCODE_BLE_Audio/examples/BapBroadcastSink/BapBroadcastSink.ino>), [NUCODE_BLE_Audio/BapBroadcastSource](<NUCODE_BLE_Audio/examples/BapBroadcastSource/BapBroadcastSource.ino>), [NUCODE_BLE_Audio/BapUnicastCycle](<NUCODE_BLE_Audio/examples/BapUnicastCycle/BapUnicastCycle.ino>), [NUCODE_BLE_Audio/BapUnicastDuplexClient](<NUCODE_BLE_Audio/examples/BapUnicastDuplexClient/BapUnicastDuplexClient.ino>), [NUCODE_BLE_Audio/BapUnicastDuplexServer](<NUCODE_BLE_Audio/examples/BapUnicastDuplexServer/BapUnicastDuplexServer.ino>), [NUCODE_BLE_Audio/BapUnicastSink](<NUCODE_BLE_Audio/examples/BapUnicastSink/BapUnicastSink.ino>), [NUCODE_BLE_Audio/BapUnicastSource](<NUCODE_BLE_Audio/examples/BapUnicastSource/BapUnicastSource.ino>), [NUCODE_BLE_Audio/CallControlClient](<NUCODE_BLE_Audio/examples/CallControlClient/CallControlClient.ino>), [NUCODE_BLE_Audio/CallControlServer](<NUCODE_BLE_Audio/examples/CallControlServer/CallControlServer.ino>), [NUCODE_BLE_Audio/CapAcceptor](<NUCODE_BLE_Audio/examples/CapAcceptor/CapAcceptor.ino>), [NUCODE_BLE_Audio/CapCommander](<NUCODE_BLE_Audio/examples/CapCommander/CapCommander.ino>), [NUCODE_BLE_Audio/CapInitiator](<NUCODE_BLE_Audio/examples/CapInitiator/CapInitiator.ino>), [NUCODE_BLE_Audio/CapUnicastAcceptor](<NUCODE_BLE_Audio/examples/CapUnicastAcceptor/CapUnicastAcceptor.ino>), [NUCODE_BLE_Audio/CapUnicastInitiator](<NUCODE_BLE_Audio/examples/CapUnicastInitiator/CapUnicastInitiator.ino>), [NUCODE_BLE_Audio/CsipSetCoordinator](<NUCODE_BLE_Audio/examples/CsipSetCoordinator/CsipSetCoordinator.ino>), [NUCODE_BLE_Audio/CsipSetMember](<NUCODE_BLE_Audio/examples/CsipSetMember/CsipSetMember.ino>), [NUCODE_BLE_Audio/ExternalI2sSpeakerSink](<NUCODE_BLE_Audio/examples/ExternalI2sSpeakerSink/ExternalI2sSpeakerSink.ino>), [NUCODE_BLE_Audio/ExternalPdmMicrophoneSource](<NUCODE_BLE_Audio/examples/ExternalPdmMicrophoneSource/ExternalPdmMicrophoneSource.ino>), [NUCODE_BLE_Audio/GamingAudioBroadcaster](<NUCODE_BLE_Audio/examples/GamingAudioBroadcaster/GamingAudioBroadcaster.ino>), [NUCODE_BLE_Audio/GamingAudioGateway](<NUCODE_BLE_Audio/examples/GamingAudioGateway/GamingAudioGateway.ino>), [NUCODE_BLE_Audio/GamingAudioReceiver](<NUCODE_BLE_Audio/examples/GamingAudioReceiver/GamingAudioReceiver.ino>), [NUCODE_BLE_Audio/GamingAudioTerminal](<NUCODE_BLE_Audio/examples/GamingAudioTerminal/GamingAudioTerminal.ino>), [NUCODE_BLE_Audio/HearingAccessClient](<NUCODE_BLE_Audio/examples/HearingAccessClient/HearingAccessClient.ino>), [NUCODE_BLE_Audio/HearingAccessServer](<NUCODE_BLE_Audio/examples/HearingAccessServer/HearingAccessServer.ino>), [NUCODE_BLE_Audio/Lc3SyntheticLoopback](<NUCODE_BLE_Audio/examples/Lc3SyntheticLoopback/Lc3SyntheticLoopback.ino>), [NUCODE_BLE_Audio/MediaControlClient](<NUCODE_BLE_Audio/examples/MediaControlClient/MediaControlClient.ino>), [NUCODE_BLE_Audio/MediaControlPlayer](<NUCODE_BLE_Audio/examples/MediaControlPlayer/MediaControlPlayer.ino>), [NUCODE_BLE_Audio/PublicAudioBroadcastSink](<NUCODE_BLE_Audio/examples/PublicAudioBroadcastSink/PublicAudioBroadcastSink.ino>), [NUCODE_BLE_Audio/PublicAudioBroadcastSource](<NUCODE_BLE_Audio/examples/PublicAudioBroadcastSource/PublicAudioBroadcastSource.ino>), [NUCODE_BLE_Audio/TelephonyMediaBroadcaster](<NUCODE_BLE_Audio/examples/TelephonyMediaBroadcaster/TelephonyMediaBroadcaster.ino>), [NUCODE_BLE_Audio/TelephonyMediaGateway](<NUCODE_BLE_Audio/examples/TelephonyMediaGateway/TelephonyMediaGateway.ino>), [NUCODE_BLE_Audio/TelephonyMediaReceiver](<NUCODE_BLE_Audio/examples/TelephonyMediaReceiver/TelephonyMediaReceiver.ino>), [NUCODE_BLE_Audio/TelephonyMediaTerminal](<NUCODE_BLE_Audio/examples/TelephonyMediaTerminal/TelephonyMediaTerminal.ino>)

### `ble_beacons` (2개)

[NUCODE_BLE/BeaconAdvertiser](<NUCODE_BLE/examples/BeaconAdvertiser/BeaconAdvertiser.ino>), [NUCODE_BLE/BeaconObserver](<NUCODE_BLE/examples/BeaconObserver/BeaconObserver.ino>)

### `ble_channel_sounding` (2개)

[NUCODE_BLE_ChannelSounding/RasInitiator](<NUCODE_BLE_ChannelSounding/examples/RasInitiator/RasInitiator.ino>), [NUCODE_BLE_ChannelSounding/RasReflector](<NUCODE_BLE_ChannelSounding/examples/RasReflector/RasReflector.ino>)

### `ble_dfu` (1개)

[NUCODE_BLE_DFU/SecureDfuPeripheral](<NUCODE_BLE_DFU/examples/SecureDfuPeripheral/SecureDfuPeripheral.ino>)

### `ble_direction_finding` (2개)

[NUCODE_BLE_DirectionFinding/ConnectedCteResponder](<NUCODE_BLE_DirectionFinding/examples/ConnectedCteResponder/ConnectedCteResponder.ino>), [NUCODE_BLE_DirectionFinding/CteBeacon](<NUCODE_BLE_DirectionFinding/examples/CteBeacon/CteBeacon.ino>)

### `ble_gap_multilink` (11개)

[NUCODE_BLE/BleThroughputCentral](<NUCODE_BLE/examples/BleThroughputCentral/BleThroughputCentral.ino>), [NUCODE_BLE/BleThroughputPeripheral](<NUCODE_BLE/examples/BleThroughputPeripheral/BleThroughputPeripheral.ino>), [NUCODE_BLE/ExtendedLeFeaturePages](<NUCODE_BLE/examples/ExtendedLeFeaturePages/ExtendedLeFeaturePages.ino>), [NUCODE_BLE/FlushableAclData](<NUCODE_BLE/examples/FlushableAclData/FlushableAclData.ino>), [NUCODE_BLE/GAPCentral](<NUCODE_BLE/examples/GAPCentral/GAPCentral.ino>), [NUCODE_BLE/GAPPeripheral](<NUCODE_BLE/examples/GAPPeripheral/GAPPeripheral.ino>), [NUCODE_BLE/MixedRoleLinks](<NUCODE_BLE/examples/MixedRoleLinks/MixedRoleLinks.ino>), [NUCODE_BLE/MultipleBleIdentities](<NUCODE_BLE/examples/MultipleBleIdentities/MultipleBleIdentities.ino>), [NUCODE_BLE/PerLinkControl](<NUCODE_BLE/examples/PerLinkControl/PerLinkControl.ino>), [NUCODE_BLE/ScalableBleResources](<NUCODE_BLE/examples/ScalableBleResources/ScalableBleResources.ino>), [NUCODE_BLE/ScanWhileConnecting](<NUCODE_BLE/examples/ScanWhileConnecting/ScanWhileConnecting.ino>)

### `ble_gatt` (9개)

[NUCODE_BLE/CustomGattCentral](<NUCODE_BLE/examples/CustomGattCentral/CustomGattCentral.ino>), [NUCODE_BLE/CustomGattPeripheral](<NUCODE_BLE/examples/CustomGattPeripheral/CustomGattPeripheral.ino>), [NUCODE_BLE/GattAuthorization](<NUCODE_BLE/examples/GattAuthorization/GattAuthorization.ino>), [NUCODE_BLE/GattDescriptors](<NUCODE_BLE/examples/GattDescriptors/GattDescriptors.ino>), [NUCODE_BLE/LongGattCentral](<NUCODE_BLE/examples/LongGattCentral/LongGattCentral.ino>), [NUCODE_BLE/LongGattPeripheral](<NUCODE_BLE/examples/LongGattPeripheral/LongGattPeripheral.ino>), [NUCODE_BLE/MixedGattCocLinks](<NUCODE_BLE/examples/MixedGattCocLinks/MixedGattCocLinks.ino>), [NUCODE_BLE/ReliableWriteCentral](<NUCODE_BLE/examples/ReliableWriteCentral/ReliableWriteCentral.ino>), [NUCODE_BLE/ReliableWritePeripheral](<NUCODE_BLE/examples/ReliableWritePeripheral/ReliableWritePeripheral.ino>)

### `ble_gatt_extensions` (4개)

[NUCODE_BLE_EATT/EattCentral](<NUCODE_BLE_EATT/examples/EattCentral/EattCentral.ino>), [NUCODE_BLE_EATT/EattPeripheral](<NUCODE_BLE_EATT/examples/EattPeripheral/EattPeripheral.ino>), [NUCODE_BLE_LegacySigning/LegacySignedWriteCentral](<NUCODE_BLE_LegacySigning/examples/LegacySignedWriteCentral/LegacySignedWriteCentral.ino>), [NUCODE_BLE_LegacySigning/LegacySignedWritePeripheral](<NUCODE_BLE_LegacySigning/examples/LegacySignedWritePeripheral/LegacySignedWritePeripheral.ino>)

### `ble_iso` (11개)

[NUCODE_BLE_ISO/BISEncryptedReceiver](<NUCODE_BLE_ISO/examples/BISEncryptedReceiver/BISEncryptedReceiver.ino>), [NUCODE_BLE_ISO/BISEncryptedSource](<NUCODE_BLE_ISO/examples/BISEncryptedSource/BISEncryptedSource.ino>), [NUCODE_BLE_ISO/BISReceiver](<NUCODE_BLE_ISO/examples/BISReceiver/BISReceiver.ino>), [NUCODE_BLE_ISO/BISSource](<NUCODE_BLE_ISO/examples/BISSource/BISSource.ino>), [NUCODE_BLE_ISO/BISTimeReceiver](<NUCODE_BLE_ISO/examples/BISTimeReceiver/BISTimeReceiver.ino>), [NUCODE_BLE_ISO/BISTimeSource](<NUCODE_BLE_ISO/examples/BISTimeSource/BISTimeSource.ino>), [NUCODE_BLE_ISO/CISCentral](<NUCODE_BLE_ISO/examples/CISCentral/CISCentral.ino>), [NUCODE_BLE_ISO/CISPeripheral](<NUCODE_BLE_ISO/examples/CISPeripheral/CISPeripheral.ino>), [NUCODE_BLE_ISO/CISToBISBridge](<NUCODE_BLE_ISO/examples/CISToBISBridge/CISToBISBridge.ino>), [NUCODE_BLE_ISO/CISToBISPeer](<NUCODE_BLE_ISO/examples/CISToBISPeer/CISToBISPeer.ino>), [NUCODE_BLE_ISO/CISToBISReceiver](<NUCODE_BLE_ISO/examples/CISToBISReceiver/CISToBISReceiver.ino>)

### `ble_l2cap` (2개)

[NUCODE_BLE/L2capCocClient](<NUCODE_BLE/examples/L2capCocClient/L2capCocClient.ino>), [NUCODE_BLE/L2capCocServer](<NUCODE_BLE/examples/L2capCocServer/L2capCocServer.ino>)

### `ble_link_control` (21개)

[NUCODE_BLE/ConnectionRadioNotification](<NUCODE_BLE/examples/ConnectionRadioNotification/ConnectionRadioNotification.ino>), [NUCODE_BLE/ConnectionSubratingCentral](<NUCODE_BLE/examples/ConnectionSubratingCentral/ConnectionSubratingCentral.ino>), [NUCODE_BLE/ConnectionSubratingPeripheral](<NUCODE_BLE/examples/ConnectionSubratingPeripheral/ConnectionSubratingPeripheral.ino>), [NUCODE_BLE/ConnectionTimeSyncCentral](<NUCODE_BLE/examples/ConnectionTimeSyncCentral/ConnectionTimeSyncCentral.ino>), [NUCODE_BLE/ConnectionTimeSyncPeripheral](<NUCODE_BLE/examples/ConnectionTimeSyncPeripheral/ConnectionTimeSyncPeripheral.ino>), [NUCODE_BLE/FrameSpaceUpdateCentral](<NUCODE_BLE/examples/FrameSpaceUpdateCentral/FrameSpaceUpdateCentral.ino>), [NUCODE_BLE/FrameSpaceUpdatePeripheral](<NUCODE_BLE/examples/FrameSpaceUpdatePeripheral/FrameSpaceUpdatePeripheral.ino>), [NUCODE_BLE/LeChannelMapControl](<NUCODE_BLE/examples/LeChannelMapControl/LeChannelMapControl.ino>), [NUCODE_BLE/LePowerControlCentral](<NUCODE_BLE/examples/LePowerControlCentral/LePowerControlCentral.ino>), [NUCODE_BLE/LePowerControlPeripheral](<NUCODE_BLE/examples/LePowerControlPeripheral/LePowerControlPeripheral.ino>), [NUCODE_BLE/NordicChannelSurvey](<NUCODE_BLE/examples/NordicChannelSurvey/NordicChannelSurvey.ino>), [NUCODE_BLE/NordicConnectionEventQos](<NUCODE_BLE/examples/NordicConnectionEventQos/NordicConnectionEventQos.ino>), [NUCODE_BLE/NordicLlpmPair](<NUCODE_BLE/examples/NordicLlpmPair/NordicLlpmPair.ino>), [NUCODE_BLE/PathLossMonitorCentral](<NUCODE_BLE/examples/PathLossMonitorCentral/PathLossMonitorCentral.ino>), [NUCODE_BLE/PathLossMonitorPeripheral](<NUCODE_BLE/examples/PathLossMonitorPeripheral/PathLossMonitorPeripheral.ino>), [NUCODE_BLE/RadioEventTrigger](<NUCODE_BLE/examples/RadioEventTrigger/RadioEventTrigger.ino>), [NUCODE_BLE/RssiPowerControlCentral](<NUCODE_BLE/examples/RssiPowerControlCentral/RssiPowerControlCentral.ino>), [NUCODE_BLE/RssiPowerControlPeripheral](<NUCODE_BLE/examples/RssiPowerControlPeripheral/RssiPowerControlPeripheral.ino>), [NUCODE_BLE/ShorterConnectionIntervalsCentral](<NUCODE_BLE/examples/ShorterConnectionIntervalsCentral/ShorterConnectionIntervalsCentral.ino>), [NUCODE_BLE/ShorterConnectionIntervalsPeripheral](<NUCODE_BLE/examples/ShorterConnectionIntervalsPeripheral/ShorterConnectionIntervalsPeripheral.ino>), [NUCODE_BLE/SleepClockAccuracyUpdate](<NUCODE_BLE/examples/SleepClockAccuracyUpdate/SleepClockAccuracyUpdate.ino>)

### `ble_mesh_management` (13개)

[NUCODE_BLE_Mesh_Management/MeshLargeCompositionDataClient](<NUCODE_BLE_Mesh_Management/examples/MeshLargeCompositionDataClient/MeshLargeCompositionDataClient.ino>), [NUCODE_BLE_Mesh_Management/MeshLargeCompositionDataServer](<NUCODE_BLE_Mesh_Management/examples/MeshLargeCompositionDataServer/MeshLargeCompositionDataServer.ino>), [NUCODE_BLE_Mesh_Management/MeshOnDemandPrivateProxy](<NUCODE_BLE_Mesh_Management/examples/MeshOnDemandPrivateProxy/MeshOnDemandPrivateProxy.ino>), [NUCODE_BLE_Mesh_Management/MeshOpcodeAggregatorClient](<NUCODE_BLE_Mesh_Management/examples/MeshOpcodeAggregatorClient/MeshOpcodeAggregatorClient.ino>), [NUCODE_BLE_Mesh_Management/MeshOpcodeAggregatorServer](<NUCODE_BLE_Mesh_Management/examples/MeshOpcodeAggregatorServer/MeshOpcodeAggregatorServer.ino>), [NUCODE_BLE_Mesh_Management/MeshPrivateBeaconClient](<NUCODE_BLE_Mesh_Management/examples/MeshPrivateBeaconClient/MeshPrivateBeaconClient.ino>), [NUCODE_BLE_Mesh_Management/MeshPrivateBeaconServer](<NUCODE_BLE_Mesh_Management/examples/MeshPrivateBeaconServer/MeshPrivateBeaconServer.ino>), [NUCODE_BLE_Mesh_Management/MeshProxySolicitation](<NUCODE_BLE_Mesh_Management/examples/MeshProxySolicitation/MeshProxySolicitation.ino>), [NUCODE_BLE_Mesh_Management/MeshRemoteProvisioner](<NUCODE_BLE_Mesh_Management/examples/MeshRemoteProvisioner/MeshRemoteProvisioner.ino>), [NUCODE_BLE_Mesh_Management/MeshRemoteProvisioningServer](<NUCODE_BLE_Mesh_Management/examples/MeshRemoteProvisioningServer/MeshRemoteProvisioningServer.ino>), [NUCODE_BLE_Mesh_Management/MeshSarConfigurationClient](<NUCODE_BLE_Mesh_Management/examples/MeshSarConfigurationClient/MeshSarConfigurationClient.ino>), [NUCODE_BLE_Mesh_Management/MeshSarConfigurationServer](<NUCODE_BLE_Mesh_Management/examples/MeshSarConfigurationServer/MeshSarConfigurationServer.ino>), [NUCODE_BLE_Mesh_Management/MeshSubnetBridge](<NUCODE_BLE_Mesh_Management/examples/MeshSubnetBridge/MeshSubnetBridge.ino>)

### `ble_mesh_models` (12개)

[NUCODE_BLE_Mesh/MeshFriend](<NUCODE_BLE_Mesh/examples/MeshFriend/MeshFriend.ino>), [NUCODE_BLE_Mesh/MeshHealth](<NUCODE_BLE_Mesh/examples/MeshHealth/MeshHealth.ino>), [NUCODE_BLE_Mesh/MeshLevel](<NUCODE_BLE_Mesh/examples/MeshLevel/MeshLevel.ino>), [NUCODE_BLE_Mesh/MeshLight](<NUCODE_BLE_Mesh/examples/MeshLight/MeshLight.ino>), [NUCODE_BLE_Mesh/MeshLowPowerNode](<NUCODE_BLE_Mesh/examples/MeshLowPowerNode/MeshLowPowerNode.ino>), [NUCODE_BLE_Mesh/MeshNode](<NUCODE_BLE_Mesh/examples/MeshNode/MeshNode.ino>), [NUCODE_BLE_Mesh/MeshOnOff](<NUCODE_BLE_Mesh/examples/MeshOnOff/MeshOnOff.ino>), [NUCODE_BLE_Mesh/MeshProvisioner](<NUCODE_BLE_Mesh/examples/MeshProvisioner/MeshProvisioner.ino>), [NUCODE_BLE_Mesh/MeshProxy](<NUCODE_BLE_Mesh/examples/MeshProxy/MeshProxy.ino>), [NUCODE_BLE_Mesh/MeshRelay](<NUCODE_BLE_Mesh/examples/MeshRelay/MeshRelay.ino>), [NUCODE_BLE_Mesh/MeshSensor](<NUCODE_BLE_Mesh/examples/MeshSensor/MeshSensor.ino>), [NUCODE_BLE_Mesh/MeshTimeSceneScheduler](<NUCODE_BLE_Mesh/examples/MeshTimeSceneScheduler/MeshTimeSceneScheduler.ino>)

### `ble_mesh_update` (4개)

[NUCODE_BLE_Mesh_Update/MeshBlobClient](<NUCODE_BLE_Mesh_Update/examples/MeshBlobClient/MeshBlobClient.ino>), [NUCODE_BLE_Mesh_Update/MeshBlobServer](<NUCODE_BLE_Mesh_Update/examples/MeshBlobServer/MeshBlobServer.ino>), [NUCODE_BLE_Mesh_Update/MeshDfuTarget](<NUCODE_BLE_Mesh_Update/examples/MeshDfuTarget/MeshDfuTarget.ino>), [NUCODE_BLE_Mesh_Update/MeshFirmwareDistributor](<NUCODE_BLE_Mesh_Update/examples/MeshFirmwareDistributor/MeshFirmwareDistributor.ino>)

### `ble_profiles_and_ecosystems` (16개)

[NUCODE_BLE_Companion/AppleMediaClient](<NUCODE_BLE_Companion/examples/AppleMediaClient/AppleMediaClient.ino>), [NUCODE_BLE_Companion/AppleNotificationClient](<NUCODE_BLE_Companion/examples/AppleNotificationClient/AppleNotificationClient.ino>), [NUCODE_BLE_Profiles/AlertSensor](<NUCODE_BLE_Profiles/examples/AlertSensor/AlertSensor.ino>), [NUCODE_BLE_Profiles/BondManagement](<NUCODE_BLE_Profiles/examples/BondManagement/BondManagement.ino>), [NUCODE_BLE_Profiles/GlucoseSensor](<NUCODE_BLE_Profiles/examples/GlucoseSensor/GlucoseSensor.ino>), [NUCODE_BLE_Profiles/ObjectClient](<NUCODE_BLE_Profiles/examples/ObjectClient/ObjectClient.ino>), [NUCODE_BLE_Profiles/ObjectServer](<NUCODE_BLE_Profiles/examples/ObjectServer/ObjectServer.ino>), [NUCODE_BLE_Profiles/StandardCollector](<NUCODE_BLE_Profiles/examples/StandardCollector/StandardCollector.ino>), [NUCODE_BLE_Profiles/StandardSensor](<NUCODE_BLE_Profiles/examples/StandardSensor/StandardSensor.ino>), [NUCODE_BLE_Security/EnvironmentalSensing](<NUCODE_BLE_Security/examples/EnvironmentalSensing/EnvironmentalSensing.ino>), [NUCODE_BLE_Security/GattCacheCentral](<NUCODE_BLE_Security/examples/GattCacheCentral/GattCacheCentral.ino>), [NUCODE_BLE_Security/GattCachePeripheral](<NUCODE_BLE_Security/examples/GattCachePeripheral/GattCachePeripheral.ino>), [NUCODE_BLE_Security/HeartRate](<NUCODE_BLE_Security/examples/HeartRate/HeartRate.ino>), [NUCODE_BLE_Security/SecureConsumerControl](<NUCODE_BLE_Security/examples/SecureConsumerControl/SecureConsumerControl.ino>), [NUCODE_BLE_Security/SecureKeyboard](<NUCODE_BLE_Security/examples/SecureKeyboard/SecureKeyboard.ino>), [NUCODE_BLE_Security/SecureMouse](<NUCODE_BLE_Security/examples/SecureMouse/SecureMouse.ino>)

### `ble_uart` (2개)

[NUCODE_BLE/NUSCentral](<NUCODE_BLE/examples/NUSCentral/NUSCentral.ino>), [NUCODE_BLE/NUSPeripheral](<NUCODE_BLE/examples/NUSPeripheral/NUSPeripheral.ino>)

### `board_system_power` (4개)

[NUCODE_NU54DK/BoardInfo](<NUCODE_NU54DK/examples/BoardInfo/BoardInfo.ino>), [NUCODE_NU54DK/CounterAlarm](<NUCODE_NU54DK/examples/CounterAlarm/CounterAlarm.ino>), [NUCODE_NU54DK/SystemOffWake](<NUCODE_NU54DK/examples/SystemOffWake/SystemOffWake.ino>), [NUCODE_NU54DK/WatchdogBasic](<NUCODE_NU54DK/examples/WatchdogBasic/WatchdogBasic.ino>)

### `gpio_interrupt` (2개)

[NUCODE_NU54DK/Blink](<NUCODE_NU54DK/examples/Blink/Blink.ino>), [NUCODE_NU54DK/InterruptButton](<NUCODE_NU54DK/examples/InterruptButton/InterruptButton.ino>)

### `i2c_wire` (2개)

[NUCODE_NU54DK/WireRuntimePins](<NUCODE_NU54DK/examples/WireRuntimePins/WireRuntimePins.ino>), [Wire/WirePmicId](<Wire/examples/WirePmicId/WirePmicId.ino>)

### `peripheral_fabric` (7개)

[NUCODE_Peripheral_Fabric/AdcContinuousDma](<NUCODE_Peripheral_Fabric/examples/AdcContinuousDma/AdcContinuousDma.ino>), [NUCODE_Peripheral_Fabric/FabricCapabilities](<NUCODE_Peripheral_Fabric/examples/FabricCapabilities/FabricCapabilities.ino>), [NUCODE_Peripheral_Fabric/PwmSequencePlayback](<NUCODE_Peripheral_Fabric/examples/PwmSequencePlayback/PwmSequencePlayback.ino>), [NUCODE_Peripheral_Fabric/ResourceConflictDemo](<NUCODE_Peripheral_Fabric/examples/ResourceConflictDemo/ResourceConflictDemo.ino>), [NUCODE_Peripheral_Fabric/SpiAsyncLoopback](<NUCODE_Peripheral_Fabric/examples/SpiAsyncLoopback/SpiAsyncLoopback.ino>), [NUCODE_Peripheral_Fabric/TwisTargetDoubleBuffer](<NUCODE_Peripheral_Fabric/examples/TwisTargetDoubleBuffer/TwisTargetDoubleBuffer.ino>), [NUCODE_Peripheral_Fabric/UarteAsyncEcho](<NUCODE_Peripheral_Fabric/examples/UarteAsyncEcho/UarteAsyncEcho.ino>)

### `radio_802154` (2개)

[NUCODE_Radio_IEEE802154/Radio154Receiver](<NUCODE_Radio_IEEE802154/examples/Radio154Receiver/Radio154Receiver.ino>), [NUCODE_Radio_IEEE802154/Radio154Transmitter](<NUCODE_Radio_IEEE802154/examples/Radio154Transmitter/Radio154Transmitter.ino>)

### `radio_coexistence` (4개)

[NUCODE_Radio_Coexistence/Ble154Coexistence](<NUCODE_Radio_Coexistence/examples/Ble154Coexistence/Ble154Coexistence.ino>), [NUCODE_Radio_Coexistence/BleEsbCoexistence](<NUCODE_Radio_Coexistence/examples/BleEsbCoexistence/BleEsbCoexistence.ino>), [NUCODE_Radio_Coexistence/BleMeshCoexistence](<NUCODE_Radio_Coexistence/examples/BleMeshCoexistence/BleMeshCoexistence.ino>), [NUCODE_Radio_Coexistence/RadioCoexistenceOneWire](<NUCODE_Radio_Coexistence/examples/RadioCoexistenceOneWire/RadioCoexistenceOneWire.ino>)

### `radio_esb` (2개)

[NUCODE_Radio_ESB/EsbPrx](<NUCODE_Radio_ESB/examples/EsbPrx/EsbPrx.ino>), [NUCODE_Radio_ESB/EsbPtx](<NUCODE_Radio_ESB/examples/EsbPtx/EsbPtx.ino>)

### `serial` (2개)

[NUCODE_NU54DK/Serial1RuntimePins](<NUCODE_NU54DK/examples/Serial1RuntimePins/Serial1RuntimePins.ino>), [NUCODE_NU54DK/SerialEcho](<NUCODE_NU54DK/examples/SerialEcho/SerialEcho.ino>)

### `servo_motion` (1개)

[Servo/Sweep](<Servo/examples/Sweep/Sweep.ino>)

### `spi` (2개)

[NUCODE_NU54DK/SPI00RuntimePins](<NUCODE_NU54DK/examples/SPI00RuntimePins/SPI00RuntimePins.ino>), [SPI/SPITransaction](<SPI/examples/SPITransaction/SPITransaction.ino>)

### `storage` (3개)

[EEPROM/EEPROMPersistence](<EEPROM/examples/EEPROMPersistence/EEPROMPersistence.ino>), [LittleFS/LittleFSPersistence](<LittleFS/examples/LittleFSPersistence/LittleFSPersistence.ino>), [NUCODE_NU54DK/SettingsStorage](<NUCODE_NU54DK/examples/SettingsStorage/SettingsStorage.ino>)

## Reference — 전체 204개

| 예제 | Recipe | 권장 profile | 보드/역할 | runtime 판정 |
| --- | --- | --- | --- | --- |
| [EEPROM/EEPROMPersistence](<EEPROM/examples/EEPROMPersistence/EEPROMPersistence.ino>) | `storage` | `standard` | 1대 — EEPROMPersistence 실행 보드 | `procedure_documented_not_physical_pass` |
| [LittleFS/LittleFSPersistence](<LittleFS/examples/LittleFSPersistence/LittleFSPersistence.ino>) | `storage` | `standard` | 1대 — LittleFSPersistence 실행 보드 | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE/AdvertisingAcceptList](<NUCODE_BLE/examples/AdvertisingAcceptList/AdvertisingAcceptList.ino>) | `ble_advertising_scanning` | `ble` | 2대 — AdvertisingAcceptList (peripheral); 허용 주소로 설정한 central | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE/AdvertisingCodingSelection](<NUCODE_BLE/examples/AdvertisingCodingSelection/AdvertisingCodingSelection.ino>) | `ble_advertising_scanning` | `ble` | 2대 — AdvertisingCodingSelection (advertiser); ExtendedScanner (coded scanner) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE/BeaconAdvertiser](<NUCODE_BLE/examples/BeaconAdvertiser/BeaconAdvertiser.ino>) | `ble_beacons` | `ble` | 2대 — BeaconAdvertiser (broadcaster); BeaconObserver (passive scanner) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE/BeaconObserver](<NUCODE_BLE/examples/BeaconObserver/BeaconObserver.ino>) | `ble_beacons` | `ble` | 2대 — BeaconAdvertiser (broadcaster); BeaconObserver (passive scanner) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE/BleThroughputCentral](<NUCODE_BLE/examples/BleThroughputCentral/BleThroughputCentral.ino>) | `ble_gap_multilink` | `ble` | 2대 — BleThroughputCentral (central/sender); BleThroughputPeripheral (peripheral/receiver) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE/BleThroughputPeripheral](<NUCODE_BLE/examples/BleThroughputPeripheral/BleThroughputPeripheral.ino>) | `ble_gap_multilink` | `ble` | 2대 — BleThroughputCentral (central/sender); BleThroughputPeripheral (peripheral/receiver) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE/ConnectionRadioNotification](<NUCODE_BLE/examples/ConnectionRadioNotification/ConnectionRadioNotification.ino>) | `ble_link_control` | `ble` | 2대 — ConnectionRadioNotification (peripheral); 연결 가능한 BLE central | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE/ConnectionSubratingCentral](<NUCODE_BLE/examples/ConnectionSubratingCentral/ConnectionSubratingCentral.ino>) | `ble_link_control` | `ble` | 2대 — ConnectionSubratingCentral (central/requester); ConnectionSubratingPeripheral (peripheral/responder) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE/ConnectionSubratingPeripheral](<NUCODE_BLE/examples/ConnectionSubratingPeripheral/ConnectionSubratingPeripheral.ino>) | `ble_link_control` | `ble` | 2대 — ConnectionSubratingCentral (central/requester); ConnectionSubratingPeripheral (peripheral/responder) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE/ConnectionTimeSyncCentral](<NUCODE_BLE/examples/ConnectionTimeSyncCentral/ConnectionTimeSyncCentral.ino>) | `ble_link_control` | `ble` | 2대 — ConnectionTimeSyncCentral (central); ConnectionTimeSyncPeripheral (peripheral) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE/ConnectionTimeSyncPeripheral](<NUCODE_BLE/examples/ConnectionTimeSyncPeripheral/ConnectionTimeSyncPeripheral.ino>) | `ble_link_control` | `ble` | 2대 — ConnectionTimeSyncCentral (central); ConnectionTimeSyncPeripheral (peripheral) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE/CustomGattCentral](<NUCODE_BLE/examples/CustomGattCentral/CustomGattCentral.ino>) | `ble_gatt` | `ble` | 2대 — CustomGattCentral (central/client); CustomGattPeripheral (peripheral/server) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE/CustomGattPeripheral](<NUCODE_BLE/examples/CustomGattPeripheral/CustomGattPeripheral.ino>) | `ble_gatt` | `ble` | 2대 — CustomGattCentral (central/client); CustomGattPeripheral (peripheral/server) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE/DirectedAdvertisingCentral](<NUCODE_BLE/examples/DirectedAdvertisingCentral/DirectedAdvertisingCentral.ino>) | `ble_advertising_scanning` | `ble` | 2대 — DirectedAdvertisingPeripheral (peripheral); DirectedAdvertisingCentral (central) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE/DirectedAdvertisingPeripheral](<NUCODE_BLE/examples/DirectedAdvertisingPeripheral/DirectedAdvertisingPeripheral.ino>) | `ble_advertising_scanning` | `ble` | 2대 — DirectedAdvertisingPeripheral (peripheral); DirectedAdvertisingCentral (central) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE/EncryptedAdvertisingCentral](<NUCODE_BLE/examples/EncryptedAdvertisingCentral/EncryptedAdvertisingCentral.ino>) | `ble_advertising_scanning` | `ble` | 2대 — EncryptedAdvertisingPeripheral (advertiser); EncryptedAdvertisingCentral (scanner) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE/EncryptedAdvertisingPeripheral](<NUCODE_BLE/examples/EncryptedAdvertisingPeripheral/EncryptedAdvertisingPeripheral.ino>) | `ble_advertising_scanning` | `ble` | 2대 — EncryptedAdvertisingPeripheral (advertiser); EncryptedAdvertisingCentral (scanner) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE/ExtendedAdvertising](<NUCODE_BLE/examples/ExtendedAdvertising/ExtendedAdvertising.ino>) | `ble_advertising_scanning` | `ble` | 2대 — ExtendedAdvertising 실행 보드; ExtendedScanner (scanner) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE/ExtendedLeFeaturePages](<NUCODE_BLE/examples/ExtendedLeFeaturePages/ExtendedLeFeaturePages.ino>) | `ble_gap_multilink` | `ble` | 1대 — ExtendedLeFeaturePages (local controller query) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE/ExtendedScanner](<NUCODE_BLE/examples/ExtendedScanner/ExtendedScanner.ino>) | `ble_advertising_scanning` | `ble` | 2대 — ExtendedAdvertising 실행 보드; ExtendedScanner (scanner) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE/FlushableAclData](<NUCODE_BLE/examples/FlushableAclData/FlushableAclData.ino>) | `ble_gap_multilink` | `ble` | 1대 — FlushableAclData 적용성 확인 보드 | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE/FrameSpaceUpdateCentral](<NUCODE_BLE/examples/FrameSpaceUpdateCentral/FrameSpaceUpdateCentral.ino>) | `ble_link_control` | `ble` | 2대 — FrameSpaceUpdateCentral (central/requester); FrameSpaceUpdatePeripheral (peripheral/responder) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE/FrameSpaceUpdatePeripheral](<NUCODE_BLE/examples/FrameSpaceUpdatePeripheral/FrameSpaceUpdatePeripheral.ino>) | `ble_link_control` | `ble` | 2대 — FrameSpaceUpdateCentral (central/requester); FrameSpaceUpdatePeripheral (peripheral/responder) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE/GAPCentral](<NUCODE_BLE/examples/GAPCentral/GAPCentral.ino>) | `ble_gap_multilink` | `ble` | 2대 — GAPCentral (central/client); GAPPeripheral (peripheral/server) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE/GAPPeripheral](<NUCODE_BLE/examples/GAPPeripheral/GAPPeripheral.ino>) | `ble_gap_multilink` | `ble` | 2대 — GAPCentral (central/client); GAPPeripheral (peripheral/server) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE/GattAuthorization](<NUCODE_BLE/examples/GattAuthorization/GattAuthorization.ino>) | `ble_gatt` | `ble` | 2대 — GattAuthorization 실행 보드; GattDescriptors 실행 보드 | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE/GattDescriptors](<NUCODE_BLE/examples/GattDescriptors/GattDescriptors.ino>) | `ble_gatt` | `ble` | 2대 — GattAuthorization 실행 보드; GattDescriptors 실행 보드 | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE/L2capCocClient](<NUCODE_BLE/examples/L2capCocClient/L2capCocClient.ino>) | `ble_l2cap` | `ble` | 2대 — L2capCocClient (client/controller); L2capCocServer (server/device) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE/L2capCocServer](<NUCODE_BLE/examples/L2capCocServer/L2capCocServer.ino>) | `ble_l2cap` | `ble` | 2대 — L2capCocClient (client/controller); L2capCocServer (server/device) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE/LeChannelMapControl](<NUCODE_BLE/examples/LeChannelMapControl/LeChannelMapControl.ino>) | `ble_link_control` | `ble` | 1대 — LeChannelMapControl (Host classifier) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE/LePowerControlCentral](<NUCODE_BLE/examples/LePowerControlCentral/LePowerControlCentral.ino>) | `ble_link_control` | `ble` | 2대 — LePowerControlCentral (central/controller); LePowerControlPeripheral (peripheral/device) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE/LePowerControlPeripheral](<NUCODE_BLE/examples/LePowerControlPeripheral/LePowerControlPeripheral.ino>) | `ble_link_control` | `ble` | 2대 — LePowerControlCentral (central/controller); LePowerControlPeripheral (peripheral/device) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE/LongGattCentral](<NUCODE_BLE/examples/LongGattCentral/LongGattCentral.ino>) | `ble_gatt` | `ble` | 2대 — LongGattCentral (central/client); LongGattPeripheral (peripheral/server) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE/LongGattPeripheral](<NUCODE_BLE/examples/LongGattPeripheral/LongGattPeripheral.ino>) | `ble_gatt` | `ble` | 2대 — LongGattCentral (central/client); LongGattPeripheral (peripheral/server) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE/MixedGattCocLinks](<NUCODE_BLE/examples/MixedGattCocLinks/MixedGattCocLinks.ino>) | `ble_gatt` | `ble` | 1대 — MixedGattCocLinks 실행 보드 | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE/MixedRoleLinks](<NUCODE_BLE/examples/MixedRoleLinks/MixedRoleLinks.ino>) | `ble_gap_multilink` | `ble` | 1대 — MixedRoleLinks 실행 보드 | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE/MultipleAdvertisingSets](<NUCODE_BLE/examples/MultipleAdvertisingSets/MultipleAdvertisingSets.ino>) | `ble_advertising_scanning` | `ble` | 2대 — MultipleAdvertisingSets (advertiser); ExtendedScanner (scanner) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE/MultipleBleIdentities](<NUCODE_BLE/examples/MultipleBleIdentities/MultipleBleIdentities.ino>) | `ble_gap_multilink` | `ble` | 2대 — MultipleBleIdentities (advertiser); ExtendedScanner (scanner) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE/MultiplePeriodicSyncs](<NUCODE_BLE/examples/MultiplePeriodicSyncs/MultiplePeriodicSyncs.ino>) | `ble_advertising_scanning` | `ble` | 3대 — PeriodicAdvertiser 첫 번째 송신기; PeriodicAdvertiser 두 번째 송신기; MultiplePeriodicSyncs (scanner) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE/NordicChannelSurvey](<NUCODE_BLE/examples/NordicChannelSurvey/NordicChannelSurvey.ino>) | `ble_link_control` | `ble` | 1대 — NordicChannelSurvey 실행 보드 | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE/NordicConnectionEventQos](<NUCODE_BLE/examples/NordicConnectionEventQos/NordicConnectionEventQos.ino>) | `ble_link_control` | `ble` | 2대 — NordicConnectionEventQos 실행 보드; 연결 가능한 BLE peer | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE/NordicLlpmPair](<NUCODE_BLE/examples/NordicLlpmPair/NordicLlpmPair.ino>) | `ble_link_control` | `ble` | 2대 — NordicLlpmPair (central); NordicLlpmPair (peripheral) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE/NUSCentral](<NUCODE_BLE/examples/NUSCentral/NUSCentral.ino>) | `ble_uart` | `ble` | 2대 — NUSCentral (central/client); NUSPeripheral (peripheral/server) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE/NUSPeripheral](<NUCODE_BLE/examples/NUSPeripheral/NUSPeripheral.ino>) | `ble_uart` | `ble` | 2대 — NUSCentral (central/client); NUSPeripheral (peripheral/server) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE/PastReceiver](<NUCODE_BLE/examples/PastReceiver/PastReceiver.ino>) | `ble_advertising_scanning` | `ble` | 2대 — PastSender (sender); PastReceiver (receiver) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE/PastSender](<NUCODE_BLE/examples/PastSender/PastSender.ino>) | `ble_advertising_scanning` | `ble` | 2대 — PastSender (sender); PastReceiver (receiver) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE/PathLossMonitorCentral](<NUCODE_BLE/examples/PathLossMonitorCentral/PathLossMonitorCentral.ino>) | `ble_link_control` | `ble` | 2대 — PathLossMonitorCentral (central/monitor); PathLossMonitorPeripheral (peripheral/monitor) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE/PathLossMonitorPeripheral](<NUCODE_BLE/examples/PathLossMonitorPeripheral/PathLossMonitorPeripheral.ino>) | `ble_link_control` | `ble` | 2대 — PathLossMonitorCentral (central/monitor); PathLossMonitorPeripheral (peripheral/monitor) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE/PawrAdvertiser](<NUCODE_BLE/examples/PawrAdvertiser/PawrAdvertiser.ino>) | `ble_advertising_scanning` | `ble` | 2대 — PawrAdvertiser (advertiser); PawrScanner (scanner) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE/PawrScanner](<NUCODE_BLE/examples/PawrScanner/PawrScanner.ino>) | `ble_advertising_scanning` | `ble` | 2대 — PawrAdvertiser (advertiser); PawrScanner (scanner) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE/PeriodicAdvertiser](<NUCODE_BLE/examples/PeriodicAdvertiser/PeriodicAdvertiser.ino>) | `ble_advertising_scanning` | `ble` | 2대 — PeriodicAdvertiser (advertiser); PeriodicScanner (scanner) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE/PeriodicAdvertiserList](<NUCODE_BLE/examples/PeriodicAdvertiserList/PeriodicAdvertiserList.ino>) | `ble_advertising_scanning` | `ble` | 3대 — PeriodicAdvertiser 첫 번째 송신기; PeriodicAdvertiser 두 번째 송신기; PeriodicAdvertiserList 실행 보드 | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE/PeriodicScanner](<NUCODE_BLE/examples/PeriodicScanner/PeriodicScanner.ino>) | `ble_advertising_scanning` | `ble` | 2대 — PeriodicAdvertiser (advertiser); PeriodicScanner (scanner) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE/PerLinkControl](<NUCODE_BLE/examples/PerLinkControl/PerLinkControl.ino>) | `ble_gap_multilink` | `ble` | 1대 — PerLinkControl 실행 보드 | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE/PrivacyPeripheral](<NUCODE_BLE/examples/PrivacyPeripheral/PrivacyPeripheral.ino>) | `ble_advertising_scanning` | `ble` | 1대 — PrivacyPeripheral (peripheral/server) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE/RadioEventTrigger](<NUCODE_BLE/examples/RadioEventTrigger/RadioEventTrigger.ino>) | `ble_link_control` | `ble` | 1대 — RadioEventTrigger scanner | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE/ReliableWriteCentral](<NUCODE_BLE/examples/ReliableWriteCentral/ReliableWriteCentral.ino>) | `ble_gatt` | `ble` | 2대 — ReliableWriteCentral (central/client); ReliableWritePeripheral (peripheral/server) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE/ReliableWritePeripheral](<NUCODE_BLE/examples/ReliableWritePeripheral/ReliableWritePeripheral.ino>) | `ble_gatt` | `ble` | 2대 — ReliableWriteCentral (central/client); ReliableWritePeripheral (peripheral/server) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE/RssiPowerControlCentral](<NUCODE_BLE/examples/RssiPowerControlCentral/RssiPowerControlCentral.ino>) | `ble_link_control` | `ble` | 2대 — RssiPowerControlCentral (central/controller); RssiPowerControlPeripheral (peripheral/device) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE/RssiPowerControlPeripheral](<NUCODE_BLE/examples/RssiPowerControlPeripheral/RssiPowerControlPeripheral.ino>) | `ble_link_control` | `ble` | 2대 — RssiPowerControlCentral (central/controller); RssiPowerControlPeripheral (peripheral/device) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE/ScalableBleResources](<NUCODE_BLE/examples/ScalableBleResources/ScalableBleResources.ino>) | `ble_gap_multilink` | `ble` | 1대 — ScalableBleResources 실행 보드 | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE/ScanWhileConnecting](<NUCODE_BLE/examples/ScanWhileConnecting/ScanWhileConnecting.ino>) | `ble_gap_multilink` | `ble` | 2대 — connectable peripheral; ScanWhileConnecting (central/scanner) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE/ShorterConnectionIntervalsCentral](<NUCODE_BLE/examples/ShorterConnectionIntervalsCentral/ShorterConnectionIntervalsCentral.ino>) | `ble_link_control` | `ble` | 2대 — ShorterConnectionIntervalsCentral (central/requester); ShorterConnectionIntervalsPeripheral (peripheral/responder) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE/ShorterConnectionIntervalsPeripheral](<NUCODE_BLE/examples/ShorterConnectionIntervalsPeripheral/ShorterConnectionIntervalsPeripheral.ino>) | `ble_link_control` | `ble` | 2대 — ShorterConnectionIntervalsCentral (central/requester); ShorterConnectionIntervalsPeripheral (peripheral/responder) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE/SleepClockAccuracyUpdate](<NUCODE_BLE/examples/SleepClockAccuracyUpdate/SleepClockAccuracyUpdate.ino>) | `ble_link_control` | `ble` | 1대 — SleepClockAccuracyUpdate (support reporter) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Audio/AudioControlController](<NUCODE_BLE_Audio/examples/AudioControlController/AudioControlController.ino>) | `ble_audio` | `ble` | 2대 — AudioControlController (controller); AudioControlDevice (device) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Audio/AudioControlDevice](<NUCODE_BLE_Audio/examples/AudioControlDevice/AudioControlDevice.ino>) | `ble_audio` | `ble` | 2대 — AudioControlController (controller); AudioControlDevice (device) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Audio/BapBroadcastAssistant](<NUCODE_BLE_Audio/examples/BapBroadcastAssistant/BapBroadcastAssistant.ino>) | `ble_audio` | `ble` | 3대 — BapBroadcastSource (source/transmitter); BapBroadcastAssistant 실행 보드; BapBroadcastDelegatorSink (sink/receiver) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Audio/BapBroadcastDelegatorSink](<NUCODE_BLE_Audio/examples/BapBroadcastDelegatorSink/BapBroadcastDelegatorSink.ino>) | `ble_audio` | `ble` | 3대 — BapBroadcastSource (source/transmitter); BapBroadcastAssistant 실행 보드; BapBroadcastDelegatorSink (sink/receiver) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Audio/BapBroadcastSink](<NUCODE_BLE_Audio/examples/BapBroadcastSink/BapBroadcastSink.ino>) | `ble_audio` | `ble` | 2대 — BapBroadcastSource (source/transmitter); BapBroadcastSink (sink/receiver) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Audio/BapBroadcastSource](<NUCODE_BLE_Audio/examples/BapBroadcastSource/BapBroadcastSource.ino>) | `ble_audio` | `ble` | 3대 — BapBroadcastSource (source/transmitter); BapBroadcastAssistant 실행 보드; BapBroadcastDelegatorSink (sink/receiver) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Audio/BapUnicastCycle](<NUCODE_BLE_Audio/examples/BapUnicastCycle/BapUnicastCycle.ino>) | `ble_audio` | `ble` | 2대 — BapUnicastCycle 실행 보드; BapUnicastSink (sink/receiver) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Audio/BapUnicastDuplexClient](<NUCODE_BLE_Audio/examples/BapUnicastDuplexClient/BapUnicastDuplexClient.ino>) | `ble_audio` | `ble` | 2대 — BapUnicastDuplexClient (client/controller); BapUnicastDuplexServer (server/device) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Audio/BapUnicastDuplexServer](<NUCODE_BLE_Audio/examples/BapUnicastDuplexServer/BapUnicastDuplexServer.ino>) | `ble_audio` | `ble` | 2대 — BapUnicastDuplexClient (client/controller); BapUnicastDuplexServer (server/device) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Audio/BapUnicastSink](<NUCODE_BLE_Audio/examples/BapUnicastSink/BapUnicastSink.ino>) | `ble_audio` | `ble` | 2대 — BapUnicastSource (source/transmitter); BapUnicastSink (sink/receiver) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Audio/BapUnicastSource](<NUCODE_BLE_Audio/examples/BapUnicastSource/BapUnicastSource.ino>) | `ble_audio` | `ble` | 2대 — BapUnicastSource (source/transmitter); BapUnicastSink (sink/receiver) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Audio/CallControlClient](<NUCODE_BLE_Audio/examples/CallControlClient/CallControlClient.ino>) | `ble_audio` | `ble` | 2대 — CallControlClient (client/controller); CallControlServer (server/device) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Audio/CallControlServer](<NUCODE_BLE_Audio/examples/CallControlServer/CallControlServer.ino>) | `ble_audio` | `ble` | 2대 — CallControlClient (client/controller); CallControlServer (server/device) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Audio/CapAcceptor](<NUCODE_BLE_Audio/examples/CapAcceptor/CapAcceptor.ino>) | `ble_audio` | `ble` | 2대 — CapCommander (commander); CapAcceptor (acceptor) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Audio/CapCommander](<NUCODE_BLE_Audio/examples/CapCommander/CapCommander.ino>) | `ble_audio` | `ble` | 2대 — CapCommander (commander); CapAcceptor (acceptor) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Audio/CapInitiator](<NUCODE_BLE_Audio/examples/CapInitiator/CapInitiator.ino>) | `ble_audio` | `ble` | 2대 — CapInitiator (initiator); CapAcceptor (acceptor) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Audio/CapUnicastAcceptor](<NUCODE_BLE_Audio/examples/CapUnicastAcceptor/CapUnicastAcceptor.ino>) | `ble_audio` | `ble` | 2대 — CapUnicastInitiator (initiator); CapUnicastAcceptor (acceptor) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Audio/CapUnicastInitiator](<NUCODE_BLE_Audio/examples/CapUnicastInitiator/CapUnicastInitiator.ino>) | `ble_audio` | `ble` | 2대 — CapUnicastInitiator (initiator); CapUnicastAcceptor (acceptor) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Audio/CsipSetCoordinator](<NUCODE_BLE_Audio/examples/CsipSetCoordinator/CsipSetCoordinator.ino>) | `ble_audio` | `ble` | 2대 — CsipSetCoordinator (coordinator); CsipSetMember (set member) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Audio/CsipSetMember](<NUCODE_BLE_Audio/examples/CsipSetMember/CsipSetMember.ino>) | `ble_audio` | `ble` | 2대 — CsipSetCoordinator (coordinator); CsipSetMember (set member) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Audio/ExternalI2sSpeakerSink](<NUCODE_BLE_Audio/examples/ExternalI2sSpeakerSink/ExternalI2sSpeakerSink.ino>) | `ble_audio` | `ble_audio_io` | 2대 — ExternalPdmMicrophoneSource (source/transmitter); ExternalI2sSpeakerSink (sink/receiver) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Audio/ExternalPdmMicrophoneSource](<NUCODE_BLE_Audio/examples/ExternalPdmMicrophoneSource/ExternalPdmMicrophoneSource.ino>) | `ble_audio` | `ble_audio_io` | 2대 — ExternalPdmMicrophoneSource (source/transmitter); ExternalI2sSpeakerSink (sink/receiver) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Audio/GamingAudioBroadcaster](<NUCODE_BLE_Audio/examples/GamingAudioBroadcaster/GamingAudioBroadcaster.ino>) | `ble_audio` | `ble` | 2대 — GamingAudioBroadcaster (broadcaster); GamingAudioReceiver (receiver) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Audio/GamingAudioGateway](<NUCODE_BLE_Audio/examples/GamingAudioGateway/GamingAudioGateway.ino>) | `ble_audio` | `ble` | 2대 — GamingAudioGateway (gateway); GamingAudioTerminal (terminal) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Audio/GamingAudioReceiver](<NUCODE_BLE_Audio/examples/GamingAudioReceiver/GamingAudioReceiver.ino>) | `ble_audio` | `ble` | 2대 — GamingAudioBroadcaster (broadcaster); GamingAudioReceiver (receiver) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Audio/GamingAudioTerminal](<NUCODE_BLE_Audio/examples/GamingAudioTerminal/GamingAudioTerminal.ino>) | `ble_audio` | `ble` | 2대 — GamingAudioGateway (gateway); GamingAudioTerminal (terminal) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Audio/HearingAccessClient](<NUCODE_BLE_Audio/examples/HearingAccessClient/HearingAccessClient.ino>) | `ble_audio` | `ble` | 2대 — HearingAccessClient (client/controller); HearingAccessServer (server/device) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Audio/HearingAccessServer](<NUCODE_BLE_Audio/examples/HearingAccessServer/HearingAccessServer.ino>) | `ble_audio` | `ble` | 2대 — HearingAccessClient (client/controller); HearingAccessServer (server/device) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Audio/Lc3SyntheticLoopback](<NUCODE_BLE_Audio/examples/Lc3SyntheticLoopback/Lc3SyntheticLoopback.ino>) | `ble_audio` | `ble` | 1대 — Lc3SyntheticLoopback 실행 보드 | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Audio/MediaControlClient](<NUCODE_BLE_Audio/examples/MediaControlClient/MediaControlClient.ino>) | `ble_audio` | `ble` | 2대 — MediaControlClient (client/controller); MediaControlPlayer (player/server) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Audio/MediaControlPlayer](<NUCODE_BLE_Audio/examples/MediaControlPlayer/MediaControlPlayer.ino>) | `ble_audio` | `ble` | 2대 — MediaControlClient (client/controller); MediaControlPlayer (player/server) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Audio/PublicAudioBroadcastSink](<NUCODE_BLE_Audio/examples/PublicAudioBroadcastSink/PublicAudioBroadcastSink.ino>) | `ble_audio` | `ble` | 2대 — PublicAudioBroadcastSource (source/transmitter); PublicAudioBroadcastSink (sink/receiver) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Audio/PublicAudioBroadcastSource](<NUCODE_BLE_Audio/examples/PublicAudioBroadcastSource/PublicAudioBroadcastSource.ino>) | `ble_audio` | `ble` | 2대 — PublicAudioBroadcastSource (source/transmitter); PublicAudioBroadcastSink (sink/receiver) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Audio/TelephonyMediaBroadcaster](<NUCODE_BLE_Audio/examples/TelephonyMediaBroadcaster/TelephonyMediaBroadcaster.ino>) | `ble_audio` | `ble` | 2대 — TelephonyMediaBroadcaster (broadcaster); TelephonyMediaReceiver (receiver) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Audio/TelephonyMediaGateway](<NUCODE_BLE_Audio/examples/TelephonyMediaGateway/TelephonyMediaGateway.ino>) | `ble_audio` | `ble` | 2대 — TelephonyMediaGateway (gateway); TelephonyMediaTerminal (terminal) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Audio/TelephonyMediaReceiver](<NUCODE_BLE_Audio/examples/TelephonyMediaReceiver/TelephonyMediaReceiver.ino>) | `ble_audio` | `ble` | 2대 — TelephonyMediaBroadcaster (broadcaster); TelephonyMediaReceiver (receiver) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Audio/TelephonyMediaTerminal](<NUCODE_BLE_Audio/examples/TelephonyMediaTerminal/TelephonyMediaTerminal.ino>) | `ble_audio` | `ble` | 2대 — TelephonyMediaGateway (gateway); TelephonyMediaTerminal (terminal) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_ChannelSounding/RasInitiator](<NUCODE_BLE_ChannelSounding/examples/RasInitiator/RasInitiator.ino>) | `ble_channel_sounding` | `ble` | 2대 — RasInitiator (initiator); RasReflector (reflector) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_ChannelSounding/RasReflector](<NUCODE_BLE_ChannelSounding/examples/RasReflector/RasReflector.ino>) | `ble_channel_sounding` | `ble` | 2대 — RasInitiator (initiator); RasReflector (reflector) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Companion/AppleMediaClient](<NUCODE_BLE_Companion/examples/AppleMediaClient/AppleMediaClient.ino>) | `ble_profiles_and_ecosystems` | `ble` | 1대 — AppleMediaClient (AMS client) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Companion/AppleNotificationClient](<NUCODE_BLE_Companion/examples/AppleNotificationClient/AppleNotificationClient.ino>) | `ble_profiles_and_ecosystems` | `ble` | 1대 — AppleNotificationClient (ANCS client) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_DFU/SecureDfuPeripheral](<NUCODE_BLE_DFU/examples/SecureDfuPeripheral/SecureDfuPeripheral.ino>) | `ble_dfu` | `secure_ble_dfu` | 1대 — SecureDfuPeripheral (peripheral/server) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_DirectionFinding/ConnectedCteResponder](<NUCODE_BLE_DirectionFinding/examples/ConnectedCteResponder/ConnectedCteResponder.ino>) | `ble_direction_finding` | `ble` | 1대 — ConnectedCteResponder (responder) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_DirectionFinding/CteBeacon](<NUCODE_BLE_DirectionFinding/examples/CteBeacon/CteBeacon.ino>) | `ble_direction_finding` | `ble` | 1대 — CteBeacon 실행 보드 | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_EATT/EattCentral](<NUCODE_BLE_EATT/examples/EattCentral/EattCentral.ino>) | `ble_gatt_extensions` | `ble` | 2대 — EattCentral (central/client); EattPeripheral (peripheral/server) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_EATT/EattPeripheral](<NUCODE_BLE_EATT/examples/EattPeripheral/EattPeripheral.ino>) | `ble_gatt_extensions` | `ble` | 2대 — EattCentral (central/client); EattPeripheral (peripheral/server) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_ISO/BISEncryptedReceiver](<NUCODE_BLE_ISO/examples/BISEncryptedReceiver/BISEncryptedReceiver.ino>) | `ble_iso` | `ble` | 2대 — BISEncryptedSource (source/transmitter); BISEncryptedReceiver (receiver) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_ISO/BISEncryptedSource](<NUCODE_BLE_ISO/examples/BISEncryptedSource/BISEncryptedSource.ino>) | `ble_iso` | `ble` | 2대 — BISEncryptedSource (source/transmitter); BISEncryptedReceiver (receiver) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_ISO/BISReceiver](<NUCODE_BLE_ISO/examples/BISReceiver/BISReceiver.ino>) | `ble_iso` | `ble` | 2대 — BISSource (source/transmitter); BISReceiver (receiver) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_ISO/BISSource](<NUCODE_BLE_ISO/examples/BISSource/BISSource.ino>) | `ble_iso` | `ble` | 2대 — BISSource (source/transmitter); BISReceiver (receiver) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_ISO/BISTimeReceiver](<NUCODE_BLE_ISO/examples/BISTimeReceiver/BISTimeReceiver.ino>) | `ble_iso` | `ble` | 2대 — BISTimeSource (source/transmitter); BISTimeReceiver (receiver) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_ISO/BISTimeSource](<NUCODE_BLE_ISO/examples/BISTimeSource/BISTimeSource.ino>) | `ble_iso` | `ble` | 2대 — BISTimeSource (source/transmitter); BISTimeReceiver (receiver) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_ISO/CISCentral](<NUCODE_BLE_ISO/examples/CISCentral/CISCentral.ino>) | `ble_iso` | `ble` | 2대 — CISCentral (central/client); CISPeripheral (peripheral/server) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_ISO/CISPeripheral](<NUCODE_BLE_ISO/examples/CISPeripheral/CISPeripheral.ino>) | `ble_iso` | `ble` | 2대 — CISCentral (central/client); CISPeripheral (peripheral/server) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_ISO/CISToBISBridge](<NUCODE_BLE_ISO/examples/CISToBISBridge/CISToBISBridge.ino>) | `ble_iso` | `ble` | 3대 — CISToBISPeer (peer); CISToBISBridge (bridge); CISToBISReceiver (receiver) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_ISO/CISToBISPeer](<NUCODE_BLE_ISO/examples/CISToBISPeer/CISToBISPeer.ino>) | `ble_iso` | `ble` | 3대 — CISToBISPeer (peer); CISToBISBridge (bridge); CISToBISReceiver (receiver) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_ISO/CISToBISReceiver](<NUCODE_BLE_ISO/examples/CISToBISReceiver/CISToBISReceiver.ino>) | `ble_iso` | `ble` | 3대 — CISToBISPeer (peer); CISToBISBridge (bridge); CISToBISReceiver (receiver) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_LegacySigning/LegacySignedWriteCentral](<NUCODE_BLE_LegacySigning/examples/LegacySignedWriteCentral/LegacySignedWriteCentral.ino>) | `ble_gatt_extensions` | `ble` | 2대 — LegacySignedWriteCentral (central/client); LegacySignedWritePeripheral (peripheral/server) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_LegacySigning/LegacySignedWritePeripheral](<NUCODE_BLE_LegacySigning/examples/LegacySignedWritePeripheral/LegacySignedWritePeripheral.ino>) | `ble_gatt_extensions` | `ble` | 2대 — LegacySignedWriteCentral (central/client); LegacySignedWritePeripheral (peripheral/server) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Mesh/MeshFriend](<NUCODE_BLE_Mesh/examples/MeshFriend/MeshFriend.ino>) | `ble_mesh_models` | `ble` | 2대 — MeshFriend 실행 보드; friendship을 요청하는 provisioned Low Power Node | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Mesh/MeshHealth](<NUCODE_BLE_Mesh/examples/MeshHealth/MeshHealth.ino>) | `ble_mesh_models` | `ble` | 2대 — MeshHealth foundation node; Configuration/Health Client를 가진 provisioner | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Mesh/MeshLevel](<NUCODE_BLE_Mesh/examples/MeshLevel/MeshLevel.ino>) | `ble_mesh_models` | `ble` | 2대 — Generic Level Client; AppKey가 bind된 Generic Level Server | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Mesh/MeshLight](<NUCODE_BLE_Mesh/examples/MeshLight/MeshLight.ino>) | `ble_mesh_models` | `ble` | 2대 — Light Lightness Client; AppKey가 bind된 Light Lightness Server | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Mesh/MeshLowPowerNode](<NUCODE_BLE_Mesh/examples/MeshLowPowerNode/MeshLowPowerNode.ino>) | `ble_mesh_models` | `ble` | 2대 — Mesh Low Power Node; 같은 subnet의 Mesh Friend | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Mesh/MeshNode](<NUCODE_BLE_Mesh/examples/MeshNode/MeshNode.ino>) | `ble_mesh_models` | `ble` | 2대 — PB-ADV/PB-GATT provisionee node; Mesh provisioner | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Mesh/MeshOnOff](<NUCODE_BLE_Mesh/examples/MeshOnOff/MeshOnOff.ino>) | `ble_mesh_models` | `ble` | 2대 — Generic OnOff Client; AppKey가 bind된 Generic OnOff Server | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Mesh/MeshProvisioner](<NUCODE_BLE_Mesh/examples/MeshProvisioner/MeshProvisioner.ino>) | `ble_mesh_models` | `ble` | 2대 — PB-ADV/PB-GATT provisioner; 초기화되지 않은 Mesh node | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Mesh/MeshProxy](<NUCODE_BLE_Mesh/examples/MeshProxy/MeshProxy.ino>) | `ble_mesh_models` | `ble` | 2대 — GATT Proxy node; Mesh Proxy Client | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Mesh/MeshRelay](<NUCODE_BLE_Mesh/examples/MeshRelay/MeshRelay.ino>) | `ble_mesh_models` | `ble` | 2대 — Relay node; 같은 subnet의 source 또는 destination node | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Mesh/MeshSensor](<NUCODE_BLE_Mesh/examples/MeshSensor/MeshSensor.ino>) | `ble_mesh_models` | `ble` | 2대 — Sensor Client; AppKey가 bind된 Sensor Server | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Mesh/MeshTimeSceneScheduler](<NUCODE_BLE_Mesh/examples/MeshTimeSceneScheduler/MeshTimeSceneScheduler.ino>) | `ble_mesh_models` | `ble` | 2대 — Time/Scene/Scheduler Client; AppKey가 bind된 Time/Scene/Scheduler Server | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Mesh_Management/MeshLargeCompositionDataClient](<NUCODE_BLE_Mesh_Management/examples/MeshLargeCompositionDataClient/MeshLargeCompositionDataClient.ino>) | `ble_mesh_management` | `ble` | 2대 — Large Composition Data Client; Large Composition Data Server | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Mesh_Management/MeshLargeCompositionDataServer](<NUCODE_BLE_Mesh_Management/examples/MeshLargeCompositionDataServer/MeshLargeCompositionDataServer.ino>) | `ble_mesh_management` | `ble` | 2대 — Large Composition Data Server; Large Composition Data Client | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Mesh_Management/MeshOnDemandPrivateProxy](<NUCODE_BLE_Mesh_Management/examples/MeshOnDemandPrivateProxy/MeshOnDemandPrivateProxy.ino>) | `ble_mesh_management` | `ble` | 2대 — On-Demand Private Proxy Client; On-Demand Private Proxy Server | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Mesh_Management/MeshOpcodeAggregatorClient](<NUCODE_BLE_Mesh_Management/examples/MeshOpcodeAggregatorClient/MeshOpcodeAggregatorClient.ino>) | `ble_mesh_management` | `ble` | 2대 — Opcodes Aggregator Client; Opcodes Aggregator Server | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Mesh_Management/MeshOpcodeAggregatorServer](<NUCODE_BLE_Mesh_Management/examples/MeshOpcodeAggregatorServer/MeshOpcodeAggregatorServer.ino>) | `ble_mesh_management` | `ble` | 2대 — Opcodes Aggregator Server; Opcodes Aggregator Client | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Mesh_Management/MeshPrivateBeaconClient](<NUCODE_BLE_Mesh_Management/examples/MeshPrivateBeaconClient/MeshPrivateBeaconClient.ino>) | `ble_mesh_management` | `ble` | 2대 — Private Beacon Client; Private Beacon Server | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Mesh_Management/MeshPrivateBeaconServer](<NUCODE_BLE_Mesh_Management/examples/MeshPrivateBeaconServer/MeshPrivateBeaconServer.ino>) | `ble_mesh_management` | `ble` | 2대 — Private Beacon Server; Private Beacon Client | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Mesh_Management/MeshProxySolicitation](<NUCODE_BLE_Mesh_Management/examples/MeshProxySolicitation/MeshProxySolicitation.ino>) | `ble_mesh_management` | `ble` | 2대 — Solicitation PDU 송신 node; On-Demand Private Proxy Server | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Mesh_Management/MeshRemoteProvisioner](<NUCODE_BLE_Mesh_Management/examples/MeshRemoteProvisioner/MeshRemoteProvisioner.ino>) | `ble_mesh_management` | `ble` | 3대 — Remote Provisioning Client; Remote Provisioning Server; unprovisioned node | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Mesh_Management/MeshRemoteProvisioningServer](<NUCODE_BLE_Mesh_Management/examples/MeshRemoteProvisioningServer/MeshRemoteProvisioningServer.ino>) | `ble_mesh_management` | `ble` | 3대 — Remote Provisioning Server; Remote Provisioning Client; unprovisioned node | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Mesh_Management/MeshSarConfigurationClient](<NUCODE_BLE_Mesh_Management/examples/MeshSarConfigurationClient/MeshSarConfigurationClient.ino>) | `ble_mesh_management` | `ble` | 2대 — SAR Configuration Client; SAR Configuration Server | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Mesh_Management/MeshSarConfigurationServer](<NUCODE_BLE_Mesh_Management/examples/MeshSarConfigurationServer/MeshSarConfigurationServer.ino>) | `ble_mesh_management` | `ble` | 2대 — SAR Configuration Server; SAR Configuration Client | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Mesh_Management/MeshSubnetBridge](<NUCODE_BLE_Mesh_Management/examples/MeshSubnetBridge/MeshSubnetBridge.ino>) | `ble_mesh_management` | `ble` | 3대 — Bridge Configuration Client; Subnet Bridge node; 두 subnet의 source 또는 destination node | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Mesh_Update/MeshBlobClient](<NUCODE_BLE_Mesh_Update/examples/MeshBlobClient/MeshBlobClient.ino>) | `ble_mesh_update` | `secure_ble_dfu` | 3대 — BLOB Client; BLOB Server target 0x0002; BLOB Server target 0x0003 | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Mesh_Update/MeshBlobServer](<NUCODE_BLE_Mesh_Update/examples/MeshBlobServer/MeshBlobServer.ino>) | `ble_mesh_update` | `secure_ble_dfu` | 2대 — BLOB Server; BLOB Client | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Mesh_Update/MeshDfuTarget](<NUCODE_BLE_Mesh_Update/examples/MeshDfuTarget/MeshDfuTarget.ino>) | `ble_mesh_update` | `secure_ble_dfu` | 2대 — Mesh DFU Target; Mesh DFU Initiator 또는 Distributor | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Mesh_Update/MeshFirmwareDistributor](<NUCODE_BLE_Mesh_Update/examples/MeshFirmwareDistributor/MeshFirmwareDistributor.ino>) | `ble_mesh_update` | `secure_ble_dfu` | 3대 — Firmware Distributor; Mesh DFU Initiator; Mesh DFU Target | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Profiles/AlertSensor](<NUCODE_BLE_Profiles/examples/AlertSensor/AlertSensor.ino>) | `ble_profiles_and_ecosystems` | `ble` | 2대 — ANS alert server; Kind::alert로 설정한 StandardCollector | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Profiles/BondManagement](<NUCODE_BLE_Profiles/examples/BondManagement/BondManagement.ino>) | `ble_profiles_and_ecosystems` | `ble` | 2대 — 사용자 무장 BMS server; 암호화·bond된 BMS 요청 peer | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Profiles/GlucoseSensor](<NUCODE_BLE_Profiles/examples/GlucoseSensor/GlucoseSensor.ino>) | `ble_profiles_and_ecosystems` | `ble` | 2대 — synthetic CGMS server; Kind::glucose로 설정한 StandardCollector | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Profiles/ObjectClient](<NUCODE_BLE_Profiles/examples/ObjectClient/ObjectClient.ino>) | `ble_profiles_and_ecosystems` | `ble` | 2대 — OTC object client; ObjectServer | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Profiles/ObjectServer](<NUCODE_BLE_Profiles/examples/ObjectServer/ObjectServer.ino>) | `ble_profiles_and_ecosystems` | `ble` | 2대 — RAM OTS object server; ObjectClient | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Profiles/StandardCollector](<NUCODE_BLE_Profiles/examples/StandardCollector/StandardCollector.ino>) | `ble_profiles_and_ecosystems` | `ble` | 2대 — 표준 GATT collector; StandardSensor/AlertSensor/GlucoseSensor 중 선택한 server | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Profiles/StandardSensor](<NUCODE_BLE_Profiles/examples/StandardSensor/StandardSensor.ino>) | `ble_profiles_and_ecosystems` | `ble` | 2대 — 선택한 표준 측정 service server; 같은 sensorKind의 StandardCollector | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Security/EnvironmentalSensing](<NUCODE_BLE_Security/examples/EnvironmentalSensing/EnvironmentalSensing.ino>) | `ble_profiles_and_ecosystems` | `ble` | 1대 — EnvironmentalSensing 실행 보드 | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Security/GattCacheCentral](<NUCODE_BLE_Security/examples/GattCacheCentral/GattCacheCentral.ino>) | `ble_profiles_and_ecosystems` | `ble` | 2대 — GattCacheCentral (central/client); GattCachePeripheral (peripheral/server) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Security/GattCachePeripheral](<NUCODE_BLE_Security/examples/GattCachePeripheral/GattCachePeripheral.ino>) | `ble_profiles_and_ecosystems` | `ble` | 2대 — GattCacheCentral (central/client); GattCachePeripheral (peripheral/server) | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Security/HeartRate](<NUCODE_BLE_Security/examples/HeartRate/HeartRate.ino>) | `ble_profiles_and_ecosystems` | `ble` | 1대 — HeartRate 실행 보드 | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Security/SecureConsumerControl](<NUCODE_BLE_Security/examples/SecureConsumerControl/SecureConsumerControl.ino>) | `ble_profiles_and_ecosystems` | `ble` | 1대 — SecureConsumerControl 실행 보드 | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Security/SecureKeyboard](<NUCODE_BLE_Security/examples/SecureKeyboard/SecureKeyboard.ino>) | `ble_profiles_and_ecosystems` | `ble` | 1대 — SecureKeyboard 실행 보드 | `procedure_documented_not_physical_pass` |
| [NUCODE_BLE_Security/SecureMouse](<NUCODE_BLE_Security/examples/SecureMouse/SecureMouse.ino>) | `ble_profiles_and_ecosystems` | `ble` | 1대 — SecureMouse 실행 보드 | `procedure_documented_not_physical_pass` |
| [NUCODE_NU54DK/AnalogChannels](<NUCODE_NU54DK/examples/AnalogChannels/AnalogChannels.ino>) | `analog_pwm_tone` | `standard` | 1대 — AnalogChannels 실행 보드 | `procedure_documented_not_physical_pass` |
| [NUCODE_NU54DK/AnalogReadA0](<NUCODE_NU54DK/examples/AnalogReadA0/AnalogReadA0.ino>) | `analog_pwm_tone` | `standard` | 1대 — AnalogReadA0 실행 보드 | `procedure_documented_not_physical_pass` |
| [NUCODE_NU54DK/AnalogResolution](<NUCODE_NU54DK/examples/AnalogResolution/AnalogResolution.ino>) | `analog_pwm_tone` | `standard` | 1대 — AnalogResolution 실행 보드 | `procedure_documented_not_physical_pass` |
| [NUCODE_NU54DK/Blink](<NUCODE_NU54DK/examples/Blink/Blink.ino>) | `gpio_interrupt` | `standard` | 1대 — Blink 실행 보드 | `procedure_documented_not_physical_pass` |
| [NUCODE_NU54DK/BoardInfo](<NUCODE_NU54DK/examples/BoardInfo/BoardInfo.ino>) | `board_system_power` | `standard` | 1대 — BoardInfo 실행 보드 | `procedure_documented_not_physical_pass` |
| [NUCODE_NU54DK/CounterAlarm](<NUCODE_NU54DK/examples/CounterAlarm/CounterAlarm.ino>) | `board_system_power` | `standard` | 1대 — CounterAlarm 실행 보드 | `procedure_documented_not_physical_pass` |
| [NUCODE_NU54DK/DynamicPWM](<NUCODE_NU54DK/examples/DynamicPWM/DynamicPWM.ino>) | `analog_pwm_tone` | `standard` | 1대 — DynamicPWM 실행 보드 | `procedure_documented_not_physical_pass` |
| [NUCODE_NU54DK/InterruptButton](<NUCODE_NU54DK/examples/InterruptButton/InterruptButton.ino>) | `gpio_interrupt` | `standard` | 1대 — InterruptButton 실행 보드 | `procedure_documented_not_physical_pass` |
| [NUCODE_NU54DK/PWMFade](<NUCODE_NU54DK/examples/PWMFade/PWMFade.ino>) | `analog_pwm_tone` | `standard` | 1대 — PWMFade 실행 보드 | `procedure_documented_not_physical_pass` |
| [NUCODE_NU54DK/Serial1RuntimePins](<NUCODE_NU54DK/examples/Serial1RuntimePins/Serial1RuntimePins.ino>) | `serial` | `standard` | 1대 — Serial1RuntimePins 실행 보드 | `procedure_documented_not_physical_pass` |
| [NUCODE_NU54DK/SerialEcho](<NUCODE_NU54DK/examples/SerialEcho/SerialEcho.ino>) | `serial` | `standard` | 1대 — SerialEcho 실행 보드 | `procedure_documented_not_physical_pass` |
| [NUCODE_NU54DK/SettingsStorage](<NUCODE_NU54DK/examples/SettingsStorage/SettingsStorage.ino>) | `storage` | `standard` | 1대 — SettingsStorage 실행 보드 | `procedure_documented_not_physical_pass` |
| [NUCODE_NU54DK/SPI00RuntimePins](<NUCODE_NU54DK/examples/SPI00RuntimePins/SPI00RuntimePins.ino>) | `spi` | `standard` | 1대 — SPI00RuntimePins 실행 보드 | `procedure_documented_not_physical_pass` |
| [NUCODE_NU54DK/SystemOffWake](<NUCODE_NU54DK/examples/SystemOffWake/SystemOffWake.ino>) | `board_system_power` | `standard` | 1대 — SystemOffWake 실행 보드 | `procedure_documented_not_physical_pass` |
| [NUCODE_NU54DK/ToneOutput](<NUCODE_NU54DK/examples/ToneOutput/ToneOutput.ino>) | `analog_pwm_tone` | `standard` | 1대 — ToneOutput 실행 보드 | `procedure_documented_not_physical_pass` |
| [NUCODE_NU54DK/WatchdogBasic](<NUCODE_NU54DK/examples/WatchdogBasic/WatchdogBasic.ino>) | `board_system_power` | `standard` | 1대 — WatchdogBasic 실행 보드 | `procedure_documented_not_physical_pass` |
| [NUCODE_NU54DK/WireRuntimePins](<NUCODE_NU54DK/examples/WireRuntimePins/WireRuntimePins.ino>) | `i2c_wire` | `standard` | 1대 — WireRuntimePins 실행 보드 | `procedure_documented_not_physical_pass` |
| [NUCODE_Peripheral_Fabric/AdcContinuousDma](<NUCODE_Peripheral_Fabric/examples/AdcContinuousDma/AdcContinuousDma.ino>) | `peripheral_fabric` | `fabric` | 1대 — SAADC continuous DMA 실행 보드 | `procedure_documented_not_physical_pass` |
| [NUCODE_Peripheral_Fabric/FabricCapabilities](<NUCODE_Peripheral_Fabric/examples/FabricCapabilities/FabricCapabilities.ino>) | `peripheral_fabric` | `fabric` | 1대 — FabricCapabilities 실행 보드 | `procedure_documented_not_physical_pass` |
| [NUCODE_Peripheral_Fabric/PwmSequencePlayback](<NUCODE_Peripheral_Fabric/examples/PwmSequencePlayback/PwmSequencePlayback.ino>) | `peripheral_fabric` | `fabric` | 1대 — PWM sequence 재생 보드 | `procedure_documented_not_physical_pass` |
| [NUCODE_Peripheral_Fabric/ResourceConflictDemo](<NUCODE_Peripheral_Fabric/examples/ResourceConflictDemo/ResourceConflictDemo.ino>) | `peripheral_fabric` | `fabric` | 1대 — Serial block 충돌·재획득 실행 보드 | `procedure_documented_not_physical_pass` |
| [NUCODE_Peripheral_Fabric/SpiAsyncLoopback](<NUCODE_Peripheral_Fabric/examples/SpiAsyncLoopback/SpiAsyncLoopback.ino>) | `peripheral_fabric` | `fabric` | 1대 — SPIM20 async loopback 보드 | `procedure_documented_not_physical_pass` |
| [NUCODE_Peripheral_Fabric/TwisTargetDoubleBuffer](<NUCODE_Peripheral_Fabric/examples/TwisTargetDoubleBuffer/TwisTargetDoubleBuffer.ino>) | `peripheral_fabric` | `fabric` | 1대 — TWIS21 target 보드 | `procedure_documented_not_physical_pass` |
| [NUCODE_Peripheral_Fabric/UarteAsyncEcho](<NUCODE_Peripheral_Fabric/examples/UarteAsyncEcho/UarteAsyncEcho.ino>) | `peripheral_fabric` | `fabric` | 1대 — UARTE20 async echo 보드 | `procedure_documented_not_physical_pass` |
| [NUCODE_Radio_Coexistence/Ble154Coexistence](<NUCODE_Radio_Coexistence/examples/Ble154Coexistence/Ble154Coexistence.ino>) | `radio_coexistence` | `coexistence_ble_154` | 3대 — BLE + IEEE 802.15.4 coexistence receiver; IEEE 802.15.4 transmitter 0x0001; BLE NUS central | `procedure_documented_not_physical_pass` |
| [NUCODE_Radio_Coexistence/BleEsbCoexistence](<NUCODE_Radio_Coexistence/examples/BleEsbCoexistence/BleEsbCoexistence.ino>) | `radio_coexistence` | `coexistence_ble_esb` | 3대 — BLE + ESB coexistence PRX; ESB PTX; BLE NUS central | `procedure_documented_not_physical_pass` |
| [NUCODE_Radio_Coexistence/BleMeshCoexistence](<NUCODE_Radio_Coexistence/examples/BleMeshCoexistence/BleMeshCoexistence.ino>) | `radio_coexistence` | `coexistence_ble_mesh` | 3대 — BLE NUS + Mesh coexistence node; Mesh provisioner/peer; BLE NUS central | `procedure_documented_not_physical_pass` |
| [NUCODE_Radio_Coexistence/RadioCoexistenceOneWire](<NUCODE_Radio_Coexistence/examples/RadioCoexistenceOneWire/RadioCoexistenceOneWire.ino>) | `radio_coexistence` | `external_coexistence` | 1대 — 1-wire grant simulator와 BLE advertiser | `procedure_documented_not_physical_pass` |
| [NUCODE_Radio_ESB/EsbPrx](<NUCODE_Radio_ESB/examples/EsbPrx/EsbPrx.ino>) | `radio_esb` | `radio_esb` | 2대 — ESB PRX; ESB PTX | `procedure_documented_not_physical_pass` |
| [NUCODE_Radio_ESB/EsbPtx](<NUCODE_Radio_ESB/examples/EsbPtx/EsbPtx.ino>) | `radio_esb` | `radio_esb` | 2대 — ESB PTX; ESB PRX | `procedure_documented_not_physical_pass` |
| [NUCODE_Radio_IEEE802154/Radio154Receiver](<NUCODE_Radio_IEEE802154/examples/Radio154Receiver/Radio154Receiver.ino>) | `radio_802154` | `radio_ieee802154` | 2대 — IEEE 802.15.4 receiver 0x0002; IEEE 802.15.4 transmitter 0x0001 | `procedure_documented_not_physical_pass` |
| [NUCODE_Radio_IEEE802154/Radio154Transmitter](<NUCODE_Radio_IEEE802154/examples/Radio154Transmitter/Radio154Transmitter.ino>) | `radio_802154` | `radio_ieee802154` | 2대 — IEEE 802.15.4 transmitter 0x0001; IEEE 802.15.4 receiver 0x0002 | `procedure_documented_not_physical_pass` |
| [Servo/Sweep](<Servo/examples/Sweep/Sweep.ino>) | `servo_motion` | `standard` | 1대 — Sweep 실행 보드 | `procedure_documented_not_physical_pass` |
| [SPI/SPITransaction](<SPI/examples/SPITransaction/SPITransaction.ino>) | `spi` | `standard` | 1대 — SPITransaction 실행 보드 | `procedure_documented_not_physical_pass` |
| [Wire/WirePmicId](<Wire/examples/WirePmicId/WirePmicId.ino>) | `i2c_wire` | `standard` | 1대 — WirePmicId 실행 보드 | `procedure_documented_not_physical_pass` |

## 판정 경계

- `clean_installed_compile_required`는 clean 설치본 compile 대상이라는 뜻이며 runtime PASS가 아닙니다.
- `procedure_documented_not_physical_pass`는 실행 절차와 역할 계약이 있다는 뜻이며 미실행 실물을 PASS로 세지 않습니다.
- Apple/Google peer, 외장 audio·sensor·RF 계측기는 사용자 후속 결과를 별도 `NOT_RUN` 또는 실제 결과로 기록합니다.
- 자동 mass erase·unlock·recover는 예제 실행 절차에 포함하지 않습니다.
