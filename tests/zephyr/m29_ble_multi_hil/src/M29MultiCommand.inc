/**
 * @file M29MultiCommand.inc
 * @brief Host READY·START 명령과 실행 제한을 처리합니다.
 *
 * SPDX-License-Identifier: MIT
 */

    /** @brief 검증된 START 뒤 role별 server와 scan/advertising을 시작합니다. */
    void startProtocol()
    {
        if (!acceptStartCommand())
        {
            fail("start_record");
            return;
        }
        session_started = true;
        session_deadline = k_uptime_get() + session_timeout_ms;
        session_statistics_base = BLEL2cap.statistics();
        printBegin();
        if (hasServer() && !BLEL2cap.startServer(coc_psm))
        {
            fail("coc_server", BLEDevice.lastDriverError());
            return;
        }
#if defined(NUCODE_M29_MULTI_PERIPHERAL)
        if (!startAdvertising())
        {
            fail("peripheral_advertising", BLEDevice.lastDriverError());
        }
#else
        if (!startScan())
        {
            fail("scan_start", BLEDevice.lastDriverError());
        }
#endif
    }

    /** @brief STOP을 수락하고 radio·link·CoC 정리를 bounded 상태로 시작합니다. */
    void startCleanup()
    {
        if (!acceptStopCommand())
        {
            fail("stop_record");
            return;
        }
        cleanup_requested = true;
        cleanup_deadline = k_uptime_get() + cleanup_timeout_ms;
    }

    /** @brief 모든 link와 pending buffer가 0인 뒤 CLEANUP ACK를 출력하고 재무장합니다. */
    void driveCleanup()
    {
        if (!cleanup_requested)
        {
            return;
        }
        if (!cleanup_started)
        {
            cleanup_started = true;
            if (scan_started)
            {
                static_cast<void>(BLEScan.stop());
                scan_started = false;
            }
            if (advertising_started)
            {
                static_cast<void>(BLEAdvertising.stop());
                advertising_started = false;
            }
            if (client_channel.valid())
            {
                static_cast<void>(BLEL2cap.disconnect(client_channel));
            }
            if (server_channel.valid())
            {
                static_cast<void>(BLEL2cap.disconnect(server_channel));
            }
            if (client_connection.valid())
            {
                static_cast<void>(BLEConnection.disconnect(client_connection));
            }
            if (server_connection.valid())
            {
                static_cast<void>(BLEConnection.disconnect(server_connection));
            }
        }
        const bool links_zero = !client_connection.valid() && !server_connection.valid() &&
                                !client_channel.valid() && !server_channel.valid();
        const bool pending_zero = !gatt_inflight && !coc_waiting_for_echo &&
                                  !server_echo_pending;
        const bool buffers_zero =
            BLEL2cap.availableForWrite() == nucode::ble::L2capCoc::transmit_buffers;
        if (links_zero && pending_zero && buffers_zero)
        {
            Serial.print(protocol);
            Serial.print("|CLEANUP|role=");
            Serial.print(roleName());
            Serial.print("|active_links=0|pending_operations=0|buffers=0|status=pass");
            printSuffix();
            Serial.println();
            resetSessionState();
            return;
        }
        if (k_uptime_get() >= cleanup_deadline)
        {
            Serial.print(protocol);
            Serial.print("|FAIL|role=");
            Serial.print(roleName());
            Serial.print("|stage=cleanup_timeout|code=0");
            printSuffix();
            Serial.println();
            cleanup_requested = false;
        }
    }

    /** @brief Host의 bounded 한 줄 command만 수집합니다. */
    void pollHostCommand()
    {
        while (Serial.available() > 0 && !cleanup_requested)
        {
            const int incoming = Serial.read();
            if (incoming < 0)
            {
                return;
            }
            const char value = static_cast<char>(incoming);
            if (value == '\r')
            {
                continue;
            }
            if (value == '\n')
            {
                command[command_length] = '\0';
                if (!session_started && !session_finished &&
                    ::strcmp(command, ready_query) == 0)
                {
                    command_length = 0U;
                    printReady();
                    return;
                }
                if (!session_started && !session_finished)
                {
                    startProtocol();
                }
                else if (session_finished)
                {
                    startCleanup();
                }
                else
                {
                    fail("unexpected_command");
                }
                command_length = 0U;
                return;
            }
            if (command_length + 1U >= sizeof(command))
            {
                fail("command_overflow");
                return;
            }
            command[command_length++] = value;
        }
    }
