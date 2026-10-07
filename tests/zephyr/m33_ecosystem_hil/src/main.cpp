/** @file @brief 합성 ANCS/AMS peer와 실제 AppleClient의 유한 무선 시험입니다.
 * SPDX-License-Identifier: MIT
 */
#include <NUCODE_BLE_Companion.h>
#include <NUCODE_BLE_Security.h>
#include <zephyr/kernel.h>
#include <zephyr/drivers/watchdog.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

using namespace nucode::ble;
using namespace nucode::ble::companion;
using CompanionError = nucode::ble::companion::Error;
using CompanionEvent = nucode::ble::companion::Event;
namespace
{
    constexpr const char *protocol = "M33ECO|2";
    constexpr size_t maximum_bonds = 4U;
#if defined(COMPANION_PEER)
    constexpr const char *role = "peer";
#else
    constexpr const char *role = "client";
#endif
    AppleClient client;
    BLEConnectionHandle link;
    char nonce[33];
    char case_name[16];
    char peer_name[32];
    char line[100];
    size_t line_used;
    bool line_overflow;
    bool initialized;
    bool active;
    bool stopping;
    bool failed;
    bool reported;
    bool malformed;
    bool media_commands_sent;
    bool peer_released;
    bool security_failure_seen;
    bool companion_security_failure_seen;
    bool session_bonded;
    bool data_complete;
    bool baseline_ready;
    bool owned_bond;
    bool paired_peer_ready;
    Service selected;
    int64_t deadline;
    int64_t next_send;
    uint32_t uid;
    unsigned packets;
    unsigned attributes;
    unsigned writes;
    unsigned phase;
    unsigned negative;
    unsigned security_level;
    unsigned pairings;
    unsigned reconnects;
    unsigned security_rejects;
    Notification latest;
    PeerAddress baseline_bonds[maximum_bonds] = {};
    PeerAddress owned_peer = {};
    PeerAddress paired_peer = {};
    size_t baseline_bond_count = 0U;
    char owned_nonce[33] = {};
    const device *watchdog = DEVICE_DT_GET(DT_ALIAS(watchdog0));
    int watchdog_channel = -1;

    /** @brief 결과를 nonce·역할·source와 함께 한 줄로 출력합니다. */
    void record(const char *event)
    {
        Serial.print(protocol);
        Serial.print('|');
        Serial.print(event);
        Serial.print("|role=");
        Serial.print(role);
        Serial.print("|nonce=");
        Serial.print(nonce);
        Serial.print("|case=");
        Serial.print(case_name);
        Serial.print("|revision=");
        Serial.print(COMPANION_CORE_REVISION);
        Serial.print("|identity=");
        Serial.print(COMPANION_FIRMWARE_IDENTITY);
        Serial.print("|packets=");
        Serial.print(packets);
        Serial.print("|attributes=");
        Serial.print(attributes);
        Serial.print("|writes=");
        Serial.print(writes);
        Serial.print("|negative=");
        Serial.print(negative);
        Serial.print("|security=");
        Serial.print(security_level);
        Serial.print("|pairings=");
        Serial.print(pairings);
        Serial.print("|bonded=");
        Serial.print(session_bonded ? 1 : 0);
        Serial.print("|reconnects=");
        Serial.print(reconnects);
        Serial.print("|security_rejects=");
        Serial.print(security_rejects);
        Serial.print("|test_bond=");
        Serial.print(owned_bond ? 1 : 0);
        Serial.print("|links=");
        Serial.println(BLEConnection.count());
    }

    /** @brief 실패 시 후속 무선 작업을 중단하고 원인을 보존합니다. */
    void fail(const char *reason)
    {
        if (!failed)
        {
            failed = true;
            Serial.print("M33ECO_ERROR reason=");
            Serial.println(reason);
            record("FAIL");
            client.end();
            AppleClient::stopAdvertising();
            (void)BLEScan.stop();
            if (BLEConnection.connected(link))
            {
                (void)BLEConnection.disconnect(link);
            }
        }
    }

    /** @brief 공개 주소 구조를 직렬화하지 않고 두 identity를 비교합니다. */
    bool samePeer(const PeerAddress &left, const PeerAddress &right)
    {
        return left.type == right.type && memcmp(left.value, right.value, sizeof(left.value)) == 0;
    }

    /** @brief 현재 연결 전 목록에 지정 identity가 있었는지 검사합니다. */
    bool baselineContains(const PeerAddress &peer)
    {
        for (size_t index = 0U; index < baseline_bond_count; ++index)
        {
            if (samePeer(baseline_bonds[index], peer))
            {
                return true;
            }
        }
        return false;
    }

    /** @brief 첫 START 직전의 기존 bond 목록을 삭제 불가 baseline으로 고정합니다. */
    bool captureBaseline()
    {
        if (baseline_ready)
        {
            return true;
        }
        baseline_bond_count = BLESecurity.bondCount();
        if (baseline_bond_count > maximum_bonds ||
            BLESecurity.copyBonds(baseline_bonds, maximum_bonds) != baseline_bond_count)
        {
            return false;
        }
        baseline_ready = true;
        return true;
    }

    /** @brief 현재 bond 집합이 baseline과 선택적 시험 bond의 정확한 합집합인지 확인합니다. */
    bool bondSetMatches(bool include_owned)
    {
        PeerAddress current[maximum_bonds] = {};
        const size_t expected = baseline_bond_count + (include_owned ? 1U : 0U);
        const size_t count = BLESecurity.bondCount();
        if (!baseline_ready || count != expected || count > maximum_bonds ||
            BLESecurity.copyBonds(current, maximum_bonds) != count)
        {
            return false;
        }
        for (size_t index = 0U; index < count; ++index)
        {
            bool found = include_owned && samePeer(current[index], owned_peer);
            for (size_t baseline = 0U; baseline < baseline_bond_count; ++baseline)
            {
                found = found || samePeer(current[index], baseline_bonds[baseline]);
            }
            if (!found)
            {
                return false;
            }
        }
        for (size_t baseline = 0U; baseline < baseline_bond_count; ++baseline)
        {
            bool found = false;
            for (size_t index = 0U; index < count; ++index)
            {
                found = found || samePeer(current[index], baseline_bonds[baseline]);
            }
            if (!found)
            {
                return false;
            }
        }
        return !include_owned || !baselineContains(owned_peer);
    }

    /** @brief 신규 pairing peer가 baseline에 없고 유일하게 증가했을 때만 시험 소유로 지정합니다. */
    void refreshOwnedBond()
    {
        if (owned_bond || !paired_peer_ready || !baseline_ready || baselineContains(paired_peer))
        {
            return;
        }
        owned_peer = paired_peer;
        if (bondSetMatches(true))
        {
            owned_bond = true;
            strcpy(owned_nonce, nonce);
        }
    }

    /** @brief 보안·bond 계약과 data 분모가 모두 끝난 뒤에만 성공을 보고합니다. */
    void reportPassIfReady()
    {
        if (reported || failed || !active || !data_complete)
        {
            return;
        }
        if (strcmp(case_name, "access_denied") == 0)
        {
#if defined(COMPANION_PEER)
            constexpr unsigned expected_security_rejects = 1U;
#else
            constexpr unsigned expected_security_rejects = 0U;
#endif
            if (security_failure_seen && companion_security_failure_seen &&
                security_rejects == expected_security_rejects && security_level == 0U &&
                pairings == 0U && !session_bonded && reconnects == 0U && packets == 0U &&
                attributes == 0U && writes == 0U)
            {
                reported = true;
                record("PASS");
            }
            return;
        }
        refreshOwnedBond();
        const bool fresh = pairings == 1U && owned_bond && strcmp(owned_nonce, nonce) == 0;
        const bool restored = pairings == 0U && owned_bond && reconnects == 1U;
        if (security_level == 1U && session_bonded && (fresh || restored))
        {
            reported = true;
            record("PASS");
        }
    }

    /** @brief data 경로 완료를 보안 완료와 합류시킵니다. */
    void completeData()
    {
        data_complete = true;
        reportPassIfReady();
    }

    /** @brief idle에서 이번 실행이 만든 exact peer 한 개만 제거하고 baseline을 재검증합니다. */
    void cleanupOwnedBond(const char *supplied)
    {
        if (!initialized || active || stopping || BLEConnection.count() != 0U ||
            BLEConnection.connecting() || !owned_bond || strcmp(supplied, owned_nonce) != 0 ||
            !bondSetMatches(true))
        {
            record("REJECT");
            return;
        }
        strcpy(nonce, supplied);
        if (!BLESecurity.eraseBond(owned_peer))
        {
            fail("cleanup_erase");
            return;
        }
        if (!bondSetMatches(false))
        {
            fail("cleanup_baseline");
            return;
        }
        owned_bond = false;
        owned_peer = {};
        owned_nonce[0] = 0;
        case_name[0] = 0;
        failed = reported = malformed = media_commands_sent = false;
        security_failure_seen = companion_security_failure_seen = false;
        session_bonded = data_complete = paired_peer_ready = false;
        paired_peer = {};
        packets = attributes = writes = phase = negative = 0U;
        security_level = pairings = reconnects = security_rejects = 0U;
        record("CLEANED");
    }

#if defined(COMPANION_PEER)
    /** @brief 필요한 byte가 올바른 link의 command에서 왔는지 검사합니다. */
    bool requestMatches(const uint8_t *data, size_t length, uint8_t command)
    {
        return data != nullptr && length >= 5 && data[0] == command &&
               data[1] == static_cast<uint8_t>(uid) && data[2] == static_cast<uint8_t>(uid >> 8) &&
               data[3] == static_cast<uint8_t>(uid >> 16) &&
               data[4] == static_cast<uint8_t>(uid >> 24);
    }

    BLEService ancs(BLEUuid("7905f431-b5ce-4e99-a40f-4b1e122d00d0"));
    BLEService ams(BLEUuid("89d3502b-0f36-433a-8ef4-c502ad55f8dc"));
    BLECharacteristic ns(BLEUuid("9fbf120d-6301-42d9-8c58-25e699a21dbd"), BLEProperty::notify,
                         BLEPermission::none, 20);
    BLECharacteristic ds(BLEUuid("22eac6e9-24d6-4bb5-be44-b36ace7c7bfb"), BLEProperty::notify,
                         BLEPermission::none, 20);
    BLECharacteristic cp(BLEUuid("69d1d8f3-45e1-49a8-9821-9bbdfdaad9d9"), BLEProperty::write,
                         BLEPermission::write, 16);
    BLECharacteristic rc(BLEUuid("9b3c81d8-57b1-4a8a-b8df-0e56f7ca51c2"),
                         BLEProperty::write | BLEProperty::notify, BLEPermission::write, 16);
    BLECharacteristic eu(BLEUuid("2f7cabce-808d-411f-9a0c-bb92ba96c102"),
                         BLEProperty::write | BLEProperty::notify, BLEPermission::write, 20);
    BLECharacteristic ea(BLEUuid("c6b2f38c-23ab-46d8-a6ab-a3a870bbd5d7"),
                         BLEProperty::write | BLEProperty::read,
                         BLEPermission::write | BLEPermission::read, 20);

    /** @brief SDK 없이 합성 server가 실제 Control Point 내용을 검증합니다. */
    void characteristicEvent(BLECharacteristic &characteristic,
                             const BLECharacteristicEventInfo &event, void *)
    {
        if (!active || event.event != BLECharacteristicEvent::written)
        {
            return;
        }
        if (event.connection != link)
        {
            fail("cross_link");
            return;
        }
        if (&characteristic == &cp)
        {
            if (requestMatches(event.data, event.length, 0) && event.length == 8 &&
                event.data[5] == 1)
            {
                ++writes;
                phase = 2;
                next_send = k_uptime_get() + 100;
            }
            else if (requestMatches(event.data, event.length, 2) && event.length == 6 &&
                     event.data[5] == 0)
            {
                ++writes;
                completeData();
            }
            else
            {
                fail("ancs_command");
            }
        }
        else if (&characteristic == &eu)
        {
            if (event.length != 2 || event.data[0] != 2 || event.data[1] != 2)
            {
                fail("media_selection");
            }
            else
            {
                ++writes;
                phase = 2;
                next_send = k_uptime_get() + 100;
            }
        }
        else if (&characteristic == &ea)
        {
            if (event.length != 2 || event.data[0] != 2 || event.data[1] != 2 ||
                !ea.setValue("complete title", 14))
            {
                fail("media_read_selection");
            }
            else
            {
                ++writes;
            }
        }
        else if (&characteristic == &rc)
        {
            if (event.length != 1 || event.data[0] != 2)
            {
                fail("media_command");
            }
            else
            {
                ++writes;
                completeData();
            }
        }
    }

    /** @brief 이름과 세션 nonce가 일치한 실제 광고에만 연결합니다. */
    void scanned(const BLEScanResult &result, void *)
    {
        if (active && !stopping && BLEScan.running() && !BLEConnection.connecting() &&
            !BLEConnection.connected())
        {
            (void)BLEScan.stop();
            if (!BLEConnection.connect(result.address, link))
            {
                fail("connect");
            }
        }
    }

    /** @brief 합성 notification·분할 attribute·AMS update를 유한하게 전송합니다. */
    void peerPoll()
    {
        if (!active || failed || !peer_released || !BLEConnection.connected(link) ||
            k_uptime_get() < next_send)
        {
            return;
        }
        if (selected == Service::notifications && ns.notificationSubscribed() &&
            ds.notificationSubscribed())
        {
            if (phase == 0)
            {
                const uint8_t data[] = {static_cast<uint8_t>(malformed ? 3 : 0),
                                        0x18,
                                        6,
                                        1,
                                        static_cast<uint8_t>(uid),
                                        static_cast<uint8_t>(uid >> 8),
                                        static_cast<uint8_t>(uid >> 16),
                                        static_cast<uint8_t>(uid >> 24)};
                if (!ns.setValue(data, sizeof(data)) || !ns.notify(link))
                {
                    fail("notify");
                }
                ++packets;
                phase = 1;
                if (malformed)
                {
                    ++negative;
                    completeData();
                }
            }
            else if (phase == 2)
            {
                const uint8_t header[] = {0,
                                          static_cast<uint8_t>(uid),
                                          static_cast<uint8_t>(uid >> 8),
                                          static_cast<uint8_t>(uid >> 16),
                                          static_cast<uint8_t>(uid >> 24),
                                          1,
                                          5,
                                          0};
                if (!ds.setValue(header, sizeof(header)) || !ds.notify(link))
                {
                    fail("attribute_header");
                }
                phase = 3;
                next_send = k_uptime_get() + 100;
            }
            else if (phase == 3)
            {
                if (!ds.setValue("title", 5) || !ds.notify(link))
                {
                    fail("attribute_text");
                }
                ++attributes;
                phase = 4;
            }
        }
        else if (selected == Service::media && rc.notificationSubscribed() &&
                 eu.notificationSubscribed())
        {
            if (!media_commands_sent)
            {
                const uint8_t supported[] = {0, 1, 2, 3};
                if (!rc.setValue(supported, sizeof(supported)) || !rc.notify(link))
                {
                    fail("supported");
                }
                media_commands_sent = true;
                if (phase == 0)
                {
                    phase = 1;
                }
            }
            else if (phase == 2)
            {
                const uint8_t update[] = {
                    2, 2, static_cast<uint8_t>(malformed ? 2 : 1), 't', 'i', 't', 'l', 'e'};
                if (!eu.setValue(update, sizeof(update)) || !eu.notify(link))
                {
                    fail("update");
                }
                ++packets;
                phase = 3;
                if (malformed)
                {
                    ++negative;
                    completeData();
                }
            }
        }
    }
#else
    /** @brief production AppleClient의 수신과 제어 응답을 nonce payload와 대조합니다. */
    void companionEvent(const EventInfo &event, void *)
    {
        if (!active || stopping)
        {
            return;
        }
        if (event.event == CompanionEvent::ready)
        {
            record("CLIENT_READY");
            if (client.sendMediaCommand(13) != CompanionError::unsupported)
            {
                fail("unsupported_command");
            }
            ++negative;
            if (selected == Service::media)
            {
                const uint8_t selection[] = {2};
                if (client.selectMediaAttributes(2, selection, 1) != CompanionError::none)
                {
                    fail("select");
                }
            }
        }
        else if (event.event == CompanionEvent::notification)
        {
            if (event.notification.uid != uid || event.notification.category != 6)
            {
                fail("notification_payload");
                return;
            }
            latest = event.notification;
            ++packets;
            if (client.requestAttribute(uid, 1) != CompanionError::none)
            {
                fail("request");
            }
        }
        else if (event.event == CompanionEvent::attribute)
        {
            if (event.length != 5 || memcmp(event.data, "title", 5) != 0 ||
                event.notification.uid != uid)
            {
                fail("attribute_payload");
                return;
            }
            ++attributes;
            phase = 2;
        }
        else if (event.event == CompanionEvent::media_update)
        {
            if (event.entity != 2 || event.attribute != 2)
            {
                fail("entity");
                return;
            }
            if (event.truncated)
            {
                ++packets;
                phase = 2;
            }
            else if (event.length == 14 && memcmp(event.data, "complete title", 14) == 0)
            {
                ++attributes;
                phase = 3;
            }
            else
            {
                fail("media_payload");
            }
        }
        else if (event.event == CompanionEvent::command_complete)
        {
            ++writes;
            if (phase == 4)
            {
                completeData();
            }
        }
        else if (event.event == CompanionEvent::error)
        {
            if (malformed && event.error == CompanionError::malformed)
            {
                ++negative;
                completeData();
            }
            else if (strcmp(case_name, "access_denied") == 0 &&
                     event.error == CompanionError::security)
            {
                companion_security_failure_seen = true;
                data_complete = true;
                reportPassIfReady();
            }
            else
            {
                fail("client_error");
            }
        }
    }
#endif

    /** @brief SMP 승인·거부와 새 bond/동일 bond 재연결을 공개 Security API로 판정합니다. */
    void securityEvent(const SecurityEventRecord &event, void *)
    {
        if (!active || stopping)
        {
            return;
        }
        if (!event.connection.valid() || event.connection != link)
        {
            fail("security_cross_link");
            return;
        }
        switch (event.event)
        {
        case SecurityEvent::pairing_requested:
            if (strcmp(case_name, "access_denied") == 0)
            {
                if (!BLESecurity.acceptPairing(event.connection, false))
                {
                    fail("pairing_reject");
                }
                else
                {
                    ++security_rejects;
                }
            }
            else if (!BLESecurity.acceptPairing(event.connection, true))
            {
                fail("pairing_accept");
            }
            break;
        case SecurityEvent::paired:
            ++pairings;
            paired_peer = event.peer;
            paired_peer_ready = true;
            session_bonded = event.bond_state == BondState::persistence_pending;
            refreshOwnedBond();
            reportPassIfReady();
            break;
        case SecurityEvent::bond_persistence_pending:
            paired_peer = event.peer;
            paired_peer_ready = true;
            session_bonded = true;
            refreshOwnedBond();
            reportPassIfReady();
            break;
        case SecurityEvent::bond_verified:
            session_bonded = true;
            if (pairings == 0U && owned_bond && samePeer(event.peer, owned_peer))
            {
                reconnects = 1U;
            }
            reportPassIfReady();
            break;
        case SecurityEvent::security_changed:
            security_level = event.level >= SecurityLevel::encrypted ? 1U : 0U;
            if (pairings == 0U && owned_bond && samePeer(event.peer, owned_peer) &&
                BLESecurity.paired(event.connection) && bondSetMatches(true))
            {
                session_bonded = true;
                reconnects = 1U;
            }
            reportPassIfReady();
            break;
        case SecurityEvent::pairing_failed:
            if (strcmp(case_name, "access_denied") != 0)
            {
                fail("security_failed");
                break;
            }
            security_failure_seen = true;
            negative = 1U;
#if defined(COMPANION_PEER)
            companion_security_failure_seen = true;
            data_complete = true;
#endif
            reportPassIfReady();
            break;
        case SecurityEvent::pairing_cancelled:
        case SecurityEvent::timeout:
        case SecurityEvent::error:
            if (strcmp(case_name, "access_denied") != 0)
            {
                fail("security_error");
            }
            break;
        default:
            break;
        }
    }

    /** @brief link generation을 추적하고 종료 시 stale handle 사용을 거부합니다. */
    void gapEvent(const BLEEventInfo &event, void *)
    {
        if (event.event == BLEEvent::connecting || event.event == BLEEvent::connected ||
            event.event == BLEEvent::disconnected || event.event == BLEEvent::error)
        {
            Serial.print("M33ECO_GAP event=");
            Serial.print(static_cast<unsigned>(event.event));
            Serial.print(" reason=");
            Serial.print(event.reason);
            Serial.print(" error=");
            Serial.print(static_cast<unsigned>(BLEDevice.lastError()));
            Serial.print(" native=");
            Serial.println(BLEDevice.lastDriverError());
        }
        if (event.event == BLEEvent::connected)
        {
            if (!active || stopping)
            {
                (void)BLEConnection.disconnect(event.connection);
                return;
            }
            link = event.connection;
#if !defined(COMPANION_PEER)
            AppleClient::stopAdvertising();
            if (client.begin(link, selected) != CompanionError::none)
            {
                fail("begin");
            }
#endif
        }
#if defined(COMPANION_PEER)
        else if ((event.event == BLEEvent::disconnected || event.event == BLEEvent::error) &&
                 active && !stopping && !reported && !failed && !BLEConnection.connecting() &&
                 !BLEConnection.connected() && !BLEScan.running())
        {
            link = {};
            if (!BLEScan.startExtended(true, false, false))
            {
                fail("scan_restart");
            }
        }
#endif
    }

    /** @brief 고정 형식 명령만 수용하고 45초 lease 후 연결을 정리합니다. */
    void command(const char *input)
    {
        if (strcmp(input, "STATUS") == 0)
        {
            record("READY");
            return;
        }
        char verb[10], supplied[34], requested[17], extra;
        const int count = sscanf(input, "%9s %33s %16s %c", verb, supplied, requested, &extra);
        if (count == 2 && strcmp(verb, "CLEANUP") == 0)
        {
            cleanupOwnedBond(supplied);
            return;
        }
        if (count == 2 && strcmp(verb, "STOP") == 0 && strcmp(supplied, nonce) == 0)
        {
            stopping = true;
            client.end();
            AppleClient::stopAdvertising();
            (void)BLEScan.stop();
            if (BLEConnection.connected(link))
            {
                (void)BLEConnection.disconnect(link);
            }
            return;
        }
        if (count == 2 && strcmp(verb, "GO") == 0 && active && !stopping &&
            strcmp(supplied, nonce) == 0)
        {
#if defined(COMPANION_PEER)
            peer_released = true;
            next_send = k_uptime_get() + 100;
            record("GO_ACK");
#else
            record("REJECT");
#endif
            return;
        }
        if (count != 3 || strcmp(verb, "START") != 0 || strlen(supplied) != 32 || active ||
            !initialized || strcmp(supplied, "00000000000000000000000000000000") == 0)
        {
            record("REJECT");
            return;
        }
        for (size_t i = 0; i < 32; ++i)
        {
            if (!((supplied[i] >= '0' && supplied[i] <= '9') ||
                  (supplied[i] >= 'a' && supplied[i] <= 'f')))
            {
                record("REJECT");
                return;
            }
        }
        if (strcmp(requested, "ancs") != 0 && strcmp(requested, "ams") != 0 &&
            strcmp(requested, "ancs_bad") != 0 && strcmp(requested, "ams_bad") != 0 &&
            strcmp(requested, "access_denied") != 0)
        {
            record("REJECT");
            return;
        }
        if (!captureBaseline())
        {
            fail("bond_snapshot");
            return;
        }
        strcpy(nonce, supplied);
        strcpy(case_name, requested);
        snprintf(peer_name, sizeof(peer_name), "NU54-ECO-%.16s", nonce);
        char prefix[9];
        memcpy(prefix, nonce, 8);
        prefix[8] = 0;
        uid = static_cast<uint32_t>(strtoul(prefix, nullptr, 16));
        selected = strncmp(requested, "ams", 3) == 0 ? Service::media : Service::notifications;
        malformed = strstr(requested, "_bad") != nullptr;
        active = true;
        stopping = failed = reported = false;
        media_commands_sent = false;
        peer_released = false;
        security_failure_seen = false;
        companion_security_failure_seen = false;
        session_bonded = false;
        data_complete = false;
        paired_peer_ready = false;
        packets = attributes = writes = phase = negative = 0;
        security_level = pairings = reconnects = security_rejects = 0U;
        deadline = k_uptime_get() + 45000;
        next_send = k_uptime_get() + 500;
#if defined(COMPANION_PEER)
        if (!BLEScan.clearFilters() || !BLEScan.filterName(peer_name) ||
            !BLEScan.startExtended(true, false, false))
        {
            fail("scan");
        }
#else
        if (AppleClient::advertise(selected, peer_name) != CompanionError::none)
        {
            fail("advertise");
        }
#endif
        record("STARTED");
    }
} // namespace

/** @brief watchdog·역할별 GATT·callback을 구성하고 준비 상태를 출력합니다. */
void setup()
{
    Serial.begin(115200);
    const wdt_timeout_cfg watchdog_config = {
        .window = {.min = 0, .max = 5000}, .callback = nullptr, .flags = WDT_FLAG_RESET_SOC};
    if (!device_is_ready(watchdog) ||
        (watchdog_channel = wdt_install_timeout(watchdog, &watchdog_config)) < 0 ||
        wdt_setup(watchdog, WDT_OPT_PAUSE_HALTED_BY_DBG) != 0)
    {
        fail("watchdog");
        return;
    }
    BLEDevice.onEventInfo(gapEvent);
    BLESecurity.onEvent(securityEvent);
    SecurityConfig security_config;
    security_config.minimum_level = SecurityLevel::encrypted;
    security_config.bonding = true;
    security_config.response_timeout_ms = 10000U;
    security_config.io_capability = SecurityIoCapability::no_input_output;
    if (!BLESecurity.begin(security_config))
    {
        fail("security_stack");
        return;
    }
#if defined(COMPANION_PEER)
    cp.onEvent(characteristicEvent);
    rc.onEvent(characteristicEvent);
    eu.onEvent(characteristicEvent);
    ea.onEvent(characteristicEvent);
    if (!ancs.addCharacteristic(ns) || !ancs.addCharacteristic(ds) || !ancs.addCharacteristic(cp) ||
        !ams.addCharacteristic(rc) || !ams.addCharacteristic(eu) || !ams.addCharacteristic(ea) ||
        !BLEDevice.addService(ancs) || !BLEDevice.addService(ams))
    {
        fail("schema");
    }
    BLEScan.onResult(scanned);
#else
    client.onEvent(companionEvent);
#endif
    if (!BLEDevice.begin("NU54-ECO-IDLE"))
    {
        fail("stack");
    }
    initialized = !failed;
    record("READY");
}

/** @brief 유한 명령·GATT 데이터 경로·lease·종료 조건을 진행합니다. */
void loop()
{
    if (watchdog_channel >= 0)
    {
        (void)wdt_feed(watchdog, watchdog_channel);
    }
    BLEDevice.poll();
    BLESecurity.poll();
    client.poll();
    while (Serial.available() > 0)
    {
        const int value = Serial.read();
        if (value == '\n')
        {
            line[line_used] = 0;
            if (line_overflow)
            {
                record("REJECT");
            }
            else
            {
                command(line);
            }
            line_used = 0;
            line_overflow = false;
        }
        else if (value != '\r' && line_used < sizeof(line) - 1)
        {
            line[line_used++] = static_cast<char>(value);
        }
        else if (value != '\r')
        {
            line_overflow = true;
        }
    }
    if (active && !stopping && !failed)
    {
        refreshOwnedBond();
        reportPassIfReady();
#if defined(COMPANION_PEER)
        peerPoll();
#else
        CompanionError result = CompanionError::busy;
        if (phase == 2)
        {
            result = selected == Service::notifications ? client.performAction(latest, true)
                                                        : client.readMediaAttribute(2, 2);
            if (result == CompanionError::none)
            {
                phase = selected == Service::notifications ? 4 : 5;
            }
        }
        else if (phase == 3)
        {
            result = client.sendMediaCommand(2);
            if (result == CompanionError::none)
            {
                phase = 4;
            }
        }
        if (result != CompanionError::none && result != CompanionError::busy)
        {
            fail("command_send");
        }
#endif
        if (k_uptime_get() > deadline)
        {
            fail("lease_timeout");
            stopping = true;
        }
    }
    if (active && stopping && BLEConnection.count() == 0 && !BLEConnection.connecting())
    {
        record("STOPPED");
        active = false;
        stopping = false;
    }
    delay(2);
}
