# SPDX-License-Identifier: MIT

cmake_minimum_required(VERSION 3.20.0)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(nucode_m32_mesh_update_hil)

zephyr_get(M32_MESH_UPDATE_ROLE)
get_filename_component(NUCODE_ROOT "${CMAKE_CURRENT_LIST_DIR}/../../.." ABSOLUTE)

execute_process(
    COMMAND git -c "safe.directory=${NUCODE_ROOT}" -C "${NUCODE_ROOT}" rev-parse HEAD
    RESULT_VARIABLE revision_result
    OUTPUT_VARIABLE M32_MESH_UPDATE_CORE_REVISION
    ERROR_VARIABLE revision_error
    OUTPUT_STRIP_TRAILING_WHITESPACE
)
string(LENGTH "${M32_MESH_UPDATE_CORE_REVISION}" revision_length)
if(NOT revision_result EQUAL 0 OR NOT revision_length EQUAL 40 OR
   NOT M32_MESH_UPDATE_CORE_REVISION MATCHES "^[0-9a-f]+$")
    message(FATAL_ERROR "M32 W08 Core revision query failed: ${revision_error}")
endif()

target_sources(app PRIVATE
    src/main.cpp
    "${NUCODE_ROOT}/libraries/NUCODE_BLE_Mesh/src/NUCODE_BLE_Mesh.cpp"
    "${NUCODE_ROOT}/libraries/NUCODE_BLE_Mesh/src/NUCODE_BLE_Mesh_Composition.c"
    "${NUCODE_ROOT}/libraries/NUCODE_BLE_Mesh_Update/src/NUCODE_BLE_Mesh_Update.cpp"
)
target_include_directories(app PRIVATE
    "${NUCODE_ROOT}/libraries/NUCODE_BLE_Mesh/src"
    "${NUCODE_ROOT}/libraries/NUCODE_BLE_Mesh_Update/src"
)
target_compile_definitions(app PRIVATE
    M32_MESH_UPDATE_CORE_REVISION="${M32_MESH_UPDATE_CORE_REVISION}"
)

if("${M32_MESH_UPDATE_ROLE}" STREQUAL "blob_client")
    target_compile_definitions(app PRIVATE NUCODE_M32_BLOB_CLIENT=1)
elseif("${M32_MESH_UPDATE_ROLE}" STREQUAL "target_a")
    target_compile_definitions(app PRIVATE NUCODE_M32_BLOB_TARGET_A=1)
elseif("${M32_MESH_UPDATE_ROLE}" STREQUAL "target_b")
    target_compile_definitions(app PRIVATE NUCODE_M32_BLOB_TARGET_B=1)
else()
    message(FATAL_ERROR "M32_MESH_UPDATE_ROLE must be blob_client, target_a, or target_b")
endif()
