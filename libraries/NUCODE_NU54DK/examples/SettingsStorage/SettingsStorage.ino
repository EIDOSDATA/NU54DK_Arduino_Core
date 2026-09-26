/** @nucode_example_setup_begin
 * @brief 이 블록은 `libraries/example-metadata.json`에서 생성한 Arduino IDE 설정 안내입니다.
 * @par Board
 * NU54DK (nRF54L15, Zephyr)
 * @par Feature set
 * 기본 권장: Standard peripherals (`standard`)
 * 호환 대안: 없음
 * @par 보드와 역할
 * 1대 — 1) SettingsStorage 실행 보드
 * @par Serial Monitor
 * 115200 baud
 * @par 필수 sidecar
 * 없음
 * @par Upload probe
 * probe 1대는 CMSIS-DAP 자동 선택, 여러 대는 Arduino CLI `--upload-field probe_id=<UID>`로 명시 선택합니다.
 * @par 추가 조건
 * 추가 조건 없음
 * @par Metadata
 * identity `NUCODE_NU54DK/SettingsStorage`, sha256 `8d281c209008f0774ed54e2527bef2140f1d27c354563d1412ef08edcaf45d42`
 * @nucode_example_setup_end */

/**
 * @file SettingsStorage.ino
 * @brief NU54DK 내부 storage_partition에 boot count를 저장합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_NU54DK.h>

#include <stdio.h>

using nucode::nu54dk::Error;

namespace
{
    constexpr char boot_count_key[] = "example.boot-count";
}

void setup()
{
    Serial.begin(115200);
    delay(200);

    if (NU54DK.storageBegin() != Error::none)
    {
        Serial.println("storage init failed");
        return;
    }

    std::uint32_t boot_count = 0U;
    std::size_t actual_length = 0U;
    const Error load_result =
        NU54DK.storageGet(boot_count_key, &boot_count, sizeof(boot_count), actual_length);
    if ((load_result != Error::none) || (actual_length != sizeof(boot_count)))
    {
        boot_count = 0U;
    }
    ++boot_count;

    if (NU54DK.storagePut(boot_count_key, &boot_count, sizeof(boot_count)) == Error::none)
    {
        char message[48] = {};
        snprintf(message, sizeof(message), "stored boot count=%lu",
                 static_cast<unsigned long>(boot_count));
        Serial.println(message);
    }
    else
    {
        Serial.println("storage write failed");
    }
}

void loop()
{
    delay(1000);
}
