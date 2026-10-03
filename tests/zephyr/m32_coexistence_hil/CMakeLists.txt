# SPDX-License-Identifier: MIT

cmake_minimum_required(VERSION 3.20.0)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(nucode_m32_coexistence_hil)

zephyr_get(M32_COEX_SCENARIO)
zephyr_get(M32_COEX_ROLE)
get_filename_component(NUCODE_ROOT "${CMAKE_CURRENT_LIST_DIR}/../../.." ABSOLUTE)

execute_process(
    COMMAND git -c "safe.directory=${NUCODE_ROOT}" -C "${NUCODE_ROOT}" rev-parse HEAD
    RESULT_VARIABLE revision_result
    OUTPUT_VARIABLE M32_COEX_CORE_REVISION
    ERROR_VARIABLE revision_error
    OUTPUT_STRIP_TRAILING_WHITESPACE
)
string(LENGTH "${M32_COEX_CORE_REVISION}" revision_length)
if(NOT revision_result EQUAL 0 OR NOT revision_length EQUAL 40 OR
   NOT M32_COEX_CORE_REVISION MATCHES "^[0-9a-f]+$")
    message(FATAL_ERROR "M32 W10 Core revision query failed: ${revision_error}")
endif()

target_sources(app PRIVATE src/main.cpp)
target_include_directories(app PRIVATE
    "${NUCODE_ROOT}/libraries/NUCODE_BLE/src"
    "${NUCODE_ROOT}/libraries/NUCODE_BLE_Mesh/src"
    "${NUCODE_ROOT}/libraries/NUCODE_Radio_Coexistence/src"
    "${NUCODE_ROOT}/libraries/NUCODE_Radio_IEEE802154/src"
    "${NUCODE_ROOT}/libraries/NUCODE_Radio_ESB/src"
)
target_compile_definitions(app PRIVATE
    M32_COEX_CORE_REVISION="${M32_COEX_CORE_REVISION}"
)

if("${M32_COEX_SCENARIO}" STREQUAL "ble_154")
    target_compile_definitions(app PRIVATE NUCODE_M32_COEX_154=1)
elseif("${M32_COEX_SCENARIO}" STREQUAL "ble_esb")
    target_compile_definitions(app PRIVATE NUCODE_M32_COEX_ESB=1)
elseif("${M32_COEX_SCENARIO}" STREQUAL "ble_mesh")
    target_compile_definitions(app PRIVATE NUCODE_M32_COEX_MESH=1)
else()
    message(FATAL_ERROR "M32_COEX_SCENARIO must be ble_154, ble_esb, or ble_mesh")
endif()

if("${M32_COEX_ROLE}" STREQUAL "dut")
    target_compile_definitions(app PRIVATE NUCODE_M32_COEX_DUT=1)
    target_sources(app PRIVATE
        "${NUCODE_ROOT}/libraries/NUCODE_BLE/src/NUCODE_BLE.cpp"
        "${NUCODE_ROOT}/libraries/NUCODE_BLE/src/internal/NUCODE_BLE_Stack.cpp"
        "${NUCODE_ROOT}/libraries/NUCODE_Radio_Coexistence/src/NUCODE_Radio_Coexistence.cpp"
    )
elseif("${M32_COEX_ROLE}" STREQUAL "ble_peer")
    target_compile_definitions(app PRIVATE NUCODE_M32_COEX_BLE_PEER=1)
    target_sources(app PRIVATE
        "${NUCODE_ROOT}/libraries/NUCODE_BLE/src/NUCODE_BLE.cpp"
        "${NUCODE_ROOT}/libraries/NUCODE_BLE/src/internal/NUCODE_BLE_Stack.cpp"
    )
elseif("${M32_COEX_ROLE}" STREQUAL "radio_peer")
    if("${M32_COEX_SCENARIO}" STREQUAL "ble_mesh")
        message(FATAL_ERROR "ble_mesh uses mesh_peer")
    endif()
    target_compile_definitions(app PRIVATE NUCODE_M32_COEX_RADIO_PEER=1)
elseif("${M32_COEX_ROLE}" STREQUAL "mesh_peer")
    if(NOT "${M32_COEX_SCENARIO}" STREQUAL "ble_mesh")
        message(FATAL_ERROR "mesh_peer is valid only for ble_mesh")
    endif()
    target_compile_definitions(app PRIVATE NUCODE_M32_COEX_MESH_PEER=1)
else()
    message(FATAL_ERROR "M32_COEX_ROLE is invalid")
endif()

if("${M32_COEX_SCENARIO}" STREQUAL "ble_154" AND
   NOT "${M32_COEX_ROLE}" STREQUAL "ble_peer")
    target_sources(app PRIVATE
        "${NUCODE_ROOT}/libraries/NUCODE_Radio_IEEE802154/src/NUCODE_Radio_IEEE802154.cpp"
    )
elseif("${M32_COEX_SCENARIO}" STREQUAL "ble_esb" AND
       NOT "${M32_COEX_ROLE}" STREQUAL "ble_peer")
    target_sources(app PRIVATE
        "${NUCODE_ROOT}/libraries/NUCODE_Radio_ESB/src/NUCODE_Radio_ESB.cpp"
    )
elseif("${M32_COEX_SCENARIO}" STREQUAL "ble_mesh" AND
       NOT "${M32_COEX_ROLE}" STREQUAL "ble_peer")
    target_sources(app PRIVATE
        "${NUCODE_ROOT}/libraries/NUCODE_BLE_Mesh/src/NUCODE_BLE_Mesh.cpp"
        "${NUCODE_ROOT}/libraries/NUCODE_BLE_Mesh/src/NUCODE_BLE_Mesh_Composition.c"
    )
endif()
