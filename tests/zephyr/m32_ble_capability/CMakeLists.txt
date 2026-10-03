# SPDX-License-Identifier: MIT

cmake_minimum_required(VERSION 3.20.0)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(nucode_m32_ble_capability)

get_filename_component(NUCODE_ROOT "${CMAKE_CURRENT_LIST_DIR}/../../.." ABSOLUTE)
get_filename_component(NCS_ROOT "${ZEPHYR_BASE}/.." ABSOLUTE)

# @brief 실행 image가 exact source revision을 자체 보고하게 합니다.
function(m32_git_revision repository output_name)
    execute_process(
        COMMAND git -c "safe.directory=${repository}" -C "${repository}" rev-parse HEAD
        RESULT_VARIABLE command_result
        OUTPUT_VARIABLE revision
        ERROR_VARIABLE command_error
        OUTPUT_STRIP_TRAILING_WHITESPACE
    )
    string(LENGTH "${revision}" revision_length)
    if(NOT command_result EQUAL 0 OR
       NOT revision_length EQUAL 40 OR
       NOT revision MATCHES "^[0-9a-f]+$")
        message(FATAL_ERROR "M32 revision query failed for ${repository}: ${command_error}")
    endif()
    set(${output_name} "${revision}" PARENT_SCOPE)
endfunction()

m32_git_revision("${NUCODE_ROOT}" M32_CORE_REVISION)
m32_git_revision("${NUCODE_ROOT}/board_package/NU54DK_Zephyr_DTS" M32_BOARD_REVISION)
m32_git_revision("${NCS_ROOT}/nrf" M32_NCS_REVISION)
m32_git_revision("${NCS_ROOT}/zephyr" M32_ZEPHYR_REVISION)

if(CONFIG_BT_LE_EXTENDED_FEAT_SET)
    set(M32_RESOURCE_PROFILE "ble_extended")
else()
    set(M32_RESOURCE_PROFILE "ble_baseline")
endif()

target_sources(app PRIVATE src/main.cpp)
target_compile_definitions(app PRIVATE
    M32_CORE_REVISION="${M32_CORE_REVISION}"
    M32_BOARD_REVISION="${M32_BOARD_REVISION}"
    M32_NCS_REVISION="${M32_NCS_REVISION}"
    M32_ZEPHYR_REVISION="${M32_ZEPHYR_REVISION}"
    M32_RESOURCE_PROFILE="${M32_RESOURCE_PROFILE}"
)
