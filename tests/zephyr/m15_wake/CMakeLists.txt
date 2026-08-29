# SPDX-License-Identifier: MIT

cmake_minimum_required(VERSION 3.20.0)

find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(nucode_m15_wake)

get_filename_component(NUCODE_CORE_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../../.." ABSOLUTE)

target_sources(app PRIVATE
  src/main.cpp
  "${NUCODE_CORE_ROOT}/libraries/NUCODE_NU54DK/src/NUCODE_NU54DK.cpp"
)

target_include_directories(app PRIVATE
  "${NUCODE_CORE_ROOT}/libraries/NUCODE_NU54DK/src"
)
