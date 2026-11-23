# v0.6.0 Host 문제 해결 — 비공개 후보

실패한 source·kit hash·OS/version/architecture·실행 단계·exit code와 원본 log를 먼저 보존한다.
새 attempt와 기존 FAIL을 구분하고, probe·serial identity는 비식별 hash로 수집한다.
비밀번호·서명 key·credential은 로그나 채팅에 남기지 않는다.

| 환경·증상 | 확인 순서 |
| --- | --- |
| Boards Manager에0.6.0이 없음 | 현재 공개 index는0.5.0이다. 후보 kit 설치인지 확인한다. Git push만으로 배포되지 않음 |
| Windows11에서 probe/COM이 바뀜 | 현재 장치를 다시 열거하고 hash를 확인한다. 과거 COM 번호로 장치를 추정하지 않는다. 여러 probe면 명시 UID를 사용한다 |
| WSL2에서 USB가 없음 | WSL VERSION2와 실제 usbipd 연결 상태를 확인하고 Linux에서 probe/serial을 다시 열거한다. 재연결 뒤 attach가 필요한지 확인한다 |
| WSL2 permission/build 경로 오류 | Linux 그룹/udev와 Linux 파일시스템의 SDK·cache 경로를 확인한다. `/mnt/d`의 Windows SDK/cache와 공유하지 않는다 |
| Mac 설치·실행 권한 오류 | 실제 OS/ARM64·고정 kit hash·설치 권한과 quarantine/Gatekeeper 메시지를 기록한다. 보안 우회나 전역 권한 완화를 하지 않는다 |
| Mac process 정리 EPERM | C10 원형과 C11을 구분한다. C11에서도 실패하면 같은 PGID·시각·원래 오류를 새 attempt에 보존한다. 그룹 부재 확인 없이 PASS로 처리하지 않는다 |
| IDE Verify와 CLI 결과가 다름 | 사용한 후보 package·board·feature set·예제와 IDE log를 확인한다. 다른 source 설치본이나 IDE 창의 동시 빌드 혼입을 확인한다 |
| C11 RC1 IDE Upload에서 `No module named 'yaml'` | IDE package의 격리 Python에서 runners.yaml을 읽을 PyYAML이 빠져 있다. C11 kit로 빌드한 대표 예제는 `START.sh --work-root <경로> upload --example blink --probe-sha256 <현재 inventory의 probe hash>`로 업로드한다. [337번](<../../04_검증 기록/337_HOST_W07_C11_macOS_27_실기_검증과_마감.md>) |
| compile/runtime 실패 | 설치·경로·build/cache·USB/probe·target/runtime 단계로 분리한다. compile PASS와 실제 보드 동작은 별도 판정이다 |

구체적인 명령과 기대 출력은 [Host RC1 절차](<../../02_빌드 설계/15_Host_RC1_실기_도구와_증거_절차.md>),
고정 설치 입력은 [Nordic 환경 설치](<../../02_빌드 설계/12_Host별_고정_Nordic_환경_설치.md>)를 따른다.
macOS26의 실제 재연결은 기본 UART timeout 기록을 보존한 뒤 C11의 명시적 `--synchronize-line`을 선택해 통과했다. IDE 2.3.11은 현재 계정의 설정을 사용했고 CLI 실행 환경에서 후보 인덱스·데이터·캐시를 분리했다. [336번](<../../04_검증 기록/336_HOST_W07_C11_macOS_26_실기_검증과_재연결.md>)
