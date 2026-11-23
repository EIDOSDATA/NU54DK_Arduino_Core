/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par 목적
 * 4 subevent × 4 response slot PAwR train을 송신하고 response를 읽습니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 2대 — 1) PawrAdvertiser (advertiser); 2) PawrScanner (scanner)
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * 없음
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par 준비물
 * - NU54DK 보드 2대 — 1) PawrAdvertiser (advertiser); 2) PawrScanner (scanner)
 * @par 설정
 * - Tools → Feature set에서 `ble` profile을 선택합니다.
 * - Serial Monitor는 115200 baud로 엽니다.
 * @par 실행 순서
 * - 권장 profile로 현재 Sketch와 metadata에 적힌 각 peer 역할 Sketch를 빌드합니다.
 * - probe가 여러 대이면 `NUCODE_PROBE_UID`를 지정하고 Arduino Upload로 역할별 보드를 구분합니다.
 * - peer·외장 조건을 먼저 준비한 뒤 reset 또는 예제에 명시된 입력으로 실행합니다.
 * @par 성공 출력
 * - Serial 문구 `response subevent=`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `slot=`를 포함한 정상 상태 전이를 확인합니다.
 * - Serial 문구 `bytes=`를 포함한 정상 상태 전이를 확인합니다.
 * @par 흔한 오류
 * - 권장 profile과 sidecar가 다르면 기능·Kconfig가 빠질 수 있으므로 먼저 설정을 다시 확인합니다.
 * - 여러 probe가 연결된 상태에서 UID를 생략하면 다른 보드에 upload될 수 있습니다.
 * - `PAwR advertiser start failed` 출력은 실패이며 원인을 확인한 뒤 재시작합니다.
 * @par 다음 예제
 * - `NUCODE_BLE/PawrScanner`
 * - `NUCODE_BLE/PeriodicAdvertiser`
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
 * Recipe `ble_advertising_scanning`; 내부 증거 ID는 metadata에서 관리합니다.
 * 직접 upstream 복사 아님; NCS `99553055607b2e9885fbc80ccd11fa9da81c2df0`, Zephyr `bf801e4e3d19e1ffa76164346480cb7734dd2800`
 * build `clean_installed_compile_required`, runtime `procedure_documented_not_physical_pass`
 * @par Metadata
 * identity `NUCODE_BLE/PawrAdvertiser`, sha256 `a3d454b481a2b44616bf3288b9dbbb2fc13022a22e033465be6f9a43c6925f1f`
 * @nucode_example_setup_end */

/**
 * @file PawrAdvertiser.ino
 * @brief 4 subevent × 4 response slot PAwR train을 송신하고 response를 읽습니다.
 */

#include <NUCODE_BLE.h>

nucode::ble::BLEAdvertisingSetHandle advertisingSet;
uint8_t extendedPayload[] = {3U, 0x09U, 'P', 'R'};

/** @brief main-thread로 전달된 PAwR response의 위치와 길이를 출력합니다. */
void onResponse(const nucode::ble::BLEPawrResponse &response, void *)
{
    Serial.print("response subevent=");
    Serial.print(response.subevent);
    Serial.print(" slot=");
    Serial.print(response.response_slot);
    Serial.print(" bytes=");
    Serial.println(response.payload_length);
}

void setup()
{
    Serial.begin(115200);
    nucode::ble::BLEExtendedAdvertisingParameters extendedParameters{};
    extendedParameters.sid = 3U;
    if (!BLEDevice.begin("NU54-PAWR-ADV") ||
        !BLEExtendedAdvertising.create(extendedParameters, advertisingSet) ||
        !BLEExtendedAdvertising.setData(advertisingSet, extendedPayload,
                                        sizeof(extendedPayload)) ||
        !BLEPawr.configureAdvertiser(advertisingSet))
    {
        return;
    }
    for (uint8_t subevent = 0U; subevent < 4U; ++subevent)
    {
        const uint8_t payload[] = {subevent, 0xa5U};
        if (!BLEPawr.setSubeventData(advertisingSet, subevent, payload,
                                    sizeof(payload)))
        {
            return;
        }
    }
    BLEPawr.onResponse(onResponse);
    if (!BLEPeriodicAdvertising.start(advertisingSet) ||
        !BLEExtendedAdvertising.start(advertisingSet))
    {
        Serial.println("PAwR advertiser start failed");
    }
}

void loop()
{
    BLEDevice.poll();
}
