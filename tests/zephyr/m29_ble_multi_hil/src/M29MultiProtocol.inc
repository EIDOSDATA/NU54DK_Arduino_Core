/**
 * @file M29MultiProtocol.inc
 * @brief role·session identity와 fail-closed protocol 출력을 구현합니다.
 *
 * SPDX-License-Identifier: MIT
 */

    /** @brief 현재 image의 고정 role 이름을 반환합니다. */
    const char *roleName()
    {
#if defined(NUCODE_M29_MULTI_PERIPHERAL)
        return "peripheral";
#elif defined(NUCODE_M29_MULTI_MIXED)
        return "mixed";
#else
        return "central";
#endif
    }

    /** @brief 현재 role이 GATT·CoC client traffic을 생성하는지 반환합니다. */
    constexpr bool hasClient()
    {
#if defined(NUCODE_M29_MULTI_PERIPHERAL)
        return false;
#else
        return true;
#endif
    }

    /** @brief 현재 role이 GATT·CoC server traffic을 수신하는지 반환합니다. */
    constexpr bool hasServer()
    {
#if defined(NUCODE_M29_MULTI_CENTRAL)
        return false;
#else
        return true;
#endif
    }

    /** @brief 현재 server link의 RF marker를 반환합니다. */
    constexpr std::uint8_t serverMarker()
    {
#if defined(NUCODE_M29_MULTI_PERIPHERAL)
        return peripheral_marker;
#else
        return mixed_marker;
#endif
    }

    /** @brief 현재 client가 찾아야 할 peer의 RF marker를 반환합니다. */
    constexpr std::uint8_t peerMarker()
    {
#if defined(NUCODE_M29_MULTI_MIXED)
        return peripheral_marker;
#else
        return mixed_marker;
#endif
    }

    /** @brief 모든 session record에 nonce와 exact Core revision을 붙입니다. */
    void printSuffix()
    {
        Serial.print("|nonce=");
        Serial.print(nonce);
        Serial.print("|core=");
        Serial.print(M29_MULTI_CORE_REVISION);
    }

    /** @brief 첫 실패를 고정 protocol로 출력하고 추가 target 동작을 중단합니다. */
    void fail(const char *stage, int code = 0)
    {
        if (session_finished)
        {
            return;
        }
        Serial.print(protocol);
        Serial.print("|FAIL|role=");
        Serial.print(roleName());
        Serial.print("|stage=");
        Serial.print(stage == nullptr ? "unknown" : stage);
        Serial.print("|code=");
        Serial.print(code);
        printSuffix();
        Serial.println();
        session_finished = true;
    }

    /** @brief 공개 callback이 Arduino main thread에서 실행됐는지 확인합니다. */
    void checkCallbackContext()
    {
        if (k_current_get() != setup_thread)
        {
            callback_context_valid = false;
            fail("callback_context");
        }
    }

    /** @brief READY record를 full Core revision과 함께 출력합니다. */
    void printReady()
    {
        Serial.print(protocol);
        Serial.print("|READY|role=");
        Serial.print(roleName());
        Serial.print("|core=");
        Serial.println(M29_MULTI_CORE_REVISION);
    }

    /** @brief BEGIN record를 session identity와 함께 출력합니다. */
    void printBegin()
    {
        Serial.print(protocol);
        Serial.print("|BEGIN|role=");
        Serial.print(roleName());
        Serial.print("|test=M29-MULTI-01");
        printSuffix();
        Serial.println();
    }

    /** @brief 128-bit lowercase nonce와 exact revision START만 허용합니다. */
    bool acceptStartCommand()
    {
        const std::size_t prefix_length = ::strlen(start_prefix);
        if (::strncmp(command, start_prefix, prefix_length) != 0)
        {
            return false;
        }
        const char *nonce_start = command + prefix_length;
        char nonce_candidate[MultiPayload::nonce_text_length + 1U] = {};
        ::memcpy(nonce_candidate, nonce_start, MultiPayload::nonce_text_length);
        if (::strcmp(nonce_start + MultiPayload::nonce_text_length, core_suffix) != 0 ||
            !MultiPayload::decodeNonce(nonce_candidate, nonce_binary))
        {
            return false;
        }
        ::memcpy(nonce, nonce_candidate, sizeof(nonce));
        return true;
    }

    /** @brief 현재 session nonce와 exact revision의 STOP만 허용합니다. */
    bool acceptStopCommand()
    {
        const std::size_t prefix_length = ::strlen(stop_prefix);
        if (::strncmp(command, stop_prefix, prefix_length) != 0)
        {
            return false;
        }
        const char *nonce_start = command + prefix_length;
        return ::strncmp(nonce_start, nonce, MultiPayload::nonce_text_length) == 0 &&
               ::strcmp(nonce_start + MultiPayload::nonce_text_length, core_suffix) == 0;
    }

    /** @brief cleanup 완료 뒤 다음 독립 session을 위해 모든 local 상태를 초기화합니다. */
    void resetSessionState()
    {
        ::memset(command, 0, sizeof(command));
        command_length = 0U;
        ::memset(nonce, 0, sizeof(nonce));
        ::memset(nonce_binary, 0, sizeof(nonce_binary));
        session_started = false;
        session_finished = false;
        cleanup_requested = false;
        cleanup_started = false;
        callback_context_valid = true;
        peer_found = false;
        scan_started = false;
        client_discovered = false;
        client_channel_connected = false;
        server_channel_connected = false;
        advertising_started = false;
        mixed_advertising_started = false;
        link_reported = false;
        traffic_started = false;
        gatt_inflight = false;
        coc_waiting_for_echo = false;
        server_echo_pending = false;
        session_deadline = 0;
        cleanup_deadline = 0;
        progress_reported = 0U;
        client_gatt_completed = 0U;
        client_coc_sent = 0U;
        client_coc_received = 0U;
        server_gatt_received = 0U;
        server_coc_received = 0U;
        server_coc_sent = 0U;
        cross_link_events = 0U;
        payload_errors = 0U;
        client_connection = nucode::ble::BLEConnectionHandle{};
        server_connection = nucode::ble::BLEConnectionHandle{};
        client_channel = nucode::ble::BLEL2capChannelHandle{};
        server_channel = nucode::ble::BLEL2capChannelHandle{};
    }
