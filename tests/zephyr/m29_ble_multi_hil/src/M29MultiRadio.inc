/**
 * @file M29MultiRadio.inc
 * @brief 같은 session peer만 고르는 광고·검색 처리를 구현합니다.
 *
 * SPDX-License-Identifier: MIT
 */

    /** @brief advertising payload 안의 company ID·role·128-bit nonce를 확인합니다. */
    bool validRfPeer(const nucode::ble::BLEScanResult &result)
    {
        std::size_t cursor = 0U;
        while (cursor < result.payload_length)
        {
            const std::uint8_t field_length = result.payload[cursor];
            if (field_length == 0U || cursor + field_length >= result.payload_length)
            {
                return false;
            }
            const std::uint8_t type = result.payload[cursor + 1U];
            if (type == BT_DATA_MANUFACTURER_DATA &&
                field_length == MultiPayload::nonce_binary_length + 4U)
            {
                const std::uint8_t *value = &result.payload[cursor + 2U];
                return value[0] == static_cast<std::uint8_t>(company_id & 0xffU) &&
                       value[1] == static_cast<std::uint8_t>(company_id >> 8U) &&
                       value[2] == peerMarker() &&
                       ::memcmp(value + 3U, nonce_binary,
                                MultiPayload::nonce_binary_length) == 0;
            }
            cursor += field_length + 1U;
        }
        return false;
    }

    /** @brief role marker와 full nonce를 포함한 connectable advertising을 시작합니다. */
    [[maybe_unused]] bool startAdvertising()
    {
        std::uint8_t manufacturer[MultiPayload::nonce_binary_length + 1U] = {};
        manufacturer[0] = serverMarker();
        ::memcpy(manufacturer + 1U, nonce_binary, MultiPayload::nonce_binary_length);
        if (!BLEAdvertising.clear() || !BLEAdvertising.setConnectable(true) ||
            !BLEAdvertising.setManufacturerData(company_id, manufacturer,
                                                  sizeof(manufacturer)) ||
            !BLEAdvertising.setScanResponseName(true) || !BLEAdvertising.start())
        {
            return false;
        }
        Serial.print(protocol);
        Serial.print("|ADVERTISE|role=");
        Serial.print(roleName());
        Serial.print("|marker=");
        Serial.print(serverMarker());
        Serial.print("|psm=129|status=pass");
        printSuffix();
        Serial.println();
        return true;
    }
    /** @brief company ID·role·exact nonce로 peer를 고르는 active scan을 시작합니다. */
    [[maybe_unused]] bool startScan()
    {
        if (!BLEScan.clearFilters() || !BLEScan.start(true))
        {
            return false;
        }
        scan_started = true;
        Serial.print(protocol);
        Serial.print("|SCAN|role=");
        Serial.print(roleName());
        Serial.print("|status=pass");
        printSuffix();
        Serial.println();
        return true;
    }
