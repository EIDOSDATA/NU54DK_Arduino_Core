# v0.5.0-rc.1 Release notes

v0.4.1의 Arduino 주변장치·Storage·기본 BLE를 유지하고 M28~M31의 확장을 Windows RC로 통합했습니다.
정식 stable 승격이나 Bluetooth qualification 완료를 의미하지 않습니다.

## 주요 변경

| 영역 | RC에 포함한 기능 |
| --- | --- |
| GAP·Link·Privacy | Central 1개 + Peripheral 1개, 총 2-link; 확장·주기 광고, PAST·PAwR와 privacy/RPA |
| ATT·GATT·L2CAP | Long/reliable GATT, descriptor·authorization·cache와 LE CoC; 선택형 Signed Write·EATT |
| Security·Profile·DFU | Link별 보안·OOB·bond 관리, 추가 profile과 별도 MCUboot secure BLE DFU |
| ISO·LE Audio | CIS/BIS·암호화·시간 동기, LC3, BAP/CAP/CSIP/PBP와 TMAP/GMAP/HAP 역할 예제 |
| Direction Finding | 제품 SDC의 connectionless AoA CTE 송신과 별도 Zephyr LL opt-in의 연결형 CTE response; 제품 SDC IQ RX·AoD는 미지원 |
| Channel Sounding | Initiator/reflector, RAS, raw·거리 결과, 오류 처리·재접속 경로 |
| 설치·검증 | 16개 library·113개 예제, Windows GitHub Actions 8 shard에서 113/113 compile |

각 기능의 역할·용량·profile은 예제 README와
[API 지원 범위](<../../01_아두이노 코어 설계/04_Arduino_API_지원_범위.md>)를 따릅니다.
Signed Write는 deprecated legacy opt-in, EATT는 experimental opt-in입니다.
모든 기능·역할을 하나의 firmware에서 동시에 사용할 수 있다는 의미는 아닙니다.

## 메모리와 구성

M31 메모리 최적화 P0·P1·P2와 W01~W08을 완료했습니다. 지원 범위의 오류·최악 부하,
stack/heap 여유와 최종 크기, 동등 조건 Nordic native FLASH/RAM 비교 결과는
[262번 기록](<../../04_검증 기록/262_M31_메모리_최적화_P2_세_축_완료.md>)에 있습니다.

`standard/full` 기본값과 근거가 없는 축소 대상의 기존 크기는 유지합니다.
`adaptive`는 실험적 opt-in이며 기본 profile을 대체하지 않습니다.
정적 symbol 크기나 controller 예약 pool 크기를 runtime 최고 사용량으로 해석하지 않습니다.

## 검증과 제한

[Testing](TESTING.md)은 package·Host/compile·물리 HIL·공개 smoke를 구분해 설명합니다.
외장 audio와 상용 peer, 정밀 angle/distance 보정 및 미지원 controller 기능은
[Known issues](KNOWN_ISSUES.md)를 확인하십시오.

정확한 source·조건·결과는 [W08 완료 기록](<../../04_검증 기록/267_M31_W08_Windows_RC_준비와_M31_완료.md>)과
[공개 RC 기록](<../../04_검증 기록/268_v0.5.0-rc.1_공개와_다운로드_smoke.md>)을 따릅니다.
이 페이지의 후속 안내 보완은 공개 tag·package·checksum을 변경하지 않습니다.
