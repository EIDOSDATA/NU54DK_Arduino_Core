# NU54DK Arduino Core

NU54DK의 nRF54L15 애플리케이션 코어(CPUAPP)에서 Arduino 스케치를 실행합니다. 스케치와 라이브러리를 고정된 nRF Connect SDK(NCS) 3.4.0으로 빌드하고, 보드에 내장된 CMSIS-DAP으로 업로드합니다.

## 버전 선택

| 사용 목적 | 선택할 버전 | 설치 경로 |
| --- | --- | --- |
| v0.6.0 개발 및 검증 | 개발 브랜치 `Dev-0.6.0-M33`, 비공개 패키지 `0.6.0-rc.1` | [후보 설치 및 버전 확인](<00_Docs/05_릴리스/v0.6.0/README.md>) |
| 공개 버전 설치 | Windows 10/11 x64용 v0.5.0 | [공개 Boards Manager 설치 안내](<00_Docs/05_릴리스/v0.5.0/README.md>) |

v0.6.0 후보에는 라이브러리 24개, Arduino 예제 204개, 빌드 레시피 29개가 있습니다. Windows 11 x64, Ubuntu 24.04 및 26.04 LTS AMD64(WSL2), macOS 26 및 27(Apple Silicon)에서 배정한 검증을 마쳤습니다. Ubuntu 사용자 장치 검증은 WSL2에서 수행했고, native Linux 사용자 실기는 미실행입니다. 정식 v0.6.0 패키지와 공개 설치 URL은 최종 후보 심사 및 공개 승인 후 확정합니다. [OS별 검증 범위](<00_Docs/05_릴리스/v0.6.0/SUPPORT_MATRIX.md>)

## 빠른 시작

1. 위 표에서 설치 경로를 고릅니다. Mac에서 일반 IDE Upload를 사용할 때는 C12 후보를 선택합니다. C11과 C12는 버전명이 같으므로 설치한 패키지의 `release-manifest.json`에서 `core_revision`이 `97c7cd01ff59fb5ae3689e9de62b9c820b83fd5e`인지 확인합니다.
2. 데이터 통신용 USB 케이블로 NU54DK 한 대를 연결합니다. Arduino IDE에서 보드 `NU54DK (nRF54L15, Zephyr)`와 현재 보드의 직렬 포트를 선택합니다. `Tools > Feature set`은 `Standard peripherals`, `Upload probe`는 기본 CMSIS-DAP 설정을 사용합니다.
3. `File > Examples > NUCODE NU54DK > Blink`에서 **Verify**를 누른 뒤 **Upload**를 누릅니다. 출력 창에 `Done uploading.`이 표시되고 온보드 LED가 250 ms마다 바뀌면 동작을 확인한 것입니다. [Blink 소스](libraries/NUCODE_NU54DK/examples/Blink/Blink.ino)
4. UART를 확인하려면 같은 설정으로 `SerialEcho`를 업로드합니다. 보드의 DAP UART 포트를 115200 8N1로 열고 Serial Monitor의 줄 끝을 `Newline`으로 설정하세요. `test`를 보내면 `NUCODE_M6_ECHO:test`가 돌아옵니다. 여러 보드를 연결했다면 현재 열거한 probe와 포트의 대응을 확인합니다. [SerialEcho](libraries/NUCODE_NU54DK/examples/SerialEcho/SerialEcho.ino), [업로드와 디버그](<00_Docs/02_빌드 설계/05_업로드와_디버그.md>)

**Mac에서 `No module named 'yaml'`가 뜨면** IDE가 사용한 설치본부터 확인하세요. C11의 오류는 probe 선택 전에 발생합니다. C12는 runner 설정을 읽을 때 고정 Nordic SDK의 Python을 사용합니다. macOS 27.2.1, Arduino IDE 2.3.11에서 일반 Upload와 LED 점멸을 확인했습니다. [후보 구분 및 문제 해결](<00_Docs/05_릴리스/v0.6.0/TROUBLESHOOTING.md>)

## 지원 기능

| 사용할 기능 | IDE의 Feature set 또는 선택 기준 |
| --- | --- |
| GPIO, Serial, Wire, SPI, ADC, PWM, Servo, 내부 저장소 | `standard`가 기본입니다. `fabric`은 인스턴스 및 DMA 직접 제어용이며 DAP UART 연결을 해제합니다. |
| BLE NUS, GAP/GATT, 보안, 프로필, ISO, LE Audio, CTE 송신, Channel Sounding | 예제에 지정한 구성을 선택합니다. 기본 BLE는 `ble`, 서명된 DFU는 `secure_ble_dfu`, 외장 오디오 I/O는 `ble_audio_io`입니다. |
| Bluetooth Mesh, BLOB 전송, Mesh 펌웨어 업데이트 | 각 역할의 설정과 상대 보드를 준비합니다. BLE와 Mesh의 공존 예제는 `coexistence_ble_mesh`를 사용합니다. |
| IEEE 802.15.4, Enhanced ShockBurst(ESB) | 단독 무선은 `radio_ieee802154` 또는 `radio_esb`, BLE와 병행하는 예제는 `coexistence_ble_154` 또는 후보 구성 `coexistence_ble_esb`를 사용합니다. |
| 외부 무선 공존, 자동 기능 선택 | 외부 1-wire 공존은 `external_coexistence`, 실험적 자동 선택은 `adaptive`입니다. |

`Serial`은 CMSIS-DAP의 UART 브리지를 사용합니다. Peripheral Fabric과 외장 오디오 예제에서는 UART 공유 핀과 결선을 먼저 확인하세요. 제품 SDC의 Direction Finding IQ 수신 및 AoD는 지원 범위 밖입니다. Apple/Google 서비스와 외부 상용 장치의 상호운용은 사용자 후속 검증 항목입니다. [핀맵](<00_Docs/01_아두이노 코어 설계/13_NU54DK_P2_P4_커넥터_핀맵.md>), [API 범위](<00_Docs/01_아두이노 코어 설계/04_Arduino_API_지원_범위.md>), [알려진 제한](<00_Docs/05_릴리스/v0.6.0/KNOWN_ISSUES.md>)

## 예제

각 스케치의 첫 주석에서 권장 Feature set, 보드 수와 역할, 필요한 설정 파일을 확인할 수 있습니다. 예제 폴더를 복사할 때는 설정 파일도 함께 가져오세요. [전체 예제 색인](libraries/EXAMPLES.md)

| 해볼 작업 | 시작할 예제 |
| --- | --- |
| LED와 직렬 통신 | [Blink](libraries/NUCODE_NU54DK/examples/Blink), [SerialEcho](libraries/NUCODE_NU54DK/examples/SerialEcho) |
| Mesh 네트워크 구성 | [MeshProvisioner](libraries/NUCODE_BLE_Mesh/examples/MeshProvisioner), [MeshNode](libraries/NUCODE_BLE_Mesh/examples/MeshNode) |
| IEEE 802.15.4 송수신 | [Radio154Transmitter](libraries/NUCODE_Radio_IEEE802154/examples/Radio154Transmitter), [Radio154Receiver](libraries/NUCODE_Radio_IEEE802154/examples/Radio154Receiver) |
| 외부 BLE 서비스 연동 | [Companion 예제와 준비 조건](libraries/NUCODE_BLE_Companion/README.md) |

## 문서

- [v0.6.0 변경 사항](<00_Docs/05_릴리스/v0.6.0/RELEASE_NOTES.md>), [버전 전환 안내](<00_Docs/05_릴리스/v0.6.0/MIGRATION.md>)
- [검증한 소스와 결과](<00_Docs/05_릴리스/v0.6.0/TESTING.md>), [정식 배포까지 남은 작업](<00_Docs/05_릴리스/v0.6.0/RELEASE_CHECKLIST.md>)
- [문서 목차](00_Docs/README.md), [개발 인계](00_Docs/HANDOFF.md), [기여 및 검사 방법](CONTRIBUTING.md)

## 문제 보고와 기여

문제를 보고할 때는 OS와 아키텍처, IDE 또는 CLI 버전, 설치한 패키지의 버전과 소스 SHA, 예제와 Feature set, 첫 오류 로그를 함께 적어 주세요. 장치 문제는 보드 수와 연결 방식도 도움이 됩니다. 로그에서 인증 정보와 원시 probe UID를 제거한 뒤 제출해 주세요. [GitHub Issues](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/issues)

## 작성자와 라이선스

NUCODE의 Quantum이 개발합니다. NUCODE 작성 코드에는 MIT 라이선스를 적용합니다. [라이선스](LICENSE), [외부 구성요소 고지](third_party/THIRD_PARTY_NOTICES.md)
