/**
 * @file main.cpp
 * @brief M32 최신 연결 timing·feature 공개 API의 target link 계약입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE_GAP.h>

#include <cstdint>

static_assert(CONFIG_BT_MAX_CONN == 2);
static_assert(CONFIG_BT_SUBRATING == 1);
static_assert(CONFIG_BT_SCA_UPDATE == 1);
static_assert(CONFIG_BT_LE_EXTENDED_FEAT_SET == 1);
static_assert(CONFIG_BT_FRAME_SPACE_UPDATE == 1);
static_assert(CONFIG_BT_SHORTER_CONNECTION_INTERVALS == 1);

int main()
{
    nucode::ble::BLEConnectionHandle connection;
    nucode::ble::BLESubrateParameters subrate_parameters;
    nucode::ble::BLESubrateInfo subrate_information;
    nucode::ble::BLEConnectionRateParameters rate_parameters;
    nucode::ble::BLEConnectionRateInfo rate_information;
    nucode::ble::BLEFrameSpaceParameters frame_parameters;
    nucode::ble::BLEFrameSpaceInfo frame_information;
    nucode::ble::BLEExtendedFeatureSet local_features;
    nucode::ble::BLEExtendedFeatureSet remote_features;
    std::uint16_t minimum_interval_us = 0U;
    const std::uint8_t channel_map[5] = {0xffU, 0xffU, 0xffU, 0xffU, 0x1fU};

    static_cast<void>(BLEConnection.setDefaultSubrate(subrate_parameters));
    static_cast<void>(BLEConnection.requestSubrate(connection, subrate_parameters));
    static_cast<void>(BLEConnection.subrate(connection, subrate_information));
    static_cast<void>(BLEConnection.setDefaultConnectionRate(rate_parameters));
    static_cast<void>(BLEConnection.requestConnectionRate(connection, rate_parameters));
    static_cast<void>(BLEConnection.connectionRate(connection, rate_information));
    static_cast<void>(BLEConnection.minimumConnectionInterval(minimum_interval_us));
    static_cast<void>(BLEConnection.requestFrameSpace(connection, frame_parameters));
    static_cast<void>(BLEConnection.frameSpace(connection, frame_information));
    static_cast<void>(BLEConnection.localExtendedFeatures(local_features));
    static_cast<void>(BLEConnection.requestRemoteExtendedFeatures(connection));
    static_cast<void>(BLEConnection.remoteExtendedFeatures(connection, remote_features));
    static_cast<void>(BLEConnection.sleepClockAccuracySupport());
    static_cast<void>(BLEConnection.setChannelClassification(channel_map));
    return 0;
}
