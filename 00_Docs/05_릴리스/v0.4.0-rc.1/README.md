# NU54DK Arduino Core v0.4.0-rc.1 — 내부 준비

| 항목 | 상태 |
| --- | --- |
| 제품선 | Peripheral Parity |
| RC 공개 | HOLD — tag·GitHub Release·공개 index 없음 |
| 현재 설치 대상 | [v0.3.0 stable](../v0.3.0/README.md) |
| 현재 개발 상태·다음 작업 | [v0.4.0 TODO](../../TODO_v0.4.0.md) |

이 문서는 공개 릴리스 노트가 아니라 준비 범위와 공개 조건을 설명합니다.
현재 진행 수치와 실행별 이력은 TODO와 [검증 기록](<../../04_검증 기록/README.md>)에서 관리합니다.

| 사용자 문서 | 링크 |
| --- | --- |
| 변경 내용 | [Release notes](RELEASE_NOTES.md) |
| v0.3.0 Sketch 이동 | [Migration](MIGRATION.md) |
| 검증 범위와 최종 재실행 | [Testing](TESTING.md) |
| 진단 절차 | [Troubleshooting](TROUBLESHOOTING.md) |
| 제한·미지원 범위 | [Known issues](KNOWN_ISSUES.md) |

## 준비된 기술 범위

| 묶음 | 준비 범위 | 해석 |
| --- | --- | --- |
| M23 | 75개 peripheral identity, block/channel/DMA 소유권 계약 | 지원·실기 상태는 개별 항목별로 판정 |
| M24 | `fabric` profile의 UARTE·SPIM/SPIS·TWIM/TWIS 23개 | 단독 HIL·route·공개 원장 PASS, 미실행 동시 조합은 보증하지 않음 |
| M25 | SAADC·PWM·timer/event·PDM·I2S 직접 API | 검증 범위 공개, QDEC만 unsupported·추가 진단 제외 |
| M26 | 16개 system 기능의 지원 경계 | TEMP·WDT30 실기 PASS를 `SystemFabric`에 연결, 나머지는 행별 경계 유지 |
| M27 | checksum·SBOM·license·RC/stable HOLD plan | T18 절차 완료, R14/T19 이후 최종 비공개 package 재생성·검증 필요 |

초기 M27의 격리 staging 예제 29/29 compile 결과는
[39번 기록](<../../04_검증 기록/39_M27_v0.4.0_rc1_자동_준비와_HOLD.md>)의 당시 source에 한정됩니다.
최종 frozen RC의 설치·Upload·수명주기 통과로 재사용하지 않습니다.
T16 이후 현재 후보는 `NUCODE Peripheral Fabric` 예제를 포함한 **30개**이며 최종 T20에서 전부
다시 검사합니다.

## 현재 범위 결정

- R00~R13과 source별 T11 단독 회귀는 완료했습니다. T12는 QDEC 문제 보고를 포함해 사용자가 수용했습니다.
- QDEC 추가 진단과 연속 UART/SPI/TWI 종류·역할 전환(시리얼 핸드오버)은 이번 실행에서 제외합니다.
- 요청한 S 범위는 **PASS 56 + 제외 2 / 58**로 종료했습니다. 제외한 2조건은 기존 M15 GRTC·버튼
  wake 실기와 중복되는 T13 peer 제어 System OFF 추가 결합 시험입니다.
- UARTE00 별도 4-net 결선 검사, 정상 180초, RTS/CTS 200회와 TX/RX 취소 400회를 완료했습니다.
  완료 근거는 [115번 기록](<../../04_검증 기록/115_T13_U_UART00_완료와_T13_종료.md>)에 있습니다.
- T14/T15의 원인·수정·지원 범위 확정과 T16 설치 profile 통합을 완료했습니다.
- T17 문서·지원 매트릭스와 T18 stable 준비·승인 차단 절차를 완료했습니다. 현재 R14/T19에서 RC를 고정합니다.
- T20~T21 비공개 package 검증 뒤 T22 소유자 승인 전에는 tag·Release·stable index를 쓰지 않습니다.

## 실기 검증 경계

[42번 범위 합의](<../../04_검증 기록/42_v0.4.0_코어_기능_검증_범위_합의.md>)에 따라
온보드 자원과 두 NU54DK의 peer/loopback·합성 신호·capture를 사용합니다.
별도 계측기·교정 신호원·실제 마이크/코덱/엔코더를 필수 준비물로 요구하지 않습니다.

정밀 정확도·jitter·소비전력·신호 품질·개별 외부 부품 호환성은 이 기능 검증의 보증 대상이 아닙니다.
합성 peer를 포함한 실제 데이터·DMA·오류 복구·동시성·합의된 안정성 조건은 증거로 판정하며,
미실행이나 범위 제외를 PASS로 기록하지 않습니다.

## 공개 전 gate

1. T11~T15의 source별 기능·복구·동시성 결과와 제외·제한사항 확정 — 완료
2. T16 설치 profile·API·예제 통합, T17 문서·지원 원장과 T18 공개 절차 — 완료
3. R14 frozen RC의 Host·문서·전체 target build·이중 package 재현
4. 격리 Boards Manager 설치·전체 예제 compile·실제 Upload·제거·재설치·version 전환
5. T22 프로젝트 소유자의 결과별 명시적 공개 승인
6. T23 공개 후 T24 공개 URL 검사와 T25 마무리

[Readiness](../../../variants/nu54dk/v0.4.0-release-readiness.json)와
[M27 도구](../../../tools/release/M27_README.md)의 HOLD는 문서 정리만으로 해제하지 않습니다.
공개 payload는 덮어쓰지 않으며 구버전 공급 종료·원본 archive 보존은
[106번 결정](<../../04_검증 기록/106_Git_이력_정리와_구버전_패키지_공급_종료.md>)을 따릅니다.
