/**
 * @file M29MultiTraffic.inc
 * @brief link별 GATT·CoC traffic과 완료 판정을 구현합니다.
 *
 * SPDX-License-Identifier: MIT
 */

    /** @brief 두 link가 모두 준비된 뒤 role별 고정 연결 수를 출력합니다. */
    void printLinkIfReady()
    {
        if (link_reported)
        {
            return;
        }
#if defined(NUCODE_M29_MULTI_MIXED)
        if (!client_discovered || !client_channel_connected ||
            !server_connection.valid() || !server_channel_connected)
        {
            return;
        }
        const unsigned int links = 2U;
#elif defined(NUCODE_M29_MULTI_PERIPHERAL)
        if (!server_connection.valid() || !server_channel_connected)
        {
            return;
        }
        const unsigned int links = 1U;
#else
        if (!client_discovered || !client_channel_connected)
        {
            return;
        }
        const unsigned int links = 1U;
#endif
        link_reported = true;
        Serial.print(protocol);
        Serial.print("|LINK|role=");
        Serial.print(roleName());
        Serial.print("|connections=");
        Serial.print(links);
        Serial.print("|gatt=ready|coc=ready");
        printSuffix();
        Serial.println();
    }

    /** @brief mixed의 upstream 준비 뒤에만 downstream advertising을 시작합니다. */
    void startMixedAdvertisingIfReady()
    {
#if defined(NUCODE_M29_MULTI_MIXED)
        if (mixed_advertising_started || !client_discovered || !client_channel_connected)
        {
            return;
        }
        Serial.print(protocol);
        Serial.print("|UPSTREAM|role=mixed|gatt=ready|coc=ready");
        printSuffix();
        Serial.println();
        mixed_advertising_started = true;
        if (!startAdvertising())
        {
            fail("mixed_advertising", BLEDevice.lastDriverError());
        }
#endif
    }

    /** @brief GATT와 CoC에 각각 최대 한 작업만 유지해 두 transport를 병렬 진행합니다. */
    void issueClientTraffic()
    {
        if (!hasClient() || !traffic_started)
        {
            return;
        }
        if (!gatt_inflight && client_gatt_completed < required_operations)
        {
            MultiPayload::build(gatt_payload, peerMarker(), MultiPayload::gatt_kind,
                                client_gatt_completed, nonce_binary);
            if (!BLEClient.write(client_connection, gatt_payload, sizeof(gatt_payload)))
            {
                fail("gatt_write_start", BLEDevice.lastDriverError());
                return;
            }
            gatt_inflight = true;
        }
        if (!coc_waiting_for_echo && client_coc_received < required_operations)
        {
            MultiPayload::build(coc_payload, peerMarker(), MultiPayload::coc_kind,
                                client_coc_received, nonce_binary);
            if (!BLEL2cap.send(client_channel, coc_payload, sizeof(coc_payload)))
            {
                fail("coc_send_start", BLEDevice.lastDriverError());
                return;
            }
            coc_waiting_for_echo = true;
        }
    }

    /** @brief 모든 local link가 100회씩 전진한 지점을 고정 progress record로 출력합니다. */
    void printProgress()
    {
        std::uint32_t completed = required_operations;
        if (hasClient())
        {
            completed = client_gatt_completed < client_coc_received
                            ? client_gatt_completed
                            : client_coc_received;
        }
        if (hasServer())
        {
            const std::uint32_t server_completed =
                server_gatt_received < server_coc_sent ? server_gatt_received
                                                       : server_coc_sent;
            if (server_completed < completed)
            {
                completed = server_completed;
            }
        }
        while (progress_reported + 100U <= completed)
        {
            progress_reported += 100U;
            Serial.print(protocol);
            Serial.print("|PROGRESS|role=");
            Serial.print(roleName());
            Serial.print("|operations_per_link=");
            Serial.print(progress_reported);
            printSuffix();
            Serial.println();
        }
    }

    /** @brief role별 모든 정량 조건과 production CoC 통계를 확인해 RESULT·END를 출력합니다. */
    void finishIfComplete()
    {
        if (session_finished || !traffic_started)
        {
            return;
        }
        const bool client_complete = !hasClient() ||
                                     (client_gatt_completed == required_operations &&
                                      client_coc_received == required_operations &&
            client_coc_sent == required_operations);
        const bool server_complete = !hasServer() ||
                                     (server_gatt_received == required_operations &&
                                      server_coc_received == required_operations &&
                                      server_coc_sent == required_operations);
        if (!client_complete || !server_complete)
        {
            return;
        }
        const nucode::ble::BLEL2capStatistics statistics = BLEL2cap.statistics();
#if defined(NUCODE_M29_MULTI_MIXED)
        const std::uint32_t expected_connections = 2U;
        const std::uint32_t expected_packets = 2000U;
#else
        const std::uint32_t expected_connections = 1U;
        const std::uint32_t expected_packets = 1000U;
#endif
        if (statistics.connected != expected_connections || statistics.sent != expected_packets ||
            statistics.received != expected_packets || statistics.disconnected != 0U ||
            statistics.backpressure != 0U || statistics.rejected != 0U ||
            statistics.dropped_events != 0U || cross_link_events != 0U ||
            payload_errors != 0U || !callback_context_valid)
        {
            fail("final_statistics");
            return;
        }
        Serial.print(protocol);
        Serial.print("|RESULT|role=");
        Serial.print(roleName());
        Serial.print("|connections=");
        Serial.print(expected_connections);
        Serial.print("|gatt_tx=");
        Serial.print(client_gatt_completed);
        Serial.print("|gatt_rx=");
        Serial.print(server_gatt_received);
        Serial.print("|coc_tx=");
        Serial.print(client_coc_sent + server_coc_sent);
        Serial.print("|coc_rx=");
        Serial.print(client_coc_received + server_coc_received);
        Serial.print("|cross_link=0|payload_errors=0|dropped_events=0");
        Serial.print("|callback_context=pass");
        printSuffix();
        Serial.println();
        Serial.print(protocol);
        Serial.print("|END|role=");
        Serial.print(roleName());
        Serial.print("|status=pass");
        printSuffix();
        Serial.println();
        session_finished = true;
    }

    /** @brief mixed/central에서 두 transport가 준비된 순간 traffic을 시작합니다. */
    void startTrafficIfReady()
    {
        if (traffic_started)
        {
            return;
        }
        if (hasClient() && (!client_discovered || !client_channel_connected))
        {
            return;
        }
        if (hasServer() && (!server_connection.valid() || !server_channel_connected))
        {
            return;
        }
        printLinkIfReady();
        traffic_started = true;
        issueClientTraffic();
    }

    /** @brief exact nonce가 포함된 peer scan result 하나만 연결합니다. */
    void onScanResult(const nucode::ble::BLEScanResult &result, void *context)
    {
        static_cast<void>(context);
        checkCallbackContext();
        if (session_finished || !session_started || !scan_started || peer_found ||
            !result.connectable || result.scan_response || !validRfPeer(result))
        {
            return;
        }
        peer_found = true;
        peer_address = result.address;
    }

    /** @brief link 식별 가능한 GATT client 완료만 현재 client state에 반영합니다. */
    void onClientEvent(const nucode::ble::BLEGattClientEventInfo &information, void *context)
    {
        static_cast<void>(context);
        checkCallbackContext();
        if (!session_started || session_finished)
        {
            return;
        }
        if (information.connection != client_connection)
        {
            ++cross_link_events;
            fail("cross_link_gatt_client");
            return;
        }
        if (information.event == nucode::ble::BLEGattClientEvent::operation_failed)
        {
            fail("gatt_client_operation", information.status);
            return;
        }
        if (!client_discovered)
        {
            if (information.event != nucode::ble::BLEGattClientEvent::discovery_complete ||
                !BLEClient.discovered(client_connection))
            {
                fail("gatt_discovery_result");
                return;
            }
            client_discovered = true;
            startMixedAdvertisingIfReady();
            startTrafficIfReady();
            return;
        }
        if (information.event != nucode::ble::BLEGattClientEvent::write_complete ||
            !gatt_inflight)
        {
            fail("gatt_write_event");
            return;
        }
        gatt_inflight = false;
        ++client_gatt_completed;
        issueClientTraffic();
        printProgress();
        finishIfComplete();
    }
    /** @brief server write의 link marker·sequence·payload를 main thread에서 검증합니다. */
    void onCharacteristicEvent(nucode::ble::BLECharacteristic &characteristic,
                               const nucode::ble::BLECharacteristicEventInfo &information,
                               void *context)
    {
        static_cast<void>(characteristic);
        static_cast<void>(context);
        checkCallbackContext();
        if (!session_started || session_finished ||
            information.event != nucode::ble::BLECharacteristicEvent::written)
        {
            return;
        }
        if (information.connection != server_connection)
        {
            ++cross_link_events;
            fail("cross_link_gatt_server");
            return;
        }
        if (information.offset != 0U || information.without_response ||
            !MultiPayload::valid(information.data, information.length, serverMarker(),
                                 MultiPayload::gatt_kind, server_gatt_received,
                                 nonce_binary))
        {
            ++payload_errors;
            fail("gatt_server_payload");
            return;
        }
        ++server_gatt_received;
        printProgress();
        finishIfComplete();
    }
