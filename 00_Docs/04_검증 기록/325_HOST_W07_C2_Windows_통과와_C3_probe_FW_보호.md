# HOST-W07 C2 Windows 통과와 C3 probe FW 보호

2026-11-13. Host 완료는 **6/8**, 현재 HOST-W07 RC1 도구·Windows 검증을 진행한다.
W06 S19 실제 PASS46·수락3(#29·40·44)·FAIL·soak는 동결하며 #29 분석은 유예한다.
source/run/attempt별 결과를 다른 최종 실적으로 합성하지 않는다.

## C2 실제 결과

source `f18038869fa64c422b807e8fac2d821816804cd0`, private `0.6.0-rc.1`이다.

| 항목 | 실제 결과 |
| --- | --- |
| software | run42846429084,9success·0skip |
| prerequisite | run42846392684,3OS 성공;294reported·286PASS·8조건부SKIP |
| kit·SDK | START plan `9eae86/exit0`, SDK 재검증 `dc3551/exit0` |
| Windows lifecycle | `bc64ad/exit0`; H12→RC1 upgrade·동일 version no-op·제거→재설치·실제 post-install;958파일 대조·24library/204example 발견·사용자 데이터/공유 SDK 보존 |
| Windows build | `3abf30/exit0`; Blink·SerialEcho·NUS Peripheral·NUS Central 각cold/warm,총8compile PASS;manifest4개·artifact16개 재hash |
| 전체204·실물 | 이 C2 실행에서는 NOT_RUN |
| 원래 native | run42846392776 FAILURE:28success·1cancelled·1skip;macOS shard5가 hosted runner를 배정받지 못해 실행 자체가 없었음 |
| fresh native | run43366923416 attempt1,C3 교정 필요로 종료 요청·최종cancelled;부분 성공을 전체PASS로 세지 않음 |

C1 FAIL은 [324번](324_HOST_W07_C1_Windows_진입점_FAIL과_C2_교정.md)에 보존한다.
C2 kit `D:/w06/host-w07/c2-kit`의 manifest SHA-256은
`06b7ca4a0f6765dc51536581069e217912a29331d82d41f2c13f8046a13371f6`이다.
세부 원형 receipt는 `D:/w06/control/` 아래 다음 파일이다.

- `host-w07-c2-windows-lifecycle-audit-20261113.json`
- `host-w07-c2-windows-build-audit-20261113.json`
- `host-w07-c2-terminal-log-audit-20261113.json`
- `host-w07-c2-cancelled-macos5-diagnosis-20261113.json`

## C3 연결 보호 교정

실제 readonly 열거의 세 probe 모두 SDK JLinkProbe의 J-Link OB이며 CMSIS-DAP 실물이 아니다.
고정 pyOCD0.42.0/pylink-square1.7.0의 기본 non-interactive 편의 함수가
SilentUpdateFW를 호출함을 SDK 코드에서 확인했다. 이 경로로 장치를 열지 않았다.
C2 preflight는 미실행 상태에서 실행을 차단했다. 새 Host 도구의 보호 누락이며 대상 firmware 실기 FAIL이 아니다.

기본 CMSIS-DAP은 유지한다. J-Link-via-pyOCD는 exact probe identity와
`--allow-jlink-backend`를 함께 지정할 때만 사용한다. SDK 공식 user script가 Session 생성 중
probe open보다 먼저 실제 backend·고정 SDK version·DLL 경로/hash를 확인한다.
J-Link는 native OpenEx 전에 DisableAutoUpdateFW·SuppressGUI 설정을 적용한다.
설정 거부·경고 시 열지 않고 실패하며, 기본 SilentUpdateFW 편의 함수·전력 제어·자동 device 선택·
JTAG fallback·unsecure 수락을 거부한다. 부분 실패의 native 자원과 lock을 정리한다.
SDK·pyOCD·pylink 원본 파일과 probe firmware를 변경하지 않는다.
[SEGGER 명령 계약](https://kb.segger.com/J-Link_Command_Strings)과
[pyOCD 옵션](https://pyocd.io/docs/options.html)을 고정 SDK 구현과 대조했다.

## C3 개발 검사와 남은 순서

- 보호 단위 검사21개 `6c73de/exit0`: synthetic 검사이며 물리 PASS가 아니다.
- 실제 고정 SDK Session 생성 `29b2fc/exit0`: 공식 hook이 실제 backend에 open 전 적용됨을 확인했다.
  native open/reset/halt/program은0회다.
- 통합 a001 `a0a034/exit1`: 새 파일2개의 portability inventory 누락1FAIL. 원형 log를 보존했다.
- 목록 보완 후 fresh a002 `f20514/exit0`:140reported·135PASS·5조건부SKIP.
  이 개발 검사와 최종 C3 CI·실기를 구분한다.

다음은 C3 exact source 고정→같은 source CI·private producer/kit→Windows11 build·
보호된 실물 upload/ELF/GPIO/Serial/NUS→전체204예제·profile 거부9개→문서·증거 감사 순서다.
J-Link 실제 결과를 CMSIS-DAP 물리 PASS로 합산하지 않는다.
이후 [RC1 절차](<../02_빌드 설계/15_Host_RC1_실기_도구와_증거_절차.md>)의 사용자 OS gate→
HOST-W08/M33-W07 마감→M33-W08 공개 검토 순서다. 필수 gate와 별도 공개 승인은 미완료다.
