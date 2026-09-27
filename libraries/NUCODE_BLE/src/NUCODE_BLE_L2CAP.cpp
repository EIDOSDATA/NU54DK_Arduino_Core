/**
 * @file NUCODE_BLE_L2CAP.cpp
 * @brief 고정 자원 Bluetooth LE Credit Based Channel을 구현합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <NUCODE_BLE_L2CAP.h>

#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE)

#include <internal/NUCODE_BLE_Internal.h>

#include <errno.h>

#if defined(CONFIG_NUCODE_BLE_L2CAP) && defined(CONFIG_BT_L2CAP_DYNAMIC_CHANNEL)

#include <zephyr/bluetooth/l2cap.h>
#include <zephyr/kernel.h>
#include <zephyr/net_buf.h>
#include <zephyr/sys/atomic.h>

#include <string.h>

namespace nucode::ble::internal
{

    /** @brief 공개 LE CoC handle의 token 표현을 구현 내부에만 개방합니다. */
    struct BLEL2capChannelHandleAccess
    {
        [[nodiscard]] static constexpr BLEL2capChannelHandle make(
            std::size_t slot, std::uint32_t generation) noexcept
        {
            return generation == 0U
                       ? BLEL2capChannelHandle{}
                       : BLEL2capChannelHandle((static_cast<std::uint64_t>(generation) << 8U) |
                                               static_cast<std::uint64_t>(slot + 1U));
        }

        [[nodiscard]] static constexpr std::size_t slot(
            BLEL2capChannelHandle handle) noexcept
        {
            const std::uint64_t encoded = handle.token_ & 0xffU;
            return encoded == 0U ? static_cast<std::size_t>(0xffU)
                                 : static_cast<std::size_t>(encoded - 1U);
        }

        [[nodiscard]] static constexpr std::uint32_t generation(
            BLEL2capChannelHandle handle) noexcept
        {
            return static_cast<std::uint32_t>(handle.token_ >> 8U);
        }
    };

} // namespace nucode::ble::internal

namespace nucode::ble::internal::l2cap
{

    namespace
    {
        constexpr std::size_t channel_count = L2capCoc::maximum_channels;
        constexpr std::size_t rx_record_count = L2capCoc::receive_records_per_channel;
        constexpr std::size_t maximum_sdu = L2capCoc::maximum_sdu_length;
        constexpr std::uint16_t minimum_dynamic_psm = 0x0080U;
        constexpr std::uint16_t maximum_dynamic_psm = 0x00ffU;
        constexpr std::uint8_t no_rx_record = 0xffU;

        enum class ChannelState : std::uint8_t
        {
            free,
            connecting,
            connected,
            disconnecting,
            disconnected,
        };

        /** @brief callback payload를 stack buffer 수명과 분리하는 한 개의 고정 RX record입니다. */
        struct ReceiveRecord
        {
            std::uint32_t generation = 0U;
            std::uint16_t length = 0U;
            bool occupied = false;
            std::uint8_t data[maximum_sdu] = {};
        };

        /** @brief Zephyr channel 객체와 공개 generation 수명을 결합합니다. */
        struct ChannelSlot
        {
            struct bt_l2cap_le_chan channel = {};
            BLEConnectionHandle connection;
            std::uint32_t generation = 0U;
            std::uint8_t pending_transmits = 0U;
            ChannelState state = ChannelState::free;
            ReceiveRecord receives[rx_record_count] = {};
        };

        /** @brief main thread가 소비할 작은 control 또는 RX record 참조입니다. */
        struct EventRecord
        {
            BLEL2capEvent event = BLEL2capEvent::disconnected;
            BLEL2capChannelHandle channel;
            BLEConnectionHandle connection;
            std::uint32_t session_generation = 0U;
            std::uint16_t local_mtu = 0U;
            std::uint16_t remote_mtu = 0U;
            std::uint8_t receive_index = no_rx_record;
            int status = 0;
        };

        /** @brief server·두 channel·통계를 image 수명 동안 한 곳에서 소유합니다. */
        struct L2capContext
        {
            struct k_spinlock lock;
            struct bt_l2cap_server server = {};
            ChannelSlot channels[channel_count] = {};
            atomic_t next_generation = ATOMIC_INIT(1);
            atomic_t session_generation = ATOMIC_INIT(1);
            bool server_registered = false;
            bool server_enabled = false;
            bool session_active = false;
            std::uint8_t transmits_in_use = 0U;
            BLEL2capEventCallback callback = nullptr;
            void *callback_context = nullptr;
            BLEL2capStatistics statistics;
        };

        K_MSGQ_DEFINE(event_queue, sizeof(EventRecord),
                      CONFIG_NUCODE_BLE_L2CAP_EVENT_QUEUE_SIZE, alignof(EventRecord));
        NET_BUF_POOL_FIXED_DEFINE(rx_pool, channel_count,
                                  BT_L2CAP_SDU_BUF_SIZE(maximum_sdu), sizeof(std::uint16_t),
                                  nullptr);
        NET_BUF_POOL_FIXED_DEFINE(tx_pool, L2capCoc::transmit_buffers,
                                  BT_L2CAP_SDU_BUF_SIZE(maximum_sdu),
                                  CONFIG_BT_CONN_TX_USER_DATA_SIZE, nullptr);

        L2capContext context{};

        void channelConnected(struct bt_l2cap_chan *channel);
        void channelDisconnected(struct bt_l2cap_chan *channel);
        struct net_buf *allocateReceiveBuffer(struct bt_l2cap_chan *channel);
        int channelReceived(struct bt_l2cap_chan *channel, struct net_buf *buffer);
        void channelSent(struct bt_l2cap_chan *channel);
        void channelReleased(struct bt_l2cap_chan *channel);
        void channelReconfigured(struct bt_l2cap_chan *channel);
        int acceptChannel(struct bt_conn *connection, struct bt_l2cap_server *server,
                          struct bt_l2cap_chan **channel);

        const struct bt_l2cap_chan_ops channel_operations = {
            .connected = channelConnected,
            .disconnected = channelDisconnected,
            .encrypt_change = nullptr,
            .alloc_seg = nullptr,
            .alloc_buf = allocateReceiveBuffer,
            .recv = channelReceived,
            .sent = channelSent,
            .status = nullptr,
            .released = channelReleased,
            .reconfigured = channelReconfigured,
        };

        /** @brief 0을 건너뛰는 image 수명 channel generation을 발급합니다. */
        std::uint32_t nextGeneration() noexcept
        {
            std::uint32_t generation =
                static_cast<std::uint32_t>(atomic_inc(&context.next_generation)) + 1U;
            if (generation == 0U)
            {
                generation = static_cast<std::uint32_t>(
                                 atomic_inc(&context.next_generation)) +
                             1U;
            }
            return generation;
        }

        /** @brief PSM이 자동 할당 또는 LE 동적 범위인지 확인합니다. */
        bool validPsm(std::uint16_t psm, bool allow_auto) noexcept
        {
            return (allow_auto && psm == 0U) ||
                   (psm >= minimum_dynamic_psm && psm <= maximum_dynamic_psm);
        }

        /** @brief Zephyr callback channel이 소유 slot인지 lock 안에서 찾습니다. */
        ChannelSlot *slotForChannelLocked(struct bt_l2cap_chan *channel,
                                          std::size_t &slot_index) noexcept
        {
            for (std::size_t index = 0U; index < channel_count; ++index)
            {
                if (&context.channels[index].channel.chan == channel)
                {
                    slot_index = index;
                    return &context.channels[index];
                }
            }
            slot_index = channel_count;
            return nullptr;
        }

        /** @brief 공개 handle이 현재 slot generation과 일치하는지 lock 안에서 확인합니다. */
        ChannelSlot *slotForHandleLocked(BLEL2capChannelHandle handle,
                                         std::size_t &slot_index) noexcept
        {
            if (!handle.valid())
            {
                slot_index = channel_count;
                return nullptr;
            }
            slot_index = BLEL2capChannelHandleAccess::slot(handle);
            if (slot_index >= channel_count)
            {
                return nullptr;
            }
            ChannelSlot &slot = context.channels[slot_index];
            if (slot.generation != BLEL2capChannelHandleAccess::generation(handle) ||
                slot.state == ChannelState::free)
            {
                return nullptr;
            }
            return &slot;
        }

        /** @brief free slot을 Zephyr가 요구하는 zeroed channel 객체로 초기화합니다. */
        ChannelSlot *reserveSlotLocked(BLEConnectionHandle connection,
                                       std::size_t &slot_index) noexcept
        {
            for (std::size_t index = 0U; index < channel_count; ++index)
            {
                ChannelSlot &slot = context.channels[index];
                if (slot.state != ChannelState::free)
                {
                    continue;
                }
                ::memset(&slot.channel, 0, sizeof(slot.channel));
                slot.channel.chan.ops = &channel_operations;
                slot.channel.rx.mtu = static_cast<std::uint16_t>(maximum_sdu);
                slot.channel.required_sec_level = BT_SECURITY_L1;
                slot.connection = connection;
                slot.generation = nextGeneration();
                slot.pending_transmits = 0U;
                slot.state = ChannelState::connecting;
                slot_index = index;
                return &slot;
            }
            slot_index = channel_count;
            return nullptr;
        }

        /** @brief queue overflow를 누적하고 공통 오류 경계에 보고합니다. */
        bool queueEvent(const EventRecord &record) noexcept
        {
            if (k_msgq_put(&event_queue, &record, K_NO_WAIT) == 0)
            {
                return true;
            }
            k_spinlock_key_t key = k_spin_lock(&context.lock);
            ++context.statistics.dropped_events;
            k_spin_unlock(&context.lock, key);
            nucode::ble::internal::recordError(BLEError::event_overflow, -ENOBUFS, true);
            return false;
        }

        /** @brief 현재 slot 상태를 main-thread event record로 복사합니다. */
        EventRecord makeEventLocked(BLEL2capEvent event, std::size_t slot_index,
                                    int status = 0) noexcept
        {
            const ChannelSlot &slot = context.channels[slot_index];
            return {
                .event = event,
                .channel = BLEL2capChannelHandleAccess::make(slot_index, slot.generation),
                .connection = slot.connection,
                .session_generation = static_cast<std::uint32_t>(
                    atomic_get(&context.session_generation)),
                .local_mtu = slot.channel.rx.mtu,
                .remote_mtu = slot.channel.tx.mtu,
                .receive_index = no_rx_record,
                .status = status,
            };
        }

        void channelConnected(struct bt_l2cap_chan *channel)
        {
            EventRecord record = {};
            bool deliver = false;
            k_spinlock_key_t key = k_spin_lock(&context.lock);
            std::size_t slot_index = channel_count;
            ChannelSlot *slot = slotForChannelLocked(channel, slot_index);
            if (context.session_active && slot != nullptr &&
                slot->state == ChannelState::connecting)
            {
                slot->state = ChannelState::connected;
                ++context.statistics.connected;
                record = makeEventLocked(BLEL2capEvent::connected, slot_index);
                deliver = true;
            }
            k_spin_unlock(&context.lock, key);
            if (deliver)
            {
                static_cast<void>(queueEvent(record));
            }
        }

        void channelDisconnected(struct bt_l2cap_chan *channel)
        {
            EventRecord record = {};
            bool deliver = false;
            k_spinlock_key_t key = k_spin_lock(&context.lock);
            std::size_t slot_index = channel_count;
            ChannelSlot *slot = slotForChannelLocked(channel, slot_index);
            if (slot != nullptr && slot->state != ChannelState::free &&
                slot->state != ChannelState::disconnected)
            {
                if (slot->pending_transmits <= context.transmits_in_use)
                {
                    context.transmits_in_use = static_cast<std::uint8_t>(
                        context.transmits_in_use - slot->pending_transmits);
                }
                else
                {
                    context.transmits_in_use = 0U;
                }
                slot->pending_transmits = 0U;
                slot->state = ChannelState::disconnected;
                ++context.statistics.disconnected;
                if (context.session_active)
                {
                    record = makeEventLocked(BLEL2capEvent::disconnected, slot_index);
                    deliver = true;
                }
            }
            k_spin_unlock(&context.lock, key);
            if (deliver)
            {
                static_cast<void>(queueEvent(record));
            }
        }

        struct net_buf *allocateReceiveBuffer(struct bt_l2cap_chan *channel)
        {
            static_cast<void>(channel);
            return net_buf_alloc(&rx_pool, K_FOREVER);
        }

        int channelReceived(struct bt_l2cap_chan *channel, struct net_buf *buffer)
        {
            if (buffer == nullptr || buffer->len > maximum_sdu)
            {
                return -EMSGSIZE;
            }

            EventRecord record = {};
            std::uint8_t receive_index = no_rx_record;
            k_spinlock_key_t key = k_spin_lock(&context.lock);
            std::size_t slot_index = channel_count;
            ChannelSlot *slot = slotForChannelLocked(channel, slot_index);
            if (context.session_active && slot != nullptr &&
                slot->state == ChannelState::connected)
            {
                for (std::size_t index = 0U; index < rx_record_count; ++index)
                {
                    if (!slot->receives[index].occupied)
                    {
                        ReceiveRecord &receive = slot->receives[index];
                        receive.occupied = true;
                        receive.generation = slot->generation;
                        receive.length = static_cast<std::uint16_t>(buffer->len);
                        if (buffer->len != 0U)
                        {
                            ::memcpy(receive.data, buffer->data, buffer->len);
                        }
                        receive_index = static_cast<std::uint8_t>(index);
                        record = makeEventLocked(BLEL2capEvent::received, slot_index);
                        record.receive_index = receive_index;
                        ++context.statistics.received;
                        break;
                    }
                }
            }
            if (receive_index == no_rx_record)
            {
                ++context.statistics.dropped_events;
            }
            k_spin_unlock(&context.lock, key);

            if (receive_index == no_rx_record)
            {
                nucode::ble::internal::recordError(BLEError::event_overflow, -ENOBUFS, true);
                return 0;
            }
            if (!queueEvent(record))
            {
                key = k_spin_lock(&context.lock);
                ReceiveRecord &receive =
                    context.channels[slot_index].receives[receive_index];
                if (receive.occupied &&
                    receive.generation == BLEL2capChannelHandleAccess::generation(record.channel))
                {
                    receive.occupied = false;
                    receive.length = 0U;
                }
                k_spin_unlock(&context.lock, key);
            }
            return 0;
        }

        void channelSent(struct bt_l2cap_chan *channel)
        {
            EventRecord record = {};
            bool deliver = false;
            k_spinlock_key_t key = k_spin_lock(&context.lock);
            std::size_t slot_index = channel_count;
            ChannelSlot *slot = slotForChannelLocked(channel, slot_index);
            if (slot != nullptr && slot->state != ChannelState::free)
            {
                if (slot->pending_transmits != 0U)
                {
                    --slot->pending_transmits;
                    if (context.transmits_in_use != 0U)
                    {
                        --context.transmits_in_use;
                    }
                }
                ++context.statistics.sent;
                if (context.session_active)
                {
                    record = makeEventLocked(BLEL2capEvent::sent, slot_index);
                    deliver = true;
                }
            }
            k_spin_unlock(&context.lock, key);
            if (deliver)
            {
                static_cast<void>(queueEvent(record));
            }
        }

        void channelReleased(struct bt_l2cap_chan *channel)
        {
            k_spinlock_key_t key = k_spin_lock(&context.lock);
            std::size_t slot_index = channel_count;
            ChannelSlot *slot = slotForChannelLocked(channel, slot_index);
            if (slot != nullptr)
            {
                slot->state = ChannelState::free;
                slot->connection = BLEConnectionHandle{};
                slot->pending_transmits = 0U;
            }
            k_spin_unlock(&context.lock, key);
        }

        void channelReconfigured(struct bt_l2cap_chan *channel)
        {
            EventRecord record = {};
            bool deliver = false;
            k_spinlock_key_t key = k_spin_lock(&context.lock);
            std::size_t slot_index = channel_count;
            ChannelSlot *slot = slotForChannelLocked(channel, slot_index);
            if (context.session_active && slot != nullptr &&
                slot->state == ChannelState::connected)
            {
                record = makeEventLocked(BLEL2capEvent::reconfigured, slot_index);
                deliver = true;
            }
            k_spin_unlock(&context.lock, key);
            if (deliver)
            {
                static_cast<void>(queueEvent(record));
            }
        }

        int acceptChannel(struct bt_conn *connection, struct bt_l2cap_server *server,
                          struct bt_l2cap_chan **channel)
        {
            static_cast<void>(server);
            if (channel == nullptr)
            {
                return -EINVAL;
            }
            const BLEConnectionHandle connection_handle =
                nucode::ble::internal::handleForActiveConnection(connection);
            if (!connection_handle.valid())
            {
                k_spinlock_key_t key = k_spin_lock(&context.lock);
                ++context.statistics.rejected;
                k_spin_unlock(&context.lock, key);
                return -ENOTCONN;
            }

            k_spinlock_key_t key = k_spin_lock(&context.lock);
            if (!context.session_active || !context.server_enabled)
            {
                ++context.statistics.rejected;
                k_spin_unlock(&context.lock, key);
                return -EACCES;
            }
            std::size_t slot_index = channel_count;
            ChannelSlot *slot = reserveSlotLocked(connection_handle, slot_index);
            if (slot == nullptr)
            {
                ++context.statistics.rejected;
                k_spin_unlock(&context.lock, key);
                return -ENOMEM;
            }
            ++context.statistics.accepted;
            *channel = &slot->channel.chan;
            k_spin_unlock(&context.lock, key);
            return 0;
        }

    } // namespace

    void poll() noexcept
    {
        EventRecord record = {};
        while (k_msgq_get(&event_queue, &record, K_NO_WAIT) == 0)
        {
            if (record.session_generation != static_cast<std::uint32_t>(
                                                    atomic_get(&context.session_generation)))
            {
                continue;
            }

            BLEL2capEventCallback callback = nullptr;
            void *callback_context = nullptr;
            BLEL2capEventInfo information = {
                .event = record.event,
                .channel = record.channel,
                .connection = record.connection,
                .data = nullptr,
                .length = 0U,
                .local_mtu = record.local_mtu,
                .remote_mtu = record.remote_mtu,
                .status = record.status,
            };
            ReceiveRecord *receive = nullptr;

            k_spinlock_key_t key = k_spin_lock(&context.lock);
            const std::size_t slot_index = BLEL2capChannelHandleAccess::slot(record.channel);
            const std::uint32_t generation =
                BLEL2capChannelHandleAccess::generation(record.channel);
            if (slot_index < channel_count &&
                context.channels[slot_index].generation == generation)
            {
                callback = context.callback;
                callback_context = context.callback_context;
                if (record.receive_index < rx_record_count)
                {
                    ReceiveRecord &candidate =
                        context.channels[slot_index].receives[record.receive_index];
                    if (candidate.occupied && candidate.generation == generation)
                    {
                        receive = &candidate;
                        information.data = candidate.data;
                        information.length = candidate.length;
                    }
                }
            }
            k_spin_unlock(&context.lock, key);

            if (record.event != BLEL2capEvent::received || receive != nullptr)
            {
                if (callback != nullptr)
                {
                    callback(information, callback_context);
                }
            }

            if (receive != nullptr)
            {
                key = k_spin_lock(&context.lock);
                if (receive->occupied && receive->generation == generation)
                {
                    receive->occupied = false;
                    receive->length = 0U;
                }
                k_spin_unlock(&context.lock, key);
            }
        }
    }

    void end() noexcept
    {
        struct bt_l2cap_chan *channels[channel_count] = {};
        atomic_inc(&context.session_generation);
        k_spinlock_key_t key = k_spin_lock(&context.lock);
        context.session_active = false;
        context.server_enabled = false;
        for (std::size_t slot_index = 0U; slot_index < channel_count; ++slot_index)
        {
            ChannelSlot &slot = context.channels[slot_index];
            if (slot.state == ChannelState::connecting || slot.state == ChannelState::connected)
            {
                slot.state = ChannelState::disconnecting;
                channels[slot_index] = &slot.channel.chan;
            }
            for (ReceiveRecord &receive : slot.receives)
            {
                receive.occupied = false;
                receive.length = 0U;
            }
        }
        context.transmits_in_use = 0U;
        k_spin_unlock(&context.lock, key);
        k_msgq_purge(&event_queue);

        for (struct bt_l2cap_chan *channel : channels)
        {
            if (channel != nullptr)
            {
                static_cast<void>(bt_l2cap_chan_disconnect(channel));
            }
        }
    }

} // namespace nucode::ble::internal::l2cap

namespace nucode::ble::internal
{

    void pollL2cap() noexcept
    {
        l2cap::poll();
    }

    void l2capEnded() noexcept
    {
        l2cap::end();
    }

} // namespace nucode::ble::internal

namespace nucode::ble
{

    bool L2capCoc::startServer(std::uint16_t psm) noexcept
    {
        using namespace internal::l2cap;
        if (!internal::requireThreadContext())
        {
            return false;
        }
        if (!BLEDevice.initialized())
        {
            internal::recordError(BLEError::not_initialized, -ENODEV, true);
            return false;
        }
        if (!validPsm(psm, true))
        {
            internal::recordError(BLEError::invalid_argument, -EINVAL, true);
            return false;
        }

        internal::l2cap::L2capContext &state = internal::l2cap::context;
        k_spinlock_key_t key = k_spin_lock(&state.lock);
        if (state.server_registered)
        {
            if (psm != 0U && psm != state.server.psm)
            {
                k_spin_unlock(&state.lock, key);
                internal::recordError(BLEError::already_started, -EALREADY, true);
                return false;
            }
            state.server_enabled = true;
            state.session_active = true;
            k_spin_unlock(&state.lock, key);
            internal::recordError(BLEError::none);
            return true;
        }
        ::memset(&state.server, 0, sizeof(state.server));
        state.server.psm = psm;
        state.server.sec_level = BT_SECURITY_L1;
        state.server.accept = internal::l2cap::acceptChannel;
        k_spin_unlock(&state.lock, key);

        const int result = bt_l2cap_server_register(&state.server);
        key = k_spin_lock(&state.lock);
        if (result == 0)
        {
            state.server_registered = true;
            state.server_enabled = true;
            state.session_active = true;
        }
        k_spin_unlock(&state.lock, key);
        if (result < 0)
        {
            internal::recordError(BLEError::driver_error, result, true);
            return false;
        }
        internal::recordError(BLEError::none);
        return true;
    }

    std::uint16_t L2capCoc::serverPsm() const noexcept
    {
        k_spinlock_key_t key = k_spin_lock(&internal::l2cap::context.lock);
        const std::uint16_t psm = internal::l2cap::context.server_registered
                                      ? internal::l2cap::context.server.psm
                                      : 0U;
        k_spin_unlock(&internal::l2cap::context.lock, key);
        return psm;
    }

    bool L2capCoc::connect(BLEConnectionHandle connection, std::uint16_t psm,
                           BLEL2capChannelHandle &channel) noexcept
    {
        channel = BLEL2capChannelHandle{};
        if (!internal::requireThreadContext())
        {
            return false;
        }
        if (!BLEDevice.initialized())
        {
            internal::recordError(BLEError::not_initialized, -ENODEV, true);
            return false;
        }
        if (!connection.valid() || !internal::l2cap::validPsm(psm, false))
        {
            internal::recordError(BLEError::invalid_argument, -EINVAL, true);
            return false;
        }
        struct bt_conn *stack_connection = internal::referenceConnection(connection);
        if (stack_connection == nullptr)
        {
            internal::recordError(BLEError::not_connected, -ENOTCONN, true);
            return false;
        }

        k_spinlock_key_t key = k_spin_lock(&internal::l2cap::context.lock);
        std::size_t slot_index = internal::l2cap::channel_count;
        internal::l2cap::ChannelSlot *slot =
            internal::l2cap::reserveSlotLocked(connection, slot_index);
        if (slot == nullptr)
        {
            ++internal::l2cap::context.statistics.rejected;
            k_spin_unlock(&internal::l2cap::context.lock, key);
            bt_conn_unref(stack_connection);
            internal::recordError(BLEError::busy, -ENOSPC, true);
            return false;
        }
        internal::l2cap::context.session_active = true;
        channel = internal::BLEL2capChannelHandleAccess::make(slot_index, slot->generation);
        struct bt_l2cap_chan *stack_channel = &slot->channel.chan;
        k_spin_unlock(&internal::l2cap::context.lock, key);

        const int result = bt_l2cap_chan_connect(stack_connection, stack_channel, psm);
        bt_conn_unref(stack_connection);
        if (result < 0)
        {
            key = k_spin_lock(&internal::l2cap::context.lock);
            if (slot->generation ==
                internal::BLEL2capChannelHandleAccess::generation(channel))
            {
                slot->state = internal::l2cap::ChannelState::free;
                slot->connection = BLEConnectionHandle{};
            }
            ++internal::l2cap::context.statistics.rejected;
            k_spin_unlock(&internal::l2cap::context.lock, key);
            channel = BLEL2capChannelHandle{};
            internal::recordError(BLEError::driver_error, result, true);
            return false;
        }
        internal::recordError(BLEError::none);
        return true;
    }

    bool L2capCoc::send(BLEL2capChannelHandle channel, const void *data,
                        std::size_t length) noexcept
    {
        if (!internal::requireThreadContext())
        {
            return false;
        }
        if (data == nullptr || length == 0U)
        {
            internal::recordError(BLEError::invalid_argument, -EINVAL, true);
            return false;
        }
        if (length > maximum_sdu_length)
        {
            internal::recordError(BLEError::value_overflow, -EMSGSIZE, true);
            return false;
        }

        k_spinlock_key_t key = k_spin_lock(&internal::l2cap::context.lock);
        std::size_t slot_index = internal::l2cap::channel_count;
        internal::l2cap::ChannelSlot *slot =
            internal::l2cap::slotForHandleLocked(channel, slot_index);
        if (slot == nullptr || slot->state != internal::l2cap::ChannelState::connected)
        {
            k_spin_unlock(&internal::l2cap::context.lock, key);
            internal::recordError(BLEError::not_connected, -ENOTCONN, true);
            return false;
        }
        if (length > slot->channel.tx.mtu)
        {
            k_spin_unlock(&internal::l2cap::context.lock, key);
            internal::recordError(BLEError::value_overflow, -EMSGSIZE, true);
            return false;
        }
        struct bt_l2cap_chan *stack_channel = &slot->channel.chan;
        const std::uint32_t generation = slot->generation;
        k_spin_unlock(&internal::l2cap::context.lock, key);

        struct net_buf *buffer = net_buf_alloc(&internal::l2cap::tx_pool, K_NO_WAIT);
        if (buffer == nullptr)
        {
            key = k_spin_lock(&internal::l2cap::context.lock);
            ++internal::l2cap::context.statistics.backpressure;
            k_spin_unlock(&internal::l2cap::context.lock, key);
            internal::recordError(BLEError::busy, -EAGAIN, true);
            return false;
        }
        net_buf_reserve(buffer, BT_L2CAP_SDU_CHAN_SEND_RESERVE);
        static_cast<void>(net_buf_add_mem(buffer, data, length));

        key = k_spin_lock(&internal::l2cap::context.lock);
        slot = internal::l2cap::slotForHandleLocked(channel, slot_index);
        if (slot == nullptr || slot->generation != generation ||
            slot->state != internal::l2cap::ChannelState::connected)
        {
            k_spin_unlock(&internal::l2cap::context.lock, key);
            net_buf_unref(buffer);
            internal::recordError(BLEError::not_connected, -ENOTCONN, true);
            return false;
        }
        ++slot->pending_transmits;
        ++internal::l2cap::context.transmits_in_use;
        k_spin_unlock(&internal::l2cap::context.lock, key);

        const int result = bt_l2cap_chan_send(stack_channel, buffer);
        if (result < 0)
        {
            net_buf_unref(buffer);
            key = k_spin_lock(&internal::l2cap::context.lock);
            slot = internal::l2cap::slotForHandleLocked(channel, slot_index);
            if (slot != nullptr && slot->generation == generation &&
                slot->pending_transmits != 0U)
            {
                --slot->pending_transmits;
                if (internal::l2cap::context.transmits_in_use != 0U)
                {
                    --internal::l2cap::context.transmits_in_use;
                }
            }
            k_spin_unlock(&internal::l2cap::context.lock, key);
            if (result == -EAGAIN || result == -ENOMEM)
            {
                key = k_spin_lock(&internal::l2cap::context.lock);
                ++internal::l2cap::context.statistics.backpressure;
                k_spin_unlock(&internal::l2cap::context.lock, key);
                internal::recordError(BLEError::busy, result, true);
            }
            else
            {
                internal::recordError(BLEError::driver_error, result, true);
            }
            return false;
        }

        internal::recordError(BLEError::none);
        return true;
    }

    bool L2capCoc::disconnect(BLEL2capChannelHandle channel) noexcept
    {
        if (!internal::requireThreadContext())
        {
            return false;
        }
        k_spinlock_key_t key = k_spin_lock(&internal::l2cap::context.lock);
        std::size_t slot_index = internal::l2cap::channel_count;
        internal::l2cap::ChannelSlot *slot =
            internal::l2cap::slotForHandleLocked(channel, slot_index);
        if (slot == nullptr ||
            (slot->state != internal::l2cap::ChannelState::connecting &&
             slot->state != internal::l2cap::ChannelState::connected))
        {
            k_spin_unlock(&internal::l2cap::context.lock, key);
            internal::recordError(BLEError::not_connected, -ENOTCONN, true);
            return false;
        }
        const internal::l2cap::ChannelState previous_state = slot->state;
        slot->state = internal::l2cap::ChannelState::disconnecting;
        struct bt_l2cap_chan *stack_channel = &slot->channel.chan;
        k_spin_unlock(&internal::l2cap::context.lock, key);

        const int result = bt_l2cap_chan_disconnect(stack_channel);
        if (result < 0)
        {
            key = k_spin_lock(&internal::l2cap::context.lock);
            slot = internal::l2cap::slotForHandleLocked(channel, slot_index);
            if (slot != nullptr && slot->state == internal::l2cap::ChannelState::disconnecting)
            {
                slot->state = previous_state;
            }
            k_spin_unlock(&internal::l2cap::context.lock, key);
            internal::recordError(BLEError::driver_error, result, true);
            return false;
        }
        internal::recordError(BLEError::none);
        return true;
    }

    bool L2capCoc::connected(BLEL2capChannelHandle channel) const noexcept
    {
        k_spinlock_key_t key = k_spin_lock(&internal::l2cap::context.lock);
        std::size_t slot_index = internal::l2cap::channel_count;
        const internal::l2cap::ChannelSlot *slot =
            internal::l2cap::slotForHandleLocked(channel, slot_index);
        const bool active = slot != nullptr &&
                            slot->state == internal::l2cap::ChannelState::connected;
        k_spin_unlock(&internal::l2cap::context.lock, key);
        return active;
    }

    std::size_t L2capCoc::availableForWrite() const noexcept
    {
        k_spinlock_key_t key = k_spin_lock(&internal::l2cap::context.lock);
        const std::size_t in_use = internal::l2cap::context.transmits_in_use;
        k_spin_unlock(&internal::l2cap::context.lock, key);
        return in_use >= transmit_buffers ? 0U : transmit_buffers - in_use;
    }

    BLEL2capStatistics L2capCoc::statistics() const noexcept
    {
        k_spinlock_key_t key = k_spin_lock(&internal::l2cap::context.lock);
        const BLEL2capStatistics snapshot = internal::l2cap::context.statistics;
        k_spin_unlock(&internal::l2cap::context.lock, key);
        return snapshot;
    }

    void L2capCoc::onEvent(BLEL2capEventCallback callback, void *callback_context) noexcept
    {
        k_spinlock_key_t key = k_spin_lock(&internal::l2cap::context.lock);
        internal::l2cap::context.callback = callback;
        internal::l2cap::context.callback_context = callback_context;
        k_spin_unlock(&internal::l2cap::context.lock, key);
    }

} // namespace nucode::ble

#else

namespace nucode::ble::internal
{

    void pollL2cap() noexcept
    {
    }

    void l2capEnded() noexcept
    {
    }

} // namespace nucode::ble::internal

namespace nucode::ble
{

    namespace
    {
        /** @brief build profile에서 LE CoC가 꺼졌음을 공통 오류로 보고합니다. */
        bool unsupportedL2cap() noexcept
        {
            internal::recordError(BLEError::unsupported, -ENOTSUP, true);
            return false;
        }
    } // namespace

    bool L2capCoc::startServer(std::uint16_t) noexcept
    {
        return unsupportedL2cap();
    }

    std::uint16_t L2capCoc::serverPsm() const noexcept
    {
        return 0U;
    }

    bool L2capCoc::connect(BLEConnectionHandle, std::uint16_t,
                           BLEL2capChannelHandle &channel) noexcept
    {
        channel = BLEL2capChannelHandle{};
        return unsupportedL2cap();
    }

    bool L2capCoc::send(BLEL2capChannelHandle, const void *, std::size_t) noexcept
    {
        return unsupportedL2cap();
    }

    bool L2capCoc::disconnect(BLEL2capChannelHandle) noexcept
    {
        return unsupportedL2cap();
    }

    bool L2capCoc::connected(BLEL2capChannelHandle) const noexcept
    {
        return false;
    }

    std::size_t L2capCoc::availableForWrite() const noexcept
    {
        return 0U;
    }

    BLEL2capStatistics L2capCoc::statistics() const noexcept
    {
        return {};
    }

    void L2capCoc::onEvent(BLEL2capEventCallback, void *) noexcept
    {
    }

} // namespace nucode::ble

#endif

nucode::ble::L2capCoc BLEL2cap;

#endif
