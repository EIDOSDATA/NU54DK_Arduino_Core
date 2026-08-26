# NU54DK Arduino Core

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Author: Quantum](https://img.shields.io/badge/Author-Quantum%20%40%20NUCODE-blue.svg)](#작성자)

NU54DK에서 Loader 없이 동작하는 Native Full Zephyr 기반 Arduino Core입니다.

## 현재 상태

- 아키텍처 결정 완료
- 저장소 기본 구조 생성 완료
- NU54DK Zephyr 보드 패키지 `fe65f2f0880b` 서브모듈 연결 완료
- 구현 로드맵과 빌드·펌웨어 설계 기준선 작성 완료
- NCS v3.4.0에서 M1~M3 pristine build 기준선 통과
- 온보드 CMSIS-DAP V2/pyOCD 기본 경로와 LED 실행 확인
- M1 **GO**, clean 보드 package 기반 C++·Blinky pristine build와 실기 기준선 통과
- M2 **GO**, Zephyr module·Core runtime·Core 비활성 회귀와 C++ 정책 build 통과
- M3 Blink·버튼 육안 동작과 시간·scheduler trace 통과
- M3 sample 3종과 Core 비활성·`led0` 누락 negative build 통과
- M3 **CONDITIONAL GO**, LED 물리 식별과 GPIO RAM trace·외부 계측·Twister·rollover·PM/idle 검증 대기
- 외장 J-Link flash/debug HIL은 M3 필수 게이트가 아니라 M8에서 별도 검증
- 이번 clean 기준선 갱신은 build-only이며 장치 플래시는 다시 수행하지 않음

## 보드 정의

NU54DK의 물리 핀, 주변장치, pinctrl 및 runner 정보는 별도 저장소를 단일 원본으로 사용합니다. Arduino Core 저장소에는 해당 저장소를 다음 경로의 Git 서브모듈로 고정합니다.

- [Nucode01/NU54DK_Zephyr_DTS](https://github.com/Nucode01/NU54DK_Zephyr_DTS)
- `board_package/NU54DK_Zephyr_DTS`

Arduino Core 안에 독립적인 보드 DTS 복사본을 만들지는 않습니다. 빌드할 때 서브모듈 루트를 Zephyr의 `BOARD_ROOT`로 전달합니다.
`NU54DK_Zephyr_DTS`는 상위 저장소가 가리키는 commit에 고정된 **읽기 전용 빌드 입력**입니다.
Arduino Core 작업에서는 서브모듈 내부 파일을 수정하지 않습니다. 보드 자체 변경이 필요하면 보드
저장소에서 별도 변경·검증한 뒤, 의도적으로 상위 gitlink를 갱신합니다.

~~~text
-DBOARD_ROOT=<NU54DK_Arduino_Core>/board_package/NU54DK_Zephyr_DTS
~~~

소스 저장소를 처음 복제할 때는 서브모듈도 함께 내려받아야 합니다.

~~~shell
git clone --recurse-submodules <NU54DK_Arduino_Core 저장소 URL>
~~~

이미 저장소를 복제했다면 다음 명령을 사용합니다.

~~~shell
git submodule update --init --recursive
~~~

Boards Manager용 배포 archive에는 고정된 서브모듈 commit의 실제 보드 파일을 같은 경로에 포함합니다. 따라서 Arduino IDE 사용자는 Git이나 서브모듈 명령을 따로 실행하지 않습니다.

## 문서

- [전체 문서 안내](./00_Docs/README.md)
- [개발 방식 비교 및 아키텍처 결정](./00_Docs/00_사전%20리서치/01_개발_방식_비교_및_아키텍처_결정.md)
- [저장소 폴더 구조](./00_Docs/01_아두이노%20코어%20설계/01_저장소_폴더_구조.md)
- [구현 로드맵](./00_Docs/01_아두이노%20코어%20설계/02_구현_로드맵.md)
- [M1 도구 환경과 보드 실기 기준선](./00_Docs/04_검증%20기록/01_M1_도구와_보드_기준선.md)
- [M2 Zephyr module과 runtime 기준선](./00_Docs/04_검증%20기록/02_M2_Zephyr_Module과_Runtime_기준선.md)
- [M3 GPIO·시간·Scheduler 기준선](./00_Docs/04_검증%20기록/03_M3_GPIO_시간과_Scheduler_기준선.md)

## 작성자

이 Arduino Core와 문서의 작성자는 **NUCODE의 Quantum**입니다.

## 라이선스

NUCODE가 자체 작성한 코드는 [MIT License](LICENSE)를 적용합니다. Zephyr, NCS,
ArduinoCore-API와 보드 package 등 third-party 구성요소에는 각 원본 라이선스와 고지가
별도로 적용됩니다.
