# SPDX-License-Identifier: MIT

cmake_minimum_required(VERSION 3.20.0)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(nucode_m32_ble_advertising_hil)

zephyr_get(M32_ADV_ROLE)
get_filename_component(NUCODE_ROOT "${CMAKE_CURRENT_LIST_DIR}/../../.." ABSOLUTE)

execute_process(
    COMMAND git -c "safe.directory=${NUCODE_ROOT}" -C "${NUCODE_ROOT}" rev-parse HEAD
    RESULT_VARIABLE revision_result
    OUTPUT_VARIABLE M32_ADV_CORE_REVISION
    ERROR_VARIABLE revision_error
    OUTPUT_STRIP_TRAILING_WHITESPACE
)
string(LENGTH "${M32_ADV_CORE_REVISION}" revision_length)
if(NOT revision_result EQUAL 0 OR NOT revision_length EQUAL 40 OR
   NOT M32_ADV_CORE_REVISION MATCHES "^[0-9a-f]+$")
    message(FATAL_ERROR "M32 W04 advertising Core revision query failed: ${revision_error}")
endif()

target_sources(app PRIVATE
    src/main.cpp
    "${NUCODE_ROOT}/libraries/NUCODE_BLE/src/NUCODE_BLE_GAP.cpp"
    "${NUCODE_ROOT}/libraries/NUCODE_BLE/src/internal/gap/GapValues.cpp"
    "${NUCODE_ROOT}/libraries/NUCODE_BLE/src/internal/gap/GapAdvertising.cpp"
    "${NUCODE_ROOT}/libraries/NUCODE_BLE/src/internal/gap/GapExtendedAdvertising.cpp"
    "${NUCODE_ROOT}/libraries/NUCODE_BLE/src/internal/gap/GapPeriodicAdvertising.cpp"
    "${NUCODE_ROOT}/libraries/NUCODE_BLE/src/internal/gap/GapPawr.cpp"
    "${NUCODE_ROOT}/libraries/NUCODE_BLE/src/internal/gap/GapScanning.cpp"
    "${NUCODE_ROOT}/libraries/NUCODE_BLE/src/internal/gap/GapConnection.cpp"
    "${NUCODE_ROOT}/libraries/NUCODE_BLE/src/internal/NUCODE_BLE_Stack.cpp"
)
target_include_directories(app PRIVATE
    "${NUCODE_ROOT}/libraries/NUCODE_BLE/src"
)
target_compile_definitions(app PRIVATE
    M32_ADV_CORE_REVISION="${M32_ADV_CORE_REVISION}"
)

if("${M32_ADV_ROLE}" STREQUAL "advertiser_a")
    target_compile_definitions(app PRIVATE NUCODE_M32_ADV_ADVERTISER=1 NUCODE_M32_ADV_INDEX=0)
elseif("${M32_ADV_ROLE}" STREQUAL "advertiser_b")
    target_compile_definitions(app PRIVATE NUCODE_M32_ADV_ADVERTISER=1 NUCODE_M32_ADV_INDEX=1)
elseif(NOT "${M32_ADV_ROLE}" STREQUAL "scanner")
    message(FATAL_ERROR "M32_ADV_ROLE must be advertiser_a, advertiser_b, or scanner")
endif()
