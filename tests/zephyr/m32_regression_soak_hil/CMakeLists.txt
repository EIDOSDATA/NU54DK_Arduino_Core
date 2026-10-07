# SPDX-License-Identifier: MIT

cmake_minimum_required(VERSION 3.20.0)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(nucode_m32_regression_soak_hil)

zephyr_get(M32_W11_ROLE)
get_filename_component(NUCODE_ROOT "${CMAKE_CURRENT_LIST_DIR}/../../.." ABSOLUTE)
get_filename_component(M32_W11_BOARD_ROOT
    "${NUCODE_ROOT}/board_package/NU54DK_Zephyr_DTS" ABSOLUTE)
get_filename_component(M32_W11_NRF_ROOT "${ZEPHYR_BASE}/../nrf" ABSOLUTE)

function(m32_w11_git_revision output_name repository)
    execute_process(
        COMMAND git -c "safe.directory=${repository}" -C "${repository}" rev-parse HEAD
        RESULT_VARIABLE revision_result
        OUTPUT_VARIABLE revision
        ERROR_VARIABLE revision_error
        OUTPUT_STRIP_TRAILING_WHITESPACE
    )
    string(LENGTH "${revision}" revision_length)
    if(NOT revision_result EQUAL 0 OR NOT revision_length EQUAL 40 OR
       NOT revision MATCHES "^[0-9a-f]+$")
        message(FATAL_ERROR "M32 W11 revision query failed for ${repository}: ${revision_error}")
    endif()
    set(${output_name} "${revision}" PARENT_SCOPE)
endfunction()

m32_w11_git_revision(M32_W11_CORE_REVISION "${NUCODE_ROOT}")
m32_w11_git_revision(M32_W11_BOARD_REVISION "${M32_W11_BOARD_ROOT}")
m32_w11_git_revision(M32_W11_NCS_REVISION "${M32_W11_NRF_ROOT}")
m32_w11_git_revision(M32_W11_ZEPHYR_REVISION "${ZEPHYR_BASE}")

set(M32_W11_FIRMWARE_SOURCE
    "${CMAKE_CURRENT_LIST_DIR}/../m28_ble_3board_hil/src/main.cpp")
find_package(Python3 REQUIRED COMPONENTS Interpreter)
set(M32_W11_BUILD_RECORD "${CMAKE_BINARY_DIR}/m33_w06_build_record.json")
set(M32_W11_MANIFEST_VARIABLES "${CMAKE_BINARY_DIR}/m33_w06_manifest.cmake")
execute_process(
    COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_LIST_DIR}/m33_w06_manifest.py"
        --core "${NUCODE_ROOT}"
        --board "${M32_W11_BOARD_ROOT}"
        --application "${CMAKE_CURRENT_LIST_DIR}"
        --firmware "${M32_W11_FIRMWARE_SOURCE}"
        --core-revision "${M32_W11_CORE_REVISION}"
        --board-revision "${M32_W11_BOARD_REVISION}"
        --ncs-revision "${M32_W11_NCS_REVISION}"
        --zephyr-revision "${M32_W11_ZEPHYR_REVISION}"
        --role "${M32_W11_ROLE}"
        --json-output "${M32_W11_BUILD_RECORD}"
        --cmake-output "${M32_W11_MANIFEST_VARIABLES}"
    RESULT_VARIABLE M32_W11_MANIFEST_RESULT
    ERROR_VARIABLE M32_W11_MANIFEST_ERROR
)
if(NOT M32_W11_MANIFEST_RESULT EQUAL 0)
    message(FATAL_ERROR "M33 W06 manifest generation failed: ${M32_W11_MANIFEST_ERROR}")
endif()
include("${M32_W11_MANIFEST_VARIABLES}")

target_sources(app PRIVATE
    "${CMAKE_CURRENT_LIST_DIR}/../m28_ble_3board_hil/src/main.cpp"
    "${NUCODE_ROOT}/libraries/NUCODE_BLE/src/NUCODE_BLE_GAP.cpp"
    "${NUCODE_ROOT}/libraries/NUCODE_BLE/src/internal/gap/GapValues.cpp"
    "${NUCODE_ROOT}/libraries/NUCODE_BLE/src/internal/gap/GapAdvertising.cpp"
    "${NUCODE_ROOT}/libraries/NUCODE_BLE/src/internal/gap/GapExtendedAdvertising.cpp"
    "${NUCODE_ROOT}/libraries/NUCODE_BLE/src/internal/gap/GapPeriodicAdvertising.cpp"
    "${NUCODE_ROOT}/libraries/NUCODE_BLE/src/internal/gap/GapPawr.cpp"
    "${NUCODE_ROOT}/libraries/NUCODE_BLE/src/internal/gap/GapScanning.cpp"
    "${NUCODE_ROOT}/libraries/NUCODE_BLE/src/internal/gap/GapConnection.cpp"
    "${NUCODE_ROOT}/libraries/NUCODE_BLE/src/NUCODE_BLE_GATT.cpp"
    "${NUCODE_ROOT}/libraries/NUCODE_BLE/src/internal/gatt/GattDatabase.cpp"
    "${NUCODE_ROOT}/libraries/NUCODE_BLE/src/internal/gatt/GattCache.cpp"
    "${NUCODE_ROOT}/libraries/NUCODE_BLE/src/internal/gatt/GattServer.cpp"
    "${NUCODE_ROOT}/libraries/NUCODE_BLE/src/internal/gatt/GattClient.cpp"
    "${NUCODE_ROOT}/libraries/NUCODE_BLE/src/internal/NUCODE_BLE_Stack.cpp"
)
target_include_directories(app PRIVATE
    "${NUCODE_ROOT}/libraries/NUCODE_BLE/src"
)
target_compile_definitions(app PRIVATE
    M32_W11_CORE_REVISION="${M32_W11_CORE_REVISION}"
    M32_W11_BOARD_REVISION="${M32_W11_BOARD_REVISION}"
    M32_W11_NCS_REVISION="${M32_W11_NCS_REVISION}"
    M32_W11_ZEPHYR_REVISION="${M32_W11_ZEPHYR_REVISION}"
    M32_W11_CORE_SOURCE_SHA256="${M32_W11_CORE_SOURCE_SHA256}"
    M32_W11_APPLICATION_SOURCE_SHA256="${M32_W11_APPLICATION_SOURCE_SHA256}"
    M32_W11_BOARD_SOURCE_SHA256="${M32_W11_BOARD_SOURCE_SHA256}"
    M32_W11_FIRMWARE_SOURCE_SHA256="${M32_W11_FIRMWARE_SOURCE_SHA256}"
    M32_W11_APPLICATION_CMAKE_SHA256="${M32_W11_APPLICATION_CMAKE_SHA256}"
    M32_W11_APPLICATION_CONFIG_SHA256="${M32_W11_APPLICATION_CONFIG_SHA256}"
    M32_W11_SOURCE_MANIFEST_SHA256="${M32_W11_SOURCE_MANIFEST_SHA256}"
    NUCODE_M28_B3_TEST_SOAK=1
    NUCODE_M32_W11_SOAK=1
)

if("${M32_W11_ROLE}" STREQUAL "peripheral")
    target_compile_definitions(app PRIVATE NUCODE_M28_B3_ROLE_PERIPHERAL=1)
elseif("${M32_W11_ROLE}" STREQUAL "mixed")
    target_compile_definitions(app PRIVATE NUCODE_M28_B3_ROLE_MIXED=1)
elseif("${M32_W11_ROLE}" STREQUAL "central")
    target_compile_definitions(app PRIVATE NUCODE_M28_B3_ROLE_CENTRAL=1)
else()
    message(FATAL_ERROR "M32_W11_ROLE must be peripheral, mixed, or central")
endif()
