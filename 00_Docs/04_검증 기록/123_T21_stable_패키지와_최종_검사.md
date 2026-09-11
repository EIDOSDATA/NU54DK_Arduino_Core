# T21 stable 패키지와 최종 검사

> 이 기록의 지원 상태·후보·다음 단계는 작성 당시 기준입니다. 이후 QDEC20/21 지원 범위와
> 영향 재검증은 [124번](124_T22전_QDEC_지원_범위_재확정.md), 최종 승인·공개·T24/T25 완료는
> [125번](125_v0.4.0_정식_릴리스_공개와_T24_T25_마감.md)에 있습니다. 당시 판정과 artifact identity는 그대로 보존합니다.

## 결론

**T21을 완료했습니다.** 비공개 `0.4.0-rc.1`과 `0.4.0` 후보를 각각 두 번 생성해
재현성을 확인했고, 정규화한 runtime payload가 같음을 확인했습니다. 격리 Boards Manager에
stable을 설치해 예제 30/30 clean compile과 실제 CMSIS-DAP Upload도 통과했습니다.

공개 tag·GitHub Release·stable index는 만들지 않았습니다. 남은 차단 항목은 T22 프로젝트
소유자의 명시적 공개 승인뿐이며, 승인 전에는 T23 게시 명령을 실행하지 않습니다.

## 소스와 최종 후보

T21 runtime 검사는 `9e9bbf9ab96bee9ee3d6b7b506d5590cff5d9db2`를 기준으로 수행했습니다.
이후 변경은 설치 stable 예제 실행기·계약 테스트, 이 기록을 포함한 문서와 release-readiness
근거 갱신입니다. 예비·최종 archive를 비교한 결과 설치 payload에서 달라진 원본은 패키지에 포함된
`variants/nu54dk/v0.4.0-release-readiness.json`뿐이며 실행 코드·라이브러리·보드 정의는 같습니다.
최종 문서 commit의 authoritative identity와 artifact hash는 다음 로컬 plan에 보존합니다.

- RC plan: `C:\m27-t21-authoritative-rc\m27-release-plan.json`
- Stable plan: `C:\m27-t21-authoritative-stable\m27-stable-release-plan.json`

최종 plan은 clean local `HEAD`와 `origin/main`이 같은 상태에서 다시 생성·검증합니다. Stable
plan은 모든 비인간 gate를 PASS로 판정하되 `project_owner_approval` 하나 때문에 게시를 HOLD합니다.

## 회귀와 패키지 재현성

| 검사 | 결과 |
| --- | --- |
| M12 Host | PASS. LLVM/Clang 22 Windows host 실행 |
| 계약 검사 | 46/46 PASS |
| Inventory | PASS. 남은 blocker는 human approval 1개 |
| 문서 검사 | 249/249 PASS |
| Target | 35/35 PASS. T19 runtime 이후 source 변경 없음 |
| RC package | 독립 2회 byte-identical |
| Stable package | 독립 2회 byte-identical |
| RC/Stable runtime | 동일, SHA-256 `0883219f9ea96ca82f41a6056f9966b108619aac26c8029645a47f091fde9cd3` |

이 fingerprint는 `platform.txt`의 version만 정규화하고 readiness를 포함한 전체 설치 payload를
해시합니다. 따라서 예비 후보의 fingerprint와 달라졌지만 archive 비교로 readiness 근거 갱신만
차이임을 확인했고, 같은 최종 commit의 RC와 stable은 정확히 일치합니다.

GCC 16의 Windows PE-COFF weak hook 차이는 host 기본 hook을 보완해 해결했습니다. 이후 Windows
Smart App Control이 새로 링크한 일부 unsigned GCC host 실행 파일을 차단해, 같은 host gate를
설치된 LLVM/Clang 22로 실행했습니다. Code Integrity 이벤트로 환경 정책임을 확인했으며 target
firmware 결함으로 분류하지 않습니다.

## Stable 설치본 예제와 실제 Upload

격리 Arduino data root `C:\NU54CI\M27\t21-9e9bbf9a`에 `nucode:zephyr@0.4.0`을
설치했습니다. 설치 후 prerequisite marker는 NCS `v3.4.0`, toolchain `dcbdc366a1`, nRF Util
`8.2.1`을 가리켰습니다.

| 검사 | 결과 |
| --- | --- |
| 설치본 발견 목록 | 30/30 |
| Clean compile | 30/30 PASS |
| 증거 유형 | `installed-stable-package-examples` |
| 금지한 개발 저장소 경로 누출 | 없음 |
| 예제 증적 SHA-256 | `aa6495f038bfdbad00265dbcabd18152ef3dfc07ba4cd1d7cad3d30bb09f4998` |
| 대표 Sketch | 설치본 `NUCODE NU54DK / Blink`, `standard` profile |
| HEX SHA-256 | `1b9aee244728e9bc16f19cfa9d645cdc1b5cd000ff3a7b27539e98d62921742e` |
| Upload | pyOCD exact probe, PASS |
| 파괴 옵션 | mass erase `false`, recover `false`, smart flash `false` |
| 공개 Upload 로그 SHA-256 | `96d479192db60aef0ed7d8f27a147701fc1e86f54acc42224806de1da307bcfc` |
| 공개 flash 로그 SHA-256 | `b9ac05a4f0f414e75db66495dd2fc10661233944d71142d10a544dfceca65870` |

원시 probe UID는 공개 로그와 문서에 기록하지 않았습니다. 이번 단계에서는 기존 기능 HIL이나
S/U 결선을 반복하지 않았고, 설치 stable의 대표 firmware를 한 보드에 sector erase 방식으로
Upload했습니다.

## 완료 상태와 다음 단계

- T21 기술 gate: **완료**
- 발견된 미해결 Core 결함: **0건**
- T22 `project_owner_approval`: **HOLD — 프로젝트 소유자의 명시적 승인 필요**
- T23 tag·Release·stable index: **미실행**
- T24 공개 URL 설치 검증: **미실행 — T23 이후**
- T25 공개 결과 문서·CI·임시 출력 정리: **미실행 — T23~T24 이후**
