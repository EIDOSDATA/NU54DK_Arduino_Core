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

    /** @brief Host의 bounded 한 줄 command만 수집합니다. */
    void pollHostCommand()
    {
        while (Serial.available() > 0 && !session_started && !session_finished)
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
                if (::strcmp(command, ready_query) == 0)
                {
                    command_length = 0U;
                    printReady();
                    return;
                }
                startProtocol();
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
