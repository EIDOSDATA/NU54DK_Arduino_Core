/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par 목적
 * 두 LE CoC channel에서 최대 512-byte SDU를 그대로 돌려주는 echo server 예제입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 2대 — 1) L2capCocClient (client/controller); 2) L2capCocServer (server/device)
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * 없음
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par 준비물
 * - NU54DK 보드 2대 — 1) L2capCocClient (client/controller); 2) L2capCocServer (server/device)
 * @par 설정
 * - Tools → Feature set에서 `ble` profile을 선택합니다.
 * - Serial Monitor는 115200 baud로 엽니다.
 * @par 실행 순서
 * - 권장 profile로 현재 Sketch와 metadata에 적힌 각 peer 역할 Sketch를 빌드합니다.
 * - probe가 여러 대이면 `NUCODE_PROBE_UID`를 지정하고 Arduino Upload로 역할별 보드를 구분합니다.
 * - peer·외장 조건을 먼저 준비한 뒤 reset 또는 예제에 명시된 입력으로 실행합니다.
 * @par 성공 출력
 * - Serial 문구 `LE CoC connected, remote MTU=`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `LE CoC disconnected`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `LE CoC echo PSM=0x`를 포함한 정상 상태 전이를 확인합니다.
 * @par 흔한 오류
 * - 권장 profile과 sidecar가 다르면 기능·Kconfig가 빠질 수 있으므로 먼저 설정을 다시 확인합니다.
 * - 여러 probe가 연결된 상태에서 UID를 생략하면 다른 보드에 upload될 수 있습니다.
 * - `LE CoC echo failed, error=` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * - `LE CoC server start failed, error=` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * - `BLE advertising restart failed` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * @par 다음 예제
 * - `NUCODE_BLE/LeChannelMapControl`
 * - `NUCODE_BLE/LePowerControlCentral`
 * @par 종료와 재시작
 * - 예제의 stop/end/disconnect 또는 유한 완료 흐름 뒤 오류와 자원 반환을 확인합니다.
 * - 실패 문구와 driver 상태를 확인한 뒤 명시적 reset 또는 예제의 재시작 흐름을 사용합니다.
 * @par 보안
 * - wireless_example_no_implicit_security_claim
 * - 무선 연결 성공만으로 인증·암호화·상호운용 보안을 주장하지 않습니다.
 * @par 제한
 * - Compile·Host 검사는 실제 보드 runtime 또는 외부 제품 상호운용 PASS를 대신하지 않습니다.
 * - 목적과 metadata 조건 밖의 성능·동시성·정밀도는 이 예제의 보증 범위가 아닙니다.
 * @par Negative
 * - wrong_profile_or_missing_sidecar
 * - missing_or_wrong_role_peer
 * - startup_or_runtime_error_reported
 * @par Traceability
 * Recipe `ble_l2cap`; 내부 증거 ID는 metadata에서 관리합니다.
 * 직접 upstream 복사 아님; NCS `99553055607b2e9885fbc80ccd11fa9da81c2df0`, Zephyr `bf801e4e3d19e1ffa76164346480cb7734dd2800`
 * build `clean_installed_compile_required`, runtime `procedure_documented_not_physical_pass`
 * @par Metadata
 * identity `NUCODE_BLE/L2capCocServer`, sha256 `acd276a4e8af60832546ae010771ed61c6fe765d6056bae4f7149e7499f35a82`
 * @nucode_example_setup_end */

/**
 * @file L2capCocServer.ino
 * @brief 두 LE CoC channel에서 최대 512-byte SDU를 그대로 돌려주는 echo server 예제입니다.
 */

#include <NUCODE_BLE.h>

constexpr std::uint16_t echoPsm = 0x0080U;
bool restartAdvertising = false;

/** @brief 연결 해제 뒤 connectable advertising 재시작을 예약합니다. */
void onBleEvent(const nucode::ble::BLEEventInfo &information, void *context)
{
    static_cast<void>(context);
    if (information.event == nucode::ble::BLEEvent::disconnected)
    {
        restartAdvertising = true;
    }
}

/** @brief main thread에서 받은 SDU를 같은 channel에 echo합니다. */
void onL2capEvent(const nucode::ble::BLEL2capEventInfo &information, void *context)
{
    static_cast<void>(context);
    if (information.event == nucode::ble::BLEL2capEvent::connected)
    {
        Serial.print("LE CoC connected, remote MTU=");
        Serial.println(information.remote_mtu);
    }
    else if (information.event == nucode::ble::BLEL2capEvent::received)
    {
        if (!BLEL2cap.send(information.channel, information.data, information.length))
        {
            Serial.print("LE CoC echo failed, error=");
            Serial.println(static_cast<unsigned>(BLEDevice.lastError()));
        }
    }
    else if (information.event == nucode::ble::BLEL2capEvent::disconnected)
    {
        Serial.println("LE CoC disconnected");
    }
}

void setup()
{
    Serial.begin(115200);
    BLEDevice.onEventInfo(onBleEvent);
    BLEL2cap.onEvent(onL2capEvent);

    if (!BLEDevice.begin("NU54-CoC-Echo") || !BLEL2cap.startServer(echoPsm) ||
        !BLEAdvertising.clear() || !BLEAdvertising.setConnectable(true) ||
        !BLEAdvertising.start())
    {
        Serial.print("LE CoC server start failed, error=");
        Serial.println(static_cast<unsigned>(BLEDevice.lastError()));
        return;
    }
    Serial.print("LE CoC echo PSM=0x");
    Serial.println(BLEL2cap.serverPsm(), HEX);
}

void loop()
{
    BLEDevice.poll();
    if (restartAdvertising && BLEConnection.count() == 0U)
    {
        restartAdvertising = false;
        if (!BLEAdvertising.start())
        {
            Serial.println("BLE advertising restart failed");
        }
    }
}
