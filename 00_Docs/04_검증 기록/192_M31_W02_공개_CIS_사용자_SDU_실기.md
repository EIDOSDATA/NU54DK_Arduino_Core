# M31-W02 공개 CIS 사용자 SDU 두 역할 실기

clean Core `1d058140dda468ba19dcfdf3b3b26b1202100efb`에서
[`CISCentral`](../../libraries/NUCODE_BLE_ISO/examples/CISCentral/CISCentral.ino)과
[`CISPeripheral`](../../libraries/NUCODE_BLE_ISO/examples/CISPeripheral/CISPeripheral.ino)을
각각 NU54DK Zephyr / BLE로 빌드했다. 두 `.ino`는 공통 16-byte session ID로
서로를 찾고, Central에서 사용자가 만든 8-byte SDU를 `RawCis::sendFrame()`으로 보내며,
Peripheral에서 `RawCis::readFrame()`으로 받은 payload와 순서를 검사한다.
Zephyr의 ACL·CIG·ISO callback·HCI buffer는 library `.cpp`가 소유한다. 두 예제는
100 frame 송수신 후 명시적 `stop()`·자원 해제·재연결을 반복한다.

두 CMSIS-DAP V2 probe를 익명 SHA-256 mapping으로 확인하고 각 이미지에 sector
flash와 hardware reset을 수행했다. [원본 실행](evidence/m31-w02-public-cis-1d058140/public-cis-exact.json)은
두 보드가 출력한 Core revision과 clean source를 일치시켰다. 최종 reset 이후
**20회 × 중앙 송신 100 frame / 주변 수신 100 frame**, 주변 payload 오류 0,
부분 수신 0, 재시도 0으로 `PASS`다. Central FLASH 272,924 B·RAM 115,557 B,
Peripheral FLASH 272,036 B·RAM 115,554 B다.

[manifest](evidence/m31-w02-public-cis-1d058140/manifest.json)에 두 HEX SHA-256,
역할별 설정·runner hash와 원본 JSON hash를 묶었다. 첫 후보에서 한 번 정상 송신한
뒤 central scan과 ACL이 둘 다 꺼졌는데 오류가 0으로 남은 현상을 CMSIS-DAP
메모리 상태로 확인했다. 예상 밖 ACL 해제를 공개 오류로 전달하도록 수정하고
재시험했다. 중간 실행 두 건에서는 HCI `0x3e`(연결 설정 실패)가 한 차례씩 있었고
각각 약 4초 안에 완전한 다음 세션으로 복구했다. 그 실행은 무오류 20회 분자에
포함하지 않고 원본을 보존했다. 최종 runner는 마지막 부팅 revision 출력 전의
잔류 Serial 행도 별도로 보존·제외해 재설정 이전 출력을 세지 않는다.

이 결과는 W02의 공개 CIS central 송신/peripheral 수신 **두 역할**에 해당한다.
BIS source/receiver·암호화·time sync·세 보드 combined의 남은 9개 공개 예제는
여전히 시험용 `Program::begin()`/`poll()` 중심이므로 W02 전체는 진행 중이다.
기존 고정 SDU 무선 HIL은 유지하되 그 PASS를 새 공개 payload API 증거로
대체하지 않는다. CI/CD는 조회하지 않았다.
