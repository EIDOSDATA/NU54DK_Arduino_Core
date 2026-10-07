/** @file @brief NCS OTS/OTC의 단일 session·고정 buffer Arduino API입니다.
 * SPDX-License-Identifier: MIT
 */
#ifndef NUCODE_BLE_OBJECT_TRANSFER_H_
#define NUCODE_BLE_OBJECT_TRANSFER_H_
#include <NUCODE_BLE.h>
#include <NUCODE_BLE_ObjectStore.h>
namespace nucode::ble::profiles
{
    enum class ObjectEventType : std::uint8_t
    {
        ready,
        created,
        deleted,
        selected,
        metadata,
        received,
        written,
        disconnected,
        error
    };
    /** @brief callback 수명과 무관한 이벤트 복사본입니다. received는 최대 512-byte object입니다. */
    struct ObjectEvent
    {
        ObjectEventType type = ObjectEventType::error;
        BLEConnectionHandle peer;
        std::uint64_t id = 0U;
        int status = 0;
        std::size_t length = 0U;
        std::uint8_t data[ObjectStore::maximum_bytes] = {};
        char name[ObjectStore::maximum_name + 1U] = {};
        std::uint32_t properties = 0U;
    };
    /**
     * @brief Native OTS service의 object 저장소입니다. RAM object만 제공하며 재부팅하면 사라집니다.
     * @note CONFIG_BT_OTS=y, CONFIG_BT_MAX_CONN=1 필요. local add는 연결 전만 허용합니다.
     */
    class ObjectTransferServer final
    {
      public:
        [[nodiscard]] bool begin() noexcept;
        [[nodiscard]] bool add(const char *name, const std::uint8_t *data, std::size_t length,
                               bool writable, bool removable, std::uint64_t &id) noexcept;
        [[nodiscard]] bool remove(std::uint64_t id) noexcept;
        [[nodiscard]] bool readEvent(ObjectEvent &event) noexcept;
        [[nodiscard]] int lastError() const noexcept;
    };
    /**
     * @brief OTS client의 발견·구독·목록 이동·metadata·CoC read/write입니다.
     * @note 각 비동기 요청은 하나씩 진행합니다. poll을 호출하면 10초 timeout에 연결을 종료합니다.
     * Native SDK가 한 client instance를 제공하므로 두 번째 link 요청은 fail-closed합니다.
     */
    class ObjectTransferClient final
    {
      public:
        [[nodiscard]] bool begin(BLEConnectionHandle peer) noexcept;
        void poll() noexcept;
        [[nodiscard]] bool selectFirst() noexcept;
        [[nodiscard]] bool selectNext() noexcept;
        [[nodiscard]] bool select(std::uint64_t id) noexcept;
        [[nodiscard]] bool metadata() noexcept;
        [[nodiscard]] bool read() noexcept;
        [[nodiscard]] bool write(const std::uint8_t *data, std::size_t length,
                                 std::uint32_t offset = 0U) noexcept;
        /** @brief 원격 object를 만들며, 생성 후 name 설정 전 연결이 끊기면 SDK가 폐기합니다. */
        [[nodiscard]] bool create(std::uint32_t capacity) noexcept;
        [[nodiscard]] bool rename(const char *name) noexcept;
        [[nodiscard]] bool remove() noexcept;
        /** @brief 연결을 종료해 CoC와 진행 요청을 정리합니다. 이후 새 begin으로 재시작합니다. */
        [[nodiscard]] bool cancel() noexcept;
        [[nodiscard]] bool busy() const noexcept;
        /** @brief 현재/최근 read에서 복사한 byte 수입니다. 전체 완료는 received event로 판정합니다. */
        [[nodiscard]] std::size_t bytesReceived() const noexcept;
        [[nodiscard]] bool readEvent(ObjectEvent &event) noexcept;
        [[nodiscard]] int lastError() const noexcept;
    };
} // namespace nucode::ble::profiles
#endif
