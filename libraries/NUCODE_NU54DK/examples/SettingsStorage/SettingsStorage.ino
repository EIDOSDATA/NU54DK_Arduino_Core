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
