# v0.6.0 지원 목표와 현재 검증 상태

**미공개 후보의 검증표**다. 현재 stable v0.5.0의 Windows 10/11 지원을 변경하지 않는다.
v0.6.0 목표 다섯 행 중 완료 근거가 있는 행은3개이며 Mac2개는 실기 `NOT_RUN`이다.

| 목표 OS·CPU | 검증한 실행 환경 | 보존된 근거 | 현재 판정·잔여 |
| --- | --- | --- | --- |
| Windows11 x64 | 사용자 Windows11; 제한 영향 검사는 Windows Server2025 CI | C5 설치·USB upload/runtime·serial·debug·재연결·IDE, C10/C11 공통 도구 영향 | 배정 검증 완료. CI를 새 Windows11 실기로 표시하지 않음 |
| Ubuntu24.04 LTS AMD64 | C5 native CI + C10 WSL2 사용자 환경 | C5 전체 빌드, C10 설치·대표4cold/4warm·USB/serial/debug·BLE·재연결·IDE | WSL2 기준선·변경 영향 완료. native 사용자 실기 `NOT_RUN` |
| Ubuntu26.04 LTS AMD64 | C10 WSL2 | 24.04 기준선에 연결한 설치·대표4cold/4warm·lifecycle·USB/serial/debug·IDE | WSL2 버전 호환성 완료. native 사용자 실기 `NOT_RUN`; 전체204·BLE·재연결 반복 없음 |
| macOS26 Apple Silicon | C11 CI 26.7.2 및 실기 준비 Mac 26.7.3 (25G342) ARM64 | C5 전체 빌드 보존, C11 CI 새 SDK 설치·lifecycle·대표4cold/4warm·관련 Host unit | software CI와 실제 Mac SDK·수명주기·대표 빌드·inventory PASS. USB·serial·debug·물리 재연결·IDE `NOT_RUN`. [335번](<../../04_검증 기록/335_HOST_W07_C11_macOS_26_SDK_설치와_대표_빌드.md>) |
| macOS27 Apple Silicon | C11 native CI, 실제27.0.1 ARM64 | C11 새 SDK 설치·lifecycle·대표4cold/4warm·관련 Host unit | software PASS. USB·serial·debug·물리 재연결·IDE `NOT_RUN` |

지원표 정본은 [host-readiness.json](../../../variants/nu54dk/host-readiness.json)의
`release_support_rows`와 `release_support_summary`다. C5·C10·C11은 서로 다른 source다.
위 연결은 기준선과 변경 영향의 검토이며 C11 동일-source 전체 시험 PASS가 아니다.
실제 source·run·attempt·artifact는 [Testing](TESTING.md)의 색인을 따른다.

## Mac 실기와 지원 확정

사용자 지시로 장비가 없는 동안 Mac 실기를 `NOT_RUN`으로 남기고 HOST-W08 문서 준비를 먼저 마쳤다.
이 결정은 Mac 실기 수락 처리나 다섯 OS 정식 지원 확정이 아니다. 현재 지원 목표를 유지하면
실제 Mac 검증 뒤 HOST-W07·HOST-W08과 M33-W07의 최종 gate를 마감한다.
Mac 지원을 후속으로 미루는 다른 공개 범위를 택하려면 별도의 범위 결정이 필요하며 현재 적용하지 않았다.

향후 준비물은 26·27을 각각 실행할 수 있는 Apple Silicon Mac 또는 같은 조건의 테스터,
NU54DK 한 대, CMSIS-DAP 데이터 USB 연결, IDE 사용 계정과 고정 SDK 설치 권한이다.
두 OS를 위해 Mac 두 대를 구입할 필요는 없다. BLE 두 보드 시험이 실제 배정될 때만 두 번째 NU54DK를 추가한다.
실기는 보존된 C11 kit로 필요한 장치·IDE 호환성을 확인하며 전체204를 반복하지 않는다.

## 범위 밖

Windows10은 v0.6.0 대상에서 제외했으며 이전 v0.5.0 지원 기록을 보존한다.
Linux ARM64·다른 Linux 배포판·Intel Mac·Rosetta·Windows on ARM·WSL1·판별 불명 WSL·container USB는
이번 지원 목표가 아니다. WSL2 USB PASS를 native Linux 실기로 바꾸지 않는다.
