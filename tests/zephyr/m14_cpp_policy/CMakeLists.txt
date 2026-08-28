# SPDX-License-Identifier: MIT

cmake_minimum_required(VERSION 3.20.0)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(nucode_m14_cpp_policy)

get_filename_component(NUCODE_M14_ROOT "${CMAKE_CURRENT_LIST_DIR}/../../.." ABSOLUTE)

target_sources(app PRIVATE
  src/main.cpp
  "${NUCODE_M14_ROOT}/cores/arduino/diagnostics.cpp"
  "${NUCODE_M14_ROOT}/cores/arduino/wiring_random.cpp"
)

target_include_directories(app PRIVATE
  "${NUCODE_M14_ROOT}/cores/arduino"
  "${NUCODE_M14_ROOT}/variants/nu54dk"
  "${NUCODE_M14_ROOT}/third_party/ArduinoCore-API"
)
