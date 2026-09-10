# v0.4.0-rc.1 Testing — 비공개 후보

## 현재 완료된 범위

| 범위 | 상태 |
| --- | --- |
| M24 Serial identity | 23/23 단독 HIL PASS |
| M25 지원 대상 | 34 PASS, QDEC20/21 partial·unsupported |
| T13 정상·동시성 | 단독 29/29 + 동시 7/7, C05 3600초 포함 |
| T13 오류 복구·UARTE00 | 합의 범위 완료 |
| T14 자원 충돌 교정 | Host·target·두 보드 520 cycle PASS |
| T16 설치 진입점 | `fabric` target와 격리 Arduino build PASS |

실행별 exact source·결선·명령·원본은 [검증 기록 색인](<../../04_검증 기록/README.md>)에서
확인합니다. 이전 source의 PASS를 최종 RC 결과로 복사하지 않습니다.

## 로컬 software 검사

저장소 root에서 현재 변경에 맞는 gate를 실행합니다.

```text
python -B tools/ci/run_m12_gate.py contract
python -B tools/ci/run_m12_gate.py host
python -B tools/ci/run_m12_gate.py docs
python -B tools/peripheral/verify_generated.py
```

Target build와 package 검사는 고정 NCS v3.4.0 workspace와 lock에 기록한 도구를 사용합니다.
임의 SDK나 이전 build cache의 성공을 재현 결과로 사용하지 않습니다.

## 최종 RC에서 다시 실행할 범위

T19에서 exact source·board·SDK·toolchain을 고정한 뒤 전체 Host·문서·inventory·target build를
실행합니다. T20~T21에서는 package를 독립적으로 두 번 만들고 ZIP·SBOM·checksum·license를
비교한 다음 격리 Boards Manager 설치, 30개 예제 compile, 실제 Upload, 제거·재설치·version
전환을 검사합니다. 공개 URL 시험은 T23 이후 T24의 별도 단계입니다.
