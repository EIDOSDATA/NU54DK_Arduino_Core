# @brief 최종 Kconfig에서 연결형 Arduino Host+SDC의 ACL 흐름 제어를 검증합니다.
# @details 정책 심볼만 검사하지 않아 명시적인 override로 검사를 우회할 수 없습니다.
function(nucode_validate_ble_flow_control)
    if(CONFIG_NUCODE_ARDUINO_API AND CONFIG_BT AND CONFIG_BT_CONN AND
       CONFIG_BT_HCI_HOST AND CONFIG_HAS_BT_CTLR AND CONFIG_BT_LL_SOFTDEVICE AND
       NOT CONFIG_BT_HCI_RAW)
        if(NOT CONFIG_NUCODE_BLE_HOST_ACL_FLOW_CONTROL OR
           NOT CONFIG_BT_HCI_ACL_FLOW_CONTROL)
            message(FATAL_ERROR
                "[NUCODE:E_BLE_FLOW_CONTROL] Arduino Host+SDC requires controller-to-host ACL flow control"
            )
        endif()

        if(NOT DEFINED CONFIG_BT_BUF_ACL_RX_COUNT_EXTRA OR
           NOT "${CONFIG_BT_BUF_ACL_RX_COUNT_EXTRA}" MATCHES "^[0-9]+$")
            message(FATAL_ERROR
                "[NUCODE:E_BLE_FLOW_CONTROL] ACL RX EXTRA must be a resolved positive integer"
            )
        endif()
        if(CONFIG_BT_BUF_ACL_RX_COUNT_EXTRA LESS 1 OR
           CONFIG_BT_BUF_ACL_RX_COUNT_EXTRA GREATER 62)
            message(FATAL_ERROR
                "[NUCODE:E_BLE_FLOW_CONTROL] ACL RX EXTRA must be 1..62 with the SDK command-buffer limit of 64"
            )
        endif()
        if(NOT DEFINED CONFIG_BT_BUF_CMD_TX_COUNT OR
           NOT "${CONFIG_BT_BUF_CMD_TX_COUNT}" MATCHES "^[0-9]+$")
            message(FATAL_ERROR
                "[NUCODE:E_BLE_FLOW_CONTROL] CMD TX count must be a resolved positive integer"
            )
        endif()

        # @brief 고정 SDK의 RX_COUNT=EXTRA+1보다 CMD 수가 커야 합니다.
        math(EXPR nucode_minimum_command_buffers "${CONFIG_BT_BUF_ACL_RX_COUNT_EXTRA} + 2")
        if(CONFIG_BT_BUF_CMD_TX_COUNT LESS nucode_minimum_command_buffers OR
           CONFIG_BT_BUF_CMD_TX_COUNT GREATER 64)
            message(FATAL_ERROR
                "[NUCODE:E_BLE_FLOW_CONTROL] CMD TX count ${CONFIG_BT_BUF_CMD_TX_COUNT} must be ${nucode_minimum_command_buffers}..64 for ACL RX EXTRA ${CONFIG_BT_BUF_ACL_RX_COUNT_EXTRA}"
            )
        endif()
    elseif(CONFIG_NUCODE_BLE_HOST_ACL_FLOW_CONTROL)
        message(FATAL_ERROR
            "[NUCODE:E_BLE_FLOW_CONTROL] Arduino ACL flow-control policy is enabled outside its supported scope"
        )
    endif()
endfunction()

nucode_validate_ble_flow_control()
