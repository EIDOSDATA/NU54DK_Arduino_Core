/**
 * @file main.cpp
 * @brief 두 NU54DK로 extended advertising·PAwR·privacy 재연결을 검증합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>
#include <NUCODE_BLE_Security.h>

#include <zephyr/kernel.h>

#include <cstddef>
#include <cstdint>
#include <string.h>

namespace
{

    constexpr char start_prefix[] = "NUCODE_M28B2_START:";
    constexpr std::size_t nonce_text_length = 32U;
    constexpr std::size_t nonce_binary_length = 16U;
    constexpr std::uint16_t company_id = 0x054dU;
    constexpr std::uint8_t pawr_sid = 8U;
    constexpr std::uint8_t privacy_sid = 9U;
    constexpr std::uint32_t advertising_updates = 110U;
    constexpr std::uint32_t required_advertising_reports = 100U;
    constexpr std::uint32_t required_pawr_responses = 100U;
    constexpr std::uint32_t central_pawr_responses = 105U;
    constexpr std::uint32_t required_rpa_rotations = 3U;
    constexpr std::uint32_t required_rpa_addresses = required_rpa_rotations + 1U;
    constexpr std::uint32_t required_reconnects = 20U;
    constexpr std::int64_t advertising_update_interval_ms = 60;
    constexpr std::int64_t reconnect_advertising_delay_ms = 1200;
    constexpr std::int64_t security_request_delay_ms = 400;
    constexpr std::int64_t secured_disconnect_delay_ms = 700;
    constexpr std::int64_t protocol_timeout_ms = 240000;

    enum class Phase : std::uint8_t
    {
        waiting,
        advertising,
        pawr_discovery,
        pawr_active,
        privacy_scan,
        privacy_rotation,
        privacy_link,
        complete,
    };

    char nonce[nonce_text_length + 1U] = {};
    std::uint8_t nonce_binary[nonce_binary_length] = {};
    char command[64] = {};
    std::size_t command_length = 0U;
    bool protocol_started = false;
    bool protocol_failed = false;
    Phase phase = Phase::waiting;
    std::int64_t protocol_deadline_ms = 0;
    nucode::ble::BLEAdvertisingSetHandle advertising_set;
    [[maybe_unused]] nucode::ble::BLEPeriodicSyncHandle periodic_sync;
    nucode::ble::BLEConnectionHandle current_connection;

    [[maybe_unused]] std::uint32_t advertising_report_count = 0U;
    [[maybe_unused]] std::uint32_t advertising_corrupt_count = 0U;
    [[maybe_unused]] std::uint32_t advertising_stale_count = 0U;
    [[maybe_unused]] bool advertising_sequences[advertising_updates + 1U] = {};
    [[maybe_unused]] std::uint32_t advertising_sequence = 0U;
    [[maybe_unused]] std::int64_t next_advertising_update_ms = 0;

    std::uint32_t pawr_response_count = 0U;
    std::uint32_t pawr_corrupt_count = 0U;
    std::uint32_t pawr_out_of_window_count = 0U;
    std::uint8_t pawr_subevent_mask = 0U;
    std::uint8_t pawr_slot_mask = 0U;
    [[maybe_unused]] std::uint16_t last_pawr_event = 0U;
    [[maybe_unused]] bool last_pawr_event_valid = false;

    [[maybe_unused]] std::uint32_t rotation_baseline = 0U;
    std::uint32_t connection_count = 0U;
    std::uint32_t disconnect_count = 0U;
    std::uint32_t pairing_count = 0U;
    std::uint32_t security_count = 0U;
    std::uint32_t identity_mismatch_count = 0U;
    std::uint32_t stale_handle_count = 0U;
    nucode::ble::PeerAddress stable_identity = {};
    bool stable_identity_valid = false;
    [[maybe_unused]] nucode::ble::BLEAddress
        observed_rpas[required_rpa_addresses] = {};
    [[maybe_unused]] std::uint32_t observed_rpa_count = 0U;
    [[maybe_unused]] bool security_request_pending = false;
    [[maybe_unused]] bool disconnect_pending = false;
    [[maybe_unused]] bool advertising_restart_pending = false;
    [[maybe_unused]] bool scan_restart_pending = false;
    [[maybe_unused]] bool privacy_transition_pending = false;
    std::int64_t pending_action_ms = 0;

    /** @brief 현재 image의 role 이름을 반환합니다. */
    const char *roleName()
    {
#if defined(NUCODE_M28_B2_CENTRAL)
        return "central";
#else
        return "peripheral";
#endif
    }

    /** @brief 첫 오류만 고정 FAIL protocol로 출력합니다. */
    void fail(const char *reason)
    {
        if (!protocol_failed)
        {
            Serial.print("NUCODE_M28B2_FAIL:role=");
            Serial.print(roleName());
            Serial.print(":reason=");
            Serial.println(reason == nullptr ? "unknown" : reason);
        }
        protocol_failed = true;
    }

    /** @brief 현재 nonce를 PASS token 끝에 결합합니다. */
    void passToken(const char *token)
    {
        Serial.print(token);
        Serial.print(":nonce=");
        Serial.println(nonce);
    }

    /** @brief 소문자 hex 한 글자를 binary nibble로 변환합니다. */
    std::uint8_t hexNibble(char value)
    {
        return static_cast<std::uint8_t>(value <= '9' ? value - '0' : value - 'a' + 10);
    }

    /** @brief start command의 128-bit nonce를 엄격하게 해석합니다. */
    bool acceptStartCommand()
    {
        const std::size_t prefix_length = ::strlen(start_prefix);
        if (::strncmp(command, start_prefix, prefix_length) != 0 ||
            ::strlen(command + prefix_length) != nonce_text_length)
        {
            return false;
        }
        for (std::size_t index = 0U; index < nonce_text_length; ++index)
        {
            const char value = command[prefix_length + index];
            if (!((value >= '0' && value <= '9') || (value >= 'a' && value <= 'f')))
            {
                return false;
            }
        }
        ::memcpy(nonce, command + prefix_length, nonce_text_length + 1U);
        for (std::size_t index = 0U; index < nonce_binary_length; ++index)
        {
            nonce_binary[index] = static_cast<std::uint8_t>(
                (hexNibble(nonce[index * 2U]) << 4U) |
                hexNibble(nonce[index * 2U + 1U]));
        }
        return true;
    }

    /** @brief 255-byte manufacturer AD payload에 nonce와 sequence를 기록합니다. */
    [[maybe_unused]] void buildAdvertisingPayload(std::uint8_t *payload,
                                                  std::uint32_t sequence)
    {
        payload[0] = 254U;
        payload[1] = 0xffU;
        payload[2] = static_cast<std::uint8_t>(company_id & 0xffU);
        payload[3] = static_cast<std::uint8_t>(company_id >> 8U);
        payload[4] = 'M';
        payload[5] = '2';
        payload[6] = '8';
        ::memcpy(&payload[7], nonce_binary, nonce_binary_length);
        payload[23] = static_cast<std::uint8_t>(sequence);
        payload[24] = static_cast<std::uint8_t>(sequence >> 8U);
        payload[25] = static_cast<std::uint8_t>(sequence >> 16U);
        payload[26] = static_cast<std::uint8_t>(sequence >> 24U);
        for (std::size_t index = 27U; index < 255U; ++index)
        {
            payload[index] = static_cast<std::uint8_t>(sequence + index);
        }
    }

    /** @brief 255-byte report의 모든 byte와 sequence를 검증합니다. */
    [[maybe_unused]] bool validAdvertisingPayload(
        const nucode::ble::BLEScanResult &result, std::uint32_t &sequence)
    {
        if (!result.extended || result.truncated || result.payload_length != 255U)
        {
            return false;
        }
        const std::uint8_t *payload = result.payload;
        if (payload[0] != 254U || payload[1] != 0xffU ||
            payload[2] != static_cast<std::uint8_t>(company_id & 0xffU) ||
            payload[3] != static_cast<std::uint8_t>(company_id >> 8U) ||
            payload[4] != 'M' || payload[5] != '2' || payload[6] != '8' ||
            ::memcmp(&payload[7], nonce_binary, nonce_binary_length) != 0)
        {
            return false;
        }
        sequence = static_cast<std::uint32_t>(payload[23]) |
                   (static_cast<std::uint32_t>(payload[24]) << 8U) |
                   (static_cast<std::uint32_t>(payload[25]) << 16U) |
                   (static_cast<std::uint32_t>(payload[26]) << 24U);
        if (sequence == 0U || sequence > advertising_updates)
        {
            return false;
        }
        for (std::size_t index = 27U; index < 255U; ++index)
        {
            if (payload[index] != static_cast<std::uint8_t>(sequence + index))
            {
                return false;
            }
        }
        return true;
    }

    /** @brief 작은 discovery AD payload를 company/tag/nonce로 구성합니다. */
    [[maybe_unused]] std::size_t buildDiscoveryPayload(std::uint8_t *payload,
                                                       const char tag[5])
    {
        payload[0] = 23U;
        payload[1] = 0xffU;
        payload[2] = static_cast<std::uint8_t>(company_id & 0xffU);
        payload[3] = static_cast<std::uint8_t>(company_id >> 8U);
        ::memcpy(&payload[4], tag, 4U);
        ::memcpy(&payload[8], nonce_binary, nonce_binary_length);
        return 24U;
    }

    /** @brief scan result가 현재 실행의 discovery tag와 정확히 일치하는지 확인합니다. */
    [[maybe_unused]] bool matchesDiscovery(
        const nucode::ble::BLEScanResult &result, const char tag[5])
    {
        return result.extended && !result.truncated && result.payload_length == 24U &&
               result.payload[0] == 23U && result.payload[1] == 0xffU &&
               result.payload[2] == static_cast<std::uint8_t>(company_id & 0xffU) &&
               result.payload[3] == static_cast<std::uint8_t>(company_id >> 8U) &&
               ::memcmp(&result.payload[4], tag, 4U) == 0 &&
               ::memcmp(&result.payload[8], nonce_binary, nonce_binary_length) == 0;
    }

    /** @brief PAwR subevent payload를 현재 nonce와 subevent에 결합합니다. */
    [[maybe_unused]] void buildPawrPayload(std::uint8_t *payload,
                                           std::uint8_t subevent)
    {
        payload[0] = 'P';
        payload[1] = 'W';
        payload[2] = 'R';
        ::memcpy(&payload[3], nonce_binary, nonce_binary_length);
        payload[19] = subevent;
    }

    /** @brief PAwR request payload의 nonce와 subevent를 검증합니다. */
    [[maybe_unused]] bool validPawrPayload(
        const nucode::ble::BLEPeriodicReport &report)
    {
        return report.payload_length == 20U && report.payload[0] == 'P' &&
               report.payload[1] == 'W' && report.payload[2] == 'R' &&
               ::memcmp(&report.payload[3], nonce_binary, nonce_binary_length) == 0 &&
               report.payload[19] == report.subevent && report.subevent < 4U;
    }

    /** @brief PAwR response payload를 현재 request 위치와 결합합니다. */
    [[maybe_unused]] void buildPawrResponse(std::uint8_t *payload,
                                            std::uint8_t subevent,
                                            std::uint8_t slot)
    {
        payload[0] = 'R';
        payload[1] = 'S';
        payload[2] = 'P';
        ::memcpy(&payload[3], nonce_binary, nonce_binary_length);
        payload[19] = subevent;
        payload[20] = slot;
    }

    /** @brief 보안 event identity가 이전 연결과 동일한지 누적 검사합니다. */
    void validateIdentity(const nucode::ble::PeerAddress &identity)
    {
        if (!stable_identity_valid)
        {
            stable_identity = identity;
            stable_identity_valid = true;
        }
        else if (stable_identity.type != identity.type ||
                 ::memcmp(stable_identity.value, identity.value,
                          sizeof(identity.value)) != 0)
        {
            ++identity_mismatch_count;
            fail("identity-mismatch");
        }
    }

    /** @brief PAwR result의 공통 고정 필드를 출력합니다. */
    void reportPawrPass(const char *role, std::uint32_t responses)
    {
        Serial.print("NUCODE_M28B2_");
        Serial.print(role);
        Serial.print(":PAWR:PASS:responses=");
        Serial.print(responses);
        Serial.print(":corrupt=");
        Serial.print(pawr_corrupt_count);
        Serial.print(":out_of_window=");
        Serial.print(pawr_out_of_window_count);
        Serial.print(":subevent_mask=");
        Serial.print(pawr_subevent_mask);
        Serial.print(":slot_mask=");
        Serial.print(pawr_slot_mask);
        Serial.print(":drops=");
#if defined(NUCODE_M28_B2_CENTRAL)
        Serial.print(BLEPeriodicAdvertising.droppedReports());
#else
        Serial.print(BLEPawr.droppedResponses());
#endif
        Serial.print(":nonce=");
        Serial.println(nonce);
    }

#if defined(NUCODE_M28_B2_CENTRAL)

    /** @brief central이 PAwR 뒤 privacy advertising scan을 시작합니다. */
    void startPrivacyScan()
    {
        if (BLEScan.running())
        {
            static_cast<void>(BLEScan.stop());
        }
        if (periodic_sync.valid())
        {
            static_cast<void>(BLEPeriodicAdvertising.deleteSync(periodic_sync));
            periodic_sync = {};
        }
        reportPawrPass("CENTRAL", pawr_response_count);
        phase = Phase::privacy_scan;
        if (!BLEScan.clearFilters() || !BLEScan.startExtended(false, false, false))
        {
            fail("privacy-scan-start");
        }
    }

    /** @brief 초기 주소와 세 번 회전한 RPA를 중복 없이 저장합니다. */
    void rememberRpa(const nucode::ble::BLEAddress &address)
    {
        for (std::uint32_t index = 0U; index < observed_rpa_count; ++index)
        {
            if (observed_rpas[index] == address)
            {
                return;
            }
        }
        if (observed_rpa_count < required_rpa_addresses)
        {
            observed_rpas[observed_rpa_count++] = address;
        }
    }

    /** @brief extended scan report를 현재 중앙 role phase에 전달합니다. */
    void onScanResult(const nucode::ble::BLEScanResult &result, void *)
    {
        if (!protocol_started || protocol_failed)
        {
            return;
        }
        if (phase == Phase::advertising)
        {
            std::uint32_t sequence = 0U;
            if (!validAdvertisingPayload(result, sequence))
            {
                return;
            }
            if (advertising_sequences[sequence])
            {
                ++advertising_stale_count;
                fail("advertising-duplicate");
                return;
            }
            advertising_sequences[sequence] = true;
            ++advertising_report_count;
            if (advertising_report_count == required_advertising_reports)
            {
                if (!BLEScan.stop())
                {
                    fail("advertising-scan-stop");
                    return;
                }
                Serial.print("NUCODE_M28B2_CENTRAL:ADV:PASS:reports=100:payload=255:corrupt=");
                Serial.print(advertising_corrupt_count);
                Serial.print(":stale=");
                Serial.print(advertising_stale_count);
                Serial.print(":nonce=");
                Serial.println(nonce);
                phase = Phase::pawr_discovery;
                if (!BLEScan.startExtended(false))
                {
                    fail("pawr-scan-start");
                }
            }
        }
        else if (phase == Phase::pawr_discovery && result.periodic_interval != 0U &&
                 matchesDiscovery(result, "PAWR"))
        {
            if (!BLEScan.stop() ||
                !BLEPeriodicAdvertising.createSync(result.address, result.sid,
                                                    periodic_sync))
            {
                fail("pawr-sync-create");
            }
        }
        else if (phase == Phase::privacy_scan)
        {
            if (matchesDiscovery(result, "ROT0"))
            {
                rememberRpa(result.address);
            }
            else if (matchesDiscovery(result, "PRIV") && result.connectable &&
                     observed_rpa_count == required_rpa_addresses)
            {
                if (!BLEScan.stop() || !BLEConnection.connect(result.address,
                                                              current_connection))
                {
                    fail("privacy-connect");
                    return;
                }
                phase = Phase::privacy_link;
                passToken("NUCODE_M28B2_CENTRAL:RPA:PASS:rotations=3");
            }
        }
    }

    /** @brief PAwR event마다 한 subevent/slot response만 예약합니다. */
    void onPeriodicReport(const nucode::ble::BLEPeriodicReport &report, void *)
    {
        if (phase != Phase::pawr_active || protocol_failed)
        {
            return;
        }
        if (!validPawrPayload(report))
        {
            ++pawr_corrupt_count;
            fail("pawr-request-corrupt");
            return;
        }
        if (last_pawr_event_valid && report.periodic_event_counter == last_pawr_event)
        {
            return;
        }
        const std::uint8_t selected =
            static_cast<std::uint8_t>(report.periodic_event_counter % 4U);
        if (report.subevent != selected)
        {
            return;
        }
        std::uint8_t response[21] = {};
        buildPawrResponse(response, selected, selected);
        if (!BLEPawr.sendResponse(report.sync, report.periodic_event_counter,
                                  report.subevent, selected, selected,
                                  response, sizeof(response)))
        {
            fail("pawr-response-send");
            return;
        }
        last_pawr_event = report.periodic_event_counter;
        last_pawr_event_valid = true;
        ++pawr_response_count;
        pawr_subevent_mask |= static_cast<std::uint8_t>(1U << selected);
        pawr_slot_mask |= static_cast<std::uint8_t>(1U << selected);
        if (pawr_response_count >= central_pawr_responses)
        {
            startPrivacyScan();
        }
    }

#else

    /** @brief peripheral이 nonce-bound 255-byte advertising 갱신을 시작합니다. */
    void startAdvertisingPhase()
    {
        nucode::ble::BLEExtendedAdvertisingParameters parameters{};
        parameters.sid = 7U;
        parameters.interval_min = 0x0030U;
        parameters.interval_max = 0x0030U;
        std::uint8_t payload[255] = {};
        advertising_sequence = 1U;
        buildAdvertisingPayload(payload, advertising_sequence);
        if (!BLEExtendedAdvertising.create(parameters, advertising_set) ||
            !BLEExtendedAdvertising.setData(advertising_set, payload, sizeof(payload)) ||
            !BLEExtendedAdvertising.start(advertising_set))
        {
            fail("advertising-start");
            return;
        }
        phase = Phase::advertising;
        next_advertising_update_ms = k_uptime_get() + advertising_update_interval_ms;
        passToken("NUCODE_M28B2_PERIPHERAL:ADVERTISE:PASS");
    }

    /** @brief peripheral이 4×4 PAwR advertiser를 구성합니다. */
    void startPawrPhase()
    {
        nucode::ble::BLEExtendedAdvertisingParameters extended{};
        extended.sid = pawr_sid;
        std::uint8_t discovery[24] = {};
        buildDiscoveryPayload(discovery, "PAWR");
        if (!BLEExtendedAdvertising.create(extended, advertising_set) ||
            !BLEExtendedAdvertising.setData(advertising_set, discovery,
                                            sizeof(discovery)) ||
            !BLEPawr.configureAdvertiser(advertising_set))
        {
            fail("pawr-configure");
            return;
        }
        for (std::uint8_t subevent = 0U; subevent < 4U; ++subevent)
        {
            std::uint8_t payload[20] = {};
            buildPawrPayload(payload, subevent);
            if (!BLEPawr.setSubeventData(advertising_set, subevent, payload,
                                        sizeof(payload)))
            {
                fail("pawr-subevent-data");
                return;
            }
        }
        if (!BLEPeriodicAdvertising.start(advertising_set) ||
            !BLEExtendedAdvertising.start(advertising_set))
        {
            fail("pawr-start");
            return;
        }
        phase = Phase::pawr_active;
    }

    /** @brief 세 번의 RPA 회전을 관측할 non-connectable set을 시작합니다. */
    void startPrivacyRotation()
    {
        nucode::ble::BLEExtendedAdvertisingParameters parameters{};
        parameters.sid = privacy_sid;
        std::uint8_t payload[24] = {};
        buildDiscoveryPayload(payload, "ROT0");
        rotation_baseline = BLEPrivacy.expirationCount();
        if (!BLEPrivacy.setRotationTimeout(1U) ||
            !BLEExtendedAdvertising.create(parameters, advertising_set) ||
            !BLEExtendedAdvertising.setData(advertising_set, payload,
                                            sizeof(payload)) ||
            !BLEExtendedAdvertising.start(advertising_set))
        {
            fail("privacy-rotation-start");
            return;
        }
        phase = Phase::privacy_rotation;
    }

    /** @brief 회전 판정 뒤 connectable privacy set을 시작합니다. */
    void startPrivateConnectionAdvertising()
    {
        if (BLEExtendedAdvertising.running(advertising_set) &&
            !BLEExtendedAdvertising.stop(advertising_set))
        {
            fail("privacy-rotation-stop");
            return;
        }
        if (!BLEExtendedAdvertising.remove(advertising_set))
        {
            fail("privacy-rotation-remove");
            return;
        }
        nucode::ble::BLEExtendedAdvertisingParameters parameters{};
        parameters.connectable = true;
        parameters.sid = privacy_sid;
        std::uint8_t payload[24] = {};
        buildDiscoveryPayload(payload, "PRIV");
        if (!BLEExtendedAdvertising.create(parameters, advertising_set) ||
            !BLEExtendedAdvertising.setData(advertising_set, payload,
                                            sizeof(payload)) ||
            !BLEExtendedAdvertising.start(advertising_set))
        {
            fail("privacy-advertising-start");
            return;
        }
        phase = Phase::privacy_link;
        passToken("NUCODE_M28B2_PERIPHERAL:RPA:PASS:rotations=3");
    }

    /** @brief advertiser가 받은 PAwR response의 nonce와 위치를 검증합니다. */
    void onPawrResponse(const nucode::ble::BLEPawrResponse &response, void *)
    {
        if (phase != Phase::pawr_active || protocol_failed || !response.received)
        {
            return;
        }
        if (response.payload_length != 21U || response.payload[0] != 'R' ||
            response.payload[1] != 'S' || response.payload[2] != 'P' ||
            ::memcmp(&response.payload[3], nonce_binary, nonce_binary_length) != 0)
        {
            ++pawr_corrupt_count;
            fail("pawr-response-corrupt");
            return;
        }
        if (response.subevent >= 4U || response.response_slot >= 4U ||
            response.payload[19] != response.subevent ||
            response.payload[20] != response.response_slot)
        {
            ++pawr_out_of_window_count;
            fail("pawr-response-window");
            return;
        }
        ++pawr_response_count;
        pawr_subevent_mask |= static_cast<std::uint8_t>(1U << response.subevent);
        pawr_slot_mask |= static_cast<std::uint8_t>(1U << response.response_slot);
        if (pawr_response_count == required_pawr_responses)
        {
            if (!BLEPeriodicAdvertising.stop(advertising_set) ||
                !BLEExtendedAdvertising.stop(advertising_set) ||
                !BLEExtendedAdvertising.remove(advertising_set))
            {
                fail("pawr-stop");
                return;
            }
            reportPawrPass("PERIPHERAL", pawr_response_count);
            startPrivacyRotation();
        }
    }

#endif

    /** @brief 두 role의 privacy 연결·RPA·sync event를 처리합니다. */
    void onBleEvent(const nucode::ble::BLEEventInfo &information, void *)
    {
        if (!protocol_started || protocol_failed)
        {
            return;
        }
#if defined(NUCODE_M28_B2_CENTRAL)
        if (information.event == nucode::ble::BLEEvent::periodic_sync_synchronized &&
            phase == Phase::pawr_discovery)
        {
            const std::uint8_t subevents[] = {0U, 1U, 2U, 3U};
            if (!BLEPawr.configureScanner(information.periodic_sync, subevents,
                                          sizeof(subevents)))
            {
                fail("pawr-scanner-configure");
                return;
            }
            phase = Phase::pawr_active;
        }
        else if (information.event == nucode::ble::BLEEvent::periodic_sync_terminated &&
                 phase == Phase::pawr_active)
        {
            if (pawr_response_count < 99U)
            {
                fail("pawr-response-rate");
            }
            else
            {
                startPrivacyScan();
            }
        }
#else
        if (information.event == nucode::ble::BLEEvent::rpa_expired &&
            phase == Phase::privacy_rotation &&
            BLEPrivacy.expirationCount() - rotation_baseline >= required_rpa_rotations)
        {
            privacy_transition_pending = true;
            pending_action_ms = k_uptime_get() + 600;
        }
#endif
        if (information.event == nucode::ble::BLEEvent::connected &&
            phase == Phase::privacy_link)
        {
            current_connection = information.connection;
            ++connection_count;
            security_request_pending =
#if defined(NUCODE_M28_B2_CENTRAL)
                true;
#else
                false;
#endif
            pending_action_ms = k_uptime_get() + security_request_delay_ms;
        }
        else if (information.event == nucode::ble::BLEEvent::identity_resolved &&
                 phase == Phase::privacy_link)
        {
            const nucode::ble::BLEAddress identity =
                BLEConnection.peerAddress(information.connection);
            nucode::ble::PeerAddress peer{};
            peer.type = static_cast<std::uint8_t>(identity.type());
            ::memcpy(peer.value, identity.data(), sizeof(peer.value));
            validateIdentity(peer);
        }
        else if (information.event == nucode::ble::BLEEvent::disconnected &&
                 phase == Phase::privacy_link)
        {
            ++disconnect_count;
            if (BLEConnection.connected(current_connection))
            {
                ++stale_handle_count;
                fail("stale-handle-active");
                return;
            }
            current_connection = {};
            if (connection_count < required_reconnects + 1U)
            {
#if defined(NUCODE_M28_B2_CENTRAL)
                scan_restart_pending = true;
#else
                advertising_restart_pending = true;
#endif
                pending_action_ms = k_uptime_get() + reconnect_advertising_delay_ms;
            }
        }
    }

    /** @brief Just Works와 보안 완료를 pairing·identity·재연결 수치로 변환합니다. */
    void onSecurityEvent(const nucode::ble::SecurityEventRecord &event, void *)
    {
        if (!protocol_started || protocol_failed || phase != Phase::privacy_link)
        {
            return;
        }
        if (event.event == nucode::ble::SecurityEvent::pairing_requested)
        {
            if (!BLESecurity.acceptPairing(true))
            {
                fail("pairing-accept");
            }
        }
        else if (event.event == nucode::ble::SecurityEvent::paired)
        {
            ++pairing_count;
            if (pairing_count > 1U)
            {
                fail("pairing-repeated");
            }
        }
        else if (event.event == nucode::ble::SecurityEvent::security_changed &&
                 event.level >= nucode::ble::SecurityLevel::encrypted)
        {
            validateIdentity(event.peer);
            ++security_count;
#if defined(NUCODE_M28_B2_CENTRAL)
            disconnect_pending = true;
            pending_action_ms = k_uptime_get() + secured_disconnect_delay_ms;
#endif
        }
        else if (event.event == nucode::ble::SecurityEvent::pairing_failed ||
                 event.event == nucode::ble::SecurityEvent::timeout ||
                 event.event == nucode::ble::SecurityEvent::error)
        {
            fail("security-event");
        }
    }

    /** @brief privacy 반복이 exact 기준을 만족하면 role FINAL을 출력합니다. */
    void finishPrivacyIfComplete()
    {
        if (phase != Phase::privacy_link || connection_count != required_reconnects + 1U ||
            security_count != required_reconnects + 1U || disconnect_count != connection_count)
        {
            return;
        }
        if (pairing_count != 1U || BLESecurity.bondCount() != 1U ||
            identity_mismatch_count != 0U || stale_handle_count != 0U)
        {
            fail("privacy-final-counts");
            return;
        }
        Serial.print("NUCODE_M28B2_");
#if defined(NUCODE_M28_B2_CENTRAL)
        Serial.print("CENTRAL");
#else
        Serial.print("PERIPHERAL");
#endif
        Serial.print(":PRIV:PASS:connections=21:reconnects=20:pairings=1:bond_count=1:identity_mismatch=0:stale=0:nonce=");
        Serial.println(nonce);
        Serial.print("NUCODE_M28B2_");
#if defined(NUCODE_M28_B2_CENTRAL)
        Serial.print("CENTRAL");
#else
        Serial.print("PERIPHERAL");
#endif
        Serial.print(":FINAL:PASS:adv=PASS:pawr=PASS:privacy=PASS:nonce=");
        Serial.println(nonce);
        phase = Phase::complete;
    }

    /** @brief 검증된 START 뒤 role별 첫 phase를 실행합니다. */
    void startProtocol()
    {
        if (!acceptStartCommand())
        {
            fail("bad-start-command");
            return;
        }
        if (!BLESecurity.eraseAllBonds())
        {
            fail("bond-clear");
            return;
        }
        protocol_started = true;
        protocol_deadline_ms = k_uptime_get() + protocol_timeout_ms;
#if defined(NUCODE_M28_B2_CENTRAL)
        phase = Phase::advertising;
        if (!BLEScan.clearFilters() || !BLEScan.startExtended(false))
        {
            fail("advertising-scan-start");
        }
#else
        startAdvertisingPhase();
#endif
    }

    /** @brief UART의 한 줄 START command를 bounded buffer로 수집합니다. */
    void pollHostCommand()
    {
        while (Serial.available() > 0 && !protocol_started && !protocol_failed)
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
                startProtocol();
                return;
            }
            if (command_length + 1U >= sizeof(command))
            {
                fail("command-overflow");
                return;
            }
            command[command_length++] = value;
        }
    }

    /** @brief callback 밖에서 실행해야 하는 유한 phase 작업을 처리합니다. */
    void driveProtocol()
    {
        if (!protocol_started || protocol_failed || phase == Phase::complete)
        {
            return;
        }
        const std::int64_t now = k_uptime_get();
        if (now >= protocol_deadline_ms)
        {
            fail("protocol-timeout");
            return;
        }
#if !defined(NUCODE_M28_B2_CENTRAL)
        if (phase == Phase::advertising && now >= next_advertising_update_ms)
        {
            if (advertising_sequence < advertising_updates)
            {
                ++advertising_sequence;
                std::uint8_t payload[255] = {};
                buildAdvertisingPayload(payload, advertising_sequence);
                if (!BLEExtendedAdvertising.stop(advertising_set) ||
                    !BLEExtendedAdvertising.setData(advertising_set, payload,
                                                    sizeof(payload)) ||
                    !BLEExtendedAdvertising.start(advertising_set))
                {
                    fail("advertising-update");
                    return;
                }
                next_advertising_update_ms = now + advertising_update_interval_ms;
            }
            else
            {
                if (!BLEExtendedAdvertising.stop(advertising_set) ||
                    !BLEExtendedAdvertising.remove(advertising_set))
                {
                    fail("advertising-stop");
                    return;
                }
                passToken("NUCODE_M28B2_PERIPHERAL:ADV:PASS:reports=110:payload=255:corrupt=0:stale=0");
                startPawrPhase();
            }
        }
        if (advertising_restart_pending && now >= pending_action_ms)
        {
            advertising_restart_pending = false;
            if (!BLEExtendedAdvertising.start(advertising_set))
            {
                fail("privacy-readvertise");
            }
        }
        if (privacy_transition_pending && now >= pending_action_ms)
        {
            privacy_transition_pending = false;
            startPrivateConnectionAdvertising();
        }
#else
        if (security_request_pending && now >= pending_action_ms)
        {
            security_request_pending = false;
            if (!BLESecurity.requestSecurity())
            {
                fail("security-request");
            }
        }
        if (disconnect_pending && now >= pending_action_ms)
        {
            disconnect_pending = false;
            if (!BLEConnection.disconnect(current_connection))
            {
                fail("privacy-disconnect");
            }
        }
        if (scan_restart_pending && now >= pending_action_ms)
        {
            scan_restart_pending = false;
            phase = Phase::privacy_scan;
            if (!BLEScan.clearFilters() || !BLEScan.startExtended(false))
            {
                fail("privacy-rescan");
            }
        }
#endif
        finishPrivacyIfComplete();
    }

} // namespace

void setup()
{
    Serial.begin(115200);
    const std::int64_t serial_deadline = k_uptime_get() + 5000;
    while (!Serial && k_uptime_get() < serial_deadline)
    {
        delay(10);
    }
    const nucode::ble::SecurityConfig security = {
        nucode::ble::SecurityLevel::encrypted,
        true,
        30000U,
        nucode::ble::SecurityIoCapability::no_input_output,
    };
    BLESecurity.onEvent(onSecurityEvent);
    if (!BLESecurity.begin(security))
    {
        fail("security-begin");
        return;
    }
    BLEDevice.onEventInfo(onBleEvent);
#if defined(NUCODE_M28_B2_CENTRAL)
    BLEScan.onResult(onScanResult);
    BLEPeriodicAdvertising.onReport(onPeriodicReport);
#else
    BLEPawr.onResponse(onPawrResponse);
#endif
    if (!BLEDevice.begin(
#if defined(NUCODE_M28_B2_CENTRAL)
            "NU54-M28-B2-C"
#else
            "NU54-M28-B2-P"
#endif
            ))
    {
        fail("device-begin");
        return;
    }
    Serial.print("NUCODE_M28B2_READY:role=");
    Serial.println(roleName());
}

void loop()
{
    pollHostCommand();
    BLEDevice.poll();
    BLESecurity.poll();
    driveProtocol();
    delay(1);
}
