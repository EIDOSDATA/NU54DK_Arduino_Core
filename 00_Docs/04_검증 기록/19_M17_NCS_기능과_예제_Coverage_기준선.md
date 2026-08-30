# M17 NCS 기능과 예제 Coverage 기준선

| 항목 | 내용 |
| --- | --- |
| 문서 ID | VALIDATION-M17-001 |
| 문서 상태 | **M17 완료 — 후속 M18 RC2 재검증 진행** |
| 적용 제품 버전 | `v0.2.0` |
| 최종 갱신일 | 2026-08-30 |
| 작성자 | Quantum / NUCODE |
| M17 구현 Core | `46799034cca29858c22bc796ec06d886c9547249` |
| NCS | `v3.4.0`, `99553055607b2e9885fbc80ccd11fa9da81c2df0` |
| Zephyr | `4.4.0`, `bf801e4e3d19e1ffa76164346480cb7734dd2800` |
| Board package | `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3` — 변경 없음 |
| 공식 control target | `nrf54l15dk/nrf54l15/cpuapp` |
| NU54DK applicability target | `nrf54l15dk/nrf54l15/cpuapp/nu54dk` |

---

## 1. 완료 판정

M17은 NCS v3.4.0의 모든 기능을 Arduino wrapper로 구현하는 단계가 아니다. 선택한 기능을
machine-readable record로 만들고, 각 기능의 적절한 제공 경로와 실제 검증 수준을 정확히
분류하는 단계다.

다음 결과를 확보했으므로 M17은 **완료**다.

- exact NCS·Zephyr·board revision을 고정한 9개 coverage record
- record schema, source revision/path, license, evidence 경로와 manifest SHA-256의 fail-closed 검증
- deterministic JSON/Markdown summary 생성과 diff check
- 외부 Adafruit LSM6DS3TR-C Arduino library compile 검증
- Zephyr sensor direct와 NCS Crypto RNG의 NU54DK build 검증
- IEEE 802.15.4, OpenThread와 Matter의 공식 control/NU54DK 적용성 build 결과 분리
- networking 세 항목을 `deferred`·`build-feasibility-only`·v0.2.0 미지원으로 고정

M17 완료는 모든 record가 `supported` 또는 PASS라는 뜻이 아니다. NU54DK 적용 build 실패도
숨기지 않고 결과로 보존하며, compile 성공을 runtime·HIL·제품 지원으로 확대하지 않는다.

---

## 2. Coverage ledger

단일 원본은 [`coverage/ncs-v3.4.0`](../../coverage/ncs-v3.4.0)이다.

| 자산 | 역할 |
| --- | --- |
| [`manifest.json`](../../coverage/ncs-v3.4.0/manifest.json) | exact upstream pin과 record 경로·SHA-256 |
| [`records/`](../../coverage/ncs-v3.4.0/records) | 기능별 source, route, status, profile, hardware와 validation |
| [`generated/summary.json`](../../coverage/ncs-v3.4.0/generated/summary.json) | 도구가 생성한 deterministic machine summary |
| [`generated/summary.md`](../../coverage/ncs-v3.4.0/generated/summary.md) | 사람이 검토하는 deterministic 요약 |
| [`m17_coverage.py`](../../tools/coverage/m17_coverage.py) | strict validate/render/diff-check 진입점 |

Ledger의 9개 record는 다음 세 경계를 함께 표현한다.

| 상태 | record | 해석 |
| --- | --- | --- |
| `supported` | `board.system`, `nrf.ble-nus`, `zephyr.settings-storage` | 기존 M15/M16 구현과 HIL 증거가 연결된 지원 범위 |
| `build-only` | `arduino.adafruit-lsm6ds`, `zephyr.sensor-direct`, `nrf.crypto-rng` | compile/link 경로만 검증; semantic/runtime/HIL 또는 wrapper를 자동 추정하지 않음 |
| `deferred` | `nrf.802154-phy-test`, `nrf.openthread-cli`, `nrf.matter-template` | build feasibility 결과만 기록하며 v0.2.0에서 미지원 |

역사적 M15/M16 결과는 해당 기준선에 그대로 보존한다. M17은 기존 PASS를 다시 쓰거나 범위를
확대하지 않고 record evidence로 연결한다.

---

## 3. 외부 Arduino sensor library

[`m17-external-libraries.lock.json`](../../tools/ci/m17-external-libraries.lock.json)은 외부 archive의
버전, commit, license와 SHA-256을 고정한다. archive는 격리된 임시 경로에서 검증하며 저장소나
Core package에 vendoring하지 않는다.

| Library | 버전 | commit | license | archive SHA-256 |
| --- | --- | --- | --- | --- |
| Adafruit LSM6DS | 4.7.4 | `379a5204c0bad71264c3d635de84d0f9679ab784` | BSD-3-Clause | `098107002a2ff47fe2f4c4bc79f398f42a47bee253eebe3395924887557486a9` |
| Adafruit BusIO | 1.17.4 | `3b8364267c3ee6e16bad91bc2101aefbd5b5915f` | MIT | `e29b45a03874be4c054b04421073675efef5a950b2577b363cff8f17e90db26c` |
| Adafruit Unified Sensor | 1.1.15 | `0a9127a1e886ff1adb4c1b6f5958b24108d55aa6` | Apache-2.0 | `95556ec61cd92df3e15c450d8febed64284d0b5416ce3ac0891fab326130b3c7` |

[`m17_adafruit_lsm6ds_compile.ino`](../../tests/arduino-cli/m17_adafruit_lsm6ds_compile/m17_adafruit_lsm6ds_compile.ino)는
`Adafruit_LSM6DS3TRC`, `Wire`와 `SPI` header를 실제 Arduino build graph에 넣는다. 고정 archive로
LSM6DS3TR-C Sketch compile/link가 **PASS**했다.

| exact 재실행 항목 | 값 |
| --- | --- |
| Core | `46799034cca29858c22bc796ec06d886c9547249` |
| Evidence SHA-256 | `0a45309440068ba8c401a6ce4d2fb9de779cccf9fd47bbd8df7a1ae81f897de2` |
| Build log SHA-256 | `c3032ab1161d74a1f12691f4379323fecc7aa5d05d40f06156c0ebe3369343e6` |
| Zephyr memory report | FLASH 61,308 B / RAM 16,456 B |
| Arduino report | program 61,300 B / globals 16,481 B |

이 결과의 범위는 다음과 같다.

- 외부 library와 dependency의 source compile/link: **PASS**
- `Wire`/`SPI` feature 해석: **PASS**
- LSM6DS3TR-C 실제 장치 초기화·측정: **NOT RUN**
- sensor interrupt·FIFO·전원 mode HIL: **NOT RUN**
- NUCODE sensor wrapper/library 제공: **없음**
- package에 Adafruit source 포함: **없음**

따라서 record 상태는 `build-only`, 제공 경로는 `build-profile-only`다.

---

## 4. Sensor direct build

[`tests/zephyr/m17_sensor_direct`](../../tests/zephyr/m17_sensor_direct)은 Zephyr sensor API를 직접
사용하는 NU54DK build-only contract다. production board root와 고정 NCS/Zephyr graph에서
compile/link가 **PASS**했다.

이 결과는 direct/build example 경로가 유효하다는 증거다. Arduino sensor singleton, NUCODE
sensor library, 특정 외장 sensor의 DTS overlay 또는 실기 polling/trigger 동작은 검증하지 않았다.

---

## 5. NCS direct와 networking feasibility

[`run_m17_feasibility.py`](../../tools/ci/run_m17_feasibility.py)는 각 공식 NCS sample을 공식
nRF54L15 DK target과 NU54DK target에서 별도로 pristine sysbuild한다. 공식 target은 upstream
sample 자체와 환경을 확인하는 control이고, NU54DK target은 board 적용성을 확인한다.

| 항목 | 정책 | 공식 control | NU54DK applicability | M17 판정 |
| --- | --- | --- | --- | --- |
| `nrf/samples/crypto/rng` | build-only | **PASS** | **PASS** | NCS direct/build-only; Arduino crypto wrapper·HIL 없음 |
| `nrf/samples/peripheral/802154_phy_test` | deferred/build-feasibility-only | **PASS** | **FAIL** — NVMC type·instance·configuration symbol 오류 | v0.2.0 미지원 |
| `nrf/samples/openthread/cli` | deferred/build-feasibility-only | **PASS** | **PASS** | v0.2.0 미지원; network runtime/HIL 없음 |
| `nrf/samples/matter/template` | deferred/build-feasibility-only | **PASS** | **FAIL** — `factory_data_partition` 누락 | v0.2.0 미지원 |

### 5.1 IEEE 802.15.4 실패의 의미

공식 control build는 통과했지만 NU54DK build에서 sample의 NVMC 경로가 요구하는 symbol을
해결하지 못했다. 이는 M17에서 임의 register patch나 board submodule 변경으로 우회하지 않는다.
실패는 NU54DK 적용성 결과로 보존하고 후속 radio profile/board 지원 작업에서 재검토한다.

### 5.2 OpenThread PASS의 의미

공식 control과 NU54DK build가 모두 통과했다. 그러나 Thread network join, radio 송수신,
commissioning, multiprotocol coexistence와 Arduino facade는 실행하지 않았다. 따라서 build
feasibility PASS일 뿐 v0.2.0 정식 지원이 아니다.

### 5.3 Matter 실패의 의미

공식 control build는 통과했지만 NU54DK application graph에는 sample이 요구하는
`factory_data_partition`이 없다. M17에서는 임의 partition을 추가하거나 Matter product
profile을 선언하지 않는다. commissioning과 실제 Matter runtime도 실행하지 않았다.

---

## 6. 검증 명령과 exact 재실행 증거

M17 고정 runner는 다음 세 경로를 사용한다.

```powershell
python tools/coverage/m17_coverage.py validate
python tools/coverage/m17_coverage.py render --check
python tools/ci/run_m17_external_arduino.py --help
python tools/ci/run_m17_feasibility.py --help
python tools/ci/run_zephyr_build.py --help
```

다음은 M17 구현 commit에서 최종 exact 재실행으로 확정한 결과다.

| 증거 | 결과/값 |
| --- | --- |
| Coverage host/validate/render | host `21/21 PASS`; validate `records=9 PASS`; render check `PASS` |
| External Arduino compile log SHA-256 | `c3032ab1161d74a1f12691f4379323fecc7aa5d05d40f06156c0ebe3369343e6` |
| External Arduino evidence SHA-256 | `0a45309440068ba8c401a6ce4d2fb9de779cccf9fd47bbd8df7a1ae81f897de2` |
| Sensor direct build log/evidence SHA-256 | `bfe80a4f5b478a732295835acd38449beb67b2866a2805a6431e8cbb2f135c94` |
| Feasibility evidence SHA-256 | `1681a9032ea7160164efdab831627a5d825e4c437afe41496435a02f5ed983d9` |
| Generic Zephyr regression suite 수 | `14` |
| Generic Zephyr regression 결과 | `14/14 PASS` |
| Generic Zephyr regression evidence SHA-256 | `06ccfd8f31cb49687213d743f208a5a520f6af021a861511fa1433828737dbff` |

---

## 7. 범위 제외

다음은 M17에서 실행하지 않았거나 지원하지 않는다.

- LSM6DS3TR-C 실제 센서 runtime, interrupt, FIFO와 전기 HIL
- NUCODE sensor wrapper 또는 외부 sensor library 재배포
- Arduino crypto wrapper와 Crypto RNG semantic/HIL
- IEEE 802.15.4 PHY 송수신 HIL
- OpenThread network join·radio runtime과 Arduino facade
- Matter commissioning, factory data provisioning과 제품 partition profile
- Thread/Matter/802.15.4 정식 지원 선언과 multiprotocol
- board package 수정 또는 radio/partition 문제의 임시 우회

---

## 8. 다음 단계

M17 이후 단계는 M18이다. 자동화는 `v0.2.0-rc.1` package, checksum, SBOM, license inventory와
GitHub Draft Release까지 준비한다. Draft는 stable 공개가 아니다. 프로젝트 소유자가 clean
Windows Arduino IDE 설치·예제 열거·compile·NU54DK upload를 확인하고 알려진 제약과 공개를
승인하기 전에는 `v0.2.0` stable을 공개하지 않는다.
