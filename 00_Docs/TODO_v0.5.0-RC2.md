# v0.5.0-rc.2 사용자 경험 교정 계획

이 문서는 공개 `v0.5.0-rc.1` 사용 과정에서 확인한 Arduino IDE 사용자 경험 문제를
`0.5.0-RC2` branch에서 교정하기 위한 실행 계약이다. Branch는 2026-09-27에
`main`의 `7b8692441f92c9d5b93d2613f6c8c50312992519`에서 분기했다.

현재 stable·지원 버전은 `v0.4.1`, 공개 시험 후보는 `v0.5.0-rc.1`이다. 이 계획 작성과
branch 생성은 `v0.5.0-rc.2` tag·GitHub Release·RC catalog 공개 승인이 아니다. 기존
RC1 tag·Release·자산·검증 기록과 `0.5.0-RC1` branch는 변경하지 않는다.

## 1. 현재 확인한 문제

| ID | 문제 | 현재 근거 | RC2 완료 기준 |
| --- | --- | --- | --- |
| RC2-UX-01 | 예제별 Feature set 안내 부족 | 공개 예제 113개 중 `.ino`에서 Feature set을 직접 안내하는 것은 실질적으로 4개 | 설치본의 모든 공개 예제가 Arduino IDE에서 바로 확인 가능한 정확한 기본 Feature set을 안내 |
| RC2-UX-02 | 호환 profile과 기본 권장 profile의 구분 부족 | Channel Sounding은 `adaptive`·`ble` 모두 호환되지만 예제에는 권장값·실험적 대안 설명이 없음 | 기본 권장값, 허용 대안, 실험/전용 여부를 예제와 공통 안내에서 일치시킴 |
| RC2-UX-03 | 예제 준비 조건이 흩어짐 | 보드 수·역할·115200 baud·sidecar 유지 조건이 일부 README에만 존재 | `.ino` 첫 설명에서 Board·Feature set·보드 수/역할·Serial·필수 sidecar를 확인 가능 |
| RC2-UP-01 | 두 pyOCD 메뉴의 차이가 불명확 | 자동 단일 probe 선택과 명시 UID 선택이 서로 다른 flasher처럼 보임 | 메뉴 이름과 문서가 한 대/여러 대 선택 기준을 직접 설명 |
| RC2-UP-02 | UID 입력 경로가 불명확하거나 IDE에서 유효값을 받지 못함 | 실제 UID 대신 `CMSIS-DAP unique ID` 안내 문자열이 uploader에 전달됨 | Arduino IDE 2.x에서 대상 UID가 확실히 전달되거나, 지원하지 않는 UI 경로를 노출하지 않고 안전한 대안을 제공 |
| RC2-UP-03 | UID placeholder 사전 검증 없음 | 안내 문자열을 실제 UID처럼 조회한 뒤 `E_PROBE_NOT_FOUND` 발생 | placeholder·빈 값·잘못된 형식을 flash 전에 거부하고 바로 실행 가능한 해결 방법 출력 |
| RC2-UP-04 | UID·COM·보드 역할 대응 안내 부족 | 여러 보드 예제에서 Initiator/Reflector와 probe/COM 매핑 절차가 없음 | 원시 UID를 공개하지 않고 대상 보드·역할·COM을 구분하는 절차 제공 |
| RC2-UP-05 | 원시 probe UID 노출 | 오류와 `NU54_UPLOAD_START`가 전체 UID를 console/log에 출력 | 사용자 표시·공유 로그는 기본 마스킹하고 내부 exact 선택에는 전체 값을 유지 |
| RC2-DIAG-01 | Windows Arduino IDE에서 한국어 오류가 깨짐 | CP949 바이트가 UTF-8로 해석된 형태의 `��` 출력 재현 로그가 있음 | 기본/상세 출력과 성공/실패 경로에서 한국어 UTF-8 표시, byte-level 회귀 검사 통과 |
| RC2-DIAG-02 | 상위 오류가 실제 원인을 가림 | SWD `No ACK`도 포괄적인 `E_FLASH_WRITE`로 끝남 | probe 선택·접속·SWD 무응답·flash 실행 실패를 구분하고 첫 원인과 안전한 다음 조치 출력 |
| RC2-DIAG-03 | 안전한 `No ACK` 진단 경로 부족 | Arduino 메뉴에는 저속 SWD·under-reset 진단 경로가 없고 일반 사용자가 원인을 분리하기 어려움 | 전원·`DISABLE_SWD`·점유·저전력 상태를 순서대로 확인하고 필요 시 비파괴 저속/under-reset 진단을 명시적으로 실행 가능 |
| RC2-BUILD-01 | Verify 중 진행 상태가 보이지 않음 | 장시간 Zephyr configure/build 동안 기본 Arduino console이 사실상 무응답 | verbose 설정 없이 단계·경과 시간·가능한 compile 분모를 주기적으로 표시하고 완료/실패 단계 명시 |
| RC2-CI-01 | GitHub Actions 전체 검증이 약 1시간 이상 소요 | 성공한 RC1 run `36253017005`는 약 57분이며 8개 예제 shard의 compile 단계가 각각 약 44~49분으로 병목. Main은 현재 113개 예제를 단일 Windows job에서 다시 빌드하고 과거 제품군도 매 push마다 실행 | 검증 분모를 줄이지 않고 중복·불균형·무효 cache·과도한 artifact를 제거해 일반 변경의 빠른 feedback과 RC 전수 gate를 분리 |
| RC2-QA-01 | 사용자 안내를 검사하는 gate 없음 | 설치 예제 compile은 profile별로 검사하지만 `.ino` 설정 안내의 존재·정확성은 검사하지 않음 | 예제 metadata와 사용자 표시 안내의 누락·불일치를 CI/Host test가 거부 |

## 2. 예제별 설정 계약

모든 공개 예제는 사용자가 Arduino IDE에서 `.ino`를 연 직후 다음 항목을 확인할 수 있어야 한다.
별도 README는 상세 설명을 제공할 수 있지만 필수 빌드 설정의 유일한 위치가 되어서는 안 된다.

1. `Board: NU54DK (nRF54L15, Zephyr)`
2. 기본 권장 `Tools → Feature set`
3. 허용되는 대안 profile과 `experimental`·전용 layout 여부
4. 필요한 보드 수와 각 보드의 역할
5. 한 대/여러 대 연결 시 `Tools → Upload probe` 선택법
6. Serial Monitor 속도와 관측할 대표 출력
7. `.ino`와 함께 유지해야 하는 `nucode-build.json`·`prj.conf`·`app.overlay`·`sysbuild` 파일

기본 profile 매핑은 다음과 같이 고정한다. 실제 feature manifest가 더 넓은 호환목록을 제공해도
사용자 권장값과 같은 뜻으로 취급하지 않는다.

| 예제군 | 기본 권장 Feature set | 대안·주의 |
| --- | --- | --- |
| 기본 Arduino·Storage | `Standard peripherals` | 기본값 |
| BLE GAP/GATT/NUS/CoC·Direction Finding·Channel Sounding 등 | `BLE NUS` | metadata로 허용된 경우에만 `Adaptive capabilities (experimental)`을 실험적 대안으로 안내 |
| 역할·용량 기반 최소 구성 실험 | `Adaptive capabilities (experimental)` | 기본 stable profile로 표현하지 않음 |
| Peripheral Fabric | `Peripheral Fabric (DAP UART disconnected)` | DAP UART 공유 핀 조건 안내 |
| Secure BLE DFU | `Secure BLE DFU (MCUboot)` | 전용 layout·외부 signing key·sysbuild 조건 안내 |
| 외장 PDM/I2S Audio | `BLE Audio external I/O (DAP UART disconnected)` | 외장 결선과 DAP UART 조건 안내 |

113개 `.ino`를 손으로 서로 다르게 적어 drift를 만들지 않는다. 예제 identity별 단일 metadata에서
권장 profile·대안·보드 수·역할·sidecar·Serial 정보를 관리하고, 표시 주석 또는 동반 문서를
검사하는 방식을 우선한다. 생성 파일이면 원본과 생성기를 함께 수정한다.

## 3. Upload probe 교정 계약

- 온보드 probe 한 대만 연결했을 때는 `CMSIS-DAP (pyOCD)`가 입력 없이 그 한 대를 선택한다.
- 여러 CMSIS-DAP가 연결됐을 때는 임의 첫 probe를 고르지 않는다. 명시적으로 대상을 선택하고
  잘못된 보드에 flash하지 않도록 fail-closed를 유지한다.
- `CMSIS-DAP with UID (pyOCD)`를 계속 제공하려면 Arduino IDE 2.x의 실제 upload field 입력·보존·
  전달을 설치본에서 검증한다. IDE가 해당 field를 신뢰성 있게 제공하지 않으면 이름만 남겨 두지 않고
  검증된 대체 UX를 설계한다.
- `CMSIS-DAP unique ID`와 `J-Link serial number` 같은 label/placeholder는 유효한 식별자가 아니다.
  Builder는 이를 flash 명령 생성 전에 구체적인 오류로 거부한다.
- `SEGGER J-Link`는 외장 J-Link와 target SWD/VTref/GND를 실제로 연결한 경우에만 사용한다고 표시한다.
- console·일반 log·문서에서는 probe identity를 마스킹한다. 내부 target 선택과 증거의 보호된 원본은
  exact identity를 유지하되 공개 출력과 분리한다.
- 자동 mass erase·unlock·recover는 추가하지 않는다. `auto_unlock=false`, sector flash와 대상
  fail-closed 정책을 유지한다.

## 4. 오류 표시와 SWD 진단 계약

### UTF-8

Windows Arduino IDE 2.x, `arduino-cli`, 직접 launcher의 stdout/stderr를 각각 byte 단위로 검사한다.
Source가 UTF-8이라는 사실이나 launcher의 `PYTHONUTF8=1` 설정만으로 완료 처리하지 않는다. 설치된
RC package에서 한국어 성공·경고·오류가 실제로 깨지지 않아야 한다. 지원하기 어려운 console 경로는
안정적인 영문 오류 코드와 ASCII 요약을 먼저 표시하고 상세 한글의 인코딩을 별도로 보장한다.

### 오류 분류

상위 오류는 최소한 다음 원인을 구분한다.

- probe 없음·여러 probe ambiguity·요청 UID 불일치
- probe는 열거됐지만 target SWD가 응답하지 않는 `No ACK`
- runner/tool 미설치 또는 점유
- target 접속 뒤 erase/program/verify 단계 실패
- build artifact·manifest·profile 불일치

`No ACK`에서는 데이터 USB cable·target 전원·debug-control `DISABLE_SWD`·다른 debugger 점유를
먼저 확인한다. 필요할 때만 낮은 SWD 주파수와 under-reset/halt를 비파괴 진단으로 제공한다.
접속 성공과 flash 성공을 분리해 보고하며 진단이 자동 erase/recover로 확대되지 않게 한다.

## 5. Verify 진행 표시 계약

Arduino IDE의 기본 **Verify**에서도 긴 무출력 구간이 없어야 한다. 상세 compiler command를 모두
노출하지 않고 다음과 같은 안정적인 단계 표시를 기본으로 한다.

```text
[NU54 1/5] 환경과 Feature set 확인
[NU54 2/5] Zephyr 구성 준비 (cache hit 또는 configure)
[NU54 3/5] 소스 컴파일 중: 84/312, 18초
[NU54 4/5] 링크와 firmware 생성
[NU54 5/5] 산출물·메모리 검증 완료: 42초
```

- 실제 분모를 알 수 있을 때만 `완료/전체`를 표시한다. 알 수 없으면 가짜 퍼센트 대신 단계와 경과
  시간을 표시한다.
- 장기 단계는 최대 10~15초마다 한 줄의 heartbeat를 제공한다.
- cache hit, configure 재실행, compile, link, artifact 검증을 구분한다.
- 동일 상태를 지나치게 반복하거나 compiler command 전체를 기본 출력에 쏟지 않는다.
- verbose 모드는 상세 west/CMake/Ninja 출력을 계속 제공하고 기본 표시와 판정이 충돌하지 않게 한다.
- Arduino IDE가 stdout과 stderr 중 무엇을 기본 console에 표시하는지 설치본에서 확인하고,
  **실제 IDE 화면에 보이는 결과**를 완료 기준으로 삼는다.
- 중단·실패 시 마지막 단계, 경과 시간, 안정적인 오류 코드와 log 위치를 남긴다.

## 6. GitHub Actions 실행시간 교정

전체 검증을 생략해 시간을 줄이지 않는다. 동일 exact commit에서 같은 113개 예제를 여러 workflow가
중복 빌드하는 구조와, 변경 종류와 무관한 과거 제품군 전수 실행을 먼저 제거한다.

최근 성공한 `M31 W08 Windows RC` run `36253017005`의 wall time은 약 57분이다. Package 재현은
약 1분 22초, lifecycle은 약 18분이었고, 8개 설치 예제 shard는 약 48~55분이었다. 각 shard의
실제 compile 단계만 약 44~49분이므로 setup보다 113개 clean compile이 지배적이다. 현재 main의
`M12 Reproducible Builds`는 v0.5.0 113개를 다시 단일 Windows job에서 실행하고 v0.1.0~v0.4.0
제품군도 매 push마다 실행한다. 이 둘을 그대로 유지한 채 runner 수만 늘리지 않는다.

### 개선 원칙

1. **빠른 gate와 전수 RC gate 분리:** PR·일반 push는 변경 분류와 대표 profile build로 빠른
   feedback을 제공하고, 113/113·설치 수명주기·재현 패키지는 RC candidate exact commit 또는
   명시적 manual run에서 수행한다.
2. **113개 전수 build 중복 제거:** 같은 exact commit의 전수 compile 결과를 한 workflow가 소유하고
   다른 workflow는 검증된 artifact/evidence를 소비한다. M12와 RC workflow가 각각 113개를 다시
   빌드하지 않는다.
3. **변경 영향 분류:** 문서만 바뀐 commit은 문서·계약·예제 안내 gate를 실행한다. Core·Builder·
   profile·library·board·package 입력이 바뀌면 해당 대표 build와 전수 RC gate를 승격한다.
   Path filter만 믿지 않고 변경 분류 unit test로 누락을 막는다.
4. **부하 기반 shard:** 단순 `sorted position modulo` 대신 이전 evidence의 example elapsed time과
   profile/library cache 친화도를 사용해 shard 예상 시간을 균등화한다. 새 예제는 보수적 기본
   가중치를 사용하고 모든 identity가 정확히 한 shard에 포함되는지 검사한다.
5. **병렬도 benchmark:** 8 shard 내부 2 worker, 12~16 shard, profile/library 군집 배치를 각각
   비교한다. Windows runner의 CPU·RAM·cache lock과 Actions 동시 실행 한도를 측정한 뒤 wall time과
   총 runner-minute의 균형이 가장 좋은 구성을 채택한다.
6. **갱신 가능한 cache key:** 현재 lock-only 고정 key처럼 최초 cache가 계속 고정되지 않도록
   toolchain/SDK 불변 cache와 source/config/ccache 가변 cache를 분리한다. Exact key에는 source
   fingerprint를 넣고 제한된 `restore-keys`로 이전 cache를 seed한 뒤 새 cache를 저장한다.
7. **Artifact 최소화:** 성공 시 manifest·요약·hash·필수 log만 업로드한다. 재생성 가능한 build tree는
   제외하고 실패 시 진단 log를 추가한다. 이미 압축된 파일에는 불필요한 재압축을 하지 않으며
   artifact upload가 장시간 멈추지 않도록 크기·파일 수·timeout을 검사한다.
8. **과거 제품군 실행 주기 조정:** v0.1.0~v0.4.0 호환성은 삭제하지 않고 nightly/manual 또는
   release gate로 이동한다. 현재 제품선 변경이 실제로 과거 계약에 영향을 주는 경우에는 자동으로
   승격한다.
9. **취소·timeout·진행 표시:** 동일 branch의 이전 run은 안전하게 취소하고, job/step별 현실적인
   timeout과 heartbeat를 둔다. Queue 시간과 실제 실행 시간을 분리해 기록한다.

### 목표와 판정

- Runner 대기 시간을 제외한 일반 PR/branch의 필수 feedback 목표는 **20분 이내**다.
- Runner 대기 시간을 제외한 RC 113/113·package·lifecycle 전수 wall time의 1차 목표는
  **40분 이내**다. 실제 benchmark 없이 성공으로 기록하거나 coverage를 줄여 목표를 맞추지 않는다.
- 모든 공개 예제 113개, 여섯 profile 대표, package byte 재현, lifecycle 분모와 실패 원본은 유지한다.
- 최종 선택 전 기존 8-shard 기준과 후보별 wall time·runner-minute·cache hit·최장 shard를 같은
  exact source에서 비교한다.

## 7. 실행 순서

| 단계 | 상태 | 작업 | 완료 조건 |
| --- | --- | --- | --- |
| RC2-01 범위·재현 | 진행 전 | RC1 설치본에서 예제 안내, UID placeholder, UTF-8, Verify 무출력과 `No ACK` 진단 경계를 재현 | IDE/CLI/version/입력/첫 오류와 실제 출력 byte를 기록 |
| RC2-02 metadata·예제 안내 | 진행 전 | 113개 예제의 profile·역할·보드 수·sidecar·Serial 단일 원본과 사용자 표시 추가 | 누락·불일치 0, 예제 audit PASS |
| RC2-03 probe UX·오류 | 진행 전 | 메뉴 문구, UID 전달·검증·마스킹, 오류 분류와 안전한 SWD 진단 개선 | 한 대/여러 대/잘못된 UID/No ACK negative가 예상 코드와 조치 출력 |
| RC2-04 UTF-8·진행 표시 | 진행 전 | launcher/Builder 출력 인코딩과 Verify 단계·heartbeat 구현 | Windows IDE 기본 화면과 CLI에서 깨짐·장기 무출력 0 |
| RC2-05 CI 실행시간 교정 | 진행 전 | 중복 제거·변경 분류·부하 기반 shard·cache/artifact 최적화 benchmark | coverage 유지, 일반 feedback·전수 RC wall time 목표를 exact run으로 판정 |
| RC2-06 변경 영향 회귀 | 진행 전 | Host/unit, profile matrix, 설치 예제 113개와 대표 build/upload 재검증 | Host·문서·전체 설치 예제 PASS; 실제 upload는 조건과 결과를 별도 기록 |
| RC2-07 패키지·공개 준비 | 진행 전 | RC2 archive/index 재현성, clean 설치·수명주기·문서 정합 | exact package 근거와 공개 전 승인 자료 준비 |
| RC2-08 공개 | 승인 대기 | 별도 사용자 승인 뒤 tag·Pre-release·RC catalog와 공개 다운로드 smoke | 승인 exact source/asset만 공개하고 공개 URL 재검증 |

## 8. 검증 분모

최소 자동 검사는 다음 범위를 포함한다.

- 모든 공개 예제 identity와 사용자 설정 metadata 113/113
- `standard`, `ble`, `adaptive`, `fabric`, `secure_ble_dfu`, `ble_audio_io` 대표 clean/cache-hit build
- Blink, NUS Central/Peripheral, Channel Sounding Initiator/Reflector의 Arduino IDE 기본 출력
- probe 0대·1대·2대, 잘못된 UID·placeholder·J-Link 미설치 negative
- stdout/stderr의 ASCII·한국어 UTF-8 success/warning/error fixture
- configure/build heartbeat와 완료/실패/사용자 중단 경로
- 문서 링크·생성 문서·package inventory·기존 Host 회귀

실제 보드 결과는 `PASS`, `FAIL`, `HOLD`, `NOT RUN`, `UNSUPPORTED`로 기록한다. Host/mock/build를
물리 PASS로 기록하지 않는다. Channel Sounding의 정밀 거리 보정, 제품 SDC DF IQ RX, M32/M33와
보류한 HOST-W04~W08은 RC2 사용자 경험 교정 범위에 새로 합산하지 않는다.

## 9. 마감과 공개 경계

RC2 구현이 끝나면 변경 영향에 맞는 Host·build·국소 HIL, 설치본 Arduino IDE 확인, 문서와
evidence를 갱신하고 exact commit을 고정한다. Branch push나 CI 실행은 tag·Release 공개가 아니다.
`v0.5.0-rc.2` tag·Pre-release·RC catalog 갱신과 공개 다운로드 smoke는 별도 사용자 승인 뒤에만
수행한다. 정식 `v0.5.0` stable tag·Release·root catalog는 그 이후에도 별도 승인 대상이다.
