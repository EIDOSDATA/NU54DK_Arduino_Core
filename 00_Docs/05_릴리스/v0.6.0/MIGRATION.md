# v0.6.0 설치 전이·profile 안내 — 미공개 후보

공개 stable은0.5.0이고 개발 source의 `coreVersion()`도 아직0.5.0이다.
비공개 검증 archive의0.6.0-rc.1과 구분하며 최종 배포 준비에서 식별자를 정합화한다.
정식 v0.6.0으로의 일반 사용자 갱신 안내는 아직 개방하지 않는다.

## 보존된 전이 증거

Windows11의 C5는 별도 CLI 환경에서 공개0.5.0→비공개 RC1 갱신, 사용자 데이터·SDK 보존과
Blink build를 확인했다. C11 Mac의 host.1→RC1은 같은 C11 source로 만든 version fixture다.
이것을 공개0.5.0에서 Mac으로 갱신한 실적으로 표시하지 않는다. 두 Mac의 IDE 설치·Verify는 `NOT_RUN`이다.
원본은 [RC1 절차](<../../02_빌드 설계/15_Host_RC1_실기_도구와_증거_절차.md>)와 [Testing](TESTING.md)을 따른다.

## 예제와 profile 선택

보드·profile·선택 옵션은 예제의 README와 `nucode-build.json`을 따른다.
기본 profile은 `standard`이며 BLE·Secure DFU·Audio 등은 해당 예제에 지정한 feature set을 사용한다.
`adaptive`는 experimental opt-in이고 모든 조합을 지원한다는 의미가 아니다.
DAP UART를 끄는 Peripheral Fabric/외장 Audio 구성은 공유 핀과 결선을 먼저 확인한다.

API 호환성은 [Arduino API 범위](<../../01_아두이노 코어 설계/04_Arduino_API_지원_범위.md>)와
[M33 예제 계약](<../../01_아두이노 코어 설계/19_NCS_Bluetooth_전체_기능과_예제_실행_계약.md>)을 따른다.
template·외부 ecosystem은 필요한 credential과 실제 peer를 준비해야 하며 자동 검사 PASS로 생략하지 않는다.

## 작업 공간과 복귀

후보 package·SDK·cache·출력을 stable 사용 환경과 분리한다. Windows SDK와 WSL Linux SDK/cache를
공유하지 않는다. 실패한 attempt는 남기고 새 입력을 새 attempt에 기록한다.
kit의 downgrade 거부 검사는 실제 downgrade PASS가 아니다. stable 복귀가 필요하면 기존 환경을 보존하고
[v0.5.0 설치 문서](../v0.5.0/README.md)에 따라 별도 설치한다. 임의 flash recover나 보안 해제는 사용하지 않는다.
