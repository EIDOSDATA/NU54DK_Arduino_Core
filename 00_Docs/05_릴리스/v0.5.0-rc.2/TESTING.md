# v0.5.0-rc.2 검증과 Arduino GUI 확인 목록

> **보존 문서·지원 종료:** 현재 정식 설치·지원 버전은 [v0.5.0](../v0.5.0/README.md) 하나입니다.
> 아래 지원 범위·설치 명령·검증 결과·예정 작업은 `v0.5.0-rc.2` 작성 당시의 기록이며 현행 설치 안내가 아닙니다.
> 이 버전은 지원·stable catalog 공급 대상이 아니며, 당시 판정·source·자산 식별값은 보존합니다.

## 완료한 자동·실물 검증

고정 Core source는 `b2e7a587ba6fde31e033dc21008d7084bd6e631b`다.
이후 main 문서 commit의 검사를 runtime 전체 재검증으로 계산하지 않는다.

| 검사 | 결과·범위 |
| --- | --- |
| [M12 CI](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/36287748591) | attempt 2, 9/9 job 성공; 대표 job 24분 20초, 시간 목표 FAIL |
| [Full RC CI](https://github.com/EIDOSDATA/NU54DK_Arduino_Core/actions/runs/36287748550) | attempt 2, 11/11 job 성공; 동일 package 설치 예제 113/113, 누락/중복/최종 실패 0 |
| Package 재현 | 두 독립 생성의 archive·manifest·SBOM·license/notices·checksum 일치 |
| 설치 수명주기 | RC1→RC2 upgrade·uninstall·reinstall PASS, SDK/cache 경계 유지 |
| 대표 실제 HIL | 최종 package의 M8 sector upload 1회·UART ready PASS, auto_unlock=false |
| 다중 probe negative | 실제 복수 probe에서 E_PROBE_AMBIGUOUS, exit 1, flash false |
| 로컬 성능 | 여섯 profile × cold/cache-hit/Sketch 수정, 18회 PASS; 별도 앞선 source 측정 |

Full RC의 첫 실행에서 SDK 설치가 정체한 worker 0/3을 중단했고, 실패 job만 재실행했다.
다른 6개 shard의 성공은 재사용했다. 최종 compile bounded retry는 1회이며 무재시도 성공으로 기록하지 않는다.
세부 source별 원본과 역사 Host 분모는 [271번 기록](<../../04_검증 기록/271_v0.5.0-rc.2_사용자경험_교정과_검증.md>)에 있다.

## 사용자 Arduino IDE 2.x GUI 시험

다음 항목 중 체크되지 않은 항목은 아직 GUI PASS가 아니다. 실행 결과·IDE 버전·선택값·첫 오류/화면을 남긴다.

- [ ] [설치 URL](README.md)을 추가하고 Boards Manager에서 0.5.0-rc.2가 보이며 설치된다.
- [ ] 보드, Feature set과 두 Upload probe 메뉴가 안내와 일치한다.
- [ ] Blink를 Standard peripherals에서 Verify하고 단계·진행 메시지·최종 메모리 사용량을 확인한다.
- [x] 한 probe 구성에서 Blink Upload·LED 점멸을 확인한다. 공개 RC2의 첫 250 ms Upload는 PASS했다.
- [x] main 후속 PM 교정 설치본에서 250 ms → 100 ms 수정 Upload를 USB 재연결 없이 연속 수행한다.
- [ ] Serial 예제의 대응 COM/115200과 한국어 진단에 깨진 문자/대체 문자가 없는지 확인한다.
- [ ] NUS Central/Peripheral을 `.ino` 안내의 BLE NUS 설정으로 각각 Verify하고 역할별 통신을 확인한다.
- [ ] RasInitiator/RasReflector를 각 예제의 Feature set/sidecar로 Verify하고 역할을 구분해 업로드한다.
- [ ] 두 probe에서 대상을 지정하지 않으면 명확한 선택 오류로 중단되며 임의 flash하지 않는다.
- [ ] 잘못된 Feature set·UID 자리표시자/불일치·J-Link 미설치에서 실제 첫 오류가 읽기 쉽게 표시된다.
- [ ] 무변경 Verify·Sketch 본문 수정 Verify에서 cache 재사용과 진행 표시를 확인한다.

Probe 식별은 업로드 직전에 확인한다. COM 선택만으로 SWD 대상이 선택됐다고 판단하지 않는다.
자동 unlock/recover/mass erase·임의 결선/전원 변경은 하지 않는다. 역할별 외장 장치 미검증은 별도 남긴다.

## 공개 후 확인

공개 자산 7개 재다운로드의 size/SHA-256 일치, 공개 index를 이용한 격리 CLI 1.5.1 설치,
설치 payload 파일 633/633개 일치·예제 113개 발견·Standard Blink compile exit 0을 확인했다.
FLASH 81,528 bytes, RAM 29,439 bytes이며 기존 SDK/toolchain을 재사용했고 추가 flash는 하지 않았다.
로컬 PowerShell 시험 보조 script 재시작 2건과 adapter state-recovery 1회도 숨기지 않고
[272번 기록](<../../04_검증 기록/272_RC2_사용자_수용과_main_통합_및_시험배포.md>)과 증거에 남겼다.
이 CLI 결과는 위 GUI 체크리스트의 PASS가 아니다. 문서 main commit의 CI는 별도 exact SHA로 확인한다.
사용자 GUI 결과가 들어오면 원래 NOT RUN을 지우지 말고 IDE 버전·날짜·package SHA와 새 결과를 추가한다.

## 공개 후 사용자 GUI 연속 Upload 결과

2026-09-27 사용자 GUI 시험에서 공개 RC2 Standard Blink의 첫 250 ms Upload와 실행은 성공했으나,
100 ms로 수정한 두 번째 Upload는 pyOCD `SWD/JTAG communication failure (No ACK)`로 실패했다.
USB 재연결 뒤 같은 100 ms image가 성공하여 compile·HEX 문제가 아닌 실행 중 target 상태 문제로 좁혔다.
같은 보드 DTS의 Zephyr 기본 Blink와 비교해 Arduino Standard에만 존재하던
`CONFIG_PM_DEVICE_RUNTIME_DEFAULT_ENABLE=y`를 제거한 설치본에서는 250 ms → 100 ms 연속 Upload가
USB 재연결 없이 성공했다. IDE 정확한 버전과 화면 캡처는 수집하지 않았으므로 다른 GUI 항목은 계속
NOT RUN으로 유지한다. 세부 판정은 [273번 기록](<../../04_검증 기록/273_RC2_GUI_연속_Upload_Runtime_PM_교정.md>)을 따른다.
