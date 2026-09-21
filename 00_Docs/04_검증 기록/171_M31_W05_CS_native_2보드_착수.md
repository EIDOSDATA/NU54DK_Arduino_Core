# M31-W05 connected Channel Sounding native 2보드 착수

고정 NCS `v3.4.0`과 NU54DK board revision에서 upstream `connected_cs` initiator·reflector를
각각 `nrf54l15dk/nrf54l15/cpuapp/nu54dk`로 clean native build했다. 두 이미지의 빌드
log·HEX 원본 SHA-256과 압축본은 [manifest](evidence/m31-w05-cs-native-332734c2/native-build-manifest.json)에
기록했다. initiator는 FLASH 235452 B/RAM 56948 B, reflector는 FLASH 221076 B/RAM
48232 B를 사용했다. 두 `.config`에서 `CONFIG_BT_CTLR_CHANNEL_SOUNDING=y`를 확인했다.

CMSIS-DAP V2 두 개의 SHA-256 probe identity와 DP/AP register identity를 다시 대조한 뒤
sector flash·hardware reset으로 두 역할을 실행했다. [익명화한 두 보드 UART 기록](evidence/m31-w05-cs-native-332734c2/native-pair-01.json)은
initiator의 ACL 연결, 보안 수준 2, 원격 CS capability 교환, config 생성, CS security 활성화,
procedure 활성화와 첫 결과 처리 진입을 보여 준다. reflector는 같은 연결과 GATT step-data
characteristic 발견, capability 교환을 출력했다. 첫 결과에서 추정기는
`A reliable distance estimate could not be computed.`를 출력했으므로 거리값 출력 PASS로
판정하지 않는다. 이 기록은 native sample의 1회 진단 실행이며 100회 procedure, 복구,
보안 negative, Arduino API·예제, 정밀도 검증의 증거가 아니다.

다음 단계는 Zephyr 호출을 비공개 C++ 구현에 두는 NU54DK Arduino CS API와 양쪽 `.ino`
예제를 작성하고, nonce·역할·보안·raw step 수·오류·중단/재시작을 두 보드 HIL에서 검증하는
것이다. 현재 M31-W05와 `M31-CS-01`은 **진행 중**이며 기능 완료 PASS가 아니다.

같은 native image로 100회 결과를 요청한 [두 번째 진단](evidence/m31-w05-cs-native-332734c2/native-pair-02-manifest.json)은
90초 동안 **1회** 결과만 관찰해 `FAIL`로 기록했다. 그 결과에는 RTT 기반 `1.773772 m`
(6 sample), phase 기반 `1.600384 m`(36 sample)의 추정 출력이 있었지만, 정밀도
검증이 아니다. 이어 initiator boot banner가 다시 나오고 reflector가 HCI reason `0x08`로
연결을 잃었다. [UART 원본](evidence/m31-w05-cs-native-332734c2/native-pair-02.json)을
보존했다. CMSIS-DAP V2 attach로 [RESETREAS](evidence/m31-w05-cs-native-332734c2/resetreas-02.json)를
읽었을 때 `0x00000001`(pin reset)이었지만, 시험 전 sector flash 뒤 수행한 hardware reset도
이 bit를 설정하므로 나중의 reboot 원인을 이 값으로 단정하지 않는다. 후속 Arduino 구현과
별도로 native 반복 중단 원인을 조사해야 한다.

후속 고정 NCS `ras_initiator`·`ras_reflector` native build 및 동일 두 이미지의 reset-only
재실행에서 거리 결과 100개를 얻은 범위는 [173번 진단](173_M31_W05_RAS_native_100회_진단.md)에
기록했다. 이는 W05 Arduino API와 필수 100회·복구·negative 검증을 대신하지 않는다.
