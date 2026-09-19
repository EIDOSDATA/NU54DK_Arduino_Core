/**
 * @file CsipSetCoordinator.ino
 * @brief 같은 set의 bonded member 두 개를 찾아 rank 순서 확인과 잠금·해제를 수행합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE.h>
#include <NUCODE_BLE_Audio.h>
#include <NUCODE_BLE_Security.h>

namespace
{
    nucode::ble::audio::CsipSetCoordinator coordinator;
    nucode::ble::BLEAddress candidateAddress;
    nucode::ble::BLEConnectionHandle links[2] = {};
    std::size_t linkCount = 0U;
    std::size_t reportedMembers = 0U;
    bool candidateReady = false;

    constexpr nucode::ble::audio::CsipSetKey setKey = {{
        0x91U, 0x72U, 0x44U, 0x13U, 0xa8U, 0x5cU, 0x2dU, 0xe1U,
        0x0bU, 0x6fU, 0xc3U, 0x39U, 0x57U, 0x8aU, 0xd4U, 0x20U,
    }};

    /** @brief 실패 단계를 출력하고 불완전한 실행을 막습니다. */
    void require(bool condition, const char *stage)
    {
        if (condition)
        {
            return;
        }
        Serial.print("Set coordinator start failed: ");
        Serial.println(stage);
        while (true)
        {
            delay(1000U);
        }
    }

    /** @brief 이미 연결한 peer의 재선택을 막습니다. */
    bool connectedAddress(const nucode::ble::BLEAddress &address)
    {
        for (std::size_t index = 0U; index < linkCount; ++index)
        {
            if (BLEConnection.connected(links[index]) &&
                BLEConnection.peerAddress(links[index]) == address)
            {
                return true;
            }
        }
        return false;
    }

    /** @brief RSI가 set key와 일치하는 connectable 광고를 선택합니다. */
    void onScanResult(const nucode::ble::BLEScanResult &result, void *context)
    {
        static_cast<void>(context);
        if (!candidateReady && result.connectable && !result.scan_response &&
            !connectedAddress(result.address) && coordinator.matches(result))
        {
            candidateAddress = result.address;
            candidateReady = true;
            if (!BLEScan.stop())
            {
                Serial.println("Set coordinator scan stop failed");
            }
        }
    }

    /** @brief exact central handle마다 bonding을 시작하고 peer loss를 정리합니다. */
    void onBleEvent(const nucode::ble::BLEEventInfo &information, void *context)
    {
        static_cast<void>(context);
        if (information.event == nucode::ble::BLEEvent::connected &&
            information.role == nucode::ble::BLELinkRole::central)
        {
            if (linkCount < 2U)
            {
                links[linkCount++] = information.connection;
            }
            if (!BLESecurity.requestSecurity(information.connection))
            {
                Serial.println("Set coordinator security request failed");
            }
        }
        else if (information.event == nucode::ble::BLEEvent::disconnected)
        {
            coordinator.poll();
            for (std::size_t index = 0U; index < linkCount; ++index)
            {
                if (links[index] == information.connection)
                {
                    links[index] = links[linkCount - 1U];
                    links[--linkCount] = {};
                    break;
                }
            }
            reportedMembers = coordinator.memberCount();
        }
    }

    /** @brief bonding 완료 뒤 해당 exact link의 CSIS를 검색합니다. */
    void onSecurityEvent(const nucode::ble::SecurityEventRecord &record, void *context)
    {
        static_cast<void>(context);
        if (record.event == nucode::ble::SecurityEvent::pairing_requested)
        {
            if (!BLESecurity.acceptPairing(record.connection, true))
            {
                Serial.println("Set coordinator pairing approval failed");
            }
        }
        else if (record.event == nucode::ble::SecurityEvent::paired ||
                 record.event == nucode::ble::SecurityEvent::bond_verified)
        {
            if (coordinator.discover(record.connection) != nucode::ble::audio::Error::none)
            {
                Serial.println("Set member discovery failed to start");
            }
        }
    }

    /** @brief 발견된 set의 size·rank·lockable 값을 출력합니다. */
    void printMembers()
    {
        for (std::size_t index = 0U; index < coordinator.memberCount(); ++index)
        {
            nucode::ble::audio::CsipMemberInfo member{};
            if (coordinator.member(index, member) == nucode::ble::audio::Error::none)
            {
                Serial.print("Member rank ");
                Serial.print(member.rank);
                Serial.print(" of ");
                Serial.println(member.set_size);
            }
        }
    }
} // namespace

void setup()
{
    Serial.begin(115200);

    nucode::ble::SecurityConfig security{};
    security.minimum_level = nucode::ble::SecurityLevel::encrypted;
    security.bonding = true;
    security.io_capability = nucode::ble::SecurityIoCapability::no_input_output;
    BLESecurity.onEvent(onSecurityEvent);
    BLEDevice.onEventInfo(onBleEvent);
    BLEScan.onResult(onScanResult);

    require(BLESecurity.begin(security), "security");
    require(BLEDevice.begin("NU54-SET-CONTROL"), "device");
    require(coordinator.begin(setKey, 2U) == nucode::ble::audio::Error::none, "coordinator");
    require(BLEScan.clearFilters(), "scan-clear");
    require(BLEScan.start(true), "scan-start");
    Serial.println("Searching for two set members");
}

void loop()
{
    BLEDevice.poll();
    BLESecurity.poll();
    coordinator.poll();

    if (candidateReady && !BLEConnection.connecting())
    {
        candidateReady = false;
        nucode::ble::BLEConnectionHandle connection;
        if (!BLEConnection.connect(candidateAddress, connection))
        {
            Serial.println("Set member connection failed");
            require(BLEScan.start(true), "scan-restart");
        }
    }
    if (coordinator.memberCount() != reportedMembers)
    {
        reportedMembers = coordinator.memberCount();
        printMembers();
        if (!coordinator.ready() && !BLEScan.running() && !BLEConnection.connecting())
        {
            require(BLEScan.start(true), "next-member-scan");
        }
        else if (coordinator.ready())
        {
            Serial.println("Set ready; send o to order, l to lock, u to release");
        }
    }
    if (!coordinator.ready() && !candidateReady && !BLEScan.running() &&
        !BLEConnection.connecting() && coordinator.stage() != nucode::ble::audio::CsipStage::operating)
    {
        require(BLEScan.start(true), "recovery-scan");
    }

    if (Serial.available() != 0)
    {
        const int command = Serial.read();
        nucode::ble::audio::Error result = nucode::ble::audio::Error::none;
        if (command == 'o')
        {
            result = coordinator.prepareOrderedAccess();
        }
        else if (command == 'l')
        {
            result = coordinator.lock();
        }
        else if (command == 'u')
        {
            result = coordinator.release();
        }
        if ((command == 'o' || command == 'l' || command == 'u') &&
            result != nucode::ble::audio::Error::none)
        {
            Serial.println("Set operation rejected");
        }
    }
    delay(1U);
}
