# v0.5.0-rc.2 — Windows Arduino GUI 시험 후보

RC2는 RC1의 예제 설정·probe 선택·한국어 출력·빌드 진행/캐시를 교정한 **Pre-release**다.
Stable 지원은 계속 v0.4.1이며 정식 v0.5.0 공개가 아니다. CI 시간 목표 미달은 사용자가 수용했고,
IDE GUI 검증은 사용자가 이어간다. 자동 검사·실물 upload 결과를 GUI PASS로 표시하지 않는다.

## Arduino IDE 2.x 설치

1. `File → Preferences → Additional Boards Manager URLs`에 아래 URL을 추가한다.
   기존 RC1 URL이 있다면 RC2 URL로 교체한다. Stable URL은 그대로 둘 수 있다.
2. `Boards Manager`에서 `NUCODE NU54DK Zephyr Boards`를 찾고 **0.5.0-rc.2**를 선택해 설치한다.
3. Post-install 실행 확인을 승인하고 `Nordic prerequisite installation PASS`를 확인한다.
   최초 설치는 고정 SDK/toolchain 다운로드 때문에 오래 걸릴 수 있다.
4. 보드 `NU54DK (nRF54L15, Zephyr)`를 선택한다.
5. 먼저 한 보드로 `File → Examples → NUCODE NU54DK → Blink`를 연다.
   Feature set은 `Standard peripherals`, Upload probe는
   `CMSIS-DAP - one probe auto (multiple: CLI UID)`를 선택하고 Verify → Upload한다.

[Boards Manager 설치 index](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/releases/download/v0.5.0-rc.2/package_nucode_nu54dk_rc_index.json):

```text
https://github.com/EIDOSDATA/NU54DK_Arduino_Core/releases/download/v0.5.0-rc.2/package_nucode_nu54dk_rc_index.json
```

다운로드 파일을 IDE에 직접 여는 것이 아니라 **위 URL을 환경설정에 붙여 넣는다**.
Windows 10/11 x64 대상이며 일반 사용자에게 별도 Git/Python/VS Code 설치는 필수가 아니다.
Serial 예제는 대응 DAP UART COM 포트의 115200 8N1을 사용한다. COM 포트 선택은 SWD probe 선택과 다르다.

> 공개 후 GUI 시험에서 Standard Blink 실행 뒤 수정한 두 번째 pyOCD Upload가 No ACK로 실패하는
> runtime PM 문제가 확인됐다. USB 재연결은 일시 복구이며, main 후속 교정은 전역 장치 자동 suspend를
> 끈다. 공개 RC2 archive는 변경하지 않았으므로 [문제 해결](TROUBLESHOOTING.md)과
> [알려진 제한](KNOWN_ISSUES.md)을 확인한다.

## 예제와 대상 선택

113개 예제의 `.ino` 상단에 Feature set·역할·필요 보드 수·Serial·sidecar 안내가 있다.
`nucode-build.json`, `prj.conf`, `app.overlay` 등은 예제 폴더와 함께 유지한다.
NUS는 `BLE NUS`, 고급 ISO/Audio/DF/CS는 해당 예제의 지정 설정을 따른다.
Feature set 이름만 보고 모든 기능을 동시에 사용할 수 있다고 판단하지 않는다.

온보드 probe가 한 대면 자동 선택한다. 여러 대면 임의 선택하지 않고 중단한다.
`NUCODE_PROBE_UID`에 실제 UID를 설정한 환경에서 IDE를 새로 시작하거나 CLI로 명시한다.
자리표시자를 실제 UID처럼 입력하지 않고 원시 UID는 공유 로그에서 제거한다.
J-Link 메뉴는 외부 SEGGER 장비·SWD/VTref/GND 결선이 있을 때만 사용한다.
세부 절차는 [문제 해결](TROUBLESHOOTING.md)과 [업로드 설계](<../../02_빌드 설계/05_업로드와_디버그.md>)를 따른다.

## 고정 배포 identity

| 항목 | 값 |
| --- | --- |
| Release | [v0.5.0-rc.2 Pre-release](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/releases/tag/v0.5.0-rc.2) |
| Core source/tag | `b2e7a587ba6fde31e033dc21008d7084bd6e631b` |
| Board source | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |
| SDK | NCS v3.4.0, 고정 Zephyr/toolchain [lock](../../../tools/ci/ncs-3.4.0.lock.json) |
| Archive SHA-256 | `b2992bcab8c2e7cb322336a3be1a5101c69da5b63fa1676add0194ae181d43c4` |
| Archive 크기 | 8,717,905 bytes |
| 패키지 분모 | 16개 library·113개 예제 |

이미 검증한 b2e7 package를 그대로 배포하며 이후 main의 문서 갱신으로 다시 만들지 않는다.
Archive 내부 문서는 생성 당시 snapshot이다. 최신 설치·GUI 시험 안내는 이 문서와 루트 README를 따른다.
`NU54DK.coreVersion()`의 `0.4.1-dev`는 source 식별 문자열이며 설치 버전은 Boards Manager/core list/manifest로 확인한다.

[변경점](RELEASE_NOTES.md) · [이동·복귀](MIGRATION.md) · [검증·GUI 체크리스트](TESTING.md) ·
[알려진 제한](KNOWN_ISSUES.md) · [문제 해결](TROUBLESHOOTING.md)
