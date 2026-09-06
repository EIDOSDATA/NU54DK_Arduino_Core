/**
 * @file fixture_gate.h
 * @brief 외부 결선 시험의 고정 핀 묶음과 만료되는 실행 허가입니다.
 * SPDX-License-Identifier: MIT
 */
#pragma once
#include <cstdint>

namespace v04
{
    /** @brief 외부 결선에서 실행할 프로토콜 계열입니다. */
    enum class FixtureFamily : std::uint32_t
    {
        invalid = 0,
        uarte,
        spi,
        twi,
        analog,
        qdec,
        i2s,
        pdm
    };

    /** @brief 결선 ID를 프로토콜 계열로 변환합니다. */
    constexpr FixtureFamily fixtureFamily(std::uint32_t fixture)
    {
        if (fixture >= 101 && fixture <= 103)
        {
            return FixtureFamily::uarte;
        }
        if (fixture >= 201 && fixture <= 203)
        {
            return FixtureFamily::spi;
        }
        if (fixture == 301)
        {
            return FixtureFamily::twi;
        }
        if ((fixture >= 401 && fixture <= 407) || fixture == 408)
        {
            return FixtureFamily::analog;
        }
        switch (fixture)
        {
        case 420:
            return FixtureFamily::qdec;
        case 430:
            return FixtureFamily::i2s;
        case 440:
            return FixtureFamily::pdm;
        default:
            return FixtureFamily::invalid;
        }
    }

    /** @brief GPIO 포트 번호이며 커넥터 이름 P2/P4와 구별합니다. */
    enum class Bank : std::uint32_t
    {
        p0 = 0,
        p1 = 1,
        p2 = 2,
        invalid = 255
    };

    /** @brief 펌웨어가 허용하는 통신 결선만 선택합니다. */
    constexpr Bank fixtureBank(std::uint32_t fixture, std::uint32_t role)
    {
        if (role != 1 && role != 2)
        {
            return Bank::invalid;
        }
        switch (fixture)
        {
        case 101:
        case 201:
            return role == 1 ? Bank::p2 : Bank::p1;
        case 102:
        case 202:
            return role == 1 ? Bank::p0 : Bank::p1;
        case 103:
        case 203:
            return Bank::p1;
        case 301:
            return role == 1 ? Bank::p1 : Bank::p0;
        case 401:
        case 402:
        case 403:
        case 404:
        case 405:
        case 406:
        case 407:
        case 408:
        case 420:
        case 430:
        case 440:
            return Bank::p1;
        default:
            return Bank::invalid;
        }
    }

    /** @brief 핀 묶음별 지원 인스턴스를 검사하며 핀을 설정하지 않습니다. */
    constexpr bool fixtureInstance(Bank bank, std::uint32_t instance)
    {
        return (bank == Bank::p2 && (instance == 0 || instance == 20)) ||
               (bank == Bank::p1 && instance >= 20 && instance <= 22) ||
               (bank == Bank::p0 && instance == 30);
    }

    /**
     * @brief SPI/TWI peripheral의 전송 buffer를 준비 단계에서 등록할지 판정합니다.
     * @note 지연 RX를 사용하는 UART가 SPI buffer 분기로 진입하면 안 됩니다.
     */
    constexpr bool shouldQueueSerialPeripheralBuffers(bool uart, bool controller,
                                                      bool gpio_line_generator,
                                                      bool deferred_twis_buffers)
    {
        return !uart && !controller && !gpio_line_generator && !deferred_twis_buffers;
    }

    /**
     * @brief 명시적 결선 확인 뒤 10초 동안만 명령을 허용합니다.
     * @note 물리 스위치를 감지하지 않습니다. Host의 사용자 확인과 함께 사용합니다.
     * 만료 후 활성 DMA의 STOP 증명과 자원 보존은 호출자가 수행합니다.
     */
    class FixtureGate
    {
      public:
        static constexpr std::uint32_t revision = 1;
        static constexpr std::uint32_t consent = 0x53414645U;
        static constexpr std::uint64_t lease_ms = 10000;

        bool arm(std::uint32_t id, std::uint32_t rev, std::uint32_t confirmed,
                 std::uint32_t controller_role, std::uint32_t local_role, std::uint64_t now)
        {
            if (fixture_ || faulted_ || rev != revision || confirmed != consent ||
                (controller_role != 1 && controller_role != 2) ||
                ((((id >= 401 && id <= 407) || id == 408 || id == 420)) && controller_role != 2) ||
                fixtureBank(id, local_role) == Bank::invalid || now > UINT64_MAX - lease_ms)
            {
                return false;
            }
            fixture_ = id;
            controller_ = controller_role;
            deadline_ = now + lease_ms;
            return true;
        }

        bool live(std::uint64_t now) const
        {
            return fixture_ && !faulted_ && now < deadline_;
        }

        bool renew(std::uint64_t now)
        {
            if (!live(now) || now > UINT64_MAX - lease_ms)
            {
                return false;
            }
            deadline_ = now + lease_ms;
            return true;
        }

        void close(bool stopped)
        {
            fixture_ = 0;
            deadline_ = 0;
            faulted_ |= !stopped;
        }

        bool claimed() const
        {
            return fixture_ || faulted_;
        }

        std::uint32_t fixture() const
        {
            return fixture_;
        }

        std::uint32_t controller() const
        {
            return controller_;
        }

      private:
        std::uint32_t fixture_ = 0;
        std::uint32_t controller_ = 0;
        std::uint64_t deadline_ = 0;
        bool faulted_ = false;
    };
} // namespace v04
