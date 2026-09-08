cmake_minimum_required(VERSION 3.20.0)
set(CONF_FILE "${CMAKE_CURRENT_SOURCE_DIR}/../v04_pair_hil/prj.conf")
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(v04t13 LANGUAGES C CXX)
include(${CMAKE_CURRENT_SOURCE_DIR}/../v04_pair_hil/read_revision.cmake)
nucode_hil_revision("${CMAKE_CURRENT_SOURCE_DIR}/../../.." HIL_REVISION)
target_compile_definitions(app PRIVATE NUCODE_HIL_CORE_REVISION="${HIL_REVISION}")
target_include_directories(app PRIVATE src ../v04_pair_hil/src)
target_sources(app PRIVATE src/main.cpp src/wiring.cpp src/engine.cpp src/serial.cpp src/stream.cpp
    src/adc.cpp src/pwm.cpp src/audio.cpp src/pdm.cpp src/flow.cpp src/uart_fault.cpp src/twi_stuck.cpp
    src/spi_timing.cpp)
target_sources_ifdef(CONFIG_NUCODE_T13_POWER app PRIVATE src/power.cpp)
