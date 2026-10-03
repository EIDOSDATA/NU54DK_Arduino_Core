/**
 * @file main.cpp
 * @brief 두 NU54DK에서 W05 Nordic 확장과 지원 경계를 검증합니다.
 *
 * SPDX-License-Identifier: MIT
 */

#include <Arduino.h>
#include <NUCODE_BLE.h>

#include <hal/nrf_egu.h>
#include <zephyr/devicetree.h>
#include <zephyr/irq.h>
#include <zephyr/kernel.h>

#include <cstddef>
#include <cstdint>
#include <string.h>

#ifndef M32_NORDIC_CORE_REVISION
#error "M32_NORDIC_CORE_REVISION is required"
#endif

#define M32_NORDIC_EGU_NODE DT_NODELABEL(egu10)
#define M32_NORDIC_EGU \
    (reinterpret_cast<NRF_EGU_Type *>(DT_REG_ADDR(M32_NORDIC_EGU_NODE)))

namespace
{
    constexpr char protocol[] = "M32NOR|1";
    constexpr char start_prefix[] = "M32NOR|1|START|nonce=";
    constexpr char stop_prefix[] = "M32NOR|1|STOP|nonce=";
    constexpr char peer_name[] = "NU54-M32-NOR";
    constexpr std::size_t nonce_length = 32U;
    constexpr std::uint32_t iteration_target = 20U;
    constexpr std::uint32_t qos_target = 200U;
    constexpr std::uint32_t survey_target = 20U;
    constexpr std::uint32_t anchor_target = 1000U;
    constexpr std::uint32_t event_target = 200U;
    constexpr std::uint32_t prepare_target = 200U;
    constexpr std::int64_t session_timeout_ms = 30000;

    char command[128] = {};
    char nonce[nonce_length + 1U] = {};
    std::size_t command_length = 0U;
    bool started = false;
    bool connected = false;
#if defined(NUCODE_M32_NORDIC_CENTRAL)
    bool llpm_requested = false;
#endif
    bool llpm_ready = false;
    bool overflow_observed = false;
    volatile bool measurement_enabled = false;
    volatile bool finishing = false;
    bool session_complete = false;
    bool stop_requested = false;
    bool failed = false;
    bool callback_context_valid = true;
    bool invalid_llpm_rejected = false;
    bool invalid_survey_rejected = false;
    bool invalid_event_task_rejected = false;
    bool duplicate_reservation_bounded = false;
    bool disabled_callback_quiet = false;
    bool projection_wrap_pass = false;
    std::int64_t deadline_ms = 0;
    std::int64_t disable_deadline_ms = 0;
    std::int64_t progress_deadline_ms = 0;
    struct k_thread *main_thread = nullptr;
    nucode::ble::BLEConnectionHandle connection_handle;
    volatile std::uint32_t qos_samples = 0U;
    volatile std::uint32_t survey_samples = 0U;
    volatile std::uint32_t anchor_samples = 0U;
    volatile std::uint32_t event_samples = 0U;
    volatile std::uint32_t prepare_samples = 0U;
    volatile std::uint32_t late_qos = 0U;
    volatile std::uint32_t late_survey = 0U;
    volatile std::uint32_t late_anchor = 0U;
    volatile std::uint32_t late_event = 0U;
    volatile std::uint32_t late_prepare = 0U;
    volatile std::uint32_t last_event_ms = 0U;
    volatile std::uint32_t maximum_event_gap_ms = 0U;
    std::uint64_t last_anchor_us = 0U;
    std::uint32_t maximum_anchor_gap_us = 0U;
    std::uint32_t llpm_interval_us = 0U;
    std::uint32_t dropped_before_overflow = 0U;
    nucode::ble::BLEFlushableAclSupport acl_support;

    /** @brief 현재 image의 고정 역할을 반환합니다. */
    const char *roleName()
    {
#if defined(NUCODE_M32_NORDIC_CENTRAL)
        return "central";
#else
        return "peripheral";
#endif
    }

    /** @brief 결과 record에 nonce와 exact Core revision을 결합합니다. */
    void printSuffix()
    {
        Serial.print("|nonce=");
        Serial.print(nonce);
        Serial.print("|core=");
        Serial.print(M32_NORDIC_CORE_REVISION);
    }

    /** @brief 첫 오류만 bounded protocol로 출력합니다. */
    void fail(const char *stage, int code = 0)
    {
        if (failed)
        {
            return;
        }
        Serial.print(protocol);
        Serial.print("|FAIL|role=");
        Serial.print(roleName());
        Serial.print("|stage=");
        Serial.print(stage);
        Serial.print("|code=");
        Serial.print(code);
        printSuffix();
        Serial.println();
        failed = true;
    }

    /** @brief main-thread callback 계약을 검사합니다. */
    void checkMainContext()
    {
        if (k_current_get() != main_thread)
        {
            callback_context_valid = false;
            fail("callback_context");
        }
    }

    /** @brief EGU event를 지우고 측정 또는 취소 뒤 callback을 계수합니다. */
    void onEguEvent(const void *context)
    {
        static_cast<void>(context);
        nrf_egu_event_clear(M32_NORDIC_EGU, NRF_EGU_EVENT_TRIGGERED0);
        if (measurement_enabled)
        {
            const std::uint32_t now = k_uptime_get_32();
            if (event_samples < event_target)
            {
                if (last_event_ms != 0U)
                {
                    const std::uint32_t gap = now - last_event_ms;
                    if (gap > maximum_event_gap_ms)
                    {
                        maximum_event_gap_ms = gap;
                    }
                }
                last_event_ms = now;
                ++event_samples;
            }
        }
        else if (finishing)
        {
            ++late_event;
        }
    }

    /** @brief QoS event copy를 목표 분모까지만 main thread에서 계수합니다. */
    void onConnectionEvent(const nucode::ble::BLENordicConnectionEventReport &report,
                           void *context)
    {
        static_cast<void>(report);
        static_cast<void>(context);
        checkMainContext();
        if (measurement_enabled && qos_samples < qos_target)
        {
            ++qos_samples;
        }
        else if (finishing)
        {
            ++late_qos;
        }
    }

    /** @brief 40-channel survey copy의 유한 표본을 계수합니다. */
    void onSurvey(const nucode::ble::BLENordicChannelSurveyReport &report,
                  void *context)
    {
        static_cast<void>(context);
        checkMainContext();
        bool available = false;
        for (std::size_t index = 0U;
             index < nucode::ble::BLENordicChannelSurveyReport::channel_count;
             ++index)
        {
            if (report.channel_energy_dbm[index] !=
                nucode::ble::BLENordicChannelSurveyReport::unavailable)
            {
                available = true;
                break;
            }
        }
        if (!available)
        {
            fail("survey_empty");
            return;
        }
        if (measurement_enabled && survey_samples < survey_target)
        {
            ++survey_samples;
        }
        else if (finishing)
        {
            ++late_survey;
        }
    }

    /** @brief controller clock anchor의 gap과 wrap projection을 검증합니다. */
    void onAnchor(const nucode::ble::BLENordicAnchorPointReport &report,
                  void *context)
    {
        static_cast<void>(context);
        checkMainContext();
        if (measurement_enabled && anchor_samples < anchor_target)
        {
            if (last_anchor_us != 0U)
            {
                const std::uint64_t gap = report.controller_clock_us - last_anchor_us;
                if (gap > maximum_anchor_gap_us)
                {
                    maximum_anchor_gap_us = static_cast<std::uint32_t>(gap);
                }
            }
            last_anchor_us = report.controller_clock_us;
            ++anchor_samples;
            if (!projection_wrap_pass)
            {
                nucode::ble::BLENordicAnchorPointReport wrapped = report;
                wrapped.event_counter = UINT16_MAX;
                std::uint64_t projected = 0U;
                projection_wrap_pass = BLENordic.projectAnchorPoint(
                    wrapped, 0U, llpm_interval_us, projected) &&
                    projected == report.controller_clock_us + llpm_interval_us;
            }
        }
        else if (finishing)
        {
            ++late_anchor;
        }
    }

    /** @brief system workqueue radio prepare callback을 유한 계수합니다. */
    void onRadioPrepare(nucode::ble::BLEConnectionHandle connection, void *context)
    {
        static_cast<void>(connection);
        static_cast<void>(context);
        if (measurement_enabled && prepare_samples < prepare_target)
        {
            ++prepare_samples;
        }
        else if (finishing)
        {
            ++late_prepare;
        }
    }

    /** @brief exact-name scan 결과를 한 번 연결합니다. */
    void onScanResult(const nucode::ble::BLEScanResult &result, void *context)
    {
        static_cast<void>(context);
        checkMainContext();
#if defined(NUCODE_M32_NORDIC_CENTRAL)
        if (!connected && !BLEConnection.connecting())
        {
            if (!BLEScan.stop() ||
                !BLEConnection.connect(result.address, connection_handle))
            {
                fail("connect", BLEDevice.lastDriverError());
            }
        }
#else
        static_cast<void>(result);
#endif
    }

    /** @brief 실제 2M PHY가 확인된 central에서 LLPM 요청과 음수 경계를 실행합니다. */
    void requestLlpmIfReady()
    {
#if defined(NUCODE_M32_NORDIC_CENTRAL)
        if (connected && !llpm_requested &&
            BLEConnection.phy(connection_handle) == nucode::ble::BLEPhy::le_2m)
        {
            invalid_llpm_rejected = !BLENordic.requestLlpmInterval(
                connection_handle, 1500U);
            llpm_requested = true;
            if (!invalid_llpm_rejected ||
                !BLENordic.requestLlpmInterval(connection_handle, 1000U))
            {
                fail("llpm_request", BLEDevice.lastDriverError());
            }
        }
#endif
    }

    /** @brief callback 유무와 무관하게 실제 controller interval로 LLPM 전환을 확인합니다. */
    void observeLlpmInterval()
    {
        if (!connected || llpm_ready)
        {
            return;
        }
        nucode::ble::BLEConnectionParameters parameters;
        if (BLEConnection.parameters(connection_handle, parameters) &&
            parameters.interval_us <= 1000U)
        {
            llpm_interval_us = parameters.interval_us;
            llpm_ready = true;
        }
    }

    /** @brief 연결·2M PHY·LLPM·peer loss 수명주기를 처리합니다. */
    void onBleEvent(const nucode::ble::BLEEventInfo &information, void *context)
    {
        static_cast<void>(context);
        checkMainContext();
        if (information.event == nucode::ble::BLEEvent::connected)
        {
            connected = true;
            connection_handle = information.connection;
            invalid_event_task_rejected = !BLENordic.setConnectionEventTrigger(
                connection_handle, 0x1001U);
            const std::uint32_t task_address = nrf_egu_task_address_get(
                M32_NORDIC_EGU, NRF_EGU_TASK_TRIGGER0);
            const bool first = BLENordic.setConnectionEventTrigger(
                connection_handle, task_address);
            const bool second = BLENordic.setConnectionEventTrigger(
                connection_handle, task_address);
            duplicate_reservation_bounded = first && !second;
        }
        else if (information.event == nucode::ble::BLEEvent::phy_changed &&
                 information.connection == connection_handle)
        {
            requestLlpmIfReady();
        }
        else if (information.event == nucode::ble::BLEEvent::parameters_changed &&
                 information.connection == connection_handle)
        {
            nucode::ble::BLEConnectionParameters parameters;
            if (!BLEConnection.parameters(connection_handle, parameters))
            {
                fail("parameters", BLEDevice.lastDriverError());
                return;
            }
            if (parameters.interval_us <= 1000U)
            {
                llpm_interval_us = parameters.interval_us;
                llpm_ready = true;
            }
        }
        else if (information.event == nucode::ble::BLEEvent::disconnected)
        {
            connected = false;
            if (!stop_requested && !session_complete)
            {
                fail("peer_loss");
                return;
            }
            if (!stop_requested)
            {
                return;
            }
            nucode::ble::BLENordicAnchorPointReport stale;
            if (BLENordic.readAnchorPointReport(stale) ||
                BLENordic.setConnectionEventTrigger(connection_handle, 0U))
            {
                fail("stale_sample");
                return;
            }
            Serial.print(protocol);
            Serial.print("|STOPPED|role=");
            Serial.print(roleName());
            Serial.print("|cleanup=pass");
            printSuffix();
            Serial.println();
            stop_requested = false;
        }
    }

    /** @brief START record의 nonce와 exact revision을 검증합니다. */
    bool acceptStart()
    {
        const std::size_t prefix_length = ::strlen(start_prefix);
        if (::strncmp(command, start_prefix, prefix_length) != 0)
        {
            return false;
        }
        const char *cursor = command + prefix_length;
        for (std::size_t index = 0U; index < nonce_length; ++index)
        {
            const char value = cursor[index];
            if (!((value >= '0' && value <= '9') ||
                  (value >= 'a' && value <= 'f')))
            {
                return false;
            }
        }
        constexpr char core_prefix[] = "|core=";
        if (::strncmp(cursor + nonce_length, core_prefix,
                      sizeof(core_prefix) - 1U) != 0 ||
            ::strcmp(cursor + nonce_length + sizeof(core_prefix) - 1U,
                     M32_NORDIC_CORE_REVISION) != 0)
        {
            return false;
        }
        ::memcpy(nonce, cursor, nonce_length);
        nonce[nonce_length] = '\0';
        return true;
    }

    /** @brief Nordic extension을 enable하고 역할별 BLE radio를 시작합니다. */
    void startProtocol()
    {
        invalid_survey_rejected = !BLENordic.setChannelSurvey(true, 2999U);
        const bool invalid_radio = !BLENordic.setRadioNotification(true, 0U);
        nucode::ble::BLENordicAnchorPointReport invalid_reference;
        std::uint64_t invalid_projection = 0U;
        const bool invalid_projection_rejected = !BLENordic.projectAnchorPoint(
            invalid_reference, 1U, 1000U, invalid_projection);
        acl_support = BLENordic.flushableAclSupport();
        if (!invalid_survey_rejected || !invalid_radio ||
            !invalid_projection_rejected || !acl_support.controller_experimental ||
            acl_support.host_transmit_path || acl_support.usable ||
            !BLENordic.setLlpmMode(true) ||
            !BLENordic.setConnectionEventReports(true) ||
            !BLENordic.setChannelSurvey(true, 50000U) ||
            !BLENordic.setAnchorPointReports(true) ||
            !BLENordic.setRadioNotification(true, 500U))
        {
            fail("extension_start", BLEDevice.lastDriverError());
            return;
        }
#if defined(NUCODE_M32_NORDIC_CENTRAL)
        if (!BLEScan.clearFilters() || !BLEScan.filterName(peer_name) ||
            !BLEScan.start(true))
#else
        if (!BLEAdvertising.clear() || !BLEAdvertising.setConnectable(true) ||
            !BLEAdvertising.setScanResponseName(true) ||
            !BLEAdvertising.start())
#endif
        {
            fail("radio_start", BLEDevice.lastDriverError());
            return;
        }
        started = true;
        deadline_ms = k_uptime_get() + session_timeout_ms;
        progress_deadline_ms = k_uptime_get() + 5000;
        Serial.print(protocol);
        Serial.print("|BEGIN|role=");
        Serial.print(roleName());
        printSuffix();
        Serial.println();
    }

    /** @brief 의도한 queue overflow 뒤 exact 측정 분모를 0에서 시작합니다. */
    void beginMeasurement()
    {
        dropped_before_overflow = BLENordic.droppedReports();
        delay(75);
        BLEDevice.poll();
        overflow_observed = BLENordic.droppedReports() > dropped_before_overflow;
        if (!overflow_observed)
        {
            fail("overflow_missing");
            return;
        }
        qos_samples = 0U;
        survey_samples = 0U;
        anchor_samples = 0U;
        event_samples = 0U;
        prepare_samples = 0U;
        last_event_ms = 0U;
        maximum_event_gap_ms = 0U;
        last_anchor_us = 0U;
        maximum_anchor_gap_us = 0U;
        measurement_enabled = true;
    }

    /** @brief 모든 extension을 해제해 late callback과 취소 경계를 검사합니다. */
    void beginDisableCheck()
    {
        measurement_enabled = false;
        if (!BLENordic.setConnectionEventReports(false) ||
            !BLENordic.setConnectionEventTrigger(connection_handle, 0U) ||
            !BLENordic.setRadioNotification(false) ||
            !BLENordic.setAnchorPointReports(false) ||
            !BLENordic.setChannelSurvey(false))
        {
            fail("extension_stop", BLEDevice.lastDriverError());
            return;
        }
        nrf_egu_event_clear(M32_NORDIC_EGU, NRF_EGU_EVENT_TRIGGERED0);
        finishing = true;
        disable_deadline_ms = k_uptime_get() + 50;
    }

    /** @brief role별 유한 분모와 negative·지원 경계를 출력합니다. */
    void printResult()
    {
        disabled_callback_quiet = late_qos == 0U && late_survey == 0U &&
                                  late_anchor == 0U && late_event == 0U &&
                                  late_prepare == 0U;
        if (!disabled_callback_quiet || !projection_wrap_pass ||
            maximum_anchor_gap_us > 5000U || maximum_event_gap_ms > 5U)
        {
            fail("result_boundary");
            return;
        }
        Serial.print(protocol);
        Serial.print("|RESULT|role=");
        Serial.print(roleName());
        Serial.print("|qos=");
        Serial.print(qos_samples);
        Serial.print("|survey=");
        Serial.print(survey_samples);
        Serial.print("|anchors=");
        Serial.print(anchor_samples);
        Serial.print("|events=");
        Serial.print(event_samples);
        Serial.print("|prepares=");
        Serial.print(prepare_samples);
        Serial.print("|llpm_interval_us=");
        Serial.print(llpm_interval_us);
        Serial.print("|max_anchor_gap_us=");
        Serial.print(maximum_anchor_gap_us);
        Serial.print("|max_event_gap_ms=");
        Serial.print(maximum_event_gap_ms);
        Serial.print("|iterations=");
        Serial.print(iteration_target);
        Serial.print("|overflow_observed=");
        Serial.print(overflow_observed ? 1 : 0);
        Serial.print("|invalid_llpm_rejected=");
        Serial.print(invalid_llpm_rejected ? 1 : 0);
        Serial.print("|invalid_survey_rejected=");
        Serial.print(invalid_survey_rejected ? 1 : 0);
        Serial.print("|invalid_event_task_rejected=");
        Serial.print(invalid_event_task_rejected ? 1 : 0);
        Serial.print("|duplicate_reservation_bounded=");
        Serial.print(duplicate_reservation_bounded ? 1 : 0);
        Serial.print("|disabled_callback_quiet=");
        Serial.print(disabled_callback_quiet ? 1 : 0);
        Serial.print("|projection_wrap_pass=");
        Serial.print(projection_wrap_pass ? 1 : 0);
        Serial.print("|acl_controller_experimental=");
        Serial.print(acl_support.controller_experimental ? 1 : 0);
        Serial.print("|acl_host_transmit_path=");
        Serial.print(acl_support.host_transmit_path ? 1 : 0);
        Serial.print("|acl_usable=");
        Serial.print(acl_support.usable ? 1 : 0);
        Serial.print("|callback_context=");
        Serial.print(callback_context_valid ? "pass" : "fail");
        printSuffix();
        Serial.println();
        Serial.print(protocol);
        Serial.print("|END|role=");
        Serial.print(roleName());
        Serial.print("|status=pass");
        printSuffix();
        Serial.println();
        session_complete = true;
    }

    /** @brief 개발 및 실패 분석을 위해 현재 유한 분모를 주기적으로 출력합니다. */
    void printProgress()
    {
        Serial.print(protocol);
        Serial.print("|PROGRESS|role=");
        Serial.print(roleName());
        Serial.print("|connected=");
        Serial.print(connected ? 1 : 0);
        Serial.print("|llpm_ready=");
        Serial.print(llpm_ready ? 1 : 0);
        Serial.print("|phy=");
        Serial.print(static_cast<unsigned int>(BLEConnection.phy(connection_handle)));
#if defined(NUCODE_M32_NORDIC_CENTRAL)
        Serial.print("|llpm_requested=");
        Serial.print(llpm_requested ? 1 : 0);
#endif
        Serial.print("|measuring=");
        Serial.print(measurement_enabled ? 1 : 0);
        Serial.print("|qos=");
        Serial.print(qos_samples);
        Serial.print("|survey=");
        Serial.print(survey_samples);
        Serial.print("|anchors=");
        Serial.print(anchor_samples);
        Serial.print("|events=");
        Serial.print(event_samples);
        Serial.print("|prepares=");
        Serial.print(prepare_samples);
        printSuffix();
        Serial.println();
    }

    /** @brief PROBE·START·STOP 명령을 고정 길이로 처리합니다. */
    void processCommand()
    {
        if (::strcmp(command, "M32NOR|1|PROBE") == 0)
        {
            Serial.print(protocol);
            Serial.print("|READY|role=");
            Serial.print(roleName());
            Serial.print("|core=");
            Serial.println(M32_NORDIC_CORE_REVISION);
            return;
        }
        if (!started && acceptStart())
        {
            startProtocol();
            return;
        }
        if (session_complete &&
            ::strncmp(command, stop_prefix, sizeof(stop_prefix) - 1U) == 0 &&
            ::strcmp(command + sizeof(stop_prefix) - 1U, nonce) == 0)
        {
            stop_requested = true;
            if (connected)
            {
                if (!BLEConnection.disconnect(connection_handle))
                {
                    fail("disconnect", BLEDevice.lastDriverError());
                }
            }
            else
            {
                Serial.print(protocol);
                Serial.print("|STOPPED|role=");
                Serial.print(roleName());
                Serial.print("|cleanup=pass");
                printSuffix();
                Serial.println();
                stop_requested = false;
            }
            return;
        }
        fail("command");
    }

    /** @brief CR/LF serial 명령을 overflow 없이 수집합니다. */
    void pollSerial()
    {
        while (Serial.available() > 0)
        {
            const int incoming = Serial.read();
            if (incoming == '\r')
            {
                continue;
            }
            if (incoming == '\n')
            {
                command[command_length] = '\0';
                processCommand();
                command_length = 0U;
                continue;
            }
            if (incoming < 0 || command_length + 1U >= sizeof(command))
            {
                command_length = 0U;
                fail("command_length");
                continue;
            }
            command[command_length++] = static_cast<char>(incoming);
        }
    }
}

void setup()
{
    Serial.begin(115200);
    main_thread = k_current_get();
    IRQ_CONNECT(DT_IRQN(M32_NORDIC_EGU_NODE), 5, onEguEvent, nullptr, 0);
    nrf_egu_int_enable(M32_NORDIC_EGU, NRF_EGU_INT_TRIGGERED0);
    irq_enable(DT_IRQN(M32_NORDIC_EGU_NODE));
    BLEDevice.onEventInfo(onBleEvent);
    BLEScan.onResult(onScanResult);
    BLENordic.onConnectionEvent(onConnectionEvent);
    BLENordic.onChannelSurvey(onSurvey);
    BLENordic.onAnchorPoint(onAnchor);
    BLENordic.onRadioPrepare(onRadioPrepare);
    if (!BLEDevice.begin(peer_name))
    {
        fail("ble_begin", BLEDevice.lastDriverError());
    }
}

void loop()
{
    BLEDevice.poll();
    pollSerial();
    requestLlpmIfReady();
    observeLlpmInterval();
    if (failed)
    {
        return;
    }
    if (started && llpm_ready && !overflow_observed && !measurement_enabled)
    {
        beginMeasurement();
    }
    if (measurement_enabled && qos_samples >= qos_target &&
        survey_samples >= survey_target && anchor_samples >= anchor_target &&
        event_samples >= event_target && prepare_samples >= prepare_target)
    {
        beginDisableCheck();
    }
    if (finishing && !session_complete && k_uptime_get() >= disable_deadline_ms)
    {
        finishing = false;
        printResult();
    }
    if (started && !session_complete && k_uptime_get() >= progress_deadline_ms)
    {
        printProgress();
        progress_deadline_ms = k_uptime_get() + 5000;
    }
    if (started && !session_complete && k_uptime_get() >= deadline_ms)
    {
        fail("timeout");
    }
    delay(1);
}
