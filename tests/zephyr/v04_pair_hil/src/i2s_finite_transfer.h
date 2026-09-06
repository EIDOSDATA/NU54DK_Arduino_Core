/**
 * @file i2s_finite_transfer.h
 * @brief 연속 I2S에서 유한 payload와 마지막 반환용 tail buffer의 순서를 관리합니다.
 * SPDX-License-Identifier: MIT
 */
#pragma once
#include <cstdint>

namespace v04
{
    class I2sFiniteTransfer
    {
      public:
        /** @brief slot 0으로 시작한 단일/이중 payload의 다음 요청을 준비합니다. */
        void reset(std::uint32_t buffers)
        {
            buffers_ = buffers;
            next_ = 1U;
            completed_ = 0U;
        }

        /** @brief 다음 payload, tail slot 2, 정지 보호용 slot 3 순서로 반환합니다. */
        std::uint32_t nextSlot() const
        {
            return next_ < buffers_ ? next_ : 2U + next_ - buffers_;
        }

        /** @brief driver가 다음 buffer를 실제로 수락한 뒤에만 진행합니다. */
        void queued()
        {
            ++next_;
        }

        /** @brief 제출되지 않은 slot·tail·중복 반환을 payload 완료로 인정하지 않습니다. */
        bool released(std::uint32_t slot)
        {
            if (slot >= buffers_ || slot >= next_ || (completed_ & (1U << slot)) != 0U)
            {
                return false;
            }
            completed_ |= 1U << slot;
            return true;
        }

        /** @brief 모든 요청 payload가 각각 반환되었는지 확인합니다. */
        bool complete() const
        {
            return completed_ == ((1U << buffers_) - 1U);
        }

      private:
        std::uint32_t buffers_ = 1U;
        std::uint32_t next_ = 1U;
        std::uint32_t completed_ = 0U;
    };
} // namespace v04
