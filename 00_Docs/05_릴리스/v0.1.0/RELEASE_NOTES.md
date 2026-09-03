# NU54DK Arduino Core v0.1.0 릴리스 노트

`v0.1.0`은 Loader 없이 Sketch와 Zephyr를 하나의 정적 firmware로 만드는 NU54DK 전용 첫
정식 Release다. 공식 host 범위는 Windows 10/11 x64다.

> **공개 완료:** `v0.1.0` tag와 일반 GitHub Release를 2026-08-28T13:07:19Z에 공개했다.
> 7개 공개 자산을 인증 없이 다시 내려받아 size·SHA-256과 archive/index 계약을 검증했다.

## 주요 기능

- NCS v3.4.0 / Zephyr 4.4.0 기반 Native Full Zephyr build
- Arduino IDE/CLI 공용 `nucode:zephyr:nu54dk` platform
- Arduino `setup()`/`loop()`와 Zephyr API의 동시 사용
- GPIO, 시간·delay, `String`, `Print`, `Stream`, DAP UART `Serial`, GPIO interrupt
- I2C `Wire`, SPI00, A0 ADC와 P1.10 PWM
- CMSIS-DAP V2/pyOCD 기본 Upload와 외장 J-Link 선택 Upload/debug
- persistent Zephyr cache, ccache, lock/LRU와 손상 복구
- Boards Manager stable index, SPDX SBOM, license inventory와 사용자 영역 Nordic 설치

## RC 이후 변경

- package version과 소스 표시 version을 `0.1.0`으로 확정했다.
- stable 전용 package 채널과 `package_nucode_nu54dk_index.json`을 추가했다.
- stable package의 프로젝트 소유자 승인 상태를 license inventory에 기록한다.
- RC 전용 검증 도구는 역사적 evidence를 변경하지 않도록 stable을 계속 거부한다.

firmware runtime, NU54DK DTS, pin mapping과 Upload 구현은 rc.2 이후 변경하지 않았다. 패키지
검증에서는 version 문자열만 정규화한 runtime fingerprint를 rc.2와 비교한다.

## 검증 경계

- rc.1 exact artifact의 필수 gate 8/8은 역사적 기준선으로 보존한다.
- rc.2는 자동 gate 5/5와 별도 clean Windows Arduino IDE 2.3.10 설치·compile·실제 NU54DK
  upload·실행의 프로젝트 소유자 수동 검증을 통과했다.
- stable archive는 exact release commit, archive/index schema, checksum, SBOM, license와
  runtime fingerprint 동등성을 새로 검증한다.
- rc.2 수동 HIL을 stable exact HIL로 바꿔 기록하지 않는다. 정식 공개 후 수행한 stable
  package 검증은 별도 공개 기록에 남긴다.

## 공개 identity

| 항목 | 값 |
| --- | --- |
| Release commit | `5dbc5e37270e477d21f578dd877f4b5226b44a0d` |
| Board package commit | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |
| Archive | 760,412 byte, SHA-256 `722a46685b97aff42a75fb84db8ea74de75f3c32f59ea58225cd86d5acd141a6` |
| Stable index snapshot | 1,125 byte, SHA-256 `385445512ba6bb842024979e8314f2f953eb15a14e3ce72076b6d475e2e7583d` |
| Runtime fingerprint | `e6d205e261328c842a164762f1df1ff010b0a209319c925df89ee797ad99f659` — rc.2와 일치 |
| GitHub Release | [v0.1.0](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/releases/tag/v0.1.0), Draft 아님·Prerelease 아님 |

전체 자산과 검증 경계는
[정식 릴리스 공개 기록](<../../04_검증 기록/13_v0.1.0_정식_릴리스_공개_기록.md>)에 있다.

## 설치

```text
https://raw.githubusercontent.com/EIDOSDATA/NU54DK_Arduino_Core/main/package_nucode_nu54dk_index.json
```

자세한 절차는 [마이그레이션 안내](MIGRATION.md)를 따른다.

## 라이선스와 공개 승인

NUCODE 자체 작성 코드는 MIT License다. ArduinoCore-API, NU54DK board package와 외부
prerequisite에는 각 원본 라이선스와 고지가 적용된다. Nordic/SEGGER binary는 Core ZIP에
재배포하지 않는다. 프로젝트 소유자는 v0.1.0의 라이선스 판단, 알려진 제약과 정식 공개를
승인했다. 기계적 inventory는 법률 자문을 대신하지 않는다.
