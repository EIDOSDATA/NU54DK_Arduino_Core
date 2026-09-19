/**
 * @file NUCODE_BLE_Audio_BroadcastSink.cpp
 * @brief LC3 BAP broadcast sink 공개 API를 구현합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include "NUCODE_BLE_Audio.h"

#if !defined(ARDUINO_LIBRARY_DISCOVERY_PHASE) && defined(CONFIG_BT_BAP_BROADCAST_SINK)

#include <NUCODE_BLE.h>

#include <zephyr/bluetooth/assigned_numbers.h>
#include <zephyr/bluetooth/audio/bap.h>
#include <zephyr/bluetooth/audio/lc3.h>
#include <zephyr/bluetooth/audio/pacs.h>
#if defined(CONFIG_BT_PBP)
#include <zephyr/bluetooth/audio/pbp.h>
#endif
#include <zephyr/bluetooth/bluetooth.h>
#include <zephyr/bluetooth/hci.h>
#include <zephyr/bluetooth/iso.h>
#include <zephyr/kernel.h>
#include <zephyr/net_buf.h>
#include <zephyr/sys/atomic.h>
#include <zephyr/sys/byteorder.h>
#include <zephyr/sys/util_utf8.h>

#include <errno.h>
#include <string.h>

namespace nucode::ble::audio
{
    namespace
    {
        constexpr std::size_t frame_octets = 40U;
        constexpr std::size_t maximum_broadcast_name = 31U;
        constexpr std::size_t maximum_public_broadcast_name = 128U;
        constexpr std::size_t maximum_program_info = 64U;
        constexpr std::size_t stream_generation_slots = 4U;
        constexpr std::uint32_t periodic_timeout_ratio = 20U;

        K_MSGQ_DEFINE(receive_queue, frame_octets, 8, 4);
        K_SEM_DEFINE(sink_stopped, 0, 1);
        K_SEM_DEFINE(periodic_stopped, 0, 1);
        bt_bap_stream stream_slots[stream_generation_slots] = {};
        std::uint32_t stream_slot_generations[stream_generation_slots] = {};
        atomic_t generation_counter = 0;

        /** @brief 한 Arduino 객체가 소유하는 broadcast sink 상태입니다. */
        struct SinkState
        {
            BroadcastSink *owner = nullptr;
            bt_bap_broadcast_sink *sink = nullptr;
            bt_le_per_adv_sync *periodic_sync = nullptr;
            bt_bap_stream *stream = nullptr;
            bt_addr_le_t broadcaster = {};
            char target_name[maximum_public_broadcast_name + 1U] = {};
            PublicBroadcastInfo public_info = {};
            std::uint32_t broadcast_id = 0U;
            std::uint32_t selected_bis = 0U;
            std::uint32_t generation = 0U;
            std::uint16_t periodic_interval = 0U;
            std::uint8_t sid = 0U;
            BroadcastCode broadcast_code = {};
            atomic_t found = 0;
            atomic_t periodic_synced = 0;
            atomic_t base_received = 0;
            atomic_t syncable = 0;
            atomic_t streaming = 0;
            atomic_t received = 0;
            atomic_t dropped = 0;
            atomic_t error = 0;
            atomic_t stopping = 0;
            atomic_t delegated_start = 0;
            atomic_t delegated_cleanup = 0;
            atomic_t delegated_adds = 0;
            atomic_t delegated_modifications = 0;
            atomic_t delegated_removals = 0;
            BroadcastSinkStep cleanup_failure = BroadcastSinkStep::cleanup;
            bool scan_callback_registered = false;
            bool periodic_callback_registered = false;
            bool pacs_registered = false;
            bool capability_registered = false;
            bool scan_delegator_registered = false;
            bool scanning = false;
            bool sink_created = false;
            bool sync_requested = false;
            bool has_broadcast_code = false;
            bool encrypted = false;
            bool delegated = false;
            bool delegated_source = false;
            bool public_broadcast = false;
            bool advertised_encrypted = false;
            std::uint8_t delegated_source_id = 0xffU;
            std::uint8_t stream_slot = 0U;
        };

        SinkState sink_state;
        bool sink_callback_registered = false;

        constexpr bt_audio_context contexts = BT_AUDIO_CONTEXT_TYPE_MEDIA;
        const bt_audio_codec_cap codec_cap = BT_AUDIO_CODEC_CAP_LC3(
            BT_AUDIO_CODEC_CAP_FREQ_16KHZ, BT_AUDIO_CODEC_CAP_DURATION_10,
            BT_AUDIO_CODEC_CAP_CHAN_COUNT_SUPPORT(1), frame_octets, frame_octets, 1U,
            contexts);
        bt_pacs_cap pac_sink = {
            .codec_cap = &codec_cap,
        };
        bt_bap_scan_delegator_cb scan_delegator_callbacks = {};

        /** @brief 현재 세대에 할당한 stream callback만 상태를 바꾸도록 확인합니다. */
        bool activeStream(const bt_bap_stream *stream) noexcept
        {
            return (sink_state.owner != nullptr) &&
                   (sink_state.generation != 0U) &&
                   (stream == sink_state.stream) &&
                   (stream_slot_generations[sink_state.stream_slot] ==
                    sink_state.generation);
        }

        /** @brief 한 광고 packet에서 BAP announcement와 방송 이름을 수집합니다. */
        struct AdvertisementMatch
        {
            bool service = false;
            bool name = false;
            bool public_announcement = false;
            bool standard_quality = false;
            bool high_quality = false;
            bool encrypted = false;
            char broadcast_name[maximum_public_broadcast_name + 1U] = {};
            char program_info[maximum_program_info + 1U] = {};
            std::uint32_t broadcast_id = 0U;
        };

        /** @brief PBA metadata에서 Program Info를 고정 크기 문자열로 복사합니다. */
        bool parseProgramInfo(const std::uint8_t *metadata, std::size_t metadata_length,
                              char (&program_info)[maximum_program_info + 1U])
        {
            std::size_t offset = 0U;
            while (offset < metadata_length)
            {
                const std::size_t field_length = metadata[offset];
                if ((field_length == 0U) ||
                    ((offset + field_length + 1U) > metadata_length))
                {
                    return false;
                }
                if (metadata[offset + 1U] == BT_AUDIO_METADATA_TYPE_PROGRAM_INFO)
                {
                    const std::size_t value_length = field_length - 1U;
                    if (value_length > maximum_program_info)
                    {
                        return false;
                    }
                    const std::uint8_t *value = &metadata[offset + 2U];
                    if (memchr(value, '\0', value_length) != nullptr)
                    {
                        return false;
                    }
                    memcpy(program_info, value, value_length);
                    program_info[value_length] = '\0';
                    if (utf8_count_chars(program_info) < 0)
                    {
                        return false;
                    }
                }
                offset += field_length + 1U;
            }
            return true;
        }

        /** @brief Service Data와 Broadcast Name AD element를 해석합니다. */
        bool inspectData(bt_data *data, void *user_data)
        {
            auto *match = static_cast<AdvertisementMatch *>(user_data);
            if ((data->type == BT_DATA_SVC_DATA16) &&
                (data->data_len >= BT_UUID_SIZE_16 + BT_AUDIO_BROADCAST_ID_SIZE) &&
                (sys_get_le16(data->data) == BT_UUID_BROADCAST_AUDIO_VAL))
            {
                match->service = true;
                match->broadcast_id = sys_get_le24(data->data + BT_UUID_SIZE_16);
            }
            else if (data->type == BT_DATA_BROADCAST_NAME)
            {
                if (sink_state.public_broadcast)
                {
                    if ((data->data_len >= BT_AUDIO_BROADCAST_NAME_LEN_MIN) &&
                        (data->data_len <= BT_AUDIO_BROADCAST_NAME_LEN_MAX) &&
                        (memchr(data->data, '\0', data->data_len) == nullptr))
                    {
                        memcpy(match->broadcast_name, data->data, data->data_len);
                        match->broadcast_name[data->data_len] = '\0';
                        const int character_count =
                            utf8_count_chars(match->broadcast_name);
                        const bool valid_name =
                            (character_count >= static_cast<int>(
                                 BT_AUDIO_BROADCAST_NAME_LEN_MIN)) &&
                            (character_count <= 32);
                        const bool matches_filter =
                            (sink_state.target_name[0] == '\0') ||
                            ((data->data_len == strlen(sink_state.target_name)) &&
                             (memcmp(data->data, sink_state.target_name,
                                     data->data_len) == 0));
                        match->name = valid_name && matches_filter;
                    }
                }
                else if ((data->data_len == strlen(sink_state.target_name)) &&
                         (memcmp(data->data, sink_state.target_name,
                                 data->data_len) == 0))
                {
                    match->name = true;
                }
            }
#if defined(CONFIG_BT_PBP)
            else if ((data->type == BT_DATA_SVC_DATA16) &&
                     (data->data_len >= BT_UUID_SIZE_16) &&
                     (sys_get_le16(data->data) == BT_UUID_PBA_VAL))
            {
                bt_pbp_announcement_feature features = {};
                std::uint8_t *metadata = nullptr;
                const int metadata_length =
                    bt_pbp_parse_announcement(data, &features, &metadata);
                if ((metadata_length >= 0) &&
                    parseProgramInfo(metadata,
                                     static_cast<std::size_t>(metadata_length),
                                     match->program_info))
                {
                    const std::uint8_t feature_bits =
                        static_cast<std::uint8_t>(features);
                    match->public_announcement = true;
                    match->standard_quality =
                        (feature_bits &
                         BT_PBP_ANNOUNCEMENT_FEATURE_STANDARD_QUALITY) != 0U;
                    match->high_quality =
                        (feature_bits &
                         BT_PBP_ANNOUNCEMENT_FEATURE_HIGH_QUALITY) != 0U;
                    match->encrypted =
                        (feature_bits &
                         BT_PBP_ANNOUNCEMENT_FEATURE_ENCRYPTION) != 0U;
                }
            }
#endif
            return true;
        }

        /** @brief 이름과 Broadcast Audio announcement가 함께 있는 source를 선택합니다. */
        void scanReceived(const bt_le_scan_recv_info *info, net_buf_simple *advertising_data)
        {
            if ((sink_state.owner == nullptr) || (atomic_get(&sink_state.found) != 0) ||
                (info->interval == 0U) ||
                ((info->adv_props & BT_GAP_ADV_PROP_CONNECTABLE) != 0U))
            {
                return;
            }

            AdvertisementMatch match;
            net_buf_simple copy;
            net_buf_simple_clone(advertising_data, &copy);
            bt_data_parse(&copy, inspectData, &match);
            const bool exact_source = !sink_state.delegated ||
                                      (bt_addr_le_cmp(info->addr,
                                                      &sink_state.broadcaster) == 0 &&
                                       info->sid == sink_state.sid &&
                                       match.broadcast_id == sink_state.broadcast_id);
            const bool public_match = !sink_state.public_broadcast ||
                                      (match.public_announcement &&
                                       match.standard_quality && match.name &&
                                       (match.encrypted ==
                                        sink_state.has_broadcast_code));
            if (!match.service || (!sink_state.delegated && !match.name) ||
                !public_match || !exact_source)
            {
                return;
            }
            if (atomic_get(&sink_state.found) == 0)
            {
                bt_addr_le_copy(&sink_state.broadcaster, info->addr);
                sink_state.sid = info->sid;
                sink_state.periodic_interval = info->interval;
                sink_state.broadcast_id = match.broadcast_id;
                if (sink_state.public_broadcast)
                {
                    memcpy(sink_state.public_info.broadcast_name,
                           match.broadcast_name,
                           sizeof(sink_state.public_info.broadcast_name));
                    memcpy(sink_state.public_info.program_info,
                           match.program_info,
                           sizeof(sink_state.public_info.program_info));
                    sink_state.public_info.broadcast_id = match.broadcast_id;
                    sink_state.public_info.encrypted = match.encrypted;
                    sink_state.public_info.standard_quality =
                        match.standard_quality;
                    sink_state.public_info.high_quality = match.high_quality;
                    sink_state.advertised_encrypted = match.encrypted;
                }
                atomic_set(&sink_state.found, 1);
            }
        }

        bt_le_scan_cb scan_callbacks = {
            .recv = scanReceived,
        };

        /** @brief periodic advertising 동기화 완료를 poll()에 전달합니다. */
        void periodicSynced(bt_le_per_adv_sync *sync,
                            bt_le_per_adv_sync_synced_info *info)
        {
            static_cast<void>(info);
            if ((sink_state.owner != nullptr) && (sync == sink_state.periodic_sync))
            {
                atomic_set(&sink_state.periodic_synced, 1);
            }
        }

        /** @brief 예상하지 않은 periodic sync 손실을 오류로 기록합니다. */
        void periodicTerminated(bt_le_per_adv_sync *sync,
                                const bt_le_per_adv_sync_term_info *info)
        {
            if (sync == sink_state.periodic_sync)
            {
                sink_state.periodic_sync = nullptr;
                atomic_set(&sink_state.periodic_synced, 0);
                atomic_set(&sink_state.streaming, 0);
                if ((sink_state.owner != nullptr) &&
                    (atomic_get(&sink_state.stopping) == 0) &&
                    (info->reason != BT_HCI_ERR_LOCALHOST_TERM_CONN))
                {
                    atomic_set(&sink_state.error,
                               info->reason != 0U
                                   ? -static_cast<int>(info->reason)
                                   : -ECONNRESET);
                }
                if (atomic_get(&sink_state.stopping) != 0)
                {
                    k_sem_give(&periodic_stopped);
                }
            }
        }

        bt_le_per_adv_sync_cb periodic_callbacks = {
            .synced = periodicSynced,
            .term = periodicTerminated,
        };

        /** @brief BIS codec 값을 subgroup codec 설정에 병합합니다. */
        struct CodecMergeContext
        {
            bt_audio_codec_cfg *codec = nullptr;
            int error = 0;
        };

        /** @brief BASE에서 선택한 단일 Standard Quality BIS를 보존합니다. */
        struct BaseSelection
        {
            std::uint32_t bis = 0U;
            int error = 0;
            bt_audio_codec_cfg codec = {};
        };

        /** @brief BIS level LTV가 subgroup 값을 안전하게 덮어쓰도록 병합합니다. */
        bool mergeCodecData(bt_data *data, void *user_data)
        {
            auto *context = static_cast<CodecMergeContext *>(user_data);
            const int result = bt_audio_codec_cfg_set_val(
                context->codec,
                static_cast<bt_audio_codec_cfg_type>(data->type),
                data->data, data->data_len);
            if (result < 0)
            {
                context->error = result;
                return false;
            }
            return true;
        }

        /** @brief 공개 decoder가 지원하는 16 kHz mono 10 ms/40-byte 설정인지 확인합니다. */
        bool supportedPublicCodec(const bt_audio_codec_cfg &codec) noexcept
        {
            bt_audio_location location = BT_AUDIO_LOCATION_MONO_AUDIO;
            if ((codec.id != BT_HCI_CODING_FORMAT_LC3) ||
                (bt_audio_codec_cfg_get_freq(&codec) !=
                 BT_AUDIO_CODEC_CFG_FREQ_16KHZ) ||
                (bt_audio_codec_cfg_get_frame_dur(&codec) !=
                 BT_AUDIO_CODEC_CFG_DURATION_10) ||
                (bt_audio_codec_cfg_get_octets_per_frame(&codec) !=
                 static_cast<int>(frame_octets)) ||
                (bt_audio_codec_cfg_get_frame_blocks_per_sdu(&codec, true) != 1) ||
                (bt_audio_codec_cfg_get_chan_allocation(&codec, &location, true) != 0))
            {
                return false;
            }
            return bt_audio_get_chan_count(location) == 1U;
        }

        /** @brief 한 subgroup에서 실제 지원 codec 설정을 가진 첫 BIS를 선택합니다. */
        bool selectBis(const bt_bap_base_subgroup_bis *bis, void *user_data)
        {
            auto *context = static_cast<BaseSelection *>(user_data);
            bt_audio_codec_cfg codec = context->codec;
            if (bis->data_len > 0U)
            {
                CodecMergeContext merge = {
                    .codec = &codec,
                };
                const int result = bt_audio_data_parse(
                    bis->data, bis->data_len, mergeCodecData, &merge);
                if ((result != 0) || (merge.error != 0))
                {
                    context->error = merge.error != 0 ? merge.error : result;
                    return false;
                }
            }
            if ((bis->index == 0U) || (bis->index > BT_ISO_BIS_INDEX_MAX))
            {
                context->error = -EBADMSG;
                return false;
            }
            if (supportedPublicCodec(codec))
            {
                context->bis = BT_ISO_BIS_INDEX_BIT(bis->index);
                return false;
            }
            return true;
        }

        /** @brief subgroup codec과 BIS override를 합쳐 지원 BIS를 검색합니다. */
        bool selectSubgroup(const bt_bap_base_subgroup *subgroup, void *user_data)
        {
            auto *selection = static_cast<BaseSelection *>(user_data);
            memset(&selection->codec, 0, sizeof(selection->codec));
            const int codec_result = bt_bap_base_subgroup_codec_to_codec_cfg(
                subgroup, &selection->codec);
            if (codec_result != 0)
            {
                selection->error = codec_result;
                return false;
            }
            const int result = bt_bap_base_subgroup_foreach_bis(
                subgroup, selectBis, selection);
            if (selection->bis != 0U)
            {
                return false;
            }
            if ((result != 0) && (selection->error != 0))
            {
                return false;
            }
            return true;
        }

        /** @brief BASE에서 실제 지원 Standard Quality BIS를 선택합니다. */
        void baseReceived(bt_bap_broadcast_sink *sink, const bt_bap_base *base,
                          std::size_t base_size)
        {
            if ((sink_state.owner == nullptr) || (sink != sink_state.sink) ||
                (base == nullptr) || (atomic_get(&sink_state.base_received) != 0))
            {
                return;
            }
            const int parsed_size = bt_bap_base_get_size(base);
            if ((parsed_size <= 0) ||
                (static_cast<std::size_t>(parsed_size) > base_size))
            {
                atomic_set(&sink_state.error, -EBADMSG);
                return;
            }

            BaseSelection selection;
            const int result = bt_bap_base_foreach_subgroup(
                base, selectSubgroup, &selection);
            if (selection.bis == 0U)
            {
                const int error = selection.error != 0
                                      ? selection.error
                                      : ((result != 0) ? result : -ENOTSUP);
                atomic_set(&sink_state.error, error);
                return;
            }
            sink_state.selected_bis = selection.bis;
            atomic_set(&sink_state.base_received, 1);
        }

        /** @brief BIGInfo와 제공된 Broadcast Code를 동기화 조건으로 확인합니다. */
        void sinkSyncable(bt_bap_broadcast_sink *sink, const bt_iso_biginfo *biginfo)
        {
            if ((sink_state.owner == nullptr) || (sink != sink_state.sink))
            {
                return;
            }
            sink_state.encrypted = biginfo->encryption;
            if (sink_state.public_broadcast &&
                (sink_state.encrypted != sink_state.advertised_encrypted))
            {
                atomic_set(&sink_state.error, -EBADMSG);
                return;
            }
            if (sink_state.encrypted && !sink_state.has_broadcast_code)
            {
                if (!sink_state.delegated)
                {
                    atomic_set(&sink_state.error, -EACCES);
                }
                return;
            }
            atomic_set(&sink_state.syncable, 1);
        }

        /** @brief BIG 동기화 완료를 공개 streaming 상태로 표시합니다. */
        void sinkStarted(bt_bap_broadcast_sink *sink)
        {
            if ((sink_state.owner != nullptr) && (sink == sink_state.sink))
            {
                atomic_set(&sink_state.streaming, 1);
            }
        }

        /** @brief BIG 중단을 공개 상태와 종료 대기에 반영합니다. */
        void sinkStopped(bt_bap_broadcast_sink *sink, std::uint8_t reason)
        {
            if (sink == sink_state.sink)
            {
                atomic_set(&sink_state.streaming, 0);
                if ((sink_state.owner != nullptr) && sink_state.sync_requested &&
                    (atomic_get(&sink_state.stopping) == 0) &&
                    (reason != BT_HCI_ERR_LOCALHOST_TERM_CONN))
                {
                    atomic_set(&sink_state.error,
                               reason != 0U
                                   ? -static_cast<int>(reason)
                                   : -ECONNRESET);
                }
                if (atomic_get(&sink_state.stopping) != 0)
                {
                    k_sem_give(&sink_stopped);
                }
            }
        }

        bt_bap_broadcast_sink_cb sink_callbacks = {
            .base_recv = baseReceived,
            .syncable = sinkSyncable,
            .started = sinkStarted,
            .stopped = sinkStopped,
        };

        /** @brief 유효한 40-byte LC3 SDU를 고정 queue에 복사합니다. */
        void streamReceived(bt_bap_stream *stream, const bt_iso_recv_info *info,
                            net_buf *buffer)
        {
            if (!activeStream(stream) ||
                ((info->flags & BT_ISO_FLAGS_VALID) == 0U))
            {
                return;
            }
            if (buffer->len != frame_octets)
            {
                atomic_set(&sink_state.error, -EMSGSIZE);
                return;
            }
            atomic_inc(&sink_state.received);
            if (k_msgq_put(&receive_queue, buffer->data, K_NO_WAIT) != 0)
            {
                atomic_inc(&sink_state.dropped);
            }
        }

        /** @brief BIS 수신 시작을 공개 상태에 반영합니다. */
        void streamStarted(bt_bap_stream *stream)
        {
            if (activeStream(stream))
            {
                atomic_set(&sink_state.streaming, 1);
            }
        }

        /** @brief BIS 수신 중단 시 queue와 공개 상태를 정리합니다. */
        void streamStopped(bt_bap_stream *stream, std::uint8_t reason)
        {
            if (activeStream(stream))
            {
                atomic_set(&sink_state.streaming, 0);
                if (sink_state.sync_requested &&
                    (atomic_get(&sink_state.stopping) == 0))
                {
                    atomic_set(&sink_state.error,
                               reason != 0U
                                   ? -static_cast<int>(reason)
                                   : -ECONNRESET);
                }
            }
        }

        bt_bap_stream_ops stream_callbacks = {
            .started = streamStarted,
            .stopped = streamStopped,
            .recv = streamReceived,
        };

        /** @brief Assistant가 요청한 source의 주소와 ID를 동기화 대상으로 복사합니다. */
        void selectDelegatedSource(const bt_bap_scan_delegator_recv_state *state,
                                   std::uint16_t periodic_interval) noexcept
        {
            bt_addr_le_copy(&sink_state.broadcaster, &state->addr);
            sink_state.sid = state->adv_sid;
            sink_state.broadcast_id = state->broadcast_id;
            sink_state.periodic_interval = periodic_interval;
            sink_state.delegated_source_id = state->src_id;
            sink_state.delegated_source = true;
        }

        /** @brief BASS Add Source 요청을 한 receive state 슬롯으로 제한해 수락합니다. */
        int delegatedAdd(bt_conn *connection,
                         const bt_bap_scan_delegator_recv_state *state) noexcept
        {
            static_cast<void>(connection);
            if (!sink_state.delegated || (state == nullptr) ||
                sink_state.delegated_source || (state->num_subgroups != 1U))
            {
                return -EINVAL;
            }
            selectDelegatedSource(state, 0U);
            atomic_inc(&sink_state.delegated_adds);
            return 0;
        }

        /** @brief 현재 source에 대한 BASS Modify Source 요청만 수락합니다. */
        int delegatedModify(bt_conn *connection,
                            const bt_bap_scan_delegator_recv_state *state) noexcept
        {
            static_cast<void>(connection);
            if (!sink_state.delegated || (state == nullptr) ||
                !sink_state.delegated_source ||
                (state->src_id != sink_state.delegated_source_id) ||
                (state->num_subgroups != 1U))
            {
                return -EINVAL;
            }
            atomic_inc(&sink_state.delegated_modifications);
            return 0;
        }

        /** @brief 현재 source에 대한 BASS Remove Source 요청을 main thread에 전달합니다. */
        int delegatedRemove(bt_conn *connection, std::uint8_t source_id) noexcept
        {
            static_cast<void>(connection);
            if (!sink_state.delegated || !sink_state.delegated_source ||
                (source_id != sink_state.delegated_source_id))
            {
                return -EINVAL;
            }
            atomic_inc(&sink_state.delegated_removals);
            atomic_set(&sink_state.stopping, 1);
            atomic_set(&sink_state.delegated_cleanup, 1);
            sink_state.delegated_source = false;
            return 0;
        }

        /** @brief Assistant의 PA sync 요청을 Arduino poll 문맥으로 전달합니다. */
        int delegatedPaSync(bt_conn *connection,
                            const bt_bap_scan_delegator_recv_state *state,
                            bool past_available, std::uint16_t periodic_interval) noexcept
        {
            static_cast<void>(connection);
            static_cast<void>(past_available);
            if (!sink_state.delegated || (state == nullptr) ||
                (state->src_id != sink_state.delegated_source_id))
            {
                return -EINVAL;
            }
            selectDelegatedSource(state, periodic_interval);
            atomic_set(&sink_state.delegated_start, 1);
            return 0;
        }

        /** @brief Assistant의 PA sync 해제 요청을 Arduino poll 문맥으로 전달합니다. */
        int delegatedPaTerminate(bt_conn *connection,
                                 const bt_bap_scan_delegator_recv_state *state) noexcept
        {
            static_cast<void>(connection);
            if (!sink_state.delegated || (state == nullptr) ||
                (state->src_id != sink_state.delegated_source_id))
            {
                return -EINVAL;
            }
            atomic_set(&sink_state.stopping, 1);
            atomic_set(&sink_state.delegated_cleanup, 1);
            return 0;
        }

        /** @brief Assistant가 전달한 Broadcast Code를 BIS sync에 사용합니다. */
        void delegatedCode(bt_conn *connection,
                           const bt_bap_scan_delegator_recv_state *state,
                           const std::uint8_t broadcast_code[BT_ISO_BROADCAST_CODE_SIZE]) noexcept
        {
            static_cast<void>(connection);
            if (!sink_state.delegated || (state == nullptr) ||
                (state->src_id != sink_state.delegated_source_id))
            {
                return;
            }
            memcpy(sink_state.broadcast_code, broadcast_code,
                   sizeof(sink_state.broadcast_code));
            sink_state.has_broadcast_code = true;
            if (sink_state.encrypted)
            {
                atomic_set(&sink_state.syncable, 1);
            }
        }

        /** @brief BIS 1 또는 no-preference 요청만 수락하고 해제 요청을 전달합니다. */
        int delegatedBisSync(
            bt_conn *connection, const bt_bap_scan_delegator_recv_state *state,
            const std::uint32_t bis_sync[BT_BAP_BASS_MAX_SUBGROUPS]) noexcept
        {
            static_cast<void>(connection);
            if (!sink_state.delegated || (state == nullptr) ||
                (state->src_id != sink_state.delegated_source_id))
            {
                return -EINVAL;
            }
            const std::uint32_t requested = bis_sync[0];
            if ((requested != 0U) && (requested != BT_BAP_BIS_SYNC_NO_PREF) &&
                ((requested & ~BT_ISO_BIS_INDEX_BIT(1U)) != 0U))
            {
                return -EINVAL;
            }
            if (requested == 0U)
            {
                atomic_set(&sink_state.stopping, 1);
                atomic_set(&sink_state.delegated_cleanup, 1);
            }
            return 0;
        }

        /** @brief 광고 주기에서 안전한 PA sync timeout을 계산합니다. */
        std::uint16_t periodicTimeout(std::uint16_t interval) noexcept
        {
            if (interval == 0U)
            {
                return 1000U;
            }
            const std::uint32_t timeout =
                (static_cast<std::uint32_t>(interval) * 125U *
                 periodic_timeout_ratio) /
                1000U;
            return static_cast<std::uint16_t>(CLAMP(timeout, BT_GAP_PER_ADV_MIN_TIMEOUT,
                                                    BT_GAP_PER_ADV_MAX_TIMEOUT));
        }

        /** @brief 진행 중인 검색과 동기화 자원을 역순으로 반환합니다. */
        int releaseSink() noexcept
        {
            int first_error = 0;
            atomic_set(&sink_state.stopping, 1);
            sink_state.cleanup_failure = BroadcastSinkStep::cleanup;
            if (sink_state.scanning)
            {
                const int result = bt_le_scan_stop();
                if ((result != 0) && (result != -EALREADY))
                {
                    first_error = result;
                    sink_state.cleanup_failure = BroadcastSinkStep::cleanup_callbacks;
                }
                else
                {
                    sink_state.scanning = false;
                }
            }
            if (sink_state.sink_created && sink_state.sync_requested)
            {
                k_sem_reset(&sink_stopped);
                const int result = bt_bap_broadcast_sink_stop(sink_state.sink);
                if (result == 0)
                {
                    const int wait_result = k_sem_take(&sink_stopped, K_SECONDS(2));
                    if (wait_result == 0)
                    {
                        sink_state.sync_requested = false;
                    }
                    else if (first_error == 0)
                    {
                        first_error = wait_result;
                        sink_state.cleanup_failure =
                            BroadcastSinkStep::cleanup_sink_stop;
                    }
                }
                else if (result == -EALREADY)
                {
                    sink_state.sync_requested = false;
                }
                else if (first_error == 0)
                {
                    first_error = result;
                    sink_state.cleanup_failure = BroadcastSinkStep::cleanup_sink_stop;
                }
            }
            if (sink_state.delegated && sink_state.delegated_source &&
                (sink_state.delegated_source_id != 0xffU))
            {
                int result = bt_bap_scan_delegator_set_pa_state(
                    sink_state.delegated_source_id, BT_BAP_PA_STATE_NOT_SYNCED);
                if (result == 0)
                {
                    result = bt_bap_scan_delegator_rem_src(
                        sink_state.delegated_source_id);
                }
                if (result == 0)
                {
                    sink_state.delegated_source = false;
                    sink_state.delegated_source_id = 0xffU;
                }
                else if (first_error == 0)
                {
                    first_error = result;
                    sink_state.cleanup_failure = BroadcastSinkStep::cleanup_callbacks;
                }
            }
            if (sink_state.sink_created && !sink_state.sync_requested)
            {
                const int result = bt_bap_broadcast_sink_delete(sink_state.sink);
                if (result == 0)
                {
                    sink_state.sink = nullptr;
                    sink_state.sink_created = false;
                }
                else if (first_error == 0)
                {
                    first_error = result;
                    sink_state.cleanup_failure = BroadcastSinkStep::cleanup_sink_delete;
                }
            }
            if (!sink_state.sink_created && (sink_state.periodic_sync != nullptr))
            {
                k_sem_reset(&periodic_stopped);
                const int result = bt_le_per_adv_sync_delete(sink_state.periodic_sync);
                const int wait_result = (result == 0)
                                            ? k_sem_take(&periodic_stopped, K_SECONDS(2))
                                            : 0;
                if ((result == 0) && (wait_result == 0))
                {
                    sink_state.periodic_sync = nullptr;
                }
                else if (first_error == 0)
                {
                    first_error = (result != 0) ? result : wait_result;
                    sink_state.cleanup_failure = BroadcastSinkStep::cleanup_periodic_sync;
                }
            }
            const bool reception_released = !sink_state.scanning &&
                                             !sink_state.sink_created &&
                                             (sink_state.periodic_sync == nullptr) &&
                                             !sink_state.delegated_source;
            if (reception_released && sink_state.scan_callback_registered)
            {
                bt_le_scan_cb_unregister(&scan_callbacks);
                sink_state.scan_callback_registered = false;
            }
            if (reception_released && sink_state.periodic_callback_registered)
            {
                const int result = bt_le_per_adv_sync_cb_unregister(&periodic_callbacks);
                if (result == 0)
                {
                    sink_state.periodic_callback_registered = false;
                }
                else if (first_error == 0)
                {
                    first_error = result;
                    sink_state.cleanup_failure = BroadcastSinkStep::cleanup_callbacks;
                }
            }
            if (reception_released && sink_state.scan_delegator_registered)
            {
                const int result = bt_bap_scan_delegator_unregister();
                if (result == 0)
                {
                    sink_state.scan_delegator_registered = false;
                }
                else if (first_error == 0)
                {
                    first_error = result;
                    sink_state.cleanup_failure = BroadcastSinkStep::cleanup_scan_delegator;
                }
            }
            if (reception_released && !sink_state.scan_delegator_registered &&
                sink_state.capability_registered)
            {
                const int result = bt_pacs_cap_unregister(BT_AUDIO_DIR_SINK, &pac_sink);
                if (result == 0)
                {
                    sink_state.capability_registered = false;
                }
                else if (first_error == 0)
                {
                    first_error = result;
                    sink_state.cleanup_failure = BroadcastSinkStep::cleanup_capability;
                }
            }
            if (reception_released && !sink_state.capability_registered &&
                sink_state.pacs_registered)
            {
                const int result = bt_pacs_unregister();
                if (result == 0)
                {
                    sink_state.pacs_registered = false;
                }
                else if (first_error == 0)
                {
                    first_error = result;
                    sink_state.cleanup_failure = BroadcastSinkStep::cleanup_pacs;
                }
            }
            if ((first_error == 0) && reception_released &&
                !sink_state.periodic_callback_registered &&
                !sink_state.scan_delegator_registered &&
                !sink_state.capability_registered && !sink_state.pacs_registered)
            {
                sink_state.sync_requested = false;
                sink_state.selected_bis = 0U;
                sink_state.stream = nullptr;
                sink_state.generation = 0U;
                atomic_set(&sink_state.streaming, 0);
                atomic_set(&sink_state.stopping, 0);
                k_msgq_purge(&receive_queue);
            }
            return first_error;
        }

        /** @brief BASS/PACS 등록은 유지하고 현재 방송 수신 자원만 반환합니다. */
        int releaseDelegatedReception() noexcept
        {
            int first_error = 0;
            atomic_set(&sink_state.stopping, 1);
            sink_state.cleanup_failure = BroadcastSinkStep::cleanup;
            if (sink_state.scanning)
            {
                const int result = bt_le_scan_stop();
                if ((result != 0) && (result != -EALREADY))
                {
                    first_error = result;
                    sink_state.cleanup_failure = BroadcastSinkStep::cleanup_callbacks;
                }
                else
                {
                    sink_state.scanning = false;
                }
            }
            if (sink_state.sink_created && sink_state.sync_requested)
            {
                k_sem_reset(&sink_stopped);
                const int result = bt_bap_broadcast_sink_stop(sink_state.sink);
                if (result == 0)
                {
                    const int wait_result = k_sem_take(&sink_stopped, K_SECONDS(2));
                    if (wait_result == 0)
                    {
                        sink_state.sync_requested = false;
                    }
                    else if (first_error == 0)
                    {
                        first_error = wait_result;
                        sink_state.cleanup_failure =
                            BroadcastSinkStep::cleanup_sink_stop;
                    }
                }
                else if (result == -EALREADY)
                {
                    sink_state.sync_requested = false;
                }
                else if (first_error == 0)
                {
                    first_error = result;
                    sink_state.cleanup_failure = BroadcastSinkStep::cleanup_sink_stop;
                }
            }
            if (sink_state.delegated_source &&
                (sink_state.delegated_source_id != 0xffU))
            {
                const int result = bt_bap_scan_delegator_set_pa_state(
                    sink_state.delegated_source_id, BT_BAP_PA_STATE_NOT_SYNCED);
                if ((result != 0) && (first_error == 0))
                {
                    first_error = result;
                    sink_state.cleanup_failure = BroadcastSinkStep::cleanup_callbacks;
                }
            }
            if (sink_state.sink_created && !sink_state.sync_requested)
            {
                const int result = bt_bap_broadcast_sink_delete(sink_state.sink);
                if (result == 0)
                {
                    sink_state.sink = nullptr;
                    sink_state.sink_created = false;
                }
                else if (first_error == 0)
                {
                    first_error = result;
                    sink_state.cleanup_failure = BroadcastSinkStep::cleanup_sink_delete;
                }
            }
            if (!sink_state.sink_created && (sink_state.periodic_sync != nullptr))
            {
                k_sem_reset(&periodic_stopped);
                const int result = bt_le_per_adv_sync_delete(sink_state.periodic_sync);
                const int wait_result = (result == 0)
                                            ? k_sem_take(&periodic_stopped, K_SECONDS(2))
                                            : 0;
                if ((result == 0) && (wait_result == 0))
                {
                    sink_state.periodic_sync = nullptr;
                }
                else if (first_error == 0)
                {
                    first_error = (result != 0) ? result : wait_result;
                    sink_state.cleanup_failure = BroadcastSinkStep::cleanup_periodic_sync;
                }
            }
            if ((first_error == 0) && !sink_state.scanning &&
                !sink_state.sink_created && (sink_state.periodic_sync == nullptr))
            {
                sink_state.sync_requested = false;
                sink_state.selected_bis = 0U;
                sink_state.encrypted = false;
                atomic_set(&sink_state.found, 0);
                atomic_set(&sink_state.periodic_synced, 0);
                atomic_set(&sink_state.base_received, 0);
                atomic_set(&sink_state.syncable, 0);
                atomic_set(&sink_state.streaming, 0);
                atomic_set(&sink_state.error, 0);
                atomic_set(&sink_state.stopping, 0);
                k_msgq_purge(&receive_queue);
            }
            return first_error;
        }
    } // namespace

    /** @brief 마지막 공개 오류와 원본 stack 오류를 기록합니다. */
    Error BroadcastSink::record(Error error, int native_code) noexcept
    {
        last_error_ = error;
        native_code_ = native_code;
        return error;
    }

    /** @brief BAP broadcast source 검색과 callback 집합을 시작합니다. */
    Error BroadcastSink::begin(const char *broadcast_name) noexcept
    {
        return start(broadcast_name, nullptr);
    }

    /** @brief Broadcast Code가 필요한 source 검색을 시작합니다. */
    Error BroadcastSink::begin(const char *broadcast_name,
                               const BroadcastCode &broadcast_code) noexcept
    {
        return start(broadcast_name, broadcast_code);
    }

    /** @brief BASS Assistant가 지정할 source를 기다리는 Scan Delegator를 시작합니다. */
    Error BroadcastSink::beginDelegated() noexcept
    {
        return start(nullptr, nullptr);
    }

    /** @brief 일반 BAP broadcast 설정을 기존 경로로 전달합니다. */
    Error BroadcastSink::start(const char *broadcast_name,
                               const std::uint8_t *broadcast_code) noexcept
    {
        return startConfigured(broadcast_name, broadcast_code, false);
    }

    /** @brief Standard Quality 공개 방송 검색 조건을 적용합니다. */
    Error BroadcastSink::startPublic(const PublicBroadcastFilter &filter,
                                     const std::uint8_t *broadcast_code) noexcept
    {
#if defined(CONFIG_BT_PBP)
        if (filter.required_quality != PublicBroadcastQuality::standard)
        {
            return record(Error::unsupported);
        }
        if (filter.broadcast_name != nullptr)
        {
            const std::size_t name_bytes = strlen(filter.broadcast_name);
            const int name_characters = utf8_count_chars(filter.broadcast_name);
            if ((name_bytes < BT_AUDIO_BROADCAST_NAME_LEN_MIN) ||
                (name_bytes > BT_AUDIO_BROADCAST_NAME_LEN_MAX) ||
                (name_characters < static_cast<int>(
                     BT_AUDIO_BROADCAST_NAME_LEN_MIN)) ||
                (name_characters > 32))
            {
                return record(Error::invalid_argument);
            }
        }
        return startConfigured(filter.broadcast_name, broadcast_code, true);
#else
        static_cast<void>(filter);
        static_cast<void>(broadcast_code);
        return record(Error::unsupported);
#endif
    }

    /** @brief 선택한 code와 함께 검색·PACS·BASS 자원을 구성합니다. */
    Error BroadcastSink::startConfigured(const char *broadcast_name,
                                         const std::uint8_t *broadcast_code,
                                         bool public_broadcast) noexcept
    {
        if (started_)
        {
            return record(Error::already_started);
        }
        if (!BLEDevice.initialized())
        {
            return record(Error::not_ready);
        }
        if (sink_state.owner != nullptr)
        {
            return record(Error::busy);
        }
        if (!public_broadcast && (broadcast_name != nullptr) &&
            ((broadcast_name[0] == '\0') ||
             (strlen(broadcast_name) > maximum_broadcast_name)))
        {
            return record(Error::invalid_argument);
        }

        sink_state = {};
        sink_state.owner = this;
        sink_state.generation =
            static_cast<std::uint32_t>(atomic_inc(&generation_counter)) + 1U;
        if (sink_state.generation == 0U)
        {
            sink_state.generation =
                static_cast<std::uint32_t>(atomic_inc(&generation_counter)) + 1U;
        }
        sink_state.stream_slot = static_cast<std::uint8_t>(
            sink_state.generation % stream_generation_slots);
        sink_state.stream = &stream_slots[sink_state.stream_slot];
        stream_slot_generations[sink_state.stream_slot] = sink_state.generation;
        sink_state.public_broadcast = public_broadcast;
        sink_state.delegated = !public_broadcast && (broadcast_name == nullptr);
        if (broadcast_name != nullptr)
        {
            memcpy(sink_state.target_name, broadcast_name, strlen(broadcast_name) + 1U);
        }
        if (broadcast_code != nullptr)
        {
            memcpy(sink_state.broadcast_code, broadcast_code,
                   sizeof(sink_state.broadcast_code));
            sink_state.has_broadcast_code = true;
        }
        memset(sink_state.stream, 0, sizeof(*sink_state.stream));
        bt_bap_stream_cb_register(sink_state.stream, &stream_callbacks);
        k_msgq_purge(&receive_queue);
        k_sem_reset(&sink_stopped);
        k_sem_reset(&periodic_stopped);
        scan_delegator_callbacks.recv_state_updated = nullptr;
        scan_delegator_callbacks.pa_sync_req = delegatedPaSync;
        scan_delegator_callbacks.pa_sync_term_req = delegatedPaTerminate;
        scan_delegator_callbacks.broadcast_code = delegatedCode;
        scan_delegator_callbacks.bis_sync_req = delegatedBisSync;
        scan_delegator_callbacks.scanning_state = nullptr;
        scan_delegator_callbacks.add_source = delegatedAdd;
        scan_delegator_callbacks.modify_source = delegatedModify;
        scan_delegator_callbacks.remove_source = delegatedRemove;

        const bt_pacs_register_param pacs_config = {
            .snk_pac = true,
            .snk_loc = true,
        };
        last_step_ = BroadcastSinkStep::pacs;
        int result = bt_pacs_register(&pacs_config);
        sink_state.pacs_registered = result == 0;
        if (result == 0)
        {
            last_step_ = BroadcastSinkStep::capability;
            result = bt_pacs_cap_register(BT_AUDIO_DIR_SINK, &pac_sink);
            sink_state.capability_registered = result == 0;
        }
        if (result == 0)
        {
            last_step_ = BroadcastSinkStep::location;
            result = bt_pacs_set_location(BT_AUDIO_DIR_SINK,
                                          BT_AUDIO_LOCATION_FRONT_LEFT);
        }
        if (result == 0)
        {
            last_step_ = BroadcastSinkStep::supported_contexts;
            result = bt_pacs_set_supported_contexts(BT_AUDIO_DIR_SINK, contexts);
        }
        if (result == 0)
        {
            last_step_ = BroadcastSinkStep::available_contexts;
            result = bt_pacs_set_available_contexts(BT_AUDIO_DIR_SINK, contexts);
        }
        if (result == 0)
        {
            last_step_ = BroadcastSinkStep::scan_delegator;
            result = bt_bap_scan_delegator_register(&scan_delegator_callbacks);
            sink_state.scan_delegator_registered = result == 0;
        }
        if ((result == 0) && !sink_callback_registered)
        {
            last_step_ = BroadcastSinkStep::callbacks;
            result = bt_bap_broadcast_sink_register_cb(&sink_callbacks);
            if (result == 0)
            {
                sink_callback_registered = true;
            }
        }
        if (result == 0)
        {
            last_step_ = BroadcastSinkStep::callbacks;
            result = bt_le_scan_cb_register(&scan_callbacks);
            sink_state.scan_callback_registered = result == 0;
        }
        if (result == 0)
        {
            last_step_ = BroadcastSinkStep::callbacks;
            result = bt_le_per_adv_sync_cb_register(&periodic_callbacks);
            sink_state.periodic_callback_registered = result == 0;
        }
        if ((result == 0) && !sink_state.delegated)
        {
            last_step_ = BroadcastSinkStep::scan;
            result = bt_le_scan_start(BT_LE_SCAN_ACTIVE, nullptr);
            sink_state.scanning = result == 0;
        }
        if (result != 0)
        {
            const int cleanup_result = releaseSink();
            if (cleanup_result != 0)
            {
                started_ = true;
                stage_ = BroadcastStage::failed;
                last_step_ = sink_state.cleanup_failure;
                return record(Error::stack_error, cleanup_result);
            }
            sink_state.owner = nullptr;
            sink_state.generation = 0U;
            return record(Error::stack_error, result);
        }

        started_ = true;
        stage_ = sink_state.delegated ? BroadcastStage::idle : BroadcastStage::scanning;
        return record(Error::none);
    }

    /** @brief 검색 결과를 PA/BASE/BIG/BIS 동기화 단계로 진행합니다. */
    void BroadcastSink::poll() noexcept
    {
        if (!started_)
        {
            return;
        }

        if (sink_state.delegated &&
            atomic_cas(&sink_state.delegated_cleanup, 1, 0))
        {
            stage_ = BroadcastStage::stopping;
            const int cleanup_result = releaseDelegatedReception();
            if (cleanup_result != 0)
            {
                stage_ = BroadcastStage::failed;
                last_step_ = sink_state.cleanup_failure;
                (void)record(Error::stack_error, cleanup_result);
                return;
            }
            stage_ = BroadcastStage::idle;
            (void)record(Error::none);
        }

        if (stage_ == BroadcastStage::failed)
        {
            return;
        }

        if (sink_state.delegated &&
            atomic_cas(&sink_state.delegated_start, 1, 0))
        {
            if (stage_ != BroadcastStage::idle)
            {
                const int cleanup_result = releaseDelegatedReception();
                if (cleanup_result != 0)
                {
                    stage_ = BroadcastStage::failed;
                    last_step_ = sink_state.cleanup_failure;
                    (void)record(Error::stack_error, cleanup_result);
                    return;
                }
            }
            last_step_ = BroadcastSinkStep::scan;
            const int scan_result = bt_le_scan_start(BT_LE_SCAN_ACTIVE, nullptr);
            if (scan_result != 0)
            {
                stage_ = BroadcastStage::failed;
                (void)record(Error::stack_error, scan_result);
                return;
            }
            sink_state.scanning = true;
            stage_ = BroadcastStage::scanning;
        }

        const int callback_error = atomic_get(&sink_state.error);
        if (callback_error != 0)
        {
            stage_ = BroadcastStage::failed;
            (void)record(Error::stack_error, callback_error);
            return;
        }

        if ((stage_ == BroadcastStage::scanning) &&
            (atomic_get(&sink_state.found) != 0))
        {
            if (sink_state.scanning)
            {
                const int scan_result = bt_le_scan_stop();
                if ((scan_result != 0) && (scan_result != -EALREADY))
                {
                    stage_ = BroadcastStage::failed;
                    (void)record(Error::stack_error, scan_result);
                    return;
                }
                sink_state.scanning = false;
            }

            const bt_le_per_adv_sync_param sync_param = {
                .addr = sink_state.broadcaster,
                .sid = sink_state.sid,
                .options = BT_LE_PER_ADV_SYNC_OPT_NONE,
                .skip = 5U,
                .timeout = periodicTimeout(sink_state.periodic_interval),
            };
            last_step_ = BroadcastSinkStep::periodic_sync;
            const int result = bt_le_per_adv_sync_create(&sync_param,
                                                         &sink_state.periodic_sync);
            if (result != 0)
            {
                stage_ = BroadcastStage::failed;
                (void)record(Error::stack_error, result);
                return;
            }
            stage_ = BroadcastStage::synchronizing;
        }

        if ((stage_ == BroadcastStage::synchronizing) &&
            (atomic_get(&sink_state.periodic_synced) != 0) &&
            !sink_state.sink_created)
        {
            last_step_ = BroadcastSinkStep::sink_create;
            const int result = bt_bap_broadcast_sink_create(sink_state.periodic_sync,
                                                            sink_state.broadcast_id,
                                                            &sink_state.sink);
            if (result != 0)
            {
                stage_ = BroadcastStage::failed;
                (void)record(Error::stack_error, result);
                return;
            }
            sink_state.sink_created = true;
        }

        if ((stage_ == BroadcastStage::synchronizing) && sink_state.sink_created &&
            !sink_state.sync_requested &&
            (atomic_get(&sink_state.base_received) != 0) &&
            (atomic_get(&sink_state.syncable) != 0) &&
            (!sink_state.encrypted || sink_state.has_broadcast_code))
        {
            bt_bap_stream *streams[] = {sink_state.stream};
            last_step_ = BroadcastSinkStep::bis_sync;
            const std::uint8_t *broadcast_code =
                sink_state.encrypted ? sink_state.broadcast_code : nullptr;
            const int result = bt_bap_broadcast_sink_sync(
                sink_state.sink, sink_state.selected_bis, streams, broadcast_code);
            if (result != 0)
            {
                stage_ = BroadcastStage::failed;
                (void)record(Error::stack_error, result);
                return;
            }
            sink_state.sync_requested = true;
        }

        if ((stage_ == BroadcastStage::synchronizing) && streaming())
        {
            stage_ = BroadcastStage::streaming;
            (void)record(Error::none);
        }
    }

    /** @brief BIS, PA sync, 검색 callback을 중단하고 backend 소유권을 반환합니다. */
    Error BroadcastSink::end() noexcept
    {
        if (!started_)
        {
            return record(Error::not_started);
        }
        stage_ = BroadcastStage::stopping;
        last_step_ = BroadcastSinkStep::cleanup;
        const int result = releaseSink();
        if (result != 0)
        {
            stage_ = BroadcastStage::failed;
            last_step_ = sink_state.cleanup_failure;
            return record(Error::stack_error, result);
        }
        sink_state.owner = nullptr;
        started_ = false;
        stage_ = BroadcastStage::idle;
        return record(Error::none);
    }

    /** @brief callback이 확정한 BIS 수신 상태를 반환합니다. */
    bool BroadcastSink::streaming() const noexcept
    {
        return started_ && (atomic_get(&sink_state.streaming) != 0);
    }

    /** @brief queue의 LC3 frame 한 개를 Arduino 문맥으로 전달합니다. */
    bool BroadcastSink::readFrame(std::uint8_t (&frame)[40]) noexcept
    {
        return started_ && (k_msgq_get(&receive_queue, frame, K_NO_WAIT) == 0);
    }

    /** @brief 선택된 공개 방송 announcement 정보를 복사합니다. */
    bool BroadcastSink::selectedPublic(PublicBroadcastInfo &info) const noexcept
    {
        if (!started_ || !sink_state.public_broadcast ||
            (atomic_get(&sink_state.found) == 0))
        {
            return false;
        }
        info = sink_state.public_info;
        return true;
    }

    /** @brief 현재 비동기 단계를 반환합니다. */
    BroadcastStage BroadcastSink::stage() const noexcept
    {
        return stage_;
    }

    /** @brief 마지막 Host 요청 또는 오류 작업을 반환합니다. */
    BroadcastSinkStep BroadcastSink::lastStep() const noexcept
    {
        return last_step_;
    }

    /** @brief 유효한 BIS frame 수를 반환합니다. */
    std::uint32_t BroadcastSink::receivedFrames() const noexcept
    {
        return started_ ? static_cast<std::uint32_t>(atomic_get(&sink_state.received)) : 0U;
    }

    /** @brief queue 포화로 폐기한 BIS frame 수를 반환합니다. */
    std::uint32_t BroadcastSink::droppedFrames() const noexcept
    {
        return started_ ? static_cast<std::uint32_t>(atomic_get(&sink_state.dropped)) : 0U;
    }

    /** @brief 마지막 공개 오류를 반환합니다. */
    Error BroadcastSink::lastError() const noexcept
    {
        return last_error_;
    }

    /** @brief 마지막 callback 또는 stack 오류를 반환합니다. */
    int BroadcastSink::nativeCode() const noexcept
    {
        const int callback_error = atomic_get(&sink_state.error);
        return callback_error != 0 ? callback_error : native_code_;
    }

    /** @brief 수락한 BASS Add Source 요청 수를 반환합니다. */
    std::uint32_t BroadcastSink::delegatedAdds() const noexcept
    {
        return started_
                   ? static_cast<std::uint32_t>(atomic_get(&sink_state.delegated_adds))
                   : 0U;
    }

    /** @brief 수락한 BASS Modify Source 요청 수를 반환합니다. */
    std::uint32_t BroadcastSink::delegatedModifications() const noexcept
    {
        return started_ ? static_cast<std::uint32_t>(
                              atomic_get(&sink_state.delegated_modifications))
                        : 0U;
    }

    /** @brief 수락한 BASS Remove Source 요청 수를 반환합니다. */
    std::uint32_t BroadcastSink::delegatedRemovals() const noexcept
    {
        return started_
                   ? static_cast<std::uint32_t>(atomic_get(&sink_state.delegated_removals))
                   : 0U;
    }
} // namespace nucode::ble::audio

#else

namespace nucode::ble::audio
{
    /** @brief broadcast sink 기능이 없는 image에서는 시작을 거부합니다. */
    Error BroadcastSink::begin(const char *) noexcept
    {
        return record(Error::not_ready);
    }

    /** @brief 기능이 없는 image에서는 암호화 broadcast 검색도 거부합니다. */
    Error BroadcastSink::begin(const char *, const BroadcastCode &) noexcept
    {
        return record(Error::not_ready);
    }

    /** @brief 기능이 없는 image에서는 delegated sink 시작도 거부합니다. */
    Error BroadcastSink::beginDelegated() noexcept
    {
        return record(Error::not_ready);
    }

    Error BroadcastSink::start(const char *, const std::uint8_t *) noexcept
    {
        return record(Error::not_ready);
    }

    Error BroadcastSink::startPublic(const PublicBroadcastFilter &,
                                     const std::uint8_t *) noexcept
    {
        return record(Error::unsupported);
    }

    Error BroadcastSink::startConfigured(const char *, const std::uint8_t *,
                                         bool) noexcept
    {
        return record(Error::not_ready);
    }

    /** @brief 기능이 없는 image에서는 진행할 동기화 단계가 없습니다. */
    void BroadcastSink::poll() noexcept
    {
    }

    /** @brief 시작하지 않은 broadcast sink는 해제할 자원이 없습니다. */
    Error BroadcastSink::end() noexcept
    {
        return record(Error::not_started);
    }

    /** @brief 기능이 없는 image에서 streaming은 항상 거짓입니다. */
    bool BroadcastSink::streaming() const noexcept
    {
        return false;
    }

    /** @brief 기능이 없는 image에서 수신 frame은 없습니다. */
    bool BroadcastSink::readFrame(std::uint8_t (&frame)[40]) noexcept
    {
        static_cast<void>(frame);
        return false;
    }

    bool BroadcastSink::selectedPublic(PublicBroadcastInfo &) const noexcept
    {
        return false;
    }

    /** @brief 기능이 없는 image는 idle 상태입니다. */
    BroadcastStage BroadcastSink::stage() const noexcept
    {
        return stage_;
    }

    /** @brief 기능이 없는 image는 요청한 작업이 없습니다. */
    BroadcastSinkStep BroadcastSink::lastStep() const noexcept
    {
        return last_step_;
    }

    /** @brief 기능이 없는 image의 수신 수는 0입니다. */
    std::uint32_t BroadcastSink::receivedFrames() const noexcept
    {
        return 0U;
    }

    /** @brief 기능이 없는 image의 폐기 수는 0입니다. */
    std::uint32_t BroadcastSink::droppedFrames() const noexcept
    {
        return 0U;
    }

    /** @brief 마지막 공개 오류를 반환합니다. */
    Error BroadcastSink::lastError() const noexcept
    {
        return last_error_;
    }

    /** @brief 기능이 없는 image에서 stack 오류는 없습니다. */
    int BroadcastSink::nativeCode() const noexcept
    {
        return 0;
    }

    std::uint32_t BroadcastSink::delegatedAdds() const noexcept
    {
        return 0U;
    }

    std::uint32_t BroadcastSink::delegatedModifications() const noexcept
    {
        return 0U;
    }

    std::uint32_t BroadcastSink::delegatedRemovals() const noexcept
    {
        return 0U;
    }

    /** @brief 마지막 공개 오류를 기록합니다. */
    Error BroadcastSink::record(Error error, int native_code) noexcept
    {
        static_cast<void>(native_code);
        last_error_ = error;
        return error;
    }
} // namespace nucode::ble::audio

#endif
