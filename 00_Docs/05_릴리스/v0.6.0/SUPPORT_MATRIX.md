# v0.6.0 후보의 OS별 지원 검증

다섯 목표 환경에서 배정한 검증을 완료했습니다. 이 표에서 WSL2는 Windows의 Linux 게스트이고, CI는 자동 실행 환경입니다. 정식 지원 범위는 최종 배포 후보 심사에서 확정합니다.

| 목표 OS | 검증 환경과 소스 | 실제로 확인한 범위 |
| --- | --- | --- |
| Windows 11 x64 | 사용자 PC, C5 | 설치, USB 업로드와 실행, 직렬 통신, 디버그, USB 재연결, IDE. 공통 도구 변경의 일부는 Windows Server 2025 CI에서 별도로 검사했습니다. [329번 기록](<../../04_검증 기록/329_M33_W07_v0.6.0_OS_지원_범위와_Windows11_진행.md>) |
| Ubuntu 24.04 LTS AMD64 | native CI(C5), 사용자 WSL2(C10) | CI 전체 빌드. WSL2에서 설치, 대표 cold/warm 빌드, USB, 직렬 통신, 디버그, BLE, 물리 재연결, IDE를 확인했습니다. native 사용자 실기는 `NOT_RUN`입니다. [330번 기록](<../../04_검증 기록/330_HOST_W07_C6_WSL2_지원과_Ubuntu24.04_검증.md>) |
| Ubuntu 26.04 LTS AMD64 | 사용자 WSL2, C10 | 설치 수명주기, 대표 cold/warm 빌드, 한 보드의 USB, 직렬 통신, 디버그, IDE. 전체 204개 빌드, BLE, 재연결은 24.04 기준선을 적용했습니다. native 사용자 실기는 `NOT_RUN`입니다. [330번 기록](<../../04_검증 기록/330_HOST_W07_C6_WSL2_지원과_Ubuntu24.04_검증.md>) |
| macOS 26 Apple Silicon | C11 CI 26.7.2, 실제 Mac 26.7.3 (25G342) | 승인된 USB 허브에서 Blink, 디버그, 직렬 통신, IDE Verify를 확인했습니다. 물리 재연결 뒤 기본 설정의 첫 UART 응답은 시간 초과였고, 줄 동기화를 명시한 새 시도는 통과했습니다. [336번 기록](<../../04_검증 기록/336_HOST_W07_C11_macOS_26_실기_검증과_재연결.md>) |
| macOS 27 Apple Silicon | C11 CI 27.0.1, 실제 Mac 27.2.1 (26B131) | C11의 대표 빌드, Blink, 디버그, SerialEcho, 물리 재연결 후 LF 동기화와 UART 6/6, IDE Verify가 통과했습니다. 같은 실제 Mac에서 C12의 일반 IDE Upload와 LED 동작을 확인했습니다. [337번 기록](<../../04_검증 기록/337_HOST_W07_C11_macOS_27_실기_검증과_마감.md>), [338번 기록](<../../04_검증 기록/338_HOST_W07_macOS_27_Arduino_IDE_Upload_교정.md>) |

Mac 두 행의 BLE 두 보드 검증은 배정 범위 밖으로 `NOT_RUN`입니다. 이 표의 C10 Ubuntu 24.04 WSL2 결과에 두 보드 실기 근거가 있습니다.

## 후속 검증

최종 버전 후보의 macOS 27 설치 전이와 대표 빌드 결과는 [339번 기록](<../../04_검증 기록/339_HOST_W08_v0.6.0_최종_후보와_배포_자산_준비.md>)에 있습니다.

macOS 26과 Ubuntu 24.04의 결과는 보존합니다. 앞으로 해당 계열의 변경 영향은 macOS 27과 Ubuntu 26.04 WSL2에서 필요한 범위만 확인합니다. 각 행의 소스와 실행 기록은 [검증 근거](TESTING.md), 기계 판독용 상태는 [Host 원장](../../../variants/nu54dk/host-readiness.json)의 `release_support_rows`와 `release_support_summary`에서 확인할 수 있습니다.
