# v0.5.0-rc.2 문제 해결

> **보존 문서·지원 종료:** 현재 정식 설치·지원 버전은 [v0.5.0](../v0.5.0/README.md) 하나입니다.
> 아래 지원 범위·설치 명령·검증 결과·예정 작업은 `v0.5.0-rc.2` 작성 당시의 기록이며 현행 설치 안내가 아닙니다.
> 이 버전은 지원·stable catalog 공급 대상이 아니며, 당시 판정·source·자산 식별값은 보존합니다.

먼저 [설치 안내](README.md)와 예제 `.ino` 상단의 설정을 확인한다.
설치 prerequisite·proxy·권한의 기본 진단은 [RC1 문제 해결](../v0.5.0-rc.1/TROUBLESHOOTING.md)을 참고하되,
RC2에는 아래 메뉴/UID 계약을 우선 적용한다.

| 증상 | 확인할 내용 |
| --- | --- |
| RC2가 보이지 않음 | RC1이 아닌 RC2 release의 index URL인지, Boards Manager 검색/버전 목록과 네트워크 접근 확인 |
| 예제 compile이 설정 오류로 중단 | `.ino` 상단 Feature set, `nucode-build.json`·Kconfig/overlay가 예제 폴더에 함께 있는지 확인 |
| Verify가 오래 걸림 | 최초 SDK/configure는 오래 걸릴 수 있음. 단계/heartbeat·CPU/디스크 활동·첫 실패를 보존; 시간 목표 달성 보증 없음 |
| 한글 깨짐 | IDE/CLI 버전과 원본 출력 byte를 수집. RC2 launcher는 UTF-8을 사용하지만 실제 GUI 렌더링은 사용자 확인 대상 |
| E_PROBE_AMBIGUOUS | probe가 복수이고 UID 미지정. 자동으로 첫 장비를 고르지 않는 정상 안전 차단 |
| UID placeholder/invalid/mismatch | 문서의 예시 문자열 대신 실제 대상 UID를 사용. 공백·다른 probe UID·환경 변수 상속 여부 확인 |
| SWD No ACK/접근 실패 | 대상 전원·SWD 차단 스위치·VTref/GND·probe 종류 확인. 자동 unlock/recover/mass erase로 우회하지 않음 |
| 첫 Upload 뒤 수정한 Sketch의 두 번째 Upload만 `E_SWD_NO_ACK` | 공개 RC2 Standard profile의 전역 runtime PM 자동 enable 재현 가능. USB 재연결은 일시 복구일 뿐이며, main 후속 교정은 `CONFIG_PM_DEVICE_RUNTIME_DEFAULT_ENABLE=n`으로 전체 자동 suspend를 끔 |
| J-Link 실행 파일 없음 | 온보드 CMSIS-DAP에는 pyOCD 메뉴 사용. 외부 J-Link는 실제 장비·별도 소프트웨어/결선 필요 |
| COM을 골라도 다른 probe 오류 | COM은 Serial용이며 SWD 대상은 별도 UID 선택 계약 |
| 긴 경로/재구성 실패 | 짧은 build/cache root에서 재현하고 첫 실패 로그 보존. 사용자 전체 cache/SDK를 무작정 삭제하지 않음 |

다중 CMSIS-DAP의 IDE 사용은 실제 `NUCODE_PROBE_UID`를 설정한 환경에서 IDE를 새로 실행해야 한다.
이미 열린 IDE는 새 환경 변수를 상속하지 않는다. UID를 공개 로그에 붙이지 않는다.
CLI 직접 선택과 safe SWD 세부 단계는 [업로드·디버그](<../../02_빌드 설계/05_업로드와_디버그.md>)에 있다.

온보드 probe에서 `under-reset` 진단은 DAPLink USB timeout과 인터페이스 소실을 일으킬 수 있으므로
이 증상의 일반 해결책으로 자동 실행하지 않는다. 사용자 GUI 확인에서는 수정 전 250 ms Blink의 첫 Upload가
성공하고 100 ms 변경 Upload가 No ACK로 실패했지만, 전역 runtime PM 자동 enable을 끈 설치본은
USB 재연결 없는 동일한 연속 Upload를 통과했다. 공개 RC2 archive는 고정되어 있으므로 이 교정은
main과 정식 [v0.5.0](../v0.5.0/README.md)에 포함됐으며 기존 RC2 재설치로 적용되지 않는다.

문제 보고에는 Boards Manager 버전 0.5.0-rc.2, Windows/IDE/CLI 버전, 예제 이름, Feature set,
probe 종류·보드 수·역할, 첫 오류와 재현 순서를 남긴다. 정상 출력처럼 보이는 마지막 몇 줄만으로
실패 원인을 판단하지 않는다. [Known issues](KNOWN_ISSUES.md)의 성능·GUI 미검증 상태도 함께 확인한다.
