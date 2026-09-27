# v0.5.0 문제 해결

## 설치

- Boards Manager에 0.5.0이 없으면 stable index URL의 오탈자와 인터넷 연결을 확인합니다.
- post-install을 승인하고 `Nordic prerequisite installation PASS`가 나올 때까지 첫 오류를 확인합니다.
- 이전 RC URL이 함께 있으면 RC URL을 제거하고 IDE를 다시 시작합니다.
- 긴 경로 오류는 Arduino data/cache directory를 짧은 경로로 옮겨 재현합니다.

## Verify

- `.ino` 상단의 권장 Feature set과 필수 sidecar를 확인합니다.
- `[NU54 1/5]`부터 `[NU54 5/5]`까지 단계와 원본 `build.log` 경로를 확인합니다.
- cache hit/miss 자체를 오류로 보지 말고 마지막 안정 오류 코드와 첫 원인을 함께 확인합니다.
- 한국어가 `��`로 깨지면 IDE/CLI 버전, 기본·상세 출력 여부와 원본 byte 로그를 첨부합니다.

## Upload probe

- probe 1대: 자동 선택 메뉴를 사용합니다.
- probe 2대 이상: 자동 선택은 안전하게 중단합니다. `NUCODE_PROBE_UID`를 설정한 환경에서 IDE를
  다시 시작하거나 CLI에서 exact UID를 지정합니다.
- `CMSIS-DAP unique ID` 같은 자리표시자, 빈 값, 잘못된 형식은 실제 UID가 아닙니다.
- J-Link는 외장 SEGGER 장비와 SWDIO/SWDCLK/VTref/GND가 연결된 경우에만 선택합니다.
- 공유 로그에서는 UID를 마스킹하지만 내부 선택에는 전체 identity가 필요합니다.

## `E_SWD_NO_ACK`

1. 대상 전원, VTref, GND, SWDIO, SWDCLK와 `DISABLE_SWD` 상태를 확인합니다.
2. VS Code, pyOCD, debugger 등 다른 프로세스가 probe를 점유하지 않는지 확인합니다.
3. 1 MHz SWD 또는 명시적 under-reset 연결을 진단으로 시도할 수 있습니다.
4. 자동 recover, unlock, mass erase는 실행하지 않습니다.

v0.5.0은 RC2에서 발생한 미사용 장치의 부팅 직후 자동 suspend를 끕니다. 그래도 USB 재연결에만
의존해 반복 성공시키지 말고 위 순서로 첫 원인을 구분합니다. 문제 보고에는 설치 버전, Windows·IDE/CLI
버전, Feature set, 최소 Sketch와 첫 오류를 포함하고 인증 정보와 원시 probe UID는 제거합니다.
