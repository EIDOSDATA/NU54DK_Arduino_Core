# M24~M26 온보드 protocol 교정과 실기 재검증

| 항목 | 내용 |
| --- | --- |
| 문서 ID | VERIFY-V04-ONBOARD-FIX-001 |
| 기록일 | 2026-09-04 |
| 최종 시험 source | `51c1986242b60ac99df643ee4291946aa83b9986` |
| Board gitlink | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` |
| 판정 | **온보드 4개 runner PASS / 외부 fixture·최종 release gate HOLD** |
| 공개 상태 | `v0.3.0` 자산 불변, `v0.4.0` release HOLD |

## 1. 이전 실패에서 고친 내용

[앞선 USB·UART 진단](40_M24_M26_온보드_재개와_USB_UART_진단.md)의 실패를 소급 PASS로 바꾸지
않는다. 아래 변경을 새 commit으로 고정한 뒤 같은 DUT에서 재실행했다.

| Commit | 변경과 근거 |
| --- | --- |
| `f55bfa3` | M26 reset 준비 marker와 별도 결과 요청 도입; TWIM·M25 응답을 flash당 단발로 고정 |
| `d4b5bc6` | flash 직후 자동 reset/resume 금지; CPU reset·halt 확인 → 두 VCOM buffer 정리 → 명시적 resume |
| `5276f9a` | SAADC의 advanced non-blocking START와 SAMPLE 분리; READY 뒤 수동 SAMPLE 요청, nrfx가 소비하는 STOPPED 처리와 timeout 시 DMA lease 유지 |
| `6437682` | 꺼진 콘솔의 UART20 부팅 예약 제거; 콘솔 off인 정확한 DAP UARTE profile만 P1.4~P1.7 사용 허용 |
| `51c1986` | TWIM init 뒤 누락됐던 enable 전환 추가; 활성화 호출 순서의 source 회귀 검사 |

UART20 콘솔이 실제로 켜진 일반 profile에서는 기존 예약을 유지한다. P1 DAP pad의 공개 GPIO
capability를 넓히거나 connector 출력으로 전면 개방하지 않았다. 다른 serial personality와 DMA
RAM의 lease 충돌 검사도 그대로 유지한다.

M26 protocol v2의 예상 reset 구간은 최대 64바이트 prefix를 별도로 기록할 수 있지만, 최초 READY,
AR26, 최종 NU26은 정확히 32바이트여야 한다. 다른 VCOM 데이터, checksum 불일치, watchdog bit
누락, 지원 mask 밖 reset cause는 계속 실패다. 세부 계약은 [HIL 안내](../../tests/hil/nu54dk/README.md)를
따른다.

## 2. 환경과 재현 입력

- NCS `v3.4.0`, bundle `dcbdc366a1`, bundled Python `3.12.4`·pyOCD `0.42.0`.
- Host gate는 `C:\NU54DEV\venv\host-3.12.10\Scripts\python.exe`와 WinLibs GCC `16.1.0` 사용.
- Target child PATH는 공식 `environment.json`을 적용하고 외부 WinLibs를 제외했다.
- Bundled `pyocd.exe`도 `#!python.exe`에 따라 다른 PATH Python을 실행할 수 있음을 확인했다.
  실행 전에 interpreter와 module 경로를 검증했다. 절대 exe 경로만으로 재현 환경을 보장하지 않는다.
- Twister의 plain `c++filt` 요구는 bundled Arm demangler와 SHA-256가 같은 작업 폴더 hard link로 충족했다.
  SDK 파일, 전역 PATH, 보안 정책과 허용 목록은 수정하지 않았다.
- DUT는 기존 COM5/COM6에 한정했다. 두 번째 보드(COM7/COM8)의 firmware는 변경하지 않았다.
  UID 원문 대신 SHA-256 `32f71533ff6ba27fd38ed32a17bf6d80a90d4f4980221051ed5c5a2e7fdb63a9`를 기록한다.
- 모든 flash는 `auto_unlock=false`, sector erase, no-config를 사용했다. mass erase/recover는 하지 않았다.

최종 build root는 `C:\nb\05`다. `v0.4.0` 그룹 **18/18 build-only, failed 0, error 0,
warning 0, 409.91초**이며 target 실행 18건이라는 뜻이 아니다. 동일 source에서 Host 회귀 시험도
`M12_GATE_PASS=host`로 완료했다.

| 최종 로컬 log | 원본 SHA-256 |
| --- | --- |
| build.log | `a5132de8043b4f61ab8716df2defe7338b4e3883cf921ebcdd5226724cc93a7b` |
| host.log | `1f8df343be43c116dd4c5e16737d18cf83700f3c228a4d1c17454c48480deb8c` |

원본 log와 evidence는 작업 공간의 `work/v04-fixed-51c1986/`에 보존한다.

## 3. 정식 runner 결과

| Runner | 실제 결과 | Evidence |
| --- | --- | --- |
| M24 UARTE | 20/21/22는 P1 VCOM, 30은 P0 VCOM에서 각 32-byte EasyDMA 왕복 PASS | [UART JSON](evidence/51c1986/m24_uarte_onboard.json) |
| M24 TWIM | 20/21/22가 모두 BQ25186 주소 `0x6A`, register `0x0C`에서 `0x41` read-only PASS | [I2C JSON](evidence/51c1986/m24_twim_onboard.json) |
| M25 | EGU20→DPPIC20→TIMER20 `2003 ticks`, 내부 VDD SAADC raw `4092`, sample·stop PASS | [M25 JSON](evidence/51c1986/m25_onboard.json) |
| M26 | TEMP `2900` centi-°C, WDT30 configure/start/feed·reset, cause `0x10` PASS | [M26 JSON](evidence/51c1986/m26_onboard.json) |

모든 최초 READY·측정 결과는 선택 VCOM에만 정확한 32바이트가 도착했고 다른 VCOM은 조용했다.
M26의 **예상 reset 경계에서만** prefix `7f9fff97ff` 5바이트가 기록됐고, `1.922초` 뒤 정확한
RESET_READY에 이어 별도 request의 NU26을 검증했다. Reset 경계 신호가 전기적으로 무잡음이라는
판정은 아니다. 최종 시험 뒤 SWD CPUID `0x411fd210` 재읽기와 COM5/COM6 연결 유지도 확인했다.

M25의 `4092`는 12-bit raw code이며 full scale에 가깝다. 이 gate는 내부 입력의 DMA sample
수집·종료와 event 경로 확인이다. 교정된 VDD 전압, ADC 정확도·선형성·gain 범위 또는 외부
채널 전체 지원으로 해석하지 않는다. `stream_linked=1` 역시 handle 통합 확인일 뿐 PDM/I2S/QDEC
외부 신호 시험이 아니다.

| 원본 runner JSON | 원본 SHA-256 |
| --- | --- |
| m24_uarte_onboard.json | `4eaf70961069ddc2f8ddd980d06d3beecb69e8cf67da443965848304d70dae65` |
| m24_twim_onboard.json | `bd5d157ccf178c04337c62a0ef61a5c5a3aa78315b2917708465258b4640031a` |
| m25_onboard.json | `74acf00af630786c8fbcbb0fca963ea6691ebea3e8755c74b09e7ec8468e53c0` |
| m26_onboard.json | `2535bc67515e7e344091a0abfd38889106621924fbb7052b5e0e9fc69d8189de` |

저장소의 JSON 사본은 동일한 구조·값을 UTF-8/LF로 정규화했다. 위 checksum은 로컬 원본 기준이며
줄바꿈 정규화 뒤 Git blob의 byte checksum과 혼동하지 않는다.


## 4. 실패와 중단도 보존한 범위

- `d4b5bc6`의 M24 UART 첫 실행은 COM6 8,201바이트의 예상 밖 데이터로 실패했고, TWIM20은
  READY 무응답으로 실패했다. M25는 event ticks `2004`와 stream identity를 확인했지만 ADC
  sample `0`으로 실패했다. 이 실행들에 PASS JSON을 만들지 않았다.
- 같은 `d4b5bc6`의 M26은 별도로 정식 PASS했다. TEMP `2900` centi-°C, watchdog reset
  `0x10`, RESET_READY 대기 `1.938초`, prefix `0바이트`였다. 원본 evidence SHA-256는
  `fe58e51180e6bd2111cb1766bcaa2c04c95c7baa8da92ec7d6ee493541e5138f`다.
- `C:\nb\03`은 18/18 compile·link를 마쳤지만 build 도중 두 HIL source에 외부 서식 변경이
  들어왔다. 공백 외 동일함을 확인해 변경을 보존했으며, dirty-source 검사 때문에 formal HIL은
  실행하지 않았다. 이를 exact source의 실기 PASS로 사용하지 않는다.
- `C:\nb\04` build는 TWIM enable 누락을 발견한 뒤 명시적으로 취소했다. 완료 build로 세지 않는다.
- 요구사항을 설치하지 않은 standalone Python으로 시작한 Host 시험은 PyYAML 부재로 실패했다.
  이미 준비된 hash 고정 host venv로 재실행해 통과했다. 해당 실패를 firmware 결함으로 분류하지 않는다.

## 5. 남은 physical·release gate

외부 UART/SPI/TWIS peer·loopback, SAADC 외부 정확도와 PWM timing, PDM/I2S/QDEC 실제 신호,
최대 동시성·오류 주입·처리량·장시간 soak·CPU·전력은 이 온보드 PASS로 대체하지 않는다.
M24/M25 전체 완료, 모든 instance의 물리 지원, 새 공개 API 또는 BLE 확장 완료도 선언하지 않는다.

남은 fixture 결과를 결합한 뒤 frozen RC에서 Host·문서·target build·package 이중 재현,
설치본 전체 예제·upload·설치 수명주기를 다시 검증한다. 이전 비공개 package의 29/29 compile
기록은 [M27 자동 준비 기록](39_M27_v0.4.0_rc1_자동_준비와_HOLD.md)에 남기되 새 source의 최종
release gate로 대체하지 않는다. 태그·Release·Boards Manager index는 변경하지 않았다.

문서 반영 후 Markdown UTF-8·local-link 137개, CI contract unit 45개, 온보드 runner unit 25개,
clean checkout의 M27 unit 6개를 통과했다. Readiness ledger는 16개 필수 gate 중 8개가 남아 있으며,
이번 변경은 세 온보드 gate만 PASS로 올렸다. 외부 fixture와 frozen RC gate는 유지한다.
