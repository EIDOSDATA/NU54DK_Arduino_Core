/**
 * @file MediaControlClient.ino
 * @brief 원격 media player의 track과 재생 상태를 제어하는 예제입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE.h>
#include <NUCODE_BLE_Audio.h>
#include <NUCODE_BLE_Security.h>

using nucode::ble::BLEAddress;
using nucode::ble::BLEConnectionHandle;
using nucode::ble::BLEEvent;
using nucode::ble::BLEEventInfo;
using nucode::ble::BLELinkRole;
using nucode::ble::BLEScanResult;
using nucode::ble::BLEUuid;
using nucode::ble::SecurityConfig;
using nucode::ble::SecurityEvent;
using nucode::ble::SecurityEventRecord;
using nucode::ble::SecurityIoCapability;
using nucode::ble::SecurityLevel;
using nucode::ble::audio::Error;
using nucode::ble::audio::MediaCommand;
using nucode::ble::audio::MediaControlClient;

namespace
{
    MediaControlClient controller;
    BLEAddress peerAddress;
    BLEConnectionHandle peerConnection;
    bool peerFound = false;
    bool controllerStarted = false;
    bool scanPending = false;
    std::uint32_t scanAt = 0U;
    const char *pendingOperation = nullptr;
    bool pendingNegative = false;
    std::uint32_t normalOperations = 0U;

    /** @brief Media Control Service를 광고하는 player를 검색합니다. */
    bool startScan()
    {
        return BLEScan.clearFilters() && BLEScan.filterServiceUuid(BLEUuid(0x1848U)) &&
               BLEScan.start(true);
    }

    /** @brief 처음 발견한 connectable player를 선택합니다. */
    void onScanResult(const BLEScanResult &result, void *context)
    {
        static_cast<void>(context);
        if (!peerFound && result.connectable)
        {
            peerAddress = result.address;
            peerFound = true;
            static_cast<void>(BLEScan.stop());
        }
    }

    /** @brief 암호화 완료 뒤 MCS discovery를 시작합니다. */
    void onSecurityEvent(const SecurityEventRecord &event, void *context)
    {
        static_cast<void>(context);
        if (event.event == SecurityEvent::pairing_requested)
        {
            static_cast<void>(BLESecurity.acceptPairing(event.connection, true));
        }
        else if (((event.event == SecurityEvent::paired) ||
                  (event.event == SecurityEvent::bond_verified) ||
                  (event.event == SecurityEvent::security_changed)) &&
                 (event.connection == peerConnection) && !controllerStarted)
        {
            const Error result = controller.begin(peerConnection);
            controllerStarted = result == Error::none;
            Serial.print("Media discovery result=");
            Serial.println(static_cast<unsigned int>(result));
        }
    }

    /** @brief 연결 수명에 controller와 재검색을 결합합니다. */
    void onBleEvent(const BLEEventInfo &event, void *context)
    {
        static_cast<void>(context);
        if ((event.event == BLEEvent::connected) && (event.role == BLELinkRole::central))
        {
            peerConnection = event.connection;
            if (!BLESecurity.requestSecurity(peerConnection))
            {
                Serial.println("Media security request failed");
            }
        }
        else if ((event.event == BLEEvent::disconnected) && (event.connection == peerConnection))
        {
            if (controllerStarted)
            {
                static_cast<void>(controller.end());
            }
            controllerStarted = false;
            peerFound = false;
            peerConnection = BLEConnectionHandle();
            scanPending = true;
            scanAt = millis() + 100U;
        }
    }

    /** @brief 원격 track/index/state snapshot을 출력합니다. */
    void printState()
    {
        const auto state = controller.snapshot();
        Serial.print("player=");
        Serial.print(state.player_name);
        Serial.print(" track=");
        Serial.print(state.track_title);
        Serial.print(" id=");
        Serial.print(static_cast<unsigned long>(state.current_track_id));
        Serial.print(" position=");
        Serial.print(state.track_position);
        Serial.print(" duration=");
        Serial.print(state.track_duration);
        Serial.print(" opcodes=");
        Serial.print(state.supported_commands);
        Serial.print(" state=");
        Serial.print(static_cast<unsigned int>(state.state));
        Serial.print(" updates=");
        Serial.print(state.updates);
        Serial.print(" notifications=");
        Serial.println(state.state_notifications);
    }

    /** @brief 공개 command 결과와 원본 MCC 오류를 출력합니다. */
    void report(const char *name, Error result)
    {
        Serial.print(name);
        Serial.print(" result=");
        Serial.print(static_cast<unsigned int>(result));
        Serial.print(" native=");
        Serial.println(controller.nativeCode());
    }

    /** @brief 비동기 명령 제출 상태를 자동 검증 가능한 형식으로 기록합니다. */
    void submitOperation(const char *name, Error result, bool negative)
    {
        if (result == Error::none)
        {
            pendingOperation = name;
            pendingNegative = negative;
            Serial.print(name);
            Serial.println(" submitted=1");
            return;
        }
        Serial.print(name);
        Serial.print(negative ? " rejected=1" : " complete=0");
        Serial.print(" result=");
        Serial.print(static_cast<unsigned int>(result));
        Serial.print(" native=");
        Serial.println(controller.nativeCode());
        if (negative)
        {
            report("MEDIA_RECOVERY", controller.refresh());
        }
    }

    /** @brief 원격 완료·거부 결과를 출력하고 negative 뒤 snapshot 읽기를 복구합니다. */
    void observeOperation()
    {
        if (pendingOperation == nullptr)
        {
            return;
        }
        const auto currentStage = controller.stage();
        if (currentStage == nucode::ble::audio::RemoteControlStage::failed)
        {
            Serial.print(pendingOperation);
            Serial.print(" rejected=1 result=");
            Serial.print(static_cast<unsigned int>(controller.lastError()));
            Serial.print(" native=");
            Serial.println(controller.nativeCode());
            pendingOperation = nullptr;
            pendingNegative = false;
            report("MEDIA_RECOVERY", controller.refresh());
        }
        else if (currentStage == nucode::ble::audio::RemoteControlStage::ready)
        {
            Serial.print(pendingOperation);
            if (pendingNegative)
            {
                Serial.print(" rejected=0");
            }
            else
            {
                ++normalOperations;
                Serial.print(" complete=1 normal_ops=");
                Serial.print(normalOperations);
            }
            Serial.println();
            pendingOperation = nullptr;
            pendingNegative = false;
        }
    }
} // namespace

/** @brief central·security·MCS 검색을 준비합니다. */
void setup()
{
    Serial.begin(115200);
    SecurityConfig security;
    security.minimum_level = SecurityLevel::encrypted;
    security.bonding = false;
    security.io_capability = SecurityIoCapability::no_input_output;
    BLEScan.onResult(onScanResult);
    BLEDevice.onEventInfo(onBleEvent);
    BLESecurity.onEvent(onSecurityEvent);
    if (!BLESecurity.begin(security) || !BLEDevice.begin("NU54-MEDIA-REMOTE") || !startScan())
    {
        Serial.println("Media controller start failed");
    }
    Serial.println("Commands: p=play u=pause x=stop n=next b=previous +=seek i=select k=bad-opcode "
                   "z=stale-object s=state r=refresh");
}

/** @brief MCS discovery와 사용자 media command를 비차단 처리합니다. */
void loop()
{
    BLEDevice.poll();
    BLESecurity.poll();
    controller.poll();
    observeOperation();
    if (scanPending && !BLEConnection.connected() && !BLEConnection.connecting() &&
        (static_cast<std::int32_t>(millis() - scanAt) >= 0))
    {
        if (startScan())
        {
            scanPending = false;
        }
        else
        {
            scanAt = millis() + 1000U;
        }
    }
    if (peerFound && !BLEConnection.connected() && !BLEConnection.connecting())
    {
        peerFound = false;
        if (!BLEConnection.connect(peerAddress, peerConnection))
        {
            scanPending = true;
            scanAt = millis() + 1000U;
        }
    }
    while (Serial.available() > 0)
    {
        const char command = static_cast<char>(Serial.read());
        if (command == 'p')
        {
            submitOperation("MEDIA_PLAY", controller.command(MediaCommand::play), false);
        }
        else if (command == 'u')
        {
            submitOperation("MEDIA_PAUSE", controller.command(MediaCommand::pause), false);
        }
        else if (command == 'x')
        {
            submitOperation("MEDIA_STOP", controller.command(MediaCommand::stop), false);
        }
        else if (command == 'n')
        {
            submitOperation("MEDIA_NEXT", controller.command(MediaCommand::next_track), false);
        }
        else if (command == 'b')
        {
            submitOperation("MEDIA_PREVIOUS", controller.command(MediaCommand::previous_track),
                            false);
        }
        else if (command == '+')
        {
            submitOperation("MEDIA_SEEK", controller.moveRelative(500), false);
        }
        else if (command == 'i')
        {
            const std::uint64_t identifier = controller.snapshot().current_track_id;
            submitOperation("MEDIA_SELECT", controller.selectTrack(identifier), false);
        }
        else if (command == 'k')
        {
            submitOperation("MEDIA_NEG_OPCODE", controller.commandOpcode(0x7fU), true);
        }
        else if (command == 'z')
        {
            submitOperation("MEDIA_NEG_STALE_OBJECT", controller.selectTrack(0x00ffffffULL), true);
        }
        else if (command == 'r')
        {
            submitOperation("MEDIA_REFRESH", controller.refresh(), false);
        }
        else if (command == 's')
        {
            printState();
        }
    }
    static std::uint32_t updates = 0U;
    if (controller.ready() && (updates != controller.snapshot().updates))
    {
        updates = controller.snapshot().updates;
        printState();
    }
    delay(1U);
}
