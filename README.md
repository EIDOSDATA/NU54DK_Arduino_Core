# NU54DK Arduino Core

NU54DK의 nRF54L15 애플리케이션 코어(CPUAPP)에서 Arduino 스케치를 실행합니다. 스케치와 라이브러리를 고정된 nRF Connect SDK(NCS) 3.4.0으로 빌드하고, 보드에 내장된 CMSIS-DAP으로 업로드합니다.

## 버전 선택

**현재 stable은 v0.6.0**입니다. 라이브러리 24개, 예제 204개와 빌드 레시피 29개를 포함합니다. Windows 11 x64, Ubuntu 24.04 및 26.04 LTS AMD64(WSL2 실기), macOS 26 및 27 Apple Silicon의 검증 범위는 지원표에서 확인하세요. [설치 안내](<00_Docs/05_릴리스/v0.6.0/README.md>), [OS별 지원표](<00_Docs/05_릴리스/v0.6.0/SUPPORT_MATRIX.md>), [GitHub Release](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/releases/tag/v0.6.0)

## 빠른 시작

1. Arduino IDE의 **Additional Boards Manager URLs**에 stable 인덱스를 추가합니다. Boards Manager에서 **NUCODE NU54DK Zephyr Boards 0.6.0**을 설치합니다. [stable 인덱스](https://raw.githubusercontent.com/EIDOSDATA/NU54DK_Arduino_Core/main/package_nucode_nu54dk_index.json), [설치 안내](<00_Docs/05_릴리스/v0.6.0/README.md>)
2. 데이터 통신용 USB 케이블로 NU54DK 한 대를 연결합니다. Arduino IDE에서 보드 `NU54DK (nRF54L15, Zephyr)`와 현재 보드의 직렬 포트를 선택합니다. `Tools > Feature set`은 `Standard peripherals`, `Upload probe`는 기본 CMSIS-DAP 설정을 사용합니다.
3. `File > Examples > NUCODE NU54DK > Blink`에서 **Verify**를 누른 뒤 **Upload**를 누릅니다. 출력 창에 `Done uploading.`이 표시되고 온보드 LED가 250 ms마다 바뀌면 동작을 확인한 것입니다. [Blink 소스](libraries/NUCODE_NU54DK/examples/Blink/Blink.ino)
4. UART를 확인하려면 같은 설정으로 `SerialEcho`를 업로드합니다. 보드의 DAP UART 포트를 115200 8N1로 열고 Serial Monitor의 줄 끝을 `Newline`으로 설정하세요. `test`를 보내면 `NUCODE_M6_ECHO:test`가 돌아옵니다. 여러 보드를 연결했다면 현재 열거한 probe와 포트의 대응을 확인합니다. [SerialEcho](libraries/NUCODE_NU54DK/examples/SerialEcho/SerialEcho.ino), [업로드와 디버그](<00_Docs/02_빌드 설계/05_업로드와_디버그.md>)

**Mac에서 업로드 중 YAML 오류가 뜨면** Boards Manager의 설치 버전을 먼저 확인하세요. [일반 Upload 문제 해결](<00_Docs/05_릴리스/v0.6.0/TROUBLESHOOTING.md>)

## 내 스케치에 맞는 예제 찾기

| 하고 싶은 일 | 어디서 시작하나요? |
| --- | --- |
| 보드 한 대로 LED를 켜고 PC와 문자 주고받기 | [Blink와 SerialEcho 코드 따라 하기](<00_Docs/05_릴리스/v0.6.0/EXAMPLE_WALKTHROUGH.md>) |
| 보드 두 대로 BLE 메시지 보내기 | [NUSPeripheral과 NUSCentral 연결하기](<00_Docs/05_릴리스/v0.6.0/EXAMPLE_WALKTHROUGH.md#3-보드-두-대로-ble-메시지-보내기>) |
| Tools 메뉴에서 내 기능에 맞는 설정 고르기 | [Feature set 12개 비교와 대표 예제](<00_Docs/05_릴리스/v0.6.0/FEATURE_SETS.md>) |
| Mesh, 센서, 오디오 등 다른 예제 찾기 | [204개 예제 색인](libraries/EXAMPLES.md), [커넥터 핀맵](<00_Docs/01_아두이노 코어 설계/13_NU54DK_P2_P4_커넥터_핀맵.md>), [알려진 제한](<00_Docs/05_릴리스/v0.6.0/KNOWN_ISSUES.md>) |

## 문서

- [v0.6.0 변경 사항](<00_Docs/05_릴리스/v0.6.0/RELEASE_NOTES.md>), [버전 전환 안내](<00_Docs/05_릴리스/v0.6.0/MIGRATION.md>)
- [검증한 소스와 결과](<00_Docs/05_릴리스/v0.6.0/TESTING.md>), [정식 배포 및 공개 설치 기록](<00_Docs/05_릴리스/v0.6.0/RELEASE_CHECKLIST.md>)
- [문서 목차](00_Docs/README.md), [개발 인계](00_Docs/HANDOFF.md), [기여 및 검사 방법](CONTRIBUTING.md)

## 문제 보고와 기여

문제를 보고할 때는 OS와 아키텍처, IDE 또는 CLI 버전, 설치한 패키지의 버전과 소스 SHA, 예제와 Feature set, 첫 오류 로그를 함께 적어 주세요. 장치 문제는 보드 수와 연결 방식도 도움이 됩니다. 로그에서 인증 정보와 원시 probe UID를 제거한 뒤 제출해 주세요. [GitHub Issues](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/issues)

## 작성자와 라이선스

NUCODE의 Quantum이 개발합니다. NUCODE 작성 코드에는 MIT 라이선스를 적용합니다. [라이선스](LICENSE), [외부 구성요소 고지](third_party/THIRD_PARTY_NOTICES.md)
