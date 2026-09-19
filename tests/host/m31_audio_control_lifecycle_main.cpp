/**
 * @file m31_audio_control_lifecycle_main.cpp
 * @brief Audio Control 전용 read와 callback 수명 경쟁을 실행 검증합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <cassert>
#include <cstdint>

namespace
{
    struct Connection
    {
        std::uint32_t references = 1U;
        bool active = true;
    };

    struct ReadParameters
    {
        std::uint32_t operation = 0U;
    };

    struct Backend;

    struct GattStub
    {
        Backend *backend = nullptr;
        ReadParameters *pending = nullptr;
        std::uint32_t cancel_callbacks = 0U;

        bool read(ReadParameters *parameters) noexcept;
        void complete() noexcept;
        void cancel(ReadParameters *parameters) noexcept;
    };

    struct CallbackEpoch
    {
        Backend *backend = nullptr;
        Connection *connection = nullptr;
        std::uint32_t generation = 0U;
        bool held = false;

        void leave() noexcept;
    };

    struct Backend
    {
        GattStub gatt = {};
        Connection connection = {};
        ReadParameters read_parameters = {};
        std::uint32_t generation = 0U;
        std::uint32_t operation_counter = 0U;
        std::uint32_t active_operation = 0U;
        std::uint32_t callbacks_inflight = 0U;
        std::uint32_t notifications = 0U;
        std::uint32_t read_completions = 0U;
        bool owner = false;
        bool retired = false;
        bool sdk_bound = false;
        bool ready = false;
        bool failed = false;

        Backend() noexcept
        {
            gatt.backend = this;
        }

        bool begin() noexcept
        {
            if (owner || (callbacks_inflight != 0U) ||
                (retired && (connection.active || sdk_bound)))
            {
                return false;
            }
            ++generation;
            owner = true;
            retired = false;
            sdk_bound = true;
            ready = false;
            failed = false;
            return true;
        }

        bool startRead() noexcept
        {
            if (!owner || (active_operation != 0U))
            {
                return false;
            }
            ++operation_counter;
            if (operation_counter == 0U)
            {
                ++operation_counter;
            }
            active_operation = operation_counter;
            read_parameters.operation = active_operation;
            return gatt.read(&read_parameters);
        }

        void notification() noexcept
        {
            ++notifications;
        }

        void readComplete(std::uint32_t operation) noexcept
        {
            if (!owner || (operation == 0U) || (operation != active_operation))
            {
                return;
            }
            active_operation = 0U;
            ++read_completions;
            ready = true;
        }

        CallbackEpoch enterCallback() noexcept
        {
            if (!owner)
            {
                return {};
            }
            ++callbacks_inflight;
            ++connection.references;
            return {this, &connection, generation, true};
        }

        bool accepts(const CallbackEpoch &callback) const noexcept
        {
            return callback.held && owner && (callback.generation == generation);
        }

        void timeout() noexcept
        {
            failed = true;
            active_operation = 0U;
            gatt.cancel(&read_parameters);
        }

        void end() noexcept
        {
            const bool cancel_read = active_operation != 0U;
            owner = false;
            retired = true;
            ++generation;
            active_operation = 0U;
            if (cancel_read)
            {
                gatt.cancel(&read_parameters);
            }
            --connection.references;
        }

        void disconnectAndReleaseSdk() noexcept
        {
            connection.active = false;
            sdk_bound = false;
        }
    };

    bool GattStub::read(ReadParameters *parameters) noexcept
    {
        if (pending != nullptr)
        {
            return false;
        }
        pending = parameters;
        return true;
    }

    void GattStub::complete() noexcept
    {
        ReadParameters *completed = pending;
        pending = nullptr;
        if (completed != nullptr)
        {
            backend->readComplete(completed->operation);
        }
    }

    void GattStub::cancel(ReadParameters *parameters) noexcept
    {
        if (pending == parameters)
        {
            pending = nullptr;
            ++cancel_callbacks;
            backend->readComplete(parameters->operation);
        }
    }

    void CallbackEpoch::leave() noexcept
    {
        if (!held)
        {
            return;
        }
        --connection->references;
        --backend->callbacks_inflight;
        held = false;
    }

    /** @brief notification 선행이 전용 read 완료로 처리되지 않는지 검사합니다. */
    void notificationBeforeReadResponse() noexcept
    {
        Backend backend;
        assert(backend.begin());
        assert(backend.startRead());
        backend.notification();
        assert(backend.notifications == 1U);
        assert(backend.read_completions == 0U);
        assert(!backend.ready);
        backend.gatt.complete();
        assert(backend.read_completions == 1U);
        assert(backend.ready);
    }

    /** @brief callback snapshot 직후 end가 connection ref를 조기 해제하지 않는지 검사합니다. */
    void snapshotThenEnd() noexcept
    {
        Backend backend;
        assert(backend.begin());
        CallbackEpoch callback = backend.enterCallback();
        assert(callback.held);
        assert(backend.callbacks_inflight == 1U);
        assert(backend.connection.references == 2U);
        backend.end();
        assert(backend.connection.references == 1U);
        assert(!backend.accepts(callback));
        callback.leave();
        assert(backend.connection.references == 0U);
        assert(backend.callbacks_inflight == 0U);
    }

    /** @brief timeout-end-begin 사이의 cancel drain과 stale epoch 거부를 검사합니다. */
    void timeoutEndBeginLateCallback() noexcept
    {
        Backend backend;
        assert(backend.begin());
        assert(backend.startRead());
        const std::uint32_t old_operation = backend.active_operation;
        backend.timeout();
        assert(backend.gatt.pending == nullptr);
        assert(backend.gatt.cancel_callbacks == 1U);
        assert(backend.read_completions == 0U);

        CallbackEpoch late = backend.enterCallback();
        assert(late.held);
        backend.end();
        assert(!backend.begin());
        assert(!backend.accepts(late));
        late.leave();
        backend.disconnectAndReleaseSdk();
        assert(backend.begin());
        assert(!backend.accepts(late));
        backend.readComplete(old_operation);
        assert(backend.read_completions == 0U);
    }
} // namespace

int main()
{
    notificationBeforeReadResponse();
    snapshotThenEnd();
    timeoutEndBeginLateCallback();
    return 0;
}
