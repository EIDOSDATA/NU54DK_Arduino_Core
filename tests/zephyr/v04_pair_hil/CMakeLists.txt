cmake_minimum_required(VERSION 3.20.0)
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(v04pair LANGUAGES C CXX)
include(${CMAKE_CURRENT_SOURCE_DIR}/read_revision.cmake)
nucode_hil_revision("${CMAKE_CURRENT_SOURCE_DIR}/../../.." HIL_REVISION)
target_compile_definitions(app PRIVATE NUCODE_HIL_CORE_REVISION="${HIL_REVISION}")
target_sources(app PRIVATE src/main.cpp src/serial_hil.cpp src/fixture_hil.cpp
                           src/signal_hil.cpp)
