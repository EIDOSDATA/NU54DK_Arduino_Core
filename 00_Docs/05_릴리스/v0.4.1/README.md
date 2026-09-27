# NU54DK Arduino Core v0.4.1

> **보존 문서·지원 종료:** 현재 정식 설치·지원 버전은 [v0.5.0](../v0.5.0/README.md) 하나입니다.
> 아래 지원 범위·설치 명령·검증 결과·예정 작업은 `v0.4.1` 작성 당시의 기록이며 현행 설치 안내가 아닙니다.
> 이 버전은 지원·stable catalog 공급 대상이 아니며, 당시 판정·source·자산 식별값은 보존합니다.

`v0.4.1`은 `v0.4.0`의 보드 기능과 Arduino API를 그대로 유지하면서 Nordic prerequisite
설치 결과를 더 정확하게 표시한 유지보수 릴리스입니다. 공개 당시 정식 설치·지원 대상과
stable Boards Manager 공급을 v0.4.1 하나로 전환했습니다. 이후 정식 v0.5.0 공개로
v0.4.1의 지원·catalog 공급을 종료했으며, 과거 tag·Release·자산·검증 기록은 보존합니다.

| 항목 | 값 |
| --- | --- |
| 보드 | NU54DK v2, nRF54L15 application core |
| Board/FQBN | `nucode:zephyr:nu54dk` |
| 공식 사용자 OS | Windows 10/11 x64 |
| SDK | nRF Connect SDK v3.4.0 |
| Toolchain | `dcbdc366a1` |
| 당시 설치 channel | Stable Boards Manager index |
| 당시 정식 지원 버전 | `0.4.1` 단독; 현재는 지원·catalog 공급 종료 |
| 기능 기준선 | v0.4.0과 동일 |

공개 source·ZIP·checksum의 고정 identity와 설치 검증 결과는
[129번 기록](<../../04_검증 기록/129_v0.4.1_설치기_유지보수_릴리스.md>)에서 확인합니다.
후속 제품선에서 완료한 M28~M31 BLE 확장과 RC2 사용자 경험 교정은 이 설치 패키지에 포함되지
않습니다. 개발 소스의 지원 범위와 v0.5.0 상태는 [개발 TODO](../../TODO_v0.5.0.md)와
[RC2 실행 기록](../../TODO_v0.5.0-RC2.md)을 따릅니다.

## 당시 설치 절차

현재 index에서는 `0.4.1`을 선택할 수 없습니다. 신규 설치는 [v0.5.0 설치 안내](../v0.5.0/README.md)를 따릅니다.

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
