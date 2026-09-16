# Secure BLE DFU 예제

`SecureDfuPeripheral`은 `secure_ble_dfu` Arduino board profile에서 빌드한다. 이 profile은
MCUboot sysbuild, ECDSA P-256 image 서명, MCUmgr SMP over BLE, 인증된 GATT 접근을 함께
선택한다. 빌드에는 외부 signing key 경로인 `NUCODE_DFU_SIGNING_KEY`가 필요하다. private key
내용을 sketch, 빌드 로그, 저장소에 복사하지 않는다.

예제는 실행 image의 MCUboot header를 읽고 BLE 보안과 SMP service UUID 광고를 초기화한다.
실제 SMP GATT service는 고정 Zephyr transport가 등록하며, sketch의 UUID 광고는 scanner가
찾기 위한 정보다. Serial Monitor는 115200 baud와 newline을 사용한다.

| UART 명령 | 실제 동작 |
| --- | --- |
| `STATUS` | active slot, semantic version, confirmed bit를 출력한다. |
| `PAIR YES` / `PAIR NO` | 현재 connection의 pairing 요청에 사용자 응답을 보낸다. |
| `VERIFY YES` / `VERIFY NO` | 표시된 numeric comparison을 현재 connection에 승인/거부한다. |
| `PIN 123456` | stack이 passkey 입력을 요구한 경우에만 6자리 값을 제공한다. |
| `CONFIRM` | MCUboot header·보안·광고 self-test가 성공한 후 실행 image를 **명시적으로** 확인한다. |

`CONFIRM`을 자동 호출하지 않는다. 새 test image를 확인하지 않고 재시작하면 MCUboot rollback
대상이 된다. 연결이 없거나 사용자 응답이 만료되면 pairing 명령을 거부한다. 32-byte보다 긴
UART 줄 전체를 폐기하고 명령의 나머지 조각을 실행하지 않는다. 인증된 peer의 DFU image 업로드,
reboot, rollback 실기는 [M30 DFU 검증 기록](<../../../00_Docs/04_검증 기록/157_M30_W06_secure_BLE_DFU_negative_rollback_완료.md>)의
별도 HIL 결과와 구분한다.
