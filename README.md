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
- M1 완료, clean 보드 package 기반 C++·Blinky pristine build와 실기 기준선 통과
- M2 완료, Zephyr module·Core runtime·Core 비활성 회귀와 C++ 정책 build 통과
- M3 Blink·버튼 육안 동작과 시간·scheduler trace 통과
- M3 sample 3종 pristine build와 Core 비활성·`led0` 누락 negative build 통과
- M3 GPIO·시간·scheduler ztest/Twister NU54DK HIL 9/9 통과
- M3 완료; GPIO RAM trace·외부 계측·실제 PM·외장 J-Link는 합의된 범위에 따라 필수 증거에서 제외
- 외장 J-Link flash/debug HIL은 M3 필수 게이트가 아니라 M8에서 별도 검증
- M3 자동 회귀 이미지는 온보드 DAPLink MSD로 플래시하고 COM10에서 Twister 결과를 수집
- M4 완료, ArduinoCore-API 1.5.2를 정확한 commit과 LF 원본으로 vendor하고 NU54DK target API 계약 build 통과
- M5 완료, `nucode:zephyr:nu54dk` FQBN에서 `.ino`와 Arduino library를 Loader 없는 Full Zephyr ELF·HEX·BIN·map으로 빌드
- M5 staged-copy 자동 회귀 6/6 통과: Blink, compile error, library dependency, config/overlay, parallel 격리, incremental build
- M6 완료, ArduinoCore-API `Common`·`String`·`Print`·`Stream`, non-owning UART20 `Serial`과 GPIO edge interrupt 구현
- M6 NU54DK target ztest 10/10과 COM10 실제 Serial READY·고유 echo HIL 통과
- M6 실제 P1.13 active-low 버튼 HIL 통과: `FALLING`·`RISING` 각각 1회, `CHANGE` 누름·해제 누적 1·2회
- M7 완료, NU54DK Twister target 11/11·Arduino CLI 4/4·I2C/ADC/PWM HIL과 SPI 4 MHz 물리 loopback 통과
- M7 통합 staged Builder 회귀 8/8 named group 통과: blink, library, config, error, parallel, incremental, m6, m7
- M7 BQ25186 `MASK_ID(0x0C)=0x41` repeated-start HIL을 100/400 kHz에서 통과하고 SPI00 P2.2→P2.4 40-byte loopback 일치 확인
- M8 완료, Arduino IDE/CLI 공용 Upload recipe와 pyOCD 기본·J-Link 선택 경로 구현
- M8 온보드 CMSIS-DAP 자동 선택, Arduino CLI pyOCD upload 10/10 및 최종 COM10 reset 표식 통과
- M8 Full Zephyr ELF로 pyOCD debugserver와 원본 `.ino` `setup()` source breakpoint 통과
- M8 통합 staged Builder 회귀 9/9와 M7·M8 host protocol/contract unittest 22/22 통과
- M9 완료, Arduino 임시 경로와 분리된 persistent Zephyr cache, canonical key, 전용 ccache와 안전한 lock/LRU 구현
- M9 host 계약 43/43과 Arduino CLI library·parallel·cache 회귀 통과: no-change compiler 0회, Sketch 수정 3.57초, 손상 tree 복구 확인
- M10 완료, 공개 preview `0.0.96`→`0.0.97`을 별도 clean Windows PC에서 최초 설치하고 package 수명주기 11/11 통과
- M10 NCS v3.4.0/Toolchain exact-pin 설치, cold/warm Blink build, 온보드 CMSIS-DAP V2/pyOCD upload 10/10 통과
- M11 기술 완료, exact `v0.1.0-rc.1` artifact의 필수 gate 8/8 통과와 evidence manifest `ready-for-human-approval`
- `v0.1.0-rc.1` tag와 GitHub prerelease는 아직 게시하지 않았으며 프로젝트 소유자 승인 대기
- stable `v0.1.0`, 최종 법률 검토, tag·GitHub Release·stable index 공개는 프로젝트 소유자 승인 대기

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
- [M4 ArduinoCore-API 계약 기준선](./00_Docs/04_검증%20기록/04_M4_ArduinoCore_API_계약_기준선.md)
- [M5 Arduino CLI Build Adapter 기준선](./00_Docs/04_검증%20기록/05_M5_Arduino_CLI_Build_Adapter_기준선.md)
- [M6 기본 Arduino API, Serial과 인터럽트 기준선](./00_Docs/04_검증%20기록/06_M6_기본_Arduino_API_Serial과_인터럽트_기준선.md)
- [M7 Wire·SPI·ADC·PWM 기준선](./00_Docs/04_검증%20기록/07_M7_Wire_SPI_ADC_PWM_기준선.md)
- [M8 업로드와 디버그 기준선](./00_Docs/04_검증%20기록/08_M8_업로드와_디버그_기준선.md)
- [M9 증분 빌드·캐시와 재현성 기준선](./00_Docs/04_검증%20기록/09_M9_증분_빌드_캐시와_재현성_기준선.md)
- [Boards Manager 설치와 패키징](./00_Docs/02_빌드%20설계/06_Boards_Manager_설치와_패키징.md)
- [M10 Boards Manager와 clean Windows 기준선](./00_Docs/04_검증%20기록/10_M10_Boards_Manager_패키징과_Clean_Windows_기준선.md)
- [M11 v0.1.0-rc.1 릴리스 후보 기준선](./00_Docs/04_검증%20기록/11_M11_v0.1.0_rc1_릴리스_후보_기준선.md)
- [v0.1.0-rc.1 릴리스 노트](./00_Docs/05_릴리스/03_v0.1.0_rc1_릴리스_노트.md)
- [v0.1.0-rc.1 알려진 제약](./00_Docs/05_릴리스/04_v0.1.0_rc1_알려진_제약.md)

## 작성자

이 Arduino Core와 문서의 작성자는 **NUCODE의 Quantum**입니다.

## 라이선스

NUCODE가 자체 작성한 코드는 [MIT License](LICENSE)를 적용합니다. Zephyr, NCS,
ArduinoCore-API와 보드 package 등 third-party 구성요소에는 각 원본 라이선스와 고지가
별도로 적용됩니다. 저장소에 포함된 ArduinoCore-API의 고정 revision과 라이선스 범위는
[third-party notices](./third_party/THIRD_PARTY_NOTICES.md)에서 확인할 수 있습니다.
