# v0.6.0 후보 설치 및 업로드 문제 해결

문제를 보고할 때는 소스 SHA, kit 해시, OS 버전과 아키텍처, 실패 단계, 종료 코드와 첫 오류 로그를 기록하세요.
다시 시도할 때는 새 실행 폴더를 사용하고 probe와 직렬 포트의 식별 정보는 해시로 남기세요.
로그를 공유하기 전에 비밀번호와 서명 키를 제거하세요.

## Mac IDE에서 YAML 오류가 뜰 때

C11에서 `Verify`는 성공해도 일반 `Upload`가 `E_RUNNER_UNAVAILABLE`로 중단되고 상세 메시지에 `No module named 'yaml'`가 표시될 수 있습니다. 이 경우에는 IDE가 probe를 선택하기 전에 패키지의 초기 Python 3.12.16이 runner 설정을 읽다가 중단된 것입니다.

1. 설치한 패키지의 `release-manifest.json`에서 `core_revision`을 확인합니다. `d304f369…`는 C11입니다. `0.6.0-rc.1` 표시는 C11과 C12에서 같습니다.
2. [후보 설치 안내](README.md)에 따라 C12를 설치하고 `core_revision`이 `97c7cd01ff59fb5ae3689e9de62b9c820b83fd5e`인지 확인합니다. C12는 runner 설정과 probe 열거에 SDK Python 3.12.4와 PyYAML 6.0.3을 사용합니다.
3. 실제 NU54DK 포트와 `Standard peripherals`를 선택하고 Blink에서 일반 **Upload**를 누릅니다. 정상 출력은 `NU54_UPLOAD_PASS`와 `Done uploading.`입니다. [338번 기록](<../../04_검증 기록/338_HOST_W07_macOS_27_Arduino_IDE_Upload_교정.md>)

C11을 재현하는 동안에는 kit에서 빌드한 Blink를 다음과 같이 올릴 수 있습니다. `WORK_ROOT`와 `PROBE_HASH`는 그 실행의 작업 경로와 현재 inventory에서 확인한 probe SHA-256을 사용하세요.

```sh
./START.sh --work-root "$WORK_ROOT" upload --example blink --probe-sha256 "$PROBE_HASH"
```

## 그 밖의 증상

| 환경·증상 | 확인 순서 |
| --- | --- |
| Boards Manager에 0.6.0이 없음 | 현재 공개 index는 0.5.0이다. 후보 kit 설치인지 확인한다. Git push만으로 배포되지 않음 |
| Windows 11에서 probe/COM이 바뀜 | 현재 장치를 다시 열거하고 hash를 확인한다. 과거 COM 번호로 장치를 추정하지 않는다. 여러 probe면 명시 UID를 사용한다 |
| WSL2에서 USB가 없음 | WSL VERSION2와 실제 usbipd 연결 상태를 확인하고 Linux에서 probe/serial을 다시 열거한다. 재연결 뒤 attach가 필요한지 확인한다 |
| WSL2 permission/build 경로 오류 | Linux 그룹/udev와 Linux 파일시스템의 SDK·cache 경로를 확인한다. `/mnt/d`의 Windows SDK/cache와 공유하지 않는다 |
| Mac 설치·실행 권한 오류 | Mac의 OS 버전과 아키텍처, kit 해시, 설치 권한, Gatekeeper 메시지를 기록한다. 보안 우회나 전역 권한 완화를 하지 않는다 |
| Mac process 정리 EPERM | C10 원형과 C11을 구분한다. C11에서도 실패하면 같은 PGID·시각·원래 오류를 새 attempt에 보존한다. 그룹 부재 확인 없이 PASS로 처리하지 않는다 |
| IDE Verify와 CLI 결과가 다름 | 후보의 소스 SHA, 보드, Feature set, 예제와 IDE 로그를 확인한다. 다른 source 설치본이나 IDE 창의 동시 빌드 혼입을 확인한다 |
| compile/runtime 실패 | 첫 오류가 설치, 빌드, 보드 연결, 실행 중 어디에서 발생했는지 확인한다. compile PASS와 실제 보드 동작은 별도 판정이다 |

구체적인 명령과 기대 출력은 [Host RC1 절차](<../../02_빌드 설계/15_Host_RC1_실기_도구와_증거_절차.md>),
고정 설치 입력은 [Nordic 환경 설치](<../../02_빌드 설계/12_Host별_고정_Nordic_환경_설치.md>)를 따른다.
macOS26의 실제 재연결은 기본 UART timeout 기록을 보존한 뒤 C11의 명시적 `--synchronize-line`을 선택해 통과했다. IDE 2.3.11은 현재 계정의 설정을 사용했고 CLI 실행 환경에서 후보 인덱스·데이터·캐시를 분리했다. [336번](<../../04_검증 기록/336_HOST_W07_C11_macOS_26_실기_검증과_재연결.md>)
