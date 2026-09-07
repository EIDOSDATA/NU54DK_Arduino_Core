/** @file @brief PDM 연속 DMA의 순서·경계·버퍼별 통계를 보존합니다. */
#pragma once
#include <cstddef>
#include <cstdint>

namespace v04
{
    class PdmContinuous
    {
      public:
        static constexpr unsigned capacity = 1024U, total = 104U, slots = 4U;
        /** @brief 네 DMA slot과 전체 반환 기록을 새 실행 상태로 초기화합니다. */
        void reset(unsigned samples, bool stereo)
        {
            samples_ = samples;
            stereo_ = stereo;
            submitted_ = completed_ = 0U;
            for (auto &slot : data_)
            {
                slot.before = slot.after = canary;
                slot.busy = false;
                for (auto &value : slot.samples)
                {
                    value = sentinel;
                }
            }
        }
        /** @brief 반환 전 slot 재사용과 요청 범위 초과를 거부합니다. */
        std::int16_t *next()
        {
            if (samples_ == 0U || samples_ > capacity || submitted_ >= total + 2U ||
                data_[submitted_ % slots].busy || !guards())
            {
                return nullptr;
            }
            return data_[submitted_ % slots].samples;
        }
        /** @brief 실제 driver 제출 성공 이후에만 DMA 소유 상태를 진행합니다. */
        void queued()
        {
            data_[submitted_ % slots].busy = true;
            ++submitted_;
        }
        /** @brief 기대 순서·포인터·길이·경계를 검사하고 실제 sample 통계를 저장합니다. */
        bool released(const std::int16_t *pointer, unsigned samples)
        {
            const auto slot = completed_ % slots;
            if (completed_ >= total || pointer != data_[slot].samples || !data_[slot].busy ||
                samples != samples_ || !guards())
            {
                return false;
            }
            auto *record = records_[completed_];
            record[0] = completed_;
            record[1] = slot;
            record[2] = samples;
            std::int32_t sums[2]{};
            std::int16_t minima[2]{32767, 32767}, maxima[2]{-32768, -32768};
            std::uint32_t hash = 2166136261U;
            for (unsigned index = 0U; index < samples; ++index)
            {
                const auto channel = stereo_ ? index % 2U : 0U;
                const auto value = pointer[index];
                sums[channel] += value;
                minima[channel] = value < minima[channel] ? value : minima[channel];
                maxima[channel] = value > maxima[channel] ? value : maxima[channel];
                const auto bits = static_cast<std::uint16_t>(value);
                hash = (hash ^ (bits & 255U)) * 16777619U;
                hash = (hash ^ (bits >> 8U)) * 16777619U;
            }
            for (unsigned channel = 0U; channel < 2U; ++channel)
            {
                record[3U + channel] = static_cast<std::uint32_t>(sums[channel]);
                record[5U + channel] =
                    static_cast<std::uint16_t>(minima[channel]) |
                    (static_cast<std::uint32_t>(static_cast<std::uint16_t>(maxima[channel]))
                     << 16U);
            }
            record[7] = hash;
            data_[slot].busy = false;
            ++completed_;
            return true;
        }
        /** @brief DMA payload 앞뒤와 짧은 buffer 뒤의 미사용 영역을 검사합니다. */
        bool guards() const
        {
            for (const auto &slot : data_)
            {
                if (slot.before != canary || slot.after != canary)
                {
                    return false;
                }
                for (unsigned index = samples_; index < capacity; ++index)
                {
                    if (slot.samples[index] != sentinel)
                    {
                        return false;
                    }
                }
            }
            return true;
        }
        bool complete() const
        {
            return completed_ == total;
        }
        const std::uint32_t *record(unsigned index) const
        {
            return index < completed_ ? records_[index] : nullptr;
        }

      private:
        static constexpr std::uint32_t canary = 0xC35AA53CU;
        static constexpr std::int16_t sentinel = 0x5A5A;
        struct alignas(4) Slot
        {
            std::uint32_t before{};
            std::int16_t samples[capacity]{};
            std::uint32_t after{};
            bool busy{};
        };
        Slot data_[slots]{};
        std::uint32_t records_[total][8]{};
        unsigned samples_{}, submitted_{}, completed_{};
        bool stereo_{};
    };
} // namespace v04
