/**
 * @file m31_audio_control_lifecycle_main.cpp
 * @brief 실제 Audio Control controller 구현의 read와 수명 경쟁을 실행 검증합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <cassert>
#include <cstdint>

#include "../../libraries/NUCODE_BLE_Audio/src/NUCODE_BLE_Audio_ControlController.cpp"

namespace
{
    using nucode::ble::BLEConnectionHandle;
    using nucode::ble::audio::AudioControlStage;
    using nucode::ble::audio::AudioInputMode;
    using nucode::ble::audio::Error;
    using nucode::ble::audio::MicrophoneController;
    using nucode::ble::audio::VolumeController;

    /** @brief VCP bootstrap의 현재 read에 wire payload를 전달하고 다음 단계를 시작합니다. */
    void completeVolumeStep(VolumeController &controller, const void *data,
                            std::uint16_t length) noexcept
    {
        assert(audio_control_stub::pending_read != nullptr);
        audio_control_stub::completeRead(data, length);
        controller.poll();
    }

    /** @brief MICP bootstrap의 현재 read에 wire payload를 전달하고 다음 단계를 시작합니다. */
    void completeMicrophoneStep(MicrophoneController &controller, const void *data,
                                std::uint16_t length) noexcept
    {
        assert(audio_control_stub::pending_read != nullptr);
        audio_control_stub::completeRead(data, length);
        controller.poll();
    }

    /** @brief 실제 VCP/VOCS/AICS bootstrap과 native cache 반영을 검사합니다. */
    void bootstrapVolume(VolumeController &controller,
                         const BLEConnectionHandle &handle) noexcept
    {
        assert(controller.begin(handle) == Error::none);
        assert(audio_control_stub::volume_callbacks != nullptr);
        audio_control_stub::volume_callbacks->discover(&audio_control_stub::volume_controller, 0,
                                                       1U, 1U);

        const vcs_state volume = {32U, BT_VCP_STATE_MUTED, 7U};
        completeVolumeStep(controller, &volume, sizeof(volume));
        const std::uint8_t flags = 3U;
        completeVolumeStep(controller, &flags, sizeof(flags));
        const std::uint8_t offset[] = {0x34U, 0xffU, 9U};
        completeVolumeStep(controller, offset, sizeof(offset));
        const std::uint8_t location[] = {0x78U, 0x56U, 0x34U, 0x12U};
        completeVolumeStep(controller, location, sizeof(location));
        const bt_aics_state input = {-4, BT_AICS_STATE_MUTED, 3U, 11U};
        completeVolumeStep(controller, &input, sizeof(input));
        const std::uint8_t active = BT_AICS_STATUS_ACTIVE;
        completeVolumeStep(controller, &active, sizeof(active));
        const bt_aics_gain_settings gain = {2U, -20, 20};
        completeVolumeStep(controller, &gain, sizeof(gain));
        const std::uint8_t type = 6U;
        completeVolumeStep(controller, &type, sizeof(type));

        assert(controller.ready());
        assert(controller.state().volume == 32U);
        assert(controller.state().muted);
        assert(controller.state().flags == flags);
        assert(controller.offsetState().offset == static_cast<std::int16_t>(-204));
        assert(controller.offsetState().location == 0x12345678U);
        assert(audio_control_stub::volume_controller.state.change_counter == 7U);
        assert(audio_control_stub::volume_controller.vol_flags == flags);
        assert(audio_control_stub::volume_offset.state.change_counter == 9U);
        assert(audio_control_stub::volume_offset.location == 0x12345678U);
        assert(audio_control_stub::volume_input.cli.change_counter == 11U);
    }

    /** @brief notification이 read 응답보다 앞서면 낡은 raw 상태를 버리는지 검사합니다. */
    void volumeNotificationBeforeResponse(VolumeController &controller) noexcept
    {
        assert(controller.readVolume() == Error::none);
        assert(audio_control_stub::pending_read != nullptr);

        audio_control_stub::volume_controller.state = {99U, 0U, 22U};
        audio_control_stub::volume_callbacks->state(&audio_control_stub::volume_controller, 0,
                                                    99U, 0U);
        const vcs_state stale = {12U, BT_VCP_STATE_MUTED, 3U};
        audio_control_stub::completeRead(&stale, sizeof(stale));

        assert(controller.ready());
        assert(controller.state().volume == 99U);
        assert(!controller.state().muted);
        assert(audio_control_stub::volume_controller.state.volume == 99U);
        assert(audio_control_stub::volume_controller.state.change_counter == 22U);
    }

    /** @brief 공개 VOCS/AICS read가 LE 값과 native change counter를 함께 갱신하는지 검사합니다. */
    void volumeDirectReads(VolumeController &controller) noexcept
    {
        assert(controller.readOffset() == Error::none);
        const std::uint8_t offset[] = {0x7fU, 0x00U, 31U};
        audio_control_stub::completeRead(offset, sizeof(offset));
        assert(controller.ready());
        assert(controller.offsetState().offset == 127);
        assert(audio_control_stub::volume_offset.state.offset == 127);
        assert(audio_control_stub::volume_offset.state.change_counter == 31U);

        assert(controller.readInput() == Error::none);
        const bt_aics_state input = {8, 0U, 3U, 41U};
        audio_control_stub::completeRead(&input, sizeof(input));
        assert(controller.ready());
        assert(controller.inputState().gain == 8);
        assert(controller.inputState().mode == AudioInputMode::automatic);
        assert(audio_control_stub::volume_input.cli.change_counter == 41U);
    }

    /** @brief 다른 characteristic notification이 현재 raw read 응답을 억제하지 않는지 검사합니다. */
    void volumeCharacteristicIsolation(VolumeController &controller) noexcept
    {
        assert(controller.readOffset() == Error::none);
        audio_control_stub::volume_controller.state = {88U, 0U, 52U};
        audio_control_stub::volume_callbacks->state(&audio_control_stub::volume_controller, 0,
                                                    88U, 0U);
        const std::uint8_t offset[] = {0x2aU, 0x00U, 53U};
        audio_control_stub::completeRead(offset, sizeof(offset));
        assert(controller.ready());
        assert(controller.offsetState().offset == 42);
        assert(audio_control_stub::volume_offset.state.change_counter == 53U);
    }

    /** @brief 실제 MICP/AICS bootstrap과 public read의 cache 일관성을 검사합니다. */
    void microphoneReads(MicrophoneController &controller,
                         const BLEConnectionHandle &handle) noexcept
    {
        assert(controller.begin(handle) == Error::none);
        assert(audio_control_stub::microphone_callbacks != nullptr);
        audio_control_stub::microphone_callbacks->discover(
            &audio_control_stub::microphone_controller, 0, 1U);

        const std::uint8_t microphone_mute = BT_MICP_MUTE_MUTED;
        completeMicrophoneStep(controller, &microphone_mute, sizeof(microphone_mute));
        const bt_aics_state input = {-3, 0U, 3U, 51U};
        completeMicrophoneStep(controller, &input, sizeof(input));
        const std::uint8_t active = BT_AICS_STATUS_ACTIVE;
        completeMicrophoneStep(controller, &active, sizeof(active));
        const bt_aics_gain_settings gain = {4U, -30, 30};
        completeMicrophoneStep(controller, &gain, sizeof(gain));
        const std::uint8_t type = 2U;
        completeMicrophoneStep(controller, &type, sizeof(type));

        assert(controller.ready());
        assert(controller.state().muted);
        assert(controller.inputState().gain == -3);
        assert(audio_control_stub::microphone_input.cli.change_counter == 51U);

        assert(controller.readMicrophone() == Error::none);
        const std::uint8_t unmuted = 0U;
        audio_control_stub::completeRead(&unmuted, sizeof(unmuted));
        assert(controller.ready());
        assert(!controller.state().muted);

        assert(controller.readInput() == Error::none);
        audio_control_stub::microphone_input.cli.change_counter = 73U;
        audio_control_stub::microphone_callbacks->aics_cb.state(
            &audio_control_stub::microphone_input, 0, 17, 0U, 2U);
        const bt_aics_state stale = {-9, BT_AICS_STATE_MUTED, 3U, 6U};
        audio_control_stub::completeRead(&stale, sizeof(stale));
        assert(controller.ready());
        assert(controller.inputState().gain == 17);
        assert(!controller.inputState().muted);
        assert(controller.inputState().mode == AudioInputMode::manual);
        assert(audio_control_stub::microphone_input.cli.change_counter == 73U);

        assert(controller.readInput() == Error::none);
        audio_control_stub::microphone_callbacks->mute(
            &audio_control_stub::microphone_controller, 0, BT_MICP_MUTE_MUTED);
        const bt_aics_state isolated = {6, 0U, 3U, 74U};
        audio_control_stub::completeRead(&isolated, sizeof(isolated));
        assert(controller.ready());
        assert(controller.inputState().gain == 6);
        assert(audio_control_stub::microphone_input.cli.change_counter == 74U);
    }

    /** @brief callback snapshot이 살아 있는 동안 end 뒤 재소유를 막는지 검사합니다. */
    void callbackInflightEnd(const BLEConnectionHandle &handle) noexcept
    {
        VolumeController controller;
        VolumeController replacement;
        assert(controller.begin(handle) == Error::none);
        {
            const auto callback = nucode::ble::audio::currentVolumeController(
                &audio_control_stub::volume_controller);
            assert(callback.generation != 0U);
            assert(controller.end() == Error::none);
            assert(replacement.begin(handle) == Error::busy);
        }
        assert(replacement.begin(handle) == Error::busy);
        audio_control_stub::connection.active = false;
        audio_control_stub::volume_controller.conn = nullptr;
        audio_control_stub::volume_input.cli.conn = nullptr;
        assert(replacement.begin(handle) == Error::not_connected);
        audio_control_stub::connection.active = true;
        audio_control_stub::volume_controller.conn = &audio_control_stub::connection;
        audio_control_stub::volume_input.cli.conn = &audio_control_stub::connection;
    }

    /** @brief cancel lookup 뒤 늦은 old callback이 새 generation을 소비하지 않는지 검사합니다. */
    void cancelNoFindLateCallback(const BLEConnectionHandle &handle) noexcept
    {
        VolumeController controller;
        VolumeController replacement;
        assert(controller.begin(handle) == Error::none);
        audio_control_stub::volume_callbacks->discover(&audio_control_stub::volume_controller, 0,
                                                       1U, 1U);
        assert(audio_control_stub::pending_read != nullptr);
        audio_control_stub::detachReadForLateCallback();
        assert(controller.end() == Error::none);
        assert(replacement.begin(handle) == Error::busy);
        audio_control_stub::completeLateRead();
        assert(replacement.begin(handle) == Error::busy);

        audio_control_stub::connection.active = false;
        audio_control_stub::volume_controller.conn = nullptr;
        audio_control_stub::volume_input.cli.conn = nullptr;
        assert(audio_control_stub::volume_offset.conn == &audio_control_stub::connection);
        assert(replacement.begin(handle) == Error::not_connected);

        audio_control_stub::connection.active = true;
        audio_control_stub::volume_controller.conn = &audio_control_stub::connection;
        audio_control_stub::volume_input.cli.conn = &audio_control_stub::connection;
    }

    /** @brief poll이 먼저 disconnect를 봐도 sticky VOCS barrier를 우회하지 않는지 검사합니다. */
    void pollBeforeEndStickyVocs(const BLEConnectionHandle &handle) noexcept
    {
        VolumeController controller;
        VolumeController replacement;
        assert(controller.begin(handle) == Error::none);
        audio_control_stub::volume_callbacks->discover(&audio_control_stub::volume_controller, 0,
                                                       1U, 1U);
        audio_control_stub::connection.active = false;
        controller.poll();
        assert(controller.stage() == AudioControlStage::disconnected);
        assert(controller.end() == Error::none);

        audio_control_stub::volume_controller.conn = nullptr;
        audio_control_stub::volume_input.cli.conn = nullptr;
        assert(audio_control_stub::volume_offset.conn == &audio_control_stub::connection);
        assert(replacement.begin(handle) == Error::not_connected);

        audio_control_stub::connection.active = true;
        audio_control_stub::volume_controller.conn = &audio_control_stub::connection;
        audio_control_stub::volume_input.cli.conn = &audio_control_stub::connection;
    }

    /** @brief synchronous cancel, timeout, retired barrier와 end/rebegin을 검사합니다. */
    void timeoutEndRebegin(const BLEConnectionHandle &handle) noexcept
    {
        const std::uint32_t cancel_callbacks = audio_control_stub::cancel_callbacks;
        VolumeController controller;
        assert(controller.begin(handle) == Error::none);
        audio_control_stub::volume_callbacks->discover(&audio_control_stub::volume_controller, 0,
                                                       1U, 1U);
        assert(audio_control_stub::pending_read != nullptr);

        audio_control_stub::uptime_ms = 5001U;
        controller.poll();
        assert(controller.stage() == AudioControlStage::failed);
        assert(audio_control_stub::pending_read == nullptr);
        assert(audio_control_stub::cancel_callbacks == cancel_callbacks + 1U);
        assert(controller.end() == Error::none);

        VolumeController replacement;
        assert(replacement.begin(handle) == Error::busy);
        audio_control_stub::connection.active = false;
        audio_control_stub::volume_controller.conn = nullptr;
        audio_control_stub::volume_input.cli.conn = nullptr;
        assert(replacement.begin(handle) == Error::not_connected);

        audio_control_stub::connection.active = true;
        audio_control_stub::volume_controller.conn = &audio_control_stub::connection;
        audio_control_stub::volume_offset.conn = &audio_control_stub::connection;
        audio_control_stub::volume_input.cli.conn = &audio_control_stub::connection;
        assert(replacement.begin(handle) == Error::none);
        assert(replacement.end() == Error::none);
    }
} // namespace

int main()
{
    audio_control_stub::reset();
    const BLEConnectionHandle handle(1U);

    VolumeController volume;
    bootstrapVolume(volume, handle);
    volumeNotificationBeforeResponse(volume);
    volumeDirectReads(volume);
    volumeCharacteristicIsolation(volume);
    assert(volume.end() == Error::none);

    MicrophoneController microphone;
    microphoneReads(microphone, handle);
    assert(microphone.end() == Error::none);

    audio_control_stub::connection.active = false;
    audio_control_stub::volume_controller.conn = nullptr;
    audio_control_stub::volume_input.cli.conn = nullptr;
    audio_control_stub::microphone_controller.conn = nullptr;
    audio_control_stub::microphone_input.cli.conn = nullptr;
    VolumeController volume_barrier;
    MicrophoneController microphone_barrier;
    assert(volume_barrier.begin(handle) == Error::not_connected);
    assert(microphone_barrier.begin(handle) == Error::not_connected);

    audio_control_stub::connection.active = true;
    audio_control_stub::volume_controller.conn = &audio_control_stub::connection;
    audio_control_stub::volume_offset.conn = &audio_control_stub::connection;
    audio_control_stub::volume_input.cli.conn = &audio_control_stub::connection;
    audio_control_stub::microphone_controller.conn = &audio_control_stub::connection;
    audio_control_stub::microphone_input.cli.conn = &audio_control_stub::connection;
    callbackInflightEnd(handle);
    cancelNoFindLateCallback(handle);
    pollBeforeEndStickyVocs(handle);
    timeoutEndRebegin(handle);
    return 0;
}
