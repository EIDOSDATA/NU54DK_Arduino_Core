/**
 * @file NUCODE_BLE_Audio_CapAcceptor.cpp
 * @brief CAP Acceptor 공개 API를 구현합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include "NUCODE_BLE_Audio.h"

#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE) && defined(CONFIG_BT_CAP_ACCEPTOR) && \
    !defined(CONFIG_BT_CAP_ACCEPTOR_SET_MEMBER)

#include <NUCODE_BLE.h>

namespace nucode::ble::audio
{
    /** @brief 정적 CAS와 Bluetooth 준비 상태를 공개 객체에 결합합니다. */
    Error CapAcceptor::begin() noexcept
    {
        if (started_)
        {
            return record(Error::already_started);
        }
        if (!BLEDevice.initialized())
        {
            return record(Error::not_ready);
        }

        started_ = true;
        stage_ = CapStage::ready;
        return record(Error::none);
    }

    /** @brief 공개 Acceptor 객체의 수명을 종료합니다. */
    Error CapAcceptor::end() noexcept
    {
        if (!started_)
        {
            return record(Error::not_started);
        }
        started_ = false;
        stage_ = CapStage::idle;
        return record(Error::none);
    }

    /** @brief 정적 CAS가 활성 image에서 준비되었는지 반환합니다. */
    bool CapAcceptor::ready() const noexcept
    {
        return started_ && (stage_ == CapStage::ready);
    }

    /** @brief 현재 CAP Acceptor 단계를 반환합니다. */
    CapStage CapAcceptor::stage() const noexcept
    {
        return stage_;
    }

    /** @brief 마지막 공개 오류를 반환합니다. */
    Error CapAcceptor::lastError() const noexcept
    {
        return last_error_;
    }

    /** @brief 마지막 Host 오류를 반환합니다. */
    int CapAcceptor::nativeCode() const noexcept
    {
        return native_code_;
    }

    /** @brief 마지막 공개 오류와 원본 Host 오류를 기록합니다. */
    Error CapAcceptor::record(Error error, int native_code) noexcept
    {
        last_error_ = error;
        native_code_ = native_code;
        return error;
    }
} // namespace nucode::ble::audio

#else

namespace nucode::ble::audio
{
    Error CapAcceptor::begin() noexcept
    {
        stage_ = CapStage::failed;
        return record(Error::not_ready);
    }

    Error CapAcceptor::end() noexcept
    {
        return record(Error::not_started);
    }

    bool CapAcceptor::ready() const noexcept
    {
        return false;
    }

    CapStage CapAcceptor::stage() const noexcept
    {
        return stage_;
    }

    Error CapAcceptor::lastError() const noexcept
    {
        return last_error_;
    }

    int CapAcceptor::nativeCode() const noexcept
    {
        return native_code_;
    }

    Error CapAcceptor::record(Error error, int native_code) noexcept
    {
        last_error_ = error;
        native_code_ = native_code;
        return error;
    }
} // namespace nucode::ble::audio

#endif
