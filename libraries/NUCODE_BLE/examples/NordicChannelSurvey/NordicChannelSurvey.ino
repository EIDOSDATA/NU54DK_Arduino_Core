/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: BLE NUS (`ble`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 1대 — 1) NordicChannelSurvey 실행 보드
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * prj.conf
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI 실행 전에 `NUCODE_PROBE_UID`로 명시 선택합니다.
 * @par 추가 조건
 * SDC channel energy 측정값은 spectrum analyzer 교정값이 아닙니다.
 * @par Metadata
 * identity `NUCODE_BLE/NordicChannelSurvey`, sha256 `a7467f0b85e14f78a63f9a77f0ea091f8db005e8220d90ab7377cded925a51cd`
 * @nucode_example_setup_end */

/**
 * @file NordicChannelSurvey.ino
 * @brief Nordic QoS channel survey의 40개 channel energy를 주기적으로 출력합니다.
 */

#include <NUCODE_BLE.h>

/** @brief 사용 가능한 channel 중 가장 높은 energy와 index를 출력합니다. */
void onSurvey(const nucode::ble::BLENordicChannelSurveyReport &report, void *context)
{
    static_cast<void>(context);
    std::int8_t highest = -127;
    std::size_t channel = 0U;
    for (std::size_t index = 0U;
         index < nucode::ble::BLENordicChannelSurveyReport::channel_count; ++index)
    {
        const std::int8_t energy = report.channel_energy_dbm[index];
        if (energy != nucode::ble::BLENordicChannelSurveyReport::unavailable &&
            energy > highest)
        {
            highest = energy;
            channel = index;
        }
    }
    Serial.print("Highest channel/energy dBm: ");
    Serial.print(channel);
    Serial.print('/');
    Serial.println(highest);
}

void setup()
{
    Serial.begin(115200);
    BLENordic.onChannelSurvey(onSurvey);
    if (!BLEDevice.begin("NU54-SURVEY") ||
        !BLENordic.setChannelSurvey(true, 100000U))
    {
        Serial.println("Channel survey start failed");
    }
}

void loop()
{
    BLEDevice.poll();
}
