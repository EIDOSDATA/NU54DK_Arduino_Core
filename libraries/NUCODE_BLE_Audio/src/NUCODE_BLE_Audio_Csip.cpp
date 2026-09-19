/**
 * @file NUCODE_BLE_Audio_Csip.cpp
 * @brief Coordinated Set Member와 Coordinator 공개 API의 backend입니다.
 *
 * SPDX-License-Identifier: MIT
 */

#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE)

#include <NUCODE_BLE.h>
#include <NUCODE_BLE_Audio.h>
#include <internal/NUCODE_BLE_Internal.h>

#include <zephyr/bluetooth/audio/csip.h>
#include <zephyr/sys/atomic.h>
#include <zephyr/sys/util.h>

#include <errno.h>
#include <string.h>

namespace nucode::ble::audio
{
    namespace
    {
        /** @brief 음수 errno를 안정된 공개 오류로 변환합니다. */
        Error publicError(int error) noexcept
        {
            if (error == 0)
            {
                return Error::none;
            }
            if (error == -EINVAL || error == -ERANGE || error == -EACCES)
            {
                return Error::invalid_argument;
            }
            if (error == -EALREADY || error == -EEXIST)
            {
                return Error::already_started;
            }
            if (error == -EBUSY || error == -EINPROGRESS)
            {
                return Error::busy;
            }
            if (error == -ENOTCONN)
            {
                return Error::not_connected;
            }
            if (error == -ENOTSUP)
            {
                return Error::unsupported;
            }
            return Error::stack_error;
        }

#if defined(CONFIG_BT_CSIP_SET_MEMBER)
        /** @brief 한 image의 단일 CSIS Member service 상태입니다. */
        struct MemberContext
        {
            const CsipSetMember *owner = nullptr;
            struct bt_csip_set_member_svc_inst *instance = nullptr;
            bt_addr_le_t authorized_identity = {};
            std::uint8_t authorized_local_id = 0U;
            Error last_error = Error::not_started;
            int native_code = 0;
            atomic_t locked = ATOMIC_INIT(0);
            atomic_t lock_changes = ATOMIC_INIT(0);
            bool identity_authorized = false;
            bool transitioning = false;
            struct k_spinlock lock;
        };

        MemberContext member_context;

        /** @brief peer 또는 local timeout의 실제 잠금 변경을 보존합니다. */
        void memberLockChanged(struct bt_conn *connection,
                               struct bt_csip_set_member_svc_inst *instance,
                               bool locked) noexcept
        {
            ARG_UNUSED(connection);
            k_spinlock_key_t key = k_spin_lock(&member_context.lock);
            if (member_context.owner == nullptr || member_context.instance != instance ||
                member_context.transitioning)
            {
                k_spin_unlock(&member_context.lock, key);
                return;
            }
            atomic_set(&member_context.locked, locked ? 1 : 0);
            atomic_inc(&member_context.lock_changes);
            k_spin_unlock(&member_context.lock, key);
        }

        /** @brief 명시적으로 승인한 bonded identity에만 encrypted SIRK 읽기를 허용합니다. */
        std::uint8_t memberSirkReadRequested(
            struct bt_conn *connection,
            struct bt_csip_set_member_svc_inst *instance) noexcept
        {
            bt_addr_le_t authorized_identity = {};
            std::uint8_t authorized_local_id = 0U;
            bool authorized = false;
            k_spinlock_key_t key = k_spin_lock(&member_context.lock);
            if (connection != nullptr && member_context.owner != nullptr &&
                member_context.instance == instance && !member_context.transitioning &&
                member_context.identity_authorized)
            {
                authorized_identity = member_context.authorized_identity;
                authorized_local_id = member_context.authorized_local_id;
                authorized = true;
            }
            k_spin_unlock(&member_context.lock, key);
            if (!authorized || bt_conn_get_security(connection) < BT_SECURITY_L2)
            {
                return BT_CSIP_READ_SIRK_REQ_RSP_REJECT;
            }
            struct bt_conn_info information = {};
            if (bt_conn_get_info(connection, &information) != 0 ||
                information.type != BT_CONN_TYPE_LE || information.le.dst == nullptr ||
                information.id != authorized_local_id ||
                !bt_addr_le_eq(information.le.dst, &authorized_identity) ||
                !bt_le_bond_exists(information.id, information.le.dst))
            {
                return BT_CSIP_READ_SIRK_REQ_RSP_REJECT;
            }
            return BT_CSIP_READ_SIRK_REQ_RSP_ACCEPT_ENC;
        }

        struct bt_csip_set_member_cb member_callbacks = {
            .lock_changed = memberLockChanged,
            .sirk_read_req = memberSirkReadRequested,
        };

        /** @brief owner와 안정된 service instance를 lifecycle lock 아래에서 확인합니다. */
        struct bt_csip_set_member_svc_inst *memberInstance(
            const CsipSetMember *owner) noexcept
        {
            struct bt_csip_set_member_svc_inst *instance = nullptr;
            k_spinlock_key_t key = k_spin_lock(&member_context.lock);
            if (member_context.owner == owner && !member_context.transitioning)
            {
                instance = member_context.instance;
            }
            k_spin_unlock(&member_context.lock, key);
            return instance;
        }

        /** @brief native 결과가 같은 owner·instance 수명에 속할 때만 상태에 반영합니다. */
        void recordMemberResult(const CsipSetMember *owner,
                                struct bt_csip_set_member_svc_inst *instance,
                                int result) noexcept
        {
            k_spinlock_key_t key = k_spin_lock(&member_context.lock);
            if (member_context.owner == owner && member_context.instance == instance &&
                !member_context.transitioning)
            {
                member_context.last_error = publicError(result);
                member_context.native_code = result;
            }
            k_spin_unlock(&member_context.lock, key);
        }
#endif

#if defined(CONFIG_BT_CSIP_SET_COORDINATOR)
        /** @brief 한 remote CSIS instance와 exact public handle의 결합입니다. */
        struct CoordinatorMember
        {
            BLEConnectionHandle connection;
            const struct bt_csip_set_coordinator_set_member *member = nullptr;
            const struct bt_csip_set_coordinator_csis_inst *instance = nullptr;
            CsipMemberInfo information;
        };

        /** @brief callback context가 없는 SDK 절차를 session·exact peer snapshot에 결합합니다. */
        struct CoordinatorOperation
        {
            std::uint32_t identity = 0U;
            std::uint32_t session = 0U;
            CsipStep step = CsipStep::none;
            BLEConnectionHandle connections[CsipSetCoordinator::maximum_members] = {};
            const struct bt_csip_set_coordinator_set_member
                *members[CsipSetCoordinator::maximum_members] = {};
            const struct bt_csip_set_coordinator_csis_inst
                *instances[CsipSetCoordinator::maximum_members] = {};
            const struct bt_csip_set_coordinator_set_info *set_info = nullptr;
            std::uint8_t count = 0U;
            bool active = false;
            bool valid = false;
        };

        /** @brief callback 등록은 image 수명 한 번, 공개 owner는 한 번에 하나입니다. */
        struct CoordinatorContext
        {
            const CsipSetCoordinator *owner = nullptr;
            CsipSetKey key;
            std::uint8_t expected_members = 0U;
            std::uint8_t member_count = 0U;
            CoordinatorMember members[CsipSetCoordinator::maximum_members] = {};
            BLEConnectionHandle ordered[CsipSetCoordinator::maximum_members] = {};
            BLEConnectionHandle pending_connection;
            CsipStage stage = CsipStage::idle;
            CsipStep last_step = CsipStep::none;
            Error last_error = Error::not_started;
            int native_code = 0;
            std::uint32_t lock_changes = 0U;
            bool callbacks_registered = false;
            bool locked = false;
            std::uint32_t session = 0U;
            std::uint32_t next_session = 1U;
            std::uint32_t next_operation_identity = 1U;
            CoordinatorOperation operation;
            struct k_spinlock lock;
        };

        CoordinatorContext coordinator_context;

        /** @brief spinlock 자체를 유지하며 공개 coordinator session만 초기화합니다. */
        void resetCoordinatorSessionLocked() noexcept
        {
            coordinator_context.owner = nullptr;
            coordinator_context.key = {};
            coordinator_context.expected_members = 0U;
            coordinator_context.member_count = 0U;
            for (std::size_t index = 0U; index < CsipSetCoordinator::maximum_members; ++index)
            {
                coordinator_context.members[index] = {};
                coordinator_context.ordered[index] = BLEConnectionHandle{};
            }
            coordinator_context.pending_connection = BLEConnectionHandle{};
            coordinator_context.stage = CsipStage::idle;
            coordinator_context.last_step = CsipStep::none;
            coordinator_context.last_error = Error::not_started;
            coordinator_context.native_code = 0;
            coordinator_context.lock_changes = 0U;
            coordinator_context.locked = false;
            coordinator_context.session = 0U;
        }

        /** @brief 0을 건너뛰는 coordinator session 번호를 발급합니다. */
        std::uint32_t nextCoordinatorSessionLocked() noexcept
        {
            std::uint32_t session = coordinator_context.next_session++;
            if (session == 0U)
            {
                session = coordinator_context.next_session++;
            }
            return session;
        }

        /** @brief 현재 member snapshot으로 callback 없는 SDK operation을 시작합니다. */
        bool startCoordinatorOperationLocked(CsipStep step) noexcept
        {
            if (coordinator_context.operation.active)
            {
                return false;
            }
            CoordinatorOperation operation = {};
            operation.identity = coordinator_context.next_operation_identity++;
            if (operation.identity == 0U)
            {
                operation.identity = coordinator_context.next_operation_identity++;
            }
            operation.session = coordinator_context.session;
            operation.step = step;
            operation.count = coordinator_context.member_count;
            operation.active = true;
            operation.valid = true;
            for (std::size_t index = 0U; index < operation.count; ++index)
            {
                operation.connections[index] = coordinator_context.members[index].connection;
                operation.members[index] = coordinator_context.members[index].member;
                operation.instances[index] = coordinator_context.members[index].instance;
            }
            if (operation.count != 0U)
            {
                operation.set_info = &coordinator_context.members[0].instance->info;
            }
            coordinator_context.operation = operation;
            return true;
        }

        /** @brief pending operation을 무효화하되 늦은 callback을 소비할 때까지 보존합니다. */
        void invalidateCoordinatorOperationLocked() noexcept
        {
            if (coordinator_context.operation.active)
            {
                coordinator_context.operation.valid = false;
            }
        }

        /** @brief expected callback의 session·step·exact member snapshot을 검증하고 소비합니다. */
        bool consumeCoordinatorOperation(CsipStep step,
                                         CoordinatorOperation &operation) noexcept
        {
            k_spinlock_key_t key = k_spin_lock(&coordinator_context.lock);
            if (!coordinator_context.operation.active ||
                coordinator_context.operation.step != step)
            {
                k_spin_unlock(&coordinator_context.lock, key);
                return false;
            }
            operation = coordinator_context.operation;
            coordinator_context.operation.active = false;
            coordinator_context.operation.valid = false;
            bool current = operation.valid && coordinator_context.owner != nullptr &&
                           operation.session == coordinator_context.session &&
                           operation.count == coordinator_context.member_count;
            for (std::size_t index = 0U; current && index < operation.count; ++index)
            {
                current = coordinator_context.members[index].connection ==
                              operation.connections[index] &&
                          coordinator_context.members[index].member == operation.members[index] &&
                          coordinator_context.members[index].instance ==
                              operation.instances[index];
            }
            k_spin_unlock(&coordinator_context.lock, key);
            for (std::size_t index = 0U; current && index < operation.count; ++index)
            {
                current = BLEConnection.connected(operation.connections[index]);
            }
            return current;
        }

        /** @brief 동기 시작 실패에는 callback이 없으므로 operation token을 즉시 폐기합니다. */
        void cancelCoordinatorOperation(std::uint32_t identity) noexcept
        {
            k_spinlock_key_t key = k_spin_lock(&coordinator_context.lock);
            if (coordinator_context.operation.active &&
                coordinator_context.operation.identity == identity)
            {
                coordinator_context.operation = {};
            }
            k_spin_unlock(&coordinator_context.lock, key);
        }

        /** @brief connection을 pending exact handle과 대조해 CSIS 검색 결과를 저장합니다. */
        void coordinatorDiscovered(
            struct bt_conn *connection,
            const struct bt_csip_set_coordinator_set_member *member,
            int error,
            std::size_t set_count) noexcept
        {
            const BLEConnectionHandle handle = internal::handleForActiveConnection(connection);
            k_spinlock_key_t key = k_spin_lock(&coordinator_context.lock);
            if (!coordinator_context.operation.active ||
                coordinator_context.operation.step != CsipStep::discover)
            {
                k_spin_unlock(&coordinator_context.lock, key);
                return;
            }
            const CoordinatorOperation operation = coordinator_context.operation;
            coordinator_context.operation.active = false;
            coordinator_context.operation.valid = false;
            if (!operation.valid || coordinator_context.owner == nullptr ||
                operation.session != coordinator_context.session ||
                handle != coordinator_context.pending_connection ||
                handle != operation.connections[0])
            {
                k_spin_unlock(&coordinator_context.lock, key);
                return;
            }
            coordinator_context.pending_connection = BLEConnectionHandle{};
            if (error != 0 || member == nullptr || set_count == 0U)
            {
                coordinator_context.last_error = publicError(error == 0 ? -ENOENT : error);
                coordinator_context.native_code = error == 0 ? -ENOENT : error;
                coordinator_context.stage = CsipStage::failed;
                k_spin_unlock(&coordinator_context.lock, key);
                return;
            }

            const struct bt_csip_set_coordinator_csis_inst *instance = nullptr;
            for (std::size_t index = 0U; index < set_count; ++index)
            {
                if (::memcmp(member->insts[index].info.sirk,
                             coordinator_context.key.bytes,
                             sizeof(coordinator_context.key.bytes)) == 0)
                {
                    instance = &member->insts[index];
                    break;
                }
            }
            if (instance == nullptr || !instance->info.lockable || instance->info.rank == 0U ||
                instance->info.rank > coordinator_context.expected_members ||
                instance->info.set_size != coordinator_context.expected_members)
            {
                coordinator_context.last_error = Error::invalid_argument;
                coordinator_context.native_code = -EACCES;
                coordinator_context.stage = CsipStage::failed;
                k_spin_unlock(&coordinator_context.lock, key);
                return;
            }
            for (std::size_t index = 0U; index < coordinator_context.member_count; ++index)
            {
                if (coordinator_context.members[index].information.rank == instance->info.rank)
                {
                    coordinator_context.last_error = Error::invalid_argument;
                    coordinator_context.native_code = -EEXIST;
                    coordinator_context.stage = CsipStage::failed;
                    k_spin_unlock(&coordinator_context.lock, key);
                    return;
                }
            }

            CoordinatorMember &slot =
                coordinator_context.members[coordinator_context.member_count++];
            slot.connection = handle;
            slot.member = member;
            slot.instance = instance;
            slot.information = {
                .set_size = instance->info.set_size,
                .rank = instance->info.rank,
                .lockable = instance->info.lockable,
                .locked = false,
            };
            coordinator_context.last_error = Error::none;
            coordinator_context.native_code = 0;
            coordinator_context.stage =
                coordinator_context.member_count == coordinator_context.expected_members
                    ? CsipStage::ready
                    : CsipStage::discovering;
            k_spin_unlock(&coordinator_context.lock, key);
        }

        /** @brief lock procedure 완료를 공개 상태로 변환합니다. */
        void coordinatorLocked(int error) noexcept
        {
            CoordinatorOperation operation;
            if (!consumeCoordinatorOperation(CsipStep::lock, operation))
            {
                return;
            }
            if (error != 0)
            {
                k_spinlock_key_t error_key = k_spin_lock(&coordinator_context.lock);
                if (coordinator_context.owner != nullptr &&
                    coordinator_context.session == operation.session)
                {
                    coordinator_context.last_error = publicError(error);
                    coordinator_context.native_code = error;
                    coordinator_context.stage = CsipStage::failed;
                }
                k_spin_unlock(&coordinator_context.lock, error_key);
                return;
            }
            k_spinlock_key_t key = k_spin_lock(&coordinator_context.lock);
            if (coordinator_context.owner != nullptr &&
                coordinator_context.session == operation.session)
            {
                coordinator_context.locked = true;
                coordinator_context.last_error = Error::none;
                coordinator_context.native_code = 0;
                coordinator_context.stage = CsipStage::locked;
                for (std::size_t index = 0U; index < coordinator_context.member_count; ++index)
                {
                    coordinator_context.members[index].information.locked = true;
                }
            }
            k_spin_unlock(&coordinator_context.lock, key);
        }

        /** @brief release procedure 완료를 공개 상태로 변환합니다. */
        void coordinatorReleased(int error) noexcept
        {
            CoordinatorOperation operation;
            if (!consumeCoordinatorOperation(CsipStep::release, operation))
            {
                return;
            }
            if (error != 0)
            {
                k_spinlock_key_t error_key = k_spin_lock(&coordinator_context.lock);
                if (coordinator_context.owner != nullptr &&
                    coordinator_context.session == operation.session)
                {
                    coordinator_context.last_error = publicError(error);
                    coordinator_context.native_code = error;
                    coordinator_context.stage = CsipStage::failed;
                }
                k_spin_unlock(&coordinator_context.lock, error_key);
                return;
            }
            k_spinlock_key_t key = k_spin_lock(&coordinator_context.lock);
            if (coordinator_context.owner != nullptr &&
                coordinator_context.session == operation.session)
            {
                coordinator_context.locked = false;
                coordinator_context.last_error = Error::none;
                coordinator_context.native_code = 0;
                coordinator_context.stage = CsipStage::ready;
                for (std::size_t index = 0U; index < coordinator_context.member_count; ++index)
                {
                    coordinator_context.members[index].information.locked = false;
                }
            }
            k_spin_unlock(&coordinator_context.lock, key);
        }

        /** @brief peer notification으로 들어온 한 instance의 잠금 상태를 갱신합니다. */
        void coordinatorLockChanged(struct bt_csip_set_coordinator_csis_inst *instance,
                                    bool locked) noexcept
        {
            k_spinlock_key_t key = k_spin_lock(&coordinator_context.lock);
            bool found = false;
            for (std::size_t index = 0U; index < coordinator_context.member_count; ++index)
            {
                if (coordinator_context.owner != nullptr &&
                    coordinator_context.members[index].instance == instance)
                {
                    coordinator_context.members[index].information.locked = locked;
                    ++coordinator_context.lock_changes;
                    found = true;
                    break;
                }
            }
            if (found)
            {
                bool aggregate_locked = coordinator_context.member_count ==
                                        coordinator_context.expected_members;
                for (std::size_t index = 0U;
                     aggregate_locked && index < coordinator_context.member_count; ++index)
                {
                    aggregate_locked = coordinator_context.members[index].information.locked;
                }
                coordinator_context.locked = aggregate_locked;
                if (coordinator_context.stage != CsipStage::operating)
                {
                    coordinator_context.stage =
                        aggregate_locked ? CsipStage::locked
                                         : (coordinator_context.member_count ==
                                                    coordinator_context.expected_members
                                                ? CsipStage::ready
                                                : CsipStage::discovering);
                }
            }
            k_spin_unlock(&coordinator_context.lock, key);
        }

        /** @brief 변경된 exact member를 제거하고 기존 순서·aggregate lock을 무효화합니다. */
        void invalidateCoordinatorMember(
            const struct bt_csip_set_coordinator_csis_inst *instance,
            BLEConnectionHandle connection, int error) noexcept
        {
            k_spinlock_key_t key = k_spin_lock(&coordinator_context.lock);
            if (coordinator_context.owner == nullptr)
            {
                k_spin_unlock(&coordinator_context.lock, key);
                return;
            }
            std::size_t remove_index = coordinator_context.member_count;
            for (std::size_t index = 0U; index < coordinator_context.member_count; ++index)
            {
                const CoordinatorMember &candidate = coordinator_context.members[index];
                if (candidate.instance == instance &&
                    (!connection.valid() || candidate.connection == connection))
                {
                    remove_index = index;
                    break;
                }
            }
            if (remove_index == coordinator_context.member_count)
            {
                k_spin_unlock(&coordinator_context.lock, key);
                return;
            }
            for (std::size_t index = remove_index + 1U;
                 index < coordinator_context.member_count; ++index)
            {
                coordinator_context.members[index - 1U] = coordinator_context.members[index];
            }
            coordinator_context.members[--coordinator_context.member_count] = {};
            for (std::size_t index = 0U; index < CsipSetCoordinator::maximum_members; ++index)
            {
                coordinator_context.ordered[index] = BLEConnectionHandle{};
            }
            coordinator_context.locked = false;
            invalidateCoordinatorOperationLocked();
            coordinator_context.last_error = publicError(error);
            coordinator_context.native_code = error;
            coordinator_context.stage = CsipStage::discovering;
            coordinator_context.last_step = CsipStep::cleanup;
            k_spin_unlock(&coordinator_context.lock, key);
        }

        /** @brief SIRK 변경은 기존 set identity를 무효화하므로 재검색을 요구합니다. */
        void coordinatorSirkChanged(struct bt_csip_set_coordinator_csis_inst *instance) noexcept
        {
            invalidateCoordinatorMember(instance, BLEConnectionHandle{}, -EACCES);
        }

        /** @brief set size 변경은 rank 일관성을 잃으므로 재검색을 요구합니다. */
        void coordinatorSizeChanged(
            struct bt_conn *connection,
            const struct bt_csip_set_coordinator_csis_inst *instance) noexcept
        {
            invalidateCoordinatorMember(instance, internal::handleForActiveConnection(connection),
                                        -ERANGE);
        }

        /** @brief ordered access의 최종 GATT 결과를 반영합니다. */
        void coordinatorOrderedAccessComplete(
            const struct bt_csip_set_coordinator_set_info *set_info,
            int error,
            bool locked,
            struct bt_csip_set_coordinator_set_member *member) noexcept
        {
            CoordinatorOperation operation;
            if (!consumeCoordinatorOperation(CsipStep::ordered_access, operation) ||
                set_info != operation.set_info)
            {
                return;
            }
            if (member != nullptr)
            {
                bool exact_member = false;
                for (std::size_t index = 0U; index < operation.count; ++index)
                {
                    exact_member = exact_member || operation.members[index] == member;
                }
                if (!exact_member)
                {
                    return;
                }
            }
            if (error != 0 || locked)
            {
                const int operation_error = error == 0 ? -EBUSY : error;
                k_spinlock_key_t error_key = k_spin_lock(&coordinator_context.lock);
                if (coordinator_context.owner != nullptr &&
                    coordinator_context.session == operation.session)
                {
                    coordinator_context.last_error = publicError(operation_error);
                    coordinator_context.native_code = operation_error;
                    coordinator_context.stage = CsipStage::failed;
                }
                k_spin_unlock(&coordinator_context.lock, error_key);
                return;
            }
            k_spinlock_key_t key = k_spin_lock(&coordinator_context.lock);
            if (coordinator_context.owner != nullptr &&
                coordinator_context.session == operation.session)
            {
                coordinator_context.last_error = Error::none;
                coordinator_context.native_code = 0;
                coordinator_context.stage = CsipStage::ready;
            }
            k_spin_unlock(&coordinator_context.lock, key);
        }

        /** @brief SDK가 제공한 rank 순서를 exact public handle 배열로 복사합니다. */
        bool coordinatorOrderedAccess(
            const struct bt_csip_set_coordinator_set_info *set_info,
            struct bt_csip_set_coordinator_set_member *members[],
            std::size_t count) noexcept
        {
            k_spinlock_key_t key = k_spin_lock(&coordinator_context.lock);
            if (coordinator_context.owner == nullptr ||
                !coordinator_context.operation.active ||
                !coordinator_context.operation.valid ||
                coordinator_context.operation.step != CsipStep::ordered_access ||
                coordinator_context.operation.session != coordinator_context.session ||
                set_info != coordinator_context.operation.set_info ||
                count != coordinator_context.operation.count ||
                count != coordinator_context.member_count)
            {
                k_spin_unlock(&coordinator_context.lock, key);
                return false;
            }
            for (std::size_t ordered_index = 0U; ordered_index < count; ++ordered_index)
            {
                bool found = false;
                for (std::size_t index = 0U; index < coordinator_context.member_count; ++index)
                {
                    if (coordinator_context.members[index].member ==
                            coordinator_context.operation.members[index] &&
                        coordinator_context.members[index].member == members[ordered_index])
                    {
                        coordinator_context.ordered[ordered_index] =
                            coordinator_context.members[index].connection;
                        found = true;
                        break;
                    }
                }
                if (!found)
                {
                    k_spin_unlock(&coordinator_context.lock, key);
                    return false;
                }
            }
            k_spin_unlock(&coordinator_context.lock, key);
            return true;
        }

        struct bt_csip_set_coordinator_cb coordinator_callbacks = {
            .discover = coordinatorDiscovered,
            .lock_set = coordinatorLocked,
            .release_set = coordinatorReleased,
            .lock_changed = coordinatorLockChanged,
            .sirk_changed = coordinatorSirkChanged,
            .size_changed = coordinatorSizeChanged,
            .ordered_access = coordinatorOrderedAccessComplete,
        };
#endif
    } // namespace

    Error CsipSetMember::begin(const CsipMemberConfig &configuration) noexcept
    {
#if defined(CONFIG_BT_CSIP_SET_MEMBER)
        if (!internal::requireThreadContext())
        {
            return Error::stack_error;
        }
        if (configuration.set_size == 0U || configuration.rank == 0U ||
            configuration.rank > configuration.set_size)
        {
            return Error::invalid_argument;
        }
        if (!internal::stackReady())
        {
            return Error::not_ready;
        }
        k_spinlock_key_t context_key = k_spin_lock(&member_context.lock);
        if (member_context.owner != nullptr)
        {
            const Error error = member_context.owner == this ? Error::already_started : Error::busy;
            k_spin_unlock(&member_context.lock, context_key);
            return error;
        }
        member_context.owner = this;
        member_context.transitioning = true;
        member_context.identity_authorized = false;
        k_spin_unlock(&member_context.lock, context_key);
        struct bt_csip_set_member_register_param parameters = {
            .set_size = configuration.set_size,
            .lockable = configuration.lockable,
            .rank = configuration.rank,
            .cb = &member_callbacks,
        };
        ::memcpy(parameters.sirk, configuration.key.bytes, sizeof(parameters.sirk));
        struct bt_csip_set_member_svc_inst *registered_instance = nullptr;
        const int result = bt_csip_set_member_register(&parameters, &registered_instance);
        context_key = k_spin_lock(&member_context.lock);
        member_context.last_error = publicError(result);
        member_context.native_code = result;
        if (result == 0)
        {
            member_context.instance = registered_instance;
            member_context.transitioning = false;
            atomic_set(&member_context.locked, 0);
            atomic_set(&member_context.lock_changes, 0);
        }
        else
        {
            member_context.owner = nullptr;
            member_context.instance = nullptr;
            member_context.transitioning = false;
        }
        const Error public_result = member_context.last_error;
        k_spin_unlock(&member_context.lock, context_key);
        return public_result;
#else
        ARG_UNUSED(configuration);
        return Error::unsupported;
#endif
    }

    Error CsipSetMember::end() noexcept
    {
#if defined(CONFIG_BT_CSIP_SET_MEMBER)
        k_spinlock_key_t context_key = k_spin_lock(&member_context.lock);
        if (member_context.owner == nullptr)
        {
            k_spin_unlock(&member_context.lock, context_key);
            return Error::none;
        }
        if (member_context.owner != this || member_context.transitioning)
        {
            k_spin_unlock(&member_context.lock, context_key);
            return Error::busy;
        }
        struct bt_csip_set_member_svc_inst *const instance = member_context.instance;
        member_context.transitioning = true;
        k_spin_unlock(&member_context.lock, context_key);
        const int result = bt_csip_set_member_unregister(instance);
        context_key = k_spin_lock(&member_context.lock);
        member_context.last_error = publicError(result);
        member_context.native_code = result;
        if (member_context.owner == this && member_context.instance == instance)
        {
            if (result == 0)
            {
                member_context.owner = nullptr;
                member_context.instance = nullptr;
                member_context.identity_authorized = false;
                member_context.authorized_identity = {};
                atomic_set(&member_context.locked, 0);
            }
            member_context.transitioning = false;
        }
        const Error public_result = member_context.last_error;
        k_spin_unlock(&member_context.lock, context_key);
        return public_result;
#else
        return Error::none;
#endif
    }

    Error CsipSetMember::generateRsi(std::uint8_t (&rsi)[6]) noexcept
    {
#if defined(CONFIG_BT_CSIP_SET_MEMBER)
        struct bt_csip_set_member_svc_inst *const instance = memberInstance(this);
        if (instance == nullptr)
        {
            return Error::not_started;
        }
        const int result = bt_csip_set_member_generate_rsi(instance, rsi);
        recordMemberResult(this, instance, result);
        return publicError(result);
#else
        ARG_UNUSED(rsi);
        return Error::unsupported;
#endif
    }

    Error CsipSetMember::authorizeSirkRead(const BLEConnectionHandle &connection,
                                           bool authorized) noexcept
    {
#if defined(CONFIG_BT_CSIP_SET_MEMBER)
        struct bt_conn *native_connection = internal::referenceConnection(connection);
        if (native_connection == nullptr)
        {
            return Error::not_connected;
        }
        struct bt_conn_info information = {};
        const int result = bt_conn_get_info(native_connection, &information);
        const bool valid_identity = result == 0 && information.type == BT_CONN_TYPE_LE &&
                                    information.le.dst != nullptr;
        const bt_addr_le_t identity = valid_identity ? *information.le.dst : bt_addr_le_t{};
        bt_conn_unref(native_connection);
        if (!valid_identity)
        {
            return Error::invalid_argument;
        }
        k_spinlock_key_t key = k_spin_lock(&member_context.lock);
        if (member_context.owner != this || member_context.instance == nullptr ||
            member_context.transitioning)
        {
            k_spin_unlock(&member_context.lock, key);
            return Error::not_started;
        }
        member_context.identity_authorized = authorized;
        member_context.authorized_local_id = authorized ? information.id : 0U;
        member_context.authorized_identity = authorized ? identity : bt_addr_le_t{};
        member_context.last_error = Error::none;
        member_context.native_code = 0;
        k_spin_unlock(&member_context.lock, key);
        return Error::none;
#else
        ARG_UNUSED(connection);
        ARG_UNUSED(authorized);
        return Error::unsupported;
#endif
    }

    Error CsipSetMember::setKey(const CsipSetKey &key) noexcept
    {
#if defined(CONFIG_BT_CSIP_SET_MEMBER)
        struct bt_csip_set_member_svc_inst *const instance = memberInstance(this);
        if (instance == nullptr)
        {
            return Error::not_started;
        }
        const int result = bt_csip_set_member_sirk(instance, key.bytes);
        recordMemberResult(this, instance, result);
        return publicError(result);
#else
        ARG_UNUSED(key);
        return Error::unsupported;
#endif
    }

    Error CsipSetMember::setSizeAndRank(std::uint8_t set_size, std::uint8_t rank) noexcept
    {
#if defined(CONFIG_BT_CSIP_SET_MEMBER)
        struct bt_csip_set_member_svc_inst *const instance = memberInstance(this);
        if (instance == nullptr)
        {
            return Error::not_started;
        }
        if (set_size == 0U || rank == 0U || rank > set_size)
        {
            return Error::invalid_argument;
        }
        const int result =
            bt_csip_set_member_set_size_and_rank(instance, set_size, rank);
        recordMemberResult(this, instance, result);
        return publicError(result);
#else
        ARG_UNUSED(set_size);
        ARG_UNUSED(rank);
        return Error::unsupported;
#endif
    }

    Error CsipSetMember::forceRelease() noexcept
    {
#if defined(CONFIG_BT_CSIP_SET_MEMBER)
        struct bt_csip_set_member_svc_inst *const instance = memberInstance(this);
        if (instance == nullptr)
        {
            return Error::not_started;
        }
        const int result = bt_csip_set_member_lock(instance, false, true);
        recordMemberResult(this, instance, result);
        return publicError(result);
#else
        return Error::unsupported;
#endif
    }

    Error CsipSetMember::info(CsipMemberInfo &information) const noexcept
    {
#if defined(CONFIG_BT_CSIP_SET_MEMBER)
        struct bt_csip_set_member_svc_inst *const instance = memberInstance(this);
        if (instance == nullptr)
        {
            return Error::not_started;
        }
        struct bt_csip_set_member_set_info native_information = {};
        const int result =
            bt_csip_set_member_get_info(instance, &native_information);
        recordMemberResult(this, instance, result);
        if (result == 0)
        {
            information = {
                .set_size = native_information.set_size,
                .rank = native_information.rank,
                .lockable = native_information.lockable,
                .locked = native_information.locked,
            };
        }
        return publicError(result);
#else
        ARG_UNUSED(information);
        return Error::unsupported;
#endif
    }

    bool CsipSetMember::active() const noexcept
    {
#if defined(CONFIG_BT_CSIP_SET_MEMBER)
        k_spinlock_key_t key = k_spin_lock(&member_context.lock);
        const bool active = member_context.owner == this && member_context.instance != nullptr &&
                            !member_context.transitioning;
        k_spin_unlock(&member_context.lock, key);
        return active;
#else
        return false;
#endif
    }

    bool CsipSetMember::locked() const noexcept
    {
#if defined(CONFIG_BT_CSIP_SET_MEMBER)
        k_spinlock_key_t key = k_spin_lock(&member_context.lock);
        const bool locked = member_context.owner == this && !member_context.transitioning &&
                            atomic_get(&member_context.locked) != 0;
        k_spin_unlock(&member_context.lock, key);
        return locked;
#else
        return false;
#endif
    }

    std::uint32_t CsipSetMember::lockChanges() const noexcept
    {
#if defined(CONFIG_BT_CSIP_SET_MEMBER)
        k_spinlock_key_t key = k_spin_lock(&member_context.lock);
        const std::uint32_t changes =
            member_context.owner == this && !member_context.transitioning
                ? static_cast<std::uint32_t>(atomic_get(&member_context.lock_changes))
                : 0U;
        k_spin_unlock(&member_context.lock, key);
        return changes;
#else
        return 0U;
#endif
    }

    Error CsipSetMember::lastError() const noexcept
    {
#if defined(CONFIG_BT_CSIP_SET_MEMBER)
        k_spinlock_key_t key = k_spin_lock(&member_context.lock);
        const Error error = member_context.owner == this ? member_context.last_error
                                                          : Error::not_started;
        k_spin_unlock(&member_context.lock, key);
        return error;
#else
        return Error::unsupported;
#endif
    }

    int CsipSetMember::nativeCode() const noexcept
    {
#if defined(CONFIG_BT_CSIP_SET_MEMBER)
        k_spinlock_key_t key = k_spin_lock(&member_context.lock);
        const int result = member_context.owner == this ? member_context.native_code : -ENOTSUP;
        k_spin_unlock(&member_context.lock, key);
        return result;
#else
        return -ENOTSUP;
#endif
    }

    Error CsipSetCoordinator::begin(const CsipSetKey &key_value,
                                    std::uint8_t expected_members) noexcept
    {
#if defined(CONFIG_BT_CSIP_SET_COORDINATOR)
        if (!internal::requireThreadContext())
        {
            return Error::stack_error;
        }
        if (expected_members == 0U || expected_members > maximum_members)
        {
            return Error::invalid_argument;
        }
        if (!internal::stackReady())
        {
            return Error::not_ready;
        }
        k_spinlock_key_t lock_key = k_spin_lock(&coordinator_context.lock);
        if (coordinator_context.owner != nullptr)
        {
            const Error result = coordinator_context.owner == this ? Error::already_started
                                                                    : Error::busy;
            k_spin_unlock(&coordinator_context.lock, lock_key);
            return result;
        }
        const bool register_callbacks = !coordinator_context.callbacks_registered;
        k_spin_unlock(&coordinator_context.lock, lock_key);
        if (register_callbacks)
        {
            const int result = bt_csip_set_coordinator_register_cb(&coordinator_callbacks);
            if (result != 0)
            {
                return publicError(result);
            }
        }
        lock_key = k_spin_lock(&coordinator_context.lock);
        resetCoordinatorSessionLocked();
        coordinator_context.owner = this;
        coordinator_context.session = nextCoordinatorSessionLocked();
        coordinator_context.key = key_value;
        coordinator_context.expected_members = expected_members;
        coordinator_context.callbacks_registered = true;
        coordinator_context.stage = CsipStage::discovering;
        coordinator_context.last_error = Error::none;
        k_spin_unlock(&coordinator_context.lock, lock_key);
        return Error::none;
#else
        ARG_UNUSED(key_value);
        ARG_UNUSED(expected_members);
        return Error::unsupported;
#endif
    }

    Error CsipSetCoordinator::end() noexcept
    {
#if defined(CONFIG_BT_CSIP_SET_COORDINATOR)
        k_spinlock_key_t key = k_spin_lock(&coordinator_context.lock);
        if (coordinator_context.owner == nullptr)
        {
            k_spin_unlock(&coordinator_context.lock, key);
            return Error::none;
        }
        if (coordinator_context.owner != this ||
            coordinator_context.stage == CsipStage::operating)
        {
            k_spin_unlock(&coordinator_context.lock, key);
            return Error::busy;
        }
        invalidateCoordinatorOperationLocked();
        resetCoordinatorSessionLocked();
        k_spin_unlock(&coordinator_context.lock, key);
        return Error::none;
#else
        return Error::none;
#endif
    }

    bool CsipSetCoordinator::matches(const BLEScanResult &result) const noexcept
    {
#if defined(CONFIG_BT_CSIP_SET_COORDINATOR)
        CsipSetKey key_value;
        k_spinlock_key_t key = k_spin_lock(&coordinator_context.lock);
        if (coordinator_context.owner != this)
        {
            k_spin_unlock(&coordinator_context.lock, key);
            return false;
        }
        key_value = coordinator_context.key;
        k_spin_unlock(&coordinator_context.lock, key);
        std::size_t offset = 0U;
        while (offset < result.payload_length)
        {
            const std::size_t field_length = result.payload[offset];
            if (field_length == 0U || offset + field_length + 1U > result.payload_length)
            {
                return false;
            }
            if (result.payload[offset + 1U] == BT_DATA_CSIS_RSI &&
                field_length == BT_CSIP_RSI_SIZE + 1U)
            {
                struct bt_data data = {
                    .type = BT_DATA_CSIS_RSI,
                    .data_len = BT_CSIP_RSI_SIZE,
                    .data = &result.payload[offset + 2U],
                };
                return bt_csip_set_coordinator_is_set_member(key_value.bytes, &data);
            }
            offset += field_length + 1U;
        }
        return false;
#else
        ARG_UNUSED(result);
        return false;
#endif
    }

    Error CsipSetCoordinator::discover(const BLEConnectionHandle &connection) noexcept
    {
#if defined(CONFIG_BT_CSIP_SET_COORDINATOR)
        struct bt_conn *native_connection = internal::referenceConnection(connection);
        if (native_connection == nullptr)
        {
            return Error::not_connected;
        }
        k_spinlock_key_t key = k_spin_lock(&coordinator_context.lock);
        if (coordinator_context.owner != this || coordinator_context.pending_connection.valid() ||
            coordinator_context.operation.active ||
            coordinator_context.stage == CsipStage::operating ||
            coordinator_context.member_count >= coordinator_context.expected_members)
        {
            const Error result = coordinator_context.owner != this ? Error::not_started
                                                                    : Error::busy;
            k_spin_unlock(&coordinator_context.lock, key);
            bt_conn_unref(native_connection);
            return result;
        }
        for (std::size_t index = 0U; index < coordinator_context.member_count; ++index)
        {
            if (coordinator_context.members[index].connection == connection)
            {
                k_spin_unlock(&coordinator_context.lock, key);
                bt_conn_unref(native_connection);
                return Error::already_started;
            }
        }
        coordinator_context.pending_connection = connection;
        coordinator_context.stage = CsipStage::discovering;
        coordinator_context.last_step = CsipStep::discover;
        if (!startCoordinatorOperationLocked(CsipStep::discover))
        {
            coordinator_context.pending_connection = BLEConnectionHandle{};
            k_spin_unlock(&coordinator_context.lock, key);
            bt_conn_unref(native_connection);
            return Error::busy;
        }
        coordinator_context.operation.connections[0] = connection;
        const std::uint32_t operation_identity = coordinator_context.operation.identity;
        k_spin_unlock(&coordinator_context.lock, key);

        const int result = bt_csip_set_coordinator_discover(native_connection);
        bt_conn_unref(native_connection);
        if (result != 0)
        {
            key = k_spin_lock(&coordinator_context.lock);
            if (coordinator_context.operation.active &&
                coordinator_context.operation.identity == operation_identity)
            {
                coordinator_context.operation = {};
                coordinator_context.pending_connection = BLEConnectionHandle{};
                coordinator_context.last_error = publicError(result);
                coordinator_context.native_code = result;
                coordinator_context.stage = CsipStage::failed;
            }
            k_spin_unlock(&coordinator_context.lock, key);
        }
        return publicError(result);
#else
        ARG_UNUSED(connection);
        return Error::unsupported;
#endif
    }

    void CsipSetCoordinator::poll() noexcept
    {
#if defined(CONFIG_BT_CSIP_SET_COORDINATOR)
        CoordinatorMember snapshot[maximum_members] = {};
        BLEConnectionHandle pending_connection;
        std::size_t count = 0U;
        bool release_remaining = false;
        k_spinlock_key_t key = k_spin_lock(&coordinator_context.lock);
        if (coordinator_context.owner == this)
        {
            count = coordinator_context.member_count;
            pending_connection = coordinator_context.pending_connection;
            for (std::size_t index = 0U; index < count; ++index)
            {
                snapshot[index] = coordinator_context.members[index];
            }
        }
        k_spin_unlock(&coordinator_context.lock, key);
        if (pending_connection.valid() && !BLEConnection.connected(pending_connection))
        {
            key = k_spin_lock(&coordinator_context.lock);
            if (coordinator_context.owner == this &&
                coordinator_context.pending_connection == pending_connection)
            {
                coordinator_context.pending_connection = BLEConnectionHandle{};
                invalidateCoordinatorOperationLocked();
                coordinator_context.last_error = Error::not_connected;
                coordinator_context.native_code = -ENOTCONN;
                coordinator_context.stage = CsipStage::discovering;
                coordinator_context.last_step = CsipStep::cleanup;
            }
            k_spin_unlock(&coordinator_context.lock, key);
        }
        for (std::size_t index = count; index > 0U; --index)
        {
            if (!BLEConnection.connected(snapshot[index - 1U].connection))
            {
                key = k_spin_lock(&coordinator_context.lock);
                if (coordinator_context.owner == this &&
                    index <= coordinator_context.member_count &&
                    coordinator_context.members[index - 1U].connection ==
                        snapshot[index - 1U].connection)
                {
                    for (std::size_t move = index; move < coordinator_context.member_count; ++move)
                    {
                        coordinator_context.members[move - 1U] =
                            coordinator_context.members[move];
                    }
                    coordinator_context.members[--coordinator_context.member_count] = {};
                    for (std::size_t ordered_index = 0U; ordered_index < maximum_members;
                         ++ordered_index)
                    {
                        coordinator_context.ordered[ordered_index] = BLEConnectionHandle{};
                    }
                    release_remaining = release_remaining || coordinator_context.locked;
                    coordinator_context.locked = false;
                    invalidateCoordinatorOperationLocked();
                    coordinator_context.last_error = Error::not_connected;
                    coordinator_context.native_code = -ENOTCONN;
                    coordinator_context.stage = CsipStage::discovering;
                    coordinator_context.last_step = CsipStep::cleanup;
                }
                k_spin_unlock(&coordinator_context.lock, key);
            }
        }
        if (release_remaining && memberCount() != 0U)
        {
            (void)release();
        }
#endif
    }

    Error CsipSetCoordinator::prepareOrderedAccess() noexcept
    {
#if defined(CONFIG_BT_CSIP_SET_COORDINATOR)
        poll();
        const struct bt_csip_set_coordinator_set_member *members[maximum_members] = {};
        const struct bt_csip_set_coordinator_set_info *set_info = nullptr;
        std::uint8_t count = 0U;
        std::uint32_t operation_identity = 0U;
        k_spinlock_key_t key = k_spin_lock(&coordinator_context.lock);
        if (coordinator_context.owner != this ||
            coordinator_context.member_count != coordinator_context.expected_members ||
            coordinator_context.stage == CsipStage::operating ||
            coordinator_context.operation.active)
        {
            const Error result = coordinator_context.owner != this ? Error::not_started
                                                                    : Error::not_ready;
            k_spin_unlock(&coordinator_context.lock, key);
            return result;
        }
        count = coordinator_context.member_count;
        for (std::size_t index = 0U; index < count; ++index)
        {
            members[index] = coordinator_context.members[index].member;
            coordinator_context.ordered[index] = BLEConnectionHandle{};
        }
        set_info = &coordinator_context.members[0].instance->info;
        coordinator_context.stage = CsipStage::operating;
        coordinator_context.last_step = CsipStep::ordered_access;
        if (!startCoordinatorOperationLocked(CsipStep::ordered_access))
        {
            coordinator_context.stage = CsipStage::ready;
            k_spin_unlock(&coordinator_context.lock, key);
            return Error::busy;
        }
        operation_identity = coordinator_context.operation.identity;
        k_spin_unlock(&coordinator_context.lock, key);
        const int result = bt_csip_set_coordinator_ordered_access(
            members, count, set_info, coordinatorOrderedAccess);
        if (result != 0)
        {
            cancelCoordinatorOperation(operation_identity);
            key = k_spin_lock(&coordinator_context.lock);
            if (coordinator_context.owner == this)
            {
                coordinator_context.last_error = publicError(result);
                coordinator_context.native_code = result;
                coordinator_context.stage = CsipStage::failed;
            }
            k_spin_unlock(&coordinator_context.lock, key);
        }
        return publicError(result);
#else
        return Error::unsupported;
#endif
    }

    Error CsipSetCoordinator::lock() noexcept
    {
#if defined(CONFIG_BT_CSIP_SET_COORDINATOR)
        poll();
        const struct bt_csip_set_coordinator_set_member *members[maximum_members] = {};
        const struct bt_csip_set_coordinator_set_info *set_info = nullptr;
        std::uint8_t count = 0U;
        std::uint32_t operation_identity = 0U;
        k_spinlock_key_t key = k_spin_lock(&coordinator_context.lock);
        if (coordinator_context.owner != this ||
            coordinator_context.member_count != coordinator_context.expected_members ||
            coordinator_context.stage == CsipStage::operating ||
            coordinator_context.operation.active)
        {
            const Error result = coordinator_context.owner != this ? Error::not_started
                                                                    : Error::not_ready;
            k_spin_unlock(&coordinator_context.lock, key);
            return result;
        }
        if (coordinator_context.locked)
        {
            k_spin_unlock(&coordinator_context.lock, key);
            return Error::already_started;
        }
        count = coordinator_context.member_count;
        for (std::size_t index = 0U; index < count; ++index)
        {
            members[index] = coordinator_context.members[index].member;
        }
        set_info = &coordinator_context.members[0].instance->info;
        coordinator_context.stage = CsipStage::operating;
        coordinator_context.last_step = CsipStep::lock;
        if (!startCoordinatorOperationLocked(CsipStep::lock))
        {
            coordinator_context.stage = CsipStage::ready;
            k_spin_unlock(&coordinator_context.lock, key);
            return Error::busy;
        }
        operation_identity = coordinator_context.operation.identity;
        k_spin_unlock(&coordinator_context.lock, key);
        const int result = bt_csip_set_coordinator_lock(members, count, set_info);
        if (result != 0)
        {
            cancelCoordinatorOperation(operation_identity);
            key = k_spin_lock(&coordinator_context.lock);
            if (coordinator_context.owner == this)
            {
                coordinator_context.last_error = publicError(result);
                coordinator_context.native_code = result;
                coordinator_context.stage = CsipStage::failed;
            }
            k_spin_unlock(&coordinator_context.lock, key);
        }
        return publicError(result);
#else
        return Error::unsupported;
#endif
    }

    Error CsipSetCoordinator::release() noexcept
    {
#if defined(CONFIG_BT_CSIP_SET_COORDINATOR)
        poll();
        const struct bt_csip_set_coordinator_set_member *members[maximum_members] = {};
        const struct bt_csip_set_coordinator_set_info *set_info = nullptr;
        std::uint8_t count = 0U;
        std::uint32_t operation_identity = 0U;
        k_spinlock_key_t key = k_spin_lock(&coordinator_context.lock);
        const bool cleanup = coordinator_context.last_step == CsipStep::cleanup &&
                             coordinator_context.member_count != 0U;
        if (coordinator_context.owner != this || (!coordinator_context.locked && !cleanup) ||
            coordinator_context.stage == CsipStage::operating ||
            coordinator_context.operation.active)
        {
            const Error result = coordinator_context.owner != this ? Error::not_started
                                                                    : Error::not_ready;
            k_spin_unlock(&coordinator_context.lock, key);
            return result;
        }
        count = coordinator_context.member_count;
        for (std::size_t index = 0U; index < count; ++index)
        {
            members[index] = coordinator_context.members[index].member;
        }
        set_info = &coordinator_context.members[0].instance->info;
        coordinator_context.stage = CsipStage::operating;
        coordinator_context.last_step = CsipStep::release;
        if (!startCoordinatorOperationLocked(CsipStep::release))
        {
            coordinator_context.stage = coordinator_context.locked ? CsipStage::locked
                                                                    : CsipStage::ready;
            k_spin_unlock(&coordinator_context.lock, key);
            return Error::busy;
        }
        operation_identity = coordinator_context.operation.identity;
        k_spin_unlock(&coordinator_context.lock, key);
        const int result = bt_csip_set_coordinator_release(members, count, set_info);
        if (result != 0)
        {
            cancelCoordinatorOperation(operation_identity);
            key = k_spin_lock(&coordinator_context.lock);
            if (coordinator_context.owner == this)
            {
                coordinator_context.last_error = publicError(result);
                coordinator_context.native_code = result;
                coordinator_context.stage = CsipStage::failed;
            }
            k_spin_unlock(&coordinator_context.lock, key);
        }
        return publicError(result);
#else
        return Error::unsupported;
#endif
    }

    std::size_t CsipSetCoordinator::memberCount() const noexcept
    {
#if defined(CONFIG_BT_CSIP_SET_COORDINATOR)
        k_spinlock_key_t key = k_spin_lock(&coordinator_context.lock);
        const std::size_t count =
            coordinator_context.owner == this ? coordinator_context.member_count : 0U;
        k_spin_unlock(&coordinator_context.lock, key);
        return count;
#else
        return 0U;
#endif
    }

    Error CsipSetCoordinator::member(std::size_t index,
                                     CsipMemberInfo &information) const noexcept
    {
#if defined(CONFIG_BT_CSIP_SET_COORDINATOR)
        k_spinlock_key_t key = k_spin_lock(&coordinator_context.lock);
        if (coordinator_context.owner != this || index >= coordinator_context.member_count)
        {
            k_spin_unlock(&coordinator_context.lock, key);
            return Error::invalid_argument;
        }
        information = coordinator_context.members[index].information;
        k_spin_unlock(&coordinator_context.lock, key);
        return Error::none;
#else
        ARG_UNUSED(index);
        ARG_UNUSED(information);
        return Error::unsupported;
#endif
    }

    BLEConnectionHandle CsipSetCoordinator::orderedMember(std::size_t index) const noexcept
    {
#if defined(CONFIG_BT_CSIP_SET_COORDINATOR)
        k_spinlock_key_t key = k_spin_lock(&coordinator_context.lock);
        const BLEConnectionHandle result =
            coordinator_context.owner == this && index < coordinator_context.member_count
                ? coordinator_context.ordered[index]
                : BLEConnectionHandle{};
        k_spin_unlock(&coordinator_context.lock, key);
        return result;
#else
        ARG_UNUSED(index);
        return BLEConnectionHandle{};
#endif
    }

    bool CsipSetCoordinator::ready() const noexcept
    {
#if defined(CONFIG_BT_CSIP_SET_COORDINATOR)
        k_spinlock_key_t key = k_spin_lock(&coordinator_context.lock);
        const bool result = coordinator_context.owner == this &&
                            coordinator_context.member_count ==
                                coordinator_context.expected_members &&
                            (coordinator_context.stage == CsipStage::ready ||
                             coordinator_context.stage == CsipStage::locked);
        k_spin_unlock(&coordinator_context.lock, key);
        return result;
#else
        return false;
#endif
    }

    bool CsipSetCoordinator::locked() const noexcept
    {
#if defined(CONFIG_BT_CSIP_SET_COORDINATOR)
        k_spinlock_key_t key = k_spin_lock(&coordinator_context.lock);
        const bool result = coordinator_context.owner == this && coordinator_context.locked;
        k_spin_unlock(&coordinator_context.lock, key);
        return result;
#else
        return false;
#endif
    }

    CsipStage CsipSetCoordinator::stage() const noexcept
    {
#if defined(CONFIG_BT_CSIP_SET_COORDINATOR)
        k_spinlock_key_t key = k_spin_lock(&coordinator_context.lock);
        const CsipStage result =
            coordinator_context.owner == this ? coordinator_context.stage : CsipStage::idle;
        k_spin_unlock(&coordinator_context.lock, key);
        return result;
#else
        return CsipStage::idle;
#endif
    }

    CsipStep CsipSetCoordinator::lastStep() const noexcept
    {
#if defined(CONFIG_BT_CSIP_SET_COORDINATOR)
        k_spinlock_key_t key = k_spin_lock(&coordinator_context.lock);
        const CsipStep result =
            coordinator_context.owner == this ? coordinator_context.last_step : CsipStep::none;
        k_spin_unlock(&coordinator_context.lock, key);
        return result;
#else
        return CsipStep::none;
#endif
    }

    std::uint32_t CsipSetCoordinator::lockChanges() const noexcept
    {
#if defined(CONFIG_BT_CSIP_SET_COORDINATOR)
        k_spinlock_key_t key = k_spin_lock(&coordinator_context.lock);
        const std::uint32_t result =
            coordinator_context.owner == this ? coordinator_context.lock_changes : 0U;
        k_spin_unlock(&coordinator_context.lock, key);
        return result;
#else
        return 0U;
#endif
    }

    Error CsipSetCoordinator::lastError() const noexcept
    {
#if defined(CONFIG_BT_CSIP_SET_COORDINATOR)
        k_spinlock_key_t key = k_spin_lock(&coordinator_context.lock);
        const Error result = coordinator_context.owner == this ? coordinator_context.last_error
                                                                : Error::not_started;
        k_spin_unlock(&coordinator_context.lock, key);
        return result;
#else
        return Error::unsupported;
#endif
    }

    int CsipSetCoordinator::nativeCode() const noexcept
    {
#if defined(CONFIG_BT_CSIP_SET_COORDINATOR)
        k_spinlock_key_t key = k_spin_lock(&coordinator_context.lock);
        const int result =
            coordinator_context.owner == this ? coordinator_context.native_code : -ENOTSUP;
        k_spin_unlock(&coordinator_context.lock, key);
        return result;
#else
        return -ENOTSUP;
#endif
    }
} // namespace nucode::ble::audio

#endif
