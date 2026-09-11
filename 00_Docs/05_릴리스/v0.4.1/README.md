# NU54DK Arduino Core v0.4.1

`v0.4.1`은 `v0.4.0`의 보드 기능과 Arduino API를 그대로 유지하면서 Nordic prerequisite
설치 결과를 더 정확하게 표시하는 유지보수 릴리스입니다. **현재 설치·지원 대상은 v0.4.1
하나이며, 이전 stable·RC·preview는 지원하지 않고 stable Boards Manager 목록에서도
제공하지 않습니다.** 과거 tag·Release·자산·검증 기록은 재현성 감사를 위해 보존합니다.

| 항목 | 값 |
| --- | --- |
| 보드 | NU54DK v2, nRF54L15 application core |
| SDK | nRF Connect SDK v3.4.0 |
| Toolchain | `dcbdc366a1` |
| 설치 channel | Stable Boards Manager index |
| 지원 버전 | `0.4.1`만 지원 |
| 기능 기준선 | v0.4.0과 동일 |

## 설치

Arduino IDE의 Additional Boards Manager URLs에 다음 주소를 추가합니다.

```text
https://raw.githubusercontent.com/EIDOSDATA/NU54DK_Arduino_Core/main/package_nucode_nu54dk_index.json
```

Boards Manager에서 `NUCODE NU54DK Zephyr Boards`의 `0.4.1`을 설치합니다. 설치가 끝나면
`Nordic prerequisite installation PASS`와 검증 로그의 최종 성공 상태를 함께 확인하십시오.

## 문서

| 문서 | 내용 |
| --- | --- |
| [Release notes](RELEASE_NOTES.md) | v0.4.0 대비 변경점 |
| [Migration](MIGRATION.md) | 이전 설치에서 이동하는 방법 |
| [Testing](TESTING.md) | 검증 범위와 판정 기준 |
| [Troubleshooting](TROUBLESHOOTING.md) | 설치·빌드·실행 진단 |
| [Known issues](KNOWN_ISSUES.md) | 기능 지원 경계 |

## 기능 지원 경계

Profile, library 9개, 예제 30개와 nRF54L15 주변장치 지원 범위는 v0.4.0과 같습니다.
QDEC20/21은 기본 정·역회전과 SAMPLE/REPORT event 누산을 지원합니다. 반복 manual
`read()/clear` 무손실, 반복 Serial personality handover, 모든 주변장치 동시 조합, 정밀 ADC
정확도·jitter·음질·신호 무결성은 보증하지 않습니다.
