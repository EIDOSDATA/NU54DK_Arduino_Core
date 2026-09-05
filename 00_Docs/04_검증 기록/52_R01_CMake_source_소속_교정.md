# R01 — Serial adapter의 Core target 소속 교정

2026-09-06, 시작 source `d2c125c` (`main`). 종료 commit은 이 문서의 최초 commit으로 식별한다.
R00의 [51번 기준선](51_R00_리팩토링_기준선.md)에 이어 F01을 재현하고 교정했다.

SPIM/SPIS/TWIM/TWIS가 Core library 생성 전 호출한 `zephyr_library_sources()`는 상위 library에
source를 붙였다. 네 호출을 기존 `NUCODE_ARDUINO_CORE_SOURCES` 목록 추가로 바꿔 UARTE와 같은
최종 `nucode_arduino_core` target에 한 번 등록한다. Kconfig와 API, SDK·board, runtime 코드는 그대로다.

## 재현과 검증

| 관측 | 결과 |
| --- | --- |
| 실제 module CMake를 포함하는 Host configure | 수정 전 SPIM/SPIS/TWIM/TWIS/all 5개 실패, 수정 후 none·각 5개·all 7개 통과 |
| exact NCS target | 같은 7개 설정과 DUT/Peer 2개, 합계 9/9 build-only, fail/error/warning 0 |
| target 내용 검사 | 실제 `.config` prerequisite·충돌 설정, compile database의 선택 source 1개/비선택 0개, Core object 소속과 최종 ELF의 실제 호출 `configure` symbol 일치 |
| 검사기 negative | source 누락·중복·상위 target·resolved 설정 불일치·link symbol 누락 거부 |
| Host 전체 | 600개 중 598 PASS, 2 조건부 SKIP; compiler 회귀는 실행. 검사기 추가 후 해당 8개 별도 재실행 |
| CI contract / package | 45/45 / 20/20 PASS |
| Inventory | identity 75, serial 23, system 16, readiness 16개·blocker 8개 유지 |
| 문서 / 스타일 | UTF-8·내부 링크 및 clang-format 22.1.8, first-party 228개 PASS |
| 실기 / 전체 56 target | NOT RUN / R13 최종 gate에 남김 |

Host 출력 중 HIL PASS 문자열은 mock runner 시험의 출력이며 장치 실행이 아니다.
두 skip은 설치 discovery opt-in과 dirty checkout 전용 조건이다. R00 commit 직후 clean checkout의
M27 release Host 9/9도 별도로 실행해 통과했다. Actions 상태는 새로 확인하지 않았다.

DUT/Peer의 resolved `.config`와 text/data/bss 크기는 R00과 각각 같다.
DUT flash(text+data) 181,092 / RAM(data+bss) 161,234 byte,
Peer flash 181,112 / RAM 161,234 byte다. 객체 소속이 바뀌어 artifact hash와 link 배치는 별도로 기록하며
과거 T11 image와의 동일 동작 또는 새 physical PASS를 주장하지 않는다.

## 증거와 재실행

- [실제 source/config/link 증거](evidence/r01-d2c125c/serial-source-builds.json)
- [target 선택과 고정 SDK identity](evidence/r01-d2c125c/target-build.json)
- [DUT/Peer 전후 object 명령·크기·hash](evidence/r01-d2c125c/pair-comparison.json)
- [software 원본 log hash와 결과](evidence/r01-d2c125c/software-gates.json)

실행 환경은 51번의 고정 Python/SDK/GCC/Arduino CLI와 같다. target 명령은
`run_zephyr_build.py --workspace C:/ncs/v3.4.0 --outdir C:/r01 --group v0.4.0 --jobs 4`에
`--suite nucode.r01.none/uarte/spim/spis/twim/twis/all`을 각각 반복 지정하고
`nucode.v04.pair_dut`, `nucode.v04.pair_peer`를 추가했다. slash 표기는 일곱 scenario의 축약이다.
빌드 디렉터리는 보존하며 재실행에는 새로운 짧은 경로가 필요하다.
Host 재현은 `python -m unittest discover -s tests/host -p test_v04_cmake_sources.py`다.

되돌림 단위는 네 CMake 호출과 R01 target/Host 시험·검사기 등록이다. API·CLI·builder schema·저장
형식 migration은 없다. 다음 R02는 파일 이동 없이 SPIM/TWIM 동기 완료의 세대 식별, timeout,
event 소비자 분리와 같은 handle의 submit/cancel/deactivate 수명주기를 검증·교정한다.
최종 source의 UART/SPI/TWI 전체 current-source T11은 R13 뒤에만 시작한다.
