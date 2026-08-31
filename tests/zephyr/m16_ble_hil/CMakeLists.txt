# SPDX-License-Identifier: MIT

cmake_minimum_required(VERSION 3.20.0)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(nucode_m16_ble_hil)

# @brief 플랫폼 기본 sysbuild에서도 Twister의 role별 cache 변수를 현재 image로 가져옵니다.
zephyr_get(M16_ROLE)

get_filename_component(NUCODE_ROOT "${CMAKE_CURRENT_LIST_DIR}/../../.." ABSOLUTE)
target_sources(app PRIVATE
  src/main.cpp
  "${NUCODE_ROOT}/libraries/NUCODE_BLE/src/NUCODE_BLE.cpp"
  "${NUCODE_ROOT}/libraries/NUCODE_BLE/src/internal/NUCODE_BLE_Stack.cpp"
)
target_include_directories(app PRIVATE
  "${NUCODE_ROOT}/libraries/NUCODE_BLE/src"
)

if("${M16_ROLE}" STREQUAL "central")
  target_compile_definitions(app PRIVATE NUCODE_M16_CENTRAL=1)
elseif(NOT "${M16_ROLE}" STREQUAL "peripheral")
  message(FATAL_ERROR "M16_ROLE must be peripheral or central")
endif()

