/**
 * @file M29MultiEvents.inc
 * @brief GAP·LE CoC event를 generation handle별로 분리합니다.
 *
 * SPDX-License-Identifier: MIT
 */

    /** @brief GAP의 local role로 mixed의 두 generation handle을 분리합니다. */
    void onBleEvent(const nucode::ble::BLEEventInfo &information, void *context)
    {
        static_cast<void>(context);
        checkCallbackContext();
        if (!session_started || session_finished)
        {
            return;
        }
        if (information.event == nucode::ble::BLEEvent::error)
        {
            fail("gap_error", BLEDevice.lastDriverError());
            return;
        }
        if (information.event == nucode::ble::BLEEvent::connected)
        {
            if (!information.connection.valid())
            {
                fail("connection_handle");
                return;
            }
            if (information.role == nucode::ble::BLELinkRole::central && hasClient())
            {
                if (client_connection.valid() &&
                    client_connection != information.connection)
                {
                    ++cross_link_events;
                    fail("duplicate_client_link");
                    return;
                }
                client_connection = information.connection;
                if (!BLEL2cap.connect(client_connection, coc_psm, client_channel) ||
                    !BLEClient.discover(client_connection, service_uuid, characteristic_uuid))
                {
                    fail("client_link_setup", BLEDevice.lastDriverError());
                }
                return;
            }
            if (information.role == nucode::ble::BLELinkRole::peripheral && hasServer())
            {
                if (server_connection.valid())
                {
                    ++cross_link_events;
                    fail("duplicate_server_link");
                    return;
                }
                server_connection = information.connection;
                printLinkIfReady();
                startTrafficIfReady();
                return;
            }
            ++cross_link_events;
            fail("unexpected_connection_role");
            return;
        }
        if (information.event == nucode::ble::BLEEvent::disconnected)
        {
            fail("early_disconnect");
        }
    }

    /** @brief 두 link의 CoC channel·payload·echo를 generation handle로 분리합니다. */
    void onL2capEvent(const nucode::ble::BLEL2capEventInfo &information, void *context)
    {
        static_cast<void>(context);
        checkCallbackContext();
        if (!session_started || session_finished)
        {
            return;
        }
        const bool client_event = client_channel.valid() && information.channel == client_channel;
        const bool server_event = server_channel.valid() && information.channel == server_channel;
        if (information.event == nucode::ble::BLEL2capEvent::connected)
        {
            if (information.connection == client_connection && information.channel == client_channel &&
                hasClient() && !client_channel_connected)
            {
                if (information.local_mtu != 512U || information.remote_mtu != 512U)
                {
                    fail("client_coc_mtu");
                    return;
                }
                client_channel_connected = true;
                startMixedAdvertisingIfReady();
                startTrafficIfReady();
                return;
            }
            if (information.connection == server_connection && hasServer() &&
                !server_channel_connected)
            {
                if (information.local_mtu != 512U || information.remote_mtu != 512U)
                {
                    fail("server_coc_mtu");
                    return;
                }
                server_channel = information.channel;
                server_channel_connected = true;
                printLinkIfReady();
                startTrafficIfReady();
                return;
            }
            ++cross_link_events;
            fail("cross_link_coc_connect");
            return;
        }
        if (!client_event && !server_event)
        {
            ++cross_link_events;
            fail("cross_link_coc_event");
            return;
        }
        if (information.event == nucode::ble::BLEL2capEvent::disconnected)
        {
            fail("early_coc_disconnect", information.status);
            return;
        }
        if (information.event == nucode::ble::BLEL2capEvent::sent)
        {
            if (client_event)
            {
                ++client_coc_sent;
                if (client_coc_sent > required_operations)
                {
                    fail("client_coc_sent_overflow");
                }
                printProgress();
                finishIfComplete();
            }
            else if (!server_echo_pending)
            {
                fail("server_coc_unexpected_sent");
            }
            else
            {
                server_echo_pending = false;
                ++server_coc_sent;
                printProgress();
                finishIfComplete();
            }
            return;
        }
        if (information.event != nucode::ble::BLEL2capEvent::received)
        {
            return;
        }
        if (client_event)
        {
            if (!coc_waiting_for_echo ||
                !MultiPayload::valid(information.data, information.length, peerMarker(),
                                     MultiPayload::coc_kind, client_coc_received,
                                     nonce_binary))
            {
                ++payload_errors;
                fail("client_coc_payload");
                return;
            }
            coc_waiting_for_echo = false;
            ++client_coc_received;
            issueClientTraffic();
            printProgress();
            finishIfComplete();
            return;
        }
        if (server_echo_pending ||
            !MultiPayload::valid(information.data, information.length, serverMarker(),
                                 MultiPayload::coc_kind, server_coc_received, nonce_binary))
        {
            ++payload_errors;
            fail("server_coc_payload");
            return;
        }
        ++server_coc_received;
        server_echo_pending = true;
        if (!BLEL2cap.send(server_channel, information.data, information.length))
        {
            server_echo_pending = false;
            fail("server_coc_echo", BLEDevice.lastDriverError());
        }
    }
