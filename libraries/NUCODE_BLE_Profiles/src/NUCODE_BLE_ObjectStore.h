/** @file @brief OTS의 exact object ID와 권한·범위를 검사하는 고정 저장소입니다.
 * SPDX-License-Identifier: MIT
 */
#ifndef NUCODE_BLE_OBJECT_STORE_H_
#define NUCODE_BLE_OBJECT_STORE_H_
#include <cstddef>
#include <cstdint>

namespace nucode::ble::profiles
{
    /** @brief RAM object 4개를 관리합니다. 삭제된 ID를 index로 변환하지 않습니다. */
    class ObjectStore final
    {
      public:
        static constexpr std::size_t maximum_objects = 4U;
        static constexpr std::size_t maximum_bytes = 512U;
        static constexpr std::size_t maximum_name = 32U;
        struct Object
        {
            std::uint64_t id = 0U;
            std::uint8_t bytes[maximum_bytes] = {};
            char name[maximum_name + 1U] = {};
            std::size_t size = 0U;
            std::size_t capacity = 0U;
            bool writable = false;
            bool removable = false;
        };
        [[nodiscard]] Object *find(std::uint64_t id) noexcept;
        [[nodiscard]] const Object *find(std::uint64_t id) const noexcept;
        [[nodiscard]] Object *create(std::uint64_t id, const char *name, std::size_t capacity,
                                     const std::uint8_t *data, std::size_t length, bool writable,
                                     bool removable) noexcept;
        [[nodiscard]] bool erase(std::uint64_t id) noexcept;
        [[nodiscard]] bool write(std::uint64_t id, std::size_t offset, const std::uint8_t *data,
                                 std::size_t length) noexcept;
        [[nodiscard]] bool read(std::uint64_t id, std::size_t offset, std::uint8_t *data,
                                std::size_t length) const noexcept;
        [[nodiscard]] std::size_t count() const noexcept;

      private:
        Object objects_[maximum_objects] = {};
    };
} // namespace nucode::ble::profiles
#endif
