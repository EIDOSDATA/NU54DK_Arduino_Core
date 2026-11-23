# v0.6.0 설치 안내

**v0.6.0**은 공개 stable 버전입니다. 소스는 `0a63c501ccd0d2e26298f1ad98a81a99cddc565f`이고, NCS 3.4.0과 라이브러리 24개, 예제 204개를 제공합니다. [GitHub Release](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/releases/tag/v0.6.0), [OS별 지원 및 검증](SUPPORT_MATRIX.md)

1. macOS는 `Arduino IDE > Settings`, Windows와 Linux는 `File > Preferences`를 열고 **Additional Boards Manager URLs**에 아래 주소를 등록합니다.
2. Boards Manager에서 **NUCODE NU54DK Zephyr Boards 0.6.0**을 설치합니다. 초기 Python과 Nordic SDK가 설치되므로 첫 설치에는 다운로드 시간이 필요합니다.
3. `NU54DK (nRF54L15, Zephyr)`와 연결된 보드의 포트를 선택합니다. `Standard peripherals`에서 Blink를 Verify한 뒤 Upload합니다. [빠른 시작](../../../README.md#빠른-시작)

```text
https://raw.githubusercontent.com/EIDOSDATA/NU54DK_Arduino_Core/main/package_nucode_nu54dk_index.json
```

설치본의 `release-manifest.json`에 제품 소스 SHA가 들어 있습니다. 릴리스 기록은 `Release-0.6.0` 브랜치에 있습니다. macOS 27에서 공개 설치, 대표 빌드와 제거 후 재설치를 확인했습니다. [340번 기록](<../../04_검증 기록/340_v0.6.0_정식_게시와_공개_설치_검증.md>)

[변경 사항](RELEASE_NOTES.md) · [버전 전환](MIGRATION.md) · [알려진 제한](KNOWN_ISSUES.md) · [문제 해결](TROUBLESHOOTING.md)
