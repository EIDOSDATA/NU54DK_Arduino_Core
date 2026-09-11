# T15 지원 범위와 Physical Gate 확정

> 이 기록의 지원 상태·후보·다음 단계는 작성 당시 기준입니다. 이후 QDEC20/21 지원 범위와
> 영향 재검증은 [124번](124_T22전_QDEC_지원_범위_재확정.md), 최종 승인·공개·T24/T25 완료는
> [125번](125_v0.4.0_정식_릴리스_공개와_T24_T25_마감.md)에 있습니다. 당시 판정과 artifact identity는 그대로 보존합니다.

T15는 **완료**했습니다. T11~T14의 실제 결과를 75개 peripheral manifest와 release readiness에
반영했고, M24/M25 fixture physical gate를 **PASS**로 확정했습니다. 이 판정은 검증한 지원
범위에만 적용하며 QDEC 알려진 제한이나 미실행 조합을 PASS로 바꾸지 않습니다. 다음 단계는 T16입니다.

## 1. 판정 기준

- T11 Serial 전 인스턴스 단독 기능과 current-source 회귀
- T12 GPIO·ADC·PWM·event·PDM·I2S 기능 실기와 QDEC 실패 원본
- T13 S 정상·동시성·복구·C05 1시간 soak 및 U UART00 실기
- T14 GPIO/DMA/event/PWM 자원 충돌 판정과 두 보드 회귀
- 42번에서 합의한 기능 HIL 범위: 외부 정밀 계측과 제3자 장치 인증은 필수 gate가 아님

`partial`은 해당 경로의 일부 조합만 검증했다는 뜻이고 `not_run`은 실행하지 않았다는 뜻입니다.
두 상태를 `pass`로 확대하지 않습니다. 모든 pairwise 조합도 합의 범위가 아닙니다.

## 2. M24 Serial 최종 반영

| 항목 | 결과 |
| --- | --- |
| identity | 23개 |
| 단독 HIL | **23 pass** |
| 노출 | public 4, internal candidate 19 |
| 동시 HIL | partial 15, not_run 8 |
| readiness | `m24_fixture_hil = passed` |

동시 HIL의 `partial` 15개는 C01~C05에서 실제 함께 실행한 UARTE/SPIM/SPIS/TWIM/TWIS
identity에만 반영했습니다. 나머지 8개를 동시 지원으로 추정하지 않습니다. 반복 Serial handover는
사용자 결정으로 제외했고, 이 제외를 일반 begin/end·stop/restart 실패로 해석하지 않습니다.

M24의 public 범위는 기존 `Serial`, `Serial1`, `SPI`, `Wire`입니다. 나머지 19개 advanced
identity는 source와 실기 근거가 있어도 아직 internal candidate이며, T16 설치 통합 전 공개 API라고
표현하지 않습니다.

## 3. M25 Analog·Event·Stream 최종 반영

| 항목 | 결과 |
| --- | --- |
| identity | 36개 |
| 기능 HIL | **34 pass, 2 partial** |
| 노출 | public 10, internal candidate 26 |
| 동시 HIL | partial 11, not_run 25 |
| readiness | `m25_fixture_hil = passed` |

GPIO0/1/2, GPIOTE20/30, EGU10/20, DPPIC00/10/20/30, PPIB 8개, TIMER00/10/20~24,
GRTC, SAADC, PWM20/21/22, PDM20/21, I2S20은 각 원본에 맞춰 HIL `pass`로 교정했습니다.
C06/C08과 PWM capture에서 함께 실행한 GPIOTE20·DPPIC20·TIMER22·SAADC·PWM20/21·PDM20·I2S20은
동시 HIL `partial`로 표시했습니다.

QDEC20/21은 HIL `partial`, internal candidate를 유지합니다. 실제 파형·다수 조건은 동작했지만
활성 manual read/clear에서 간헐 누산 누락이 남았고 추가 진단은 사용자 결정으로 제외됐습니다.
따라서 QDEC를 v0.4.0 공개 지원이나 physical PASS로 선언하지 않습니다. `m25_fixture_hil` PASS는
QDEC를 제외하고 명시한 지원 범위가 완료됐다는 의미입니다.

## 4. Readiness 변화

| gate | 이전 | T15 판정 |
| --- | --- | --- |
| `m24_fixture_hil` | hold | **passed** |
| `m25_fixture_hil` | hold | **passed** |
| 전체 release blocker | 8개 | **6개** |

남은 6개 blocker는 frozen RC의 Host·문서·전체 Zephyr 재현 build,
package reproducibility, Boards Manager lifecycle, project owner 공개 승인입니다. T15는 RC를 고정하거나
tag·Release·stable index를 공개하지 않았습니다.

T15 변경 뒤 계약 46개, generated contract 5개, inventory 75개, M24 23개 profile,
M26 16개 capability와 Markdown 232개 UTF-8·로컬 링크 검사를 통과했습니다.
M27 contract는 16개 gate·blocker 6개로 일치했고 `git diff --check`도 통과했습니다.

## 5. 근거

- M24 단독: [44](44_M24_Fixture_101_UART_실기_검증.md)~[50](50_M24_Fixture_301_TWI_실기_검증.md)
- M25 ADC/PWM: [74](74_T12_Fixture_401_current_source_PWM_ADC_검증.md)~[83](83_T12_Fixture_408_current_source_PWM_ADC_검증.md)
- I2S·PDM·내부 event: [87](87_T12_Fixture_430_current_source_I2S_재검증.md), [92](92_T12_Fixture_440_PDM_연속_전체_검증.md), [95](95_T12_내부_ADC_TIMER_이벤트_무점퍼_검증.md)
- GPIO/PWM/I2S와 QDEC 경계: [100](100_T12_공통_기능_묶음과_T13_조합_확정.md), [101](101_T12_QDEC_누산_누락_원인_분리.md)
- T13/T14: [104](104_T13_S_복구_동시_안정성_검증.md), [115](115_T13_U_UART00_완료와_T13_종료.md), [116](116_T14_자원_충돌_판정과_PWM_식별_교정.md)

## 6. 종료 상태

- T13: **100% 완료**
- T14: **100% 완료**
- T15: **100% 완료**
- 추가 보드 조작·결선 변경: **없음**
- 다음 작업: **T16 — 후보 API·profile·예제의 설치본 통합**
