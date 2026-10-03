# SPDX-License-Identifier: MIT

cmake_minimum_required(VERSION 3.20.0)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(nucode_m32_mesh_update_contract)

get_filename_component(NUCODE_ROOT "${CMAKE_CURRENT_LIST_DIR}/../../.." ABSOLUTE)
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
