# HOST-W06 H9 Kconfig 경로 원인과 native 교정

기록일: 2026-11-10. Host 완료5/8, HOST-W06 진행 중이다.
Exact H9 `e132327daebc9553cbac270b3ec0c0ffeeeb7f19`의
[package CI42781574396](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/42781574396)는
producer 성공·세 OS Blink 실패로 종료했다. [318번](318_HOST_W06_H8_설치_통과와_SDK_Git_전달_교정.md)의
SDK Git 전달 누락은 교정됐으며 이번 실행은 그 다음 검사·구성 단계에 도달했다. 전체 예제·비교는 `NOT_RUN`이다.

| 실제 Host | H9 실패 단계 | 원인 상태 |
| --- | --- | --- |
| Windows | SDK Git 실행 뒤 Zephyr clean 검사 | 변경으로 잡힌 실제 파일·mode의 상세 원인 미확정. Guard 유지·변경 경로/수/summary 진단 보강 |
| Ubuntu | Kconfig CMake env 실행의 `no such file or directory` | 설치 Core의 공백 경로가 SDK 생성 CMake list에서 둘로 분할됨을 확정 |
| macOS | 같은 Kconfig env 실행 | 같은 공백 경로 분할 원인을 확정 |

고정 SDK `zephyr/scripts/zephyr_module.py`의 `process_kconfig_module_dir()`는 module 경로를
따옴표 없이 `list(APPEND kconfig_env_dirs …)`로 생성한다. 그 결과 `한글 data`가 두 CMake 인자로
나뉘어 `cmake -E env`의 실행 파일 인자로 해석된다. SDK 입력을 수정하지 않고 해당 함수만 읽어
독립 fixture를 만들었으며 고정 SDK CMake로 같은 오류를 실제 재현했다(`a36140/exit0`).
공백 경로는 env list2개·내부 실행 exit1, 짧은 ASCII 경로는 list1개·내부 실행 exit0이었다.
이는 target compile PASS가 아니라 원인 분리 실험이다. 원문·receipt는
`D:/w06/control/host-w06-kconfig-path-repro-a001`에 보존한다.

교정은 기존 Windows용 설치 Core build 복사본을 세 OS에 적용하는 것이다. 원본 설치955파일과
외부 metadata·source identity는 유지하고 CMake/compile 입력만 ASCII·공백 없는 cache 복사본으로 연결한다.
원형/복사본 byte와 경계·stale/손상은 계속 검사하며 개발 Git checkout은 자동 복사하지 않는다.
SDK source·revision·version·승인 patch는 바꾸지 않는다. Windows clean 실패는 실제 목록을 본 뒤
원인을 판정하며 알려지지 않은 변경을 무시하거나 Git reset/clean으로 지우지 않는다.

Full CI는 독립 SDK8개/OS를 유지하고 각 SDK 안에서는 compile1개와 Ninja worker2개를 사용한다.
임시 SDK patch 적용·복구가 겹치지 않도록 조정한 CI 실행 순서이며204예제/OS·profile 거부9개/OS와
artifact 비교 분모·판정은 줄이지 않는다.

교정 개발 unit은35개 중34 PASS·조건부 POSIX SKIP1(`42c810/exit0`), 기존 Windows recipe와
Host portability 회귀12개는 모두 PASS(`271a2c/exit0`)다. 실제 설치·target build의 최종 성공은
fresh 교정 source의 native CI에서 별도 확인한다.

| H9 FAIL 원형 artifact | ID | ZIP SHA-256 |
| --- | --- | --- |
| Windows | 13747310785 | `eb74705f220d9887d3d15b7c89240ef96d2ca1aa435a0326444d2d12ca66c980` |
| Ubuntu | 13747041351 | `1051ac546ba7e6891015fb90c58aa9b45fa2e392b976c392c63625cc36b97122` |
| macOS | 13745979793 | `09db8fb9f87f9494c5cab01fa95fe353d89d2c736ae42c81bc4bcffea3308bb2` |

원형 ZIP 전체와 선택 log·context·ready·결과 JSON은 `D:/w06/control/host-ci-artifact-ID`에 source binding과
원격 size·digest를 검증해 보존했다. H9 producer archive SHA-256은
`c05c2d84e2ac6ad99326bb04801cf669ac6e20d776df0af9ab32514e6ea3b779`이며 job129712617559 원문에서 확인했다.
H9 별도 prerequisite CI42781574213은 세 OS 성공, software/build-only는 별도 관찰한다. 이를 Blink의 FAIL에 합산하지 않는다.

W06 S19 actual PASS46·명시 수락 #29·40·44, 원형 FAIL·soak·private11831개·public3개·완료 TODO6개를
보존한다. #29 분석 유예·새 HIL0·w06 PAUSED 요청 유지·예약 생성/재활성화 없음.
Ubuntu/macOS 물리 USB·Serial·debug·lifecycle은 RC1 최종 사용자 gate `NOT_RUN`이다.

H10에서 POSIX 공백 경로 교정을 실제 Blink·artifact로 확인했으며 Windows mode 차이를 분리했다. 최신 결과와 교정은 [320번](320_HOST_W06_H10_POSIX_Blink_통과와_Windows_mode_교정.md)을 따른다.
