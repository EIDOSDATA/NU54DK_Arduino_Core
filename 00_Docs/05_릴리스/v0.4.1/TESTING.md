# v0.4.1 Testing

## 유지보수 변경 검증

| 범위 | 완료 기준 |
| --- | --- |
| Installer regression | 복구 가능한 초기 실패와 최종 실패를 구분하고 Windows 경로 별칭을 동일 경로로 판정 |
| Host·문서 gate | 전체 자동 회귀 PASS |
| Target source build | 고정 NCS/Toolchain의 30개 예제 build PASS |
| Package reproducibility | exact commit에서 두 번 생성한 6개 package 자산의 byte 일치 |
| Stable catalog | public index에 `0.4.1` 하나만 존재 |
| Public install | 새 격리 Arduino data에서 `nucode:zephyr@0.4.1` 설치와 prerequisite 최종 PASS |
| Installed examples | 공개 설치본 예제 발견 30/30, clean compile 30/30 |

v0.4.1은 peripheral 기능을 변경하지 않으므로 v0.4.0에서 완료한 HIL을 새 기능 PASS로 다시
계상하지 않습니다. 설치기·package·source identity 변경은 software, package, 공개 설치본
회귀로 검증합니다. 정확한 commit, CI 실행, asset hash와 공개 설치 결과는 129번 검증 기록에
추가합니다.
