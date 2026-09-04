cmake_minimum_required(VERSION 3.20.0)
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(v04pair LANGUAGES C CXX)
execute_process(COMMAND git -C ${CMAKE_CURRENT_SOURCE_DIR} rev-parse HEAD
                OUTPUT_VARIABLE HIL_REVISION OUTPUT_STRIP_TRAILING_WHITESPACE
                COMMAND_ERROR_IS_FATAL ANY)
target_compile_definitions(app PRIVATE NUCODE_HIL_CORE_REVISION="${HIL_REVISION}")
target_sources(app PRIVATE src/main.cpp src/serial_hil.cpp)
