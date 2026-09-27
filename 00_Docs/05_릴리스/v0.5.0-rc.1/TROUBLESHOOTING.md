# v0.5.0-rc.1 Troubleshooting

## RC가 설치 목록에 없음

Stable root index는 `0.4.1`만 제공합니다. [RC 설치 안내](README.md)의 RC 전용 URL을 추가하고
index를 갱신한 뒤 `0.5.0-rc.1`을 명시적으로 선택합니다.
설치 버전은 Boards Manager 또는 `arduino-cli core list`로 확인합니다.
`NU54DK.coreVersion()`의 `0.4.1-dev`를 패키지 설치 실패로 해석하지 않습니다.

## 설치는 표시됐지만 compile이 실패함

Arduino의 platform 등록만으로 Nordic prerequisite 설치가 완료되는 것은 아닙니다.
로그의 최종 `Nordic prerequisite installation PASS`, `status: ready`, 성공 종료를 확인합니다.
기본 marker 위치는 다음과 같습니다.

```text
%LOCALAPPDATA%\NUCODE\NU54DK_Arduino_Core\prerequisites\ready.json
```

`E_PREREQUISITE_READY`는 marker 누락·잘못된 상태·다른 NCS/toolchain 경로를 지정한 경우
fail-closed로 발생합니다. Marker에 기록된 고정 NCS v3.4.0 환경을 사용하며 내용을 수동으로
성공 상태로 바꾸지 않습니다. 자세한 로그·재검증 절차는
[prerequisite 안내](../../../tools/nu54-prerequisites/README.md)를 따릅니다.

## 특정 예제만 실패하거나 기능이 없음

예제의 Feature set과 `nucode-build.json`·`prj.conf`·`app.overlay`가 함께 있는지 확인합니다.
DFU 예제는 `secure_ble_dfu`와 외부 signing key, 외장 Audio I/O 예제는 전용 profile이 필요합니다.
Stable 패키지로 RC 전용 예제를 열지 않았는지 설치 버전도 확인합니다.
Controller 미지원 기능이나 검증하지 않은 조합은 [Known issues](KNOWN_ISSUES.md)를 먼저 봅니다.

## Upload 또는 Serial monitor 문제

선택한 CMSIS-DAP 대상·보드 역할·COM을 확인하고 다른 debug/monitor process가 probe나 COM을
점유했는지 확인합니다. 여러 보드 중 대상을 추측하지 않습니다.
[업로드·디버그 안내](<../../02_빌드 설계/05_업로드와_디버그.md>)의 대상 지정 절차를 사용합니다.
`Serial`은 DAP UART이고 native USB CDC가 아니며 일반 예제는 115200 8N1을 사용합니다.
자동 mass erase·unlock·recover로 오류를 우회하지 않습니다.

## 다운로드 무결성 또는 stable 복귀

다운로드 파일은 Release의 `CHECKSUMS.sha256` 및 [고정 ZIP hash](README.md#공개-package-identity)와 대조합니다.
Stable 복귀는 [Migration](MIGRATION.md)의 제거 후 명시적 `0.4.1` 설치 절차를 사용합니다.
SDK 전체나 사용자 프로젝트를 일괄 삭제하지 않습니다.

해결되지 않으면 설치 버전, Windows·IDE/CLI 버전, profile, 최소 스케치와 **첫 오류**·로그 경로를
[GitHub Issues](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/issues)에 남깁니다.
원시 probe UID·인증 정보·signing key는 제거하며 원인 없는 무한 재시도로 PASS를 만들지 않습니다.
