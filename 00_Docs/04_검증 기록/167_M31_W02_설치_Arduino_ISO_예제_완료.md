# M31-W02 설치 Arduino ISO 예제 완료

> **현재 판정 정정(2026-09-17):** 이 기록의 무선 HIL·빌드 원본은 유효하지만,
> 공개 `.ino`의 사용자 payload 송수신 API가 빠져 W02 완료 판정은 취소했다.
> [191번 재점검](191_M31_W02_공개_ISO_예제_재점검.md)과 [M31 TODO](../TODO_M31.md)를 따른다.

2026-09-16 현재 M31-W02의 raw ISO 기능과 설치 가능한 Arduino 역할 예제를 모두 완료했다.
clean source `e6ae812eb18cb40ce2d9b178e59fa48c16ff3989`로 만든 private
`0.5.0-rc.1` package에서 11개 sketch를 발견·빌드했고, 그 image를 서로 다른 CMSIS-DAP V2
보드에 sector programming한 뒤 CIS·BIS·암호화·time sync·CIS→BIS 기능을 다시 실행했다.
W02는 2/8 작업 묶음으로 완료하며 `M31-ISO-01`은 기존과 같이 4/4 subcase PASS,
M31 test family는 3/10 PASS다.

## 설치 예제와 build 결과

| 범위 | 결과 |
| --- | --- |
| Package identity | core `e6ae812e…`, board `fe65f2f0…`, nrf `99553055…`, Zephyr `bf801e4e…`; package validate PASS |
| CIS | `CISCentral`, `CISPeripheral` 2/2 build PASS |
| BIS | `BISSource`, `BISReceiver`, `BISEncryptedSource`, `BISEncryptedReceiver` 4/4 build PASS |
| ISO time | `BISTimeSource`, `BISTimeReceiver` 2/2 build PASS |
| CIS→BIS | `CISToBISBridge`, `CISToBISPeer`, `CISToBISReceiver` 3/3 build PASS |
| 설치 예제 전수 감사 | bundled library 13개, sketch 72개, issue 0 |
| 별도 DFU 예제 | `SecureDfuPeripheral` 설치 package sysbuild PASS; NUS·Security·DFU feature와 인증 MCUmgr 설정 확인 |

[Arduino build manifest](evidence/m31-w02-arduino-e6ae812e/m31-arduino-build-manifest.json)는
11개 HEX hash, artifact manifest hash, FLASH/RAM, 선택 feature와 네 source revision을 보존한다.
동일 package의 [release manifest](evidence/m31-w02-arduino-e6ae812e/nucode-nu54dk-zephyr-0.5.0-rc.1.release-manifest.json)와
[checksums](evidence/m31-w02-arduino-e6ae812e/nucode-nu54dk-zephyr-0.5.0-rc.1.CHECKSUMS.sha256)도
함께 고정했다. `CISToBISReceiver`가 `BISReceiver`와 같은 검증 backend를 사용하는 경우처럼
의도한 공유 image는 manifest에서 같은 byte hash로 드러난다. wrapper sketch는 역할 macro만
선언하고 실제 raw ISO 구현은 설치 library header에 포함하므로, 전수 감사기는 wrapper와
검증된 backend의 byte 일치까지 검사한다.

## 실제 보드 결과

| 실행 case | 실제 결과 |
| --- | --- |
| CIS | 20회×100, 2,000 송신/2,000 수신, 회차 최저 100, 손상·중복·cross-stream 0 |
| BIS | 20회×100, 2,000 송신/1,996 수신, 회차 최저 99, 손상·중복·순서 오류 0 |
| 암호화 BIS | 20회×100, 2,000 송신/1,999 수신, 회차 최저 99, 손상·중복·순서 오류 0 |
| 잘못된 Broadcast Code | 암호화 payload 유출 0, 새 올바른 session 100/100 복구 |
| Sync loss | 의도한 peer loss 동안 payload 수락 0, 새 session 100/100 복구 |
| ISO time sync | 20회×100 수신 2,000/2,000, timestamp 단조 2,000, 명시적 timestamp 송신 1,980, stale callback 0 |
| CIS→BIS | 20회×100, peer 송신·CIS 수신·BIS 전달·receiver 수신 각각 2,000/2,000, 회차 최저 100 |

각 case의 JSON과 ASCII transcript는
[W02 Arduino exact evidence](evidence/m31-w02-arduino-e6ae812e/closure-audit.json)에서
child hash로 묶는다. 세 probe는 익명 SHA-256 identity로만 선택했고, DP/AP/APPROTECT를 실제로
읽었다. programming은 `--erase sector --no-reset` 뒤 CMSIS-DAP hardware reset을 별도 확인했다.
mass erase·recover는 수행하지 않았다.

## 실패 보존과 교정

직전 clean `f50a3ab4…`의 결합 실기는 세 역할 모두 20회×100을 완료해 2,000개를 끝까지
전달했지만 host envelope가 새 `pyocd-sector-hw-reset` 증거를 과거
`pyocd-sector` 문자열과 비교해 최종 상태를 FAIL로 기록했다. 이 시도의
[JSON](evidence/m31-w02-arduino-e6ae812e/failed-f50a-combined.json)과
[transcript](evidence/m31-w02-arduino-e6ae812e/failed-f50a-combined.transcript.log)을 보존했다.
validator가 명시적 hardware reset 증거만 수락하도록 고치고 Host 회귀를 추가했다. 이후 새 clean
commit과 새 package/image로 11개를 모두 재빌드하고 모든 실제 보드 case를 다시 실행했다.
이전 무선 성공 transcript를 새 commit의 완료 근거로 재사용하지 않았다.

## 판정 경계

W02는 raw ISO 경로만 닫는다. DFU sketch는 사용자가 지적한 비어 있는 예제를 보완하고 설치
package build까지 확인한 별도 품질 증거이며 W02 분자에 더하지 않는다. W03의 LC3와 BAP·CAP·
CSIP·PBP·VCP/MICP·MCP/CCP·TMAP/GMAP·HAP은 아직 완료가 아니며 다음 작업에서 profile별
source·native/Arduino build·기능 HIL·negative를 각각 판정한다.
