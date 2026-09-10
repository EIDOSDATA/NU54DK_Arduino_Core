# v0.4.0 Testing

## 검증한 범위

| 범위 | 결과 |
| --- | --- |
| M24 Serial identity | 23/23 단독 HIL PASS |
| M25 공개 대상 | 34 PASS, QDEC20/21 unsupported |
| T13 정상·동시성 | 단독 29/29 + 동시 7/7, C05 3600초 포함 |
| T13 오류 복구·UARTE00 | 합의 범위 완료 |
| T14 PWM 소유권 교정 | Host·target·두 보드 520 cycle PASS |
| T19 frozen RC | Host·문서·inventory·target 35/35·이중 package 재현 PASS |
| T20 RC 설치 수명주기 | 격리 설치·예제 30/30·실제 Upload·전환·제거·재설치 PASS |

실행별 exact source·결선·명령과 실패 원본은
[검증 기록](<../../04_검증 기록/README.md>)에서 확인합니다. `PASS`는 적힌 source·조건에만
적용하며 범위 제외나 미실행을 포함하지 않습니다.

## 설치 package 확인

1. stable index에서 `nucode:zephyr@0.4.0`을 설치합니다.
2. post-install 로그와 prerequisite `ready.json`이 모두 PASS인지 확인합니다.
3. 설치본 30개 예제를 발견 목록과 대조하고 각 profile로 clean compile합니다.
4. 대표 Sketch를 지정 CMSIS-DAP probe에 erase/recover 없이 Upload합니다.
5. 제거·재설치와 지원하는 version 전환 뒤 설치 version과 prerequisite 보존을 확인합니다.

로컬 후보 package 결과와 공개 URL 결과는 구분합니다. 실제 GitHub asset과 stable index가 공개된
뒤에는 새 격리 환경에서 다시 내려받아 archive hash·설치·compile·Upload를 확인합니다.

## 로컬 source gate

```text
python -B tools/ci/run_m12_gate.py contract
python -B tools/ci/run_m12_gate.py host
python -B tools/ci/run_m12_gate.py docs
python -B tools/ci/run_m12_gate.py inventory
python -B tools/ci/run_m12_gate.py package
```

Target build는 고정 NCS v3.4.0과 Toolchain `dcbdc366a1`을 사용합니다. 임의 SDK, 이전 build
cache 또는 다른 source의 성공을 현재 결과로 재사용하지 않습니다.
