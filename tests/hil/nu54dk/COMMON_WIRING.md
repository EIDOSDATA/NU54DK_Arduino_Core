# NU54DK v0.4.0 공통 결선과 연결 검사

2026-09-07. **신호 17개 + 공통 GND 1개, 총 18가닥.** 기존 PWM P1.14 선과 GND는 유지하고 16가닥을 추가한다.
사용자가 17신호+GND 그대로 결선을 완료했다고 확인했다. Fixture 501 결선 checker를 구현하고 Host/target을 검사했다. 실제 배선 PASS는 새 exact image로 실행한 원본 결과를 따른다. GPIO/GPIOTE/PWM/QDEC/I2S 전체 통합은 후속 작업이다.
현재 408/420/430 개별 확인서는 이 결선의 확인서가 아니다. `v04_common_fixture.json`의 501 revision 1과 새 exact image/UID hash를 사용한다.

## 보드 식별과 연결 절차

10:47:36 UTC(19:47:36 KST) 새 읽기 확인에서 A는 COM12/13, B는 COM14/15다. 두 exact UID와 0d7f382 role identity를 대조했고, reset/halt/flash 없이 CPUID·PWM off·DPPI off 및 양쪽 17개 신호의 입력 방향을 확인했다. COM은 이 관측의 값이며 재연결 뒤 다시 열거한다.
A UID SHA-256: `32f71533ff6ba27fd38ed32a17bf6d80a90d4f4980221051ed5c5a2e7fdb63a9`.
B UID SHA-256: `4574ee31f25fe05f154395ea4d8c6aa0583b04a4f7a0ea97fe3d13b05eea8ca0`.
COM 번호는 이 관측의 식별 보조 정보다. 재연결 뒤 exact UID를 다시 열거한다.

1. A/B 표시를 붙인 뒤 두 USB와 다른 전원을 모두 분리한다.
2. 아래 표의 선만 1:1로 연결한다. GPIO 이름이 기준이며 괄호는 connector 이름-접점 번호다. GPIO P2.04와 connector P2-4는 서로 다른 뜻이다.
3. 두 보드의 DAP UART는 분리, SWD는 연결 상태로 유지한다. LFXO·PMIC·SB 설정을 변경하지 않는다.
4. 각 보드는 자기 USB로만 전원을 공급하며 I/O 전압은 같아야 한다. VDD_MOD·3V3·VBAT·VBUS 등 전원 레일, 보드 간 SWD/RESET, 외부 저항과 다른 출력은 연결하지 않는다.
5. 결선 변경 중에는 전원을 분리하고, 완료 후 현재 결선을 확인해 fixture의 exact image 확인서를 만든다. 펌웨어는 부팅만으로 LOW 시험을 시작하지 않는다.

## 고정 결선표

| 선 | A GPIO (connector) | B GPIO (connector) | 사용 |
| --- | --- | --- | --- |
| 1 | P1.14 (P4-12) | P1.14 (P4-12) | PWM capture / QDEC phase A / GPIO·GPIOTE20 |
| 2 | P1.10 (P4-8) | P1.10 (P4-8) | QDEC phase B / GPIO·GPIOTE20 |
| 3 | P1.04 (P2-12) | P1.04 (P2-12) | I2S SCK / GPIO·GPIOTE20 |
| 4 | P1.05 (P2-11) | P1.05 (P2-11) | I2S LRCK / GPIO·GPIOTE20 |
| 5 | P1.06 (P2-10) | P1.07 (P2-9) | I2S A TX → B RX / GPIO·GPIOTE20 |
| 6 | P1.07 (P2-9) | P1.06 (P2-10) | I2S B TX → A RX / GPIO·GPIOTE20 |
| 7 | P0.00 (P2-25) | P0.00 (P2-25) | GPIO·GPIOTE30 |
| 8 | P0.01 (P2-26) | P0.01 (P2-26) | GPIO·GPIOTE30 |
| 9 | P0.02 (P4-4) | P0.02 (P4-4) | GPIO·GPIOTE30 |
| 10 | P0.03 (P4-5) | P0.03 (P4-5) | GPIO·GPIOTE30 |
| 11 | P2.00 (P4-19) | P2.00 (P4-19) | GPIO level / open-drain |
| 12 | P2.01 (P4-20) | P2.01 (P4-20) | GPIO level / open-drain |
| 13 | P2.02 (P4-21) | P2.02 (P4-21) | GPIO level / open-drain |
| 14 | P2.03 (P4-22) | P2.03 (P4-22) | GPIO level / open-drain |
| 15 | P2.04 (P2-17) | P2.04 (P2-17) | GPIO level / open-drain |
| 16 | P2.05 (P2-19) | P2.05 (P2-19) | GPIO level / open-drain |
| 17 | P2.06 (P2-20) | P2.06 (P2-20) | GPIO level / open-drain |
| 18 | GND (P2-30) | GND (P2-30) | 공통 기준 전위 |

**교차 연결은 P1.06 ↔ P1.07 두 선뿐**이다. 나머지 신호는 양쪽 같은 GPIO끼리 연결한다. 한 선을 여러 핀에 분기하지 않는다.
P1.10/P1.14는 각 보드 LED buffer의 입력에 연결된 net이다. LED driver 출력에 연결하는 것이 아니다.

## 시험 순서와 핀 재사용

| 단계 | 활성 핀 / 자원 | 관측과 판정 |
| --- | --- | --- |
| 초기 연결 검사 | 17개 net을 하나씩; 출력은 한쪽의 open-drain LOW만, 반대쪽 내부 pull-up | A→B와 B→A의 실제 핀 대응, stuck level, 다른 선으로의 누출 확인 후에만 push-pull 시험 허용 |
| GPIO | 연결된 P0 4개·P1 6개·P2 7개, 양방향 순차 | LOW/HIGH·입력·지원되는 open-drain·pull·해제 후 입력 복귀; 예약/지원 불가 mode의 거부는 별도 식별 |
| GPIOTE | P1의 GPIOTE20 가용 8채널, P0의 GPIOTE30 가용 4채널을 순차 재할당 | rising/falling/toggle, task SET/CLR, 100/1000Hz·1000edge·10회, 다른 채널 누출과 release 확인. P2는 GPIOTE PASS 대상이 아님 |
| PWM | B P1.14 출력 → A P1.14 capture; PWM20/21/22 slot 순차 | 로드·길이 축소 후보 675조건, 각 100주기·상대 ±5%·정적 0/100%; sequence0/1·finite end/repeat·DPPI START·triggered-step·idle inversion은 별도 시험 |
| QDEC | B P1.14/1.10 phase A/B → A P1.14/1.10 | QDEC20/21의 정·역·도중 역전·read/clear/restart·invalid transition·1000cycle·10ms·반복 조건. 기존 420의 A P1.04/1.06 입력을 새 경로로 옮겨야 함 |
| I2S | P1.04 SCK, P1.05 LRCK, P1.06/1.07 교차 data | master 한 대만, 역할 교대; 32/256/1024word·100개 연속 buffer·TX-only/RX-only·각 width/rate의 packing과 원본 frame 순서 확인. MCK 없음 |
| 종료 | 모든 연결 신호 입력, peripheral·DPPI 정지 | guard·DMA/pin lease 반환, 출력·구독·예약 잔류, 두 exact role/source identity와 완료/실패 원본 확인 |

시험은 위 순서대로 수행하고, 전환 전에 이전 출력과 DMA를 정지한 뒤 관련 pin/DPPI/GPIOTE lease를 반환한다. 반환이 증명되지 않으면 다음 시험을 시작하지 않는다. 통신 손실 시 독립 firmware timeout으로 출력이 해제되는 경로를 검증한다.

## 실행기와 남은 통합 준비

- 연결 검사용 Fixture 501 revision 1을 별도 catalog에 등록했다. 입력 pull-up과 한쪽 단일 open-drain LOW를 사용하며 LOW는 500ms, arm은 10초 제한이다. 기존 408/420/430/440의 의미와 역사 결과는 유지한다.
- 실행 시 SWD 10 MHz, exact UID, 배타 probe lock, sector flash와 auto_unlock=false, controlled reset/halt/identity/start를 유지한다. 새 firmware는 자동으로 외부 출력을 시작하지 않는다.
- QDEC는 `connector_fixture` profile로 A P1.14/1.10을 받아야 한다. 현재 `dap_uart_disabled` profile은 P1.04~07만 허용하므로 pin 상수만 바꾸면 실패한다.
- P1.04~07의 현재 HIL overlay는 input/output/analog만 허용한다. UART 분리가 확인된 전용 HIL에서 open-drain과 필요한 GPIO/IRQ capability·소유권을 검토하고 Host/target으로 검증한다. 제품 기본 정책을 무조건 완화하지 않는다.
- GPIO/GPIOTE 전용 명령·원본 관측, PWM sequence/trigger, I2S 연속·단방향, QDEC 추가 동작과 긴 명령 처리를 구현해야 한다. GPIO/GPIOTE·stream 전환을 현재 runner가 자동으로 지원하는 상태가 아니다.
- 현재 확인 유효시간 30분·firmware 10초 lease는 그대로 적용된다. QDEC 최장 1000cycle×4state×10ms=40초와 장시간 campaign에 맞는 bounded heartbeat/취소를 검증해야 한다. 무제한 확인서나 timeout 해제는 사용하지 않는다. 이 준비 전에는 한 번 확인으로 전체 무인 종료를 보장하지 않는다.
- 675조건은 코드로 계산한 축소 후보이며 아직 canonical runner에 반영되지 않았다. 각 instance/slot/load의 모든 duty×극성, 각 TOP/길이와 최장·최저속 조합을 남긴다. 모든 조합과 동등한 검출력을 주장하지 않는다.

## 범위 경계

이 공통 결선은 남은 PWM/QDEC/I2S와 위 17개 GPIO, 가용 GPIOTE 채널을 한 배선으로 검사하기 위한 것이다. **31개 pad 전체·T12 전체 완료를 뜻하지 않는다.**

- P1.00/01(LFXO), P1.02/03(PMIC I2C), P1.11(INT), P1.12(VBAT), P2.08(PG), P2.10(CE)는 이 출력 결선에서 제외한다. 기존 내부/공유 회로 증거와 허용 동작·거부 계약을 대응하며 부족한 기능 근거는 남긴다.
- P0.04·P1.08/09/13 버튼, P2.07(LED/SWO), P2.09(LED)는 공통 선에 넣지 않는다. 기존 온보드 결과 또는 별도 조건으로 대응하며 미실행을 PASS로 바꾸지 않는다. 버튼 실제 누르기는 현재 자동 기능 시험 범위 밖이다.
- 완료된 PDM은 이 결선에 묶지 않는다. PDM 재시험, T11 변경 영향 회귀, T13의 넓은 동시 topology·단독 180초·동시 1800초·전체 대표 한 조합 3600초 안정성 검사, System OFF 재연결과 릴리즈 설치 검증은 별도 계획이다.

## 검토 근거

- 소스 `6b6f25b23adc0feb28b492d772d438af253d2659`, board gitlink `fe65f2f0880bd05b32e562d9bf1ee59142b4f4d3`.
- `tests/hil/nu54dk/nu54dk_connector_pinmap.json`: 사용자 확인 전사와 모든 connector 위치 대조.
- 고정 submodule `NU54-DK Schematic.pdf` 1·3·6·7·8·9쪽: 모듈 net, PMIC, UART 격리, SWO, LED 입력, connector 확인.
- `dts/nucode/nu54dk-arduino-pins.dtsi`, `GpioteFabric.cpp`, `EventFabricRegistry.cpp`, `StreamFabricInternal.h`, `QdecFabric.cpp`, `I2sFabric.cpp`의 핀·port·profile 계약 확인.
- 정적 감사: 17개 1:1 신호, endpoint 중복/분기/제외 pin 0, 예정 PWM/QDEC/I2S 단계에서 한 net의 이중 driver 0. 이는 도면·계획 대조이며 실제 배선/펌웨어 전환의 PASS가 아니다.

## 결선 검사 실행

실행기는 `tests/hil/nu54dk/v04_wiring_run.py`다. `--dut`/`--peer`에 새로 식별한 exact UID, `--build-root`에 해당 clean commit의 두 role build, `--pyocd`에 고정 도구 경로를 전달한다. `--swd-frequency-hz 10000000`을 유지한다. 실행 옵션이 없으면 probe 접근 없이 준비 정보와 미확인 template만 출력한다.

실제 실행에는 `--execute-fixture --confirmation 현재확인서.json --evidence 새결과.json`이 필요하다. USB 단일 명령 진단이 필요한 이 PC에서는 `--cmsis-dap-limit-packets`를 명시한다. 102회 net-round는 두 방향×17신호×3회이며 각 회차 LOW와 해제 시 양쪽 전체 17개 입력을 기록한다. 마지막에 양쪽 LOW 자동 해제와 10초 lease 반환을 별도로 검사한다.

실패 raw와 양쪽 cleanup을 보존하며 그 결과로 다음 PWM 등 출력 모드를 자동 허용하지 않는다. USB 접지를 통한 우회가 있을 수 있으므로 GND 점퍼 자체의 연속성/접촉 저항이나 전압 품질을 이 checker만으로 보증하지 않는다. 최신 준비 및 실제 결과는 저장소의 `00_Docs/04_검증 기록/99_공통_결선_검사와_승인_전_자동_진행_계획.md`에서 관리한다.
