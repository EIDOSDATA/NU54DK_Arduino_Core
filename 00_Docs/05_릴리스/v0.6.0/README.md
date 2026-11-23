# v0.6.0 후보 사용 안내

이 브랜치의 v0.6.0은 비공개 검증 후보입니다. 공개 Boards Manager 인덱스에서 설치할 수 있는 버전은 Windows용 [v0.5.0](../v0.5.0/README.md)입니다.

## 어떤 후보를 사용했나

| 후보 | 제품 소스 | 검증한 범위 |
| --- | --- | --- |
| C5 | `5ee7c10368b554ca23d68f8f82e39308b91df6de` | 세 OS의 전체 예제 빌드 기준선과 Windows 11 실기 |
| C10 | `4890f697ab80dfed3cff62bd42acc42b0f3e1a34` | Ubuntu 24.04 및 26.04 LTS의 WSL2 환경 |
| C11 | `d304f369c0d3ebbac35c3bf0ef3b7b2887f40dfa` | macOS 26 및 27의 설치, 대표 빌드, USB, 디버그, UART 재연결, IDE Verify |
| C12 | `97c7cd01ff59fb5ae3689e9de62b9c820b83fd5e` | macOS 27.2.1의 일반 IDE Upload 수정과 Blink 동작 |

C11과 C12는 모두 `0.6.0-rc.1`로 표시됩니다. 전달받은 kit는 `kit-manifest.json`의 `source_revision`, 설치본은 `release-manifest.json`의 `core_revision`으로 구별합니다. 문서를 읽는 브랜치 HEAD와 각 제품 소스 SHA는 독립적으로 확인하세요.

## 후보로 시작하기

1. 검증용 kit와 체크섬을 받았으면 원본 아카이브의 SHA-256을 대조합니다. C12 Mac kit의 SHA-256은 `db339b02d308e74e13c5ee98b3185ca11d341c9ac6ebc3fc7e06cc5cc80d727e`입니다. [C11 전달 자료](../../MAC_HANDOFF.md), [C12 패키지와 kit 기록](<../../04_검증 기록/338_HOST_W07_macOS_27_Arduino_IDE_Upload_교정.md>)
2. kit를 풀고 새 작업 폴더를 준비합니다. `START.sh`(macOS/Linux) 또는 `START.cmd`(Windows)의 `plan`으로 고정 입력을 확인합니다. NCS는 3.4.0이며 Mac의 SDK 루트는 `/opt/nordic/ncs`, toolchain bundle은 `ccc010f809`입니다.
3. `install-sdk`로 설치 또는 기존 SDK 재검증을 진행하고, `lifecycle`로 후보 패키지를 설치합니다. `build`로 대표 예제를 빌드하고 `inventory`로 현재 보드와 포트를 확인합니다. 옵션과 예시는 [OS별 RC1 절차](<../../02_빌드 설계/15_Host_RC1_실기_도구와_증거_절차.md>)를 따릅니다.
4. IDE를 사용할 때는 아래 절차로 Boards Manager에도 후보를 설치합니다. 설치한 소스를 확인한 뒤 Blink를 Verify하고 Upload합니다. YAML 오류가 나면 설치본의 소스부터 확인하세요. [Blink 빠른 시작](../../../README.md#빠른-시작), [문제 해결](TROUBLESHOOTING.md)

## Mac Arduino IDE에 후보 설치하기

`lifecycle`은 격리된 Arduino CLI에 설치한 후 임시 서버를 종료합니다. IDE의 Boards Manager는 별도로 설정해야 합니다. 아래 명령은 성공한 lifecycle 실행의 미러와 그 인덱스에 기록된 포트를 그대로 사용하는 방법입니다.

1. 터미널에서 `<작업 경로>/attempts/lifecycle-<실행 시각>/lifecycle/mirror` 폴더로 이동합니다. 다음 명령은 로컬 인덱스에서 포트를 읽고 IDE에 붙여 넣을 URL을 출력합니다. 이 터미널은 설치가 끝날 때까지 열어 두세요.

   ```sh
   INDEX=package_nucode_nu54dk_host_index.json
   PORT=$(python3 -c 'import json, sys; from urllib.parse import urlsplit; print(urlsplit(json.load(open(sys.argv[1]))["packages"][0]["platforms"][0]["url"]).port)' "$INDEX")
   echo "http://127.0.0.1:$PORT/$INDEX"
   python3 -m http.server "$PORT" --bind 127.0.0.1
   ```

2. Arduino IDE에서 `Arduino IDE > Settings > Additional Boards Manager URLs`에 출력된 URL을 추가합니다. Boards Manager에서 **NUCODE NU54DK Zephyr Boards**의 `0.6.0-rc.1`을 설치합니다. C11이 같은 버전으로 설치돼 있으면 그 코어를 제거한 뒤 C12 인덱스로 다시 설치하세요. 두 후보의 인덱스가 함께 등록돼 있다면 C11 URL을 목록에서 제외합니다.
3. IDE가 사용하는 설치본의 `release-manifest.json`에서 위 표의 C12 SHA를 확인합니다. 설치가 끝나면 서버 터미널에서 `Ctrl+C`를 누릅니다. 대표 보드와 포트를 고르고 Blink로 정상 Upload를 확인하세요.

## 검증과 릴리스 상태

다섯 OS 목표 행의 배정 검증을 완료했습니다. Host 작업은 8개 중 7개가 끝났고, 마지막 HOST-W08에는 최종 배포 후보의 식별자, 자산, 재현성, 변경 영향 심사가 남았습니다. M33은 수락 6/8, 기술 완료 5/8입니다. [지원표](SUPPORT_MATRIX.md), [검증 근거](TESTING.md), [배포 체크리스트](RELEASE_CHECKLIST.md)

기능과 예제를 선택할 때는 [변경 사항](RELEASE_NOTES.md), [설치 및 프로필 전환](MIGRATION.md), [알려진 제한](KNOWN_ISSUES.md)을 참고하세요.
