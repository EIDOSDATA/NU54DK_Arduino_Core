# v0.6.0 설치 및 업로드 문제 해결

| IDE에서 보이는 증상 | 먼저 확인할 항목 |
| --- | --- |
| Verify는 성공했는데 LED가 그대로임 | **Upload**까지 끝났는지 확인하세요. 보드 한 대만 연결하고 Blink의 두 지연 값을 바꿔 보면 새 코드가 올라갔는지 구별할 수 있습니다. [Blink 따라 하기](EXAMPLE_WALKTHROUGH.md) |
| 포트가 두 개 보이거나 직렬 모니터에 응답이 없음 | SerialEcho를 올리고 **115200 baud**, **Newline**으로 `test`를 보내세요. 두 포트 중 `NUCODE_M6_ECHO:test`를 돌려주는 쪽이 이 스케치의 콘솔입니다. [SerialEcho 실행 절차](EXAMPLE_WALKTHROUGH.md#2-serialecho로-한-줄-주고받기) |
| 예제의 BLE 또는 주변장치 초기화가 실패함 | 열린 IDE 창에서 권장 Feature set과 보드 역할을 확인하세요. 예제를 복사했다면 같은 폴더의 설정 파일도 있어야 합니다. [메뉴별 준비물](FEATURE_SETS.md) |

## Mac IDE에서 YAML 오류가 뜰 때

C11에서 `Verify`는 성공해도 일반 `Upload`가 `E_RUNNER_UNAVAILABLE`로 중단되고 상세 메시지에 `No module named 'yaml'`가 표시될 수 있습니다. 이 경우에는 IDE가 probe를 선택하기 전에 패키지의 초기 Python 3.12.16이 runner 설정을 읽다가 중단된 것입니다.

1. Boards Manager에 등록된 시험용 인덱스 URL을 제거합니다. 설치 목록에 `0.6.0-rc.1`이 남아 있다면 그 버전을 제거합니다.
2. [설치 안내](README.md)에 따라 공개 v0.6.0을 설치합니다. 설치본의 `release-manifest.json`에 있는 `core_revision`은 `0a63c501ccd0d2e26298f1ad98a81a99cddc565f`입니다. C12에서 확인한 SDK Python과 PyYAML 사용 수정이 포함됩니다.
3. 실제 NU54DK 포트와 `Standard peripherals`를 선택하고 Blink에서 일반 **Upload**를 누릅니다. 정상 출력은 `NU54_UPLOAD_PASS`와 `Done uploading.`입니다. [338번 기록](<../../04_검증 기록/338_HOST_W07_macOS_27_Arduino_IDE_Upload_교정.md>)

## 그 밖의 증상

| 환경·증상 | 확인 순서 |
| --- | --- |
| Boards Manager에 0.6.0이 없음 | [정식 인덱스 URL](README.md)이 추가됐는지 확인하고 Boards Manager 목록을 새로 고친다. 표시된 버전이 0.6.0인지 확인한다 |
| Windows 11에서 probe/COM이 바뀜 | 현재 장치를 다시 열거하고 hash를 확인한다. 과거 COM 번호로 장치를 추정하지 않는다. 여러 probe면 명시 UID를 사용한다 |
| WSL2에서 USB가 없음 | WSL VERSION2와 실제 usbipd 연결 상태를 확인하고 Linux에서 probe/serial을 다시 열거한다. 재연결 뒤 attach가 필요한지 확인한다 |
| WSL2 permission/build 경로 오류 | Linux 그룹/udev와 Linux 파일시스템의 SDK·cache 경로를 확인한다. `/mnt/d`의 Windows SDK/cache와 공유하지 않는다 |
| Mac 설치·실행 권한 오류 | Mac의 OS 버전과 아키텍처, kit 해시, 설치 권한, Gatekeeper 메시지를 기록한다. 보안 우회나 전역 권한 완화를 하지 않는다 |
| Mac process 정리 EPERM | C10 원형과 C11을 구분한다. C11에서도 실패하면 같은 PGID·시각·원래 오류를 새 attempt에 보존한다. 그룹 부재 확인 없이 PASS로 처리하지 않는다 |
| IDE Verify와 CLI 결과가 다름 | 후보의 소스 SHA, 보드, Feature set, 예제와 IDE 로그를 확인한다. 다른 source 설치본이나 IDE 창의 동시 빌드 혼입을 확인한다 |
| compile/runtime 실패 | 첫 오류가 설치, 빌드, 보드 연결, 실행 중 어디에서 발생했는지 확인한다. compile PASS와 실제 보드 동작은 별도 판정이다 |

문제를 보고할 때는 OS, IDE와 패키지 버전, 예제 이름, Feature set, 첫 오류 메시지를 적어 주세요. 개발용 kit를 재현할 때는 소스 SHA, kit 해시, 종료 코드도 함께 기록합니다.

구체적인 명령과 기대 출력은 [Host RC1 절차](<../../02_빌드 설계/15_Host_RC1_실기_도구와_증거_절차.md>),
고정 설치 입력은 [Nordic 환경 설치](<../../02_빌드 설계/12_Host별_고정_Nordic_환경_설치.md>)를 따른다.
macOS26의 실제 재연결은 기본 UART timeout 기록을 보존한 뒤 C11의 명시적 `--synchronize-line`을 선택해 통과했다. IDE 2.3.11은 현재 계정의 설정을 사용했고 CLI 실행 환경에서 후보 인덱스·데이터·캐시를 분리했다. [336번](<../../04_검증 기록/336_HOST_W07_C11_macOS_26_실기_검증과_재연결.md>)
