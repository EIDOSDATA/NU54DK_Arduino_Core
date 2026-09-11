# T20 RC 설치 수명주기와 실제 Upload

> 이 기록의 지원 상태·후보·다음 단계는 작성 당시 기준입니다. 이후 QDEC20/21 지원 범위와
> 영향 재검증은 [124번](124_T22전_QDEC_지원_범위_재확정.md), 최종 승인·공개·T24/T25 완료는
> [125번](125_v0.4.0_정식_릴리스_공개와_T24_T25_마감.md)에 있습니다. 당시 판정과 artifact identity는 그대로 보존합니다.

## 결론

**T20을 완료했습니다.** `b136c77ae5a00bb435fa6f0911539e689735414e`에서 만든
`0.4.0-rc.1`을 기존 Arduino 사용자 영역과 분리된 Boards Manager 환경에 설치해 예제
30/30 compile, 실제 CMSIS-DAP Upload, `0.3.0`과의 version 전환, 제거·재설치와
prerequisite 보존을 확인했습니다.

공개 tag·GitHub Release·stable index는 만들지 않았습니다. 다음 단계는 T20 결과가 반영된
exact commit에서 T21 RC/stable 후보를 다시 만들고 두 runtime payload가 같은지 검사하는
것입니다.

## 고정 입력과 설치 결과

| 항목 | 값 |
| --- | --- |
| Core commit | `b136c77ae5a00bb435fa6f0911539e689735414e` |
| Board submodule | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |
| RC archive | 2,632,092 bytes |
| RC archive SHA-256 | `19b7f65229509e34d7c9b970cbc1a60ff6da2e843527f3d5cdd8fba5088b29ca` |
| Runtime payload SHA-256 | `874de17c7c41b5a1bb1f8f7b2ec837fe74aceaa68c2d36bbf1b403e871e5c9b0` |
| NCS / Zephyr | `v3.4.0` / `bf801e4e3d19e1ffa76164346480cb7734dd2800` |
| Toolchain | `dcbdc366a1` |
| nRF Util | `8.2.1`, SHA-256 `22cb1bd03fc29016670c1fc8408a78bd213286ecc1156c70712485d77b097c75` |
| 설치 결과 | `nucode:zephyr@0.4.0-rc.1`, prerequisite `ready` |

Nordic의 공식 고정 URL이 같은 `8.2.1` version의 새 서명 binary를 제공해 기존 pin과 달랐습니다.
새 파일의 Authenticode 서명·version·commit을 확인하고 exact hash를 갱신한 뒤 fresh install을
다시 실행했습니다. Hash 검사를 끄거나 임의 byte를 허용하지 않았습니다.

## 설치본 예제와 Upload

설치본 발견 목록을 M27 lock과 대조한 뒤 library 9개, Sketch 30개를 각 profile로 clean
compile했습니다.

| 검사 | 결과 |
| --- | --- |
| 발견 목록 | 30/30 |
| clean compile | 30/30 PASS |
| 예제 증적 SHA-256 | `76ecd4a5fd9e400332b4f92a722631650693ccfe1a22dfb0a8b85655f43cdf74` |
| 대표 Sketch | 설치본 `NUCODE NU54DK / Blink`, `standard` profile |
| HEX SHA-256 | `1b9aee244728e9bc16f19cfa9d645cdc1b5cd000ff3a7b27539e98d62921742e` |
| Upload | pyOCD exact probe, PASS |
| 파괴 옵션 | mass erase `false`, recover `false`, smart flash `false` |
| 공개 Upload 로그 SHA-256 | `a94fc34d82241042d3b88830101c0bc93b1ca332ae5acaaba1f70dfd61ae7c18` |

첫 Upload의 `No ACK`는 기존 보드 firmware가 저전력 상태로 재진입해 일반 attach가 늦은
조건이었습니다. 두 CMSIS-DAP의 USB 열거와 100 kHz under-reset 연결을 분리해 확인했고,
under-reset 뒤 halt를 유지하자 일반 attach에서 두 보드 모두 CPUID `0x411fd210`을 읽었습니다.
같은 설치본 HEX를 다시 Upload해 PASS했습니다. SWD switch·GPIO 결선·Core firmware 결함으로
판정하지 않습니다.

한 재시도에서는 30개 병렬 build와 Upload build가 같은 cache root를 써 Upload context가
참조한 항목이 퇴출됐습니다. Upload 전용 cache root에서 HEX를 재생성해 최초 HEX와 byte가
같음을 확인하고 해결했습니다. 사용자 단일 compile→upload 경로의 실패가 아니라 시험 실행 간
cache 격리 문제입니다.

## Version 전환·제거·재설치

| 순서 | 결과 |
| --- | --- |
| `0.4.0-rc.1 → 0.3.0` | 설치 version 확인, 기존 prerequisite marker 보존 PASS |
| `0.3.0 → 0.4.0-rc.1` | 설치 version·현행 prerequisite 재검증 PASS |
| RC 제거 | Core 부재, `ready.json`과 NCS anchor byte 보존 PASS |
| RC 재설치 | version·prerequisite `ready` PASS |
| 재설치 후 발견 | M27 lock 기준 30/30 PASS |

과거 `0.3.0`의 post-install을 현행 Nordic URL로 새로 실행하지 않았습니다. 공개된 과거 package는
byte 불변이고 해당 package의 이전 nRF Util pin은 현재 같은 URL이 제공하는 새 byte와 다르므로,
version 전환은 package 설치 identity와 현행 RC 복귀를 검증했습니다. `v0.4.0`은 새 signed byte를
exact pin으로 포함합니다.

## 증적과 다음 단계

로컬 원본은 `C:\NU54CI\M27\t20-b136c77a`와 `C:\m27-t20-b136c77a`에 보존했습니다.
원시 probe UID는 공개 로그와 이 문서에 기록하지 않았습니다.

- T20 `boards_manager_lifecycle`: PASS
- 남은 기술 단계: T21 비공개 stable 이중 재현·RC runtime 동등성·stable 설치 검사
- 사람 승인: T22 이전에는 생성하거나 추정하지 않음
- 외부 공개: T23 이전에는 tag·Release·stable index를 쓰지 않음
