# v0.5.0 Release notes

`v0.5.0`은 v0.4.1의 Arduino 주변장치·Storage·Peripheral Fabric 기반에 M28~M31의 Bluetooth 기능과
RC2 사용자 경험 교정을 더한 Windows 정식 릴리스입니다.

## 주요 변경

- Central 1 + Peripheral 1의 2-link, 확장·주기 광고, PAST·PAwR, privacy/RPA를 제공합니다.
- Long/reliable GATT, descriptor·authorization·cache, LE CoC와 역할별 보안·OOB·bond 관리를 제공합니다.
- CIS/BIS, 암호화·시간 동기, LC3와 BAP/CAP/CSIP/PBP, TMAP/GMAP/HAP 예제를 제공합니다.
- 제품 SDC의 connectionless AoA CTE 송신, 별도 Zephyr LL opt-in의 connected response 송신,
  Channel Sounding Initiator/Reflector와 RAS 예제를 제공합니다.
- 별도 MCUboot 구성의 secure BLE DFU와 signed image 수명주기를 제공합니다.
- 공개 library 16개와 예제 113개를 Arduino 설치본에 포함합니다.

## RC2 이후 정식 교정

- `Standard peripherals`에서 부팅 시 모든 runtime 장치를 자동 suspend하지 않도록 하여, Blink 실행 뒤
  Sketch를 수정한 연속 pyOCD Upload의 `SWD/JTAG No ACK` 문제를 해결했습니다.
- Wire·SPI·PWM은 실제 사용 시 필요한 개별 runtime PM 경로를 유지합니다.
- 사용자 Arduino IDE에서 250 ms Blink 뒤 100 ms Blink를 USB 재연결 없이 연속 Upload해 확인했습니다.

## 빌드·업로드 사용자 경험

- 예제마다 Feature set·역할·보드 수·Serial·sidecar 안내를 제공합니다.
- 한 probe 자동 선택, 다중 probe fail-closed, UID 입력 검증·마스킹과 J-Link 조건을 명확히 합니다.
- UTF-8 한국어 진단, 단계별 Verify 진행과 heartbeat, 원인별 upload 오류 코드를 제공합니다.
- Sketch 변경과 Arduino 임시 build path 변경에서 안전한 CMake/Ninja/cache 재사용을 적용합니다.

RC2에서 수용한 CI 시간 목표 미달과 bounded retry 이력은 삭제하지 않습니다. 기능·패키지·설치·예제·
실물 Upload gate와 정식 공개 승인은 별도로 확인했습니다. 자세한 범위는 [Testing](TESTING.md)과
[274번 기록](<../../04_검증 기록/274_v0.5.0_정식_릴리스_승인과_공개.md>)을 따릅니다.
