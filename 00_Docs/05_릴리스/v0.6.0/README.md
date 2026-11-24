# v0.6.0 설치 안내

**v0.6.0**은 공개 stable 버전입니다. 소스는 `0a63c501ccd0d2e26298f1ad98a81a99cddc565f`이고, NCS 3.4.0과 라이브러리 24개, 예제 204개를 제공합니다. [GitHub Release](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/releases/tag/v0.6.0), [OS별 지원 및 검증](SUPPORT_MATRIX.md)

1. macOS는 `Arduino IDE > Settings`, Windows와 Linux는 `File > Preferences`를 열고 **Additional Boards Manager URLs**에 아래 주소를 등록합니다.

   ```text
   https://raw.githubusercontent.com/EIDOSDATA/NU54DK_Arduino_Core/main/package_nucode_nu54dk_index.json
   ```

2. Boards Manager에서 **NUCODE NU54DK Zephyr Boards 0.6.0**을 설치합니다. 초기 Python과 Nordic SDK가 설치되므로 첫 설치에는 다운로드 시간이 필요합니다.
3. 데이터 통신용 USB 케이블로 보드 한 대를 연결합니다. 보드는 **NU54DK (nRF54L15, Zephyr)**, 포트는 연결한 보드의 직렬 포트를 선택합니다.

Linux에서 첫 업로드에 `E_PROBE_NONE` 또는 `E_LOCK_PERMISSION`이 표시되면 USB 권한과 잠금 경로를 확인하세요. [Linux 업로드 문제 해결](TROUBLESHOOTING.md#linux에서-업로드-오류가-날-때)

## 설치한 다음

1. LED를 켜 보고 싶으면 **Tools > Feature set > Standard peripherals**를 선택하세요. Blink 업로드, 점멸 속도 바꾸기, 직렬 모니터로 한 줄 주고받기를 순서대로 설명합니다. [첫 예제 따라 하기](EXAMPLE_WALKTHROUGH.md)
2. BLE나 외장 장치를 쓰려면 IDE 메뉴 이름으로 설정을 찾아보세요. 프로필마다 필요한 보드 수와 확인할 결과가 다릅니다. [Feature set 선택 안내](FEATURE_SETS.md)
3. 다른 스케치를 찾으려면 라이브러리별 목록을 열고 이름을 선택하세요. [예제 색인](../../../libraries/EXAMPLES.md)

## 배포 정보

설치본의 `release-manifest.json`에 제품 소스 SHA가 들어 있습니다. 릴리스 기록은 `Release-0.6.0` 브랜치에 있습니다. macOS 27에서 공개 설치, 대표 빌드와 제거 후 재설치를 확인했습니다. [340번 기록](<../../04_검증 기록/340_v0.6.0_정식_게시와_공개_설치_검증.md>)

[변경 사항](RELEASE_NOTES.md) · [버전 전환](MIGRATION.md) · [알려진 제한](KNOWN_ISSUES.md) · [문제 해결](TROUBLESHOOTING.md)
