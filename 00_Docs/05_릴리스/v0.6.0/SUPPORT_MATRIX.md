# v0.6.0 지원 목표와 현재 검증 상태

**미공개 후보의 검증표**다. 현재 stable v0.5.0의 Windows 10/11 지원을 변경하지 않는다.
v0.6.0 목표 다섯 행에서 각각 배정된 검증을 완료했다.

| 목표 OS·CPU | 검증한 실행 환경 | 보존된 근거 | 현재 판정·잔여 |
| --- | --- | --- | --- |
| Windows11 x64 | 사용자 Windows11; 제한 영향 검사는 Windows Server2025 CI | C5 설치·USB upload/runtime·serial·debug·재연결·IDE, C10/C11 공통 도구 영향 | 배정 검증 완료. CI를 새 Windows11 실기로 표시하지 않음 |
| Ubuntu24.04 LTS AMD64 | C5 native CI + C10 WSL2 사용자 환경 | C5 전체 빌드, C10 설치·대표4cold/4warm·USB/serial/debug·BLE·재연결·IDE | WSL2 기준선·변경 영향 완료. native 사용자 실기 `NOT_RUN` |
| Ubuntu26.04 LTS AMD64 | C10 WSL2 | 24.04 기준선에 연결한 설치·대표4cold/4warm·lifecycle·USB/serial/debug·IDE | WSL2 버전 호환성 완료. native 사용자 실기 `NOT_RUN`; 전체204·BLE·재연결 반복 없음 |
| macOS26 Apple Silicon | C11 CI 26.7.2 및 실기 준비 Mac 26.7.3 (25G342) ARM64 | C5 전체 빌드 보존, C11 CI 새 SDK 설치·lifecycle·대표4cold/4warm·관련 Host unit | 배정 실기 완료. 사용자 승인 허브 경유, 첫 기본 UART FAIL 보존·명시적 줄 동기화 재연결과 IDE Verify PASS. [336번](<../../04_검증 기록/336_HOST_W07_C11_macOS_26_실기_검증과_재연결.md>) |
| macOS27 Apple Silicon | C11 native CI 27.0.1과 실제 Mac 27.2.1 (26B131) ARM64 | CI 새 SDK 설치, 실기 기존 고정 SDK 재검증·lifecycle·대표4cold/4warm·Blink·ELF debug·SerialEcho | 승인된 USB 허브로 물리 재연결 뒤 LF 동기화·첫 UART 6/6 및 IDE 2.3.11 Blink Verify PASS. [337번](<../../04_검증 기록/337_HOST_W07_C11_macOS_27_실기_검증과_마감.md>) |

지원표 정본은 [host-readiness.json](../../../variants/nu54dk/host-readiness.json)의
`release_support_rows`와 `release_support_summary`다. C5·C10·C11은 서로 다른 source다.
위 연결은 기준선과 변경 영향의 검토이며 C11 동일-source 전체 시험 PASS가 아니다.
실제 source·run·attempt·artifact는 [Testing](TESTING.md)의 색인을 따른다.

## 후속 검증과 지원 확정

사용자 지시에 따라 macOS26과 Ubuntu24.04의 기존 결과를 보존하고 해당 행을 반복하지 않는다.
후속 변경 영향 검증은 macOS27과 Ubuntu26.04 WSL2에서 필요한 범위만 수행한다.
정식 지원 범위는 최종 후보의 source·version·package·자산·공개 계획을 심사하는 HOST-W08과 M33-W07에서 확정한다.
