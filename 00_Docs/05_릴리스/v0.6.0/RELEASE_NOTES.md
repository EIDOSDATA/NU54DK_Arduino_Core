# v0.6.0 변경 사항

이번 릴리스는 NCS 3.4.0에서 BLE와 무선 예제를 확장하고 Windows, WSL2, Apple Silicon용 설치 및 검사 도구를 제공합니다. 정식 배포 소스와 자산 해시는 [340번 기록](<../../04_검증 기록/340_v0.6.0_정식_게시와_공개_설치_검증.md>)에서 확인할 수 있습니다.

## 기능과 예제

- M32에서 송신 전력, Path Loss, 연결 타이밍, 광고 및 identity 제어를 추가했습니다. Bluetooth Mesh, BLOB 전송, Mesh DFU, IEEE 802.15.4 및 ESB 단독 무선과 지정된 공존 조합을 포함합니다. 12개 작업을 완료했습니다. [M32 기능 범위](../../TODO_M32.md)
- M33의 W01부터 W05까지는 GATT 프로필, beacon, 외부 서비스용 companion, DTM/HCI 템플릿, 역할별 설치 예제를 다룹니다. 라이브러리 24개와 예제 204개의 빌드 기준선, 실제 보드에서 실행한 범위를 각각 기록했습니다. [M33 기능 및 예제 근거](../../TODO_M33.md)
- Host별 SDK 설치와 실행기, 캐시 경로 및 잠금, 패키지 CI, WSL2 USB 절차를 마련했습니다. C11은 macOS에서 정리 중 SIGKILL이 EPERM으로 반환됐을 때 실제 프로세스 그룹의 종료 여부를 확인합니다. [지원표](SUPPORT_MATRIX.md)

## Mac에서 달라진 점

C11에서는 macOS 26과 27에서 CMSIS-DAP 업로드, ELF 디버그, SerialEcho, USB 케이블 재연결, Arduino IDE의 Blink Verify를 검증했습니다. macOS 27에서 IDE의 일반 Upload는 runner 설정을 읽다가 PyYAML을 찾지 못해 중단됐습니다.

C12는 runner 설정 확인과 probe 열거에 고정된 Nordic SDK Python을 사용합니다. macOS 27.2.1과 IDE 2.3.11에서 일반 Upload가 완료됐고 온보드 LED 점멸도 확인했습니다. 두 후보의 표시 버전은 같습니다. [후보별 소스와 검증 결과](TESTING.md), [338번 기록](<../../04_검증 기록/338_HOST_W07_macOS_27_Arduino_IDE_Upload_교정.md>)

## 사용자에게 알려야 할 경계

M33-W06은 **실제 PASS 46건과 사용자 수락 3건(#29, #40, #44)**으로 마감했다. 49개 기술 PASS가 아니며
해당 FAIL·집계 원형은 [310번](<../../04_검증 기록/310_M33_W06_사용자_수락_마감_완료.md>),
#40·44의 별도 명시 수락과 판단 정정은 [311번](<../../04_검증 기록/311_M33_W06_명시_수락_정정과_HOST_W04_착수.md>)에 보존한다.
#29 원인 분석은 유예한다. 이 예외를 새로운 source의 PASS로 옮기지 않는다.

Apple/Google·외부 제품·외장 장치의 실제 interop는 사용자 후속 `NOT_RUN`이다.
자동 scripted peer 결과는 제품 인증이나 실제 외부 제품 상호운용 보증이 아니다.
실험적 프로필과 템플릿은 예제별 설정, 자격 증명, 상대 장치와 결선 조건을 따른다.
NCS 3.4.0과 고정 toolchain을 유지하며 이번 릴리스 준비에서 SDK를 교체하지 않는다.

API/profile 이동과 opt-in은 [Migration](MIGRATION.md), 제한은 [Known issues](KNOWN_ISSUES.md)를 따른다.
